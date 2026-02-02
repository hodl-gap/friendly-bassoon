"""
Integration Module

Wires Variable Mapper output to Data Collection adapters.
Provides a unified interface for the BTC Intelligence subproject to:
1. Run Variable Mapper on retriever synthesis
2. Fetch data for mapped variables via appropriate adapters
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

# Add subprojects to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "subproject_variable_mapper"))
sys.path.insert(0, str(PROJECT_ROOT / "subproject_data_collection"))

from .variable_resolver import resolve_variable


def map_and_fetch_variables(
    synthesis: str,
    logic_chains: List[Dict[str, Any]] = None,
    temporal_context: Dict[str, Any] = None,
    lookback_days: int = 45
) -> Dict[str, Any]:
    """
    Map variables from synthesis text and fetch their current data.

    This is the main integration point between:
    - Variable Mapper: extracts and normalizes variables from text
    - Data Collection: fetches data via appropriate adapters (FRED, Yahoo, etc.)

    Args:
        synthesis: Synthesis text from database_retriever
        logic_chains: Optional structured logic_chains from retriever (for efficient extraction)
        temporal_context: Optional temporal context from retriever
        lookback_days: Days of historical data to fetch (default: 45)

    Returns:
        Dict with:
        - mapped_variables: List of variables with their data source info
        - fetched_data: Dict of variable_name -> fetched data with history
        - unmapped_variables: List of variables that couldn't be mapped
        - errors: List of fetch errors
    """
    result = {
        "mapped_variables": [],
        "fetched_data": {},
        "unmapped_variables": [],
        "errors": []
    }

    # Step 1: Run Variable Mapper
    try:
        from variable_mapper_orchestrator import run_variable_mapper
        mapper_result = run_variable_mapper(
            synthesis,
            data_temporal_context=temporal_context or {}
        )
        extracted_vars = mapper_result.get("normalized_variables", [])
        unmapped = mapper_result.get("unmapped_variables", [])
        result["unmapped_variables"] = unmapped
    except ImportError as e:
        print(f"[integration] Variable Mapper not available: {e}")
        # Fall back to extracting from logic_chains structure if available
        extracted_vars = _extract_from_logic_chains(logic_chains) if logic_chains else []
    except Exception as e:
        print(f"[integration] Variable Mapper error: {e}")
        result["errors"].append(f"Variable Mapper failed: {e}")
        extracted_vars = _extract_from_logic_chains(logic_chains) if logic_chains else []

    # Step 2: Resolve each variable to its data source
    variables_to_fetch = []
    for var in extracted_vars:
        var_name = var.get("normalized_name", var.get("name", ""))
        if not var_name:
            continue

        resolution = resolve_variable(var_name)
        if resolution:
            var_info = {
                "name": var_name,
                "raw_name": var.get("raw_name", var_name),
                "source": resolution["source"],
                "series_id": resolution["series_id"],
                "data_id": resolution["data_id"],
                "metadata": resolution.get("metadata", {})
            }
            variables_to_fetch.append(var_info)
            result["mapped_variables"].append(var_info)
        else:
            if var_name not in result["unmapped_variables"]:
                result["unmapped_variables"].append(var_name)

    # Step 3: Fetch data for each mapped variable
    end_date = datetime.now()
    start_date = end_date - timedelta(days=lookback_days)

    for var_info in variables_to_fetch:
        var_name = var_info["name"]
        source = var_info["source"]
        series_id = var_info["series_id"]

        try:
            data = _fetch_data(source, series_id, start_date, end_date)
            if data:
                result["fetched_data"][var_name] = data
                print(f"[integration] Fetched {var_name} from {source}: {len(data.get('data', []))} points")
        except Exception as e:
            error_msg = f"Failed to fetch {var_name} ({source}:{series_id}): {e}"
            print(f"[integration] {error_msg}")
            result["errors"].append(error_msg)

    return result


def _extract_from_logic_chains(logic_chains: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """
    Extract variable names from structured logic_chains.

    This is a fallback when Variable Mapper is not available.
    Extracts cause_normalized and effect_normalized from chain steps.

    Args:
        logic_chains: List of logic chain dicts with steps

    Returns:
        List of variable dicts with name field
    """
    variables = []
    seen = set()

    for chain in (logic_chains or []):
        steps = chain.get("steps", [])
        if not steps:
            # Try legacy format
            steps = chain.get("logic_chain", {}).get("steps", [])

        for step in steps:
            cause_norm = step.get("cause_normalized", "")
            effect_norm = step.get("effect_normalized", "")

            if cause_norm and cause_norm not in seen:
                variables.append({"name": cause_norm, "raw_name": step.get("cause", cause_norm)})
                seen.add(cause_norm)

            if effect_norm and effect_norm not in seen:
                variables.append({"name": effect_norm, "raw_name": step.get("effect", effect_norm)})
                seen.add(effect_norm)

    return variables


def _fetch_data(
    source: str,
    series_id: str,
    start_date: datetime,
    end_date: datetime
) -> Optional[Dict[str, Any]]:
    """
    Fetch data using the appropriate adapter.

    Args:
        source: Data source name (FRED, Yahoo, etc.)
        series_id: Series identifier
        start_date: Start date
        end_date: End date

    Returns:
        Dict with data, metadata, etc. or None on failure
    """
    source_upper = source.upper()

    if source_upper == "FRED":
        try:
            from adapters.fred_adapter import FREDAdapter
            adapter = FREDAdapter()
            return adapter.fetch(series_id, start_date, end_date)
        except ImportError:
            print("[integration] FRED adapter not available, using fallback")
            return _fetch_fred_fallback(series_id, start_date, end_date)

    elif source_upper == "YAHOO":
        try:
            from adapters.yahoo_adapter import YahooAdapter
            adapter = YahooAdapter()
            return adapter.fetch(series_id, start_date, end_date)
        except ImportError:
            print("[integration] Yahoo adapter not available, using fallback")
            return _fetch_yahoo_fallback(series_id, start_date, end_date)

    else:
        print(f"[integration] Unknown source: {source}, skipping")
        return None


def _fetch_fred_fallback(
    series_id: str,
    start_date: datetime,
    end_date: datetime
) -> Optional[Dict[str, Any]]:
    """
    Fallback FRED fetcher using requests directly.
    Used when the Data Collection adapter is not available.
    """
    import os
    import requests
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.getenv("FRED_API_KEY", "")

    if not api_key:
        print("[integration] No FRED API key configured")
        return None

    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": start_date.strftime("%Y-%m-%d"),
        "observation_end": end_date.strftime("%Y-%m-%d"),
        "sort_order": "asc"
    }

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        if data.get("observations"):
            history = []
            for obs in data["observations"]:
                if obs["value"] != ".":
                    history.append((obs["date"], float(obs["value"])))

            if history:
                return {
                    "data": history,
                    "source": "FRED",
                    "series_id": series_id,
                    "start_date": start_date.strftime("%Y-%m-%d"),
                    "end_date": end_date.strftime("%Y-%m-%d"),
                    "data_points": len(history)
                }
    except Exception as e:
        print(f"[integration] FRED fallback error: {e}")

    return None


def _fetch_yahoo_fallback(
    series_id: str,
    start_date: datetime,
    end_date: datetime
) -> Optional[Dict[str, Any]]:
    """
    Fallback Yahoo fetcher using yfinance directly.
    Used when the Data Collection adapter is not available.
    """
    try:
        import yfinance as yf

        ticker = yf.Ticker(series_id)
        df = ticker.history(
            start=start_date.strftime("%Y-%m-%d"),
            end=end_date.strftime("%Y-%m-%d")
        )

        if not df.empty:
            history = []
            for date, row in df.iterrows():
                date_str = date.strftime("%Y-%m-%d")
                history.append((date_str, float(row["Close"])))

            if history:
                return {
                    "data": history,
                    "source": "Yahoo",
                    "series_id": series_id,
                    "start_date": start_date.strftime("%Y-%m-%d"),
                    "end_date": end_date.strftime("%Y-%m-%d"),
                    "data_points": len(history)
                }
    except ImportError:
        print("[integration] yfinance not installed")
    except Exception as e:
        print(f"[integration] Yahoo fallback error: {e}")

    return None


def get_adapter_for_source(source: str):
    """
    Get the appropriate data adapter for a source.

    Args:
        source: Data source name (FRED, Yahoo, etc.)

    Returns:
        Adapter instance or None if not available
    """
    source_upper = source.upper()

    if source_upper == "FRED":
        try:
            from adapters.fred_adapter import FREDAdapter
            return FREDAdapter()
        except ImportError:
            return None

    elif source_upper == "YAHOO":
        try:
            from adapters.yahoo_adapter import YahooAdapter
            return YahooAdapter()
        except ImportError:
            return None

    return None
