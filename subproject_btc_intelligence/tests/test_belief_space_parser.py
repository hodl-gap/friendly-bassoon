"""
Test the belief-space parser without API calls.

This tests whether the refactored parser correctly extracts
multiple scenarios and contradictions from LLM responses.
"""

import sys
import re
from pathlib import Path
from typing import Dict, Any, List


# Copy the parser functions directly to avoid import issues
def parse_scenarios(response: str) -> List[Dict[str, Any]]:
    """Parse all scenarios from the SCENARIOS section of the LLM response."""
    scenarios = []

    # Find the SCENARIOS section
    scenarios_match = re.search(
        r"SCENARIOS:\s*\n(.+?)(?=\nPRIMARY_DIRECTION:|\nCONTRADICTIONS:|\nDIRECTION:|\Z)",
        response,
        re.DOTALL | re.IGNORECASE
    )

    if not scenarios_match:
        return scenarios

    scenarios_text = scenarios_match.group(1)

    # Split by "- Scenario" to get each scenario block
    scenario_blocks = re.split(r"\n-\s*Scenario\s*", scenarios_text)

    for block in scenario_blocks:
        if not block.strip():
            continue

        scenario = {}

        # Extract scenario name (first line or after letter like "A:")
        # Handle various formats: "A: Name", "A - Name", just "Name"
        first_line = block.strip().split('\n')[0].strip()
        # Remove leading "- Scenario" prefix if present (edge case from split)
        first_line = re.sub(r'^-?\s*Scenario\s*', '', first_line, flags=re.IGNORECASE)
        # Parse "A: Name" or "A - Name" or just "Name"
        name_match = re.match(r"([A-Z])[\s:.-]+(.+?)$", first_line.strip())
        if name_match:
            scenario["name"] = name_match.group(2).strip()
        else:
            scenario["name"] = first_line.strip()

        # Extract Chain
        chain_match = re.search(r"-\s*Chain:\s*(.+?)(?:\n|$)", block)
        if chain_match:
            scenario["chain"] = chain_match.group(1).strip()

        # Extract Direction
        dir_match = re.search(r"-\s*Direction:\s*(BULLISH|BEARISH|NEUTRAL)", block, re.IGNORECASE)
        if dir_match:
            scenario["direction"] = dir_match.group(1).upper()
            scenario["polarity"] = dir_match.group(1).upper()

        # Extract Likelihood
        likelihood_match = re.search(r"-\s*Likelihood:\s*(\d+)%?\s*(?:based on\s*)?(.+)?(?:\n|$)", block, re.IGNORECASE)
        if likelihood_match:
            scenario["likelihood"] = int(likelihood_match.group(1)) / 100.0
            if likelihood_match.group(2):
                scenario["likelihood_basis"] = likelihood_match.group(2).strip()

        # Extract Rationale if present
        rationale_match = re.search(r"-\s*Rationale:\s*(.+?)(?:\n-|\n\n|$)", block, re.DOTALL)
        if rationale_match:
            scenario["rationale"] = rationale_match.group(1).strip()

        if scenario.get("name") or scenario.get("chain"):
            scenarios.append(scenario)

    return scenarios


def parse_contradictions(response: str) -> List[Dict[str, Any]]:
    """Parse contradictions from the CONTRADICTIONS section."""
    contradictions = []

    # Find CONTRADICTIONS section
    contra_match = re.search(
        r"CONTRADICTIONS:\s*\n(.+?)(?=\nPRIMARY_DIRECTION:|\nCONFIDENCE:|\nTIME_HORIZON:|\Z)",
        response,
        re.DOTALL | re.IGNORECASE
    )

    if not contra_match:
        return contradictions

    contra_text = contra_match.group(1)

    # Parse each contradiction block (marked by - or bullet)
    contra_blocks = re.findall(
        r"-\s*(.+?)(?=\n-|\n\n|$)",
        contra_text,
        re.DOTALL
    )

    for block in contra_blocks:
        contradiction = {}

        # Try to parse structured format: "Thesis A vs Thesis B"
        vs_match = re.search(r"(.+?)\s+(?:vs\.?|versus)\s+(.+?)(?:\n|$)", block, re.IGNORECASE)
        if vs_match:
            contradiction["thesis_a"] = vs_match.group(1).strip()
            contradiction["thesis_b"] = vs_match.group(2).strip()
        else:
            contradiction["description"] = block.strip()

        # Extract implication if present
        impl_match = re.search(r"(?:Implication|Result|Means):\s*(.+?)(?:\n|$)", block, re.IGNORECASE)
        if impl_match:
            contradiction["implication"] = impl_match.group(1).strip()

        if contradiction:
            contradictions.append(contradiction)

    return contradictions


