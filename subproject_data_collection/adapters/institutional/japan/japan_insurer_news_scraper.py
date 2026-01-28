"""
Japan Insurer News Scraper

Monitors news for Japanese insurer allocation announcements via web search.

Searches for:
- Major life insurers (Nippon Life, Dai-ichi Life, Sumitomo Life, etc.)
- Rebalancing announcements
- JGB allocation changes
- Foreign bond allocation changes
"""

import sys
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime
import json
import time

try:
    from ..base_scraper import BaseScraper
except ImportError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from base_scraper import BaseScraper

# Add parent path for models import
sys.path.append(str(Path(__file__).parent.parent.parent.parent))


# Japanese major insurers to monitor
JAPAN_INSURERS = [
    "Nippon Life",
    "Dai-ichi Life",
    "Sumitomo Life",
    "Meiji Yasuda Life",
    "Fukoku Mutual Life",
    "Taiyo Life",
    "Mitsui Life",
    "T&D Holdings",
    "Tokio Marine",
    "Sompo Holdings",
    "MS&AD Insurance",
    "GPIF",  # Government Pension Investment Fund
]

# Search queries
SEARCH_QUERIES = [
    "Japan life insurer JGB allocation {year}",
    "Japanese insurer foreign bond hedging {year}",
    "Japan pension fund rebalancing {year}",
    "Nippon Life investment plan {year}",
    "Sumitomo Life JGB allocation {year}",
    "Japan insurer yen bond allocation {year}",
    "GPIF portfolio allocation {year}",
]

# Extraction prompt
JAPAN_INSURER_EXTRACTION_PROMPT = """Extract announcements about Japanese insurer allocation decisions from these search results.

Search results:
{search_results}

Extract and return a JSON object:
{{
    "announcements": [
        {{
            "entity": "name of insurer/fund",
            "action": "rebalancing/accumulating/divesting/hedging",
            "asset_class": "JGB/foreign bonds/stocks/etc",
            "direction": "buy/sell/increase/decrease",
            "amount_yen_trillion": null or amount if mentioned,
            "timeframe": "fiscal year or period",
            "source_url": "url of source",
            "headline": "brief summary",
            "date_mentioned": "date if available"
        }}
    ],
    "market_trends": ["overall trends mentioned"],
    "source_urls": ["all source urls"]
}}

Only include concrete announcements with specific entity names.
Return valid JSON only.
"""


