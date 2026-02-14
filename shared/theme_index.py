"""
Theme Index

Index layer on top of the flat chain list that organizes chains by theme
and tracks per-theme state. Chains stay in btc_relationships.json —
this is a reference index only.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

from .theme_config import get_all_themes


class ThemeIndex:
    """Organizes logic chains by macro theme."""

    def __init__(self):
        self.themes: Dict[str, Dict[str, Any]] = {}
        self.metadata: Dict[str, Any] = {
            "last_full_refresh": None,
            "theme_count": 0,
        }

    @classmethod
    def load(cls, path: str | Path) -> "ThemeIndex":
        """Load theme index from disk."""
        index = cls()
        path = Path(path)

        if path.exists():
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                index.themes = data.get("themes", {})
                index.metadata = data.get("metadata", {})
            except Exception as e:
                print(f"[ThemeIndex] Error loading: {e}")

        # Ensure all themes from config exist in index
        for theme_name, theme_def in get_all_themes().items():
            if theme_name not in index.themes:
                index.themes[theme_name] = {
                    "anchor_variables": theme_def["anchor_variables"],
                    "query_template": theme_def["query_template"],
                    "chain_ids": [],
                    "active_chain_ids": [],
                    "last_refreshed": None,
                    "assessment": None,
                }

        index.metadata["theme_count"] = len(index.themes)
        return index

    def save(self, path: str | Path) -> None:
        """Save theme index to disk."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "themes": self.themes,
            "metadata": self.metadata,
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def assign_chain_to_themes(self, chain: Dict) -> List[str]:
        """
        Assign a chain to themes based on variable overlap.

        Deterministic set intersection: extract all cause_normalized/effect_normalized
        from chain steps, intersect with each theme's anchor variables.

        Args:
            chain: Chain dict with logic_chain.steps

        Returns:
            List of theme names this chain was assigned to
        """
        chain_vars = self._extract_chain_variables(chain)
        if not chain_vars:
            return []

        chain_id = chain.get("id", "")
        matched_themes = []

        for theme_name, theme_data in self.themes.items():
            anchor_set = set(theme_data.get("anchor_variables", []))
            if chain_vars & anchor_set:
                if chain_id and chain_id not in theme_data.get("chain_ids", []):
                    theme_data.setdefault("chain_ids", []).append(chain_id)
                matched_themes.append(theme_name)

        return matched_themes

    def rebuild_from_chains(self, chains: List[Dict]) -> None:
        """
        Full rebuild: iterate all chains, assign each to themes,
        populate chain_ids per theme.
        """
        # Clear existing chain_ids
        for theme_data in self.themes.values():
            theme_data["chain_ids"] = []
            theme_data["active_chain_ids"] = []

        for chain in chains:
            self.assign_chain_to_themes(chain)

        self.metadata["last_full_refresh"] = datetime.now().isoformat()

    def get_theme_chains(self, theme_name: str, all_chains: List[Dict]) -> List[Dict]:
        """Filter chain list by IDs in this theme."""
        if theme_name not in self.themes:
            return []

        chain_ids = set(self.themes[theme_name].get("chain_ids", []))
        return [c for c in all_chains if c.get("id") in chain_ids]

    def set_active_chains(self, theme_name: str, active_ids: List[str]) -> None:
        """Set the active chain IDs for a theme."""
        if theme_name in self.themes:
            self.themes[theme_name]["active_chain_ids"] = active_ids

    def set_assessment(self, theme_name: str, assessment: str) -> None:
        """Set the assessment text for a theme."""
        if theme_name in self.themes:
            self.themes[theme_name]["assessment"] = assessment
            self.themes[theme_name]["last_refreshed"] = datetime.now().isoformat()

    def get_theme_state(self, theme_name: str) -> Optional[Dict[str, Any]]:
        """Get full state for a theme."""
        if theme_name not in self.themes:
            return None
        return dict(self.themes[theme_name])

    def get_all_theme_states(self) -> Dict[str, Dict[str, Any]]:
        """Get states for all themes."""
        return {name: dict(data) for name, data in self.themes.items()}

    @staticmethod
    def _extract_chain_variables(chain: Dict) -> set:
        """Extract all normalized variables from a chain's steps."""
        variables = set()
        steps = chain.get("logic_chain", {}).get("steps", [])
        for step in steps:
            cause = step.get("cause_normalized", "")
            effect = step.get("effect_normalized", "")
            if cause:
                variables.add(cause)
            if effect:
                variables.add(effect)
        return variables
