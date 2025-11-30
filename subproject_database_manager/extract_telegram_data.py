import json
import pandas as pd

def extract_text_from_entities(text_field):
    """Extract and combine text from text or text_entities field"""
    if isinstance(text_field, str):
        return text_field
    elif isinstance(text_field, list):
        texts = []
        for item in text_field:
            if isinstance(item, str):
                texts.append(item)
            elif isinstance(item, dict) and 'text' in item:
                texts.append(item['text'])
        return ''.join(texts)
    return ''

def extract_telegram_messages(json_path):
    """Extract name, from, date, photo, and text from Telegram JSON export"""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    channel_name = data.get('name', '')
    messages = data.get('messages', [])

    records = []
    for msg in messages:
        record = {
            'name': channel_name,
            'from': msg.get('from', ''),
            'date': msg.get('date', ''),
            'photo': msg.get('photo', ''),
            'text': extract_text_from_entities(msg.get('text', ''))
        }
        records.append(record)

    df = pd.DataFrame(records)
    return df

if __name__ == "__main__":
    json_path = 'test_data/ChatExport_2025-11-21/result.json'
    df = extract_telegram_messages(json_path)

    # Save to csv
    output_path = 'test_data/telegram_messages.csv'
    df.to_csv(output_path, index=False)

    print(f"Extracted {len(df)} messages")
    print(f"Saved to {output_path}")
    print("\nFirst few rows:")
    print(df.head())
