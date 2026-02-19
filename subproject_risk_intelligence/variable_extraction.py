"""
Variable Extraction Module

Extracts normalized variables from retrieved logic chains and synthesis.
"""

import re
from typing import List, Dict, Any, Set

import anthropic

from .states import RiskImpactState
from .asset_configs import get_asset_config
from . import config


# Common variable patterns to extract from text
VARIABLE_PATTERNS = {
    # Liquidity metrics
    "tga": ["tga", "treasury general account", "tga balance", "tga drawdown"],
    "bank_reserves": ["bank reserves", "reserves", "reserve balances"],
    "fed_balance_sheet": ["fed balance sheet", "fed assets", "fed total assets", "walcl"],
    "rrp": ["rrp", "reverse repo", "overnight reverse repo"],

    # Rates
    "sofr": ["sofr", "secured overnight"],
    "fed_funds": ["fed funds", "federal funds rate", "ffr"],
    "us10y": ["10y", "10-year", "dgs10", "10y yield", "10y treasury"],
    "us02y": ["2y", "2-year", "dgs2", "2y yield", "2y treasury"],

    # Crypto
    "btc": ["btc", "bitcoin", "btc price", "bitcoin price"],
    "eth": ["eth", "ethereum"],

    # Indices & FX
    "dxy": ["dxy", "dollar index", "usd index"],
    "vix": ["vix", "volatility index"],
    "sp500": ["s&p", "sp500", "s&p 500", "spx"],
    "gold": ["gold", "gold price", "xau"],

    # Macro
    "cpi": ["cpi", "inflation"],
    "gdp": ["gdp", "growth"],

    # Japan specific
    "usdjpy": ["usdjpy", "usd/jpy", "dollar yen"],
    "boj_rate": ["boj rate", "boj policy rate", "japan rate"],
}


def identify_analysis_variables(query: str) -> set:
    """
    Identify analysis-frame variables from the query alone (before retrieval).

    Single Haiku call that identifies variables MECHANICALLY implied by the query,
    even if no retrieved chunk mentions them explicitly.
    E.g., "carry trade unwind" → {usdjpy, boj_rate, vix}

    Returns set of normalized variable names, or empty set on failure.
    """
    from .variable_extraction_prompts import ANALYSIS_FRAME_PROMPT

    # Build known variable vocabulary
    known_vars = list(VARIABLE_PATTERNS.keys())
    from shared.variable_resolver import YAHOO_FALLBACK
    known_vars.extend(YAHOO_FALLBACK.keys())
    known_vars = sorted(set(known_vars))

    prompt = ANALYSIS_FRAME_PROMPT.format(
        query=query,
        known_variables=", ".join(known_vars)
    )

    try:
        client = anthropic.Anthropic()

        analysis_frame_tool = {
            "name": "identify_variables",
            "description": "Return the key variables implied by this query.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "variables": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Normalized variable names from the known vocabulary (3-8 max)"
                    }
                },
                "required": ["variables"]
            }
        }

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            temperature=0.0,
            tools=[analysis_frame_tool],
            tool_choice={"type": "tool", "name": "identify_variables"},
            messages=[{"role": "user", "content": prompt}]
        )

        # Log token usage
        try:
            from shared.run_logger import log_llm_call
            log_llm_call("claude-haiku-4-5-20251001", response.usage.input_tokens, response.usage.output_tokens)
        except Exception:
            pass

        for block in response.content:
            if block.type == "tool_use" and block.name == "identify_variables":
                variables = set(v.lower().strip() for v in block.input.get("variables", []))
                print(f"[Variable Extraction] Query-frame identified {len(variables)} variables: {sorted(variables)}")
                return variables

        return set()

    except Exception as e:
        print(f"[Variable Extraction] Query-frame extraction failed: {e}")
        return set()


def extract_variables_llm(state) -> set:
    """
    Extract variables using LLM inference (single Haiku call).

    Identifies both explicitly named and logically implied variables.
    Falls back to keyword extraction on failure.
    """
    from .variable_extraction_prompts import VARIABLE_INFERENCE_PROMPT

    query = state.get("query", "")
    synthesis = state.get("synthesis", "")[:1500]

    # Build chain text (truncated)
    chains_text = ""
    for chain in state.get("logic_chains", [])[:5]:
        if chain.get("chain_text"):
            chains_text += chain["chain_text"] + "\n"
        elif chain.get("steps"):
            steps = chain.get("steps", [])
            parts = []
            for s in steps:
                parts.append(f"{s.get('cause', '?')} -> {s.get('effect', '?')}")
            chains_text += " -> ".join(parts) + "\n"

    # Build known variable vocabulary
    known_vars = list(VARIABLE_PATTERNS.keys())
    from shared.variable_resolver import YAHOO_FALLBACK
    known_vars.extend(YAHOO_FALLBACK.keys())
    known_vars = sorted(set(known_vars))

    prompt = VARIABLE_INFERENCE_PROMPT.format(
        query=query,
        synthesis=synthesis,
        chains=chains_text[:1500],
        known_variables=", ".join(known_vars)
    )

    try:
        client = anthropic.Anthropic()

        variable_extraction_tool = {
            "name": "extract_variables",
            "description": "Return the list of variables relevant to this macro analysis.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "variables": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Normalized variable names from the known vocabulary"
                    },
                    "suggested_new": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "New variable names not in known vocabulary (snake_case)"
                    }
                },
                "required": ["variables"]
            }
        }

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            temperature=0.0,
            tools=[variable_extraction_tool],
            tool_choice={"type": "tool", "name": "extract_variables"},
            messages=[{"role": "user", "content": prompt}]
        )

        # Log token usage
        try:
            from shared.run_logger import log_llm_call
            log_llm_call("claude-haiku-4-5-20251001", response.usage.input_tokens, response.usage.output_tokens)
        except Exception:
            pass

        # Extract tool_use result
        result = None
        for block in response.content:
            if block.type == "tool_use" and block.name == "extract_variables":
                result = block.input
                break

        if result:
            variables = set(v.lower().strip() for v in result.get("variables", []))
            suggested = result.get("suggested_new", [])
            if suggested:
                print(f"[Variable Extraction] LLM suggested new variables: {suggested}")
                state["suggested_new_variables"] = suggested
            print(f"[Variable Extraction] LLM extracted {len(variables)} variables")
            return variables

        print("[Variable Extraction] LLM returned no tool_use block, falling back to keyword extraction")
        return None

    except Exception as e:
        print(f"[Variable Extraction] LLM extraction failed: {e}, falling back to keyword extraction")
        return None


