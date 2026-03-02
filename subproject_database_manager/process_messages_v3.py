import sys
import os
import csv
import json
import base64
import time
import asyncio
import re
sys.path.append('../')
from models import call_claude_sonnet, call_gpt41_mini, call_gpt41_mini_async, call_gpt5, process_batch_parallel, process_batch_parallel_with_retry, process_batch_parallel_with_retry_sync, call_claude_with_cache, call_claude_with_cache_async
from categorization_prompts import get_categorization_prompt
from data_opinion_prompts import get_data_opinion_extraction_prompt, get_data_opinion_system_prompt, get_data_opinion_user_prompt
from interview_meeting_prompts import get_interview_extraction_prompt
from image_extraction_prompts import get_image_summary_prompt, get_image_structured_extraction_prompt, get_combined_image_extraction_prompt
from metrics_mapping_utils import append_new_metrics, collect_new_metrics_from_extractions, normalize_sources_in_csv
from chain_vocab import normalize_extracted_data


def _build_extracted_data_json(item: dict) -> str:
    """Build normalized extracted_data JSON from an extraction item."""
    extracted = {k: v for k, v in item.items() if k not in ['message_index', 'opinion_id']}
    normalize_extracted_data(extracted)
    return json.dumps(extracted, ensure_ascii=False)


# =============================================================================
# RULE-BASED CATEGORIZATION PRE-FILTER
# =============================================================================
# Handles obvious categories without LLM, saving ~$0.0004 per matched message

# Keywords/patterns for each category
GREETING_PATTERNS = [
    r'공유드립니다',
    r'Daily recap',
    r'일일\s*리캡',
    r'^안녕하세요',
    r'^좋은\s*(아침|저녁|오후)',
]

SCHEDULE_PATTERNS = [
    r'\(월\)\s*\d{1,2}:\d{2}',  # (월) 22:30
    r'\(화\)\s*\d{1,2}:\d{2}',
    r'\(수\)\s*\d{1,2}:\d{2}',
    r'\(목\)\s*\d{1,2}:\d{2}',
    r'\(금\)\s*\d{1,2}:\d{2}',
    r'경제\s*지표\s*일정',
    r'금주\s*일정',
    r'이번주\s*일정',
]

EVENT_PATTERNS = [
    r'포럼\s*개최',
    r'세미나\s*개최',
    r'컨퍼런스\s*개최',
    r'리서치\s*포럼',
    r'참가\s*신청',
    r'등록\s*링크',
]


def categorize_by_rules(text: str) -> tuple:
    """
    Attempt to categorize message using rule-based patterns.

    Returns:
        (category, confidence) if matched, (None, None) if LLM needed
    """
    if not text:
        return None, None

    text_lower = text.lower()
    text_len = len(text)

    # Greeting: Short message + contains greeting keywords
    if text_len < 100:
        for pattern in GREETING_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return 'greeting', 'high'

    # Schedule: Contains time patterns
    schedule_match_count = 0
    for pattern in SCHEDULE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            schedule_match_count += 1
    if schedule_match_count >= 2:  # Multiple time patterns = likely schedule
        return 'schedule', 'high'

    # Event announcement: Contains event keywords
    for pattern in EVENT_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return 'event_announcement', 'medium'

    # No match - need LLM
    return None, None


# =============================================================================
# IMAGE ROUTING — categorize-first to skip unnecessary vision calls
# =============================================================================

EXTRACTABLE_CATEGORIES = {'data_opinion', 'interview_meeting'}
NON_EXTRACTABLE_CATEGORIES = {'greeting', 'event_announcement', 'schedule', 'advertisement'}
MIN_TEXT_FOR_CATEGORIZATION = 50


def classify_for_image_routing(msg):
    """
    Pre-filter: determine routing for each message before LLM categorization.

    Returns:
        (route, category, reason)
        route: 'skip' | 'needs_image' | 'text_only' | 'pending_llm'
        category: pre-assigned category if route=='skip', else None
        reason: human-readable reason for the routing decision
    """
    text = msg.get('text', '')
    has_photo = bool(msg.get('photo'))

    # Rule-based first
    rule_cat, rule_conf = categorize_by_rules(text)
    if rule_cat:
        return 'skip', rule_cat, 'rule'

    # Short text + photo → needs image context to categorize
    if has_photo and len(text.strip()) < MIN_TEXT_FOR_CATEGORIZATION:
        return 'needs_image', None, 'short_text'

    # No photo → text-only categorization (cheap)
    if not has_photo:
        return 'text_only', None, 'no_photo'

    # Has photo + enough text → LLM will categorize on text alone first
    return 'pending_llm', None, 'has_photo_and_text'


async def categorize_batch_text_only(pending_items, max_concurrent=10):
    """
    Async parallel LLM categorization using text only (no images).

    Args:
        pending_items: list of (index_into_messages, msg_dict) tuples
        max_concurrent: concurrency limit

    Returns:
        list of (index, category_str_or_None) tuples
    """
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _categorize_single(idx, msg):
        async with semaphore:
            try:
                cat_prompt = get_categorization_prompt(msg['text'], msg['date'])
                cat_messages = [{"role": "user", "content": cat_prompt}]
                response = await call_gpt41_mini_async(cat_messages, temperature=0.7, max_tokens=4000)
                cat_text = _strip_code_block(response)
                category_data = json.loads(cat_text)
                return (idx, category_data.get('category', 'unknown'))
            except Exception as e:
                print(f"  [Categorize {idx}] Error: {e}")
                return (idx, None)

    tasks = [_categorize_single(idx, msg) for idx, msg in pending_items]
    return await asyncio.gather(*tasks)


