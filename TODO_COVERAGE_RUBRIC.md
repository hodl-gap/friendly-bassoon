# Coverage Assessment Rubric — Upgraded (2026-02-25)

## What Changed

The retrieval agent's `assess_coverage()` was upgraded from a simple 3-tier rubric (chain count + counter-argument) to a **6-flag checklist** that covers the categories the agent can actually act on.

## Checklist Flags

| Flag | What it checks | Agent action if false |
|------|---------------|----------------------|
| `has_causal_chains` | >=2 independent A->B->C->impact chains | Search Pinecone, extract web chains |
| `has_counter_argument` | Opposing view or risk factor present | web_search for contrarian views |
| `has_monitoring_thresholds` | Analyst targets, key levels, intervention thresholds | web_search for targets/levels |
| `has_event_calendar` | Upcoming dated events (meetings, decisions) | web_search for event dates |
| `has_mechanism_conditions` | Preconditions for causal mechanisms specified | web_search for preconditions |
| `has_exit_criteria` | Thesis invalidation conditions specified | web_search for exit conditions |

## Rating Rules

- **INSUFFICIENT**: `has_causal_chains=false` — keep searching
- **ADEQUATE**: `has_causal_chains=true` — proceed to synthesis (even if other flags false)
- **COMPLETE**: all flags true

## What Was NOT Added (intentionally)

Two gap categories from `knowledge_gap_prompts.py` were excluded because the retrieval agent lacks tools to address them:

- **historical_precedent_depth** — requires `historical_analog` fill method (Phase 3 fetches price data for analog periods)
- **quantified_relationships** — requires `data_fetch` fill method (Phase 2 computes correlations from FRED/Yahoo)

These remain handled by the post-agent gap detection (`detect_knowledge_gaps()`) which has access to specialized fill methods.

## Two-Stage Design (preserved)

```
Retrieval Agent loop (max 5 iters):
  search → assess_coverage() [6-flag checklist] → targeted search or synthesize

Post-agent:
  detect_knowledge_gaps() [7-category rubric] → fill gaps (incl. data_fetch, historical_analog) → resynthesis
```

The gap detector still runs as a safety net. It catches:
1. Gaps the agent missed despite the checklist
2. Categories the agent can't address (quantified_relationships, historical_precedent_depth)
3. Post-synthesis evaluation (gap detector sees the synthesized output, not raw material)

## Files Modified

- `retrieval_agent_prompts.py` — COVERAGE_ASSESSMENT_PROMPT (checklist), RETRIEVAL_AGENT_SYSTEM_PROMPT (flag-based routing)
- `retrieval_agent_tools.py` — handle_assess_coverage() (parse + log checklist)
