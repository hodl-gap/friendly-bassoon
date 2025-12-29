import sys
import json
sys.path.append('../')
from models import call_claude_sonnet
from interview_meeting_prompts import get_interview_extraction_prompt

def extract_interview_meeting(message_text, message_date):
    """Extract structured data from interview/meeting message"""

    prompt = get_interview_extraction_prompt(message_text, message_date)
    messages = [{"role": "user", "content": prompt}]
    response = call_claude_sonnet(messages)
    return response

def parse_interview_response(response_text):
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
    # Test with a sample interview_meeting message
    test_message = """🇺🇸주간 연준 발언 정리 (11/17~21)

제퍼슨 연준 이사 (투표권 O, 중립)
(11/17)
- 최근 몇 달 동안 인플레에 대한 상승 위험 증가에 비해 고용에 대한 하방 위험이 증가하면서 경제의 위험 균형이 변화
- 12월 인하에 대해선 옵션을 열여두고 있음
- 연준의 2% 인플레 목표로의 진전은 관세 영향을 반영하여 정체된 것으로 보임

월러 연준 이사 (투표권 O, 비둘기)
(11/17)
- 12월 인하 지지. 노동 시장과 저소득. 중산층 소비자에게 피해를 주고 있는 금리를 다시 낮춰야 한다
- 노동시장에 초점. 9월 고용 데이터 발표 이후에도 생각이 바뀌진 않을 것

바킨 리치몬드 연은 총재 (투표권 X, 중립)
(11/18)
- 기업에게 노동 시장을 어떻게 보는지 묻는다면, 그들은 균형 잡혔다고 말할 것. 그러나 자세히 들여다보면 그렇지 않은 듯
- 대기업의 최근 정리해고 발표는 노동 시장에 주의할 추가적인 이유를 제시
- 인플레이션은 여전히 다소 높지만 크게 증가하지는 않을 것

마이클 바 연준 이사 (투표권 O, 중립)
(11/18)
- 기관의 감독을 약화시키면 은행 시스템에 축적되는 실제 위험이 발생할 수 있으며, 시간이 지남에 따라 위기의 씨앗을 뿌릴 수 있다고 경고
- 사모 신용(private credit)을 잠재적인 위험의 영역으로 보고, 관련된 보험 시스템에 취약성이 있다고 지적"""

    test_date = "2025-11-19T07:46:15"

    print("Testing interview_meeting extraction...")
    print("=" * 80)
    print(f"Message: {test_message[:200]}...")
    print("=" * 80)

    response = extract_interview_meeting(test_message, test_date)

    print("\n=== FULL RAW LLM RESPONSE ===")
    print(response)
    print("=== END RAW RESPONSE ===\n")

    data, error = parse_interview_response(response)

    if error:
        print(f"Error: {error}")
    else:
        print("\n=== PARSED STRUCTURED DATA ===")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        print("\n=== SUMMARY ===")
        print(f"Meeting type: {data.get('meeting_type')}")
        print(f"Date: {data.get('date')}")
        print(f"Number of participants: {len(data.get('participants', []))}")
        for p in data.get('participants', []):
            print(f"  - {p.get('name')} ({p.get('title')}): {len(p.get('statements', []))} statements")
