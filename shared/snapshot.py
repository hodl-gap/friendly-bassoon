"""
State snapshot utility for capturing LangGraph state at node boundaries.

Writes JSON snapshots to logs/snapshots/{run_id}/{node_name}_{direction}.json
for use as raw material when building few-shot prompt examples.

Off by default. Enable via ENABLE_SNAPSHOTS env var or set programmatically.
"""

import json
import os
from datetime import datetime
from pathlib import Path

ENABLE_SNAPSHOTS = os.environ.get("ENABLE_SNAPSHOTS", "").lower() in ("1", "true", "yes")

_current_run_id = None
_SNAPSHOT_DIR = Path(__file__).parent.parent / "logs" / "snapshots"
_TRUNCATE_LIMIT = 2000


def start_run(run_id=None):
    """Set run ID for snapshot grouping. Called at pipeline start."""
    global _current_run_id
    _current_run_id = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")


def snapshot_state(node_name, state, direction="out"):
    """Dump state as JSON after a node runs.

    Args:
        node_name: Name of the graph node (e.g. "process_query")
        state: The state dict to snapshot
        direction: "in" or "out"
    """
    if not ENABLE_SNAPSHOTS:
        return

    global _current_run_id
    if _current_run_id is None:
        start_run()

    run_dir = _SNAPSHOT_DIR / f"run_{_current_run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)

    # Truncate long text fields for example-sized data
    cleaned = _truncate_values(dict(state))

    out_path = run_dir / f"{node_name}_{direction}.json"
    with open(out_path, "w") as f:
        json.dump(cleaned, f, indent=2, default=str)


def _truncate_values(obj):
    """Recursively truncate string values longer than _TRUNCATE_LIMIT."""
    if isinstance(obj, dict):
        return {k: _truncate_values(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_truncate_values(item) for item in obj]
    if isinstance(obj, str) and len(obj) > _TRUNCATE_LIMIT:
        return obj[:_TRUNCATE_LIMIT] + " [truncated]"
    return obj
