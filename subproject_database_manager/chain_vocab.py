"""
Post-processing vocabulary normalization for logic chain cause_normalized / effect_normalized.

Loads a canonical vocabulary from data/chain_vocab.json and normalizes extracted terms via
cascade matching: exact canonical → exact synonym → word overlap → Levenshtein.
New concepts pass through cleaned (sanitized) but unmapped.
"""

import json
import os
import re

# ---------------------------------------------------------------------------
# Module-level cache for vocab
# ---------------------------------------------------------------------------
_vocab_cache = None  # dict: canonical -> [synonyms]
_reverse_cache = None  # dict: synonym -> canonical (for fast lookup)

_VOCAB_PATH = os.path.join(os.path.dirname(__file__), "data", "chain_vocab.json")


def _load_vocab():
    """Load and cache chain_vocab.json. Returns (canonical_dict, reverse_dict)."""
    global _vocab_cache, _reverse_cache
    if _vocab_cache is not None:
        return _vocab_cache, _reverse_cache

    if not os.path.exists(_VOCAB_PATH):
        _vocab_cache = {}
        _reverse_cache = {}
        return _vocab_cache, _reverse_cache

    with open(_VOCAB_PATH, "r", encoding="utf-8") as f:
        _vocab_cache = json.load(f)

    _reverse_cache = {}
    for canonical, synonyms in _vocab_cache.items():
        for syn in synonyms:
            _reverse_cache[syn] = canonical

    return _vocab_cache, _reverse_cache


# ---------------------------------------------------------------------------
# Sanitize
# ---------------------------------------------------------------------------
def _sanitize_term(raw: str) -> str:
    """Clean a raw normalized term into consistent snake_case.

    - Lowercase
    - Strip (parenthetical content)
    - Replace / - and space with _
    - Remove non-alphanum (except _)
    - Collapse multiple underscores
    - Truncate to 30 chars
    """
    if not raw:
        return ""
    t = raw.lower().strip()
    # Strip parenthetical content
    t = re.sub(r'\([^)]*\)', '', t)
    # Replace / - and space with _
    t = t.replace('/', '_').replace('-', '_').replace(' ', '_')
    # Remove anything that's not alphanum or underscore
    t = re.sub(r'[^\w]', '', t)
    # Collapse underscores
    t = re.sub(r'_+', '_', t)
    t = t.strip('_')
    # Truncate
    if len(t) > 30:
        t = t[:30].rstrip('_')
    return t


# ---------------------------------------------------------------------------
# Levenshtein (copied from metrics_mapping_utils.py for independence)
# ---------------------------------------------------------------------------
def _levenshtein_distance(s1: str, s2: str) -> int:
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


# ---------------------------------------------------------------------------
# Word overlap
# ---------------------------------------------------------------------------
def _word_overlap(a: str, b: str) -> float:
    """Jaccard-like word overlap between two snake_case terms."""
    words_a = set(a.replace('_', ' ').split())
    words_b = set(b.replace('_', ' ').split())
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def normalize_term(raw: str) -> str:
    """Normalize a single cause_normalized or effect_normalized term.

    Cascade:
      1. Exact match on canonical name
      2. Exact match on any synonym
      3. Word overlap > 0.7 vs canonical names
      4. Word overlap > 0.7 vs synonyms
      5. No match → return sanitized term (passthrough)
    """
    if not raw:
        return ""

    vocab, reverse = _load_vocab()
    sanitized = _sanitize_term(raw)

    if not sanitized:
        return ""

    # 1. Exact canonical
    if sanitized in vocab:
        return sanitized

    # 2. Exact synonym
    if sanitized in reverse:
        return reverse[sanitized]

    # 3. Word overlap > 0.7 vs canonical names
    best_overlap = 0.0
    best_canonical = None
    for canonical in vocab:
        overlap = _word_overlap(sanitized, canonical)
        if overlap > best_overlap:
            best_overlap = overlap
            best_canonical = canonical
    if best_overlap > 0.7 and best_canonical:
        return best_canonical

    # 4. Word overlap > 0.7 vs synonyms
    best_overlap = 0.0
    best_canonical = None
    for syn, canonical in reverse.items():
        overlap = _word_overlap(sanitized, syn)
        if overlap > best_overlap:
            best_overlap = overlap
            best_canonical = canonical
    if best_overlap > 0.7 and best_canonical:
        return best_canonical

    # 5. Passthrough (sanitized)
    return sanitized


def normalize_extracted_data(extracted_dict: dict) -> dict:
    """Walk logic_chains[*].steps[*] and normalize cause_normalized / effect_normalized.

    Mutates in place. Returns same dict. Idempotent.
    """
    chains = extracted_dict.get("logic_chains", [])
    for chain in chains:
        steps = chain.get("steps", [])
        for step in steps:
            if "cause_normalized" in step and step["cause_normalized"]:
                step["cause_normalized"] = normalize_term(step["cause_normalized"])
            if "effect_normalized" in step and step["effect_normalized"]:
                step["effect_normalized"] = normalize_term(step["effect_normalized"])
    return extracted_dict
