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

import anthropic

from .historical_event_prompts import (
    GAP_DETECTION_PROMPT,
    get_instrument_mapping_prompt,
    DATE_EXTRACTION_PROMPT,
    MULTI_ANALOG_DETECTION_PROMPT,
    MULTI_ANALOG_TOOL,
    format_logic_chains_for_prompt
)
from .asset_configs import get_asset_config
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

    # Use LLM for detailed analysis via tool_use
    extrapolation_note = topic_coverage.get("extrapolation_note", "(None)")

    prompt = GAP_DETECTION_PROMPT.format(
        query=query,
        synthesis=synthesis[:3000],  # Truncate to save tokens
        extrapolation_note=extrapolation_note
    )

    gap_detection_tool = {
        "name": "detect_gap",
        "description": "Report whether a historical event data gap was detected in the query.",
        "input_schema": {
            "type": "object",
            "properties": {
                "gap_detected": {
                    "type": "boolean",
                    "description": "Whether a historical event gap was detected"
                },
                "event_description": {
                    "type": ["string", "null"],
                    "description": "Brief description of the historical event, or null if no gap"
                },
                "date_search_query": {
                    "type": ["string", "null"],
                    "description": "Search query to find exact dates for the event, or null"
                },
                "reasoning": {
                    "type": "string",
                    "description": "One sentence explaining why gap was detected or not"
                }
            },
            "required": ["gap_detected", "reasoning"]
        }
    }

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            temperature=0.0,
            tools=[gap_detection_tool],
            tool_choice={"type": "tool", "name": "detect_gap"},
            messages=[{"role": "user", "content": prompt}]
        )

        # Log token usage
        try:
            from shared.run_logger import log_llm_call
            log_llm_call("claude-haiku-4-5-20251001", response.usage.input_tokens, response.usage.output_tokens)
        except Exception:
            pass

        # Extract tool_use result from response
        result = None
        for block in response.content:
            if block.type == "tool_use" and block.name == "detect_gap":
                result = block.input
                break

        if result:
            print(f"[Historical Event] Gap detection response (tool_use): {result}")
            return {
                "gap_detected": result.get("gap_detected", False),
                "event_description": result.get("event_description"),
                "date_search_query": result.get("date_search_query"),
                "reasoning": result.get("reasoning", "")
            }

        # Fallback: try parsing text response as JSON (old behavior)
        print("[Historical Event] No tool_use block found, falling back to text parsing")
        for block in response.content:
            if block.type == "text":
                json_str = block.text.strip()
                if "```json" in json_str:
                    json_str = json_str.split("```json")[1].split("```")[0].strip()
                elif "```" in json_str:
                    json_str = json_str.split("```")[1].split("```")[0].strip()
                fallback_result = json.loads(json_str)
                print(f"[Historical Event] Gap detection response (fallback): {fallback_result}")
                return {
                    "gap_detected": fallback_result.get("gap_detected", False),
                    "event_description": fallback_result.get("event_description"),
                    "date_search_query": fallback_result.get("date_search_query"),
                    "reasoning": fallback_result.get("reasoning", "")
                }

        return {
            "gap_detected": False,
            "event_description": None,
            "date_search_query": None,
            "reasoning": "No valid response from LLM"
        }

    except json.JSONDecodeError as e:
        print(f"[Historical Event] JSON parse error in fallback: {e}")
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
    logic_chains: list,
    asset_class: str = "btc"
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
        asset_class: Asset class for default instrument fallback

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

    prompt = get_instrument_mapping_prompt(asset_class).format(
        event_description=event_description,
        query=query,
        synthesis=synthesis[:3000],
        logic_chains=formatted_chains
    )

    instrument_mapping_tool = {
        "name": "identify_instruments",
        "description": "Report the financial instruments relevant to the historical event.",
        "input_schema": {
            "type": "object",
            "properties": {
                "instruments": {
                    "type": "array",
                    "description": "List of instruments relevant to the event",
                    "items": {
                        "type": "object",
                        "properties": {
                            "ticker": {
                                "type": "string",
                                "description": "Yahoo Finance or FRED ticker symbol"
                            },
                            "source": {
                                "type": "string",
                                "enum": ["Yahoo", "FRED"],
                                "description": "Data source for the instrument"
                            },
                            "role": {
                                "type": "string",
                                "description": "Brief description of the instrument's role in the event"
                            }
                        },
                        "required": ["ticker", "source", "role"]
                    }
                }
            },
            "required": ["instruments"]
        }
    }

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            temperature=0.0,
            tools=[instrument_mapping_tool],
            tool_choice={"type": "tool", "name": "identify_instruments"},
            messages=[{"role": "user", "content": prompt}]
        )

        # Log token usage
        try:
            from shared.run_logger import log_llm_call
            log_llm_call("claude-haiku-4-5-20251001", response.usage.input_tokens, response.usage.output_tokens)
        except Exception:
            pass

        # Extract tool_use result from response
        result = None
        for block in response.content:
            if block.type == "tool_use" and block.name == "identify_instruments":
                result = block.input
                break

        if result:
            print(f"[Historical Event] Instrument mapping response (tool_use): {result}")
            instruments = result.get("instruments", [])
        else:
            # Fallback: try parsing text response as JSON (old behavior)
            print("[Historical Event] No tool_use block found, falling back to text parsing")
            instruments = []
            for block in response.content:
                if block.type == "text":
                    json_str = block.text.strip()
                    if "```json" in json_str:
                        json_str = json_str.split("```json")[1].split("```")[0].strip()
                    elif "```" in json_str:
                        json_str = json_str.split("```")[1].split("```")[0].strip()
                    fallback_result = json.loads(json_str)
                    print(f"[Historical Event] Instrument mapping response (fallback): {fallback_result}")
                    instruments = fallback_result.get("instruments", [])
                    break

        # Enforce max instruments limit
        if len(instruments) > config.MAX_INSTRUMENTS_PER_EVENT:
            instruments = instruments[:config.MAX_INSTRUMENTS_PER_EVENT]

        # Ensure target asset is always included
        cfg = get_asset_config(asset_class)
        target_ticker = cfg["ticker"]
        has_target = any(
            i.get("ticker", "").upper() == target_ticker.upper()
            for i in instruments
        )
        if not has_target:
            instruments.append(cfg["default_instruments"][0])

        return instruments

    except json.JSONDecodeError as e:
        print(f"[Historical Event] Instrument JSON parse error in fallback: {e}")
        return get_asset_config(asset_class)["default_instruments"]
    except Exception as e:
        print(f"[Historical Event] Instrument identification error: {e}")
        return [get_asset_config(asset_class)["default_instruments"][0]]


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

    # Extract dates using LLM via tool_use
    prompt = DATE_EXTRACTION_PROMPT.format(
        event_description=event_description,
        search_results=formatted_results
    )

    date_extraction_tool = {
        "name": "extract_dates",
        "description": "Report the date range for a historical market event.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Start date of the event in YYYY-MM-DD format"
                },
                "end_date": {
                    "type": "string",
                    "description": "End date of the event in YYYY-MM-DD format"
                },
                "peak_date": {
                    "type": ["string", "null"],
                    "description": "Peak stress date in YYYY-MM-DD format, or null if unclear"
                },
                "confidence": {
                    "type": "string",
                    "enum": ["high", "medium", "low"],
                    "description": "Confidence level of the date extraction"
                },
                "reasoning": {
                    "type": "string",
                    "description": "Brief explanation of date selection"
                }
            },
            "required": ["start_date", "end_date", "confidence"]
        }
    }

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            temperature=0.0,
            tools=[date_extraction_tool],
            tool_choice={"type": "tool", "name": "extract_dates"},
            messages=[{"role": "user", "content": prompt}]
        )

        # Log token usage
        try:
            from shared.run_logger import log_llm_call
            log_llm_call("claude-haiku-4-5-20251001", response.usage.input_tokens, response.usage.output_tokens)
        except Exception:
            pass

        # Extract tool_use result from response
        result = None
        for block in response.content:
            if block.type == "tool_use" and block.name == "extract_dates":
                result = block.input
                break

        if not result:
            # Fallback: try parsing text response as JSON (old behavior)
            print("[Historical Event] No tool_use block found, falling back to text parsing")
            for block in response.content:
                if block.type == "text":
                    json_str = block.text.strip()
                    if "```json" in json_str:
                        json_str = json_str.split("```json")[1].split("```")[0].strip()
                    elif "```" in json_str:
                        json_str = json_str.split("```")[1].split("```")[0].strip()
                    result = json.loads(json_str)
                    print(f"[Historical Event] Date extraction response (fallback): {result}")
                    break

        if not result:
            return _fallback_date_range(event_description)

        print(f"[Historical Event] Date extraction response (tool_use): {result}")

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
        print(f"[Historical Event] Date JSON parse error in fallback: {e}")
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


