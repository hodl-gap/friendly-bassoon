import sys
import csv
import json
sys.path.append('../')
from models import call_gpt41_mini

def classify_message(message_text, message_date):
    """Check if message fits the data_opinion structure"""

    prompt = f"""You are analyzing a message from a financial research Telegram channel.

**Target Structure: "data_opinion"**

This structure is designed to extract the following fields from each message:

1. **source** - What research/institution is this from? (e.g., JPM, BoA, Bloomberg, Fed, or "하나증권" for own view)
2. **data_source** - Where did the DATA come from? (e.g., BLS, Bloomberg, Fed, ADP - could be same as source or different)
3. **asset_class** - What asset is discussed? (e.g., 국채, 주식, FX, 원자재 - can be empty)
4. **used_data** - What specific data is used/mentioned? (e.g., "비농업 고용 119k, 실업률 4.4%")
5. **what_happened** - What anomalies/changes/observations were noted in the data? (e.g., "실업률 4년래 최고치")
6. **interpretation** - What conclusions/implications are drawn? (e.g., "12월 금리 인하 가능성 증가")
7. **opinion_id** - Unique ID for grouped messages

**A message FITS this structure if:**
- It contains specific DATA (numbers, indicators, market data)
- It describes WHAT HAPPENED to that data (changes, observations, anomalies)
- It provides INTERPRETATION or conclusions about what the data means

**Examples that FIT:**
- "호주 10년물 금리는 11월 한달 간 18bp 상승해... RBA는 기준금리를 3.6%으로 동결... 금리 인하 사이클이 끝났을 가능성"
  → Has data (18bp rise), what happened (rates held), interpretation (cut cycle may be over)

**Examples that DON'T FIT:**
- "Daily recap 공유드립니다" (just announcement, no data/analysis)
- "11/17 (월) 23:00 윌리엄스 이사, 23:30 제퍼슨 이사..." (just schedule, no data/interpretation)
- Event announcements, advertisements, link-only messages

**Message to analyze:**
Date: {message_date}
Text: {message_text}

**Your task:**
Determine if this message fits the "data_opinion" structure described above.

**Output format (JSON only):**
```json
{{
    "fits_structure": true/false,
    "reason": "Brief explanation - does it have data + what_happened + interpretation?",
    "message_summary": "1-2 sentence summary of what this message is"
}}
```

Return ONLY the JSON."""

    messages = [{"role": "user", "content": prompt}]
    response = call_gpt41_mini(messages)
    return response

def classify_all_messages(csv_path, output_path):
    """Classify all messages"""

    # Read messages
    messages = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            messages.append(row)

    print(f"Loaded {len(messages)} messages from CSV\n")
    print("=" * 80)
    print("CLASSIFYING MESSAGES: Do they fit 'data_opinion' structure?")
    print("=" * 80)
    print("\nStructure requires: source + data_source + asset_class + used_data")
    print("                    + what_happened + interpretation + opinion_id")
    print("=" * 80)

    results = []
    fits_count = 0
    not_fits_count = 0

    for i, msg in enumerate(messages, 1):
        print(f"\n--- Message {i}/{len(messages)} ---")
        print(f"Date: {msg['date']}")
        print(f"Text preview: {msg['text'][:150]}...")

        # Classify
        response = classify_message(msg['text'], msg['date'])

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

            classification = json.loads(response_text)

            fits = classification.get('fits_structure', False)
            if fits:
                fits_count += 1
            else:
                not_fits_count += 1

            result = {
                'message_num': i,
                'date': msg['date'],
                'has_photo': 'Yes' if msg['photo'] else 'No',
                'fits_data_opinion': 'YES' if fits else 'NO',
                'reason': classification.get('reason', ''),
                'message_summary': classification.get('message_summary', ''),
                'text_preview': msg['text'][:300].replace('\n', ' ')
            }
            results.append(result)

            print(f"✓ Fits structure: {'YES' if fits else 'NO'}")
            print(f"  Reason: {result['reason']}")

        except json.JSONDecodeError as e:
            print(f"✗ Error parsing JSON: {e}")
            result = {
                'message_num': i,
                'date': msg['date'],
                'has_photo': 'Yes' if msg['photo'] else 'No',
                'fits_data_opinion': 'ERROR',
                'reason': f'JSON parse error: {str(e)}',
                'message_summary': '',
                'text_preview': msg['text'][:300].replace('\n', ' ')
            }
            results.append(result)

    # Write results
    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        fieldnames = ['message_num', 'date', 'has_photo', 'fits_data_opinion',
                     'reason', 'message_summary', 'text_preview']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"\n{'=' * 80}")
    print(f"CLASSIFICATION COMPLETE")
    print(f"{'=' * 80}")
    print(f"Total messages: {len(results)}")
    print(f"Fits 'data_opinion': {fits_count}")
    print(f"Does NOT fit: {not_fits_count}")

    # Show messages that don't fit
    non_fitting = [r for r in results if r['fits_data_opinion'] == 'NO']

    print(f"\n{'=' * 80}")
    print(f"MESSAGES THAT DON'T FIT 'data_opinion' STRUCTURE: {len(non_fitting)}")
    print(f"{'=' * 80}")

    if non_fitting:
        print("\nReview these to decide on new structures or ignore:\n")
        for r in non_fitting:
            print(f"Message #{r['message_num']}:")
            print(f"  Summary: {r['message_summary']}")
            print(f"  Reason: {r['reason']}")
            print(f"  Preview: {r['text_preview'][:150]}...")
            print()

    print(f"\nResults written to: {output_path}")
    print("\nNext: Review the CSV and decide what to do with non-fitting messages")

    return results

if __name__ == "__main__":
    results = classify_all_messages(
        csv_path='test_data/telegram_messages.csv',
        output_path='test_data/message_classification.csv'
    )
