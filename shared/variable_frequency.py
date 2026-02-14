"""
Variable Frequency Tracker

Tracks how often each normalized variable appears in logic chains over time.
Variables that appear frequently get promoted to anchor status.
Variables not seen for weeks get demoted.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional

from .theme_config import get_all_themes


class VariableFrequencyTracker:
    """Tracks variable frequency across chains for promotion/demotion."""

    def __init__(self):
        self.variables: Dict[str, Dict[str, Any]] = {}
        self.last_updated: Optional[str] = None

    @classmethod
    def load(cls, path: str | Path) -> "VariableFrequencyTracker":
        """Load tracker from disk."""
        tracker = cls()
        path = Path(path)

        if path.exists():
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                tracker.variables = data.get("variables", {})
                tracker.last_updated = data.get("last_updated")
            except Exception as e:
                print(f"[VariableFrequency] Error loading: {e}")

        return tracker

    def save(self, path: str | Path) -> None:
        """Save tracker to disk."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        self.last_updated = datetime.now().isoformat()
        data = {
            "variables": self.variables,
            "last_updated": self.last_updated,
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def record_variables(self, chain: Dict) -> None:
        """
        Extract all cause_normalized/effect_normalized from chain steps,
        increment chain_count, update last_seen, record source.

        Args:
            chain: Chain dict with logic_chain.steps and source_attribution
        """
        now = datetime.now().isoformat()
        source = chain.get("source_attribution", chain.get("source", "Unknown"))

        steps = chain.get("logic_chain", {}).get("steps", [])
        seen_vars = set()

        for step in steps:
            cause = step.get("cause_normalized", "")
            effect = step.get("effect_normalized", "")
            if cause:
                seen_vars.add(cause)
            if effect:
                seen_vars.add(effect)

        # Determine if variable is an anchor
        all_anchor_vars = set()
        anchor_theme_map = {}
        for theme_name, theme in get_all_themes().items():
            for var in theme["anchor_variables"]:
                all_anchor_vars.add(var)
                anchor_theme_map[var] = theme_name

        for var_name in seen_vars:
            if var_name not in self.variables:
                self.variables[var_name] = {
                    "first_seen": now,
                    "last_seen": now,
                    "chain_count": 0,
                    "sources": [],
                    "is_anchor": var_name in all_anchor_vars,
                    "anchor_theme": anchor_theme_map.get(var_name),
                }

            entry = self.variables[var_name]
            entry["chain_count"] += 1
            entry["last_seen"] = now
            if source and source not in entry["sources"]:
                entry["sources"].append(source)

    def get_candidates(
        self, min_chain_count: int = 5, min_sources: int = 2
    ) -> List[Dict[str, Any]]:
        """
        Get variables that meet promotion threshold but are NOT already anchors.

        Args:
            min_chain_count: Minimum number of chains containing this variable
            min_sources: Minimum number of distinct sources

        Returns:
            List of candidate dicts with name, chain_count, sources
        """
        candidates = []
        for name, entry in self.variables.items():
            if entry.get("is_anchor"):
                continue
            if (
                entry.get("chain_count", 0) >= min_chain_count
                and len(entry.get("sources", [])) >= min_sources
            ):
                candidates.append({
                    "name": name,
                    "chain_count": entry["chain_count"],
                    "sources": entry["sources"],
                    "first_seen": entry.get("first_seen"),
                    "last_seen": entry.get("last_seen"),
                })

        candidates.sort(key=lambda x: x["chain_count"], reverse=True)
        return candidates

    def get_stale(self, max_age_days: int = 30) -> List[Dict[str, Any]]:
        """
        Get anchor variables not seen in any chain for N days.

        Args:
            max_age_days: Maximum days since last seen before considered stale

        Returns:
            List of stale variable dicts
        """
        cutoff = datetime.now() - timedelta(days=max_age_days)
        stale = []

        for name, entry in self.variables.items():
            if not entry.get("is_anchor"):
                continue
            last_seen = entry.get("last_seen")
            if last_seen:
                try:
                    last_dt = datetime.fromisoformat(last_seen)
                    if last_dt < cutoff:
                        stale.append({
                            "name": name,
                            "last_seen": last_seen,
                            "chain_count": entry.get("chain_count", 0),
                            "anchor_theme": entry.get("anchor_theme"),
                        })
                except ValueError:
                    pass

        return stale

    def promote(self, variable_name: str, theme_name: str) -> None:
        """Promote a variable to anchor status in a theme."""
        if variable_name in self.variables:
            self.variables[variable_name]["is_anchor"] = True
            self.variables[variable_name]["anchor_theme"] = theme_name

    def demote(self, variable_name: str) -> None:
        """Remove a variable from anchor status."""
        if variable_name in self.variables:
            self.variables[variable_name]["is_anchor"] = False
            self.variables[variable_name]["anchor_theme"] = None