def extract_variables(state: RiskImpactState) -> RiskImpactState:
    """
    Extract normalized variables from retrieved context.

    Uses LLM inference if enabled, falls back to keyword matching.
    """
    extracted = set()
    query_frame_vars = set()

    # Step 0: Identify query-frame variables (before any retrieval content)
    # These are variables mechanically implied by the query itself
    query = state.get("query", "")
    if query and config.USE_LLM_VARIABLE_EXTRACTION:
        query_frame_vars = identify_analysis_variables(query)
        extracted.update(query_frame_vars)

    # Always run keyword extraction from chains (these have high-quality normalized data)
    logic_chains = state.get("logic_chains", [])
    for chain in logic_chains:
        chain_vars = extract_from_chain(chain)
        extracted.update(chain_vars)

    synthesis = state.get("synthesis", "")
    if synthesis:
        synthesis_vars = extract_from_text(synthesis)
        extracted.update(synthesis_vars)

    answer = state.get("retrieval_answer", "")
    if answer:
        answer_vars = extract_from_text(answer)
        extracted.update(answer_vars)

    keyword_count = len(extracted)

    # Supplement with LLM-inferred variables (adds logically implied ones)
    if config.USE_LLM_VARIABLE_EXTRACTION:
        llm_vars = extract_variables_llm(state)
        if llm_vars is not None:
            new_from_llm = llm_vars - extracted
            extracted.update(llm_vars)
            if new_from_llm:
                print(f"[Variable Extraction] LLM added {len(new_from_llm)} implied variables: {sorted(new_from_llm)}")

    # Always include priority variables for the asset class
    asset_cfg = get_asset_config(state.get("asset_class", "btc"))
    extracted.add(asset_cfg["always_include_variable"])

    # Always merge priority variables
    priority = get_priority_variables(state.get("asset_class", "btc"))
    extracted.update(priority)

    # Convert to list of dicts with metadata
    variables_list = []
    for var in extracted:
        variables_list.append({
            "normalized": var,
            "source": "query_frame" if var in query_frame_vars else "extraction"
        })

    state["extracted_variables"] = variables_list

    print(f"[Variable Extraction] Extracted {len(variables_list)} unique variables:")
    print(f"  {', '.join(sorted(extracted))}")

    return state


def extract_from_chain(chain: Dict[str, Any]) -> Set[str]:
    """Extract variables from a logic chain structure."""
    variables = set()

    # Check for steps array
    steps = chain.get("steps", [])
    for step in steps:
        # Look for normalized variable names
        cause_norm = step.get("cause_normalized", "")
        effect_norm = step.get("effect_normalized", "")

        if cause_norm:
            matched = match_to_known_variable(cause_norm)
            if matched:
                variables.add(matched)

        if effect_norm:
            matched = match_to_known_variable(effect_norm)
            if matched:
                variables.add(matched)

        # Also check raw cause/effect text
        cause = step.get("cause", "")
        effect = step.get("effect", "")

        if cause:
            for var in extract_from_text(cause):
                variables.add(var)

        if effect:
            for var in extract_from_text(effect):
                variables.add(var)

    # Check chain_summary
    summary = chain.get("chain_summary", "")
    if summary:
        for var in extract_from_text(summary):
            variables.add(var)

    return variables


def extract_from_text(text: str) -> Set[str]:
    """Extract variables from free text using pattern matching."""
    variables = set()
    text_lower = text.lower()

    for var_name, patterns in VARIABLE_PATTERNS.items():
        for pattern in patterns:
            if pattern in text_lower:
                variables.add(var_name)
                break  # Found this variable, move to next

    # Also look for bracketed normalized names like [tga], [bank_reserves]
    bracketed = re.findall(r'\[([a-z_]+)\]', text_lower)
    for var in bracketed:
        if var in VARIABLE_PATTERNS:
            variables.add(var)
        elif match_to_known_variable(var):
            variables.add(match_to_known_variable(var))

    return variables


def match_to_known_variable(text: str) -> str:
    """Match text to a known variable name."""
    text_lower = text.lower().strip()

    # Direct match
    if text_lower in VARIABLE_PATTERNS:
        return text_lower

    # Check patterns
    for var_name, patterns in VARIABLE_PATTERNS.items():
        if text_lower in patterns:
            return var_name
        # Partial match
        for pattern in patterns:
            if pattern in text_lower or text_lower in pattern:
                return var_name

    return ""


def get_priority_variables(asset_class: str = "btc") -> List[str]:
    """Get high-priority variables that should always be fetched for the given asset class."""
    return get_asset_config(asset_class)["priority_variables"]
