"""
Claim Parsing Module

Parses testable quantitative claims from retriever synthesis.
Extracts variables, relationship types, and parameters.
"""

import json
import re
from typing import Dict, Any, List, Optional
from pathlib import Path

import sys
sys.path.append(str(Path(__file__).parent.parent))
from models import call_claude_haiku, call_claude_sonnet

from states import DataCollectionState
from config import CLAIM_PARSING_MODEL, FALLBACK_MODEL
from claim_parsing_prompts import CLAIM_EXTRACTION_PROMPT, CLAIM_REFINEMENT_PROMPT


def parse_claims(state: DataCollectionState) -> DataCollectionState:
    """
    Parse testable claims from retriever synthesis.

    LangGraph node function.

    Args:
        state: Current workflow state with retriever_synthesis

    Returns:
        Updated state with parsed_claims
    """
    synthesis = state.get("retriever_synthesis", "")
    claims_input = state.get("claims_input", [])

    # If pre-parsed claims provided, use those
    if claims_input:
        print(f"[claim_parsing] Using {len(claims_input)} pre-parsed claims")
        state["parsed_claims"] = claims_input
        return state

    if not synthesis:
        print("[claim_parsing] No synthesis text provided")
        state["parsed_claims"] = []
        state["errors"] = state.get("errors", []) + ["No synthesis text provided"]
        return state

    print(f"[claim_parsing] Parsing claims from {len(synthesis)} chars of synthesis")

    # Extract claims using LLM
    claims = extract_claims(synthesis)

    if not claims:
        print("[claim_parsing] No testable claims found")
        state["parsed_claims"] = []
        state["warnings"] = state.get("warnings", []) + ["No testable claims found in synthesis"]
        return state

    print(f"[claim_parsing] Extracted {len(claims)} testable claims")
    state["parsed_claims"] = claims

    return state


def extract_claims(synthesis_text: str) -> List[Dict[str, Any]]:
    """
    Extract testable claims from synthesis text using LLM.

    Args:
        synthesis_text: Raw synthesis text from retriever

    Returns:
        List of parsed claim dictionaries
    """
    prompt = CLAIM_EXTRACTION_PROMPT.format(synthesis_text=synthesis_text)

    messages = [{"role": "user", "content": prompt}]

    # Call LLM
    response = call_model(messages)

    if not response:
        print("[claim_parsing] LLM returned empty response")
        return []

    # Print full response for debugging
    print(f"[claim_parsing] Full LLM response:\n{response}")

    # Parse JSON from response
    claims_data = parse_json_response(response)

    if not claims_data:
        print("[claim_parsing] Failed to parse LLM response as JSON")
        return []

    claims = claims_data.get("claims", [])

    # Validate and clean claims
    validated_claims = []
    for claim in claims:
        if validate_claim(claim):
            validated_claims.append(clean_claim(claim))

    return validated_claims


def validate_claim(claim: Dict[str, Any]) -> bool:
    """
    Validate a parsed claim has required fields.

    Args:
        claim: Parsed claim dictionary

    Returns:
        True if claim is valid
    """
    required_fields = ["claim_text", "variable_a", "relationship_type"]

    for field in required_fields:
        if not claim.get(field):
            print(f"[claim_parsing] Claim missing required field: {field}")
            return False

    # Check testability score
    score = claim.get("testability_score", 0)
    if score < 0.3:
        print(f"[claim_parsing] Claim has low testability score: {score}")
        return False

    return True


def clean_claim(claim: Dict[str, Any]) -> Dict[str, Any]:
    """
    Clean and normalize a parsed claim.

    Args:
        claim: Raw parsed claim

    Returns:
        Cleaned claim dictionary
    """
    # Normalize variable names
    var_a = normalize_variable_name(claim.get("variable_a", ""))
    var_b = normalize_variable_name(claim.get("variable_b", ""))

    # Ensure parameters exist
    parameters = claim.get("parameters", {})
    if not parameters:
        parameters = {}

    # Extract lag range if present
    lag_range = parameters.get("lag_range")
    if lag_range:
        # Ensure numeric values
        lag_range["min"] = int(lag_range.get("min", 0))
        lag_range["max"] = int(lag_range.get("max", 0))

    return {
        "claim_text": claim.get("claim_text", ""),
        "variable_a": var_a,
        "variable_b": var_b if var_b else None,
        "relationship_type": claim.get("relationship_type", "correlation"),
        "direction": claim.get("direction", "positive"),
        "parameters": parameters,
        "testability_score": float(claim.get("testability_score", 0.5)),
        "testability_reason": claim.get("testability_reason", "")
    }


