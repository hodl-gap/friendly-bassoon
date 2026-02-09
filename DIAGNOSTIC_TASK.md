# Diagnostic Task: Belief-Space Architecture Evaluation

## Role

Developer Agent evaluating an agentic research system that is currently under development.

**Not a fixer, refactorer, or implementer.**

Role is to diagnose whether the current system can achieve the stated GOAL in principle, using its existing architecture and capabilities only, and to identify what is missing or must be implemented in the future.

Must not:
- Patch or refactor the system
- Propose code-level solutions
- Force convergence or resolution
- Assume future features already exist

Output is an architectural and capability assessment, not an improvement plan.

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

### Example Query

> What triggered the risk asset crash in 2026 Feb?

### Desired Output Characteristics (Illustrative)

The system should surface multiple belief paths, for example:

```
AI CAPEX increase
-> Interpretation: Overinvestment / ROI dilution
-> Value destruction fears
-> Risk assets down
```

Contradictions like the following must be explicitly preserved:

```
"AI CAPEX implies value destruction"
AND
"AI CAPEX confirms AI leadership and long-term upside"
```

The system output may be abstract, e.g.:

```
CAPEX doubles -> overvaluation fear -> down
CAPEX doubles -> AI conviction -> up
```

as long as logical structure and polarity are preserved.

---

## Mission

Evaluate whether the current research system can achieve the GOAL, using only what already exists.

While conceptually attempting to run the system toward the GOAL, must:
- Identify where the system fails or degrades
- Classify failures into categories such as:
  - Data collection / event extraction
  - Temporal or magnitude anchoring
  - Reasoning architecture
  - Control flow
  - Representation limits
- Judge whether each limitation is:
  - Incremental (additive modules possible)
  - Foundational (requires architectural change)

Must stop and report, not fix.

---

## Evaluation Rubric (Concrete - Graded Against Sample Output)

Score system output against the illustrative example. Each item is 1 point.

### A. Trigger Identification (3 points)

| # | Item | Description | Points |
|---|------|-------------|--------|
| A1 | SaaS meltdown | Core event identified (SaaS stocks, software sector crash) | 1 |
| A2 | AI product trigger | Anthropic Claude Cowork or similar AI product launch as catalyst | 1 |
| A3 | "AI eats software" narrative | BofA or analyst narrative that AI disrupts/obsoletes SaaS | 1 |

### B. CAPEX Valuation Chain (4 points)

| # | Item | Description | Points |
|---|------|-------------|--------|
| B1 | Hyperscaler CAPEX total | $570bn aggregate or similar magnitude for 2026 | 1 |
| B2 | Alphabet CAPEX | $185bn or "doubled CAPEX" + Jan 30 announcement | 1 |
| B3 | Amazon CAPEX | $200bn guidance, exceeded expectations by ~$50bn | 1 |
| B4 | CAPEX → value destruction chain | Explicit chain: CAPEX increase → overinvestment fear → value destruction | 1 |

### C. Contradiction Preservation (2 points)

| # | Item | Description | Points |
|---|------|-------------|--------|
| C1 | "Logically impossible" | BofA or analyst noting contradictory market pricing | 1 |
| C2 | Both sides preserved | (a) AI CAPEX = weak ROI / overbuild AND (b) AI = eating software / long-term upside | 1 |

### D. Quantitative Anchoring (3 points)

| # | Item | Description | Points |
|---|------|-------------|--------|
| D1 | Market cap destruction | $0.5tn or similar magnitude of SaaS value lost | 1 |
| D2 | Valuation compression | P/E multiple compression (85x → 60x or similar) | 1 |
| D3 | Index drawdown | IGV -27% from peak, or equivalent sector index decline | 1 |

### E. Concrete Example (1 point)

| # | Item | Description | Points |
|---|------|-------------|--------|
| E1 | Company case study | Oracle $155-$175 swing, or similar single-stock example showing valuation uncertainty | 1 |

---

### Scoring Summary

| Category | Max Points |
|----------|------------|
| A. Trigger Identification | 3 |
| B. CAPEX Valuation Chain | 4 |
| C. Contradiction Preservation | 2 |
| D. Quantitative Anchoring | 3 |
| E. Concrete Example | 1 |
| **TOTAL** | **13** |

**Passing threshold**: 8/13 (62%) with at least 1 point from 3 of 4 categories A-D.

