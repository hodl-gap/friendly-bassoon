#!/usr/bin/env python3
"""
Institutional Allocation Scraper Runner

CLI for running institutional allocation scrapers.

Usage:
    # Run all scrapers
    python run_scrapers.py --all

    # Run specific scraper
    python run_scrapers.py --scraper ici_flows

    # Run category of scrapers
    python run_scrapers.py --category fund_manager

    # Check for updates only (no download)
    python run_scrapers.py --check-only

    # Run with scheduler (daemon mode)
    python run_scrapers.py --daemon

    # List available scrapers
    python run_scrapers.py --list
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime

# Add institutional path for relative-style imports
sys.path.insert(0, str(Path(__file__).parent))

from storage import ScraperStorage
from scheduler import ScraperScheduler
from scraper_config import (
    SCRAPER_SCHEDULE,
    SCRAPER_CATEGORIES,
    get_cron_trigger_args,
    get_all_scrapers,
    get_scrapers_by_category
)

# Import all scrapers
from fund_manager import (
    ICIScraper,
    AAIISentimentScraper,
    AAIIAllocationScraper,
    BofAFMSScraper
)
from insurer import (
    NAICScraper,
    ACLIScraper,
    BlackRockInsuranceScraper
)
from japan import (
    BOJIIPScraper,
    BOJTimeseriesScraper,
    JapanInsurerNewsScraper
)


# Scraper class mapping
SCRAPER_CLASSES = {
    "ici_flows": ICIScraper,
    "aaii_sentiment": AAIISentimentScraper,
    "aaii_allocation": AAIIAllocationScraper,
    "bofa_fms": BofAFMSScraper,
    "naic": NAICScraper,
    "acli": ACLIScraper,
    "blackrock_insurance": BlackRockInsuranceScraper,
    "boj_iip": BOJIIPScraper,
    "boj_timeseries": BOJTimeseriesScraper,
    "japan_insurer_news": JapanInsurerNewsScraper,
}


def get_scraper_instance(name: str):
    """Get a scraper instance by name."""
    if name not in SCRAPER_CLASSES:
        raise ValueError(f"Unknown scraper: {name}")
    return SCRAPER_CLASSES[name]()


def list_scrapers():
    """List all available scrapers with their schedules."""
    print("\nAvailable Scrapers:")
    print("=" * 70)

    for category, scrapers in SCRAPER_CATEGORIES.items():
        print(f"\n{category.upper().replace('_', ' ')}:")
        print("-" * 40)

        for name in scrapers:
            config = SCRAPER_SCHEDULE.get(name, {})
            freq = config.get("frequency", "unknown")
            desc = config.get("description", "")
            print(f"  {name:<25} ({freq}) - {desc}")

    print()


def check_updates(scraper_names: list, storage: ScraperStorage):
    """Check which scrapers have updates available."""
    print("\nChecking for updates...")
    print("=" * 50)

    for name in scraper_names:
        try:
            scraper = get_scraper_instance(name)
            has_update = scraper.check_for_update()
            last_scrape = storage.get_last_scrape_time(name)
            last_str = last_scrape.strftime("%Y-%m-%d %H:%M") if last_scrape else "Never"

            status = "UPDATE AVAILABLE" if has_update else "No update"
            print(f"  {name:<25} [{status}] (Last: {last_str})")

        except Exception as e:
            print(f"  {name:<25} [ERROR: {e}]")

    print()


def run_scrapers(scraper_names: list, storage: ScraperStorage, check_first: bool = True):
    """Run specified scrapers."""
    results = {}

    print(f"\nRunning {len(scraper_names)} scraper(s)...")
    print("=" * 50)

    for name in scraper_names:
        print(f"\n[{name}] Starting...")

        try:
            scraper = get_scraper_instance(name)

            # Check for update first if requested
            if check_first:
                has_update = scraper.check_for_update()
                if not has_update:
                    print(f"[{name}] No update detected, skipping.")
                    results[name] = {"status": "skipped", "reason": "no_update"}
                    continue

            # Run scraper
            result = scraper.fetch_latest()

            # Save result
            source_date = result.get("source_date")
            storage.save(name, result, source_date)

            print(f"[{name}] Completed successfully.")
            results[name] = {"status": "success", "source_date": source_date}

        except Exception as e:
            print(f"[{name}] ERROR: {e}")
            results[name] = {"status": "error", "error": str(e)}

    # Summary
    print("\n" + "=" * 50)
    print("Summary:")
    success = sum(1 for r in results.values() if r.get("status") == "success")
    skipped = sum(1 for r in results.values() if r.get("status") == "skipped")
    errors = sum(1 for r in results.values() if r.get("status") == "error")
    print(f"  Success: {success}, Skipped: {skipped}, Errors: {errors}")

    return results


def run_daemon(storage: ScraperStorage, log_dir: Path):
    """Run scrapers in daemon mode with scheduling."""
    print("\nStarting scraper daemon...")
    print("=" * 50)

    scheduler = ScraperScheduler(storage, log_dir)

    # Register all scrapers with their schedules
    for name in get_all_scrapers():
        scraper = get_scraper_instance(name)
        trigger_args = get_cron_trigger_args(name)

        if trigger_args:
            scheduler.register_scraper(scraper, trigger_args)
            print(f"  Registered: {name} with schedule {trigger_args}")
        else:
            scheduler.register_scraper(scraper)
            print(f"  Registered: {name} (no schedule)")

    # Show scheduled jobs
    print("\nScheduled jobs:")
    for job in scheduler.get_job_info():
        print(f"  {job['name']}: next run at {job['next_run']}")

    # Start daemon
    print("\nDaemon running. Press Ctrl+C to stop.")
    scheduler.start_daemon()

    try:
        # Keep running
        import time
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("\nShutting down...")
        scheduler.stop_daemon()


def main():
    parser = argparse.ArgumentParser(
        description="Run institutional allocation data scrapers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all scrapers"
    )
    parser.add_argument(
        "--scraper",
        type=str,
        help="Run a specific scraper by name"
    )
    parser.add_argument(
        "--category",
        type=str,
        choices=["fund_manager", "insurer", "japan"],
        help="Run all scrapers in a category"
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only check for updates, don't download"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Run even if no update detected"
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run in daemon mode with scheduling"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available scrapers"
    )

    args = parser.parse_args()

    # Setup paths
    base_dir = Path(__file__).parent.parent.parent
    storage_dir = base_dir / "data" / "scraped"
    log_dir = base_dir / "logs"

    storage = ScraperStorage(storage_dir)

    # Handle commands
    if args.list:
        list_scrapers()
        return

    if args.daemon:
        run_daemon(storage, log_dir)
        return

    # Determine which scrapers to run
    scraper_names = []

    if args.all:
        scraper_names = get_all_scrapers()
    elif args.scraper:
        if args.scraper not in SCRAPER_CLASSES:
            print(f"Unknown scraper: {args.scraper}")
            print(f"Available scrapers: {list(SCRAPER_CLASSES.keys())}")
            sys.exit(1)
        scraper_names = [args.scraper]
    elif args.category:
        scraper_names = get_scrapers_by_category(args.category)

    if not scraper_names:
        print("No scrapers specified. Use --help for options.")
        sys.exit(1)

    # Run or check
    if args.check_only:
        check_updates(scraper_names, storage)
    else:
        run_scrapers(scraper_names, storage, check_first=not args.force)


if __name__ == "__main__":
    main()
