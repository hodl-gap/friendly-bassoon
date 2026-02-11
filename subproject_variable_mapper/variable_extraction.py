"""
Variable Extraction Module

Extracts measurable financial variables from synthesis text.
This is Step 1 of the 4-step process.

Optimization: When USE_COMBINED_EXTRACTION=True, this step extracts BOTH
explicit variables AND implicit chain variables, eliminating the need for Step 3.
"""

import sys
import json
from pathlib import Path

# Add parent directory for models import
sys.path.append(str(Path(__file__).parent.parent))

from models import call_claude_sonnet, call_claude_haiku
from states import VariableMapperState
from variable_extraction_prompts import VARIABLE_EXTRACTION_PROMPT, COMBINED_EXTRACTION_PROMPT
from config import EXTRACTION_MODEL, FALLBACK_MODEL, USE_COMBINED_EXTRACTION


def extract_variables(state: VariableMapperState) -> VariableMapperState:
    """
    Extract variables from synthesis text.

    Input: synthesis (raw text from database_retriever)
           logic_chains (optional): structured chains for efficient extraction
    Output: extracted_variables (list of variable dicts)

    If USE_COMBINED_EXTRACTION=True, also outputs:
        - implicit_variables: variables found in logic chains
        - chain_dependencies: parsed chain relationships
        - skip_step3: flag to skip missing_variable_detection

    If logic_chains are provided, extracts from structure first (no LLM needed),
    then supplements with LLM extraction for variables not in structure.
    """
    synthesis_text = state.get("synthesis", "")
    logic_chains = state.get("logic_chains", [])

    if not synthesis_text and not logic_chains:
        print("[variable_extraction] No input text or chains provided")
        return {**state, "extracted_variables": [], "skip_step3": False}

    # Step 1: Extract from structured logic_chains first (if available)
    structure_vars = []
    if logic_chains:
        print(f"[variable_extraction] Extracting from {len(logic_chains)} logic chains...")
        structure_vars = extract_from_structure(logic_chains)
        print(f"[variable_extraction] Found {len(structure_vars)} variables from structure")

    # If we got enough from structure, we may skip LLM extraction
    if structure_vars and len(structure_vars) >= 5:
        print("[variable_extraction] Sufficient variables from structure, skipping LLM extraction")
        return {
            **state,
            "extracted_variables": structure_vars,
            "implicit_variables": structure_vars,
            "chain_dependencies": _extract_chain_deps(logic_chains),
            "skip_step3": True  # Structure already has chain variables
        }

    # Step 2: LLM extraction for additional variables
    print(f"[variable_extraction] Processing {len(synthesis_text)} chars with LLM...")

    if USE_COMBINED_EXTRACTION:
        llm_result = extract_variables_combined(state, synthesis_text)
    else:
        llm_result = extract_variables_simple(state, synthesis_text)

    # Step 3: Merge structure vars with LLM vars (structure vars already normalized)
    llm_vars = llm_result.get("extracted_variables", [])
    all_variables = _merge_variables(structure_vars, llm_vars)

    print(f"[variable_extraction] Total: {len(all_variables)} variables ({len(structure_vars)} from structure + {len(all_variables) - len(structure_vars)} from LLM)")

    return {
        **llm_result,
        "extracted_variables": all_variables,
    }


def extract_from_structure(logic_chains: list) -> list:
    """
    Extract variables from structured logic_chains.

    Iterates through chain.steps[].cause_normalized and effect_normalized
    to extract variables that are already in normalized form.

    Args:
        logic_chains: List of logic chain dicts with steps

    Returns:
        List of variable dicts with:
        - name: normalized variable name
        - raw_name: original text (cause or effect field)
        - already_normalized: True (skip normalization step)
        - source_type: "structure"
    """
    variables = []
    seen = set()

    for chain in (logic_chains or []):
        # Handle both formats: {steps: [...]} or {logic_chain: {steps: [...]}}
        steps = chain.get("steps", [])
        if not steps:
            steps = chain.get("logic_chain", {}).get("steps", [])

        for step in steps:
            cause_norm = step.get("cause_normalized", "")
            effect_norm = step.get("effect_normalized", "")
            cause_raw = step.get("cause", "")
            effect_raw = step.get("effect", "")

            if cause_norm and cause_norm not in seen:
                variables.append({
                    "name": cause_norm,
                    "raw_name": cause_raw or cause_norm,
                    "already_normalized": True,
                    "source_type": "structure"
                })
                seen.add(cause_norm)

            if effect_norm and effect_norm not in seen:
                variables.append({
                    "name": effect_norm,
                    "raw_name": effect_raw or effect_norm,
                    "already_normalized": True,
                    "source_type": "structure"
                })
                seen.add(effect_norm)

    return variables


def _extract_chain_deps(logic_chains: list) -> list:
    """Extract chain dependencies from logic_chains structure."""
    dependencies = []
    for chain in (logic_chains or []):
        steps = chain.get("steps", [])
        if not steps:
            steps = chain.get("logic_chain", {}).get("steps", [])

        for step in steps:
            cause_norm = step.get("cause_normalized", "")
            effect_norm = step.get("effect_normalized", "")
            if cause_norm and effect_norm:
                dependencies.append({
                    "from": cause_norm,
                    "to": effect_norm,
                    "relationship": "causes"
                })

    return dependencies


def _merge_variables(structure_vars: list, llm_vars: list) -> list:
    """Merge structure variables with LLM variables, avoiding duplicates."""
    # Structure vars take precedence (already normalized)
    seen_names = {v.get("name", "").lower() for v in structure_vars}
    merged = list(structure_vars)

    for var in llm_vars:
        var_name = var.get("name", "").lower()
        if var_name and var_name not in seen_names:
            merged.append(var)
            seen_names.add(var_name)

    return merged


