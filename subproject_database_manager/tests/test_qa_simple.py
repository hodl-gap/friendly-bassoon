"""
Simple QA test with the GPT-5 extracted structure
"""

import sys
sys.path.append('..')

from qa_validation import validate_extraction

# The extracted data from GPT-5 test
extracted_data = [
  {
    "message_index": 1,
    "opinion_id": "hyottchart_1",
    "source": "Federal Reserve",
    "data_source": "Federal Reserve (funding/operations, H.4.1), U.S. Department of the Treasury (Daily Treasury Statement for TGA)",
    "asset_class": "Rates and Money Markets",
    "used_data": "RDE jumped from -0.2 to 0.5; Treasury General Account (TGA) balance decreased to $750B",
    "what_happened": "A sharp rise in RDE indicates elevated funding demand; TGA balance fell to $750B",
    "interpretation": "Funding stress is high and may force the Fed to halt QT soon; TGA drawdown injects liquidity into the banking system",
    "tags": "direct_liquidity",
    "liquidity_metrics": [
      {
        "raw": "-0.2 to 0.5",
        "normalized": "rde_index",
        "value": 0.5,
        "direction": "up"
      },
      {
        "raw": "750B",
        "normalized": "tga_balance_usd_bn",
        "value": 750,
        "direction": "down"
      }
    ],
    "metric_relationships": [
      {
        "cause": "RDE increases",
        "effect": "Funding stress increases"
      },
      {
        "cause": "Funding stress increases",
        "effect": "Higher likelihood the Fed halts QT"
      },
      {
        "cause": "TGA balance decreases",
        "effect": "Bank reserves increase (system liquidity injection)"
      }
    ]
  },
  {
    "message_index": 2,
    "opinion_id": "hyottchart_1",
    "source": "Federal Reserve",
    "data_source": "Federal Reserve Bank of New York (Overnight Reverse Repo Facility usage)",
    "asset_class": "Money Markets",
    "used_data": "Overnight RRP usage fell to $100B",
    "what_happened": "ON RRP balances declined sharply to about $100B",
    "interpretation": "Money market funds are reallocating from the Fed facility to higher-yield alternatives, putting more cash into private markets",
    "tags": "direct_liquidity",
    "liquidity_metrics": [
      {
        "raw": "100B",
        "normalized": "on_rrp_usage_usd_bn",
        "value": 100,
        "direction": "down"
      }
    ],
    "metric_relationships": [
      {
        "cause": "ON RRP usage decreases",
        "effect": "MMFs move cash to higher-yield assets (bills/private repo)"
      },
      {
        "cause": "ON RRP usage decreases",
        "effect": "Less cash parked at the Fed and more liquidity flows to private markets"
      }
    ]
  }
]

# Original raw text (Korean)
raw_text = """오늘 RDE가 -0.2에서 0.5로 급등했습니다. 이는 시스템 내 극단적인 자금 수요를 나타내며, 연준이 곧 QT를 중단해야 할 수도 있음을 시사합니다. TGA 잔고도 750B로 감소했습니다.

추가로, O/N RRP 시설 사용량도 급감하여 현재 100B 수준입니다. 이는 머니마켓 펀드들이 더 높은 수익을 찾아 이동하고 있음을 보여줍니다."""

print("=" * 80)
print("TESTING QA VALIDATION WITH GPT-5 EXTRACTED STRUCTURE")
print("=" * 80)

# Test with the first message extraction
import json
result = validate_extraction(
    extracted_data=json.dumps(extracted_data[0]),
    raw_text=raw_text,
    category="data_opinion"
)

print("\n" + "=" * 80)
print("QA VALIDATION RESULT")
print("=" * 80)
print(f"Verdict: {result['qa_verdict']}")
print(f"Confidence: {result['qa_confidence']}")
print(f"Retrievability Score: {result['qa_retrievability_score']}")
print(f"Completeness Score: {result['qa_completeness_score']}")
print(f"Answerability Score: {result['qa_answerability_score']}")
print(f"\nChain of Thought:\n{result['qa_chain_of_thought']}")

if result['qa_missing_pieces']:
    print(f"\nMissing Pieces: {result['qa_missing_pieces']}")
if result['qa_broken_paths']:
    print(f"Broken Paths: {result['qa_broken_paths']}")
if result['qa_suggested_fixes']:
    print(f"Suggested Fixes: {result['qa_suggested_fixes']}")