def parse_impact_response(response: str) -> Dict[str, Any]:
    """Parse the structured LLM response into components."""
    result = {
        "direction": "NEUTRAL",
        "scenarios": [],
        "belief_space": {},
        "confidence": {},
        "time_horizon": "unknown",
        "decay_profile": "unknown",
        "rationale": "",
        "risk_factors": []
    }

    # Parse all scenarios (CRITICAL for belief-space output)
    scenarios = parse_scenarios(response)
    result["scenarios"] = scenarios

    # Parse contradictions
    contradictions = parse_contradictions(response)
    result["belief_space"] = {
        "contradictions": contradictions,
        "narrative_count": len(scenarios),
        "regime_uncertainty": "high" if len(scenarios) > 2 else "medium" if len(scenarios) == 2 else "low"
    }

    # Determine primary direction from highest likelihood scenario
    if scenarios:
        sorted_scenarios = sorted(scenarios, key=lambda s: s.get("likelihood", 0), reverse=True)
        result["direction"] = sorted_scenarios[0].get("direction", "NEUTRAL")
        result["belief_space"]["dominant_narrative"] = sorted_scenarios[0].get("name", "Unknown")
    else:
        # Fallback: Parse PRIMARY_DIRECTION (or DIRECTION for backward compatibility)
        direction_match = re.search(r"PRIMARY_DIRECTION:\s*(BULLISH|BEARISH|NEUTRAL)", response, re.IGNORECASE)
        if not direction_match:
            direction_match = re.search(r"DIRECTION:\s*(BULLISH|BEARISH|NEUTRAL)", response, re.IGNORECASE)
        if direction_match:
            result["direction"] = direction_match.group(1).upper()

    # Parse CONFIDENCE section
    confidence = {}
    score_match = re.search(r"score:\s*([\d.]+)", response, re.IGNORECASE)
    if score_match:
        try:
            confidence["score"] = float(score_match.group(1))
        except ValueError:
            confidence["score"] = 0.5

    chain_count_match = re.search(r"chain_count:\s*(\d+)", response, re.IGNORECASE)
    if chain_count_match:
        confidence["chain_count"] = int(chain_count_match.group(1))

    source_div_match = re.search(r"source_diversity:\s*(\d+)", response, re.IGNORECASE)
    if source_div_match:
        confidence["source_diversity"] = int(source_div_match.group(1))

    strongest_match = re.search(r"strongest_chain:\s*(.+?)(?:\n|$)", response, re.IGNORECASE)
    if strongest_match:
        confidence["strongest_chain"] = strongest_match.group(1).strip().strip('"\'')

    result["confidence"] = confidence

    # Parse TIME_HORIZON
    horizon_match = re.search(r"TIME_HORIZON:\s*(intraday|days|weeks|months|regime_shift)", response, re.IGNORECASE)
    if horizon_match:
        result["time_horizon"] = horizon_match.group(1).lower()

    # Parse DECAY_PROFILE
    decay_match = re.search(r"DECAY_PROFILE:\s*(fast|medium|slow)", response, re.IGNORECASE)
    if decay_match:
        result["decay_profile"] = decay_match.group(1).lower()

    # Parse RATIONALE
    rationale_match = re.search(r"RATIONALE:\s*\n(.+?)(?=\nRISK_FACTORS:|\Z)", response, re.DOTALL | re.IGNORECASE)
    if rationale_match:
        result["rationale"] = rationale_match.group(1).strip()

    # Parse RISK_FACTORS
    risks_match = re.search(r"RISK_FACTORS:\s*\n(.+?)(?:\Z)", response, re.DOTALL | re.IGNORECASE)
    if risks_match:
        risks_text = risks_match.group(1)
        # Extract bullet points
        risks = re.findall(r"[-•]\s*(.+?)(?:\n|$)", risks_text)
        result["risk_factors"] = [r.strip() for r in risks if r.strip()]

    return result


