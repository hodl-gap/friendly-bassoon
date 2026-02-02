"""CLI entry point for BTC Impact Module.

Usage:
    python -m subproject_btc_intelligence "What is the impact of TGA drawdown on BTC?"
    python -m subproject_btc_intelligence --json "What is the impact of DXY strength on BTC?"
    python -m subproject_btc_intelligence --skip-data "Query without live data fetch"
"""

import argparse
import sys

from .btc_impact_orchestrator import run_btc_impact_analysis
from . import config


def main():
    parser = argparse.ArgumentParser(
        description="Analyze the impact of macro events on Bitcoin price."
    )
    parser.add_argument(
        "query",
        nargs="?",
        help="The query about BTC impact (e.g., 'What is the impact of TGA drawdown on BTC?')"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output"
    )
    parser.add_argument(
        "--skip-data",
        action="store_true",
        help="Skip fetching current market data (Phase 1 mode)"
    )
    parser.add_argument(
        "--skip-chains",
        action="store_true",
        help="Skip loading/storing logic chains (disable Phase 3)"
    )

    args = parser.parse_args()

    # Handle missing query
    if not args.query:
        print("Usage: python -m subproject_btc_intelligence \"Your query about BTC impact\"")
        print("\nExamples:")
        print("  python -m subproject_btc_intelligence \"What is the impact of TGA drawdown on BTC?\"")
        print("  python -m subproject_btc_intelligence \"What is the impact of Fed rate cuts on BTC?\"")
        print("  python -m subproject_btc_intelligence --json \"What is the impact of DXY strength on BTC?\"")
        print("  python -m subproject_btc_intelligence --skip-data \"Query without live data\"")
        sys.exit(1)

    # Set verbose mode
    if args.verbose:
        config.VERBOSE = True

    # Run analysis
    result = run_btc_impact_analysis(
        args.query,
        output_json=args.json,
        skip_data_fetch=args.skip_data,
        skip_chain_store=args.skip_chains
    )

    # Exit with appropriate code
    if result.get("direction"):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
