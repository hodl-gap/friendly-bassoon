"""
Auto-expand chain_vocab.json from pipeline output.

Scans all processed CSVs (team + API pipeline), finds passthrough terms appearing 3+ times,
groups similar ones by word overlap, and proposes vocab additions.

Usage:
    python tests/expand_chain_vocab.py                # Dry run — show proposals
    python tests/expand_chain_vocab.py --execute      # Apply to chain_vocab.json
"""

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from chain_vocab import _sanitize_term, _word_overlap

VOCAB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "chain_vocab.json")
TEAM_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "team_processed")
PROC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "processed")

MIN_FREQ = 3  # Only consider terms appearing 3+ times


def scan_passthrough_terms():
    """Scan all CSVs for cause/effect_normalized terms not in current vocab."""
    with open(VOCAB_PATH, "r", encoding="utf-8") as f:
        vocab = json.load(f)
    canonical_set = set(vocab.keys())

    term_counts = Counter()

    # Scan team CSVs
    if os.path.exists(TEAM_DIR):
        for fname in os.listdir(TEAM_DIR):
            if fname.startswith("team_processed_") and fname.endswith(".csv"):
                _scan_csv(os.path.join(TEAM_DIR, fname), canonical_set, term_counts)

    # Scan API pipeline CSVs
    if os.path.exists(PROC_DIR):
        for fname in os.listdir(PROC_DIR):
            if fname.endswith(".csv"):
                _scan_csv(os.path.join(PROC_DIR, fname), canonical_set, term_counts)

    return term_counts, vocab


def _scan_csv(path, canonical_set, term_counts):
    """Extract passthrough terms from a single CSV."""
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ed = row.get("extracted_data", "").strip()
                if not ed or ed == "{}":
                    continue
                try:
                    data = json.loads(ed)
                except (json.JSONDecodeError, ValueError):
                    continue
                for chain in data.get("logic_chains", []):
                    for step in chain.get("steps", []):
                        for field in ["cause_normalized", "effect_normalized"]:
                            term = step.get(field, "")
                            if term and term not in canonical_set:
                                term_counts[term] += 1
    except Exception:
        pass


def find_existing_match(term, vocab):
    """Check if term should be a synonym of an existing canonical entry."""
    best_score = 0.0
    best_canonical = None

    for canonical, synonyms in vocab.items():
        score = _word_overlap(term, canonical)
        if score > best_score:
            best_score = score
            best_canonical = canonical
        for syn in synonyms:
            score = _word_overlap(term, syn)
            if score > best_score:
                best_score = score
                best_canonical = canonical

    # Require >0.7 overlap (stricter to avoid false merges like tariff_shock → auto_sales)
    if best_score > 0.7 and best_canonical:
        return best_canonical
    return None


def cluster_new_terms(terms_with_freq, vocab):
    """
    Group passthrough terms into:
    1. Synonym additions to existing canonical entries
    2. New canonical clusters (grouped by word overlap)
    """
    synonym_additions = defaultdict(list)  # existing_canonical -> [new synonyms]
    new_clusters = []  # [{canonical, synonyms, total_freq}]

    # Sort by frequency descending
    sorted_terms = sorted(terms_with_freq, key=lambda x: x[1], reverse=True)

    assigned = set()

    # Pass 1: match against existing vocab
    for term, freq in sorted_terms:
        match = find_existing_match(term, vocab)
        if match:
            synonym_additions[match].append((term, freq))
            assigned.add(term)

    # Pass 2: cluster remaining terms among themselves
    remaining = [(t, f) for t, f in sorted_terms if t not in assigned]

    for term, freq in remaining:
        if term in assigned:
            continue

        # Try to join an existing new cluster
        joined = False
        for cluster in new_clusters:
            if _word_overlap(term, cluster["canonical"]) > 0.6:
                cluster["synonyms"].append(term)
                cluster["total_freq"] += freq
                joined = True
                assigned.add(term)
                break
            for syn in cluster["synonyms"]:
                if _word_overlap(term, syn) > 0.6:
                    cluster["synonyms"].append(term)
                    cluster["total_freq"] += freq
                    joined = True
                    assigned.add(term)
                    break
            if joined:
                break

        if not joined:
            # Start a new cluster — most frequent term becomes canonical
            new_clusters.append({
                "canonical": term,
                "synonyms": [],
                "total_freq": freq,
            })
            assigned.add(term)

    return synonym_additions, new_clusters


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="Apply changes to chain_vocab.json")
    parser.add_argument("--min-freq", type=int, default=MIN_FREQ, help="Minimum frequency threshold")
    args = parser.parse_args()

    term_counts, vocab = scan_passthrough_terms()

    # Filter to terms with sufficient frequency
    frequent = [(t, c) for t, c in term_counts.items() if c >= args.min_freq]

    print(f"Total passthrough terms: {len(term_counts)}")
    print(f"Terms with freq >= {args.min_freq}: {len(frequent)}")
    print(f"Current vocab: {len(vocab)} canonical, {sum(len(v) for v in vocab.values())} synonyms")
    print()

    synonym_additions, new_clusters = cluster_new_terms(frequent, vocab)

    # Report synonym additions
    if synonym_additions:
        print(f"=== SYNONYM ADDITIONS ({sum(len(v) for v in synonym_additions.values())} terms → {len(synonym_additions)} existing entries) ===")
        for canonical, new_syns in sorted(synonym_additions.items()):
            existing = vocab[canonical][:3]
            new_list = [f"{t} ({f}x)" for t, f in new_syns]
            print(f"  {canonical} [has: {', '.join(existing)}...]")
            print(f"    + {', '.join(new_list)}")
        print()

    # Report new clusters
    meaningful_clusters = [c for c in new_clusters if c["total_freq"] >= args.min_freq]
    if meaningful_clusters:
        print(f"=== NEW CANONICAL ENTRIES ({len(meaningful_clusters)} clusters) ===")
        for cluster in sorted(meaningful_clusters, key=lambda x: x["total_freq"], reverse=True):
            if cluster["synonyms"]:
                print(f"  {cluster['canonical']} ({cluster['total_freq']}x total)")
                print(f"    synonyms: {', '.join(cluster['synonyms'])}")
            else:
                print(f"  {cluster['canonical']} ({cluster['total_freq']}x)")
        print()

    # Apply
    if args.execute:
        # Backup
        import shutil
        backup = VOCAB_PATH + ".bak"
        shutil.copy2(VOCAB_PATH, backup)
        print(f"Backed up to {backup}")

        # Add synonyms
        added_syns = 0
        for canonical, new_syns in synonym_additions.items():
            for term, _ in new_syns:
                if term not in vocab[canonical]:
                    vocab[canonical].append(term)
                    added_syns += 1

        # Add new canonical entries
        added_canonical = 0
        for cluster in meaningful_clusters:
            if cluster["canonical"] not in vocab:
                vocab[cluster["canonical"]] = cluster["synonyms"]
                added_canonical += 1

        with open(VOCAB_PATH, "w", encoding="utf-8") as f:
            json.dump(vocab, f, indent=2, ensure_ascii=False)

        new_total_syns = sum(len(v) for v in vocab.values())
        print(f"Added {added_syns} synonyms to existing entries")
        print(f"Added {added_canonical} new canonical entries")
        print(f"Vocab now: {len(vocab)} canonical, {new_total_syns} synonyms")
    else:
        print("Dry run. Use --execute to apply.")


if __name__ == "__main__":
    main()
