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

from .states import RiskImpactState
from .asset_configs import get_asset_config
from . import config


def _get_relationships_file(asset_class: str = "btc") -> Path:
    """Get the relationships file path for a given asset class."""
    cfg = get_asset_config(asset_class)
    return config.DATA_DIR / cfg["relationships_file"]


def _get_regime_file(asset_class: str = "btc") -> Path:
    """Get the regime state file path for a given asset class."""
    cfg = get_asset_config(asset_class)
    return config.DATA_DIR / cfg["regime_file"]


def load_relationships(asset_class: str = "btc") -> Dict[str, Any]:
    """
    Load the relationships database from disk.

    Args:
        asset_class: Asset class to load relationships for

    Returns:
        Dict with 'metadata' and 'relationships' keys
    """
    filepath = _get_relationships_file(asset_class)
    if not filepath.exists():
        return {
            "metadata": {
                "last_updated": None,
                "total_relationships": 0
            },
            "relationships": []
        }

    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"[Relationship Store] Error loading: {e}")
        return {
            "metadata": {"last_updated": None, "total_relationships": 0},
            "relationships": []
        }


def save_relationships(data: Dict[str, Any], asset_class: str = "btc") -> bool:
    """
    Save the relationships database to disk.

    Args:
        data: Dict with 'metadata' and 'relationships' keys
        asset_class: Asset class to save relationships for

    Returns:
        True if successful
    """
    try:
        # Update metadata
        data["metadata"]["last_updated"] = datetime.now().isoformat()
        data["metadata"]["total_relationships"] = len(data.get("relationships", []))

        # Ensure directory exists
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)

        filepath = _get_relationships_file(asset_class)
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"[Relationship Store] Saved {data['metadata']['total_relationships']} relationships")
        return True
    except Exception as e:
        print(f"[Relationship Store] Error saving: {e}")
        return False


def load_chains(state: RiskImpactState, asset_class: str = "btc") -> RiskImpactState:
    """
    Load historical chains from the relationship store.

    Attempts to load chains via theme index (organized by theme).
    Falls back to loading all chains from the flat list.

    Args:
        state: Current state
        asset_class: Asset class to load chains for

    Updates state with:
    - historical_chains: List of previously discovered chains
    - theme_states: Dict of per-theme assessments (if theme index exists)
    """
    # Try theme-based loading first
    try:
        asset_cfg = get_asset_config(asset_class)
        relevant_themes = asset_cfg.get("relevant_themes", [])

        if relevant_themes:
            chains = load_chains_by_theme(relevant_themes, asset_class=asset_class)
            if chains:
                state["historical_chains"] = chains
                print(f"[Relationship Store] Loaded {len(chains)} chains from themes: {relevant_themes}")

                # Also load theme states for the prompt
                from shared.theme_index import ThemeIndex
                theme_index_path = config.DATA_DIR / "theme_index.json"
                index = ThemeIndex.load(theme_index_path)
                theme_states = {}
                for theme_name in relevant_themes:
                    ts = index.get_theme_state(theme_name)
                    if ts:
                        theme_states[theme_name] = ts
                state["theme_states"] = theme_states
                return state
    except Exception as e:
        print(f"[Relationship Store] Theme-based loading failed, falling back: {e}")

    # Fallback: load all chains from flat list
    db = load_relationships(asset_class=asset_class)
    chains = db.get("relationships", [])

    state["historical_chains"] = chains

    if chains:
        print(f"[Relationship Store] Loaded {len(chains)} historical chains")
    else:
        print("[Relationship Store] No historical chains found")

    return state


def load_chains_by_theme(theme_names: List[str], asset_class: str = "btc") -> List[Dict]:
    """
    Load chains belonging to specified themes via the theme index.

    Args:
        theme_names: List of theme names to load chains for
        asset_class: Asset class (for relationships file path)

    Returns:
        List of chain dicts from the specified themes (deduplicated)
    """
    from shared.theme_index import ThemeIndex
    theme_index_path = config.DATA_DIR / "theme_index.json"
    index = ThemeIndex.load(theme_index_path)

    db = load_relationships(asset_class=asset_class)
    all_chains = db.get("relationships", [])

    seen_ids = set()
    result = []
    for theme_name in theme_names:
        theme_chains = index.get_theme_chains(theme_name, all_chains)
        for chain in theme_chains:
            chain_id = chain.get("id")
            if chain_id and chain_id not in seen_ids:
                seen_ids.add(chain_id)
                result.append(chain)

    return result


def extract_chains_from_answer(answer_text: str, asset_class: str = "btc") -> List[Dict[str, Any]]:
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
            terminal_effect = steps[-1].get("effect_normalized", "") if steps else ""

            # Store all chains — theme index handles organization
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


