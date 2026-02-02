"""
Relationship Store Module

Manages persistent storage of discovered BTC logic chains.
Stores chains in data/btc_relationships.json.
"""

import json
import re
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from .states import BTCImpactState
from . import config


def load_relationships() -> Dict[str, Any]:
    """
    Load the relationships database from disk.

    Returns:
        Dict with 'metadata' and 'relationships' keys
    """
    if not config.RELATIONSHIPS_FILE.exists():
        return {
            "metadata": {
                "last_updated": None,
                "total_relationships": 0
            },
            "relationships": []
        }

    try:
        with open(config.RELATIONSHIPS_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"[Relationship Store] Error loading: {e}")
        return {
            "metadata": {"last_updated": None, "total_relationships": 0},
            "relationships": []
        }


def save_relationships(data: Dict[str, Any]) -> bool:
    """
    Save the relationships database to disk.

    Args:
        data: Dict with 'metadata' and 'relationships' keys

    Returns:
        True if successful
    """
    try:
        # Update metadata
        data["metadata"]["last_updated"] = datetime.now().isoformat()
        data["metadata"]["total_relationships"] = len(data.get("relationships", []))

        # Ensure directory exists
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)

        with open(config.RELATIONSHIPS_FILE, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"[Relationship Store] Saved {data['metadata']['total_relationships']} relationships")
        return True
    except Exception as e:
        print(f"[Relationship Store] Error saving: {e}")
        return False


def load_chains(state: BTCImpactState) -> BTCImpactState:
    """
    Load historical chains from the relationship store.

    Updates state with:
    - historical_chains: List of previously discovered chains
    """
    db = load_relationships()
    chains = db.get("relationships", [])

    state["historical_chains"] = chains

    if chains:
        print(f"[Relationship Store] Loaded {len(chains)} historical chains")
    else:
        print("[Relationship Store] No historical chains found")

    return state


def extract_chains_from_answer(answer_text: str) -> List[Dict[str, Any]]:
    """
    Extract logic chains from the retrieval answer text.

    Parses chains in the format:
        **CHAIN:** cause [var] → effect [var] → ... → btc_price [btc]
        **MECHANISM:** explanation
        **SOURCE:** source info

    Returns:
        List of chain dicts with steps, summary, etc.
    """
    chains = []

    # Pattern to match chain blocks
    chain_pattern = re.compile(
        r'\*\*CHAIN:\*\*\s*(.+?)\n'
        r'\*\*MECHANISM:\*\*\s*(.+?)\n'
        r'\*\*SOURCE:\*\*\s*(.+?)(?=\n\*\*|$)',
        re.DOTALL
    )

    for match in chain_pattern.finditer(answer_text):
        chain_text = match.group(1).strip()
        mechanism = match.group(2).strip()
        source = match.group(3).strip()

        # Parse the chain steps
        steps = parse_chain_steps(chain_text, mechanism)

        if steps:
            # Build chain summary
            normalized_vars = [s.get("cause_normalized", s.get("cause", "?")) for s in steps]
            if steps:
                last_effect = steps[-1].get("effect_normalized", steps[-1].get("effect", "?"))
                normalized_vars.append(last_effect)

            chain_summary = " -> ".join(normalized_vars)

            # Determine if it ends in BTC
            terminal_effect = steps[-1].get("effect_normalized", "") if steps else ""
            is_btc_chain = any(btc_term in terminal_effect.lower()
                              for btc_term in ["btc", "bitcoin", "crypto"])

            if is_btc_chain or "btc" in chain_summary.lower():
                chains.append({
                    "logic_chain": {
                        "steps": steps,
                        "chain_summary": chain_summary
                    },
                    "terminal_effect": terminal_effect,
                    "mechanism": mechanism,
                    "source_attribution": source
                })

    return chains


def parse_chain_steps(chain_text: str, mechanism: str) -> List[Dict[str, Any]]:
    """
    Parse a chain string into individual steps.

    Input: "TGA drawdown [tga] → bank reserves increase [bank_reserves] → ..."
    Output: List of step dicts with cause, effect, normalized names
    """
    steps = []

    # Split by arrow (→ or ->)
    parts = re.split(r'\s*(?:→|->)\s*', chain_text)

    for i in range(len(parts) - 1):
        cause_part = parts[i].strip()
        effect_part = parts[i + 1].strip()

        # Extract normalized name from brackets
        cause_norm = extract_normalized(cause_part)
        effect_norm = extract_normalized(effect_part)

        # Clean the display text
        cause_text = re.sub(r'\s*\[.*?\]\s*', '', cause_part).strip()
        effect_text = re.sub(r'\s*\[.*?\]\s*', '', effect_part).strip()

        steps.append({
            "cause": cause_text,
            "cause_normalized": cause_norm or cause_text.lower().replace(" ", "_"),
            "effect": effect_text,
            "effect_normalized": effect_norm or effect_text.lower().replace(" ", "_"),
            "mechanism": mechanism if i == 0 else ""  # Only first step gets mechanism
        })

    return steps


