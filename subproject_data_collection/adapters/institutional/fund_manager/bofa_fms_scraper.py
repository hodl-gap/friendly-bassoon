"""
BofA Global Fund Manager Survey Scraper

Scrapes BofA FMS data via web search for leaked summaries.
BofA's monthly survey is subscription-only, but key findings often leak to:
- Yahoo Finance
- Mace News
- Zero Hedge
- Financial news sites

Data includes:
- US equity allocation/positioning
- Cash levels
- Top tail risks
- Most crowded trades
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


# Extraction prompt for BofA FMS data
BOFA_FMS_EXTRACTION_PROMPT = """Extract key data points from the BofA Global Fund Manager Survey results.

Search query: {query}

Search results:
{search_results}

Extract and return a JSON object with these fields (use null if not found):
{{
    "survey_month": "YYYY-MM format of the survey",
    "us_equity_allocation": "net percentage overweight/underweight US equities (e.g., '+15%' or '-10%')",
    "global_equity_allocation": "net percentage overweight/underweight global equities",
    "cash_level": "average cash allocation percentage",
    "cash_level_historical_avg": "historical average cash level if mentioned",
    "top_tail_risks": ["list of top 3 tail risks mentioned"],
    "most_crowded_trades": ["list of most crowded trades"],
    "recession_probability": "probability of recession mentioned",
    "fed_expectations": "expectations for Fed policy",
    "key_highlights": ["list of other notable findings"],
    "source_urls": ["urls of sources with data"]
}}

Only include data points that are explicitly mentioned in the search results.
Return valid JSON only, no other text.
"""


class BofAFMSScraper(BaseScraper):
    """Scraper for BofA Global Fund Manager Survey via web search."""

    @property
    def source_name(self) -> str:
        return "bofa_fms"

    @property
    def update_frequency(self) -> str:
        return "monthly"

    def _build_search_queries(self) -> List[str]:
        """Build search queries to find FMS data."""
        current_year = datetime.now().year
        current_month = datetime.now().strftime('%B')

        queries = [
            f"BofA Global Fund Manager Survey {current_month} {current_year}",
            f"Bank of America fund manager survey {current_year} equity allocation",
            f"BofA FMS {current_year} cash levels tail risks",
        ]
        return queries

    def _extract_fms_data(self, search_results: List[Dict]) -> Dict[str, Any]:
        """
        Extract FMS data from search results using LLM.

        Args:
            search_results: List of search result dicts

        Returns:
            Extracted FMS data
        """
        if not search_results:
            return {"error": "No search results found"}

        # Format results for LLM
        formatted = []
        for i, r in enumerate(search_results, 1):
            formatted.append(f"[{i}] {r.get('title', '')}\n{r.get('snippet', '')}\nURL: {r.get('url', '')}\n")

        formatted_text = "\n".join(formatted)
        query = "BofA Fund Manager Survey"

        prompt = BOFA_FMS_EXTRACTION_PROMPT.format(
            query=query,
            search_results=formatted_text
        )

        try:
            from models import call_claude_haiku

            messages = [{"role": "user", "content": prompt}]
            response = call_claude_haiku(messages, temperature=0.0, max_tokens=1500)

            print(f"[{self.source_name}] Raw LLM response:\n{response}")

            # Parse JSON from response
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0].strip()
            else:
                json_str = response.strip()

            return json.loads(json_str)

        except Exception as e:
            print(f"[{self.source_name}] Extraction error: {e}")
            return {"error": str(e), "raw_results": formatted_text[:2000]}

    def _search_duckduckgo(self, query: str, max_results: int = 8) -> List[Dict]:
        """Perform DuckDuckGo search."""
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

    def check_for_update(self) -> bool:
        """Check if new monthly data might be available."""
        try:
            from ..storage import ScraperStorage
        except ImportError:
            from storage import ScraperStorage
        storage_dir = Path(__file__).parent.parent.parent.parent / "data" / "scraped"
        storage = ScraperStorage(storage_dir)

        last_scrape = storage.get_last_scrape_time(self.source_name)
        if not last_scrape:
            return True

        # BofA FMS typically released mid-month
        # Check if we're in a new month or >20 days since last scrape
        now = datetime.now()
        days_since = (now - last_scrape).days

        if days_since >= 20:
            return True

        # New month
        return (now.year, now.month) > (last_scrape.year, last_scrape.month)

    def fetch_latest(self) -> Dict[str, Any]:
        """Fetch the latest BofA FMS data via web search."""
        print(f"[{self.source_name}] Searching for BofA FMS data...")

        # Run multiple search queries
        all_results = []
        queries = self._build_search_queries()

        for query in queries:
            print(f"[{self.source_name}] Searching: {query}")
            results = self._search_duckduckgo(query)
            all_results.extend(results)

            # Brief delay between searches
            time.sleep(1)

        if not all_results:
            return self.format_result(
                data={"error": "No search results found for BofA FMS"},
                source_date=datetime.now().strftime('%Y-%m-01'),
                source_url="web_search"
            )

        # Deduplicate by URL
        seen_urls = set()
        unique_results = []
        for r in all_results:
            if r.get('url') not in seen_urls:
                seen_urls.add(r.get('url'))
                unique_results.append(r)

        print(f"[{self.source_name}] Found {len(unique_results)} unique results")

        # Extract data using LLM
        extracted = self._extract_fms_data(unique_results[:12])  # Top 12 results

        # Determine source date from extracted data
        survey_month = extracted.get("survey_month")
        if survey_month:
            try:
                source_date = datetime.strptime(survey_month, '%Y-%m').strftime('%Y-%m-01')
            except ValueError:
                source_date = datetime.now().strftime('%Y-%m-01')
        else:
            source_date = datetime.now().strftime('%Y-%m-01')

        # Get source URLs
        source_urls = extracted.get("source_urls", [])
        source_url = source_urls[0] if source_urls else "web_search"

        return self.format_result(
            data=extracted,
            source_date=source_date,
            source_url=source_url
        )


if __name__ == "__main__":
    # Test the scraper
    scraper = BofAFMSScraper()
    print(f"Source: {scraper.source_name}")
    print(f"Frequency: {scraper.update_frequency}")
    print(f"Has update: {scraper.check_for_update()}")

    result = scraper.fetch_latest()
    print(f"Result keys: {result.keys()}")
    print(f"Data: {json.dumps(result.get('data', {}), indent=2)}")
