import sys
import csv
import json
import base64
import time
import asyncio
sys.path.append('../')
from models import call_claude_sonnet, call_gpt41_mini, call_gpt5, process_batch_parallel, process_batch_parallel_with_retry
from categorization_prompts import get_categorization_prompt
from data_opinion_prompts import get_data_opinion_extraction_prompt
from interview_meeting_prompts import get_interview_extraction_prompt
from metrics_mapping_utils import append_new_metrics, collect_new_metrics_from_extractions, normalize_sources_in_csv

# =============================================================================
# CONFIGURATION
# =============================================================================
# Model to use for batch extraction (Step 4)
# Options: "gpt5", "gpt51", "gpt5_mini", "claude_sonnet", "claude_haiku"
EXTRACTION_MODEL = "gpt5"
FALLBACK_MODEL = "claude_sonnet"  # Used if primary model fails

# Maximum concurrent requests for parallel processing
# Adjust based on your API tier:
# - Tier 1 (new accounts): 5
# - Tier 2: 10-15
# - Tier 3+: 20-30
MAX_CONCURRENT_REQUESTS = 10

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

    prompt = f"""Briefly summarize what this image shows (1-2 sentences).

Context text: {message_text}

Focus on:
- Type of content (chart, data table, text, announcement, etc.)
- Main topic if visible
- Key data/information if present

Return just the summary, no JSON."""

    messages = [{
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
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

    prompt = f"""Analyze this chart/image from a financial research message.

**Context:**
Date: {message_date}
Related text: {message_text[:200]}...

**Extract (ALL FIELDS MUST BE IN ENGLISH):**
1. **source**: Who created this chart? (e.g., Bloomberg, Fed, Hana Securities, Bank of Japan)
2. **data_source**: Where is the data from? (in English)
3. **asset_class**: What asset class? Use English names like "Japanese Government Bonds (JGBs)", "equities", "FX", "US Treasuries", "cryptocurrency", "ETF", "derivatives"
4. **used_data**: What data is displayed? (in English)
5. **what_happened**: What patterns/changes are visible? (in English)
6. **interpretation**: What does it suggest? (in English)

**CRITICAL: All output must be in English. Translate any Korean/Japanese/other language content.**

Return JSON only:
```json
{{
    "source": "...",
    "data_source": "...",
    "asset_class": "...",
    "used_data": "...",
    "what_happened": "...",
    "interpretation": "..."
}}
```"""

    messages = [{
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
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
        prompt = get_data_opinion_extraction_prompt(messages_batch, channel_name)
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
            response_text = response.strip()
            if response_text.startswith("```"):
                lines = response_text.split('\n')
                response_text = '\n'.join(lines[1:-1]) if len(lines) > 2 else response_text
                if response_text.startswith("json"):
                    response_text = response_text[4:].strip()

            extracted_list = json.loads(response_text)

            # Create results for each message
            for item in extracted_list:
                msg_idx = item.get('message_index', 1) - 1
                if 0 <= msg_idx < len(messages_batch):
                    original_msg = messages_batch[msg_idx]

                    # Text entry
                    text_entry = {
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
            response_text = response.strip()
            if response_text.startswith("```"):
                lines = response_text.split('\n')
                response_text = '\n'.join(lines[1:-1]) if len(lines) > 2 else response_text
                if response_text.startswith("json"):
                    response_text = response_text[4:].strip()

            extracted_list = json.loads(response_text)

            # Create results
            for item in extracted_list:
                msg_idx = item.get('message_index', 1) - 1
                if 0 <= msg_idx < len(messages_batch):
                    original_msg = messages_batch[msg_idx]

                    text_entry = {
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
    Process multiple batches in parallel using GPT-5.

    Args:
        all_batches: List of tuples (messages_batch, category)
        channel_name: Name of the Telegram channel

    Returns:
        List of all results from all batches
    """
    # Build list of prompts for parallel processing
    messages_list = []
    batch_info = []  # Track which batch each request belongs to

    for i, (messages_batch, category) in enumerate(all_batches):
        if category == 'data_opinion':
            prompt = get_data_opinion_extraction_prompt(messages_batch, channel_name)
        else:  # interview_meeting
            prompt = get_interview_extraction_prompt(messages_batch, channel_name)

        messages_list.append([{"role": "user", "content": prompt}])
        batch_info.append((i, messages_batch, category))

    if not messages_list:
        return []

    print(f"\n  🚀 Processing {len(messages_list)} batches in parallel (max {MAX_CONCURRENT_REQUESTS} concurrent)...")
    print(f"     Primary: {EXTRACTION_MODEL} | Fallback: {FALLBACK_MODEL}")
    parallel_start = time.time()

    # Process all batches in parallel with retry and fallback
    responses = await process_batch_parallel_with_retry(
        messages_list,
        model_func=EXTRACTION_MODEL,
        max_concurrent=MAX_CONCURRENT_REQUESTS,
        temperature=0.7,  # GPT-5 only supports temperature=1.0, will be adjusted internally
        max_tokens=8000,
        max_retries=2,
        fallback_model=FALLBACK_MODEL
    )

    parallel_time = time.time() - parallel_start
    print(f"  ✓ Parallel processing completed in {parallel_time:.1f}s")

    # Parse all responses
    all_results = []
    for idx, response in enumerate(responses):
        if response is None:
            print(f"  ⚠️  Batch {idx+1} failed, skipping...")
            continue

        _, messages_batch, category = batch_info[idx]

        print(f"\n=== RAW EXTRACTION RESPONSE (Batch {idx+1}) ===")
        print(response[:300] + "..." if len(response) > 300 else response)
        print(f"=== END ===")

        # Parse response
        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                lines = response_text.split('\n')
                response_text = '\n'.join(lines[1:-1]) if len(lines) > 2 else response_text
                if response_text.startswith("json"):
                    response_text = response_text[4:].strip()

            extracted_list = json.loads(response_text)

            # Create results for each message
            for item in extracted_list:
                msg_idx = item.get('message_index', 1) - 1
                if 0 <= msg_idx < len(messages_batch):
                    original_msg = messages_batch[msg_idx]

                    # Text entry
                    text_entry = {
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
            print(f"  ⚠️  Error parsing batch {idx+1}: {e}")

    return all_results

def process_all_messages_v3(input_csv, output_csv, batch_size=5, overlap=2, base_photo_path=None):
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

    print(f"Loaded {len(messages)} messages")

    # Track timing for each step
    step_times = {}

    print("=" * 80)
    print("STEP 1: EXTRACT IMAGE SUMMARIES")
    print("=" * 80)
    step1_start = time.time()

    # Step 1: Extract image summaries for categorization
    for i, msg in enumerate(messages, 1):
        if msg.get('photo'):
            print(f"\nMessage {i}/{len(messages)}: Extracting image summary...")
            print(f"  Photo: {msg['photo']}")

            photo_path = base_photo_path + msg['photo']
            image_summary = extract_image_summary(photo_path, msg['text'])
            api_costs['image_summaries'] += 1

            if image_summary:
                print(f"  Summary: {image_summary[:150]}...")
                msg['image_summary'] = image_summary
                msg['combined_text'] = f"{msg['text']}\n\n[Image contains: {image_summary}]"
            else:
                msg['image_summary'] = ""
                msg['combined_text'] = msg['text']
        else:
            msg['image_summary'] = ""
            msg['combined_text'] = msg['text']

    step_times['step1_image_summaries'] = time.time() - step1_start
    print(f"\n⏱️  Step 1 completed in {step_times['step1_image_summaries']:.1f}s")

    print(f"\n{'=' * 80}")
    print("STEP 2: CATEGORIZE USING TEXT + IMAGE")
    print("=" * 80)
    step2_start = time.time()

    # Step 2: Categorize using combined text
    for i, msg in enumerate(messages, 1):
        print(f"\nCategorizing message {i}/{len(messages)}...")

        # Use combined text for categorization
        cat_prompt = get_categorization_prompt(msg['combined_text'], msg['date'])
        cat_messages = [{"role": "user", "content": cat_prompt}]
        cat_response = call_gpt41_mini(cat_messages)
        api_costs['categorizations'] += 1

        try:
            cat_text = cat_response.strip()
            if cat_text.startswith("```"):
                lines = cat_text.split('\n')
                cat_text = '\n'.join(lines[1:-1]) if len(lines) > 2 else cat_text
                if cat_text.startswith("json"):
                    cat_text = cat_text[4:].strip()

            category_data = json.loads(cat_text)
            msg['category'] = category_data.get('category', 'unknown')
            print(f"  → {msg['category']}")

        except json.JSONDecodeError as e:
            print(f"  → Error: {e}")
            msg['category'] = 'error'

    step_times['step2_categorization'] = time.time() - step2_start
    print(f"\n⏱️  Step 2 completed in {step_times['step2_categorization']:.1f}s")

    print(f"\n{'=' * 80}")
    print("STEP 3: EXTRACT STRUCTURED DATA FROM IMAGES")
    print("=" * 80)
    step3_start = time.time()

    # Step 3: Extract structured data from images (for data_opinion/interview_meeting)
    for i, msg in enumerate(messages, 1):
        if msg.get('photo') and msg['category'] in ['data_opinion', 'interview_meeting']:
            print(f"\nMessage {i}/{len(messages)}: Extracting structured data from image...")

            photo_path = base_photo_path + msg['photo']
            image_response = extract_image_structured_data(photo_path, msg['text'], msg['date'])
            api_costs['image_extractions'] += 1

            if image_response:
                try:
                    img_text = image_response.strip()
                    if img_text.startswith("```"):
                        lines = img_text.split('\n')
                        img_text = '\n'.join(lines[1:-1]) if len(lines) > 2 else img_text
                        if img_text.startswith("json"):
                            img_text = img_text[4:].strip()

                    img_data = json.loads(img_text)
                    msg['image_structured_data'] = json.dumps(img_data, ensure_ascii=False)
                    print(f"  ✓ Extracted")
                except json.JSONDecodeError as e:
                    print(f"  Error parsing: {e}")
                    msg['image_structured_data'] = ""
            else:
                msg['image_structured_data'] = ""

    step_times['step3_image_extraction'] = time.time() - step3_start
    print(f"\n⏱️  Step 3 completed in {step_times['step3_image_extraction']:.1f}s")

    print(f"\n{'=' * 80}")
    print("STEP 4: PROCESS BY CATEGORY WITH PARALLEL BATCHING")
    print(f"  Model: {EXTRACTION_MODEL} | Max concurrent: {MAX_CONCURRENT_REQUESTS}")
    print("=" * 80)
    step4_start = time.time()

    channel_name = messages[0]['name'] if messages else "Unknown"
    all_results = []

    # Collect all batches for parallel processing
    all_batches = []

    # Process data_opinion messages
    data_opinion_msgs = [m for m in messages if m['category'] == 'data_opinion']
    if data_opinion_msgs:
        print(f"\nPreparing {len(data_opinion_msgs)} data_opinion messages for parallel processing...")
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
        print(f"Preparing {len(interview_msgs)} interview_meeting messages for parallel processing...")
        i = 0
        while i < len(interview_msgs):
            batch_end = min(i + batch_size, len(interview_msgs))
            batch = interview_msgs[i:batch_end]
            all_batches.append((batch, 'interview_meeting'))

            if batch_end < len(interview_msgs):
                i += (batch_size - overlap)
            else:
                break

    # Process all batches in parallel
    if all_batches:
        print(f"\nTotal batches to process: {len(all_batches)}")

        # Check if we're already in an async context
        try:
            loop = asyncio.get_running_loop()
            # We're in an async context - use loop.run_until_complete with a new task
            # Create a new task to run the parallel processing
            print(f"  🚀 Processing {len(all_batches)} batches in parallel (async context detected)...")
            import concurrent.futures

            # Use ThreadPoolExecutor to run async code from sync context within async
            def run_parallel():
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    return new_loop.run_until_complete(process_batches_parallel(all_batches, channel_name))
                finally:
                    new_loop.close()

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_parallel)
                parallel_results = future.result()

        except RuntimeError:
            # No running loop - safe to use asyncio.run() for parallel processing
            parallel_results = asyncio.run(process_batches_parallel(all_batches, channel_name))

        all_results.extend(parallel_results)
        api_costs['batch_extractions'] += len(all_batches)

    # Handle schedule and data_update (no extraction needed)
    for msg in messages:
        if msg['category'] in ['schedule', 'data_update']:
            all_results.append({
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
    print(f"\n⏱️  Step 4 completed in {step_times['step4_batch_extraction']:.1f}s")

    # Write results
    print(f"\n{'=' * 80}")
    print("WRITING RESULTS")
    print("=" * 80)

    with open(output_csv, 'w', encoding='utf-8', newline='') as f:
        fieldnames = ['original_message_num', 'date', 'tg_channel', 'category',
                     'entry_type', 'opinion_id', 'raw_text', 'has_photo', 'extracted_data']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_results)

    print(f"Wrote {len(all_results)} entries to {output_csv}")

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
