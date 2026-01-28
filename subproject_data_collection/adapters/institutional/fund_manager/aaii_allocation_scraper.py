"""
AAII Asset Allocation Survey Scraper

Scrapes monthly asset allocation data from the American Association of Individual Investors.
Source: https://www.aaii.com/assetallocationsurvey

Data includes:
- Stocks percentage
- Bonds/Fixed Income percentage
- Cash percentage
"""

from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
import re

import requests
from bs4 import BeautifulSoup

try:
    from ..base_scraper import BaseScraper
except ImportError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from base_scraper import BaseScraper


class AAIIAllocationScraper(BaseScraper):
    """Scraper for AAII monthly asset allocation survey data."""

    BASE_URL = "https://www.aaii.com/assetallocationsurvey"

    @property
    def source_name(self) -> str:
        return "aaii_allocation"

    @property
    def update_frequency(self) -> str:
        return "monthly"

    def _parse_percentage(self, text: str) -> Optional[float]:
        """Parse percentage from text."""
        if not text:
            return None

        text = text.strip().replace('%', '')
        try:
            return float(text)
        except ValueError:
            return None

    def _get_survey_date(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract survey date from page."""
        text = soup.get_text()

        # Look for month-year patterns
        date_patterns = [
            r'(\w+ \d{4})',  # "January 2026"
            r'(\w+ \d{1,2}, \d{4})',  # "January 15, 2026"
        ]

        for pattern in date_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for date_str in matches:
                for fmt in ['%B %Y', '%B %d, %Y', '%b %Y']:
                    try:
                        parsed = datetime.strptime(date_str, fmt)
                        # Return first day of month for monthly data
                        return parsed.strftime('%Y-%m-01')
                    except ValueError:
                        continue

        return None

    def _scrape_allocation_data(self) -> Dict[str, Any]:
        """
        Scrape allocation percentages from the AAII page.

        Returns:
            Dict with stocks_pct, bonds_pct, cash_pct
        """
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(self.BASE_URL, headers=headers, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')
            text = soup.get_text()

            data = {
                "stocks_pct": None,
                "bonds_pct": None,
                "cash_pct": None,
                "stocks_historical_avg": None,
                "bonds_historical_avg": None,
                "cash_historical_avg": None
            }

            # Pattern matching for allocation values
            patterns = {
                "stocks_pct": r'(?:stocks?|equit(?:y|ies))[:\s]+(\d+\.?\d*)\s*%?',
                "bonds_pct": r'(?:bonds?|fixed\s*income)[:\s]+(\d+\.?\d*)\s*%?',
                "cash_pct": r'cash[:\s]+(\d+\.?\d*)\s*%?'
            }

            for key, pattern in patterns.items():
                matches = re.findall(pattern, text, re.IGNORECASE)
                if matches:
                    data[key] = float(matches[0])
                    if len(matches) > 1:
                        avg_key = key.replace('_pct', '_historical_avg')
                        data[avg_key] = float(matches[1])

            # Try tables as well
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 2:
                        label = cells[0].get_text(strip=True).lower()
                        value_text = cells[1].get_text(strip=True)
                        value = self._parse_percentage(value_text)

                        if value is not None:
                            if 'stock' in label or 'equit' in label:
                                data['stocks_pct'] = value
                            elif 'bond' in label or 'fixed' in label:
                                data['bonds_pct'] = value
                            elif 'cash' in label:
                                data['cash_pct'] = value

            survey_date = self._get_survey_date(soup)

            return {
                "survey_date": survey_date,
                "allocation": data
            }

        except Exception as e:
            print(f"[{self.source_name}] Error scraping data: {e}")
            return {"error": str(e)}

    def check_for_update(self) -> bool:
        """Check if new monthly data is available."""
        try:
            from ..storage import ScraperStorage
        except ImportError:
            from storage import ScraperStorage
        storage_dir = Path(__file__).parent.parent.parent.parent / "data" / "scraped"
        storage = ScraperStorage(storage_dir)

        last_scrape = storage.get_last_scrape_time(self.source_name)
        if not last_scrape:
            return True

        # Check if we're in a new month
        now = datetime.now()
        return (now.year, now.month) > (last_scrape.year, last_scrape.month)

    def fetch_latest(self) -> Dict[str, Any]:
        """Fetch the latest AAII asset allocation data."""
        print(f"[{self.source_name}] Fetching latest allocation data...")

        scraped = self._scrape_allocation_data()

        source_date = scraped.get("survey_date") or datetime.now().strftime('%Y-%m-01')

        return self.format_result(
            data=scraped.get("allocation", scraped),
            source_date=source_date,
            source_url=self.BASE_URL
        )


if __name__ == "__main__":
    # Test the scraper
    scraper = AAIIAllocationScraper()
    print(f"Source: {scraper.source_name}")
    print(f"Frequency: {scraper.update_frequency}")

    result = scraper.fetch_latest()
    print(f"Result: {result}")
