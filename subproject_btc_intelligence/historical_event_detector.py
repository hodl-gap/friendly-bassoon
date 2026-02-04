"""
Historical Event Detector Module

Detects when a user query references a historical event that requires actual
market data to answer properly, and identifies the relevant instruments.
"""

import re
import sys
import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

# Add parent directory for shared imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from models import call_claude_haiku
from .historical_event_prompts import (
    GAP_DETECTION_PROMPT,
    INSTRUMENT_MAPPING_PROMPT,
    DATE_EXTRACTION_PROMPT,
    format_logic_chains_for_prompt
)
from . import config


# Regex patterns for quick pre-filtering
TEMPORAL_PATTERNS = [
    r"what happened",
    r"during (the )?[a-z]+ \d{4}",
    r"in (january|february|march|april|may|june|july|august|september|october|november|december) \d{4}",
    r"(january|february|march|april|may|june|july|august|september|october|november|december) \d{4}",  # month year alone
    r"\d{4} (crash|correction|crisis|rally|event|intervention|tightening|easing|recession)",
    r"(crash|correction|crisis|rally|event|intervention|tightening|easing|recession) .* \d{4}",  # event ... year
    r"(last|previous|historical|past) .*(crash|correction|crisis|event)",
    r"compare.*(to|with).*\d{4}",  # compare ... to ... year (allow words between)
    r"like in \d{4}",
]


def _quick_temporal_check(query: str) -> bool:
    """Quick regex check for temporal keywords."""
    query_lower = query.lower()
    for pattern in TEMPORAL_PATTERNS:
        if re.search(pattern, query_lower):
            return True
    return False


def detect_historical_gap(
    query: str,
    topic_coverage: dict,
    synthesis: str
) -> Dict[str, Any]:
    """
    Detect if query references a historical event not covered by data.

    Uses quick regex check first, then LLM for detailed analysis.

    Args:
        query: User's original query
        topic_coverage: Topic coverage dict from retriever (may have extrapolation_note)
        synthesis: Retrieved synthesis text

    Returns:
        {
            "gap_detected": bool,
            "event_description": "August 2024 yen carry crash" or None,
            "date_search_query": "August 2024 yen carry trade crash exact date" or None,
            "reasoning": str
        }
    """
    if not config.ENABLE_HISTORICAL_EVENT_DETECTION:
        return {
            "gap_detected": False,
            "event_description": None,
            "date_search_query": None,
            "reasoning": "Historical event detection disabled"
        }

    # Quick regex pre-filter
    has_temporal_keywords = _quick_temporal_check(query)
    has_extrapolation_note = bool(topic_coverage.get("extrapolation_note"))

    # If no signals, skip LLM call
    if not has_temporal_keywords and not has_extrapolation_note:
        return {
            "gap_detected": False,
            "event_description": None,
            "date_search_query": None,
            "reasoning": "No temporal keywords or extrapolation detected"
        }

    # Use LLM for detailed analysis
    extrapolation_note = topic_coverage.get("extrapolation_note", "(None)")

    prompt = GAP_DETECTION_PROMPT.format(
        query=query,
        synthesis=synthesis[:3000],  # Truncate to save tokens
        extrapolation_note=extrapolation_note
    )

    messages = [{"role": "user", "content": prompt}]

    try:
        response = call_claude_haiku(messages, temperature=0.0, max_tokens=500)
        print(f"[Historical Event] Gap detection response: {response}")

        # Parse JSON response - handle markdown code blocks
        json_str = response.strip()
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0].strip()
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0].strip()

        result = json.loads(json_str)
        return {
            "gap_detected": result.get("gap_detected", False),
            "event_description": result.get("event_description"),
            "date_search_query": result.get("date_search_query"),
            "reasoning": result.get("reasoning", "")
        }

    except json.JSONDecodeError as e:
        print(f"[Historical Event] JSON parse error: {e}")
        return {
            "gap_detected": False,
            "event_description": None,
            "date_search_query": None,
            "reasoning": f"Parse error: {e}"
        }
    except Exception as e:
        print(f"[Historical Event] Detection error: {e}")
        return {
            "gap_detected": False,
            "event_description": None,
            "date_search_query": None,
            "reasoning": f"Error: {e}"
        }