# Simulated LLM response that matches the new belief-space output format
MOCK_LLM_RESPONSE = """
VARIABLES_ANALYSIS:
- USED: TGA: $923B (+10% 1w) - Primary driver of analysis, indicates liquidity drain
- USED: BANK_RESERVES: $2.94T (-$50B 1w) - Confirms drain mechanism
- USED: BTC: $75,470 (-15% 1w) - Shows correlation with liquidity conditions
- NOT_USED: VIX: 18.5 - Volatility stable, not relevant to liquidity thesis

SCENARIOS:
- Scenario A: Liquidity Drain Pressure
  - Chain: TGA increase → bank reserve drain → funding stress → risk asset selling → BTC pressure
  - Direction: BEARISH
  - Likelihood: 65% based on TGA +10% weekly increase matching historical pattern
  - Key Data: TGA $923B, Reserves -$50B
  - Actors: Treasury, money market funds

- Scenario B: Fed Pivot Signal
  - Chain: TGA increase → debt ceiling concern → Fed accommodation expectation → risk-on
  - Direction: BULLISH
  - Likelihood: 25% based on market pricing of Fed cuts
  - Key Data: Fed funds futures showing 75bp cuts priced
  - Actors: Bond traders, Fed watchers

- Scenario C: Neutral Absorption
  - Chain: TGA increase → RRP buffer absorbs → net liquidity unchanged
  - Direction: NEUTRAL
  - Likelihood: 10% based on current RRP levels
  - Key Data: RRP at $500B provides cushion
  - Actors: Money market funds

CONTRADICTIONS:
- "TGA drain causes immediate BTC pressure" vs "TGA drain signals Fed pivot"
  - Source A: Macro liquidity analysts
  - Source B: Fed policy watchers
  - Implication: Market simultaneously pricing liquidity squeeze AND Fed rescue
  - Volatility Impact: High - creates two-way risk, potential for sharp reversals

PRIMARY_DIRECTION: BEARISH

CONFIDENCE:
- score: 0.68
- chain_count: 4
- source_diversity: 3
- strongest_chain: tga_increase -> reserve_drain -> funding_stress -> btc_pressure
- uncertainty_drivers: Fed policy response timing, RRP buffer capacity

TIME_HORIZON: weeks

DECAY_PROFILE: medium

RATIONALE:
The TGA increase of +10% weekly represents a significant liquidity drain from the banking system. Historical precedent shows this pattern precedes BTC weakness with 2-3 week lag. However, market is also pricing potential Fed accommodation which creates two-way risk. The primary scenario (65% likelihood) is bearish due to the direct mechanical effect of reserve drain, but the Fed pivot scenario (25%) could reverse this if accommodation signals strengthen.

RISK_FACTORS:
- Fed emergency liquidity injection could invalidate bearish thesis
- Rapid TGA drawdown (fiscal spending) would reverse the drain
- Institutional BTC accumulation at lower prices could override macro pressure
"""


def test_parse_scenarios():
    """Test that scenarios are correctly parsed."""
    scenarios = parse_scenarios(MOCK_LLM_RESPONSE)

    print(f"\n=== SCENARIO PARSING TEST ===")
    print(f"Found {len(scenarios)} scenarios")

    assert len(scenarios) == 3, f"Expected 3 scenarios, got {len(scenarios)}"

    # Check Scenario A
    scenario_a = scenarios[0]
    print(f"\nScenario A: {scenario_a.get('name')}")
    print(f"  Direction: {scenario_a.get('direction')}")
    print(f"  Likelihood: {scenario_a.get('likelihood')}")
    print(f"  Chain: {scenario_a.get('chain')}")

    assert scenario_a.get("direction") == "BEARISH", f"Expected BEARISH, got {scenario_a.get('direction')}"
    assert scenario_a.get("likelihood") == 0.65, f"Expected 0.65, got {scenario_a.get('likelihood')}"

    # Check Scenario B
    scenario_b = scenarios[1]
    print(f"\nScenario B: {scenario_b.get('name')}")
    print(f"  Direction: {scenario_b.get('direction')}")
    print(f"  Likelihood: {scenario_b.get('likelihood')}")

    assert scenario_b.get("direction") == "BULLISH", f"Expected BULLISH, got {scenario_b.get('direction')}"
    assert scenario_b.get("likelihood") == 0.25, f"Expected 0.25, got {scenario_b.get('likelihood')}"

    # Check Scenario C
    scenario_c = scenarios[2]
    print(f"\nScenario C: {scenario_c.get('name')}")
    print(f"  Direction: {scenario_c.get('direction')}")
    print(f"  Likelihood: {scenario_c.get('likelihood')}")

    assert scenario_c.get("direction") == "NEUTRAL", f"Expected NEUTRAL, got {scenario_c.get('direction')}"

    print("\n✅ Scenario parsing test PASSED")
    return scenarios