def normalize_variable_name(name: str) -> str:
    """
    Normalize variable name to snake_case.

    Args:
        name: Raw variable name

    Returns:
        Normalized name
    """
    if not name:
        return ""

    # Convert to lowercase
    name = name.lower().strip()

    # Replace common separators with underscore
    name = re.sub(r'[\s\-]+', '_', name)

    # Remove non-alphanumeric except underscore
    name = re.sub(r'[^a-z0-9_]', '', name)

    # Common mappings
    mappings = {
        "bitcoin": "btc",
        "ethereum": "eth",
        "treasury_general_account": "tga",
        "reverse_repo": "rrp",
        "federal_funds": "fed_funds",
        "sp500": "sp500",
        "s_p_500": "sp500",
        "dollar_index": "dxy",
    }

    return mappings.get(name, name)


def call_model(messages: List[Dict[str, str]]) -> Optional[str]:
    """
    Call the configured LLM with fallback.

    Args:
        messages: Message list for LLM

    Returns:
        Response text or None
    """
    try:
        if CLAIM_PARSING_MODEL == "claude_sonnet":
            return call_claude_sonnet(messages, temperature=0.2, max_tokens=4000)
        else:
            return call_claude_haiku(messages, temperature=0.2, max_tokens=4000)
    except Exception as e:
        print(f"[claim_parsing] Primary model failed: {e}")
        print(f"[claim_parsing] Trying fallback model...")
        try:
            if FALLBACK_MODEL == "claude_sonnet":
                return call_claude_sonnet(messages, temperature=0.2, max_tokens=4000)
            else:
                return call_claude_haiku(messages, temperature=0.2, max_tokens=4000)
        except Exception as e2:
            print(f"[claim_parsing] Fallback model also failed: {e2}")
            return None


def parse_json_response(response: str) -> Optional[Dict]:
    """
    Parse JSON from LLM response (handles markdown code blocks).

    Args:
        response: Raw LLM response

    Returns:
        Parsed JSON dict or None
    """
    if not response:
        return None

    text = response.strip()

    # Handle markdown code blocks
    if text.startswith("```"):
        lines = text.split("\n")
        # Find end of code block
        end_idx = len(lines) - 1
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == "```":
                end_idx = i
                break
        text = "\n".join(lines[1:end_idx])

    # Try to parse JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(f"[claim_parsing] JSON parse error: {e}")
        # Try to find JSON object in text
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return None


# Testing entry point
if __name__ == "__main__":
    sample_synthesis = """
    ## Consensus Conclusions

    1. **BTC-Gold Correlation**: BTC follows gold with a lag of 63-428 days,
       with the correlation weakening over recent years.

    2. **Liquidity Impact**: TGA drawdown leads to liquidity expansion,
       typically when TGA falls below $500B threshold.

    3. **Fed Policy Response**: When VIX spikes above 30, Fed typically
       responds within 2-3 weeks.

    4. **Dollar Weakness**: DXY has been trending down, currently -10% YTD.
    """

    from states import DataCollectionState

    state = DataCollectionState(
        mode="claim_validation",
        retriever_synthesis=sample_synthesis
    )

    result = parse_claims(state)
    print("\n" + "=" * 50)
    print("Parsed Claims:")
    for claim in result.get("parsed_claims", []):
        print(f"  - {claim['claim_text'][:60]}...")
        print(f"    Variables: {claim['variable_a']} vs {claim['variable_b']}")
        print(f"    Type: {claim['relationship_type']}")
