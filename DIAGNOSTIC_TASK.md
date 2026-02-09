# Diagnostic Task: Belief-Space Output Tuning

## Role

Developer Agent tuning an agentic research system to reproduce expected outputs.

**Iterative fixer**: Run the pipeline, diagnose failures, apply fixes, and loop until the test passes or is determined impossible.

Workflow:
1. Read test case (query + expected output + rubric)
2. Run pipeline with query
3. Score output against rubric
4. If FAIL: diagnose root cause, apply fix, go to step 2
5. If PASS: document results, commit changes
6. If IMPOSSIBLE: document why and stop

---

## Goal

The research system should take a query and output a set of explicit logical / causal chains representing the market belief space around an event.

### Key Properties of Desired Output

- Chains must be explicit and ordered
- Multiple chains may originate from the same trigger
- Chains may lead to opposing outcomes (e.g. risk assets up and down)
- Contradictory chains are valid and expected
- No single "canonical" explanation or outcome is required
- The system is mapping what was priced, debated, or feared, not determining what was "correct"

### Example Output Structure

```
Trigger Event
-> Interpretation A -> Mechanism -> Outcome (up/down)
-> Interpretation B -> Mechanism -> Outcome (up/down)
```

Contradictions like the following must be explicitly preserved:

```
"AI CAPEX implies value destruction" → down
AND
"AI CAPEX confirms AI leadership" → up
```

---

## What You CAN Change

| Allowed | Examples |
|---------|----------|
| Prompt rewrites | `*_prompts.py` files |
| Trusted domain lists | `trusted_domains.py` |
| Config flags | `config.py` thresholds, feature toggles |
| New utility functions | Helper functions in existing modules |
| Query expansion logic | Dimension generation, search queries |

## What You CANNOT Change

| Not Allowed | Reason |
|-------------|--------|
| Core architecture | LangGraph workflow structure |
| Database schema | Pinecone index, metadata format |
| External API contracts | FRED, Yahoo, Tavily interfaces |
| Model selection | Which LLM to use (defined in `models.py`) |
| Complete module rewrites | Refactoring entire files |

---

## Stopping Rules

**STOP and mark PASS if:**
- Score meets passing threshold (defined in test case rubric)
- Required category coverage is met

**STOP and mark IMPOSSIBLE if:**
- Required data doesn't exist in DB AND web search cannot surface it
- Architectural limitation prevents representing the expected output structure
- Fix would require changes to "cannot change" items above
- 5+ iterations with no score improvement

**CONTINUE iterating if:**
- Score is below threshold but improving
- Root cause is identifiable and fixable within constraints
- Fix is incremental (prompt, config, trusted domains)

---

## Test Cases

Test cases are stored in `test_cases/` directory. Each test case contains:
- Query to run
- Expected output (what the system should surface)
- Rubric (scoring criteria specific to that test case)
- Passing threshold

| # | File | Query | Status | Score |
|---|------|-------|--------|-------|
| 01 | [01_saas_meltdown.md](test_cases/01_saas_meltdown.md) | "What caused the SaaS meltdown in Feb 2026?" | PASS | 9/13 |
| 02 | [02_japan_election.md](test_cases/02_japan_election.md) | "How does the February 2026 Japan snap election (Takaichi) affect risk assets and yen carry trades?" | PASS | 11/18 |

---

## How to Run a Test Case

1. Read the test case file to get query and rubric
2. Run the pipeline:
   ```bash
   cd subproject_database_retriever
   source ../venv/bin/activate
   python -c "
   from retrieval_orchestrator import run_retrieval
   result = run_retrieval('YOUR_QUERY_HERE')
   print('Synthesis:', result.get('synthesis'))
   print('Web Chains:', len(result.get('extracted_web_chains', [])))
   "
   ```
3. Score the output against the rubric
4. Fill in the test case file with results

---

## TODO

- [ ] **Persist high-confidence web chains to DB** - Currently web chains are transient (discarded after response). Consider storing chains with `quote_verified=True` and `confidence=high` to Pinecone to build knowledge over time. Needs: QA pipeline integration, staleness management, deduplication logic.

---

## Fixes Applied (Historical)

### Fix 1: Gap Detection Prompt (Test Case 01)

**File**: `subproject_database_retriever/knowledge_gap_prompts.py` (lines 38-46)

**Problem**: Gap detector checked "Is topic mentioned?" instead of "Does synthesis answer the question?"

**Before:**
```
- COVERED: Query topic explicitly discussed in synthesis/chains
- ONLY mark as GAP if the topic is completely absent from synthesis
```

**After:**
```
- COVERED: Synthesis directly ANSWERS the specific question asked
- GAP: Synthesis does NOT answer the question, even if it mentions related topics
- IMPORTANT: Tangentially related content is NOT "covered"
```

### Fix 2: Trusted Domains (Test Case 01)

**File**: `subproject_data_collection/adapters/trusted_domains.py`

**Problem**: Bloomberg, WSJ, FT are paywalled - web chain extraction got headers, not content.

**Added:**
```python
"yahoo.com": {"name": "Yahoo Finance", "tier": 1},
"finance.yahoo.com": {"name": "Yahoo Finance", "tier": 1},
"forbes.com": {"name": "Forbes", "tier": 1},
```