def _run_async(coro):
    """Run an async coroutine from sync context, handling nested event loops."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import nest_asyncio
        nest_asyncio.apply()
    return asyncio.run(coro)


# =============================================================================
# CONFIGURATION
# =============================================================================
# Model to use for batch extraction (Step 4)
# Options: "gpt5", "gpt51", "gpt5_mini", "claude_sonnet", "claude_haiku"
def _strip_code_block(text: str) -> str:
    """Strip markdown code block fencing from LLM responses."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split('\n')
        # Remove opening line (```json or ```)
        start = 1
        # Remove closing ``` if present
        end = -1 if lines[-1].strip() == "```" else len(lines)
        text = '\n'.join(lines[start:end]).strip()
    return text


EXTRACTION_MODEL = "claude_sonnet"
FALLBACK_MODEL = "gpt5_mini"  # Used if primary model fails

# Maximum concurrent requests for parallel processing
# Adjust based on your API tier:
# - Tier 1 (new accounts): 5
# - Tier 2: 10-15
# - Tier 3+: 20-30
MAX_CONCURRENT_REQUESTS = 10

def should_extract_image(image_path: str) -> bool:
    """Pre-filter images before expensive vision API call.

    Skips tiny images (icons/avatars), very small files (stickers/emoji),
    and non-image files that somehow ended up in the photo field.
    """
    # Skip if file doesn't exist
    if not os.path.exists(image_path):
        return False

    # Skip tiny files (<5KB = likely stickers, emoji, icons)
    file_size = os.path.getsize(image_path)
    if file_size < 5_000:
        return False

    # Skip non-image extensions
    valid_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
    ext = os.path.splitext(image_path)[1].lower()
    if ext not in valid_extensions:
        return False

    return True


def _get_media_type(image_path: str) -> str:
    """Get MIME type from image file extension."""
    ext = os.path.splitext(image_path)[1].lower()
    mime_map = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.webp': 'image/webp',
        '.gif': 'image/gif',
    }
    return mime_map.get(ext, 'image/jpeg')


def encode_image(image_path):
    """Encode image to base64"""
    try:
        with open(image_path, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')
    except Exception as e:
        print(f"  Error encoding image {image_path}: {e}")
        return None

def extract_image_summary(image_path, message_text):
    """Extract summary of image content for categorization"""

    image_data = encode_image(image_path)
    if not image_data:
        return None

    prompt = get_image_summary_prompt(message_text)

    messages = [{
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": _get_media_type(image_path),
                    "data": image_data
                }
            },
            {
                "type": "text",
                "text": prompt
            }
        ]
    }]

    response = call_claude_sonnet(messages)
    return response.strip()

def extract_image_structured_data(image_path, message_text, message_date):
    """Extract structured data from image"""

    image_data = encode_image(image_path)
    if not image_data:
        return None

    prompt = get_image_structured_extraction_prompt(message_text, message_date)

    messages = [{
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": _get_media_type(image_path),
                    "data": image_data
                }
            },
            {
                "type": "text",
                "text": prompt
            }
        ]
    }]

    response = call_claude_sonnet(messages)
    return response


def extract_image_combined(image_path, message_text, message_date):
    """
    Extract BOTH summary and structured data from image in a single API call.

    Returns:
        dict with 'summary' and 'structured_data' keys, or None on failure
    """
    image_data = encode_image(image_path)
    if not image_data:
        return None

    prompt = get_combined_image_extraction_prompt(message_text, message_date)

    messages = [{
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": _get_media_type(image_path),
                    "data": image_data
                }
            },
            {
                "type": "text",
                "text": prompt
            }
        ]
    }]

    response = call_claude_sonnet(messages)

    # Parse JSON response
    try:
        response_text = _strip_code_block(response)

        parsed = json.loads(response_text)
        return {
            'summary': parsed.get('summary', ''),
            'structured_data': parsed.get('structured_data', {})
        }
    except json.JSONDecodeError as e:
        print(f"  Error parsing combined extraction: {e}")
        # Fall back to returning just the raw response as summary
        return {
            'summary': response[:200] if response else '',
            'structured_data': {}
        }