def extract_normalized(text: str) -> str:
    """Extract normalized variable name from brackets [var_name]."""
    match = re.search(r'\[([a-z_]+)\]', text.lower())
    return match.group(1) if match else ""


def generate_chain_id(chain: Dict[str, Any]) -> str:
    """Generate a unique ID for a chain based on its content."""
    summary = chain.get("logic_chain", {}).get("chain_summary", "")
    hash_input = summary.encode()
    return f"rel_{hashlib.md5(hash_input).hexdigest()[:8]}"


def is_duplicate_chain(new_chain: Dict, existing_chains: List[Dict]) -> bool:
    """Check if a chain already exists in the database."""
    new_summary = new_chain.get("logic_chain", {}).get("chain_summary", "").lower()

    for existing in existing_chains:
        existing_summary = existing.get("logic_chain", {}).get("chain_summary", "").lower()
        if new_summary == existing_summary:
            return True

    return False


def store_chains(state: BTCImpactState) -> BTCImpactState:
    """
    Extract and store new logic chains discovered in this run.

    Parses chains from retrieval_answer and saves to btc_relationships.json.

    Updates state with:
    - discovered_chains: List of newly discovered chains
    """
    # Load existing database
    db = load_relationships()
    existing_chains = db.get("relationships", [])

    # Extract chains from answer
    answer = state.get("retrieval_answer", "")
    extracted = extract_chains_from_answer(answer)

    # Filter for new chains only
    new_chains = []
    for chain in extracted:
        if not is_duplicate_chain(chain, existing_chains):
            # Add metadata
            chain["id"] = generate_chain_id(chain)
            chain["discovered_at"] = datetime.now().isoformat()
            chain["validation_count"] = 1
            chain["relationship_type"] = determine_relationship_type(chain)
            chain["confidence"] = state.get("confidence", {}).get("score", 0.5)

            new_chains.append(chain)

    if new_chains:
        print(f"[Relationship Store] Discovered {len(new_chains)} new chains")

        # Append to database
        db["relationships"].extend(new_chains)
        save_relationships(db)
    else:
        print("[Relationship Store] No new chains discovered")

    state["discovered_chains"] = new_chains

    return state


def determine_relationship_type(chain: Dict[str, Any]) -> str:
    """Determine if the relationship is positive, negative, or neutral."""
    mechanism = chain.get("mechanism", "").lower()
    summary = chain.get("logic_chain", {}).get("chain_summary", "").lower()

    # Keywords suggesting direction
    positive_keywords = ["increase", "rise", "up", "bullish", "support", "rally", "improve"]
    negative_keywords = ["decrease", "fall", "down", "bearish", "pressure", "decline", "weaken"]

    pos_count = sum(1 for kw in positive_keywords if kw in mechanism or kw in summary)
    neg_count = sum(1 for kw in negative_keywords if kw in mechanism or kw in summary)

    if pos_count > neg_count:
        return "positive"
    elif neg_count > pos_count:
        return "negative"
    else:
        return "neutral"


def get_relevant_historical_chains(
    query: str,
    historical_chains: List[Dict],
    limit: int = 5
) -> List[Dict]:
    """
    Get historical chains relevant to the current query.

    Simple keyword matching for now.
    """
    if not historical_chains:
        return []

    query_lower = query.lower()
    scored_chains = []

    for chain in historical_chains:
        summary = chain.get("logic_chain", {}).get("chain_summary", "").lower()
        mechanism = chain.get("mechanism", "").lower()

        # Simple keyword overlap score
        score = 0
        query_words = set(query_lower.split())
        chain_words = set(summary.split() + mechanism.split())

        overlap = query_words & chain_words
        score = len(overlap)

        if score > 0:
            scored_chains.append((score, chain))

    # Sort by score and return top matches
    scored_chains.sort(key=lambda x: x[0], reverse=True)
    return [chain for _, chain in scored_chains[:limit]]


def format_historical_chains_for_prompt(chains: List[Dict]) -> str:
    """Format historical chains for inclusion in LLM prompt."""
    if not chains:
        return "(No relevant historical chains)"

    lines = ["Previously discovered logic chains:"]
    for i, chain in enumerate(chains, 1):
        summary = chain.get("logic_chain", {}).get("chain_summary", "unknown")
        rel_type = chain.get("relationship_type", "unknown")
        conf = chain.get("confidence", 0)
        lines.append(f"{i}. {summary} ({rel_type}, conf: {conf:.2f})")

    return "\n".join(lines)
