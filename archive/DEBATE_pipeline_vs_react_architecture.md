# Architecture Debate: Fixed Pipeline vs. Agentic ReAct

## Goal

Produce multi-track causal insight reports that consistently score high on case study rubrics (currently 6 cases, 13-22 points each). The system takes a trader's macro query and must return: logic chains grounded in institutional research, historical precedents with quantified outcomes, current data validation, directional assessments with confidence scores, and monitoring variables. Cost is not a factor.

**Current scores:** 8/13, 11/18, 14/22, 13/20, 10/16, 10/16 (~55-65%). The question is which architecture can push these toward 80-90%+ consistently.

## Context

Should the research pipeline use a deterministic node-by-node flow (current) or an adaptive agent loop with tools (OpenClaw-style)?

---

## Option A: Current Architecture (LangGraph/Sequential Pipeline)

```
query → process_query → vector_search → generate → fill_gaps → resynthesis →
  → load_chains → extract_variables → fetch_current_data → validate_patterns →
  → historical_analogs → analyze_impact → store_chains
```

**How it works:**
- Fixed sequence of nodes, each with a dedicated prompt and single responsibility
- State object passed forward through each node
- Conditional branching exists (e.g., skip resynthesis if no gaps filled) but overall path is predetermined
- Each node makes 0-3 LLM calls with curated, node-specific inputs
- One search pass, one gap-fill pass, one analog search

**Current case study scores:** 8/13, 11/18, 14/22, 13/20, 10/16, 10/16 (~55-65%)

**Properties:**
- Every query walks the same path regardless of complexity
- Each node has a specialized prompt optimized for that exact task
- Debuggable: can isolate which node underperformed on a given rubric
- Reproducible: same query → same path → roughly same output
- Later nodes cannot influence earlier nodes (feedforward only)
- Search is single-pass (query expansion + vector search + rerank)
- Gap-filling is single-pass (detect gaps → web search → done)

---

## Option B: Agentic ReAct Loop (OpenClaw-style)

```
while not done:
    context = assemble(system_prompt, history, tool_results)
    response = llm.call(context)
    if response.is_text(): emit_report(); break
    if response.is_tool_call():
        result = execute_tool(response.tool, response.params)
        history.append(tool_result)
```

**How it works:**
- Single agent with access to tools: search_pinecone, web_search, fetch_data, validate_claims, find_analogs, compute_metrics
- Agent decides what to call, how many times, and in what order
- Each tool result feeds back into context; agent reasons about what to do next
- Agent writes final structured report when it judges research is sufficient
- One system prompt encodes all research methodology

**Properties:**
- Path varies per query — simple queries may use 5 tool calls, complex ones 25+
- Agent can iterate on retrieval (search → evaluate coverage → refine → search again)
- Gap-filling is naturally multi-round (discover gap → fill → discover new gap → fill)
- Cross-step feedback: analog results can trigger additional data fetches
- All intermediate tool results accumulate in context window
- Single prompt must cover all research phases (extraction, validation, analogs, synthesis)
- Non-deterministic: same query can produce different paths and outputs
- Harder to isolate which "step" failed since reasoning is interleaved

---

## Hybrid Option: Structured Agent with Mandatory Phases

```
PHASE 1: RETRIEVAL (agentic loop with tools: search, web_search, refine_query)
  → exit when agent confirms adequate coverage
PHASE 2: DATA GROUNDING (agentic loop with tools: fetch_data, validate_claims)
  → exit when key variables fetched and claims checked
PHASE 3: HISTORICAL CONTEXT (agentic loop with tools: detect_analogs, fetch_analog_data)
  → exit when sufficient precedent evidence gathered
PHASE 4: SYNTHESIS (single structured LLM call with curated phase 1-3 results)
  → mandatory sections enforced by output schema
```

**Properties:**
- Phase transitions are enforced (cannot skip analogs or data validation)
- Within each phase, agent iterates freely (adaptive depth)
- Final synthesis gets curated inputs, not raw tool result accumulation
- Each phase can have its own specialized prompt
- Debuggable at phase level (which phase underperformed?)
- Cost: 3-5x current pipeline per query
