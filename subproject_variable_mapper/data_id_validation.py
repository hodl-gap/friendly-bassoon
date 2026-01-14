"""
Data ID Validation Module

Validates discovered data IDs by pinging the actual APIs.
"""

import os
import requests
from typing import Optional


def validate_fred_series(series_id: str) -> Optional[bool]:
    """
    Verify FRED series exists and returns data.

    Args:
        series_id: FRED series ID (e.g., "WTREGEN", "FEDFUNDS")

    Returns:
        True if valid, False if invalid, None if cannot verify (no API key)
    """
    api_key = os.getenv("FRED_API_KEY")
    if not api_key:
        print(f"[validation] WARNING: No FRED_API_KEY, skipping validation for {series_id}")
        return None

    url = f"https://api.stlouisfed.org/fred/series?series_id={series_id}&api_key={api_key}&file_type=json"

    try:
        response = requests.get(url, timeout=10)
        data = response.json()

        # FRED returns "seriess" array if series exists
        if "seriess" in data and len(data["seriess"]) > 0:
            series_info = data["seriess"][0]
            print(f"[validation] FRED:{series_id} - Valid: {series_info.get('title', 'Unknown')}")
            return True
        else:
            print(f"[validation] FRED:{series_id} - Not found")
            return False

    except requests.exceptions.Timeout:
        print(f"[validation] FRED:{series_id} - Timeout")
        return None
    except Exception as e:
        print(f"[validation] FRED:{series_id} - Error: {e}")
        return False


def validate_world_bank_indicator(indicator_id: str) -> Optional[bool]:
    """
    Verify World Bank indicator exists.

    Args:
        indicator_id: World Bank indicator ID (e.g., "NY.GDP.MKTP.CD")

    Returns:
        True if valid, False if invalid, None if cannot verify
    """
    url = f"https://api.worldbank.org/v2/indicator/{indicator_id}?format=json"

    try:
        response = requests.get(url, timeout=10)
        data = response.json()

        # World Bank returns [metadata, [indicators]] format
        if len(data) > 1 and data[1] is not None and len(data[1]) > 0:
            indicator_info = data[1][0]
            print(f"[validation] WorldBank:{indicator_id} - Valid: {indicator_info.get('name', 'Unknown')}")
            return True
        else:
            print(f"[validation] WorldBank:{indicator_id} - Not found")
            return False

    except requests.exceptions.Timeout:
        print(f"[validation] WorldBank:{indicator_id} - Timeout")
        return None
    except Exception as e:
        print(f"[validation] WorldBank:{indicator_id} - Error: {e}")
        return False


def validate_bls_series(series_id: str) -> Optional[bool]:
    """
    Verify BLS series exists.

    Args:
        series_id: BLS series ID (e.g., "CUSR0000SA0")

    Returns:
        True if valid, False if invalid, None if cannot verify
    """
    api_key = os.getenv("BLS_API_KEY")

    # BLS allows unauthenticated requests but with lower limits
    headers = {"Content-type": "application/json"}

    payload = {
        "seriesid": [series_id],
        "startyear": "2024",
        "endyear": "2024"
    }

    if api_key:
        payload["registrationkey"] = api_key

    url = "https://api.bls.gov/publicAPI/v2/timeseries/data/"

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        data = response.json()

        if data.get("status") == "REQUEST_SUCCEEDED":
            results = data.get("Results", {}).get("series", [])
            if results and len(results) > 0:
                print(f"[validation] BLS:{series_id} - Valid")
                return True

        print(f"[validation] BLS:{series_id} - Not found or error: {data.get('message', '')}")
        return False

    except requests.exceptions.Timeout:
        print(f"[validation] BLS:{series_id} - Timeout")
        return None
    except Exception as e:
        print(f"[validation] BLS:{series_id} - Error: {e}")
        return False


def validate_api_mapping(mapping: dict) -> Optional[bool]:
    """
    Validate an API mapping based on its source.

    Args:
        mapping: Discovery result dict with 'type', 'source', 'data_id'

    Returns:
        True if valid, False if invalid, None if cannot verify
    """
    if mapping.get("type") != "api":
        print(f"[validation] Skipping non-API mapping: {mapping.get('type')}")
        return None

    source = mapping.get("source", "").upper()
    data_id = mapping.get("data_id", "")

    # Extract series ID from data_id format "SOURCE:SERIES_ID"
    if ":" in data_id:
        series_id = data_id.split(":", 1)[1]
    else:
        series_id = data_id

    if source == "FRED":
        return validate_fred_series(series_id)
    elif source == "WORLDBANK":
        return validate_world_bank_indicator(series_id)
    elif source == "BLS":
        return validate_bls_series(series_id)
    else:
        print(f"[validation] No validator for source: {source}")
        return None


# For standalone testing
if __name__ == "__main__":
    print("Testing FRED validation...")
    validate_fred_series("WTREGEN")  # TGA - should exist
    validate_fred_series("FEDFUNDS")  # Fed Funds - should exist
    validate_fred_series("INVALID_SERIES_XYZ")  # Should not exist

    print("\nTesting World Bank validation...")
    validate_world_bank_indicator("NY.GDP.MKTP.CD")  # GDP - should exist
    validate_world_bank_indicator("INVALID_INDICATOR")  # Should not exist

    print("\nTesting mapping validation...")
    validate_api_mapping({
        "type": "api",
        "source": "FRED",
        "data_id": "FRED:DGS10"
    })
