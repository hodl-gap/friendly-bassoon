"""
Scraper Configuration

Schedule configuration for all institutional allocation scrapers.
"""

# Scraper schedule configuration
# Uses APScheduler cron trigger format

SCRAPER_SCHEDULE = {
    # Fund Manager Positioning - run frequently
    "ici_flows": {
        "frequency": "weekly",
        "day_of_week": "fri",
        "hour": 18,
        "minute": 0,
        "description": "ICI weekly fund flows (released Friday afternoon)"
    },
    "aaii_sentiment": {
        "frequency": "weekly",
        "day_of_week": "thu",
        "hour": 12,
        "minute": 0,
        "description": "AAII sentiment survey (released Thursday)"
    },
    "aaii_allocation": {
        "frequency": "monthly",
        "day": 1,
        "hour": 10,
        "minute": 0,
        "description": "AAII asset allocation (monthly)"
    },
    "bofa_fms": {
        "frequency": "monthly",
        "day": 15,
        "hour": 10,
        "minute": 0,
        "description": "BofA Fund Manager Survey (mid-month for leaked summaries)"
    },

    # Insurer Allocation - check quarterly for annual updates
    "naic": {
        "frequency": "quarterly",
        "month": "1,4,7,10",
        "day": 1,
        "hour": 9,
        "minute": 0,
        "description": "NAIC insurance industry snapshots (annual, check quarterly)"
    },
    "acli": {
        "frequency": "quarterly",
        "month": "1,4,7,10",
        "day": 1,
        "hour": 9,
        "minute": 30,
        "description": "ACLI life insurers fact book (annual, check quarterly)"
    },
    "blackrock_insurance": {
        "frequency": "quarterly",
        "month": "1,4,7,10",
        "day": 1,
        "hour": 10,
        "minute": 0,
        "description": "BlackRock global insurance report (annual, check quarterly)"
    },

    # Japan-Specific - frequent checks
    "boj_iip": {
        "frequency": "monthly",
        "day": 1,
        "hour": 9,
        "minute": 0,
        "description": "BOJ International Investment Position (quarterly data, check monthly)"
    },
    "boj_timeseries": {
        "frequency": "weekly",
        "day_of_week": "mon",
        "hour": 9,
        "minute": 0,
        "description": "BOJ time-series data (weekly check)"
    },
    "japan_insurer_news": {
        "frequency": "daily",
        "hour": 8,
        "minute": 0,
        "description": "Japan insurer news and announcements (daily)"
    },
}


def get_cron_trigger_args(source_name: str) -> dict:
    """
    Get APScheduler CronTrigger arguments for a scraper.

    Args:
        source_name: Name of the scraper

    Returns:
        Dict of cron trigger arguments
    """
    if source_name not in SCRAPER_SCHEDULE:
        return {}

    config = SCRAPER_SCHEDULE[source_name]
    frequency = config.get("frequency", "daily")

    trigger_args = {}

    if frequency == "daily":
        trigger_args["hour"] = config.get("hour", 8)
        trigger_args["minute"] = config.get("minute", 0)

    elif frequency == "weekly":
        trigger_args["day_of_week"] = config.get("day_of_week", "mon")
        trigger_args["hour"] = config.get("hour", 9)
        trigger_args["minute"] = config.get("minute", 0)

    elif frequency == "monthly":
        trigger_args["day"] = config.get("day", 1)
        trigger_args["hour"] = config.get("hour", 9)
        trigger_args["minute"] = config.get("minute", 0)

    elif frequency == "quarterly":
        trigger_args["month"] = config.get("month", "1,4,7,10")
        trigger_args["day"] = config.get("day", 1)
        trigger_args["hour"] = config.get("hour", 9)
        trigger_args["minute"] = config.get("minute", 0)

    return trigger_args


# Scraper categories
SCRAPER_CATEGORIES = {
    "fund_manager": ["ici_flows", "aaii_sentiment", "aaii_allocation", "bofa_fms"],
    "insurer": ["naic", "acli", "blackrock_insurance"],
    "japan": ["boj_iip", "boj_timeseries", "japan_insurer_news"],
}


def get_all_scrapers() -> list:
    """Get list of all scraper names."""
    return list(SCRAPER_SCHEDULE.keys())


def get_scrapers_by_category(category: str) -> list:
    """Get scrapers for a specific category."""
    return SCRAPER_CATEGORIES.get(category, [])
