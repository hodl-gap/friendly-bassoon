import sys
import csv
import json
from datetime import datetime
sys.path.append('../')
from models import call_claude_sonnet
import base64

def encode_image(image_path):
    """Encode image to base64"""
    try:
        with open(image_path, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')
    except Exception as e:
        print(f"Error encoding image {image_path}: {e}")
        return None

def create_extraction_prompt(messages_batch):
    """Create prompt for structured extraction with opinion grouping"""

    prompt = """You are analyzing financial research messages from a Telegram channel. Your task is to:

1. Extract structured information from each message
2. Detect which messages belong to the same "opinion/article" (messages sent close together in time that discuss the same topic or are clearly continuations)
3. Assign the same opinion_id to messages that are part of the same article/analysis

**Opinion Grouping Rules:**
- Messages sent within a few minutes of each other discussing the same topic → same opinion_id
- Messages that are clearly continuations (e.g., follow-up points, additional data on same topic) → same opinion_id
- Daily recaps, standalone announcements, or different topics → different opinion_id
- Use format: `[하나증권 해외채권] 허성우_N` where N increments for each new opinion

**For each message, extract:**

1. **source**: Where is this research from? Options:
   - Specific institution name (e.g., "Bloomberg", "Fed", "BLS", "영국 재무부")
   - "하나증권" (if it's Hana Securities' own analysis/view)
   - "연준" or specific Fed official name (if direct Fed communication)
   - If unclear, use "하나증권"

2. **data_source**: Where did the DATA come from? (could be different from source)
   - E.g., "BLS", "Bloomberg", "뉴욕 연은", "ADP", "FOMC 회의록"
   - Can be same as source
   - Empty string if no specific data mentioned

3. **asset_class**: What asset class is discussed?
   - "국채" (government bonds), "회사채" (corporate bonds), "주식" (equities), "FX", "원자재" (commodities)
   - Can combine: "국채, 주식"
   - Empty string if not applicable

4. **used_data**: What specific data points are mentioned?
   - E.g., "비농업 고용 119k, 실업률 4.4%, 시간당 임금 3.8%"
   - E.g., "10년물 국채금리 18bp 상승"
   - Empty string if no specific data

5. **what_happened**: What changes/anomalies/observations were noted?
   - E.g., "실업률 4년래 최고치, 제조업 고용 5개월 연속 역성장"
   - E.g., "길트 장기물 금리 급등"
   - Empty string if just announcement/schedule

6. **interpretation**: What conclusions or implications are drawn?
   - E.g., "12월 금리 인하 가능성 증가"
   - E.g., "재정 신뢰도 우려 확대"
   - Empty string if no interpretation provided

7. **opinion_id**: Assign opinion ID based on grouping logic above

**Messages to analyze:**

"""

    for i, msg in enumerate(messages_batch):
        prompt += f"\n--- Message {i+1} ---\n"
        prompt += f"Timestamp: {msg['date']}\n"
        prompt += f"Text: {msg['text']}\n"
        if msg['photo']:
            prompt += f"Has photo: Yes ({msg['photo']})\n"
        prompt += "\n"

    prompt += """
**Output format:**
Return a JSON array where each element represents ONE message. If a message has both text and photo, create TWO entries (one for text analysis, one for image analysis) with the same opinion_id.

For text messages:
```json
{
    "message_index": 1,
    "entry_type": "text",
    "source": "...",
    "data_source": "...",
    "asset_class": "...",
    "used_data": "...",
    "what_happened": "...",
    "interpretation": "...",
    "opinion_id": "[하나증권 해외채권] 허성우_1"
}
```

For image analysis (when photo exists):
```json
{
    "message_index": 1,
    "entry_type": "image",
    "source": "...",
    "data_source": "...",
    "asset_class": "...",
    "used_data": "...",
    "what_happened": "...",
    "interpretation": "...",
    "opinion_id": "[하나증권 해외채권] 허성우_1"
}
```

Return ONLY the JSON array, no other text.
"""

    return prompt

def process_batch_with_images(messages_batch, base_path='test_data/ChatExport_2025-11-21/'):
    """Process a batch of messages, including image analysis"""

    # Create the extraction prompt
    text_prompt = create_extraction_prompt(messages_batch)

    # Build messages for API call
    # First, do text-only analysis
    text_messages = [
        {
            "role": "user",
            "content": [{"type": "text", "text": text_prompt}]
        }
    ]

    print(f"\n=== Processing batch of {len(messages_batch)} messages ===")
    print("Calling LLM for text analysis...")

    text_response = call_claude_sonnet(text_messages)

    print("\n=== RAW LLM RESPONSE (Text Analysis) ===")
    print(text_response)
    print("=== END RAW RESPONSE ===\n")

    # Parse JSON response
    try:
        # Extract JSON from response (handle markdown code blocks)
        response_text = text_response.strip()
        if response_text.startswith("```"):
            # Remove markdown code blocks
            lines = response_text.split('\n')
            response_text = '\n'.join(lines[1:-1]) if len(lines) > 2 else response_text

        results = json.loads(response_text)
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}")
        print("Attempting to extract JSON from response...")
        # Try to find JSON array in response
        start = text_response.find('[')
        end = text_response.rfind(']') + 1
        if start != -1 and end > start:
            try:
                results = json.loads(text_response[start:end])
            except:
                print("Failed to extract JSON. Returning empty results.")
                return []
        else:
            return []

    # Now analyze images for messages that have photos
    for msg in messages_batch:
        if msg['photo']:
            photo_path = base_path + msg['photo']
            image_data = encode_image(photo_path)

            if image_data:
                print(f"Analyzing image: {msg['photo']}")

                # Create image analysis message
                image_messages = [
                    {
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
                                "text": f"""Analyze this chart/image from a financial research message.

**Context:** This image was sent with the following text message:
"{msg['text']}"

**Extract:**
1. **source**: Who created this chart? (e.g., Bloomberg, Fed, 하나증권, etc.)
2. **data_source**: Where is the data from? (e.g., Bloomberg, BLS, Fed, etc.)
3. **asset_class**: What asset class is shown? (국채, 주식, FX, etc.)
4. **used_data**: What specific data is displayed? (data series, time periods, values)
5. **what_happened**: What patterns/changes are visible in the chart?
6. **interpretation**: What does the chart suggest or conclude?

Return ONLY a JSON object with these fields. If the image is not a chart (e.g., just text/announcement), indicate that in the interpretation."""
                            }
                        ]
                    }
                ]

                image_response = call_claude_sonnet(image_messages)

                print("\n=== RAW LLM RESPONSE (Image Analysis) ===")
                print(image_response)
                print("=== END RAW RESPONSE ===\n")

                # Parse image analysis (simplified for now - can be enhanced)
                # For now, we'll add a placeholder entry
                # You can enhance this to parse the image analysis JSON

    return results

