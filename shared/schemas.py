"""
Canonical schema definitions for the Macro Research Intelligence Platform.

These TypedDicts define the shared data structures flowing between subprojects.
All subprojects should import from here rather than defining their own.

Temperature conventions for LLM calls:
- 0.0: Deterministic (classification, gap detection, re-ranking, date extraction)
- 0.2: Structured extraction (variable extraction, chain extraction, claim parsing)
- 0.3: Analytical (impact analysis, synthesis)
- 0.7: Creative (generation tasks - none currently)
"""

from typing import TypedDict, List, Optional


class LogicChainStep(TypedDict, total=False):
    cause: str                    # Natural language
    cause_normalized: str         # Snake_case (e.g., "tga")
    effect: str                   # Natural language
    effect_normalized: str        # Snake_case (e.g., "bank_reserves")
    mechanism: str                # How cause leads to effect
    evidence_quote: str           # Verbatim source quote
    polarity: str                 # "BULLISH" | "BEARISH" | "NEUTRAL"


class LogicChain(TypedDict, total=False):
    steps: List[LogicChainStep]
    chain_summary: str            # Arrow notation: "tga -> bank_reserves -> ..."
    source: str                   # Institution name
    source_type: str              # "database" | "web" | "inferred"
    confidence_weight: float      # 1.0=DB, 0.7=web


class ConfidenceMetadata(TypedDict, total=False):
    score: float                  # 0.0-1.0
    chain_count: int              # Number of supporting chains
    source_diversity: int         # Unique institutions
    confidence_level: str         # "High" | "Medium" | "Low"
    strongest_chain: str          # Arrow notation of strongest
