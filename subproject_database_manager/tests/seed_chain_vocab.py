"""
One-time script to seed data/chain_vocab.json from anchor variables,
variable frequency data, and hardcoded synonym clusters.

Run: python tests/seed_chain_vocab.py [--dry-run]

This was used to generate the initial vocab. Future updates are manual edits
to data/chain_vocab.json.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from chain_vocab import _sanitize_term

# Paths
ANCHOR_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "shared", "data", "anchor_variables.json"
)
FREQ_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "subproject_risk_intelligence", "data", "variable_frequency.json"
)
OUTPUT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "chain_vocab.json"
)

# ── Hardcoded synonym clusters (from graph assessment) ──────────────────────
MANUAL_SYNONYMS = {
    "fed_rate_cut": ["rate_cuts", "fed_cut", "fed_rate_cuts", "fed_easing", "rate_cut", "fed_cutting"],
    "fed_rate_hike": ["rate_hike", "fed_hike", "rate_hikes", "fed_tightening", "fed_hiking"],
    "btc_price": ["bitcoin_price", "btc", "btc_rally", "bitcoin_rally", "btc_demand", "bitcoin_demand"],
    "carry_trade_unwind": ["carry_unwind", "carry_trade_unwinding", "carry_trade_reversal"],
    "jpy_weakness": ["yen_weakness", "jpy_depreciation", "weak_yen"],
    "put_call_ratio": ["put_call_ratio_spike", "put_call_ratio_surge", "put_call_ratio_rise", "pcr", "equity_put_call_ratio"],
    "contrarian_signal": ["contrarian_buy_signal", "contrarian_indicator", "contrary_sentiment_indicator", "contrarian_buy"],
    "bearish_options_positioning": ["bearish_positioning", "put_buying", "hedging_demand", "downside_hedging"],
}

# ── Terms from variable_frequency that map to existing canonicals ───────────
# (sanitized form -> canonical)
FREQ_TO_CANONICAL = {
    "extreme_put_call_ratio_spike": "put_call_ratio",
    "spike_in_cboe_equity_put_call": "put_call_ratio",
    "signal_of_investor_fear_and_ma": "market_sentiment_reversal",
    "equity_market_decline_and_trad": "equity_market_decline",
    "contrary_sentiment_indicator_s": "contrarian_signal",
    "creates_buying_opportunity_for": "contrarian_signal",
    "contrarian_buy_signal_and_subs": "equity_relief_rally",
    "significant_equity_market_gain": "equity_relief_rally",
    "trader_hedging_demand_and_mark": "bearish_options_positioning",
}

MIN_CHAIN_COUNT = 5


def load_anchor_variables():
    """Extract canonical names from anchor_variables.json."""
    with open(ANCHOR_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return list(data.keys())


def load_high_freq_terms():
    """Extract terms with chain_count >= MIN_CHAIN_COUNT from variable_frequency.json."""
    with open(FREQ_PATH, encoding="utf-8") as f:
        data = json.load(f)

    variables = data.get("variables", data)
    terms = {}
    for name, info in variables.items():
        count = info.get("chain_count", 0) if isinstance(info, dict) else 0
        if count >= MIN_CHAIN_COUNT:
            terms[name] = count
    return terms


def build_vocab():
    """Build the canonical vocabulary dict."""
    vocab = {}

    # 1. Anchor variables → canonical with empty synonyms
    anchors = load_anchor_variables()
    for anchor in anchors:
        if anchor not in vocab:
            vocab[anchor] = []

    # 2. Manual synonym clusters
    for canonical, syns in MANUAL_SYNONYMS.items():
        if canonical in vocab:
            existing = set(vocab[canonical])
            vocab[canonical] = list(existing | set(syns))
        else:
            vocab[canonical] = list(syns)

    # 3. High-frequency terms
    freq_terms = load_high_freq_terms()
    for raw_term, count in sorted(freq_terms.items(), key=lambda x: -x[1]):
        sanitized = _sanitize_term(raw_term)
        if not sanitized:
            continue

        # Check if it maps to an existing canonical via FREQ_TO_CANONICAL
        if sanitized in FREQ_TO_CANONICAL:
            canonical = FREQ_TO_CANONICAL[sanitized]
            if canonical in vocab and sanitized not in vocab[canonical]:
                vocab[canonical].append(sanitized)
            continue

        # Check if sanitized term IS a canonical
        if sanitized in vocab:
            continue

        # Check if sanitized term is a known synonym
        is_synonym = False
        for _, syns in vocab.items():
            if sanitized in syns:
                is_synonym = True
                break
        if is_synonym:
            continue

        # New concept — add as canonical
        vocab[sanitized] = []

    return vocab


def main():
    dry_run = "--dry-run" in sys.argv

    vocab = build_vocab()

    # Stats
    total_canonical = len(vocab)
    total_synonyms = sum(len(v) for v in vocab.values())
    print(f"Built vocab: {total_canonical} canonical terms, {total_synonyms} synonyms")
    print(f"  From anchor_variables: {len(load_anchor_variables())} terms")
    print(f"  From variable_frequency (>={MIN_CHAIN_COUNT}): {len(load_high_freq_terms())} terms")
    print(f"  Manual synonym clusters: {len(MANUAL_SYNONYMS)}")

    # Show top entries
    print("\nSample entries:")
    for k in list(vocab.keys())[:10]:
        syns = vocab[k][:3]
        suffix = "..." if len(vocab[k]) > 3 else ""
        print(f"  {k}: {syns}{suffix}")

    if dry_run:
        print("\n[DRY RUN] Would write to:", OUTPUT_PATH)
    else:
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(vocab, f, indent=2, ensure_ascii=False)
        print(f"\nWrote vocab to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
