"""
Central model selection — change here, applies everywhere.

Subproject configs should import from here instead of defining model choices locally.
"""

# Structured extraction tasks (variable extraction, chain parsing, gap detection, re-ranking)
EXTRACTION_MODEL = "claude_haiku"

# Synthesis, impact analysis, answer generation
ANALYSIS_MODEL = "claude_sonnet"

# Re-ranking, classification
RERANK_MODEL = "claude_haiku"

# Fallback when primary fails
FALLBACK_MODEL = "claude_sonnet"

# Impact analysis (highest-leverage call — configurable between sonnet/opus)
IMPACT_ANALYSIS_MODEL = "claude_opus"