class JapanInsurerNewsScraper(BaseScraper):
    """Scraper for Japanese insurer news and announcements."""

    @property
    def source_name(self) -> str:
        return "japan_insurer_news"

    @property
    def update_frequency(self) -> str:
        return "daily"

    def _search_duckduckgo(self, query: str, max_results: int = 8) -> List[Dict]:
        """Perform web search."""
        try:
            from duckduckgo_search import DDGS

            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    results.append({
                        "title": r.get("title", ""),
                        "snippet": r.get("body", ""),
                        "url": r.get("href", "")
                    })

            return results

        except ImportError:
            print(f"[{self.source_name}] duckduckgo-search not installed")
            return []
        except Exception as e:
            print(f"[{self.source_name}] Search error: {e}")
            return []

    def _search_news_query(self, query: str) -> List[Dict]:
        """Search for news using DuckDuckGo news search."""
        try:
            from duckduckgo_search import DDGS

            results = []
            with DDGS() as ddgs:
                for r in ddgs.news(query, max_results=5):
                    results.append({
                        "title": r.get("title", ""),
                        "snippet": r.get("body", ""),
                        "url": r.get("url", ""),
                        "date": r.get("date", "")
                    })

            return results

        except ImportError:
            return []
        except Exception as e:
            print(f"[{self.source_name}] News search error: {e}")
            return []

    def _run_searches(self) -> List[Dict]:
        """Run all search queries and collect results."""
        all_results = []
        current_year = datetime.now().year

        # Run each query
        for query_template in SEARCH_QUERIES:
            query = query_template.format(year=current_year)
            print(f"[{self.source_name}] Searching: {query}")

            # Try news search first
            results = self._search_news_query(query)
            if not results:
                results = self._search_duckduckgo(query)

            all_results.extend(results)
            time.sleep(1)  # Rate limiting

        # Also search for each specific insurer
        for insurer in JAPAN_INSURERS[:5]:  # Top 5 insurers
            query = f"{insurer} investment allocation {current_year}"
            print(f"[{self.source_name}] Searching: {query}")
            results = self._search_duckduckgo(query, max_results=3)
            all_results.extend(results)
            time.sleep(0.5)

        # Deduplicate by URL
        seen_urls = set()
        unique_results = []
        for r in all_results:
            url = r.get('url', '')
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(r)

        return unique_results

    def _extract_announcements(self, search_results: List[Dict]) -> Dict[str, Any]:
        """Extract structured announcements using LLM."""
        if not search_results:
            return {"announcements": [], "error": "No search results"}

        # Format results
        formatted = []
        for i, r in enumerate(search_results[:15], 1):
            date_str = r.get('date', '')
            date_part = f" (Date: {date_str})" if date_str else ""
            formatted.append(
                f"[{i}] {r.get('title', '')}{date_part}\n"
                f"{r.get('snippet', '')}\n"
                f"URL: {r.get('url', '')}\n"
            )

        formatted_text = "\n".join(formatted)

        try:
            from models import call_claude_haiku

            prompt = JAPAN_INSURER_EXTRACTION_PROMPT.format(search_results=formatted_text)
            messages = [{"role": "user", "content": prompt}]
            response = call_claude_haiku(messages, temperature=0.0, max_tokens=2000)

            print(f"[{self.source_name}] Raw LLM response:\n{response}")

            # Parse JSON
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0].strip()
            else:
                json_str = response.strip()

            return json.loads(json_str)

        except Exception as e:
            print(f"[{self.source_name}] Extraction error: {e}")
            return {
                "announcements": [],
                "error": str(e),
                "raw_results": formatted_text[:3000]
            }

    def check_for_update(self) -> bool:
        """Check if we should run daily scrape."""
        try:
            from ..storage import ScraperStorage
        except ImportError:
            from storage import ScraperStorage
        storage_dir = Path(__file__).parent.parent.parent.parent / "data" / "scraped"
        storage = ScraperStorage(storage_dir)

        last_scrape = storage.get_last_scrape_time(self.source_name)
        if not last_scrape:
            return True

        # Daily check
        hours_since = (datetime.now() - last_scrape).total_seconds() / 3600
        return hours_since >= 20

    def fetch_latest(self) -> Dict[str, Any]:
        """Fetch the latest Japan insurer news."""
        print(f"[{self.source_name}] Searching for Japan insurer news...")

        # Run searches
        search_results = self._run_searches()
        print(f"[{self.source_name}] Found {len(search_results)} unique results")

        if not search_results:
            return self.format_result(
                data={
                    "announcements": [],
                    "error": "No search results found"
                },
                source_date=datetime.now().strftime('%Y-%m-%d'),
                source_url="web_search"
            )

        # Extract announcements
        extracted = self._extract_announcements(search_results)

        # Add metadata
        extracted['search_result_count'] = len(search_results)
        extracted['insurers_monitored'] = JAPAN_INSURERS

        # Get source URL from first announcement or results
        source_urls = extracted.get('source_urls', [])
        if not source_urls and extracted.get('announcements'):
            source_urls = [a.get('source_url') for a in extracted['announcements'] if a.get('source_url')]

        source_url = source_urls[0] if source_urls else "web_search"

        return self.format_result(
            data=extracted,
            source_date=datetime.now().strftime('%Y-%m-%d'),
            source_url=source_url
        )


if __name__ == "__main__":
    # Test the scraper
    scraper = JapanInsurerNewsScraper()
    print(f"Source: {scraper.source_name}")
    print(f"Frequency: {scraper.update_frequency}")

    result = scraper.fetch_latest()
    print(f"Result keys: {result.keys()}")
    print(f"Announcements: {len(result.get('data', {}).get('announcements', []))}")
