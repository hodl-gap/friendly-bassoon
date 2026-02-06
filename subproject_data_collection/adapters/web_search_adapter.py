"""
Web Search Adapter

Searches the web for information and extracts key data points using LLM.
Unlike other adapters, this doesn't fetch time series - it finds qualitative data.

Cost: ~$0.0003 per search (Haiku extraction from snippets)
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import json
import hashlib
import time

# Add parent paths for imports
sys.path.append(str(Path(__file__).parent.parent))
sys.path.append(str(Path(__file__).parent.parent.parent))

from config import CACHE_DIR, ENABLE_CACHE, CACHE_EXPIRY_HOURS, WEB_SEARCH_BACKEND
from models import call_claude_haiku
from web_search_prompts import (
    EXTRACT_DATA_POINTS_PROMPT,
    EXTRACT_ANNOUNCEMENTS_PROMPT,
    EXTRACT_KNOWLEDGE_GAP_PROMPT,
    EXTRACT_LOGIC_CHAINS_PROMPT
)
from adapters.trusted_domains import filter_to_trusted_sources, is_trusted_domain


class WebSearchAdapter:
    """
    Web search adapter that extracts structured data from search results.

    Supports multiple backends:
    - "tavily": Tavily API (returns full page content, better quality)
    - "duckduckgo": DuckDuckGo (free, snippets only)

    Backend is controlled by WEB_SEARCH_BACKEND in config.py.

    Example usage:
        adapter = WebSearchAdapter()

        # Search for quantitative data
        result = adapter.search_and_extract(
            query="USD JPY hedging cost basis swap 2026",
            extract_type="data_points"
        )

        # Search for announcements
        result = adapter.search_and_extract(
            query="Sumitomo Life JGB rebalancing 2026",
            extract_type="announcements"
        )
    """

    def __init__(self, max_results: int = 8, backend: str = None):
        """
        Initialize the web search adapter.

        Args:
            max_results: Maximum search results to fetch (default 8)
            backend: Search backend override ("tavily" or "duckduckgo"). Defaults to config.
        """
        self.max_results = max_results
        self.backend = backend or WEB_SEARCH_BACKEND
        self.source_name = "WebSearch"

    def _get_cache_key(self, query: str, extract_type: str) -> str:
        """Generate cache key for this search."""
        key_str = f"{self.source_name}:{query}:{extract_type}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def _get_from_cache(self, query: str, extract_type: str) -> Optional[Dict[str, Any]]:
        """Try to get data from cache."""
        if not ENABLE_CACHE:
            return None

        cache_key = self._get_cache_key(query, extract_type)
        cache_file = CACHE_DIR / f"websearch_{cache_key}.json"

        if not cache_file.exists():
            return None

        try:
            file_mtime = datetime.fromtimestamp(cache_file.stat().st_mtime)
            age_hours = (datetime.now() - file_mtime).total_seconds() / 3600

            if age_hours > CACHE_EXPIRY_HOURS:
                print(f"[{self.source_name}] Cache expired for query: {query[:50]}...")
                return None

            with open(cache_file, 'r') as f:
                cached_data = json.load(f)
                print(f"[{self.source_name}] Cache hit for query: {query[:50]}...")
                return cached_data

        except Exception as e:
            print(f"[{self.source_name}] Cache read error: {e}")
            return None

    def _save_to_cache(self, query: str, extract_type: str, data: Dict[str, Any]) -> None:
        """Save data to cache."""
        if not ENABLE_CACHE:
            return

        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_key = self._get_cache_key(query, extract_type)
            cache_file = CACHE_DIR / f"websearch_{cache_key}.json"

            with open(cache_file, 'w') as f:
                json.dump(data, f, default=str, indent=2)
                print(f"[{self.source_name}] Cached result for query: {query[:50]}...")

        except Exception as e:
            print(f"[{self.source_name}] Cache write error: {e}")

    def _search_duckduckgo(self, query: str) -> List[Dict[str, str]]:
        """
        Search DuckDuckGo and return results.

        Returns:
            List of dicts with 'title', 'snippet', 'url'
        """
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            print(f"[{self.source_name}] duckduckgo-search not installed. Run: pip install duckduckgo-search")
            return []

        try:
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=self.max_results):
                    results.append({
                        "title": r.get("title", ""),
                        "snippet": r.get("body", ""),
                        "url": r.get("href", "")
                    })

            print(f"[{self.source_name}] Found {len(results)} results for: {query[:50]}...")
            return results

        except Exception as e:
            print(f"[{self.source_name}] Search error: {e}")
            return []

    def _search_tavily(self, query: str) -> List[Dict[str, str]]:
        """
        Search using Tavily API. Returns results with full page content.

        Returns:
            List of dicts with 'title', 'snippet', 'url', and 'content' (full page text)
        """
        try:
            from tavily import TavilyClient
        except ImportError:
            print(f"[{self.source_name}] tavily-python not installed. Run: pip install tavily-python")
            return []

        try:
            api_key = os.getenv("TAVILY_API_KEY")
            if not api_key:
                print(f"[{self.source_name}] TAVILY_API_KEY not set in .env")
                return []

            client = TavilyClient(api_key=api_key)
            response = client.search(
                query=query,
                max_results=self.max_results,
                include_raw_content=True,
                topic="finance"
            )

            results = []
            for r in response.get("results", []):
                raw_content = r.get("raw_content") or ""
                # Truncate raw content to avoid blowing up the prompt
                if len(raw_content) > 3000:
                    raw_content = raw_content[:3000] + "\n... [truncated]"

                results.append({
                    "title": r.get("title", ""),
                    "snippet": r.get("content", ""),
                    "url": r.get("url", ""),
                    "content": raw_content
                })

            print(f"[{self.source_name}] Tavily found {len(results)} results for: {query[:50]}...")
            return results

        except Exception as e:
            print(f"[{self.source_name}] Tavily search error: {e}")
            return []

    def _search(self, query: str) -> List[Dict[str, str]]:
        """Route to the configured search backend."""
        if self.backend == "tavily":
            return self._search_tavily(query)
        else:
            return self._search_duckduckgo(query)

    def _format_search_results(self, results: List[Dict[str, str]]) -> str:
        """Format search results for LLM consumption. Includes full content when available."""
        if not results:
            return "No search results found."

        formatted = []
        for i, r in enumerate(results, 1):
            entry = f"[{i}] {r['title']}\n{r['snippet']}\nSource: {r['url']}"
            # Include full page content if available (from Tavily)
            content = r.get("content", "")
            if content:
                entry += f"\n\n--- Full Content ---\n{content}"
            formatted.append(entry + "\n")

        return "\n".join(formatted)

    def _extract_with_llm(
        self,
        query: str,
        search_results: str,
        extract_type: str,
        gap_category: str = None,
        missing_description: str = None,
        topic: str = None
    ) -> Dict[str, Any]:
        """
        Extract structured data from search results using Haiku.

        Args:
            query: Original search query
            search_results: Formatted search results text
            extract_type: "data_points", "announcements", "knowledge_gap", or "logic_chains"
            gap_category: (for knowledge_gap) Category of the gap being filled
            missing_description: (for knowledge_gap) What information is needed
            topic: (for logic_chains) Topic for chain extraction

        Returns:
            Extracted data as dict
        """
        if extract_type == "data_points":
            prompt_template = EXTRACT_DATA_POINTS_PROMPT
            user_prompt = prompt_template.format(
                query=query,
                search_results=search_results
            )
        elif extract_type == "announcements":
            prompt_template = EXTRACT_ANNOUNCEMENTS_PROMPT
            user_prompt = prompt_template.format(
                query=query,
                search_results=search_results
            )
        elif extract_type == "knowledge_gap":
            prompt_template = EXTRACT_KNOWLEDGE_GAP_PROMPT
            user_prompt = prompt_template.format(
                gap_category=gap_category or "unknown",
                missing_description=missing_description or query,
                query=query,
                search_results=search_results
            )
        elif extract_type == "logic_chains":
            prompt_template = EXTRACT_LOGIC_CHAINS_PROMPT
            user_prompt = prompt_template.format(
                query=query,
                topic=topic or query,
                search_results=search_results
            )
        else:
            raise ValueError(f"Unknown extract_type: {extract_type}")

        messages = [{"role": "user", "content": user_prompt}]

        print(f"[{self.source_name}] Extracting {extract_type} with Haiku...")

        # Use higher token limit for logic_chains (more structured output)
        max_tokens = 3000 if extract_type == "logic_chains" else 1500

        try:
            response = call_claude_haiku(messages, temperature=0.0, max_tokens=max_tokens)
            print(f"[{self.source_name}] Raw LLM response:\n{response}")

            # Try to parse JSON from response
            # Handle markdown code blocks
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0].strip()
            else:
                json_str = response.strip()

            extracted = json.loads(json_str)
            return extracted

        except json.JSONDecodeError as e:
            print(f"[{self.source_name}] JSON parse error: {e}")
            return {
                "error": "Failed to parse LLM response",
                "raw_response": response
            }
        except Exception as e:
            print(f"[{self.source_name}] Extraction error: {e}")
            return {"error": str(e)}

    def search_and_extract(
        self,
        query: str,
        extract_type: str = "data_points",
        gap_category: str = None,
        missing_description: str = None
    ) -> Dict[str, Any]:
        """
        Search the web and extract structured data.

        Args:
            query: Search query (e.g., "USD JPY hedging cost 2026")
            extract_type: Type of extraction:
                - "data_points": Extract quantitative data (numbers, percentages, dates)
                - "announcements": Extract entity announcements (who, what, when)
                - "knowledge_gap": Fill a specific knowledge gap
            gap_category: (for knowledge_gap) Category of the gap being filled
            missing_description: (for knowledge_gap) What information is needed

        Returns:
            Dict containing:
            - query: Original query
            - extract_type: Type of extraction
            - timestamp: When search was performed
            - results_count: Number of search results
            - extracted: Extracted data (format depends on extract_type)
            - sources: List of source URLs
        """
        # Check cache first (include gap params in cache key for knowledge_gap type)
        cache_key_suffix = f":{gap_category}:{missing_description}" if extract_type == "knowledge_gap" else ""
        cached = self._get_from_cache(query + cache_key_suffix, extract_type)
        if cached:
            return cached

        # Perform search
        search_results = self._search(query)

        if not search_results:
            result = {
                "query": query,
                "extract_type": extract_type,
                "timestamp": datetime.now().isoformat(),
                "results_count": 0,
                "extracted": {"error": "No search results found"},
                "sources": []
            }
            return result

        # Format for LLM
        formatted_results = self._format_search_results(search_results)

        # Extract with LLM
        extracted = self._extract_with_llm(
            query,
            formatted_results,
            extract_type,
            gap_category=gap_category,
            missing_description=missing_description
        )

        # Build result
        result = {
            "query": query,
            "extract_type": extract_type,
            "timestamp": datetime.now().isoformat(),
            "results_count": len(search_results),
            "extracted": extracted,
            "sources": [r["url"] for r in search_results]
        }

        # Cache result (use same key suffix for knowledge_gap type)
        self._save_to_cache(query + cache_key_suffix, extract_type, result)

        return result

    def search_multiple(
        self,
        queries: List[str],
        extract_type: str = "data_points",
        delay_seconds: float = 1.0
    ) -> List[Dict[str, Any]]:
        """
        Search multiple queries with rate limiting.

        Args:
            queries: List of search queries
            extract_type: Type of extraction for all queries
            delay_seconds: Delay between searches to avoid rate limiting

        Returns:
            List of results (same order as queries)
        """
        results = []

        for i, query in enumerate(queries):
            print(f"[{self.source_name}] Processing query {i+1}/{len(queries)}: {query[:50]}...")

            result = self.search_and_extract(query, extract_type)
            results.append(result)

            # Rate limiting delay (skip for last query)
            if i < len(queries) - 1:
                time.sleep(delay_seconds)

        return results


    def _verify_evidence_quote(
        self,
        quote: str,
        search_results: List[Dict[str, str]]
    ) -> bool:
        """
        Verify that an evidence quote actually appears in source content.

        Args:
            quote: The evidence quote to verify
            search_results: Raw search results with content

        Returns:
            True if quote appears verbatim (or close match) in any source
        """
        if not quote or len(quote) < 20:
            return False

        # Normalize quote for comparison
        quote_normalized = quote.lower().strip()

        for result in search_results:
            content = result.get("content", "") + " " + result.get("snippet", "")
            content_normalized = content.lower()

            # Check for exact substring match
            if quote_normalized in content_normalized:
                return True

            # Check for fuzzy match (quote words appear in sequence)
            quote_words = quote_normalized.split()[:10]  # First 10 words
            if len(quote_words) >= 5:
                # Check if first 5 words appear in sequence
                first_words = " ".join(quote_words[:5])
                if first_words in content_normalized:
                    return True

        return False

    def search_and_extract_chains(
        self,
        query: str,
        topic: str,
        min_tier: int = 2,
        verify_quotes: bool = True
    ) -> Dict[str, Any]:
        """
        Search trusted sources and extract logic chains.

        This is the main method for on-the-fly chain extraction from web sources.
        It filters to trusted domains before extraction and optionally verifies
        evidence quotes.

        Args:
            query: Search query
            topic: Topic for chain extraction (used in prompt)
            min_tier: Minimum source tier (1 = Tier 1 only, 2 = include Tier 2)
            verify_quotes: Whether to verify evidence quotes appear in sources

        Returns:
            Dict containing:
            - query: Original query
            - topic: Topic used for extraction
            - chains: List of extracted logic chains
            - trusted_sources_count: Number of trusted sources found
            - filtered_sources: List of trusted source URLs
            - all_sources: List of all source URLs (before filtering)
            - verification_results: Quote verification status per chain
        """
        print(f"[{self.source_name}] Searching for logic chains on: {query[:50]}...")

        # Perform search
        search_results = self._search(query)

        if not search_results:
            return {
                "query": query,
                "topic": topic,
                "chains": [],
                "trusted_sources_count": 0,
                "filtered_sources": [],
                "all_sources": [],
                "error": "No search results found"
            }

        all_sources = [r["url"] for r in search_results]

        # Filter to trusted sources
        trusted_results = filter_to_trusted_sources(search_results, min_tier)

        if not trusted_results:
            print(f"[{self.source_name}] No trusted sources found in {len(search_results)} results")
            return {
                "query": query,
                "topic": topic,
                "chains": [],
                "trusted_sources_count": 0,
                "filtered_sources": [],
                "all_sources": all_sources,
                "warning": "No trusted sources found"
            }

        filtered_sources = [r["url"] for r in trusted_results]
        print(f"[{self.source_name}] Found {len(trusted_results)} trusted sources from {len(search_results)} total")

        # Format trusted results for LLM
        formatted_results = self._format_search_results(trusted_results)

        # Extract logic chains
        extracted = self._extract_with_llm(
            query,
            formatted_results,
            extract_type="logic_chains",
            topic=topic
        )

        chains = extracted.get("chains", [])

        # Verify evidence quotes if requested
        verification_results = []
        if verify_quotes and chains:
            for i, chain in enumerate(chains):
                quote = chain.get("evidence_quote", "")
                is_verified = self._verify_evidence_quote(quote, trusted_results)
                verification_results.append({
                    "chain_index": i,
                    "quote_verified": is_verified,
                    "quote_preview": quote[:50] + "..." if len(quote) > 50 else quote
                })

                if not is_verified:
                    print(f"[{self.source_name}] Warning: Quote not verified for chain {i}")
                    # Mark chain as unverified but don't remove it
                    chain["quote_verified"] = False
                else:
                    chain["quote_verified"] = True

        return {
            "query": query,
            "topic": topic,
            "chains": chains,
            "summary": extracted.get("summary", ""),
            "chain_count": len(chains),
            "trusted_sources_count": len(trusted_results),
            "filtered_sources": filtered_sources,
            "all_sources": all_sources,
            "verification_results": verification_results,
            "source_tier": min_tier
        }


# Convenience functions for direct use
def search_data_points(query: str) -> Dict[str, Any]:
    """Search for quantitative data points."""
    adapter = WebSearchAdapter()
    return adapter.search_and_extract(query, extract_type="data_points")


def search_announcements(query: str) -> Dict[str, Any]:
    """Search for entity announcements."""
    adapter = WebSearchAdapter()
    return adapter.search_and_extract(query, extract_type="announcements")
