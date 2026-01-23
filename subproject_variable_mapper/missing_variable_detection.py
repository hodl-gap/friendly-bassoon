"""
Missing Variable Detection Module

Parses logic chains to identify variables that are required
but weren't explicitly extracted.
This is Step 3 of the 4-step process.

Optimization: When BATCH_CHAIN_PARSING=True, all chains are parsed in a single
LLM call instead of one call per chain.

Note: This step is SKIPPED when USE_COMBINED_EXTRACTION=True because
Step 1 already extracts implicit variables from chains.
"""

import sys
import re
import json
from pathlib import Path

# Add parent directory for models import
sys.path.append(str(Path(__file__).parent.parent))

from models import call_claude_haiku
from states import VariableMapperState
from missing_variable_detection_prompts import CHAIN_PARSING_PROMPT
from variable_extraction_prompts import BATCH_CHAIN_PARSING_PROMPT
from config import BATCH_CHAIN_PARSING


def extract_chains_from_text(text: str) -> list:
    """Extract logic chains from synthesis text."""
    chains = []

    # Pattern 1: **CHAIN:** format
    pattern1 = r'\*\*CHAIN:\*\*\s*(.+?)(?=\*\*|$|\n\n)'
    matches1 = re.findall(pattern1, text, re.DOTALL | re.IGNORECASE)
    for match in matches1:
        chain = match.strip().split('\n')[0].strip()
        if chain and '→' in chain:
            chains.append(chain)

    # Pattern 2: Supporting paths format (- Path N: ...)
    pattern2 = r'- Path \d+:\s*(.+?)(?=\n|$)'
    matches2 = re.findall(pattern2, text, re.IGNORECASE)
    for match in matches2:
        chain = match.strip()
        if chain and '→' in chain:
            chains.append(chain)

    # Deduplicate
    chains = list(dict.fromkeys(chains))

    print(f"[missing_detection] Extracted {len(chains)} chains from text")
    return chains


def parse_chain_with_llm(chain: str) -> dict:
    """Use LLM to parse a chain into variables and relationships."""
    prompt = CHAIN_PARSING_PROMPT.format(chain=chain)
    messages = [{"role": "user", "content": prompt}]

    try:
        response = call_claude_haiku(messages, temperature=0.2, max_tokens=1000)
        print(f"[missing_detection] LLM response for chain:\n{response}")

        # Parse JSON response
        clean_response = response.strip()
        if clean_response.startswith("```"):
            lines = clean_response.split("\n")
            clean_response = "\n".join(lines[1:-1])

        result = json.loads(clean_response)
        return result

    except Exception as e:
        print(f"[missing_detection] Chain parsing failed: {e}")
        return {"chain": chain, "variables": [], "steps": []}


def detect_missing_variables(state: VariableMapperState) -> VariableMapperState:
    """
    Parse logic chains to find variables that weren't explicitly extracted.

    Input (from State):
        - synthesis_input: str (original text)
        - normalized_variables: List[Dict] from Step 2

    Output (to State):
        - missing_variables: List[str] - variables in chains but not extracted
        - chain_dependencies: List[Dict] - dependency graph

    Note: This step is SKIPPED when USE_COMBINED_EXTRACTION=True.
    """
    synthesis_text = state.get("synthesis_input", "")
    normalized_variables = state.get("normalized_variables", [])

    if not synthesis_text:
        print("[missing_detection] No synthesis text provided")
        return {
            **state,
            "missing_variables": [],
            "chain_dependencies": []
        }

    # Build set of already-extracted variables (both raw and normalized names)
    extracted_names = set()
    for var in normalized_variables:
        raw = var.get("raw_name", "")
        normalized = var.get("normalized_name", "")
        if raw:
            extracted_names.add(raw.lower())
        if normalized:
            extracted_names.add(normalized.lower())

    print(f"[missing_detection] Already extracted {len(extracted_names)} variable names")

    # Extract chains from text
    chains = extract_chains_from_text(synthesis_text)

    if not chains:
        print("[missing_detection] No chains found in text")
        return {
            **state,
            "missing_variables": [],
            "chain_dependencies": []
        }

    # Parse chains - use batch or individual parsing
    if BATCH_CHAIN_PARSING and len(chains) > 1:
        print(f"[missing_detection] Using BATCH parsing for {len(chains)} chains")
        chain_dependencies, all_chain_variables = parse_chains_batch(chains)
    else:
        print(f"[missing_detection] Using individual parsing for {len(chains)} chains")
        chain_dependencies = []
        all_chain_variables = set()

        for chain in chains:
            parsed = parse_chain_with_llm(chain)
            chain_dependencies.append(parsed)

            # Collect all variables mentioned in chains
            for var in parsed.get("variables", []):
                if isinstance(var, dict):
                    var_name = var.get("name", "")
                else:
                    var_name = var
                if var_name:
                    all_chain_variables.add(var_name.lower())

    print(f"[missing_detection] Found {len(all_chain_variables)} unique variables in chains")

    # Find missing variables (in chains but not in extracted)
    missing_variables = []
    for chain_var in all_chain_variables:
        if chain_var not in extracted_names:
            # Check if it's not a close match to any extracted name
            is_close_match = False
            for extracted in extracted_names:
                if chain_var in extracted or extracted in chain_var:
                    is_close_match = True
                    break

            if not is_close_match:
                missing_variables.append(chain_var)

    # Deduplicate and sort
    missing_variables = sorted(list(set(missing_variables)))

    print(f"[missing_detection] Identified {len(missing_variables)} missing variables")
    print(f"[missing_detection] Missing: {missing_variables[:10]}...")  # Print first 10

    return {
        **state,
        "missing_variables": missing_variables,
        "chain_dependencies": chain_dependencies
    }