def identify_instruments(
    event_description: str,
    query: str,
    synthesis: str,
    logic_chains: list
) -> List[Dict[str, str]]:
    """
    Identify instruments to fetch for a historical event using LLM.

    Uses the retrieved research context to determine which instruments
    are relevant for the historical event.

    Args:
        event_description: Brief description of the historical event
        query: User's original query
        synthesis: Retrieved synthesis text
        logic_chains: Logic chains from retrieval

    Returns:
        List of instrument dicts: [{"ticker": "USDJPY=X", "source": "Yahoo", "role": "..."}]
    """
    formatted_chains = format_logic_chains_for_prompt(logic_chains)

    # Debug: Show what context is being used for instrument identification
    # Per CLAUDE.md: LLM responses should be printed FULL (no truncation)
    print(f"[Historical Event] === SYNTHESIS PASSED TO INSTRUMENT MAPPING ===")
    print(synthesis)  # Full synthesis (LLM output from retriever Stage 2)
    print(f"[Historical Event] === END SYNTHESIS ===")
    print(f"[Historical Event] === LOGIC CHAINS PASSED ===")
    print(formatted_chains)
    print(f"[Historical Event] === END LOGIC CHAINS ===")

    prompt = INSTRUMENT_MAPPING_PROMPT.format(
        event_description=event_description,
        query=query,
        synthesis=synthesis[:3000],
        logic_chains=formatted_chains
    )

    messages = [{"role": "user", "content": prompt}]

    try:
        response = call_claude_haiku(messages, temperature=0.0, max_tokens=500)
        print(f"[Historical Event] Instrument mapping response: {response}")

        # Parse JSON response - handle markdown code blocks
        json_str = response.strip()
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0].strip()
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0].strip()

        result = json.loads(json_str)
        instruments = result.get("instruments", [])

        # Enforce max instruments limit
        if len(instruments) > config.MAX_INSTRUMENTS_PER_EVENT:
            instruments = instruments[:config.MAX_INSTRUMENTS_PER_EVENT]

        # Ensure BTC is always included for BTC impact analysis
        btc_tickers = ["BTC-USD", "BTC", "btc"]
        has_btc = any(
            i.get("ticker", "").upper() in [t.upper() for t in btc_tickers]
            for i in instruments
        )
        if not has_btc:
            instruments.append({
                "ticker": "BTC-USD",
                "source": "Yahoo",
                "role": "Bitcoin price"
            })

        return instruments

    except json.JSONDecodeError as e:
        print(f"[Historical Event] Instrument JSON parse error: {e}")
        # Return minimal default instruments
        return [
            {"ticker": "BTC-USD", "source": "Yahoo", "role": "Bitcoin price"},
            {"ticker": "^VIX", "source": "Yahoo", "role": "Volatility index"}
        ]
    except Exception as e:
        print(f"[Historical Event] Instrument identification error: {e}")
        return [{"ticker": "BTC-USD", "source": "Yahoo", "role": "Bitcoin price"}]


def get_date_range(
    event_description: str,
    date_search_query: str
) -> Dict[str, Any]:
    """
    Determine the date range for a historical event using web search.

    Args:
        event_description: Brief description of the event
        date_search_query: Search query to find exact dates

    Returns:
        {
            "start_date": "YYYY-MM-DD",
            "end_date": "YYYY-MM-DD",
            "peak_date": "YYYY-MM-DD" or None,
            "confidence": "high/medium/low"
        }
    """
    try:
        # Import web search adapter
        sys.path.insert(0, str(Path(__file__).parent.parent / "subproject_data_collection"))
        from adapters.web_search_adapter import WebSearchAdapter
    except ImportError:
        print("[Historical Event] WebSearchAdapter not available, using fallback")
        return _fallback_date_range(event_description)

    # Perform web search
    adapter = WebSearchAdapter(max_results=5)
    search_results = adapter._search_duckduckgo(date_search_query)

    if not search_results:
        print("[Historical Event] No search results for date query")
        return _fallback_date_range(event_description)

    # Format search results for LLM
    formatted_results = adapter._format_search_results(search_results)

    # Extract dates using LLM
    prompt = DATE_EXTRACTION_PROMPT.format(
        event_description=event_description,
        search_results=formatted_results
    )

    messages = [{"role": "user", "content": prompt}]

    try:
        response = call_claude_haiku(messages, temperature=0.0, max_tokens=300)
        print(f"[Historical Event] Date extraction response: {response}")

        result = json.loads(response.strip())

        # Validate dates
        start_date = result.get("start_date")
        end_date = result.get("end_date")

        if not start_date or not end_date:
            return _fallback_date_range(event_description)

        # Add buffer days
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        start_dt -= timedelta(days=config.HISTORICAL_DATE_BUFFER_DAYS)
        end_dt += timedelta(days=config.HISTORICAL_DATE_BUFFER_DAYS)

        return {
            "start_date": start_dt.strftime("%Y-%m-%d"),
            "end_date": end_dt.strftime("%Y-%m-%d"),
            "peak_date": result.get("peak_date"),
            "confidence": result.get("confidence", "medium")
        }

    except json.JSONDecodeError as e:
        print(f"[Historical Event] Date JSON parse error: {e}")
        return _fallback_date_range(event_description)
    except Exception as e:
        print(f"[Historical Event] Date extraction error: {e}")
        return _fallback_date_range(event_description)


def _fallback_date_range(event_description: str) -> Dict[str, Any]:
    """
    Fallback date range extraction using simple pattern matching.

    Args:
        event_description: Event description that may contain date hints

    Returns:
        Date range dict with approximate dates
    """
    # Try to extract year and month from description
    months = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12
    }

    description_lower = event_description.lower()

    # Look for "month year" pattern
    for month_name, month_num in months.items():
        if month_name in description_lower:
            # Find year
            year_match = re.search(r"20\d{2}", description_lower)
            if year_match:
                year = int(year_match.group())
                # Create date range for that month
                start_date = datetime(year, month_num, 1)
                # End of month + buffer
                if month_num == 12:
                    end_date = datetime(year + 1, 1, 15)
                else:
                    end_date = datetime(year, month_num + 1, 15)

                return {
                    "start_date": start_date.strftime("%Y-%m-%d"),
                    "end_date": end_date.strftime("%Y-%m-%d"),
                    "peak_date": None,
                    "confidence": "low"
                }

    # Look for just year
    year_match = re.search(r"20\d{2}", description_lower)
    if year_match:
        year = int(year_match.group())
        return {
            "start_date": f"{year}-01-01",
            "end_date": f"{year}-12-31",
            "peak_date": None,
            "confidence": "low"
        }

    # Default to last year if nothing found
    last_year = datetime.now().year - 1
    return {
        "start_date": f"{last_year}-01-01",
        "end_date": f"{last_year}-12-31",
        "peak_date": None,
        "confidence": "low"
    }