def process_all_messages(csv_path, output_path, batch_size=7, overlap=2):
    """Process all messages with overlapping batches"""

    # Read all messages
    messages = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            messages.append(row)

    print(f"Loaded {len(messages)} messages from CSV")

    all_results = []
    i = 0

    while i < len(messages):
        # Determine batch end
        batch_end = min(i + batch_size, len(messages))
        batch = messages[i:batch_end]

        # Process batch
        batch_results = process_batch_with_images(batch)
        all_results.extend(batch_results)

        # Move to next batch with overlap
        # If this is not the last batch, move forward by (batch_size - overlap)
        if batch_end < len(messages):
            i += (batch_size - overlap)
        else:
            break

    # Write results to CSV
    if all_results:
        fieldnames = ['message_index', 'entry_type', 'source', 'data_source',
                     'asset_class', 'used_data', 'what_happened',
                     'interpretation', 'opinion_id', 'tg_channel', 'raw_text']

        with open(output_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            # Merge with original message data
            for result in all_results:
                msg_idx = result.get('message_index', 1) - 1
                if 0 <= msg_idx < len(messages):
                    original_msg = messages[msg_idx]
                    result['tg_channel'] = original_msg['name']
                    result['raw_text'] = original_msg['text']

                writer.writerow(result)

        print(f"\nWrote {len(all_results)} entries to {output_path}")

    return all_results

if __name__ == "__main__":
    # Test with first 7 messages
    print("Starting message processing...")

    results = process_all_messages(
        csv_path='test_data/telegram_messages.csv',
        output_path='test_data/processed_messages.csv',
        batch_size=7,
        overlap=2
    )

    print(f"\nProcessing complete! Generated {len(results)} entries.")