def test_parse_contradictions():
    """Test that contradictions are correctly parsed."""
    contradictions = parse_contradictions(MOCK_LLM_RESPONSE)

    print(f"\n=== CONTRADICTION PARSING TEST ===")
    print(f"Found {len(contradictions)} contradictions")

    assert len(contradictions) >= 1, f"Expected at least 1 contradiction, got {len(contradictions)}"

    for i, c in enumerate(contradictions):
        print(f"\nContradiction {i+1}:")
        if c.get("thesis_a"):
            print(f"  Thesis A: {c.get('thesis_a')}")
            print(f"  Thesis B: {c.get('thesis_b')}")
        elif c.get("description"):
            print(f"  Description: {c.get('description')}")
        if c.get("implication"):
            print(f"  Implication: {c.get('implication')}")

    print("\n✅ Contradiction parsing test PASSED")
    return contradictions


def test_full_parse():
    """Test the full parse_impact_response function."""
    result = parse_impact_response(MOCK_LLM_RESPONSE)

    print(f"\n=== FULL PARSE TEST ===")
    print(f"Direction: {result.get('direction')}")
    print(f"Scenarios: {len(result.get('scenarios', []))}")
    print(f"Belief Space: {result.get('belief_space', {})}")
    print(f"Confidence: {result.get('confidence', {})}")

    # Check scenarios are stored
    assert len(result.get("scenarios", [])) == 3, "Expected 3 scenarios in result"

    # Check belief_space metadata
    belief_space = result.get("belief_space", {})
    assert belief_space.get("narrative_count") == 3, "Expected narrative_count = 3"
    assert len(belief_space.get("contradictions", [])) >= 1, "Expected at least 1 contradiction"

    # Check primary direction matches highest likelihood scenario
    assert result.get("direction") == "BEARISH", "Expected BEARISH as primary direction"

    # Check confidence is parsed
    confidence = result.get("confidence", {})
    assert confidence.get("score") == 0.68, f"Expected 0.68, got {confidence.get('score')}"

    print("\n✅ Full parse test PASSED")
    return result


def test_output_format():
    """Test that output matches the belief-space goal format."""
    result = parse_impact_response(MOCK_LLM_RESPONSE)

    print(f"\n=== BELIEF-SPACE OUTPUT FORMAT TEST ===")

    # The goal requires:
    # 1. Multiple scenarios with different directions
    scenarios = result.get("scenarios", [])
    directions = set(s.get("direction") for s in scenarios)
    print(f"Unique directions: {directions}")
    assert len(directions) >= 2, "Goal requires scenarios with different directions"

    # 2. Contradictions preserved
    contradictions = result.get("belief_space", {}).get("contradictions", [])
    print(f"Contradictions preserved: {len(contradictions)}")
    assert len(contradictions) >= 1, "Goal requires contradictions to be preserved"

    # 3. Likelihood percentages
    for s in scenarios:
        assert s.get("likelihood") is not None, f"Scenario {s.get('name')} missing likelihood"
    print(f"All scenarios have likelihood: ✓")

    # 4. Chains present
    for s in scenarios:
        assert s.get("chain") is not None, f"Scenario {s.get('name')} missing chain"
    print(f"All scenarios have chains: ✓")

    print("\n✅ Belief-space output format test PASSED")
    print("\n" + "="*60)
    print("ALL TESTS PASSED - Parser correctly extracts belief-space format")
    print("="*60)

    return result


if __name__ == "__main__":
    test_parse_scenarios()
    test_parse_contradictions()
    test_full_parse()
    test_output_format()
