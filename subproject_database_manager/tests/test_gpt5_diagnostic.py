"""
GPT-5 Diagnostic Test Script

Run this to understand why GPT-5 returns empty responses.
Expected output will show token usage, finish_reason, and whether reasoning is consuming the budget.
"""

import sys
sys.path.append('..')

from models import call_gpt5_diagnostic

# Test 1: Simple extraction (similar to what process_messages uses)
print("\n" + "=" * 80)
print("TEST 1: Simple extraction task")
print("=" * 80)

messages_simple = [
    {"role": "user", "content": "Extract key points from: The Fed raised rates by 25bp today. Markets reacted positively."}
]

result1 = call_gpt5_diagnostic(messages_simple)


# Test 2: More complex extraction (like actual workflow)
print("\n" + "=" * 80)
print("TEST 2: Structured extraction task (similar to actual workflow)")
print("=" * 80)

messages_complex = [
    {
        "role": "system",
        "content": """You are a financial research analyst. Extract structured data from the message.
Return JSON with these fields:
- data_source: string
- what_happened: string
- interpretation: string
- tags: array of strings"""
    },
    {
        "role": "user",
        "content": """Extract from this message:

The RDE (Reserve Demand Elasticity) rose from -0.2 to 0.5 yesterday.
This is a significant shift indicating extreme money demand in the system.
The Fed may need to pause QT soon."""
    }
]

result2 = call_gpt5_diagnostic(messages_complex)


# Test 3: With lower max_tokens to see if reasoning exhausts budget
print("\n" + "=" * 80)
print("TEST 3: Same task with lower max_tokens (2000) to test token exhaustion")
print("=" * 80)

result3 = call_gpt5_diagnostic(messages_complex, max_tokens=2000)


# Summary
print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print(f"Test 1 (simple): {'SUCCESS' if result1 else 'EMPTY'}")
print(f"Test 2 (complex): {'SUCCESS' if result2 else 'EMPTY'}")
print(f"Test 3 (low tokens): {'SUCCESS' if result3 else 'EMPTY'}")
print("\nCheck the output above to understand:")
print("1. Is finish_reason='stop' or 'length'?")
print("2. Are completion_tokens_details showing reasoning token usage?")
print("3. Is the model spending tokens on reasoning before output?")


# Test 4: Parallel processing test
print("\n" + "=" * 80)
print("TEST 4: Parallel batch processing (3 calls concurrently)")
print("=" * 80)

import asyncio
from models import process_batch_parallel

messages_batch = [
    [{"role": "user", "content": "Extract key points: Fed raised rates 25bp. Markets positive."}],
    [{"role": "user", "content": "Extract key points: ECB held rates steady. Euro weakened."}],
    [{"role": "user", "content": "Extract key points: BOJ intervened in forex. Yen strengthened."}],
]

print(f"Sending {len(messages_batch)} requests in parallel...")

async def run_parallel_test():
    results = await process_batch_parallel(
        messages_batch,
        model_func="gpt5",
        max_concurrent=3,
        max_tokens=4000
    )
    return results

results = asyncio.run(run_parallel_test())

print("\nParallel Results:")
for i, r in enumerate(results):
    status = "SUCCESS" if r else "EMPTY/FAILED"
    print(f"  Batch {i+1}: {status}")
    if r:
        print(f"    Preview: {r[:100]}...")

empty_count = sum(1 for r in results if not r)
print(f"\nParallel Summary: {len(results) - empty_count}/{len(results)} succeeded")


# Test 5: Test with UPDATED concise prompt format
print("\n" + "=" * 80)
print("TEST 5: Testing UPDATED concise extraction prompt")
print("=" * 80)

# Import the actual prompt function
from data_opinion_prompts import get_data_opinion_extraction_prompt

test_messages = [
    {
        'date': '2025-11-26',
        'text': '오늘 RDE가 -0.2에서 0.5로 급등했습니다. 이는 시스템 내 극단적인 자금 수요를 나타내며, 연준이 곧 QT를 중단해야 할 수도 있음을 시사합니다. TGA 잔고도 750B로 감소했습니다.',
        'photo': True
    },
    {
        'date': '2025-11-26',
        'text': '추가로, O/N RRP 시설 사용량도 급감하여 현재 100B 수준입니다. 이는 머니마켓 펀드들이 더 높은 수익을 찾아 이동하고 있음을 보여줍니다.',
        'photo': False
    }
]

# Use stub metrics mapping for test
metrics_mapping_text = """**Liquidity Metrics Mapping Table:**
| Raw Term | Normalized Name | Category |
|----------|-----------------|----------|
| TGA, TGA 잔고 | TGA | direct |
| ON RRP, O/N RRP | ON_RRP | direct |
| RDE | RDE | direct |"""

prompt = get_data_opinion_extraction_prompt(test_messages, "hyottchart", metrics_mapping_text)

print(f"Prompt length: {len(prompt)} chars")
print("\n--- Prompt Preview (first 1000 chars) ---")
print(prompt[:1000])
print("...")

messages_long = [{"role": "user", "content": prompt}]
result5 = call_gpt5_diagnostic(messages_long, max_tokens=8000)

print(f"\nTest 5 Result: {'SUCCESS' if result5 else 'EMPTY'}")

# Parse and show the result format
if result5:
    import json
    try:
        parsed = json.loads(result5)
        print("\n--- Extracted Structure (first entry) ---")
        if parsed and len(parsed) > 0:
            entry = parsed[0]
            print(f"used_data: {entry.get('used_data', 'N/A')}")
            print(f"what_happened: {entry.get('what_happened', 'N/A')}")
            print(f"interpretation: {entry.get('interpretation', 'N/A')}")
    except:
        pass


# Test 6: Test retry with fallback function
print("\n" + "=" * 80)
print("TEST 6: Parallel batch with retry and fallback")
print("=" * 80)

from models import process_batch_parallel_with_retry

messages_batch_6 = [
    [{"role": "user", "content": "Extract key points: Fed raised rates 25bp. Markets positive."}],
    [{"role": "user", "content": "Extract key points: ECB held rates steady. Euro weakened."}],
    [{"role": "user", "content": "Extract key points: BOJ intervened in forex. Yen strengthened."}],
]

print(f"Sending {len(messages_batch_6)} requests with retry + fallback...")

async def run_retry_test():
    results = await process_batch_parallel_with_retry(
        messages_batch_6,
        model_func="gpt5",
        max_concurrent=3,
        max_tokens=4000,
        max_retries=2,
        fallback_model="claude_sonnet"
    )
    return results

results6 = asyncio.run(run_retry_test())

print("\nRetry Test Results:")
for i, r in enumerate(results6):
    status = "SUCCESS" if r else "EMPTY/FAILED"
    print(f"  Batch {i+1}: {status}")
    if r:
        print(f"    Preview: {r[:80]}...")
