import sys
import json
sys.path.append('../')
from models import call_claude_sonnet
from data_opinion_prompts import get_data_opinion_extraction_prompt

def extract_data_opinion(message_text, message_date):
    """Extract structured data from data_opinion message"""

    prompt = get_data_opinion_extraction_prompt(message_text, message_date)
    messages = [{"role": "user", "content": prompt}]
    response = call_claude_sonnet(messages)
    return response

def parse_data_opinion_response(response_text):
    """Parse JSON response from LLM"""

    try:
        # Clean up markdown code blocks
        response_text = response_text.strip()
        if response_text.startswith("```"):
            lines = response_text.split('\n')
            response_text = '\n'.join(lines[1:-1]) if len(lines) > 2 else response_text
            if response_text.startswith("json"):
                response_text = response_text[4:].strip()

        data = json.loads(response_text)
        return data, None
    except json.JSONDecodeError as e:
        return None, f"JSON parse error: {str(e)}"

if __name__ == "__main__":
    # Test with a sample data_opinion message
    test_message = """호주-미국 10년물 스프레드도 확대되는 양상. 즉, 호주와 미국 국채 금리 간 차별화 장세 이어지는 중

최근 호주 10년물 국채금리 상승세는 가팔랐음. 호주 10년물 금리는 11월 한달 간 18bp 상승해 한국 다음으로 주요국 중 가장 높은 상승세 기록

RBA는 2주 전 기준금리를 3.6%으로 동결 결정. 불록 RBA 총재는 인플레 반등 조짐을 보이고 소비 지출이 예상보다 강세를 보이면서 단기적으로 추가 인하 가능성을 제한

화요일 공개된 의사록에서 위원들은 금융여건이 더 이상 제한적이지 않을 수도 있음을 인정

글로벌 IB들은 RBA의 금리 인하 사이클이 끝났을 가능성을 시사"""

    test_date = "2025-11-18T14:30:10"

    print("Testing data_opinion extraction...")
    print("=" * 80)
    print(f"Message: {test_message[:200]}...")
    print("=" * 80)

    response = extract_data_opinion(test_message, test_date)

    print("\n=== FULL RAW LLM RESPONSE ===")
    print(response)
    print("=== END RAW RESPONSE ===\n")

    data, error = parse_data_opinion_response(response)

    if error:
        print(f"Error: {error}")
    else:
        print("\n=== PARSED STRUCTURED DATA ===")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        print("\n=== FIELD SUMMARY ===")
        print(f"Source: {data.get('source')}")
        print(f"Data source: {data.get('data_source')}")
        print(f"Asset class: {data.get('asset_class')}")
        print(f"Used data: {data.get('used_data')}")
        print(f"What happened: {data.get('what_happened')[:100]}...")
        print(f"Interpretation: {data.get('interpretation')[:100]}...")
