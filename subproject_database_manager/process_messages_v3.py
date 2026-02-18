import sys
import os
import csv
import json
import base64
import time
import asyncio
import re
sys.path.append('../')
from models import call_claude_sonnet, call_gpt41_mini, call_gpt5, process_batch_parallel, process_batch_parallel_with_retry, process_batch_parallel_with_retry_sync, call_claude_with_cache, call_claude_with_cache_async
from categorization_prompts import get_categorization_prompt
from data_opinion_prompts import get_data_opinion_extraction_prompt, get_data_opinion_system_prompt, get_data_opinion_user_prompt
from interview_meeting_prompts import get_interview_extraction_prompt
from image_extraction_prompts import get_image_summary_prompt, get_image_structured_extraction_prompt, get_combined_image_extraction_prompt
from metrics_mapping_utils import append_new_metrics, collect_new_metrics_from_extractions, normalize_sources_in_csv


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


EXTRACTION_MODEL = "gpt5_mini"
FALLBACK_MODEL = "claude_sonnet"  # Used if primary model fails

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


def process_batch(messages_batch, category, channel_name, use_gpt5=True):
    """
    Process a batch of messages of the same category.

    Args:
        messages_batch: List of message dicts
        category: 'data_opinion' or 'interview_meeting'
        channel_name: Name of the Telegram channel
        use_gpt5: If True, use GPT-5 for extraction; if False, use Claude Sonnet
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
                        'extracted_data': json.dumps({k: v for k, v in item.items() if k not in ['message_index', 'opinion_id']}, ensure_ascii=False)
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
                        'extracted_data': json.dumps({k: v for k, v in item.items() if k not in ['message_index', 'opinion_id']}, ensure_ascii=False)
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
                        'extracted_data': json.dumps({k: v for k, v in item.items() if k not in ['message_index', 'opinion_id']}, ensure_ascii=False)
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
    Uses asyncio.run() which safely creates and manages its own event loop.

    This avoids event loop conflicts when called from background processes
    or other async contexts.
    """
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
    # Use input CSV name to create unique checkpoint file
    csv_name = Path(input_csv).stem
    checkpoint_file = checkpoint_dir / f"{csv_name}_step1.json"

    # Check for Step 1 checkpoint (resume after crash)
    skip_step1 = False
    if checkpoint_file.exists():
        print(f"\n🔄 Found Step 1 checkpoint: {checkpoint_file}")
        print("   Resuming from checkpoint (skipping Step 1 image extraction)...")
        try:
            with open(checkpoint_file, 'r', encoding='utf-8') as f:
                checkpoint_data = json.load(f)
            # Restore message data from checkpoint
            for i, msg in enumerate(messages):
                if i < len(checkpoint_data):
                    msg['image_summary'] = checkpoint_data[i].get('image_summary', '')
                    msg['combined_text'] = checkpoint_data[i].get('combined_text', msg['text'])
                    msg['image_structured_data_cached'] = checkpoint_data[i].get('image_structured_data_cached', {})
            step_times['step1_image_summaries'] = checkpoint_data[0].get('_step1_time', 0) if checkpoint_data else 0
            api_costs['image_summaries'] = checkpoint_data[0].get('_api_calls', 0) if checkpoint_data else 0
            skip_step1 = True
            print(f"   ✅ Restored {len(messages)} messages from checkpoint")
        except Exception as e:
            print(f"   ⚠️ Failed to load checkpoint: {e}")
            print("   Running Step 1 from scratch...")
            skip_step1 = False

    if not skip_step1:
        print("=" * 80)
        print("STEP 1: EXTRACT IMAGE SUMMARIES + STRUCTURED DATA (COMBINED)")
        print("=" * 80)
        step1_start = time.time()

        # Step 1: Extract BOTH summary and structured data in one call
        # This saves one API call per image for data_opinion/interview_meeting categories
        # Uses thread pool for parallel image extraction

        # Set defaults for all messages first
        for msg in messages:
            msg['image_summary'] = ""
            msg['combined_text'] = msg['text']
            msg['image_structured_data_cached'] = {}

        # Collect messages that have photos and pass the pre-filter
        image_tasks = []  # (msg_index, msg, photo_path)
        for i, msg in enumerate(messages):
            if msg.get('photo'):
                photo_path = base_photo_path + msg['photo']
                if should_extract_image(photo_path):
                    image_tasks.append((i, msg, photo_path))
                else:
                    print(f"  Skipping image for message {i+1}: failed pre-filter ({msg['photo']})")

        if image_tasks:
            print(f"\n  Extracting {len(image_tasks)} images in parallel (max {MAX_CONCURRENT_REQUESTS} concurrent)...")
            from concurrent.futures import ThreadPoolExecutor, as_completed

            def _extract_single_image(task):
                msg_idx, msg, photo_path = task
                print(f"  Extracting image for message {msg_idx+1}/{len(messages)}: {msg['photo']}")
                result = extract_image_combined(photo_path, msg['text'], msg['date'])
                return (msg_idx, result)

            with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_REQUESTS) as executor:
                futures = {executor.submit(_extract_single_image, task): task for task in image_tasks}
                for future in as_completed(futures):
                    msg_idx, combined_result = future.result()
                    msg = messages[msg_idx]
                    api_costs['image_summaries'] += 1

                    if combined_result:
                        image_summary = combined_result.get('summary', '')
                        print(f"  Message {msg_idx+1} summary: {image_summary[:150]}...")
                        msg['image_summary'] = image_summary
                        msg['combined_text'] = f"{msg['text']}\n\n[Image contains: {image_summary}]"
                        msg['image_structured_data_cached'] = combined_result.get('structured_data', {})

        step_times['step1_image_summaries'] = time.time() - step1_start
        print(f"\n⏱️  Step 1 completed in {step_times['step1_image_summaries']:.1f}s")

        # Save Step 1 checkpoint for resume capability
        print(f"   💾 Saving checkpoint to {checkpoint_file}...")
        checkpoint_data = []
        for msg in messages:
            checkpoint_data.append({
                'image_summary': msg.get('image_summary', ''),
                'combined_text': msg.get('combined_text', ''),
                'image_structured_data_cached': msg.get('image_structured_data_cached', {}),
                '_step1_time': step_times['step1_image_summaries'],
                '_api_calls': api_costs['image_summaries']
            })
        with open(checkpoint_file, 'w', encoding='utf-8') as f:
            json.dump(checkpoint_data, f, ensure_ascii=False)
        print(f"   ✅ Checkpoint saved")

    print(f"\n{'=' * 80}")
    print("STEP 2: CATEGORIZE USING TEXT + IMAGE")
    print("=" * 80)
    step2_start = time.time()

    # Track rule-based vs LLM categorizations
    rule_based_count = 0
    llm_based_count = 0

    # Step 2: Categorize using combined text
    for i, msg in enumerate(messages, 1):
        print(f"\nCategorizing message {i}/{len(messages)}...")

        # Try rule-based categorization first (saves ~$0.0004 per match)
        rule_category, rule_confidence = categorize_by_rules(msg['combined_text'])

        if rule_category:
            msg['category'] = rule_category
            rule_based_count += 1
            print(f"  → {msg['category']} (rule-based, {rule_confidence})")
            continue

        # Fall back to LLM for complex cases
        cat_prompt = get_categorization_prompt(msg['combined_text'], msg['date'])
        cat_messages = [{"role": "user", "content": cat_prompt}]
        cat_response = call_gpt41_mini(cat_messages)
        api_costs['categorizations'] += 1
        llm_based_count += 1

        try:
            cat_text = _strip_code_block(cat_response)

            category_data = json.loads(cat_text)
            msg['category'] = category_data.get('category', 'unknown')
            print(f"  → {msg['category']} (LLM)")

        except json.JSONDecodeError as e:
            print(f"  → Error: {e}")
            msg['category'] = 'error'

    step_times['step2_categorization'] = time.time() - step2_start
    print(f"\n⏱️  Step 2 completed in {step_times['step2_categorization']:.1f}s")
    total_categorized = rule_based_count + llm_based_count
    if total_categorized > 0:
        print(f"    Rule-based: {rule_based_count}, LLM: {llm_based_count} ({rule_based_count/total_categorized*100:.0f}% saved)")
    else:
        print(f"    No messages categorized")

    # Track filtered messages (categories that won't be extracted) to avoid re-categorization
    from processing_tracker import mark_filtered
    extractable_categories = {'data_opinion', 'interview_meeting'}
    filtered_count = 0
    for msg in messages:
        if msg.get('category') not in extractable_categories:
            telegram_msg_id = msg.get('telegram_msg_id')
            if telegram_msg_id:
                try:
                    mark_filtered(channel_name, int(telegram_msg_id))
                    filtered_count += 1
                except (ValueError, TypeError):
                    pass
    if filtered_count > 0:
        print(f"    Tracked {filtered_count} filtered messages (won't re-categorize on next run)")

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
        if msg['category'] in ['schedule', 'data_update']:
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
    print(f"API Calls:")
    print(f"  Image summaries (Claude Sonnet vision): {api_costs['image_summaries']}")
    print(f"  Categorizations (GPT-4.1 mini): {api_costs['categorizations']}")
    print(f"  Image extractions (Claude Sonnet vision): {api_costs['image_extractions']}")
    print(f"  Batch extractions ({EXTRACTION_MODEL}): {api_costs['batch_extractions']}")

    # Rough cost estimates (as of Nov 2025)
    # Claude Sonnet: ~$3/1M input, $15/1M output (~$0.01 per call avg)
    # GPT-4.1 mini: ~$0.10/1M input, $0.40/1M output (~$0.0004 per call avg)
    # GPT-5: ~$15/1M input, $60/1M output (~$0.05 per call avg)
    vision_cost = (api_costs['image_summaries'] + api_costs['image_extractions']) * 0.01
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

    # Clean up checkpoint after successful completion
    if checkpoint_file.exists():
        checkpoint_file.unlink()
        print(f"\n🗑️  Checkpoint cleaned up (processing completed successfully)")

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
