"""
CSV Compiler for KK Kontemporaries Telegram ingestion pipeline.

Reads all intermediate JSON files and assembles the final CSV matching
the reference pipeline format exactly:
  telegram_msg_id, original_message_num, date, tg_channel, category,
  entry_type, opinion_id, raw_text, has_photo, extracted_data
"""

import csv
import json
import sys

sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent.parent))
from chain_vocab import normalize_extracted_data

# ── File paths ────────────────────────────────────────────────────────────────

BASE = "/home/peter/git/factoai/project/execution_only_test/subproject_database_manager/data/team_processed"

INPUT_CATEGORIES    = f"{BASE}/kk_step1_categories.json"
INPUT_IMAGES_B1     = f"{BASE}/kk_step2_images_batch1.json"
INPUT_IMAGES_B2     = f"{BASE}/kk_step2_images_batch2.json"
INPUT_RECATEGORIZED = f"{BASE}/kk_step2.5_recategorized.json"
INPUT_URL_ENRICH    = f"{BASE}/kk_step2.7_url_enrichment.json"
INPUT_EXTRACT_B1    = f"{BASE}/kk_step3_extraction_batch1.json"
INPUT_EXTRACT_B2    = f"{BASE}/kk_step3_extraction_batch2.json"

OUTPUT_CSV          = f"{BASE}/team_processed_KK_Kontemporaries_2026-01-29.csv"
OUTPUT_SUMMARY      = f"{BASE}/kk_categories_summary.csv"

# ── Constants ─────────────────────────────────────────────────────────────────

CHANNEL_NAME = "KK Kontemporaries"

