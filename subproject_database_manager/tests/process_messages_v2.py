import sys
import csv
import json
import base64
sys.path.append('../')
from models import call_claude_sonnet
from message_categorization import categorize_message
from data_opinion_prompts import get_data_opinion_extraction_prompt
from interview_meeting_prompts import get_interview_extraction_prompt

def encode_image(image_path):
    """Encode image to base64"""
    try:
        with open(image_path, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')
    except Exception as e:
        print(f"Error encoding image {image_path}: {e}")
        return None

def extract_image_data(image_path, message_text, message_date):
    """Extract data from image using vision"""

    image_data = encode_image(image_path)
    if not image_data:
        return None

    prompt = f"""Analyze this chart/image from a financial research message.

**Context:**
Date: {message_date}
Related text: {message_text[:200]}...

**Extract:**
1. **source**: Who created this chart? (e.g., Bloomberg, Fed, 하나증권)
2. **data_source**: Where is the data from?
3. **asset_class**: What asset class? (국채, 주식, FX, etc.)
4. **used_data**: What data is displayed?
5. **what_happened**: What patterns/changes are visible?
6. **interpretation**: What does it suggest?

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

def process_batch(messages_batch, category, channel_name, base_photo_path):
    """Process a batch of messages of the same category"""

    results = []

    if category == 'data_opinion':
        # Extract with opinion grouping
        prompt = get_data_opinion_extraction_prompt(messages_batch, channel_name)
        messages_api = [{"role": "user", "content": prompt}]
        response = call_claude_sonnet(messages_api)

        print(f"\n=== RAW EXTRACTION RESPONSE ===")
        print(response[:1000] + "...")
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

                    # Image entry if photo exists
                    if original_msg.get('photo'):
                        photo_path = base_photo_path + original_msg['photo']
                        print(f"Analyzing image: {original_msg['photo']}")

                        image_response = extract_image_data(photo_path, original_msg['text'], original_msg['date'])

                        if image_response:
                            try:
                                img_text = image_response.strip()
                                if img_text.startswith("```"):
                                    lines = img_text.split('\n')
                                    img_text = '\n'.join(lines[1:-1]) if len(lines) > 2 else img_text
                                    if img_text.startswith("json"):
                                        img_text = img_text[4:].strip()

                                img_data = json.loads(img_text)

                                image_entry = {
                                    'original_message_num': original_msg.get('original_num'),
                                    'date': original_msg['date'],
                                    'tg_channel': channel_name,
                                    'category': category,
                                    'entry_type': 'image',
                                    'opinion_id': item.get('opinion_id', ''),
                                    'raw_text': f"[Image from message: {original_msg['text'][:100]}...]",
                                    'has_photo': original_msg['photo'],
                                    'extracted_data': json.dumps(img_data, ensure_ascii=False)
                                }
                                results.append(image_entry)
                            except json.JSONDecodeError as e:
                                print(f"Error parsing image data: {e}")

        except json.JSONDecodeError as e:
            print(f"Error parsing extraction: {e}")

    elif category == 'interview_meeting':
        # Extract with opinion grouping
        prompt = get_interview_extraction_prompt(messages_batch, channel_name)
        messages_api = [{"role": "user", "content": prompt}]
        response = call_claude_sonnet(messages_api)

        print(f"\n=== RAW EXTRACTION RESPONSE ===")
        print(response[:1000] + "...")
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

def process_all_messages_v2(input_csv, output_csv, batch_size=7, overlap=2):
    """
    Process all messages with:
    - Batch processing with overlapping windows
    - Opinion ID grouping
    - Image vision analysis
    """

    # Read all messages
    messages = []
    with open(input_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, 1):
            row['original_num'] = i
            messages.append(row)

    print(f"Loaded {len(messages)} messages")
    print("=" * 80)
    print("STEP 1: CATEGORIZING ALL MESSAGES")
    print("=" * 80)

    # Step 1: Categorize all messages
    for i, msg in enumerate(messages, 1):
        print(f"\nCategorizing message {i}/{len(messages)}...")
        cat_response = categorize_message(msg['text'], msg['date'])

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

    # Step 2: Group by category and process in batches
    print(f"\n{'=' * 80}")
    print("STEP 2: PROCESSING BY CATEGORY WITH BATCHING")
    print("=" * 80)

    channel_name = messages[0]['name'] if messages else "Unknown"
    base_photo_path = 'test_data/ChatExport_2025-11-21/'

    all_results = []

    # Process data_opinion messages
    data_opinion_msgs = [m for m in messages if m['category'] == 'data_opinion']
    if data_opinion_msgs:
        print(f"\n Processing {len(data_opinion_msgs)} data_opinion messages in batches...")
        i = 0
        while i < len(data_opinion_msgs):
            batch_end = min(i + batch_size, len(data_opinion_msgs))
            batch = data_opinion_msgs[i:batch_end]

            print(f"\n  Batch: messages {i+1} to {batch_end}")
            batch_results = process_batch(batch, 'data_opinion', channel_name, base_photo_path)
            all_results.extend(batch_results)

            if batch_end < len(data_opinion_msgs):
                i += (batch_size - overlap)
            else:
                break

    # Process interview_meeting messages
    interview_msgs = [m for m in messages if m['category'] == 'interview_meeting']
    if interview_msgs:
        print(f"\nProcessing {len(interview_msgs)} interview_meeting messages in batches...")
        i = 0
        while i < len(interview_msgs):
            batch_end = min(i + batch_size, len(interview_msgs))
            batch = interview_msgs[i:batch_end]

            print(f"\n  Batch: messages {i+1} to {batch_end}")
            batch_results = process_batch(batch, 'interview_meeting', channel_name, base_photo_path)
            all_results.extend(batch_results)

            if batch_end < len(interview_msgs):
                i += (batch_size - overlap)
            else:
                break

    # Handle schedule and data_update
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

    # Summary
    print(f"\n{'=' * 80}")
    print("PROCESSING SUMMARY")
    print("=" * 80}")
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

    return all_results

if __name__ == "__main__":
    results = process_all_messages_v2(
        input_csv='test_data/telegram_messages.csv',
        output_csv='test_data/processed_messages_v2.csv',
        batch_size=5,
        overlap=2
    )

    print("\n✓ Processing complete!")
    print(f"Output saved to: test_data/processed_messages_v2.csv")
