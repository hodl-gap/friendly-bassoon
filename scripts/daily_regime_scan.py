"""
Daily Regime Scan

CLI entry point for daily theme refresh and briefing generation.

Usage:
    python scripts/daily_regime_scan.py --all --briefing
    python scripts/daily_regime_scan.py --theme liquidity
    python scripts/daily_regime_scan.py --all --skip-retrieval

Can be scheduled via cron:
    0 8 * * * cd /path/to/project && python scripts/daily_regime_scan.py --all --briefing
"""

import sys
import argparse
from datetime import datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from subproject_risk_intelligence.theme_refresh import (
    refresh_theme,
    refresh_all_themes,
    generate_briefing,
)


def main():
    parser = argparse.ArgumentParser(description="Daily regime scan")
    parser.add_argument("--theme", type=str, help="Refresh a single theme")
    parser.add_argument("--all", action="store_true", help="Refresh all themes")
    parser.add_argument("--briefing", action="store_true", help="Generate morning briefing")
    parser.add_argument("--skip-retrieval", action="store_true", help="Skip retrieval step")
    args = parser.parse_args()

    if not args.theme and not args.all:
        parser.print_help()
        return

    # Track cost via RunLogger
    try:
        from shared.run_logger import RunLogger
        logger = RunLogger(query="daily_regime_scan")
    except ImportError:
        logger = None

    if args.all:
        print("=" * 60)
        print("DAILY REGIME SCAN — ALL THEMES")
        print("=" * 60)
        results = refresh_all_themes(skip_retrieval=args.skip_retrieval)
    elif args.theme:
        print(f"Refreshing theme: {args.theme}")
        results = {args.theme: refresh_theme(args.theme, skip_retrieval=args.skip_retrieval)}
    else:
        results = {}

    if args.briefing and results:
        briefing = generate_briefing(results)
        print("\n" + briefing)

        # Save briefing to logs
        logs_dir = PROJECT_ROOT / "logs"
        logs_dir.mkdir(exist_ok=True)
        date_str = datetime.now().strftime("%Y%m%d")
        briefing_path = logs_dir / f"briefing_{date_str}.md"
        with open(briefing_path, "w") as f:
            f.write(briefing)
        print(f"\nBriefing saved to {briefing_path}")


if __name__ == "__main__":
    main()
