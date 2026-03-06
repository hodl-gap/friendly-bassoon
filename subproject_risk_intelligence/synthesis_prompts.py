"""Prompts for the synthesis self-check phase."""

VERIFICATION_PROMPT_RETROSPECTIVE = """You are a quality reviewer for macro research causal decompositions.

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

Check the CAUSAL DECOMPOSITION against the evidence:
1. Are ALL discovered causal mechanisms from the evidence addressed in tracks?
2. Is quantitative data cited per track (specific numbers, not vague ranges)?
3. Does each track's mechanism match the evidence (no invented causal links)?
4. Are there unsourced claims? Specific quantitative claims MUST have evidence above.
5. Is the cross-track synthesis coherent (does it explain how tracks interact)?

List any specific gaps. If none, respond with exactly "NO_GAPS".

If gaps exist, respond with a numbered list of specific missing items. Be concrete.
Prefix unsourced claims with "UNSOURCED:" for clear identification."""


VERIFICATION_PROMPT_PROSPECTIVE = """You are a quality reviewer for macro research scenario analyses.

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

Check the SCENARIO ANALYSIS against the evidence:
1. Does each scenario have a falsification criterion (not just a vague "if things change")?
2. Are predictions grounded in the base rate / forward return data?
3. Are magnitude ranges consistent with the historical data provided?
4. Does the monitoring dashboard cover the key distinguishing variables?
5. Are there unsourced quantitative claims? Specific numbers MUST have evidence above.
6. Is each scenario's analog basis referencing actual episodes from the evidence?

List any specific gaps. If none, respond with exactly "NO_GAPS".

If gaps exist, respond with a numbered list of specific missing items. Be concrete.
Prefix unsourced claims with "UNSOURCED:" for clear identification."""
