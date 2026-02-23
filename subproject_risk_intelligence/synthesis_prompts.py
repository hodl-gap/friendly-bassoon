"""Prompts for the synthesis self-check phase."""

VERIFICATION_PROMPT = """You are a quality reviewer for macro research insight reports.

EVIDENCE AVAILABLE:
---
SYNTHESIS:
{synthesis}

CHAIN GRAPH (Multi-Hop Causal Paths):
{chain_graph_text}

HISTORICAL ANALOGS:
{historical_analogs_text}

CURRENT DATA:
{current_data_text}

CLAIM VALIDATION:
{claim_validation_text}
---

REPORT PRODUCED:
---
{insight_output_text}
---

Check the report against the evidence:
1. Are ALL discovered causal mechanisms from the evidence addressed in tracks?
2. Are historical precedents cited with quantified outcomes where available?
3. Are monitoring variables specified with thresholds (not just variable names)?
4. Is there at least one track addressing counter-arguments or alternative interpretations?
5. Are magnitude ranges and timing estimates provided for asset implications?

List any specific gaps. If none, respond with exactly "NO_GAPS".

If gaps exist, respond with a numbered list of specific missing items that should be added to the report. Be concrete — reference specific evidence from above that was not addressed."""