def extract_variables_simple(state: VariableMapperState, synthesis_text: str) -> VariableMapperState:
    """Original simple extraction (explicit variables only)."""
    prompt = VARIABLE_EXTRACTION_PROMPT.format(synthesis_text=synthesis_text)
    messages = [{"role": "user", "content": prompt}]

    response = call_extraction_model(messages)

    print(f"[variable_extraction] Full LLM response:\n{response}")

    extracted_variables = parse_extraction_response(response)
    print(f"[variable_extraction] Extracted {len(extracted_variables)} variables")

    return {**state, "extracted_variables": extracted_variables, "skip_step3": False}


def extract_variables_combined(state: VariableMapperState, synthesis_text: str) -> VariableMapperState:
    """
    Combined extraction: extracts BOTH explicit AND implicit variables in single call.
    Eliminates need for Step 3 (missing_variable_detection).
    """
    print("[variable_extraction] Using COMBINED extraction (explicit + implicit)")

    prompt = COMBINED_EXTRACTION_PROMPT.format(synthesis_text=synthesis_text)
    messages = [{"role": "user", "content": prompt}]

    response = call_extraction_model(messages)

    print(f"[variable_extraction] Full LLM response:\n{response}")

    # Parse combined response
    result = parse_combined_response(response)

    explicit_vars = result.get("explicit_variables", [])
    implicit_vars = result.get("implicit_variables", [])
    chain_deps = result.get("chain_dependencies", [])

    # Merge explicit and implicit into extracted_variables
    # Mark source_type for tracking
    all_variables = explicit_vars.copy()

    # Add implicit variables that aren't already in explicit
    explicit_names = {v.get("name", "").lower() for v in explicit_vars}
    for implicit_var in implicit_vars:
        name = implicit_var.get("name", "").lower()
        if name and name not in explicit_names:
            all_variables.append(implicit_var)
            explicit_names.add(name)

    print(f"[variable_extraction] Extracted {len(explicit_vars)} explicit + {len(implicit_vars)} implicit = {len(all_variables)} total")
    print(f"[variable_extraction] Parsed {len(chain_deps)} chain dependencies")

    return {
        **state,
        "extracted_variables": all_variables,
        "implicit_variables": implicit_vars,
        "chain_dependencies": chain_deps,
        "skip_step3": True  # Signal orchestrator to skip Step 3
    }


def call_extraction_model(messages: list) -> str:
    """Call the configured extraction model with fallback."""
    try:
        if EXTRACTION_MODEL == "claude_sonnet":
            return call_claude_sonnet(messages, temperature=0.2, max_tokens=4000)
        else:
            return call_claude_haiku(messages, temperature=0.2, max_tokens=4000)
    except Exception as e:
        print(f"[variable_extraction] Primary model failed: {e}")
        print(f"[variable_extraction] Trying fallback model...")
        if FALLBACK_MODEL == "claude_sonnet":
            return call_claude_sonnet(messages, temperature=0.2, max_tokens=4000)
        else:
            return call_claude_haiku(messages, temperature=0.2, max_tokens=4000)


def parse_extraction_response(response: str) -> list:
    """Parse the LLM response to extract variables list (simple format)."""
    try:
        clean_response = clean_json_response(response)
        data = json.loads(clean_response)
        return data.get("variables", [])

    except json.JSONDecodeError as e:
        print(f"[variable_extraction] JSON parse error: {e}")
        print(f"[variable_extraction] Raw response: {response[:500]}...")
        return []


def parse_combined_response(response: str) -> dict:
    """Parse the LLM response from combined extraction (explicit + implicit)."""
    try:
        clean_response = clean_json_response(response)
        data = json.loads(clean_response)
        return {
            "explicit_variables": data.get("explicit_variables", []),
            "implicit_variables": data.get("implicit_variables", []),
            "chain_dependencies": data.get("chain_dependencies", [])
        }

    except json.JSONDecodeError as e:
        print(f"[variable_extraction] JSON parse error: {e}")
        print(f"[variable_extraction] Raw response: {response[:500]}...")
        return {"explicit_variables": [], "implicit_variables": [], "chain_dependencies": []}


def clean_json_response(response: str) -> str:
    """Clean LLM response to extract JSON (handles markdown code blocks)."""
    clean_response = response.strip()

    # Handle markdown code blocks
    if clean_response.startswith("```"):
        lines = clean_response.split("\n")
        # Find the closing ```
        end_idx = len(lines) - 1
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == "```":
                end_idx = i
                break
        clean_response = "\n".join(lines[1:end_idx])

    return clean_response


# For standalone testing
if __name__ == "__main__":
    from config import SAMPLE_INPUT_FILE

    print(f"[test] Loading sample from: {SAMPLE_INPUT_FILE}")

    with open(SAMPLE_INPUT_FILE, "r", encoding="utf-8") as f:
        sample_text = f.read()

    # Create test state
    test_state = VariableMapperState(synthesis=sample_text)

    # Run extraction
    result = extract_variables(test_state)

    print("\n" + "=" * 50)
    print("EXTRACTED VARIABLES:")
    print("=" * 50)

    for var in result.get("extracted_variables", []):
        print(f"\n  Name: {var.get('name')}")
        if var.get('threshold'):
            print(f"  Threshold: {var.get('threshold')} {var.get('threshold_unit', '')}")
        print(f"  Context: {var.get('context', 'N/A')}")
