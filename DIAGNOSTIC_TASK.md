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

## Illustrative Example Output (User-Written Test Case)

```
There was a huge meltdown of SaaS stocks, which spread across global risk assets.


SaaS meltdown
Anthropic Claude Cowork -> SaaS meltdown
BofA 'AI will eat software"

SaaS earnings extinguished $0.5tn in aggregate market cap


CAPEX valuation issue
Hyperscaler CAPEX growth $570bn in 2026 spending (up 74% YoY)

Alphabet double CAPEX to $185bn for 2026 value destruction following Jan 30 announcement

Amazon's $200bn capex guidance for 2026 exceeded Wall Street expectations by over $50bn and surpassed the company's operating cash flow, triggering immediate concern about overspend risk across Big Tech

BofA characterized the market dynamic as "logically impossible," noting investors are simultaneously pricing two contradictory scenarios: deteriorating AI capex due to weak ROI and AI becoming pervasive enough to render existing software obsolete. This internal inconsistency reflects confusion about whether the $570B in hyperscaler spending for 2026 represents rational infrastructure deployment or speculative overbuild that will destroy shareholder value.

Software sector valuations compressed from 85x forward P/E in summer 2025 to below 60x by February 2026, with the IGV index entering bear market territory down 27% from its September 2025 peak. This multiple compression occurred despite the S&P 500 reaching all-time highs, indicating sector-specific valuation risk driven by AI disruption concerns and capex sustainability questions rather than broader market dynamics.

Oracle exemplified the valuation uncertainty, with shares fluctuating between $155 and $175 after announcing plans to raise $45B-$50B for AI infrastructure in 2026. The $155 price implied a $27B market cap decline, suggesting investors viewed the investment as value-destructive, while $175 implied $30B of net present value creation from the same $50B commitment—a $57B valuation swing based purely on ROI assumptions.
```

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

## Evaluation Rubric

### I. Logical Chain Formation

**Pass if:**
- The system can produce explicit, ordered chains
- Chains follow a structure like: `Trigger -> Interpretation -> Mechanism -> Outcome`

**Fail if:**
- Output is purely narrative
- Causality is implicit or vague

If Fail -> Report: Missing causal / logical representation capability.

### II. Branching From a Single Trigger (CRITICAL)

**Pass if:**
- A single trigger can generate multiple parallel chains
- Chains may lead to opposing outcomes (up and down)
- The system does not enforce one outcome per trigger

**Fail if:**
- Architecture forces a single terminal outcome
- Alternative interpretations are collapsed or suppressed

If Fail -> Report: System enforces convergence or lacks branching belief representation.

### III. Contradiction Preservation (NOT RESOLUTION)

**Pass if:**
- Contradictory chains are explicitly surfaced
- The system can state: "Markets were pricing X and NOT-X simultaneously"
- Contradictions are treated as:
  - Sources of volatility
  - Evidence of regime confusion
  - First-class explanatory objects

**Fail if:**
- Contradictions are smoothed over
- Conflicting paths are merged implicitly
- The system resolves tension without instruction

**Resolution is NOT required. Preservation IS required.**

If Fail -> Report: Missing assumption tracking or belief-branch persistence.

### IV. Outcome Polarity Support

**Pass if:**
- Chains can explicitly encode directional outcomes (e.g. risk assets up vs down)
- Polarity is part of the chain, not an afterthought

**Fail if:**
- Outcomes are forced to be uniform
- Directionality cannot be represented

If Fail -> Report: Missing outcome polarity or scenario representation.

### V. Event, Time, and Magnitude Anchoring

**Pass if:**
- Chains reference concrete events, timing, or scale
- Magnitude explains why something mattered

**Fail if:**
- Events are generic
- Numbers exist without reasoning

If Fail -> Report: Missing event extraction, temporal ordering, or scale reasoning.

### VI. Reasoning Architecture

**Pass if:**
- The system supports inspectable or stepwise reasoning
- Intermediate chains or hypotheses can be examined

**Fail if:**
- Output is purely one-shot
- No intermediate reasoning state exists

If Fail -> Report: Reasoning control-flow limitation.

### VII. Epistemic Coverage

**Pass if:**
- Output reflects a belief space, not a clean narrative
- Multiple narratives coexist, even if messy

**Fail if:**
- Output is overly clean or singular
- Known competing interpretations are absent

If Fail -> Report: Insufficient search breadth or belief diversity support.

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
