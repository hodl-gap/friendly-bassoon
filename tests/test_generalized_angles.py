"""
Full retriever test for Case Study 1 (SaaS meltdown) after generalizing angles.

Runs run_retrieval() which exercises:
- Gap detection → web chain extraction with generalized angles
- extraction_focus passthrough to LLM
- Chain merging

Then scores against the rubric from test_cases/01_saas_meltdown.md.
"""

import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
# Retriever must come before data_collection to avoid states.py collision
sys.path.insert(0, str(PROJECT_ROOT / "subproject_database_retriever"))
sys.path.append(str(PROJECT_ROOT / "subproject_data_collection"))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

QUERY = "What caused the SaaS meltdown in Feb 2026?"


def score_rubric(result: dict) -> dict:
    """Score against Case 01 rubric (13 points total, 8 to pass)."""

    synthesis = result.get("answer", "") or result.get("synthesis", "")
    chains = result.get("logic_chains", [])
    web_chains = [c for c in chains if c.get("source_type") == "web"]
    gap_text = result.get("gap_enrichment_text", "")

    # Combine all searchable text
    all_text = synthesis.lower()
    chain_text = " ".join(
        f"{c.get('cause','')} {c.get('effect','')} {c.get('mechanism','')} {c.get('evidence_quote','')}"
        for c in chains
    ).lower()
    gap_text_lower = gap_text.lower()
    searchable = all_text + " " + chain_text + " " + gap_text_lower

    scores = {}

    # A. Trigger Identification (3 points)
    a1 = "saas" in searchable and ("meltdown" in searchable or "crash" in searchable or "selloff" in searchable or "sell-off" in searchable)
    a2 = "anthropic" in searchable or ("ai" in searchable and ("tool" in searchable or "agent" in searchable or "disruption" in searchable or "eat" in searchable))
    a3 = "ai eats software" in searchable or "ai will eat" in searchable or "ai eat software" in searchable or "saaspocalypse" in searchable or "ai disruption" in searchable
    scores["A1 SaaS meltdown identified"] = 1 if a1 else 0
    scores["A2 AI disruption trigger"] = 1 if a2 else 0
    scores["A3 AI eats software / SaaSpocalypse"] = 1 if a3 else 0

    # B. CAPEX Valuation (4 points)
    b1 = "570" in searchable or "$570" in searchable or "570b" in searchable
    b2 = ("amazon" in searchable and "200" in searchable) or ("alphabet" in searchable and "185" in searchable)
    b3 = "capex" in searchable and ("destruction" in searchable or "value" in searchable or "overspend" in searchable or "sustainability" in searchable)
    b4 = ("p/e" in searchable or "pe " in searchable or "forward" in searchable) and ("compress" in searchable or "multiple" in searchable or "valuation" in searchable)
    scores["B1 Aggregate CAPEX ($570B)"] = 1 if b1 else 0
    scores["B2 Specific company CAPEX"] = 1 if b2 else 0
    scores["B3 CAPEX→value destruction chain"] = 1 if b3 else 0
    scores["B4 Valuation compression"] = 1 if b4 else 0

    # C. Contradiction (2 points)
    c1 = "logically impossible" in searchable or "contradictory" in searchable or "contradiction" in searchable
    c2 = "bofa" in searchable or "bank of america" in searchable or "merrill" in searchable
    scores["C1 Logical contradiction identified"] = 1 if c1 else 0
    scores["C2 BofA attribution"] = 1 if (c1 and c2) else 0

    # D. Quantitative Impact (3 points)
    d1 = any(x in searchable for x in ["500b", "0.5t", "300b", "$300", "$500", "trillion", "market cap"])
    d2 = any(x in searchable for x in ["39x", "21x", "85x", "60x", "p/e", "forward earnings"])
    d3 = any(x in searchable for x in ["-27%", "-30%", "27%", "30%", "bear market", "igv"])
    scores["D1 Dollar losses quantified"] = 1 if d1 else 0
    scores["D2 P/E multiple cited"] = 1 if d2 else 0
    scores["D3 Index drawdown cited"] = 1 if d3 else 0

    # E. Concrete Example (1 point)
    e1 = any(x in searchable for x in ["salesforce", "oracle", "servicenow", "workday", "toast", "fico"])
    scores["E1 Named company example"] = 1 if e1 else 0

    total = sum(scores.values())
    passed = total >= 8

    return {
        "scores": scores,
        "total": total,
        "max": 13,
        "threshold": 8,
        "passed": passed,
    }


def main():
    print(f"\n{'=' * 70}")
    print(f"FULL RETRIEVER TEST — Case Study 1: SaaS Meltdown")
    print(f"{'=' * 70}")
    print(f"Query: {QUERY}\n")

    from retrieval_orchestrator import run_retrieval
    result = run_retrieval(QUERY)

    # --- Summary ---
    chains = result.get("logic_chains", [])
    web_chains = [c for c in chains if c.get("source_type") == "web"]
    db_chains = [c for c in chains if c.get("source_type") != "web"]
    gaps = result.get("knowledge_gaps", {})
    filled = result.get("filled_gaps", [])

    print(f"\n{'=' * 70}")
    print("RETRIEVER RESULTS")
    print(f"{'=' * 70}")
    print(f"  DB chains:    {len(db_chains)}")
    print(f"  Web chains:   {len(web_chains)}")
    print(f"  Total chains: {len(chains)}")
    print(f"  Gaps found:   {len(gaps.get('gaps', [])) if isinstance(gaps, dict) else 'N/A'}")
    print(f"  Gaps filled:  {len(filled)}")

    if web_chains:
        print(f"\n  Web chains extracted:")
        for i, c in enumerate(web_chains[:10], 1):
            print(f"    {i}. {c.get('cause', '?')} → {c.get('effect', '?')} [{c.get('source_name', '?')}] conf={c.get('confidence', '?')}")

    # --- Scoring ---
    print(f"\n{'=' * 70}")
    print("RUBRIC SCORING")
    print(f"{'=' * 70}")

    scoring = score_rubric(result)
    for item, pts in scoring["scores"].items():
        mark = "+" if pts else "-"
        print(f"  [{mark}] {item}: {pts}")

    total = scoring["total"]
    verdict = "PASS" if scoring["passed"] else "FAIL"
    print(f"\n  TOTAL: {total}/{scoring['max']} (threshold: {scoring['threshold']})")
    print(f"  VERDICT: {verdict}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
