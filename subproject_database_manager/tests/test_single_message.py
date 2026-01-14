"""
Quick test: Run categorization + extraction on a single message
"""
import sys
import json
sys.path.append('../')
sys.path.append('.')

from models import call_gpt41_mini, call_gpt5_mini
from categorization_prompts import get_categorization_prompt
from data_opinion_prompts import get_data_opinion_extraction_prompt
from interview_meeting_prompts import get_interview_extraction_prompt

# Test message
TEST_MESSAGE = """그...Plan G 일동은 모여서 숏을 치면서 새해를 맞이해버렸습니다. 오늘은 마지막 거래일이기도 하고, 새해니까....한 해 마무리하면서 거래 안하자는 분위기였는데...개발자 도비씨의 한마디에 그만.

"레포가 이렇게 튀었는데도 숏 안칠 거면 레포를 왜 봐요"

맞습니다. 우리는 돈 벌려고 만난 사람들이죠.

쉽지 않은 한 해 였습니다.
코인시장은 제도권 내에 들어오기 시작하면서 여러 네러티브가 동시에 작용하면서 대응하기가 더욱 어려워진 것도 같습니다.

저희도 이러한 어려운 신세계에서 좋은 모습을 보여드리기도, 또 아쉬운 모습을 보여드리기도 한 것 같습니다. 마음은 늘 한 결 같습니다. 보시는 분들 계좌 수익률에 단 1%라도 도움이 되길 바라는 마음으로 분석하고, 전망을 나누고 있습니다.

새해에는 더 좋은 모습 보여드리기 위해 더 열심히 해보겠습니다. 함께 해주세요 ^^"""

TEST_DATE = "2026-01-01"
TEST_CHANNEL = "plan_g_test"

def main():
    print("=" * 80)
    print("STEP 1: CATEGORIZATION")
    print("=" * 80)

    # Run categorization
    cat_prompt = get_categorization_prompt(TEST_MESSAGE, TEST_DATE)
    cat_messages = [{"role": "user", "content": cat_prompt}]
    cat_response = call_gpt41_mini(cat_messages)

    print("\n=== RAW CATEGORIZATION RESPONSE ===")
    print(cat_response)
    print("=== END ===\n")

    # Parse category
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
        print(f"Reasoning: {category_data.get('reasoning', 'N/A')}")

    except json.JSONDecodeError as e:
        print(f"Error parsing: {e}")
        category = 'error'

    # If extractable category, run extraction
    if category in ['data_opinion', 'interview_meeting']:
        print("\n" + "=" * 80)
        print(f"STEP 2: EXTRACTION ({category})")
        print("=" * 80)

        # Prepare message batch (single message)
        messages_batch = [{
            'text': TEST_MESSAGE,
            'date': TEST_DATE,
            'original_num': 1,
            'photo': '',
            'combined_text': TEST_MESSAGE
        }]

        if category == 'data_opinion':
            prompt = get_data_opinion_extraction_prompt(messages_batch, TEST_CHANNEL)
        else:
            prompt = get_interview_extraction_prompt(messages_batch, TEST_CHANNEL)

        ext_messages = [{"role": "user", "content": prompt}]
        ext_response = call_gpt5_mini(ext_messages)

        print("\n=== RAW EXTRACTION RESPONSE ===")
        print(ext_response)
        print("=== END ===\n")

        # Parse extraction
        try:
            ext_text = ext_response.strip()
            if ext_text.startswith("```"):
                lines = ext_text.split('\n')
                ext_text = '\n'.join(lines[1:-1]) if len(lines) > 2 else ext_text
                if ext_text.startswith("json"):
                    ext_text = ext_text[4:].strip()

            extracted = json.loads(ext_text)
            print("=== PARSED EXTRACTION ===")
            print(json.dumps(extracted, indent=2, ensure_ascii=False))

        except json.JSONDecodeError as e:
            print(f"Error parsing extraction: {e}")
    else:
        print(f"\nCategory '{category}' does not require extraction.")

if __name__ == "__main__":
    main()