def process_batch(messages_batch, category, channel_name, use_gpt5=False):
    """
    Process a batch of messages of the same category.

    Args:
        messages_batch: List of message dicts
        category: 'data_opinion' or 'interview_meeting'
        channel_name: Name of the Telegram channel
        use_gpt5: If True, use GPT-5 for extraction; if False, use Claude Sonnet (default)
    """

    results = []

    if category == 'data_opinion':
        # Extract with opinion grouping
        # Use prompt caching for Claude Sonnet (system prompt cached for 5 min)
        system_prompt = get_data_opinion_system_prompt()
        user_prompt = get_data_opinion_user_prompt(messages_batch, channel_name)

        if use_gpt5:
            # GPT-5 doesn't support prompt caching, use combined prompt
            prompt = get_data_opinion_extraction_prompt(messages_batch, channel_name)
            messages_api = [{"role": "user", "content": prompt}]
            response = call_gpt5(messages_api)
        else:
            response, cache_stats = call_claude_with_cache(system_prompt, user_prompt, model="sonnet")
            print(f"  Cache stats: created={cache_stats.get('cache_creation_input_tokens', 0)}, "
                  f"read={cache_stats.get('cache_read_input_tokens', 0)}")

        print(f"\n=== RAW EXTRACTION RESPONSE ===")
        print(response[:500] + "..." if len(response) > 500 else response)
        print(f"=== END ===")

        # Parse response
        try:
            response_text = _strip_code_block(response)

            extracted_list = json.loads(response_text)

            # Create results for each message
            for item in extracted_list:
                msg_idx = item.get('message_index', 1) - 1
                if 0 <= msg_idx < len(messages_batch):
                    original_msg = messages_batch[msg_idx]

                    # Text entry
                    text_entry = {
                        'telegram_msg_id': original_msg.get('telegram_msg_id', ''),
                        'original_message_num': original_msg.get('original_num'),
                        'date': original_msg['date'],
                        'tg_channel': channel_name,
                        'category': category,
                        'entry_type': 'text',
                        'opinion_id': item.get('opinion_id', ''),
                        'raw_text': original_msg['text'],
                        'has_photo': original_msg.get('photo', ''),
                        'extracted_data': _build_extracted_data_json(item)
                    }
                    results.append(text_entry)

                    # Image entry if photo exists (using pre-extracted data)
                    if original_msg.get('photo') and original_msg.get('image_structured_data'):
                        image_entry = {
                            'telegram_msg_id': original_msg.get('telegram_msg_id', ''),
                            'original_message_num': original_msg.get('original_num'),
                            'date': original_msg['date'],
                            'tg_channel': channel_name,
                            'category': category,
                            'entry_type': 'image',
                            'opinion_id': item.get('opinion_id', ''),
                            'raw_text': f"[Image from message: {original_msg['text'][:100]}...]",
                            'has_photo': original_msg['photo'],
                            'extracted_data': original_msg['image_structured_data']
                        }
                        results.append(image_entry)

        except json.JSONDecodeError as e:
            print(f"Error parsing extraction: {e}")

    elif category == 'interview_meeting':
        # Extract with opinion grouping
        prompt = get_interview_extraction_prompt(messages_batch, channel_name)
        messages_api = [{"role": "user", "content": prompt}]

        if use_gpt5:
            response = call_gpt5(messages_api)
        else:
            response = call_claude_sonnet(messages_api)

        print(f"\n=== RAW EXTRACTION RESPONSE ===")
        print(response[:500] + "..." if len(response) > 500 else response)
        print(f"=== END ===")

        # Parse response
        try:
            response_text = _strip_code_block(response)

            extracted_list = json.loads(response_text)

            # Create results
            for item in extracted_list:
                msg_idx = item.get('message_index', 1) - 1
                if 0 <= msg_idx < len(messages_batch):
                    original_msg = messages_batch[msg_idx]

                    text_entry = {
                        'telegram_msg_id': original_msg.get('telegram_msg_id', ''),
                        'original_message_num': original_msg.get('original_num'),
                        'date': original_msg['date'],
                        'tg_channel': channel_name,
                        'category': category,
                        'entry_type': 'text',
                        'opinion_id': item.get('opinion_id', ''),
                        'raw_text': original_msg['text'],
                        'has_photo': original_msg.get('photo', ''),
                        'extracted_data': _build_extracted_data_json(item)
                    }
                    results.append(text_entry)

        except json.JSONDecodeError as e:
            print(f"Error parsing extraction: {e}")

    return results


