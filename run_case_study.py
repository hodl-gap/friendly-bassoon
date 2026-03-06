"""
Case Study Runner — Full Pipeline with Debug Logging

Runs a case study query through the full pipeline (Retriever → Risk Intelligence)
with comprehensive debug logging. Each run produces its own log file.

Usage:
    python run_case_study.py --case 1 --run 1
    python run_case_study.py --case 2 --run 1 --asset equity
    python run_case_study.py --query "custom query" --run 1
"""

import argparse
import os
import sys
import json
from pathlib import Path
from datetime import datetime

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "subproject_database_retriever"))
sys.path.insert(0, str(PROJECT_ROOT / "subproject_risk_intelligence"))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

# Case study definitions
CASE_STUDIES = {
    1: {
        "query": "What caused the SaaS meltdown in Feb 2026?",
        "asset": "equity",
        "rubric_file": "test_cases/01_saas_meltdown.md",
        "pass_threshold": 8,
        "total_points": 13,
    },
    2: {
        "query": "How does the February 2026 Japan snap election (Takaichi) affect risk assets and yen carry trades?",
        "asset": "equity",
        "rubric_file": "test_cases/02_japan_election.md",
        "pass_threshold": 11,
        "total_points": 18,
    },
    3: {
        "query": "Goldman Sachs Prime Book shows the biggest shorting on record for US single stocks (week of Jan 30 - Feb 5, 2026, Z-score ~+3). What are the historical precedents for record short positioning, and what outcomes followed for risk assets?",
        "asset": "equity",
        "rubric_file": "test_cases/03_record_shorting.md",
        "pass_threshold": 14,
        "total_points": 22,
    },
    4: {
        "query": "The Supreme Court ruled Trump's IEEPA tariffs illegal on Feb 20, 2026. What is the impact on US equities?",
        "asset": "equity",
        "rubric_file": "test_cases/04_scotus_tariff.md",
        "pass_threshold": 13,
        "total_points": 20,
    },
    5: {
        "query": "Equity put-call ratio surging. What does this mean for risk assets?",
        "asset": "equity",
        "rubric_file": "test_cases/05_put_call_ratio.md",
        "pass_threshold": 10,
        "total_points": 16,
    },
    6: {
        "query": "US job vacancies now equal unemployment for the first time since the pandemic. What does this mean for equities, bonds, and the dollar?",
        "asset": "equity",
        "rubric_file": "test_cases/06_labor_equilibrium.md",
        "pass_threshold": 10,
        "total_points": 16,
    },
    7: {
        "query": "FDIC data shows US banks still carry $306B in unrealized securities losses (Q4 2025), down from the -$688B peak in Q3 2022 but still 3x worse than any pre-2022 quarter. HTM losses are $207B — hidden from balance sheets. What are the historical precedents for this level of bank balance sheet stress, and under what conditions could this become a systemic risk for equities?",
        "asset": "equity",
        "rubric_file": "test_cases/07_bank_unrealized_losses.md",
        "pass_threshold": 10,
        "total_points": 16,
    },
}


def enrich_query_with_data(query: str, case_num: int) -> str:
    """Enrich a case study query with current data state when relevant.

    For queries about data-observable indicators (e.g. put-call ratio), prepend
    the actual current state so the pipeline has concrete numbers before
    retrieval begins.
    """
    if case_num == 5:
        try:
            from subproject_data_collection.proactive_data_collector import describe_put_call_state
            state = describe_put_call_state()
            if state:
                return f"{state}\n\nTrader query: {query}"
        except Exception as e:
            print(f"[enrich] Could not generate put-call state: {e}")
    if case_num == 7:
        try:
            state = _describe_fdic_state()
            if state:
                return f"{state}\n\nTrader query: {query}"
        except Exception as e:
            print(f"[enrich] Could not generate FDIC state: {e}")
    return query


def _describe_fdic_state() -> str:
    """Generate a plain-text state description of FDIC unrealized losses."""
    import csv
    csv_path = Path(__file__).parent / "subproject_data_collection" / "data" / "fdic_securities.csv"
    if not csv_path.exists():
        return ""
    rows = []
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            if row.get("total_unrealized"):
                rows.append(row)
    if len(rows) < 4:
        return ""
    latest = rows[-1]
    total = float(latest["total_unrealized"])
    htm = float(latest["htm_unrealized"]) if latest.get("htm_unrealized") else 0
    afs = float(latest["afs_unrealized"]) if latest.get("afs_unrealized") else 0
    # Peak loss
    peak_row = min(rows, key=lambda r: float(r["total_unrealized"]))
    peak_total = float(peak_row["total_unrealized"])
    # Pre-2022 worst
    pre2022 = [r for r in rows if r["date"] < "2022-01-01"]
    pre2022_worst = min(pre2022, key=lambda r: float(r["total_unrealized"])) if pre2022 else None
    lines = [
        f"FDIC bank securities data (Q4 2025): Total unrealized losses = ${total:,.0f}M "
        f"(HTM: ${htm:,.0f}M, AFS: ${afs:,.0f}M).",
        f"Peak loss: ${peak_total:,.0f}M in {peak_row['date']} (Q3 2022).",
        f"Current losses are {abs(total/peak_total)*100:.0f}% of peak but still "
        f"historically extreme.",
    ]
    if pre2022_worst:
        pre_val = float(pre2022_worst["total_unrealized"])
        lines.append(
            f"Worst pre-2022 quarter: ${pre_val:,.0f}M ({pre2022_worst['date']}). "
            f"Current level is {abs(total/pre_val):.1f}x worse."
        )
    # Recent trajectory (last 4 quarters)
    recent = rows[-4:]
    trajectory = [f"{r['date']}: ${float(r['total_unrealized']):,.0f}M" for r in recent]
    lines.append(f"Recent trajectory: {' → '.join(trajectory)}.")
    return "\n".join(lines)