def detect_historical_analogs(
    query: str,
    synthesis: str,
    logic_chains: list,
    max_analogs: int = 5,
    relevance_threshold: float = 0.5
) -> List[Dict[str, Any]]:
    """
    Detect up to N historical analogs for the current query.

    Uses Haiku + tool_use to find analogous historical events
    based on shared causal mechanisms.

    Args:
        query: User's original query
        synthesis: Retrieved synthesis text
        logic_chains: Logic chains from retrieval
        max_analogs: Maximum analogs to return
        relevance_threshold: Minimum relevance score

    Returns:
        List of analog dicts: [{event_description, year, relevance_score,
                                date_search_query, key_mechanism}]
    """
    formatted_chains = format_logic_chains_for_prompt(logic_chains)

    prompt = MULTI_ANALOG_DETECTION_PROMPT.format(
        query=query,
        synthesis=synthesis[:3000],
        logic_chains=formatted_chains
    )

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1000,
            temperature=0.0,
            tools=[MULTI_ANALOG_TOOL],
            tool_choice={"type": "tool", "name": "detect_analogs"},
            messages=[{"role": "user", "content": prompt}]
        )

        # Log token usage
        try:
            from shared.run_logger import log_llm_call
            log_llm_call("claude-haiku-4-5-20251001", response.usage.input_tokens, response.usage.output_tokens)
        except Exception:
            pass

        # Extract tool_use result
        result = None
        for block in response.content:
            if block.type == "tool_use" and block.name == "detect_analogs":
                result = block.input
                break

        if not result:
            print("[Historical Analogs] No tool_use block in response")
            return []

        analogs = result.get("analogs", [])

        # Filter by relevance threshold and limit
        filtered = [
            a for a in analogs
            if a.get("relevance_score", 0) >= relevance_threshold
        ]
        filtered.sort(key=lambda a: a.get("relevance_score", 0), reverse=True)
        filtered = filtered[:max_analogs]

        print(f"[Historical Analogs] Found {len(filtered)} analogs (from {len(analogs)} candidates)")
        for a in filtered:
            print(f"  - {a.get('event_description', '?')} ({a.get('year', '?')}, relevance: {a.get('relevance_score', 0):.2f})")

        return filtered

    except Exception as e:
        print(f"[Historical Analogs] Detection error: {e}")
        return []
