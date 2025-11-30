import sys
import csv
import json
sys.path.append('../')
from models import call_gpt41_mini
from categorization_prompts import get_categorization_prompt

def categorize_message(message_text, message_date):
    """Categorize a single telegram message"""

    prompt = get_categorization_prompt(message_text, message_date)
    messages = [{"role": "user", "content": prompt}]
    response = call_gpt41_mini(messages)
    return response

def categorize_all_messages(csv_path, output_path):
    """Categorize all messages"""

    # Read messages
    messages = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            messages.append(row)

    print(f"Loaded {len(messages)} messages from CSV\n")
    print("=" * 80)
    print("CATEGORIZING ALL MESSAGES")
    print("=" * 80)

    results = []
    category_counts = {}

    for i, msg in enumerate(messages, 1):
        print(f"\n--- Message {i}/{len(messages)} ---")
        print(f"Date: {msg['date']}")
        print(f"Text preview: {msg['text'][:100]}...")

        # Categorize
        response = categorize_message(msg['text'], msg['date'])

        print(f"\n=== RAW LLM RESPONSE ===")
        print(response)
        print(f"=== END RESPONSE ===\n")

        # Parse JSON
        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                lines = response_text.split('\n')
                response_text = '\n'.join(lines[1:-1]) if len(lines) > 2 else response_text
                if response_text.startswith("json"):
                    response_text = response_text[4:].strip()

            categorization = json.loads(response_text)

            category = categorization.get('category', 'unknown')
            category_counts[category] = category_counts.get(category, 0) + 1

            result = {
                'message_num': i,
                'date': msg['date'],
                'name': msg['name'],
                'has_photo': 'Yes' if msg['photo'] else 'No',
                'category': category,
                'confidence': categorization.get('confidence', 'unknown'),
                'reason': categorization.get('reason', ''),
                'text_preview': msg['text'][:200].replace('\n', ' '),
                'full_text': msg['text']
            }
            results.append(result)

            print(f"✓ Category: {category} (confidence: {result['confidence']})")

        except json.JSONDecodeError as e:
            print(f"✗ Error parsing JSON: {e}")
            result = {
                'message_num': i,
                'date': msg['date'],
                'name': msg['name'],
                'has_photo': 'Yes' if msg['photo'] else 'No',
                'category': 'parse_error',
                'confidence': 'n/a',
                'reason': f'JSON parse error: {str(e)}',
                'text_preview': msg['text'][:200].replace('\n', ' '),
                'full_text': msg['text']
            }
            results.append(result)

    # Write results
    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        fieldnames = ['message_num', 'date', 'name', 'has_photo', 'category',
                     'confidence', 'reason', 'text_preview', 'full_text']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"\n{'=' * 80}")
    print(f"CATEGORIZATION COMPLETE")
    print(f"{'=' * 80}")
    print(f"Total messages: {len(results)}")
    print(f"\nCategory Distribution:")
    for category, count in sorted(category_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {category}: {count}")

    # Show breakdown by category
    print(f"\n{'=' * 80}")
    print(f"CATEGORY BREAKDOWN")
    print(f"{'=' * 80}")

    for category in ['greeting', 'schedule', 'event_announcement', 'interview_meeting', 'data_update', 'data_opinion', 'other']:
        cat_msgs = [r for r in results if r['category'] == category]
        if cat_msgs:
            print(f"\n{category.upper()} ({len(cat_msgs)} messages):")
            for r in cat_msgs:
                print(f"  #{r['message_num']}: {r['text_preview'][:80]}...")

    print(f"\n{'=' * 80}")
    print(f"NEXT STEPS")
    print(f"{'=' * 80}")

    ignore_count = len([r for r in results if r['category'] in ['greeting', 'event_announcement']])
    save_raw_count = len([r for r in results if r['category'] in ['schedule', 'data_update']])
    extract_count = len([r for r in results if r['category'] in ['interview_meeting', 'data_opinion']])
    other_count = len([r for r in results if r['category'] == 'other'])

    print(f"Messages to IGNORE: {ignore_count}")
    print(f"Messages to SAVE RAW TEXT: {save_raw_count}")
    print(f"Messages needing EXTRACTION: {extract_count}")
    print(f"  - interview_meeting: {len([r for r in results if r['category'] == 'interview_meeting'])}")
    print(f"  - data_opinion: {len([r for r in results if r['category'] == 'data_opinion'])}")
    print(f"Messages flagged as OTHER (need review): {other_count}")

    print(f"\nResults written to: {output_path}")

    return results

if __name__ == "__main__":
    results = categorize_all_messages(
        csv_path='test_data/telegram_messages.csv',
        output_path='test_data/categorized_messages.csv'
    )
