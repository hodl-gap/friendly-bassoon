"""CLI entry point for Risk Intelligence Module.

Usage:
    python -m subproject_risk_intelligence "What is the impact of TGA drawdown on BTC?"
    python -m subproject_risk_intelligence --json "What is the impact of DXY strength on BTC?"
    python -m subproject_risk_intelligence --skip-data "Query without live data fetch"
    python -m subproject_risk_intelligence --use-integrated "Test TGA impact"
    python -m subproject_risk_intelligence --asset equity "What caused the SaaS meltdown?"
    python -m subproject_risk_intelligence --asset btc,equity "What caused the SaaS meltdown?"
"""

import argparse
import sys

from .insight_orchestrator import run_impact_analysis, run_multi_asset_analysis
from . import config
from shared.run_logger import RunLogger


def main():
    parser = argparse.ArgumentParser(
        description="Analyze the impact of macro events on risk assets."
    )
    parser.add_argument(
        "query",
        nargs="?",
        help="The query about macro event impact (e.g., 'What is the impact of TGA drawdown on BTC?')"
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
    parser.add_argument(
        "--use-integrated",
        action="store_true",
        help="Use integrated Variable Mapper → Data Collection pipeline"
    )
    parser.add_argument(
        "--image",
        help="Path to indicator chart image (JPEG/PNG) for vision-based date extraction"
    )
    parser.add_argument(
        "--asset",
        default="equity",
        help="Asset classes to analyze, comma-separated (e.g., 'equity', 'btc', 'btc,equity')"
    )
    parser.add_argument(
        "--mode",
        choices=["insight", "belief_space"],
        default="insight",
        help="Output mode: 'insight' (multi-track reasoning, default) or 'belief_space' (legacy scenarios)"
    )
    parser.add_argument(
        "--hybrid",
        action="store_true",
        help="Enable hybrid agentic pipeline"
    )

    args = parser.parse_args()

    if args.hybrid:
        import os
        os.environ["USE_HYBRID_PIPELINE"] = "true"

    # Handle missing query
    if not args.query:
        print("Usage: python -m subproject_risk_intelligence \"Your query about macro event impact\"")
        print("\nExamples:")
        print("  python -m subproject_risk_intelligence \"What is the impact of TGA drawdown on BTC?\"")
        print("  python -m subproject_risk_intelligence --asset equity \"What caused the SaaS meltdown?\"")
        print("  python -m subproject_risk_intelligence --asset btc,equity \"Fed just cut rates 50bps\"")
        print("  python -m subproject_risk_intelligence --json \"What is the impact of DXY strength on BTC?\"")
        print("  python -m subproject_risk_intelligence --skip-data \"Query without live data\"")
        sys.exit(1)

    # Set verbose mode
    if args.verbose:
        config.VERBOSE = True

    # Parse asset classes
    assets = [a.strip().lower() for a in args.asset.split(",")]

    # Run analysis with debug logging
    with RunLogger(query=args.query):
        if len(assets) == 1:
            # Single-asset path
            result = run_impact_analysis(
                args.query,
                asset_class=assets[0],
                output_json=args.json,
                skip_data_fetch=args.skip_data,
                skip_chain_store=args.skip_chains,
                use_integrated_pipeline=args.use_integrated,
                image_path=args.image,
                output_mode=args.mode
            )
        else:
            result = run_multi_asset_analysis(
                args.query,
                assets=assets,
                output_json=args.json,
                skip_data_fetch=args.skip_data,
                skip_chain_store=args.skip_chains,
                use_integrated_pipeline=args.use_integrated,
                image_path=args.image,
                output_mode=args.mode
            )

    # Exit with appropriate code
    if isinstance(result, dict):
        # Multi-asset returns dict of dicts; single-asset returns flat dict
        if any(isinstance(v, dict) and v.get("direction") for v in result.values()):
            sys.exit(0)
        elif result.get("direction"):
            sys.exit(0)
    sys.exit(1)


if __name__ == "__main__":
    main()
