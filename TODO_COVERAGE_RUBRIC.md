# TODO: Coverage Assessment Rubric — Too Shallow?

## Problem

The retrieval agent's `assess_coverage()` prompt (`retrieval_agent_prompts.py:31-61`) uses a **simplified 3-tier rubric** that only checks:

- **COMPLETE**: >=2 independent causal chains, counter-argument present, chains complete (A->B->C->impact)
- **ADEQUATE**: >=2 chains, most paths complete, minor gaps acceptable
- **INSUFFICIENT**: <2 chains, or major gaps, or no counter-argument

This runs inside the agent loop (up to 5 iterations) as a fast "should I keep searching?" gate.

## The Concern

The project already has a **rich 7-category rubric** in `knowledge_gap_prompts.py` (the gap detection prompt), which evaluates:

0. Topic coverage (is the actual question answered?)
1. Historical precedent depth (>=2 episodes with dates + outcomes?)
2. Quantified relationships (correlations, not just "X affects Y"?)
3. Monitoring thresholds (analyst targets, key levels?)
4. Event calendar (upcoming dates?)
5. Mechanism conditions (preconditions specified?)
6. Exit criteria (what would invalidate the thesis?)

But this rich rubric only runs **after** the agent finishes (post-agent gap detection). The agent's own coverage check doesn't look for historical precedents, quantified relationships, or any of these dimensions.

## Current Flow

```
Retrieval Agent loop (max 5 iters):
  search → assess_coverage() [simple: enough chains?] → search more or synthesize

Post-agent:
  detect_knowledge_gaps() [rich 7-category rubric] → fill gaps → resynthesis
```

## Design Question

Should the agent's in-loop coverage check be upgraded to evaluate more dimensions (historical precedents, quantified data, etc.) so the agent itself searches for those angles before exiting?

**Arguments for upgrading:**
- Agent can proactively search for historical precedents and quantitative data during its loop
- Gap filling after the agent exits is reactive (fixing what the agent missed) vs proactive (agent seeks it out)
- The rich rubric already exists — just need to port relevant parts into the agent's assessment

**Arguments against:**
- Coverage check runs on every iteration (up to 5x) — heavier prompt = more cost/latency
- The agent's search tools are limited (Pinecone + web search + web chains) — some gap categories (data_fetch, historical_analog) can't be filled by the retrieval agent anyway
- The two-stage design (fast gate + thorough audit) is intentional separation of concerns

## Files Involved

- `subproject_database_retriever/retrieval_agent_prompts.py` — COVERAGE_ASSESSMENT_PROMPT (lines 31-61)
- `subproject_database_retriever/knowledge_gap_prompts.py` — GAP_DETECTION_PROMPT (full 7-category rubric)
- `subproject_database_retriever/retrieval_agent_tools.py` — handle_assess_coverage() implementation