def run_case(case_num: int, run_num: int, asset: str = None, query_override: str = None):
    """Run a single case study through the full pipeline with debug logging."""

    case = CASE_STUDIES.get(case_num)
    if not case and not query_override:
        print(f"Unknown case number: {case_num}")
        sys.exit(1)

    query = query_override or case["query"]
    asset = asset or (case["asset"] if case else "btc")

    # Enrich data-driven queries with current state from local CSV series
    if not query_override:
        query = enrich_query_with_data(query, case_num)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"debug_case{case_num}_run{run_num}_{timestamp}.log"
    log_path = PROJECT_ROOT / "logs" / log_filename

    print(f"\n{'=' * 70}")
    print(f"CASE STUDY {case_num} — RUN {run_num}")
    print(f"{'=' * 70}")
    print(f"Query: {query}")
    print(f"Asset: {asset}")
    print(f"Debug log: {log_path}")
    print(f"{'=' * 70}\n")

    # Initialize debug logging BEFORE importing pipeline modules
    # (monkey-patches must be applied before any Anthropic/OpenAI clients are created)
    from shared.debug_logger import init_debug_log, close_debug_log, debug_log, debug_log_node
    init_debug_log(str(log_path))
    debug_log("CASE_STUDY_START", f"Case: {case_num}\nRun: {run_num}\nQuery: {query}\nAsset: {asset}")

    # Also use RunLogger for stdout capture
    from shared.run_logger import RunLogger

    try:
        with RunLogger(query=query):
            debug_log_node("run_impact_analysis", "ENTER", f"query={query}, asset={asset}")

            from subproject_risk_intelligence.insight_orchestrator import run_impact_analysis
            result = run_impact_analysis(
                query,
                asset_class=asset,
                output_json=False,
                skip_data_fetch=False,
                skip_chain_store=False,
            )

            debug_log_node("run_impact_analysis", "EXIT", f"direction={result.get('direction', 'N/A')}")

            # Log the full result state
            insight_output = result.get("insight_output", {})
            debug_log("FINAL_RESULT_STATE", json.dumps({
                "direction": result.get("direction"),
                "confidence": result.get("confidence"),
                "output_mode": insight_output.get("output_mode"),
                "scenario_count": len(insight_output.get("scenarios", [])),
                "prediction_count": len(result.get("predictions", [])),
                "insight_output": insight_output,
                "current_values_count": len(result.get("current_values", {})),
                "logic_chains_count": len(result.get("logic_chains", [])),
                "historical_event_data": result.get("historical_event_data"),
                "historical_analogs": result.get("historical_analogs"),
                "claim_validation_results": result.get("claim_validation_results"),
                "knowledge_gaps": result.get("knowledge_gaps"),
                "filled_gaps": result.get("filled_gaps"),
                "fetch_errors": result.get("fetch_errors"),
            }, indent=2, default=str))

    except Exception as e:
        debug_log("PIPELINE_ERROR", f"Error: {e}\n{import_traceback()}")
        print(f"\nPIPELINE ERROR: {e}")
        raise
    finally:
        close_debug_log()
        print(f"\nDebug log saved to: {log_path}")

    return result, str(log_path)


def import_traceback():
    """Get traceback string."""
    import traceback
    return traceback.format_exc()


def main():
    parser = argparse.ArgumentParser(description="Run case study through full pipeline")
    parser.add_argument("--case", type=int, default=1, help="Case study number (1-7)")
    parser.add_argument("--run", type=int, default=1, help="Run number for logging")
    parser.add_argument("--asset", default=None, help="Asset class (default: from case config)")
    parser.add_argument("--query", default=None, help="Override query (for custom runs)")
    parser.add_argument("--step", action="store_true", help="Step-by-step execution mode (pause after each LLM decision and tool execution)")

    args = parser.parse_args()

    if args.step:
        os.environ["STEP_MODE"] = "1"

    result, log_path = run_case(args.case, args.run, args.asset, args.query)

    print(f"\nRun complete. Log: {log_path}")


if __name__ == "__main__":
    main()
