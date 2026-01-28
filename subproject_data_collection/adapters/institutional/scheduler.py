"""
Scraper Scheduler

APScheduler-based scheduling for running scrapers on a schedule.
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable
from pathlib import Path

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False

try:
    from .base_scraper import BaseScraper
    from .storage import ScraperStorage
except ImportError:
    from base_scraper import BaseScraper
    from storage import ScraperStorage


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ScraperScheduler")


class ScraperScheduler:
    """
    Scheduler for running scrapers on a cron-like schedule.

    Uses APScheduler for scheduling. Falls back to manual execution
    if APScheduler is not installed.
    """

    def __init__(self, storage: ScraperStorage, log_dir: Optional[Path] = None):
        """
        Initialize scheduler.

        Args:
            storage: ScraperStorage instance for saving results
            log_dir: Directory for log files (optional)
        """
        self.storage = storage
        self.log_dir = log_dir
        self.scrapers: Dict[str, BaseScraper] = {}
        self.scheduler = None

        if APSCHEDULER_AVAILABLE:
            self.scheduler = BackgroundScheduler()
        else:
            logger.warning("APScheduler not installed. Run: pip install apscheduler")

        if log_dir:
            log_dir.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_dir / "scraper_scheduler.log")
            file_handler.setFormatter(
                logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            )
            logger.addHandler(file_handler)

    def register_scraper(
        self,
        scraper: BaseScraper,
        schedule_config: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Register a scraper with the scheduler.

        Args:
            scraper: Scraper instance to register
            schedule_config: Optional schedule config. If None, no scheduling.
                Example: {"day_of_week": "fri", "hour": 18}
        """
        self.scrapers[scraper.source_name] = scraper
        logger.info(f"Registered scraper: {scraper.source_name}")

        if schedule_config and self.scheduler:
            self._add_job(scraper, schedule_config)

    def _add_job(self, scraper: BaseScraper, config: Dict[str, Any]) -> None:
        """Add a scheduled job for a scraper."""
        trigger = CronTrigger(**config)
        self.scheduler.add_job(
            func=self._run_scraper,
            trigger=trigger,
            args=[scraper.source_name],
            id=scraper.source_name,
            name=f"Scrape {scraper.source_name}",
            replace_existing=True
        )
        logger.info(f"Scheduled {scraper.source_name} with config: {config}")

    def _run_scraper(self, source_name: str) -> Dict[str, Any]:
        """
        Run a single scraper and save results.

        Args:
            source_name: Name of the scraper to run

        Returns:
            Scrape result or error dict
        """
        if source_name not in self.scrapers:
            logger.error(f"Unknown scraper: {source_name}")
            return {"error": f"Unknown scraper: {source_name}"}

        scraper = self.scrapers[source_name]
        logger.info(f"Running scraper: {source_name}")

        try:
            # Check if update available
            has_update = scraper.check_for_update()

            if not has_update:
                logger.info(f"No update detected for {source_name}")
                return {
                    "source": source_name,
                    "status": "no_update",
                    "timestamp": datetime.now().isoformat()
                }

            # Fetch data
            result = scraper.fetch_latest()

            # Save to storage
            source_date = result.get("source_date")
            self.storage.save(source_name, result, source_date)

            logger.info(f"Successfully scraped {source_name}")
            return result

        except Exception as e:
            logger.error(f"Error scraping {source_name}: {e}", exc_info=True)
            return {
                "source": source_name,
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    def run_scraper(self, source_name: str) -> Dict[str, Any]:
        """
        Run a specific scraper immediately.

        Args:
            source_name: Name of scraper to run

        Returns:
            Scrape result
        """
        return self._run_scraper(source_name)

    def run_all(self, check_updates_first: bool = True) -> Dict[str, Dict[str, Any]]:
        """
        Run all registered scrapers.

        Args:
            check_updates_first: If True, only fetch if update detected

        Returns:
            Dict mapping source_name to result
        """
        results = {}
        for source_name in self.scrapers:
            results[source_name] = self._run_scraper(source_name)
        return results

    def check_all_updates(self) -> Dict[str, bool]:
        """
        Check which scrapers have updates available.

        Returns:
            Dict mapping source_name to has_update bool
        """
        updates = {}
        for source_name, scraper in self.scrapers.items():
            try:
                updates[source_name] = scraper.check_for_update()
            except Exception as e:
                logger.error(f"Error checking {source_name}: {e}")
                updates[source_name] = False
        return updates

    def start_daemon(self) -> None:
        """Start the scheduler in daemon mode."""
        if not self.scheduler:
            logger.error("APScheduler not available. Cannot start daemon.")
            return

        logger.info("Starting scheduler daemon...")
        self.scheduler.start()

    def stop_daemon(self) -> None:
        """Stop the scheduler daemon."""
        if self.scheduler:
            self.scheduler.shutdown()
            logger.info("Scheduler daemon stopped.")

    def get_job_info(self) -> List[Dict[str, Any]]:
        """Get info about scheduled jobs."""
        if not self.scheduler:
            return []

        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": str(job.next_run_time) if job.next_run_time else None,
                "trigger": str(job.trigger)
            })
        return jobs
