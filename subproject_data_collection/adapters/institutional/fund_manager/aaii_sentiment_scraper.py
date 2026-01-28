"""
AAII Sentiment Survey Scraper

Scrapes weekly sentiment data from the American Association of Individual Investors.
Source: https://www.aaii.com/sentimentsurvey

Data includes:
- Bullish percentage
- Bearish percentage
- Neutral percentage
- Historical averages
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


class AAIISentimentScraper(BaseScraper):
    """Scraper for AAII weekly sentiment survey data."""

    BASE_URL = "https://www.aaii.com/sentimentsurvey"

    @property
    def source_name(self) -> str:
        return "aaii_sentiment"

    @property
    def update_frequency(self) -> str:
        return "weekly"

    def _parse_percentage(self, text: str) -> Optional[float]:
        """Parse percentage from text like '45.2%' or '45.2'."""
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

        # Look for date patterns
        date_patterns = [
            r'(?:Survey|Results|Week).*?(\w+ \d{1,2}, \d{4})',
            r'(\w+ \d{1,2}, \d{4})',
            r'(\d{1,2}/\d{1,2}/\d{4})'
        ]

        for pattern in date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                date_str = match.group(1)
                for fmt in ['%B %d, %Y', '%b %d, %Y', '%m/%d/%Y']:
                    try:
                        parsed = datetime.strptime(date_str, fmt)
                        return parsed.strftime('%Y-%m-%d')
                    except ValueError:
                        continue

        return None

    def _scrape_sentiment_data(self) -> Dict[str, Any]:
        """
        Scrape sentiment percentages from the AAII page.

        Returns:
            Dict with bullish, bearish, neutral percentages
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
                "bullish": None,
                "bearish": None,
                "neutral": None,
                "bullish_historical_avg": None,
                "bearish_historical_avg": None,
                "neutral_historical_avg": None
            }

            # Pattern matching for sentiment values
            # Look for patterns like "Bullish: 45.2%" or "Bullish 45.2%"
            patterns = {
                "bullish": r'bullish[:\s]+(\d+\.?\d*)\s*%?',
                "bearish": r'bearish[:\s]+(\d+\.?\d*)\s*%?',
                "neutral": r'neutral[:\s]+(\d+\.?\d*)\s*%?'
            }

            for key, pattern in patterns.items():
                matches = re.findall(pattern, text, re.IGNORECASE)
                if matches:
                    # Take the first match (current value)
                    data[key] = float(matches[0])
                    # If there's a second match, it might be historical avg
                    if len(matches) > 1:
                        data[f"{key}_historical_avg"] = float(matches[1])

            # Also try to find values in tables
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
                            if 'bullish' in label:
                                data['bullish'] = value
                            elif 'bearish' in label:
                                data['bearish'] = value
                            elif 'neutral' in label:
                                data['neutral'] = value

            # Get survey date
            survey_date = self._get_survey_date(soup)

            return {
                "survey_date": survey_date,
                "sentiment": data
            }

        except Exception as e:
            print(f"[{self.source_name}] Error scraping data: {e}")
            return {"error": str(e)}

    def check_for_update(self) -> bool:
        """Check if new weekly data is available."""
        try:
            from ..storage import ScraperStorage
        except ImportError:
            from storage import ScraperStorage
        storage_dir = Path(__file__).parent.parent.parent.parent / "data" / "scraped"
        storage = ScraperStorage(storage_dir)

        last_scrape = storage.get_last_scrape_time(self.source_name)
        if not last_scrape:
            return True

        # AAII updates Thursday morning, check if it's been >5 days
        days_since = (datetime.now() - last_scrape).days
        return days_since >= 5

    def fetch_latest(self) -> Dict[str, Any]:
        """Fetch the latest AAII sentiment data."""
        print(f"[{self.source_name}] Fetching latest sentiment data...")

        scraped = self._scrape_sentiment_data()

        source_date = scraped.get("survey_date") or datetime.now().strftime('%Y-%m-%d')

        return self.format_result(
            data=scraped.get("sentiment", scraped),
            source_date=source_date,
            source_url=self.BASE_URL
        )


if __name__ == "__main__":
    # Test the scraper
    scraper = AAIISentimentScraper()
    print(f"Source: {scraper.source_name}")
    print(f"Frequency: {scraper.update_frequency}")

    result = scraper.fetch_latest()
    print(f"Result: {result}")
