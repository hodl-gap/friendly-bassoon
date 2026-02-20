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
import sys
import os
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
        "asset": "btc",
        "rubric_file": "test_cases/01_saas_meltdown.md",
        "pass_threshold": 8,
        "total_points": 13,
    },
    2: {
        "query": "How does the February 2026 Japan snap election (Takaichi) affect risk assets and yen carry trades?",
        "asset": "btc",
        "rubric_file": "test_cases/02_japan_election.md",
        "pass_threshold": 11,
        "total_points": 18,
    },
    3: {
        "query": "Goldman Sachs Prime Book shows the biggest shorting on record for US single stocks (week of Jan 30 - Feb 5, 2026, Z-score ~+3). What are the historical precedents for record short positioning, and what outcomes followed for risk assets?",
        "asset": "btc",
        "rubric_file": "test_cases/03_record_shorting.md",
        "pass_threshold": 14,
        "total_points": 22,
    },
}


def run_case(case_num: int, run_num: int, asset: str = None, query_override: str = None):
    """Run a single case study through the full pipeline with debug logging."""

    case = CASE_STUDIES.get(case_num)
    if not case and not query_override:
        print(f"Unknown case number: {case_num}")
        sys.exit(1)

    query = query_override or case["query"]
    asset = asset or (case["asset"] if case else "btc")

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
                output_json=False,
                skip_data_fetch=False,
                skip_chain_store=False,
                output_mode="insight"
            )

            debug_log_node("run_impact_analysis", "EXIT", f"direction={result.get('direction', 'N/A')}")

            # Log the full result state
            debug_log("FINAL_RESULT_STATE", json.dumps({
                "direction": result.get("direction"),
                "confidence": result.get("confidence"),
                "output_mode": result.get("output_mode"),
                "insight_output": result.get("insight_output"),
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
    parser.add_argument("--case", type=int, default=1, help="Case study number (1, 2, or 3)")
    parser.add_argument("--run", type=int, default=1, help="Run number for logging")
    parser.add_argument("--asset", default=None, help="Asset class (default: from case config)")
    parser.add_argument("--query", default=None, help="Override query (for custom runs)")

    args = parser.parse_args()
    result, log_path = run_case(args.case, args.run, args.asset, args.query)

    print(f"\nRun complete. Log: {log_path}")


if __name__ == "__main__":
    main()
