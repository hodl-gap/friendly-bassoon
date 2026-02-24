# TODO: Temporal Sensitivity in Pipeline

## Problem

The pipeline does not distinguish between **causal evidence** and **forward projections** in its output. The LLM flattens past signals, concurrent triggers, and future predictions into a single undifferentiated set of "tracks" — all presented as causal explanations.

## Important Context: This Is NOT a Data Infrastructure Problem

The pipeline's primary use case is a trader asking about something happening **right now**. In production:
- Query time = event time = data fetch time. No temporal mismatch.
- Pinecone chunks are the latest research — exactly what you want
- Relationship store chains are all from the past — all valid context
- Current data anchoring to "now" is correct by definition

The temporal issue only manifests strongly in **retrospective case studies** (e.g., asking about a late-Jan event using a relationship store that contains Feb 20+ chains). This is a testing artifact, not a production bug. Building temporal data infrastructure (event date extraction, temporal filtering, `fetch_data_at_date()`) would be **overengineering** for a system whose purpose is to continuously analyze the latest research.

## What Actually Needs Fixing

### 1. LLM prompt: separate causes from projections
- The synthesis/insight prompt should instruct the LLM to distinguish between **"what caused this"** (causal tracks) and **"what happens next"** (forward outlook)
- Currently both are presented as equivalent "tracks" — e.g., Case 1 Track 3 bundles Fundstrat's "correction through May" and "Sell in May" seasonal pattern as a causal explanation for a late-Jan event
- Fix: prompt engineering in `impact_analysis_prompts.py` — add a rule like "Only include events/mechanisms that occurred before or concurrent with the event as causal tracks. Forward projections belong in a separate 'Outlook' section, not as causal tracks."

### 2. Relationship store contamination in retrospective analysis
- IEEPA tariff chains (discovered Feb 23 from Case 4) leaked into Case 1 analysis (late-Jan SaaS meltdown) via the chain graph
- In production this doesn't happen — all stored chains are from the past
- Low priority. If retrospective testing accuracy matters, could add a `discovered_at` filter when loading chains. But this is a testing concern, not a production one.

### 3. Missing fundamental mechanism (Hyperscaler CAPEX) — retrieval agent query coverage gap

#### Diagnosis History (3 iterations of misdiagnosis)
1. **Cross-language retrieval** — wrong. Korean chunks embed fine, cosine similarity isn't the bottleneck.
2. **Bearish interpretation absent from source material** — wrong. Telegram message #18329 (하나 Global ETF / GS, 2026-02-01) contains the exact bearish framing: "Capex 상향이 과거처럼 무조건 긍정적으로 반영되기보다는, 투자 대비 수익 가시성, 잉여현금흐름 압박, 그리고 투자 회수 시점에 대한 경계심을 동시에 자극" (CAPEX no longer unconditionally positive — ROI visibility, FCF pressure, payback timeline concerns). Pinecone vector ID: `8dacc3908d3d239b_0`, category: `data_opinion`, uploaded 2026-02-20. Extraction captured bearish logic chains correctly.
3. **Actual root cause: retrieval agent never queried for CAPEX.** The agent ran 5 Pinecone queries, all SaaS/software-focused:
   - `"SaaS meltdown February 2026"` → 0 chunks
   - `"SaaS sector selloff collapse 2026"` → 8 chunks
   - `"software valuations crash 2026 causes"` → 8 chunks
   - `"AI agents replacing SaaS software licenses disruption 2026"` → 8 chunks
   - `"SaaSocalypse software sector drawdown AI disruption fears"` → 8 chunks

   None targeted "hyperscaler CAPEX overspending" or "AI infrastructure investment FCF pressure." The bearish CAPEX chunk sat in Pinecone untouched.

#### Why This Happened (Causal Chain of Events)
The event structure is: **AI disruption → SaaS selloff starts → amid fear, AI valuation/CAPEX concern raised → selloff deepens**. CAPEX overspending is a second-order amplifier, not the initial trigger. So it's natural that the first queries don't find it. But after the initial retrieval:
- The **coverage assessor** rated coverage as `ADEQUATE` after 3 iterations, noting only "no counter-argument" as a gap — never identified CAPEX as missing
- The **Sonnet self-check** flagged "dollar strengthening" as a missing mechanism but not CAPEX
- Neither component recognized that the retrieved SaaS disruption narrative has a compounding factor (CAPEX valuation fear) that should have been searched for

#### Fix Options
- **Retrieval agent prompt**: Instruct the agent to search for amplifying/compounding factors after initial cause retrieval — "what made this worse?" not just "what caused this?"
- **Coverage assessor**: Should identify second-order causes as gaps, not just direct causal mechanisms
- **Self-check prompt**: Could add a check for "does the evidence suggest additional causal factors that weren't retrieved?" — but the self-check only sees what was already retrieved, so this is weaker

### 4. Self-check prompt improvement (lower priority)
- The self-check (`synthesis_prompts.py`) currently checks for counter-arguments (check #4) but not for contrarian readings of the same data
- Adding a rule like "for large quantitative data points, check if both bullish and bearish interpretations are explored" would help cases where CAPEX data IS retrieved but only bullish-framed
- However, for Case 1 specifically, this wouldn't have helped — the bearish CAPEX chunk wasn't retrieved at all, so the self-check had nothing to work with
- Still useful as defense-in-depth for cases where the data is retrieved but one-sided

## Fix Priority

1. **Prompt fix** (causes vs projections) — small change, immediate impact
2. **Retrieval agent: second-order cause search** — instruct the agent to look for amplifying factors after initial retrieval. This is the actual fix for the CAPEX gap.
3. **Coverage assessor improvement** — should identify compounding/amplifying mechanisms as gaps
4. **Self-check: contrarian interpretation rule** — defense-in-depth, lower priority
5. **Relationship store date filter** — only if retrospective testing accuracy matters