---

## Stopping Rules

**MUST stop and report if:**
- The system cannot represent branching outcomes
- The system cannot preserve contradictions
- The system enforces a single belief or outcome per trigger
- Achieving the GOAL would require changing the core reasoning paradigm

**MAY continue reasoning if:**
- Additional belief paths can still be surfaced
- Limitations appear incremental rather than foundational

---

## Required Final Output Format

When stopped, output only the following sections:

1. **GOAL Achievability Verdict**: Achievable / Partially Achievable / Not Achievable
2. **Blocking Limitations (Ranked)**: With brief explanations
3. **Missing Capabilities (Abstract, Not Code)**: e.g. "Branching belief-state representation", "Outcome polarity encoding"
4. **What the Current System Already Does Well**

Do not:
- Propose fixes
- Write code
- Resolve contradictions
- Select a "correct" narrative

---

## Test Cases

Test cases are stored in `test_cases/` directory:

| # | File | Query | Status | Score |
|---|------|-------|--------|-------|
| 01 | [01_saas_meltdown.md](test_cases/01_saas_meltdown.md) | "What caused the SaaS meltdown in Feb 2026?" | PASS | 9/13 |

---

## TODO

- [ ] **Persist high-confidence web chains to DB** - Currently web chains are transient (discarded after response). Consider storing chains with `quote_verified=True` and `confidence=high` to Pinecone to build knowledge over time. Needs: QA pipeline integration, staleness management, deduplication logic.

---

## Fixes Applied

### Edit 1: `subproject_database_retriever/knowledge_gap_prompts.py` (lines 38-46)

**BEFORE:**
```
0. **Topic not covered**
   - COVERED: Query topic explicitly discussed in synthesis/chains
   - GAP: Query topic NOT mentioned at all in synthesis
   - ONLY mark as GAP if the topic is completely absent from synthesis (not just partially covered)
   - When gap detected, provide a GENERAL search query for the topic (not domain-specific)
```

**AFTER:**
```
0. **Topic not covered (CRITICAL - evaluate carefully)**
   - COVERED: Synthesis directly ANSWERS the specific question asked
   - GAP: Synthesis does NOT answer the question, even if it mentions related topics or timeframes
   - IMPORTANT: Tangentially related content is NOT "covered". If query asks "What caused X?" and synthesis discusses Y (even if Y happened around the same time), that's a GAP.
   - Example: Query asks "What caused the SaaS meltdown?" → Synthesis discusses Fed policy in same timeframe → GAP
   - When gap detected, provide a SPECIFIC search query targeting the actual question
```

### Edit 2: `subproject_data_collection/adapters/trusted_domains.py` (line 39)

**ADDED:**
```python
"yahoo.com": {"name": "Yahoo Finance", "tier": 1},
"finance.yahoo.com": {"name": "Yahoo Finance", "tier": 1},
"forbes.com": {"name": "Forbes", "tier": 1},
```

**Why:** Bloomberg, WSJ, FT are paywalled. Yahoo Finance and Forbes have accessible article content for web chain extraction.

---

<!--
## Archived: Abstract Evaluation Rubric (Not Currently Used)

The following criteria are preserved for future reference but not used for current grading.
They evaluate architectural capabilities rather than output relevance.

### I. Logical Chain Formation
- Pass: Explicit, ordered chains (Trigger -> Interpretation -> Mechanism -> Outcome)
- Fail: Purely narrative, implicit causality

### II. Branching From a Single Trigger (CRITICAL)
- Pass: Single trigger generates multiple parallel chains with opposing outcomes
- Fail: Architecture forces single terminal outcome

### III. Contradiction Preservation (NOT RESOLUTION)
- Pass: Contradictory chains explicitly surfaced, treated as first-class objects
- Fail: Contradictions smoothed over or resolved without instruction

### IV. Outcome Polarity Support
- Pass: Chains encode directional outcomes (up/down)
- Fail: Outcomes forced uniform

### V. Event, Time, and Magnitude Anchoring
- Pass: Concrete events, timing, scale with reasoning
- Fail: Generic events, numbers without context

### VI. Reasoning Architecture
- Pass: Inspectable, stepwise intermediate states
- Fail: Purely one-shot output

### VII. Epistemic Coverage
- Pass: Multiple narratives coexist (belief space)
- Fail: Overly clean or singular output
-->
