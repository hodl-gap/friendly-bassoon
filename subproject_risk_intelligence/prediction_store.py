"""Append-only prediction ledger for scoreable claims.

Extracts predictions from prospective output and stores them in
data/predictions.json with check_date for future scoring.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List

DATA_DIR = Path(__file__).parent / "data"
PREDICTIONS_FILE = DATA_DIR / "predictions.json"


def store_predictions(insight_output: Dict[str, Any], query: str, run_id: str) -> List[Dict]:
    """Extract predictions from scenario output and append to ledger.

    Returns list of predictions stored.
    """
    scenarios = insight_output.get("scenarios", [])
    if not scenarios:
        return []

    predictions = []
    now = datetime.now()

    for scenario in scenarios:
        scenario_title = scenario.get("title", "Unknown")
        falsification = scenario.get("falsification", "")

        for pred in scenario.get("predictions", []):
            variable = pred.get("variable", "")
            timeframe_days = pred.get("timeframe_days", 30)
            if not variable:
                continue

            pred_id = f"{run_id}_{variable}_{scenario_title[:20]}".replace(" ", "_").lower()
            predictions.append({
                "prediction_id": pred_id,
                "query": query[:200],
                "scenario": scenario_title,
                "scenario_analog_count": scenario.get("analog_count"),
                "variable": variable,
                "direction": pred.get("direction", "neutral"),
                "magnitude_low": pred.get("magnitude_low"),
                "magnitude_high": pred.get("magnitude_high"),
                "timeframe_days": timeframe_days,
                "falsification": falsification,
                "created_at": now.isoformat(),
                "check_date": (now + timedelta(days=timeframe_days)).isoformat(),
                "actual_outcome": None,
                "score": None,
            })

    if predictions:
        _append_to_ledger(predictions)
        print(f"[Prediction Store] Stored {len(predictions)} predictions (check dates: "
              f"{predictions[0]['check_date'][:10]} to {predictions[-1]['check_date'][:10]})")

    return predictions


def _append_to_ledger(predictions: List[Dict]):
    """Append predictions to the JSON ledger file."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    existing = []
    if PREDICTIONS_FILE.exists():
        try:
            existing = json.loads(PREDICTIONS_FILE.read_text())
        except (json.JSONDecodeError, IOError):
            existing = []

    existing.extend(predictions)
    PREDICTIONS_FILE.write_text(json.dumps(existing, indent=2, default=str))


def load_predictions() -> List[Dict]:
    """Load all predictions from the ledger."""
    if not PREDICTIONS_FILE.exists():
        return []
    try:
        return json.loads(PREDICTIONS_FILE.read_text())
    except (json.JSONDecodeError, IOError):
        return []
