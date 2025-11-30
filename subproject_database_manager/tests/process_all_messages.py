import sys
import csv
import json
sys.path.append('../')
from message_categorization import categorize_message
from interview_meeting_extraction import extract_interview_meeting, parse_interview_response
from data_opinion_extraction import extract_data_opinion, parse_data_opinion_response

def process_all_telegram_messages(input_csv, output_csv):
    """
    Main orchestrator: categorize and extract structured data from all messages
    """

    # Read input messages
    messages = []
    with open(input_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            messages.append(row)

    print(f"Loaded {len(messages)} messages")
    print("=" * 80)
    print("PROCESSING ALL MESSAGES")
    print("=" * 80)

    results = []

    for i, msg in enumerate(messages, 1):
        print(f"\n{'='*80}")
        print(f"Message {i}/{len(messages)}")
        print(f"{'='*80}")
        print(f"Date: {msg['date']}")
        print(f"Text: {msg['text'][:100]}...")

        # Step 1: Categorize
        print("\n[Step 1: Categorizing...]")
        cat_response = categorize_message(msg['text'], msg['date'])

        try:
            cat_text = cat_response.strip()
            if cat_text.startswith("```"):
                lines = cat_text.split('\n')
                cat_text = '\n'.join(lines[1:-1]) if len(lines) > 2 else cat_text
                if cat_text.startswith("json"):
                    cat_text = cat_text[4:].strip()

            category_data = json.loads(cat_text)
            category = category_data.get('category', 'unknown')

            print(f"Category: {category}")

        except json.JSONDecodeError as e:
            print(f"Error categorizing: {e}")
            category = 'error'

        # Step 2: Process based on category
        if category in ['greeting', 'event_announcement']:
            print("[Step 2: IGNORING - greeting or announcement]")
            continue

        elif category in ['schedule', 'data_update']:
            print(f"[Step 2: SAVING RAW TEXT - {category}]")
            result = {
                'message_num': i,
                'date': msg['date'],
                'tg_channel': msg['name'],
                'category': category,
                'raw_text': msg['text'],
                'has_photo': msg.get('photo', ''),
                'extracted_data': ''
            }
            results.append(result)

        elif category == 'interview_meeting':
            print("[Step 2: EXTRACTING - interview_meeting]")
            extract_response = extract_interview_meeting(msg['text'], msg['date'])
            print("\n=== RAW EXTRACTION RESPONSE ===")
            print(extract_response[:500] + "...")
            print("=== END ===")

            data, error = parse_interview_response(extract_response)
            if error:
                print(f"Extraction error: {error}")
                data = {}

            result = {
                'message_num': i,
                'date': msg['date'],
                'tg_channel': msg['name'],
                'category': category,
                'raw_text': msg['text'],
                'has_photo': msg.get('photo', ''),
                'extracted_data': json.dumps(data, ensure_ascii=False)
            }
            results.append(result)

        elif category == 'data_opinion':
            print("[Step 2: EXTRACTING - data_opinion]")
            extract_response = extract_data_opinion(msg['text'], msg['date'])
            print("\n=== RAW EXTRACTION RESPONSE ===")
            print(extract_response[:500] + "...")
            print("=== END ===")

            data, error = parse_data_opinion_response(extract_response)
            if error:
                print(f"Extraction error: {error}")
                data = {}

            result = {
                'message_num': i,
                'date': msg['date'],
                'tg_channel': msg['name'],
                'category': category,
                'raw_text': msg['text'],
                'has_photo': msg.get('photo', ''),
                'extracted_data': json.dumps(data, ensure_ascii=False)
            }
            results.append(result)

        else:
            print(f"[Step 2: UNKNOWN CATEGORY - {category}]")
            result = {
                'message_num': i,
                'date': msg['date'],
                'tg_channel': msg['name'],
                'category': category,
                'raw_text': msg['text'],
                'has_photo': msg.get('photo', ''),
                'extracted_data': ''
            }
            results.append(result)

    # Write results
    print(f"\n{'='*80}")
    print(f"WRITING RESULTS")
    print(f"{'='*80}")

    with open(output_csv, 'w', encoding='utf-8', newline='') as f:
        fieldnames = ['message_num', 'date', 'tg_channel', 'category',
                     'raw_text', 'has_photo', 'extracted_data']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"Wrote {len(results)} processed messages to {output_csv}")

    # Summary
    print(f"\n{'='*80}")
    print(f"PROCESSING SUMMARY")
    print(f"{'='*80}")

    cat_counts = {}
    for r in results:
        cat = r['category']
        cat_counts[cat] = cat_counts.get(cat, 0) + 1

    print(f"Total messages processed: {len(results)}")
    print(f"Messages ignored: {len(messages) - len(results)}")
    print("\nBy category:")
    for cat, count in sorted(cat_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {cat}: {count}")

    return results

if __name__ == "__main__":
    results = process_all_telegram_messages(
        input_csv='test_data/telegram_messages.csv',
        output_csv='test_data/processed_telegram_messages.csv'
    )

    print("\n✓ Processing complete!")
    print(f"Output saved to: test_data/processed_telegram_messages.csv")