def parse_chains_batch(chains: list) -> tuple:
    """
    Parse multiple chains in a single LLM call (batch parsing).

    Returns:
        tuple: (chain_dependencies, all_chain_variables)
    """
    # Format chains for batch prompt
    chains_text = "\n".join([f"{i+1}. {chain}" for i, chain in enumerate(chains)])

    prompt = BATCH_CHAIN_PARSING_PROMPT.format(chains=chains_text)
    messages = [{"role": "user", "content": prompt}]

    try:
        response = call_claude_haiku(messages, temperature=0.2, max_tokens=3000)
        print(f"[missing_detection] Batch parsing LLM response:\n{response}")

        # Parse JSON response
        clean_response = response.strip()
        if clean_response.startswith("```"):
            lines = clean_response.split("\n")
            end_idx = len(lines) - 1
            for i, line in enumerate(lines[1:], 1):
                if line.strip() == "```":
                    end_idx = i
                    break
            clean_response = "\n".join(lines[1:end_idx])

        result = json.loads(clean_response)

        chain_dependencies = result.get("parsed_chains", [])
        all_vars_list = result.get("all_variables", [])
        all_chain_variables = set(v.lower() for v in all_vars_list)

        # Also extract variables from parsed_chains if all_variables is incomplete
        for parsed in chain_dependencies:
            for var in parsed.get("variables", []):
                if isinstance(var, dict):
                    var_name = var.get("name", "")
                else:
                    var_name = var
                if var_name:
                    all_chain_variables.add(var_name.lower())

        return chain_dependencies, all_chain_variables

    except Exception as e:
        print(f"[missing_detection] Batch parsing failed: {e}, falling back to individual parsing")
        # Fallback to individual parsing
        chain_dependencies = []
        all_chain_variables = set()

        for chain in chains:
            parsed = parse_chain_with_llm(chain)
            chain_dependencies.append(parsed)

            for var in parsed.get("variables", []):
                if isinstance(var, dict):
                    var_name = var.get("name", "")
                else:
                    var_name = var
                if var_name:
                    all_chain_variables.add(var_name.lower())

        return chain_dependencies, all_chain_variables


# For standalone testing
if __name__ == "__main__":
    # Test with sample synthesis text
    sample_text = """
    **CHAIN:** Fed rate cuts → short rates down → curve steepening → flows to duration/credit/alternatives
    **MECHANISM:** easing lowers short-term rates → long rates remain sticky creating steeper curve

    **CHAIN:** QT reduction + TGA drawdown + Fed cuts → December liquidity surge → year-end risk-on rally
    **MECHANISM:** multiple liquidity sources converge → increases system reserves

    SUPPORTING PATHS:
    - Path 1: Fed rate cuts → lower yields → higher equity valuations
    - Path 2: TGA drawdown → liquidity pressure → FCI tightens → risk-off
    """

    test_state = VariableMapperState(
        synthesis_input=sample_text,
        normalized_variables=[
            {"raw_name": "TGA", "normalized_name": "tga"},
            {"raw_name": "Fed funds rate", "normalized_name": "fed_funds_rate"},
        ]
    )

    result = detect_missing_variables(test_state)

    print("\n" + "=" * 50)
    print("MISSING VARIABLES:")
    print("=" * 50)
    for var in result.get("missing_variables", []):
        print(f"  - {var}")

    print("\n" + "=" * 50)
    print("CHAIN DEPENDENCIES:")
    print("=" * 50)
    for dep in result.get("chain_dependencies", []):
        print(f"\n  Chain: {dep.get('chain', '')[:60]}...")
        print(f"  Variables: {dep.get('variables', [])}")
