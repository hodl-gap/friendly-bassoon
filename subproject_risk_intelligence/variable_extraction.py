"""
Variable Extraction Module

Extracts normalized variables from retrieved logic chains and synthesis.
"""

import re
from typing import List, Dict, Any, Set

from .states import RiskImpactState
from .asset_configs import get_asset_config


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


def extract_variables(state: RiskImpactState) -> RiskImpactState:
    """
    Extract normalized variables from retrieved context.

    Parses:
    - Logic chains from retrieved chunks
    - Synthesis text for variable mentions
    - Answer text for variable mentions

    Updates state with:
    - extracted_variables: List of variable dicts
    """
    extracted = set()

    # 1. Extract from logic chains
    logic_chains = state.get("logic_chains", [])
    for chain in logic_chains:
        chain_vars = extract_from_chain(chain)
        extracted.update(chain_vars)

    # 2. Extract from synthesis text
    synthesis = state.get("synthesis", "")
    if synthesis:
        synthesis_vars = extract_from_text(synthesis)
        extracted.update(synthesis_vars)

    # 3. Extract from answer text
    answer = state.get("retrieval_answer", "")
    if answer:
        answer_vars = extract_from_text(answer)
        extracted.update(answer_vars)

    # Always include the target asset's primary variable
    asset_cfg = get_asset_config(state.get("asset_class", "btc"))
    extracted.add(asset_cfg["always_include_variable"])

    # Convert to list of dicts with metadata
    variables_list = []
    for var in extracted:
        variables_list.append({
            "normalized": var,
            "source": "extraction"
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
