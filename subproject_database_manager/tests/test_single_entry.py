"""
Test QA Validation on a Single Entry

Quick test to validate QA system on one real entry from the CSV
"""

import sys
import os
from pathlib import Path

# Add parent directory to path
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))

from qa_validation import validate_extraction
import json


def test_single_csv_entry():
    """Test QA validation on one real entry from processed CSV"""

    # Real extracted data from processed_루팡_2025-11-23.csv
    extracted_data = {
        "source": "The National News",
        "data_source": "UAE Ministry of Foreign Affairs, TRG Datacenters",
        "asset_class": "",
        "used_data": "UAE $1 billion AI infrastructure initiative for Africa, UAE ranks 2nd globally in AI supercomputing capability after US, UAE has over 188,000 AI chips, UAE has 6.4GW total power capacity",
        "what_happened": "UAE announced 'AI for Development' initiative at G20 summit in Johannesburg, committing $1 billion to expand AI infrastructure and AI-based services across Africa. Initiative will provide access to AI computing power, technical expertise, global partnerships, and support projects in education, agriculture, healthcare, digital identity, and climate adaptation. UAE ranked 2nd globally in AI supercomputing capability based on TRG Datacenters 2025 research.",
        "interpretation": "UAE is positioning itself as a global AI leader and extending its technological capabilities to support development in the Global South, particularly Africa. This represents a shift from experimental AI deployment to large-scale practical implementation for national development priorities. The initiative aims to ensure no country is left behind in the AI era.",
        "tags": "irrelevant"
    }

    raw_text = """**UAE, 아프리카 전역 AI 인프라 확장 위해 10억 달러 규모 이니셔티브 발표**
**
요하네스버그 G20 정상회의에서 발표**

아랍에미리트(UAE)가 토요일 남아프리카공화국에서 열린 G20 정상회의에서 **아프리카 전역의 인공지능(AI) 인프라 및 AI 기반 서비스 확대를 위한 '개발을 위한 AI(AI for Development)' 이니셔티브를 발표하며, 10억 달러 규모의 계획을 공개했다.**

이 이니셔티브는 AI 컴퓨팅 파워 접근성, 기술 전문성, 글로벌 파트너십 제공, 그리고 교육·농업·의료·디지털 신원·기후 적응 분야 프로젝트를 추진하는 아프리카 국가들을 지원하는 내용을 담고 있다고 UAE 외교부 국무장관 사이드 빈 무바라크 알 하제리(Saeed Bin Mubarak Al Hajeri)는 밝혔다.

텍사스 기반 AI 슈퍼컴퓨팅 전문 기업 TRG Datacenters의 2025년 연구에 따르면,** UAE는 AI 슈퍼컴퓨팅 능력, AI 기업 활동, 정부의 AI 준비도를 종합적으로 평가한 결과 전 세계 2위, 미국 다음 순위에 올랐다. TRG는 UAE가 AI 칩 18만8,000개 이상과 총 6.4GW의 전력 용량을 보유**하고 있다고 평가한다."""

    print("="*80)
    print("TEST: QA Validation on Single Real Entry")
    print("="*80)

    result = validate_extraction(
        extracted_data=extracted_data,
        raw_text=raw_text,
        category='data_opinion'
    )

    print(f"\n{'='*80}")
    print("QA RESULT SUMMARY")
    print(f"{'='*80}")
    print(f"Verdict: {result['qa_verdict']}")
    print(f"Confidence: {result['qa_confidence']}")
    print(f"\nDimension Scores:")
    print(f"  Retrievability: {result['qa_retrievability_score']}")
    print(f"  Completeness: {result['qa_completeness_score']}")
    print(f"  Answerability: {result['qa_answerability_score']}")

    # Parse and pretty print the arrays
    print(f"\nMissing Pieces:")
    missing = json.loads(result['qa_missing_pieces']) if result['qa_missing_pieces'] else []
    for item in missing:
        print(f"  - {item}")

    print(f"\nBroken Retrieval Paths:")
    broken = json.loads(result['qa_broken_paths']) if result['qa_broken_paths'] else []
    for item in broken:
        print(f"  - {item}")

    print(f"\nSuggested Fixes:")
    fixes = json.loads(result['qa_suggested_fixes']) if result['qa_suggested_fixes'] else []
    for item in fixes:
        print(f"  - {item}")


if __name__ == "__main__":
    test_single_csv_entry()
