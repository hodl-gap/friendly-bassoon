"""
Chain Graph

Directed graph of causal chains built at query time.
Finds multi-hop causal paths from trigger variables to terminal effects,
grouped into reasoning tracks for prompt consumption.

Ephemeral (built fresh per query), dict-of-lists, no external deps.
"""

from typing import Dict, List, Any, Optional, Tuple


class ChainGraph:
    """Directed graph of causal chains built at query time."""

    def __init__(self):
        self.edges: Dict[str, List[Tuple[str, dict]]] = {}  # {cause_norm: [(effect_norm, metadata)]}
        self.reverse: Dict[str, List[Tuple[str, dict]]] = {}  # {effect_norm: [(cause_norm, metadata)]}
        self.variables: set = set()

    def add_chain(self, chain: dict, source: str) -> None:
        """Add a chain's steps as edges.

        Handles both {steps: [...]} and {logic_chain: {steps: [...]}} formats.
        """
        # Extract steps from either format
        steps = chain.get("steps", [])
        if not steps:
            lc = chain.get("logic_chain", {})
            if isinstance(lc, dict):
                steps = lc.get("steps", [])

        for step in steps:
            cause = step.get("cause_normalized", step.get("cause", ""))
            effect = step.get("effect_normalized", step.get("effect", ""))
            if not cause or not effect:
                continue

            cause = cause.lower().strip()
            effect = effect.lower().strip()

            mechanism = step.get("mechanism", "")
            metadata = {
                "mechanism": mechanism,
                "source": source,
                "chain_id": chain.get("id", ""),
            }

            self.variables.add(cause)
            self.variables.add(effect)

            self.edges.setdefault(cause, []).append((effect, metadata))
            self.reverse.setdefault(effect, []).append((cause, metadata))

    def add_chains_from_list(self, chains: list, source: str) -> None:
        """Add multiple chains."""
        for chain in chains:
            self.add_chain(chain, source)

    def find_paths(
        self, start: str, end: Optional[str] = None, max_depth: int = 6
    ) -> List[List[Tuple[str, dict]]]:
        """DFS with cycle detection.

        Returns all paths from start to end (or to terminal nodes if end=None).
        Each path is a list of (variable, edge_metadata) tuples.
        """
        start = start.lower().strip()
        if end:
            end = end.lower().strip()

        if start not in self.variables:
            return []

        paths = []
        # Each stack item: (current_node, path_so_far, visited_set)
        stack = [(start, [(start, {})], {start})]

        while stack:
            node, path, visited = stack.pop()

            neighbors = self.edges.get(node, [])

            if not neighbors or len(path) > max_depth:
                # Terminal node or max depth — record path if it has edges
                if len(path) > 1:
                    if end is None or path[-1][0] == end:
                        paths.append(path[:])
                continue

            found_unvisited = False
            for effect, meta in neighbors:
                if effect in visited:
                    continue
                found_unvisited = True
                new_visited = visited | {effect}
                new_path = path + [(effect, meta)]

                if end and effect == end:
                    paths.append(new_path)
                else:
                    stack.append((effect, new_path, new_visited))

            # If all neighbors visited, this is effectively terminal
            if not found_unvisited and len(path) > 1:
                if end is None:
                    paths.append(path[:])

        return paths

    def get_tracks(self, trigger: str, max_depth: int = 6) -> List[Dict[str, Any]]:
        """Group paths by terminal effect. Each track = independent reasoning line.

        Returns:
            [{"terminal_effect": str, "paths": [...], "path_count": int,
              "mechanisms": [...], "sources": [...]}]
        """
        paths = self.find_paths(trigger, max_depth=max_depth)
        if not paths:
            return []

        # Group by terminal variable
        groups: Dict[str, List] = {}
        for path in paths:
            terminal = path[-1][0]
            groups.setdefault(terminal, []).append(path)

        tracks = []
        for terminal, grouped_paths in groups.items():
            mechanisms = set()
            sources = set()
            for path in grouped_paths:
                for _, meta in path[1:]:
                    if meta.get("mechanism"):
                        mechanisms.add(meta["mechanism"])
                    if meta.get("source"):
                        sources.add(meta["source"])

            tracks.append({
                "terminal_effect": terminal,
                "paths": grouped_paths,
                "path_count": len(grouped_paths),
                "mechanisms": list(mechanisms),
                "sources": list(sources),
            })

        # Sort by path count descending (most-supported tracks first)
        tracks.sort(key=lambda t: t["path_count"], reverse=True)
        return tracks

    def get_trigger_variables(self, query_text: str) -> List[str]:
        """Find variables in graph whose name appears in the query, sorted by out-degree."""
        import re
        query_lower = query_text.lower()
        # Split query into tokens for matching, strip punctuation
        query_tokens = set(re.sub(r'[^\w\s]', ' ', query_lower).split())

        matches = []
        for var in self.variables:
            # Check if variable name (or its space-separated form) appears in query
            var_tokens = set(var.replace("_", " ").split())
            if var_tokens & query_tokens:
                out_degree = len(self.edges.get(var, []))
                matches.append((var, out_degree))

        # Sort by out-degree descending (most connected first)
        matches.sort(key=lambda x: x[1], reverse=True)
        return [var for var, _ in matches]

    def format_for_prompt(self, tracks: List[Dict[str, Any]], max_tracks: int = 5) -> str:
        """Format as '## MULTI-HOP CAUSAL PATHS' section for prompt."""
        if not tracks:
            return ""

        lines = ["## MULTI-HOP CAUSAL PATHS"]
        lines.append(f"({len(tracks)} reasoning tracks found)\n")

        for i, track in enumerate(tracks[:max_tracks], 1):
            terminal = track["terminal_effect"]
            path_count = track["path_count"]
            lines.append(f"### Track {i}: → {terminal} ({path_count} path{'s' if path_count > 1 else ''})")

            # Show up to 3 paths per track
            for j, path in enumerate(track["paths"][:3], 1):
                arrow_chain = " → ".join(node for node, _ in path)
                lines.append(f"  Path {j}: {arrow_chain}")

                # Show mechanisms along the path
                for node, meta in path[1:]:
                    if meta.get("mechanism"):
                        lines.append(f"    [{meta['source']}] {meta['mechanism']}")

            if track["path_count"] > 3:
                lines.append(f"  ... and {track['path_count'] - 3} more paths")

            lines.append("")

        return "\n".join(lines)

    def stats(self) -> Dict[str, int]:
        """Return graph statistics."""
        root_nodes = set(self.variables) - set(self.reverse.keys())
        terminal_nodes = set(self.variables) - set(self.edges.keys())
        edge_count = sum(len(v) for v in self.edges.values())

        return {
            "variables": len(self.variables),
            "edges": edge_count,
            "root_nodes": len(root_nodes),
            "terminal_nodes": len(terminal_nodes),
        }