async def process_batches_parallel(all_batches, channel_name):
    """
    Process multiple batches in parallel.

    Uses prompt caching for data_opinion batches via Claude (system prompt cached for 5 min).
    Non-data_opinion batches use the standard model with retry/fallback.

    Args:
        all_batches: List of tuples (messages_batch, category)
        channel_name: Name of the Telegram channel

    Returns:
        List of all results from all batches
    """
    if not all_batches:
        return []

    # Separate data_opinion (cached Claude) from other batches
    cached_batches = []  # (original_idx, messages_batch, category) for data_opinion
    standard_batches = []  # (original_idx, messages_batch, category) for others
    standard_messages_list = []  # prompts for standard path

    # Pre-compute system prompt once for all data_opinion batches (will be cached by Claude)
    system_prompt = get_data_opinion_system_prompt()

    for i, (messages_batch, category) in enumerate(all_batches):
        if category == 'data_opinion':
            cached_batches.append((i, messages_batch, category))
        else:  # interview_meeting
            prompt = get_interview_extraction_prompt(messages_batch, channel_name)
            standard_messages_list.append([{"role": "user", "content": prompt}])
            standard_batches.append((i, messages_batch, category))

    total_batches = len(all_batches)
    print(f"\n  🚀 Processing {total_batches} batches in parallel (max {MAX_CONCURRENT_REQUESTS} concurrent)...", flush=True)
    print(f"     data_opinion: {len(cached_batches)} batches (Claude with prompt caching)", flush=True)
    print(f"     other: {len(standard_batches)} batches (Primary: {EXTRACTION_MODEL} | Fallback: {FALLBACK_MODEL})", flush=True)
    parallel_start = time.time()

    # Process cached data_opinion batches via Claude with prompt caching
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    cached_responses = {}  # idx -> response
    total_cache_stats = {"cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}

    async def process_cached_batch(idx, messages_batch):
        async with semaphore:
            user_prompt = get_data_opinion_user_prompt(messages_batch, channel_name)
            try:
                response, cache_stats = await call_claude_with_cache_async(
                    system_prompt, user_prompt, model="sonnet", temperature=0.7, max_tokens=8000
                )
                total_cache_stats["cache_creation_input_tokens"] += cache_stats.get("cache_creation_input_tokens", 0)
                total_cache_stats["cache_read_input_tokens"] += cache_stats.get("cache_read_input_tokens", 0)
                return (idx, response)
            except Exception as e:
                print(f"  [Batch {idx+1}] Cached call failed: {e}, retrying without cache...", flush=True)
                try:
                    # Fallback: use combined prompt without caching
                    prompt = get_data_opinion_extraction_prompt(messages_batch, channel_name)
                    from models import call_claude_sonnet_async
                    response = await call_claude_sonnet_async(
                        [{"role": "user", "content": prompt}], temperature=0.7, max_tokens=8000
                    )
                    return (idx, response)
                except Exception as e2:
                    print(f"  [Batch {idx+1}] Fallback also failed: {e2}", flush=True)
                    return (idx, None)

    # Run cached batches
    if cached_batches:
        cached_tasks = [process_cached_batch(idx, mb) for idx, mb, _ in cached_batches]
        cached_results = await asyncio.gather(*cached_tasks)
        for idx, response in cached_results:
            cached_responses[idx] = response
        print(f"  Cache stats: created={total_cache_stats['cache_creation_input_tokens']}, "
              f"read={total_cache_stats['cache_read_input_tokens']}", flush=True)

    # Run standard batches with retry/fallback
    standard_responses_list = []
    if standard_messages_list:
        standard_responses_list = await process_batch_parallel_with_retry(
            standard_messages_list,
            model_func=EXTRACTION_MODEL,
            max_concurrent=MAX_CONCURRENT_REQUESTS,
            temperature=0.7,
            max_tokens=8000,
            max_retries=2,
            fallback_model=FALLBACK_MODEL
        )

    # Merge responses back in original order
    responses = [None] * total_batches
    for idx in cached_responses:
        responses[idx] = cached_responses[idx]
    for j, (idx, _, _) in enumerate(standard_batches):
        if j < len(standard_responses_list):
            responses[idx] = standard_responses_list[j]

    # Build batch_info for parsing
    batch_info = [(i, mb, cat) for i, (mb, cat) in enumerate(all_batches)]

    parallel_time = time.time() - parallel_start
    print(f"  ✓ Parallel processing completed in {parallel_time:.1f}s", flush=True)

    # Parse all responses
    all_results = []
    for idx, response in enumerate(responses):
        if response is None:
            print(f"  ⚠️  Batch {idx+1} failed, skipping...", flush=True)
            continue

        _, messages_batch, category = batch_info[idx]

        print(f"\n=== RAW EXTRACTION RESPONSE (Batch {idx+1}) ===", flush=True)
        print(response[:300] + "..." if len(response) > 300 else response, flush=True)
        print(f"=== END ===", flush=True)

        # Parse response
        try:
            response_text = _strip_code_block(response)

            extracted_list = json.loads(response_text)

            # Create results for each message
            for item in extracted_list:
                msg_idx = item.get('message_index', 1) - 1
                if 0 <= msg_idx < len(messages_batch):
                    original_msg = messages_batch[msg_idx]

                    # Text entry
                    text_entry = {
                        'telegram_msg_id': original_msg.get('telegram_msg_id', ''),
                        'original_message_num': original_msg.get('original_num'),
                        'date': original_msg['date'],
                        'tg_channel': channel_name,
                        'category': category,
                        'entry_type': 'text',
                        'opinion_id': item.get('opinion_id', ''),
                        'raw_text': original_msg['text'],
                        'has_photo': original_msg.get('photo', ''),
                        'extracted_data': _build_extracted_data_json(item)
                    }
                    all_results.append(text_entry)

                    # Image entry if photo exists (using pre-extracted data)
                    if original_msg.get('photo') and original_msg.get('image_structured_data'):
                        image_entry = {
                            'telegram_msg_id': original_msg.get('telegram_msg_id', ''),
                            'original_message_num': original_msg.get('original_num'),
                            'date': original_msg['date'],
                            'tg_channel': channel_name,
                            'category': category,
                            'entry_type': 'image',
                            'opinion_id': item.get('opinion_id', ''),
                            'raw_text': f"[Image from message: {original_msg['text'][:100]}...]",
                            'has_photo': original_msg['photo'],
                            'extracted_data': original_msg['image_structured_data']
                        }
                        all_results.append(image_entry)

        except json.JSONDecodeError as e:
            print(f"  ⚠️  Error parsing batch {idx+1}: {e}", flush=True)

    return all_results


def process_batches_parallel_sync(all_batches, channel_name):
    """
    Synchronous wrapper for process_batches_parallel.
    Detects whether an event loop is already running and handles accordingly.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Already inside an async context (e.g. called from orchestrator's asyncio.run)
        import nest_asyncio
        nest_asyncio.apply()
    return asyncio.run(process_batches_parallel(all_batches, channel_name))


def process_all_messages_v3(input_csv, output_csv, batch_size=5, overlap=2, base_photo_path=None, channel_name=None):
    """
    V3 Flow:
    1. Extract image summaries FIRST
    2. Categorize using text + image summary
    3. Process in batches with opinion grouping

    Args:
        input_csv: Path to input CSV file
        output_csv: Path to output CSV file
        batch_size: Size of batches for processing
        overlap: Number of overlapping messages between batches
        base_photo_path: Base path for photo files (auto-detected from input_csv if None)
    """

    # Cost tracking
    api_costs = {
        'image_summaries': 0,  # Claude Sonnet vision
        'categorizations': 0,  # GPT-4 mini
        'image_extractions': 0,  # Claude Sonnet vision
        'batch_extractions': 0  # Claude Sonnet text
    }

    # Read all messages
    messages = []
    with open(input_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, 1):
            row['original_num'] = i
            messages.append(row)

    # Auto-detect base_photo_path from input_csv location if not provided
    if base_photo_path is None:
        # Assume photos are in the same directory as the CSV
        from pathlib import Path
        csv_dir = Path(input_csv).parent
        base_photo_path = str(csv_dir) + '/'

    # Derive channel_name from parameter or first message
    if channel_name is None:
        channel_name = messages[0]['name'] if messages else "Unknown"

    print(f"Loaded {len(messages)} messages (channel: {channel_name})")

    # Track timing for each step
    step_times = {}

    # Checkpoint setup for resume capability
    from pathlib import Path
    checkpoint_dir = Path(__file__).parent / "data" / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    csv_name = Path(input_csv).stem
    checkpoint_step2 = checkpoint_dir / f"{csv_name}_step2.json"
    checkpoint_legacy = checkpoint_dir / f"{csv_name}_step1.json"

    def _save_checkpoint(complete=False):
        """Save current message state to checkpoint file."""
        data = []
        for msg in messages:
            data.append({
                'category': msg.get('category'),
                'image_summary': msg.get('image_summary', ''),
                'combined_text': msg.get('combined_text', ''),
                'image_structured_data_cached': msg.get('image_structured_data_cached', {}),
                'image_route': msg.get('image_route', ''),
                '_step1_time': step_times.get('step1_categorization', 0),
                '_step2_time': step_times.get('step2_image_extraction', 0),
                '_cat_api_calls': api_costs['categorizations'],
                '_img_api_calls': api_costs['image_summaries'],
                '_complete': complete,
            })
        with open(checkpoint_step2, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)

    # Check for checkpoint (resume support)
    skip_to_step3 = False
    categories_from_checkpoint = False
    if checkpoint_step2.exists():
        print(f"\n🔄 Found checkpoint: {checkpoint_step2}")
        try:
            with open(checkpoint_step2, 'r', encoding='utf-8') as f:
                checkpoint_data = json.load(f)
            for i, msg in enumerate(messages):
                if i < len(checkpoint_data):
                    cp = checkpoint_data[i]
                    msg['category'] = cp.get('category')
                    msg['image_summary'] = cp.get('image_summary', '')
                    msg['combined_text'] = cp.get('combined_text', msg['text'])
                    msg['image_structured_data_cached'] = cp.get('image_structured_data_cached', {})
                    msg['image_route'] = cp.get('image_route', '')
            step_times['step1_categorization'] = checkpoint_data[0].get('_step1_time', 0) if checkpoint_data else 0
            step_times['step2_image_extraction'] = checkpoint_data[0].get('_step2_time', 0) if checkpoint_data else 0
            api_costs['categorizations'] = checkpoint_data[0].get('_cat_api_calls', 0) if checkpoint_data else 0
            api_costs['image_summaries'] = checkpoint_data[0].get('_img_api_calls', 0) if checkpoint_data else 0

            if checkpoint_data and checkpoint_data[0].get('_complete'):
                skip_to_step3 = True
                print("   Resuming from complete checkpoint (skipping Steps 1, 2, 2.5)...")
            else:
                categories_from_checkpoint = True
                already_extracted = sum(1 for m in messages if m.get('image_summary'))
                print(f"   Resuming from partial checkpoint (Step 1 done, {already_extracted} images already extracted)...")
            print(f"   ✅ Restored {len(messages)} messages from checkpoint")
        except Exception as e:
            print(f"   ⚠️ Failed to load checkpoint: {e}")
            print("   Running from scratch...")
            skip_to_step3 = False
    elif checkpoint_legacy.exists():
        print(f"\n🔄 Found legacy checkpoint: {checkpoint_legacy}")
        print("   Legacy checkpoint from old pipeline — re-running with new pipeline...")
        checkpoint_legacy.unlink()

    if not skip_to_step3 and not categories_from_checkpoint:
        # ==================================================================
        # STEP 1: TEXT-ONLY CATEGORIZATION
        # ==================================================================
        print("=" * 80)
        print("STEP 1: TEXT-ONLY CATEGORIZATION (rule-based + parallel LLM)")
        print("=" * 80)
        step1_start = time.time()

        # Phase 1a: Classify every message for image routing
        route_counts = {'skip': 0, 'needs_image': 0, 'text_only': 0, 'pending_llm': 0}
        text_only_items = []    # (msg_index, msg) — no photo, categorize on text
        pending_llm_items = []  # (msg_index, msg) — has photo + text, categorize on text first
        needs_image_indices = []  # msg indices that need image before categorization

        rule_based_count = 0
        for i, msg in enumerate(messages):
            route, cat, reason = classify_for_image_routing(msg)
            msg['image_route'] = route
            route_counts[route] += 1

            if route == 'skip':
                msg['category'] = cat
                rule_based_count += 1
                print(f"  Message {i+1}: {cat} (rule-based)")
            elif route == 'text_only':
                text_only_items.append((i, msg))
            elif route == 'pending_llm':
                pending_llm_items.append((i, msg))
            elif route == 'needs_image':
                needs_image_indices.append(i)
                msg['category'] = None  # will be set after image extraction

        print(f"\n  Phase 1a routing: skip={route_counts['skip']}, text_only={route_counts['text_only']}, "
              f"pending_llm={route_counts['pending_llm']}, needs_image={route_counts['needs_image']}")

        # Phase 1b: Parallel async LLM categorization for text_only + pending_llm
        all_llm_items = text_only_items + pending_llm_items
        llm_based_count = 0

        if all_llm_items:
            print(f"\n  Phase 1b: Categorizing {len(all_llm_items)} messages via LLM (text-only, parallel)...")
            llm_results = _run_async(categorize_batch_text_only(all_llm_items, max_concurrent=MAX_CONCURRENT_REQUESTS))

            for idx, category in llm_results:
                msg = messages[idx]
                has_photo = bool(msg.get('photo'))

                if category is None:
                    # LLM failed — if has photo, route to needs_image; otherwise unknown
                    if has_photo:
                        msg['image_route'] = 'needs_image'
                        needs_image_indices.append(idx)
                        msg['category'] = None
                        print(f"  Message {idx+1}: LLM failed, routing to needs_image")
                    else:
                        msg['category'] = 'unknown'
                        print(f"  Message {idx+1}: unknown (LLM failed)")
                elif has_photo:
                    # Message has a photo — route based on category
                    if category in NON_EXTRACTABLE_CATEGORIES:
                        msg['category'] = category
                        msg['image_route'] = 'skip'
                        print(f"  Message {idx+1}: {category} (text-only, image skipped)")
                    else:
                        # Extractable or ambiguous — need the image for extraction
                        msg['category'] = category
                        msg['image_route'] = 'extract'
                        print(f"  Message {idx+1}: {category} (text-only, image needed for extraction)")
                else:
                    # No photo — category is final
                    msg['category'] = category
                    print(f"  Message {idx+1}: {category} (text-only)")

                llm_based_count += 1
                api_costs['categorizations'] += 1

        step_times['step1_categorization'] = time.time() - step1_start
        total_categorized = rule_based_count + llm_based_count
        print(f"\n⏱️  Step 1 completed in {step_times['step1_categorization']:.1f}s")
        if total_categorized > 0:
            print(f"    Rule-based: {rule_based_count}, LLM: {llm_based_count} ({rule_based_count/total_categorized*100:.0f}% saved)")

        # Save checkpoint after Step 1 (enables incremental resume for Step 2)
        _save_checkpoint(complete=False)
        print(f"   💾 Checkpoint saved after Step 1")

    # Reconstruct needs_image_indices if restoring from partial checkpoint
    if categories_from_checkpoint:
        needs_image_indices = [i for i, msg in enumerate(messages) if msg.get('image_route') == 'needs_image']

    if not skip_to_step3:
        # ==================================================================
        # STEP 2: TARGETED IMAGE EXTRACTION
        # ==================================================================
        print(f"\n{'=' * 80}")
        print("STEP 2: TARGETED IMAGE EXTRACTION (extract + needs_image only)")
        print("=" * 80)
        step2_start = time.time()

        # Set defaults for all messages
        for msg in messages:
            msg.setdefault('image_summary', '')
            msg.setdefault('combined_text', msg['text'])
            msg.setdefault('image_structured_data_cached', {})

        # Collect messages that need image extraction (skip already-extracted on resume)
        image_tasks = []
        already_done = 0
        for i, msg in enumerate(messages):
            if msg.get('image_route') in ('extract', 'needs_image') and msg.get('photo'):
                if msg.get('image_summary'):
                    already_done += 1
                    continue  # Already extracted in a previous partial run
                photo_path = base_photo_path + msg['photo']
                if should_extract_image(photo_path):
                    image_tasks.append((i, msg, photo_path))
                else:
                    print(f"  Skipping image for message {i+1}: failed pre-filter ({msg['photo']})")
        if already_done > 0:
            print(f"  {already_done} images already extracted (restored from checkpoint)")

        # Count images saved vs old pipeline (all photos)
        total_photos = sum(1 for m in messages if m.get('photo'))
        images_saved = total_photos - len(image_tasks)

        if image_tasks:
            print(f"\n  Extracting {len(image_tasks)}/{total_photos} images ({images_saved} skipped via text-only categorization)")
            print(f"  Running in parallel (max {MAX_CONCURRENT_REQUESTS} concurrent)...")
            from concurrent.futures import ThreadPoolExecutor, as_completed

            def _extract_single_image(task):
                msg_idx, msg, photo_path = task
                print(f"  Extracting image for message {msg_idx+1}/{len(messages)}: {msg['photo']}")
                result = extract_image_combined(photo_path, msg['text'], msg['date'])
                return (msg_idx, result)

            extracted_count = 0
            with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_REQUESTS) as executor:
                futures = {executor.submit(_extract_single_image, task): task for task in image_tasks}
                for future in as_completed(futures):
                    msg_idx, combined_result = future.result()
                    msg = messages[msg_idx]
                    api_costs['image_summaries'] += 1
                    extracted_count += 1

                    if combined_result:
                        image_summary = combined_result.get('summary', '')
                        print(f"  Message {msg_idx+1} summary: {image_summary[:150]}...")
                        msg['image_summary'] = image_summary
                        msg['combined_text'] = f"{msg['text']}\n\n[Image contains: {image_summary}]"
                        msg['image_structured_data_cached'] = combined_result.get('structured_data', {})

                    # Incremental checkpoint — saves progress after each image
                    _save_checkpoint(complete=False)
                    print(f"    [{extracted_count}/{len(image_tasks)}] checkpoint saved")
        else:
            print(f"\n  No images to extract ({images_saved} skipped via text-only categorization)")

        step_times['step2_image_extraction'] = time.time() - step2_start
        print(f"\n⏱️  Step 2 completed in {step_times['step2_image_extraction']:.1f}s")
        if images_saved > 0:
            saved_cost = images_saved * 0.01
            print(f"    💰 Images saved: {images_saved} (~${saved_cost:.2f} saved vs old pipeline)")

        # ==================================================================
        # STEP 2.5: RE-CATEGORIZE needs_image MESSAGES
        # ==================================================================
        needs_image_msgs = [i for i in needs_image_indices if messages[i].get('category') is None]
        if needs_image_msgs:
            print(f"\n{'=' * 80}")
            print(f"STEP 2.5: RE-CATEGORIZE {len(needs_image_msgs)} needs_image MESSAGES (with image context)")
            print("=" * 80)

            for idx in needs_image_msgs:
                msg = messages[idx]
                cat_prompt = get_categorization_prompt(msg['combined_text'], msg['date'])
                cat_messages_api = [{"role": "user", "content": cat_prompt}]
                cat_response = call_gpt41_mini(cat_messages_api)
                api_costs['categorizations'] += 1

                try:
                    cat_text = _strip_code_block(cat_response)
                    category_data = json.loads(cat_text)
                    msg['category'] = category_data.get('category', 'unknown')
                    print(f"  Message {idx+1}: {msg['category']} (re-categorized with image)")
                except json.JSONDecodeError as e:
                    print(f"  Message {idx+1}: error ({e})")
                    msg['category'] = 'error'

        # Mark filtered messages (all categorizations now final)
        from processing_tracker import mark_filtered
        filtered_count = 0
        for msg in messages:
            if msg.get('category') not in EXTRACTABLE_CATEGORIES:
                telegram_msg_id = msg.get('telegram_msg_id')
                if telegram_msg_id:
                    try:
                        mark_filtered(channel_name, int(telegram_msg_id))
                        filtered_count += 1
                    except (ValueError, TypeError):
                        pass
        if filtered_count > 0:
            print(f"    Tracked {filtered_count} filtered messages (won't re-categorize on next run)")

        # Save final checkpoint (marks all steps complete)
        _save_checkpoint(complete=True)
        print(f"   💾 Final checkpoint saved (Steps 1+2+2.5 complete)")

    print(f"\n{'=' * 80}", flush=True)
    print("STEP 3: USE CACHED STRUCTURED DATA FROM IMAGES", flush=True)
    print("=" * 80, flush=True)
    step3_start = time.time()

    # Step 3: Use cached structured data from Step 1 (no additional API calls needed)
    # Previously this made a SECOND API call per image - now we use cached data
    cached_used = 0
    for i, msg in enumerate(messages, 1):
        if msg.get('photo') and msg['category'] in ['data_opinion', 'interview_meeting']:
            cached_data = msg.get('image_structured_data_cached', {})
            if cached_data:
                msg['image_structured_data'] = json.dumps(cached_data, ensure_ascii=False)
                cached_used += 1
                print(f"  Message {i}: ✓ Using cached structured data", flush=True)
            else:
                msg['image_structured_data'] = ""
                print(f"  Message {i}: No cached data available", flush=True)
        # Note: api_costs['image_extractions'] no longer incremented - calls eliminated

    step_times['step3_image_extraction'] = time.time() - step3_start
    print(f"\n⏱️  Step 3 completed in {step_times['step3_image_extraction']:.1f}s (used {cached_used} cached extractions, 0 API calls)", flush=True)

    print(f"\n{'=' * 80}", flush=True)
    print("STEP 4: PROCESS BY CATEGORY WITH PARALLEL BATCHING", flush=True)
    print(f"  Model: {EXTRACTION_MODEL} | Max concurrent: {MAX_CONCURRENT_REQUESTS}", flush=True)
    print("=" * 80, flush=True)
    step4_start = time.time()

    all_results = []

    # Collect all batches for parallel processing
    all_batches = []

    # Process data_opinion messages
    data_opinion_msgs = [m for m in messages if m['category'] == 'data_opinion']
    if data_opinion_msgs:
        print(f"\nPreparing {len(data_opinion_msgs)} data_opinion messages for parallel processing...", flush=True)
        i = 0
        while i < len(data_opinion_msgs):
            batch_end = min(i + batch_size, len(data_opinion_msgs))
            batch = data_opinion_msgs[i:batch_end]
            all_batches.append((batch, 'data_opinion'))

            if batch_end < len(data_opinion_msgs):
                i += (batch_size - overlap)
            else:
                break

    # Process interview_meeting messages
    interview_msgs = [m for m in messages if m['category'] == 'interview_meeting']
    if interview_msgs:
        print(f"Preparing {len(interview_msgs)} interview_meeting messages for parallel processing...", flush=True)
        i = 0
        while i < len(interview_msgs):
            batch_end = min(i + batch_size, len(interview_msgs))
            batch = interview_msgs[i:batch_end]
            all_batches.append((batch, 'interview_meeting'))

            if batch_end < len(interview_msgs):
                i += (batch_size - overlap)
            else:
                break

    # Process all batches in parallel using sync wrapper (avoids event loop conflicts)
    if all_batches:
        print(f"\nTotal batches to process: {len(all_batches)}", flush=True)
        parallel_results = process_batches_parallel_sync(all_batches, channel_name)
        all_results.extend(parallel_results)
        api_costs['batch_extractions'] += len(all_batches)

    # Handle schedule and data_update (no extraction needed)
    for msg in messages:
        if msg['category'] in ['schedule', 'data_update', 'individual_stock']:
            all_results.append({
                'telegram_msg_id': msg.get('telegram_msg_id', ''),
                'original_message_num': msg['original_num'],
                'date': msg['date'],
                'tg_channel': channel_name,
                'category': msg['category'],
                'entry_type': 'text',
                'opinion_id': '',
                'raw_text': msg['text'],
                'has_photo': msg.get('photo', ''),
                'extracted_data': ''
            })

    step_times['step4_batch_extraction'] = time.time() - step4_start
    print(f"\n⏱️  Step 4 completed in {step_times['step4_batch_extraction']:.1f}s", flush=True)

    # Write results
    print(f"\n{'=' * 80}", flush=True)
    print("WRITING RESULTS")
    print("=" * 80)

    # Deduplicate by (original_message_num, date, tg_channel, entry_type)
    seen = set()
    deduped_results = []
    for result in all_results:
        key = (result['original_message_num'], result['date'], result['tg_channel'], result['entry_type'])
        if key not in seen:
            seen.add(key)
            deduped_results.append(result)

    if len(deduped_results) < len(all_results):
        print(f"Deduplicated: {len(all_results)} -> {len(deduped_results)} entries (removed {len(all_results) - len(deduped_results)} duplicates)")

    all_results = deduped_results

    with open(output_csv, 'w', encoding='utf-8', newline='') as f:
        fieldnames = ['telegram_msg_id', 'original_message_num', 'date', 'tg_channel', 'category',
                     'entry_type', 'opinion_id', 'raw_text', 'has_photo', 'extracted_data']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_results)

    print(f"Wrote {len(all_results)} entries to {output_csv}")

    # Track extracted messages in processing tracker
    from processing_tracker import mark_extracted
    tracked_count = 0
    for result in all_results:
        telegram_msg_id = result.get('telegram_msg_id')
        if telegram_msg_id:
            try:
                mark_extracted(result['tg_channel'], int(telegram_msg_id))
                tracked_count += 1
            except (ValueError, TypeError):
                pass  # Skip if telegram_msg_id is not a valid integer
    if tracked_count > 0:
        print(f"Tracked {tracked_count} messages in processing state DB")

    # Collect and append new metrics to mapping file
    all_extractions = []
    for result in all_results:
        if result.get('extracted_data'):
            try:
                extracted = json.loads(result['extracted_data'])
                all_extractions.append(extracted)
            except json.JSONDecodeError:
                pass

    all_metrics = collect_new_metrics_from_extractions(all_extractions)
    if all_metrics:
        added = append_new_metrics(all_metrics)
        if added:
            print(f"\n{'=' * 80}")
            print("NEW METRICS DISCOVERED")
            print("=" * 80)
            for m in added:
                sources_str = ', '.join(m.get('sources', [])) if m.get('sources') else 'unknown'
                print(f"  + {m.get('normalized')}: {m.get('suggested_description', '')} [from: {sources_str}]")

        # Normalize institution names in sources
        print("\nNormalizing source institutions...")
        normalize_sources_in_csv()

    # Summary
    print(f"\n{'=' * 80}")
    print("PROCESSING SUMMARY")
    print("=" * 80)
    print(f"Total messages: {len(messages)}")
    print(f"Total entries (text + images): {len(all_results)}")

    cat_counts = {}
    for m in messages:
        cat = m.get('category', 'unknown')
        cat_counts[cat] = cat_counts.get(cat, 0) + 1

    print(f"\nMessages ignored: {cat_counts.get('greeting', 0) + cat_counts.get('event_announcement', 0)}")
    print(f"\nBy category:")
    for cat, count in sorted(cat_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {cat}: {count}")

    entry_types = {}
    for r in all_results:
        et = r.get('entry_type', 'unknown')
        entry_types[et] = entry_types.get(et, 0) + 1

    print(f"\nBy entry type:")
    for et, count in entry_types.items():
        print(f"  {et}: {count}")

    # Print cost estimate
    print(f"\n{'=' * 80}")
    print("COST ESTIMATE")
    print("=" * 80)

    # Compute images saved (works for both fresh run and checkpoint resume)
    total_photos = sum(1 for m in messages if m.get('photo'))
    images_extracted = api_costs['image_summaries']
    images_saved = total_photos - images_extracted

    print(f"API Calls:")
    print(f"  Image extractions (Claude Sonnet vision): {images_extracted}")
    if images_saved > 0:
        print(f"    💰 Images skipped (text-only categorization): {images_saved} (~${images_saved * 0.01:.2f} saved)")
    print(f"  Categorizations (GPT-4.1 mini): {api_costs['categorizations']}")
    print(f"  Batch extractions ({EXTRACTION_MODEL}): {api_costs['batch_extractions']}")

    # Rough cost estimates (as of Nov 2025)
    # Claude Sonnet: ~$3/1M input, $15/1M output (~$0.01 per call avg)
    # GPT-4.1 mini: ~$0.10/1M input, $0.40/1M output (~$0.0004 per call avg)
    # GPT-5: ~$15/1M input, $60/1M output (~$0.05 per call avg)
    vision_cost = images_extracted * 0.01
    mini_cost = api_costs['categorizations'] * 0.0004

    # Batch extraction cost depends on model
    if EXTRACTION_MODEL == "gpt5":
        extraction_cost_per_call = 0.05
    elif EXTRACTION_MODEL == "gpt51":
        extraction_cost_per_call = 0.07
    elif EXTRACTION_MODEL == "gpt5_mini":
        extraction_cost_per_call = 0.01
    elif EXTRACTION_MODEL == "claude_sonnet":
        extraction_cost_per_call = 0.01
    elif EXTRACTION_MODEL == "claude_haiku":
        extraction_cost_per_call = 0.003
    else:
        extraction_cost_per_call = 0.01

    text_cost = api_costs['batch_extractions'] * extraction_cost_per_call
    total_cost = vision_cost + mini_cost + text_cost

    print(f"\nEstimated costs:")
    print(f"  Vision calls: ${vision_cost:.3f}")
    print(f"  GPT-4.1 mini calls: ${mini_cost:.3f}")
    print(f"  {EXTRACTION_MODEL} extraction calls: ${text_cost:.3f}")
    print(f"  TOTAL: ~${total_cost:.2f} USD")
    print(f"\nNote: Actual costs may vary based on token usage and current API pricing")

    # Print timing summary
    print(f"\n{'=' * 80}")
    print("TIMING SUMMARY")
    print("=" * 80)
    total_time = sum(step_times.values())
    for step_name, step_time in step_times.items():
        pct = (step_time / total_time * 100) if total_time > 0 else 0
        print(f"  {step_name}: {step_time:.1f}s ({pct:.1f}%)")
    print(f"  TOTAL: {total_time:.1f}s")

    # Clean up checkpoints after successful completion
    for cp in [checkpoint_step2, checkpoint_legacy]:
        if cp.exists():
            cp.unlink()
            print(f"\n🗑️  Checkpoint cleaned up: {cp.name}")

    return all_results

if __name__ == "__main__":
    results = process_all_messages_v3(
        input_csv='test_data/telegram_messages.csv',
        output_csv='test_data/processed_messages_v3.csv',
        batch_size=5,
        overlap=2
    )

    print("\n✓ Processing complete!")
    print(f"Output saved to: test_data/processed_messages_v3.csv")