def _extract_variable_pairs(chain: Dict) -> set:
    """Extract ordered (cause, effect) normalized variable pairs from a chain."""
    pairs = set()
    steps = chain.get("logic_chain", {}).get("steps", [])
    for step in steps:
        cause = step.get("cause_normalized", "")
        effect = step.get("effect_normalized", "")
        if cause and effect:
            pairs.add((cause, effect))
    return pairs


def find_similar_chain(
    new_chain: Dict,
    existing_chains: List[Dict],
    threshold: float = 0.7
) -> Optional[int]:
    """
    Find an existing chain similar to new_chain based on normalized variable overlap.

    Two chains are "similar" if they share >= threshold of their normalized
    cause/effect variable pairs (Jaccard similarity).

    Args:
        new_chain: New chain to check
        existing_chains: List of existing chains
        threshold: Minimum Jaccard similarity to consider similar

    Returns:
        Index of the similar chain, or None if no similar chain found
    """
    new_vars = _extract_variable_pairs(new_chain)
    if not new_vars:
        # Fallback to exact string match for chains without normalized vars
        new_summary = new_chain.get("logic_chain", {}).get("chain_summary", "").lower()
        for i, existing in enumerate(existing_chains):
            existing_summary = existing.get("logic_chain", {}).get("chain_summary", "").lower()
            if new_summary and new_summary == existing_summary:
                return i
        return None

    for i, existing in enumerate(existing_chains):
        existing_vars = _extract_variable_pairs(existing)
        if not existing_vars:
            continue

        overlap = len(new_vars & existing_vars)
        union = len(new_vars | existing_vars)
        if union > 0 and overlap / union >= threshold:
            return i

    return None


def is_duplicate_chain(new_chain: Dict, existing_chains: List[Dict]) -> bool:
    """Check if a chain already exists in the database (legacy wrapper)."""
    return find_similar_chain(new_chain, existing_chains) is not None


def store_chains(state: RiskImpactState, asset_class: str = "btc") -> RiskImpactState:
    """
    Extract and store new logic chains discovered in this run.

    Parses chains from retrieval_answer and saves to the asset-specific
    relationships file.

    Args:
        state: Current state
        asset_class: Asset class to store chains for

    Updates state with:
    - discovered_chains: List of newly discovered chains
    """
    # Load existing database
    db = load_relationships(asset_class=asset_class)
    existing_chains = db.get("relationships", [])

    # Extract chains from answer
    answer = state.get("retrieval_answer", "")
    extracted = extract_chains_from_answer(answer, asset_class=asset_class)

    # Filter for new chains, or reinforce existing similar chains
    new_chains = []
    reinforced_count = 0
    for chain in extracted:
        similar_idx = find_similar_chain(chain, existing_chains)

        if similar_idx is not None:
            # Reinforce existing chain: increment validation_count, blend confidence
            existing = existing_chains[similar_idx]
            existing["validation_count"] = existing.get("validation_count", 1) + 1
            existing["last_validated"] = datetime.now().isoformat()
            # Blend confidence: existing 0.7 + new 0.3
            new_conf = state.get("confidence", {}).get("score", 0.5)
            old_conf = existing.get("confidence", 0.5)
            existing["confidence"] = old_conf * 0.7 + new_conf * 0.3
            reinforced_count += 1
        else:
            # Store as new chain
            chain["id"] = generate_chain_id(chain)
            chain["discovered_at"] = datetime.now().isoformat()
            chain["validation_count"] = 1
            chain["relationship_type"] = determine_relationship_type(chain)
            chain["confidence"] = state.get("confidence", {}).get("score", 0.5)
            new_chains.append(chain)

    if reinforced_count > 0:
        print(f"[Relationship Store] Reinforced {reinforced_count} existing chains")
        save_relationships(db, asset_class=asset_class)

    if new_chains:
        print(f"[Relationship Store] Discovered {len(new_chains)} new chains")

        # Append to database
        db["relationships"].extend(new_chains)
        save_relationships(db, asset_class=asset_class)

        # Update theme index with new chains
        try:
            from shared.theme_index import ThemeIndex
            theme_index_path = config.DATA_DIR / "theme_index.json"
            index = ThemeIndex.load(theme_index_path)
            for chain in new_chains:
                themes = index.assign_chain_to_themes(chain)
                if themes:
                    print(f"[Relationship Store] Chain {chain.get('id', '?')} -> themes: {themes}")
            index.save(theme_index_path)
        except Exception as e:
            print(f"[Relationship Store] Theme index update failed: {e}")

        # Update variable frequency tracker
        try:
            from shared.variable_frequency import VariableFrequencyTracker
            freq_path = config.DATA_DIR / "variable_frequency.json"
            tracker = VariableFrequencyTracker.load(freq_path)
            for chain in new_chains:
                tracker.record_variables(chain)
            tracker.save(freq_path)
        except Exception as e:
            print(f"[Relationship Store] Variable frequency update failed: {e}")
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


# ============================================================================
# Regime State Persistence
# ============================================================================

