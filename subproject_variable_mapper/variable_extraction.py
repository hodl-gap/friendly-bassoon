"""
Variable Extraction Module

Extracts measurable financial variables from synthesis text.
This is Step 1 of the 4-step process.
"""

import sys
import json
from pathlib import Path

# Add parent directory for models import
sys.path.append(str(Path(__file__).parent.parent))

from models import call_gpt5_mini, call_claude_sonnet
from states import VariableMapperState
from variable_extraction_prompts import VARIABLE_EXTRACTION_PROMPT
from config import EXTRACTION_MODEL, FALLBACK_MODEL


def extract_variables(state: VariableMapperState) -> VariableMapperState:
    """
    Extract variables from synthesis text.

    Input: synthesis_input (raw text from database_retriever)
    Output: extracted_variables (list of variable dicts)
    """
    synthesis_text = state.get("synthesis_input", "")

    if not synthesis_text:
        print("[variable_extraction] No input text provided")
        return {**state, "extracted_variables": []}

    print(f"[variable_extraction] Processing {len(synthesis_text)} chars...")

    # Build prompt
    prompt = VARIABLE_EXTRACTION_PROMPT.format(synthesis_text=synthesis_text)
    messages = [{"role": "user", "content": prompt}]

    # Call LLM
    try:
        if EXTRACTION_MODEL == "gpt5_mini":
            response = call_gpt5_mini(messages, temperature=0.2, max_tokens=4000)
        else:
            response = call_claude_sonnet(messages, temperature=0.2, max_tokens=4000)
    except Exception as e:
        print(f"[variable_extraction] Primary model failed: {e}")
        print(f"[variable_extraction] Trying fallback model...")
        response = call_claude_sonnet(messages, temperature=0.2, max_tokens=4000)

    # Print full LLM response (as per CLAUDE.md guidelines)
    print(f"[variable_extraction] Full LLM response:\n{response}")

    # Parse JSON response
    extracted_variables = parse_extraction_response(response)

    print(f"[variable_extraction] Extracted {len(extracted_variables)} variables")

    return {**state, "extracted_variables": extracted_variables}


def parse_extraction_response(response: str) -> list:
    """Parse the LLM response to extract variables list."""
    try:
        # Try to parse as JSON directly
        # Handle case where response might have markdown code blocks
        clean_response = response.strip()
        if clean_response.startswith("```"):
            # Remove markdown code blocks
            lines = clean_response.split("\n")
            clean_response = "\n".join(lines[1:-1])

        data = json.loads(clean_response)
        return data.get("variables", [])

    except json.JSONDecodeError as e:
        print(f"[variable_extraction] JSON parse error: {e}")
        print(f"[variable_extraction] Raw response: {response[:500]}...")
        return []


# For standalone testing
if __name__ == "__main__":
    from config import SAMPLE_INPUT_FILE

    print(f"[test] Loading sample from: {SAMPLE_INPUT_FILE}")

    with open(SAMPLE_INPUT_FILE, "r", encoding="utf-8") as f:
        sample_text = f.read()

    # Create test state
    test_state = VariableMapperState(synthesis_input=sample_text)

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