# Reference CSV columns (must match exactly)
CSV_COLUMNS = [
    "telegram_msg_id",
    "original_message_num",
    "date",
    "tg_channel",
    "category",
    "entry_type",
    "opinion_id",
    "raw_text",
    "has_photo",
    "extracted_data",
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_extracted_data_json(extraction, url_enrich=None):
    """Build the extracted_data JSON blob from chain extraction output.

    Includes URL-enriched combined_text if available.
    """
    if extraction is None:
        return ""

    ed = {
        "source": extraction.get("source", ""),
        "data_source": extraction.get("data_source", ""),
        "asset_class": extraction.get("asset_class", ""),
        "used_data": extraction.get("used_data", ""),
        "what_happened": extraction.get("what_happened", ""),
        "interpretation": extraction.get("interpretation", ""),
        "tags": extraction.get("tags", ""),
        "topic_tags": extraction.get("topic_tags", []),
        "liquidity_metrics": extraction.get("liquidity_metrics", []),
        "logic_chains": extraction.get("logic_chains", []),
        "temporal_context": extraction.get("temporal_context", {}),
        "historical_references": extraction.get("historical_references", []),
    }
    normalize_extracted_data(ed)
    return json.dumps(ed, ensure_ascii=False)


def build_image_extracted_data_json(image_data):
    """Build extracted_data JSON blob from image structured_data."""
    if image_data is None:
        return ""

    sd = image_data.get("structured_data", {})
    summary = image_data.get("summary", "")

    ed = {
        "source": sd.get("source", ""),
        "data_source": sd.get("data_source", ""),
        "asset_class": sd.get("asset_class", ""),
        "used_data": sd.get("used_data", ""),
        "what_happened": sd.get("what_happened", ""),
        "interpretation": sd.get("interpretation", ""),
        "image_summary": summary,
    }
    return json.dumps(ed, ensure_ascii=False)


def truncate_text(text, max_len=200):
    """Truncate text for image row raw_text prefix."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


# ── Main assembly ─────────────────────────────────────────────────────────────

def main():
    # 1. Load data
    categories_data  = load_json(INPUT_CATEGORIES)
    images_b1        = load_json(INPUT_IMAGES_B1)["images"]
    images_b2        = load_json(INPUT_IMAGES_B2)["images"]
    recategorized    = load_json(INPUT_RECATEGORIZED)["recategorized"]
    url_enrichments  = load_json(INPUT_URL_ENRICH)["enrichments"]
    extractions_b1   = load_json(INPUT_EXTRACT_B1)["extractions"]
    extractions_b2   = load_json(INPUT_EXTRACT_B2)["extractions"]

    # 2. Merge image data (batch1 + batch2) keyed by str(msg_id)
    all_images = {}
    all_images.update(images_b1)
    all_images.update(images_b2)

    # 3. Build extraction lookup keyed by telegram_msg_id (int)
    extraction_by_id = {}
    for e in extractions_b1 + extractions_b2:
        extraction_by_id[e["telegram_msg_id"]] = e

    # 4. Build final category map: start from step1, override with step2.5
    messages = categories_data["messages"]
    msg_by_id = {m["telegram_msg_id"]: m for m in messages}

    for msg_id_str, recat in recategorized.items():
        msg_id = int(msg_id_str)
        if msg_id in msg_by_id:
            msg_by_id[msg_id]["category"] = recat["final_category"]

    # 5. Build opinion_id mapping: kk_kontemp_N → KK_Kontemporaries_N
    # (reference uses channel name with underscores)

    # 6. Build rows
    rows = []

    for msg in messages:
        msg_id   = msg["telegram_msg_id"]
        category = msg_by_id[msg_id]["category"]
        photo    = msg.get("photo", "")
        text     = msg.get("text", "")
        date     = msg.get("date", "")
        orig_num = msg.get("original_message_num", "")

        # Skip "other" category entirely
        if category == "other":
            continue

        extraction = extraction_by_id.get(msg_id)
        image_data = all_images.get(str(msg_id))
        url_enrich = url_enrichments.get(str(msg_id))

        # Convert opinion_id format: kk_kontemp_N → KK_Kontemporaries_N
        opinion_id_raw = extraction.get("opinion_id", "") if extraction else ""
        opinion_id = opinion_id_raw.replace("kk_kontemp_", "KK_Kontemporaries_")

        # Build raw_text for text rows: original text + URL enrichment
        raw_text_parts = []
        if text:
            raw_text_parts.append(text)
        if url_enrich and url_enrich.get("fetched_text"):
            raw_text_parts.append(url_enrich["fetched_text"])
        raw_text = "\n\n".join(raw_text_parts)

        # ── TEXT row ──────────────────────────────────────────────────────
        if extraction is not None:
            row = {
                "telegram_msg_id":    msg_id,
                "original_message_num": orig_num,
                "date":               date,
                "tg_channel":         CHANNEL_NAME,
                "category":           category,
                "entry_type":         "text",
                "opinion_id":         opinion_id,
                "raw_text":           raw_text,
                "has_photo":          photo,
                "extracted_data":     build_extracted_data_json(extraction, url_enrich),
            }
            rows.append(row)

        # ── IMAGE row ─────────────────────────────────────────────────────
        # Only if message has a photo AND image extraction data exists
        if photo and image_data is not None:
            # Image row raw_text: [Image from message: <truncated original text>]
            if text:
                image_raw_text = f"[Image from message: {truncate_text(text)}]"
            else:
                image_raw_text = "[Image — no accompanying text]"

            row = {
                "telegram_msg_id":    msg_id,
                "original_message_num": orig_num,
                "date":               date,
                "tg_channel":         CHANNEL_NAME,
                "category":           category,
                "entry_type":         "image",
                "opinion_id":         opinion_id,
                "raw_text":           image_raw_text,
                "has_photo":          photo,
                "extracted_data":     build_image_extracted_data_json(image_data),
            }
            rows.append(row)

    # 7. Sort: by telegram_msg_id ascending, then entry_type (text < image)
    def sort_key(r):
        entry_order = 0 if r["entry_type"] == "text" else 1
        return (r["telegram_msg_id"], entry_order)

    rows.sort(key=sort_key)

    # 8. Write main CSV (UTF-8 BOM)
    with open(OUTPUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {OUTPUT_CSV}")
    text_rows  = sum(1 for r in rows if r["entry_type"] == "text")
    image_rows = sum(1 for r in rows if r["entry_type"] == "image")
    print(f"  text rows:  {text_rows}")
    print(f"  image rows: {image_rows}")

    # 9. Write categories summary CSV
    from collections import Counter
    final_cats = Counter(msg_by_id[m["telegram_msg_id"]]["category"] for m in messages)

    summary_rows = [
        {"category": cat, "count": cnt}
        for cat, cnt in sorted(final_cats.items())
    ]
    with open(OUTPUT_SUMMARY, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["category", "count"])
        writer.writeheader()
        writer.writerows(summary_rows)

    print(f"\nCategories summary written to {OUTPUT_SUMMARY}")
    for r in summary_rows:
        print(f"  {r['category']}: {r['count']}")


if __name__ == "__main__":
    main()
