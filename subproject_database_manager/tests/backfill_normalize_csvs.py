"""
One-time backfill: normalize cause_normalized/effect_normalized in all existing CSVs.

Reads all processed CSVs (pipeline + team), normalizes the extracted_data JSON in-place,
writes back with .bak backup. Run once, then re-embed via vector_db_orchestrator.py.

Also updates Pinecone web chain vectors (category=web_chain) which have no CSV source.

Usage:
    python tests/backfill_normalize_csvs.py --dry-run     # Preview changes
    python tests/backfill_normalize_csvs.py               # Apply changes to CSVs
    python tests/backfill_normalize_csvs.py --pinecone    # Also update web chain vectors in Pinecone
"""

import csv
import json
import glob
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from chain_vocab import normalize_extracted_data, normalize_term

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCESSED_DIR = os.path.join(BASE, "data", "processed")
TEAM_DIR = os.path.join(BASE, "data", "team_processed")


def normalize_csv(csv_path, dry_run=False):
    """Normalize extracted_data in a single CSV. Returns (total_rows, changed_rows)."""
    rows = []
    fieldnames = None
    total = 0
    changed = 0

    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            total += 1
            ed_str = row.get("extracted_data", "")
            if not ed_str or not ed_str.strip():
                rows.append(row)
                continue

            try:
                ed = json.loads(ed_str)
            except json.JSONDecodeError:
                rows.append(row)
                continue

            chains = ed.get("logic_chains", [])
            if not chains:
                rows.append(row)
                continue

            # Snapshot before
            before = json.dumps(ed, ensure_ascii=False)
            normalize_extracted_data(ed)
            after = json.dumps(ed, ensure_ascii=False)

            if before != after:
                changed += 1
                row["extracted_data"] = after

            rows.append(row)

    if not dry_run and changed > 0:
        # Backup
        bak_path = csv_path + ".bak"
        if not os.path.exists(bak_path):
            shutil.copy2(csv_path, bak_path)

        # Write normalized CSV
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    return total, changed


def normalize_pinecone_web_chains(dry_run=False):
    """Fetch web chain vectors from Pinecone, normalize metadata, update."""
    try:
        from pinecone import Pinecone
        from dotenv import load_dotenv
        load_dotenv(os.path.join(BASE, "..", ".env"))
        pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
        index = pc.Index(os.getenv("PINECONE_INDEX_NAME", "research-papers"))
    except Exception as e:
        print(f"  Pinecone connection failed: {e}")
        return 0

    # Query for all web_chain vectors
    results = index.query(
        vector=[0.0] * 3072,
        filter={"category": "web_chain"},
        top_k=100,
        include_metadata=True,
    )

    if not results.matches:
        print("  No web chain vectors found in Pinecone")
        return 0

    # Fetch full vectors (query doesn't always return all metadata)
    ids = [m.id for m in results.matches]
    fetched = index.fetch(ids=ids)

    updated = 0
    updates = []
    for vid, vec in fetched.vectors.items():
        meta = vec.metadata
        ed_str = meta.get("extracted_data", "")
        if not ed_str:
            continue

        try:
            ed = json.loads(ed_str)
        except json.JSONDecodeError:
            continue

        before = json.dumps(ed, ensure_ascii=False)
        normalize_extracted_data(ed)
        after = json.dumps(ed, ensure_ascii=False)

        if before != after:
            updated += 1
            meta["extracted_data"] = after
            if not dry_run:
                updates.append({"id": vid, "metadata": meta})

    # Batch update metadata
    if updates and not dry_run:
        # Pinecone update requires re-upserting with same values
        # Fetch full vectors including embeddings
        for vid, vec in fetched.vectors.items():
            meta = vec.metadata
            ed_str = meta.get("extracted_data", "")
            if ed_str:
                try:
                    ed = json.loads(ed_str)
                    normalize_extracted_data(ed)
                    meta["extracted_data"] = json.dumps(ed, ensure_ascii=False)
                except json.JSONDecodeError:
                    pass

        # Upsert with original embeddings + updated metadata
        vectors_to_upsert = []
        for vid, vec in fetched.vectors.items():
            vectors_to_upsert.append({
                "id": vid,
                "values": vec.values,
                "metadata": vec.metadata,
            })

        if vectors_to_upsert:
            batch_size = 100
            for i in range(0, len(vectors_to_upsert), batch_size):
                batch = vectors_to_upsert[i:i + batch_size]
                index.upsert(vectors=batch)

    return updated


def main():
    dry_run = "--dry-run" in sys.argv
    do_pinecone = "--pinecone" in sys.argv

    if dry_run:
        print("=== DRY RUN (no files modified) ===\n")

    # Collect all CSVs
    csvs = []
    csvs.extend(sorted(glob.glob(os.path.join(PROCESSED_DIR, "processed_*.csv"))))
    csvs.extend(sorted(glob.glob(os.path.join(TEAM_DIR, "team_processed_*.csv"))))

    print(f"Found {len(csvs)} CSVs to process\n")

    grand_total = 0
    grand_changed = 0
    for csv_path in csvs:
        name = os.path.basename(csv_path)
        total, changed = normalize_csv(csv_path, dry_run=dry_run)
        grand_total += total
        grand_changed += changed
        if changed > 0:
            action = "would change" if dry_run else "changed"
            print(f"  {name}: {changed}/{total} rows {action}")
        else:
            print(f"  {name}: no changes needed ({total} rows)")

    print(f"\nTotal: {grand_changed}/{grand_total} rows {'would change' if dry_run else 'changed'}")

    if do_pinecone:
        print(f"\n--- Pinecone web chain vectors ---")
        wc_count = normalize_pinecone_web_chains(dry_run=dry_run)
        action = "would update" if dry_run else "updated"
        print(f"  Web chains: {wc_count} vectors {action}")

    if not dry_run and grand_changed > 0:
        print(f"\nBackup files created (.bak). To re-embed and re-upsert:")
        print(f"  for f in data/processed/processed_*.csv data/team_processed/team_processed_*.csv; do")
        print(f"    python vector_db_orchestrator.py --input \"$f\"")
        print(f"  done")


if __name__ == "__main__":
    main()