def load_regime_state(asset_class: str = "btc") -> Dict[str, Any]:
    """
    Load the regime state from disk.

    Args:
        asset_class: Asset class to load regime state for

    Returns:
        Dict with regime state:
        - liquidity_regime: "reserve_scarce" | "reserve_abundant" | "transitional"
        - dominant_driver: Primary driver affecting the asset
        - last_updated: ISO timestamp
        - confidence: 0.0-1.0 confidence in the assessment
        - assessment_source: Where this was determined (e.g., "impact_analysis")
    """
    filepath = _get_regime_file(asset_class)
    if not filepath.exists():
        return {
            "liquidity_regime": None,
            "dominant_driver": None,
            "last_updated": None,
            "confidence": 0.0,
            "assessment_source": None
        }

    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"[Regime State] Error loading: {e}")
        return {
            "liquidity_regime": None,
            "dominant_driver": None,
            "last_updated": None,
            "confidence": 0.0,
            "assessment_source": None
        }


def save_regime_state(state: Dict[str, Any], asset_class: str = "btc") -> bool:
    """
    Save the regime state to disk.

    Args:
        state: Dict with liquidity_regime, dominant_driver, confidence, etc.
        asset_class: Asset class to save regime state for

    Returns:
        True if successful
    """
    try:
        # Update timestamp
        state["last_updated"] = datetime.now().isoformat()

        # Ensure directory exists
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)

        filepath = _get_regime_file(asset_class)
        with open(filepath, 'w') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)

        print(f"[Regime State] Saved: {state.get('liquidity_regime')} (conf: {state.get('confidence', 0):.2f})")
        return True
    except Exception as e:
        print(f"[Regime State] Error saving: {e}")
        return False


def update_regime_from_analysis(
    analysis_result: Dict[str, Any],
    threshold: float = 0.7,
    asset_class: str = "btc"
) -> Optional[Dict[str, Any]]:
    """
    Update regime state based on impact analysis results.

    Only updates if the analysis has high enough confidence and indicates
    a regime that differs from the current state.

    Args:
        analysis_result: Result from impact analysis containing direction, confidence, etc.
        threshold: Minimum confidence required to update regime (default: 0.7)
        asset_class: Asset class to update regime for

    Returns:
        New regime state if updated, None otherwise
    """
    confidence = analysis_result.get("confidence", {}).get("score", 0)

    if confidence < threshold:
        print(f"[Regime State] Not updating: confidence {confidence:.2f} below threshold {threshold}")
        return None

    # Load current state
    current = load_regime_state(asset_class=asset_class)

    # Determine new regime from analysis
    direction = analysis_result.get("direction", "").upper()
    strongest_chain = analysis_result.get("confidence", {}).get("strongest_chain", "")

    # Simple heuristic: extract dominant driver from strongest chain
    dominant_driver = None
    if strongest_chain:
        # First part of chain is typically the dominant driver
        parts = strongest_chain.replace(" -> ", "->").split("->")
        if parts:
            dominant_driver = parts[0].strip()

    # Determine liquidity regime from direction and context
    # This is a simplified heuristic - could be enhanced
    liquidity_regime = current.get("liquidity_regime")
    if "tga" in strongest_chain.lower() and direction == "BEARISH":
        liquidity_regime = "reserve_scarce"
    elif "qe" in strongest_chain.lower() or direction == "BULLISH":
        liquidity_regime = "reserve_abundant"
    elif "qt" in strongest_chain.lower():
        liquidity_regime = "transitional"

    # Check if regime changed significantly
    regime_changed = (
        liquidity_regime != current.get("liquidity_regime") or
        dominant_driver != current.get("dominant_driver")
    )

    if not regime_changed and confidence <= current.get("confidence", 0):
        print("[Regime State] No significant change detected")
        return None

    # Build new state
    new_state = {
        "liquidity_regime": liquidity_regime,
        "dominant_driver": dominant_driver,
        "confidence": confidence,
        "assessment_source": "impact_analysis",
        "direction": direction,
        "strongest_chain": strongest_chain
    }

    # Save if changed or higher confidence
    save_regime_state(new_state, asset_class=asset_class)

    return new_state


def get_regime_context_for_prompt(asset_class: str = "btc") -> str:
    """
    Format regime state for inclusion in LLM prompt.

    Args:
        asset_class: Asset class to get regime context for

    Returns:
        String describing current regime state, or empty if no state.
    """
    state = load_regime_state(asset_class=asset_class)

    if not state.get("liquidity_regime"):
        return ""

    lines = [
        "Current Regime Assessment:",
        f"- Liquidity Regime: {state.get('liquidity_regime', 'unknown')}",
        f"- Dominant Driver: {state.get('dominant_driver', 'unknown')}",
        f"- Confidence: {state.get('confidence', 0):.2f}",
        f"- Last Updated: {state.get('last_updated', 'unknown')}"
    ]

    return "\n".join(lines)
