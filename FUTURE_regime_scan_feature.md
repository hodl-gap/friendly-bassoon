# Future Feature: Regime Scan

## Status: TODO

Prerequisite: Theme-organized logic chain storage (this document).
Downstream: Regime scan orchestrator, daily batch updater (not designed yet).

---

## Problem Statement

The system currently handles **event-based queries** well (e.g., "TGA increased +10% this week, what's the BTC impact?") but cannot answer **state-based queries** like "Should I long BTC or short BTC now?".

The original proposal (run N parallel retrievals on demand, merge, feed to Opus) is wasteful — macro regime doesn't change intraday, so re-discovering the same chains every query is redundant. The real fix requires two layers:

1. **Persistent, theme-organized logic chain storage** that accumulates the system's causal knowledge over time (this document)
2. **A regime scan orchestrator** that reads pre-computed state and runs a single Opus impact call (downstream, not designed yet)

This document covers layer 1 only.

---

## Current State of Chain Storage

### What exists (`relationship_store.py` + `btc_relationships.json`)

- **141 chains** stored as a flat list in `btc_relationships.json`
- Each chain has: `logic_chain.steps[]` (cause/effect/mechanism with normalized names), `chain_summary`, `terminal_effect`, `relationship_type`, `confidence`, `discovered_at`, `validation_count`
- Chains are **byproducts of individual queries** — discovered during retrieval, appended to the flat list
- Deduplication is **exact string match** on `chain_summary` (case-insensitive)
- Relevance filtering at query time is **bag-of-words overlap** between query and chain summary/mechanism, returning top 5
- Regime state (`regime_state.json`) is a single object: `{liquidity_regime, dominant_driver, confidence, direction, last_updated}`

### What's missing

1. **No theme organization.** All 141 chains live in one flat list. A chain about TGA → reserves sits next to a chain about BOJ → carry trade → crypto. There's no way to ask "what does the system know about liquidity?" without keyword search.

2. **No systematic refresh.** Chains are only added when a user happens to query something related. If nobody asks about positioning for 2 weeks, the positioning chains go stale with no mechanism to update them.

3. **No distinction between structural and event-driven chains.** "TGA drawdown → reserves increase → SOFR stabilize" is a structural relationship that's always valid. "JPY intervention → carry unwind → BTC crash" is event-driven and only relevant when JPY intervention is actually happening. Both are stored identically.

4. **No "active/triggered" state per chain.** The system knows 141 causal pathways exist but doesn't track which ones are currently active based on today's data. This assessment only happens at query time, then gets discarded.

5. **Regime state is a single snapshot.** One `liquidity_regime` field for the whole macro environment, updated as a side effect of high-confidence analyses. No per-theme breakdown.

---

## Proposed Change: Theme-Organized Chain Storage

### Core concept

Organize logic chains into **theme sets** — curated collections of causal pathways grouped by macro theme. Each theme set is independently refreshable and tracks which chains are currently active.

### Theme definitions

Fixed set of macro themes, each with:
- A name and description
- A set of **anchor variables** (the normalized variable names this theme cares about)
- A **retrieval query template** for refreshing the theme's knowledge

```
Theme: liquidity
  Anchor variables: tga, rrp, bank_reserves, sofr, fed_balance_sheet
  Query template: "Current US liquidity conditions TGA reserves RRP Fed balance sheet"

Theme: positioning
  Anchor variables: gs_prime_book, cta_positioning, etf_flows, futures_oi
  Query template: "Current market positioning data prime book leverage CTA"

Theme: rates
  Anchor variables: fed_funds, sofr, treasury_yields, rate_expectations
  Query template: "Current interest rate environment Fed policy SOFR treasury yields"

Theme: risk_appetite
  Anchor variables: vix, dxy, credit_spreads, high_yield
  Query template: "Current risk appetite VIX DXY credit spreads"

Theme: crypto_specific
  Anchor variables: btc_etf_flows, stablecoin_supply, exchange_reserves
  Query template: "Bitcoin ETF flows stablecoin supply crypto-specific indicators"

Theme: event_calendar
  Anchor variables: fomc, cpi, nfp, opex
  Query template: "Upcoming macro events FOMC CPI NFP options expiration"
```

### Chain assignment to themes

A chain belongs to a theme if **any of its normalized cause/effect variables** overlaps with the theme's anchor variables. A chain can belong to multiple themes (e.g., `sofr -> bank_reserves` belongs to both "liquidity" and "rates").

Assignment is deterministic — no LLM needed. Just set intersection between chain step variables and theme anchor variables.

### Per-theme state

Each theme tracks:
- **Chain set**: List of chain IDs belonging to this theme (references into the main chain list)
- **Active chains**: Subset currently triggered/validated by recent data
- **Last refreshed**: When this theme was last updated via retrieval
- **Theme-level assessment**: Brief summary of current theme state (e.g., "liquidity: tightening, TGA draining reserves")

### Storage schema evolution

Current `btc_relationships.json` structure is preserved — chains stay in the flat list with their existing schema. Theme organization is an **index layer on top**, not a replacement.

New file (e.g., `theme_index.json`):
```json
{
  "themes": {
    "liquidity": {
      "anchor_variables": ["tga", "rrp", "bank_reserves", "sofr", "fed_balance_sheet"],
      "query_template": "Current US liquidity conditions TGA reserves RRP Fed balance sheet",
      "chain_ids": ["rel_b9846c96", "rel_a1234567", ...],
      "active_chain_ids": ["rel_b9846c96"],
      "last_refreshed": "2026-02-13T08:00:00Z",
      "assessment": "Tightening: TGA draining reserves, SOFR elevated"
    },
    "positioning": { ... },
    ...
  },
  "metadata": {
    "last_full_refresh": "2026-02-13T08:00:00Z",
    "theme_count": 6
  }
}
```

### Chain lifecycle

**Structural vs. event-driven distinction:**
- A chain is **structural** if it persists across multiple refresh cycles (validated repeatedly)
- A chain is **event-driven** if it only appears when a specific event is active
- This doesn't need an explicit flag — `validation_count` already tracks this. Structural chains accumulate high `validation_count` over time; event-driven chains stay at 1-2.

**Active/triggered state:**
- During a theme refresh, each chain in the theme's set is checked against current data
- If the chain's cause variable has moved significantly (via `fetch_current_data` + `validate_patterns`), the chain is marked active
- Active chains are what get passed to the Opus impact analysis at query time

---

## What needs to be built

### 1. Theme definitions config

A data structure defining the 6 themes with anchor variables and query templates. ~30 lines.

### 2. Chain-to-theme assignment function

Takes the existing flat chain list + theme definitions → produces the theme index (which chains belong to which themes). Deterministic set intersection on normalized variable names. ~20 lines.

### 3. Theme index persistence

Load/save `theme_index.json`. Simple JSON I/O, same pattern as `relationship_store.py`. ~20 lines.

### 4. Theme refresh function

For a single theme: run `run_retrieval(query_template, skip_gap_filling=True)` → extract new chains → deduplicate → update theme's chain set + active chains + assessment. This requires the `skip_gap_filling` parameter to be added to `run_retrieval()`. ~40 lines + ~10 lines modifying retrieval_orchestrator.

### 5. Active chain detection

For a theme's chain set: fetch current data for anchor variables → check which chains have their cause variables currently in motion → mark as active. Reuses existing `fetch_current_data()` and threshold logic from `validate_patterns()`. ~30 lines.

---

## What this enables (downstream, not designed yet)

- **Daily batch regime updater**: Cron job that refreshes all themes, updates active chains, writes per-theme assessments. Cost: ~$0.24/day.
- **Fast regime scan at query time**: Load pre-computed theme states + active chains → single Opus call. Cost: ~$0.30, latency: seconds not minutes.
- **Event overlay**: When a user queries a specific event, the event-driven retrieval result merges with the pre-computed regime context so Opus sees both the event and the macro backdrop.
- **Regime change detection**: Compare today's theme assessments to yesterday's → alert on significant shifts.

---

## Relevant existing code

| File | What it provides |
|------|-----------------|
| `relationship_store.py` | Chain storage, dedup, load/save, regime state |
| `btc_relationships.json` | 141 existing chains to backfill theme index |
| `retrieval_orchestrator.py:run_retrieval()` | Per-theme retrieval (needs `skip_gap_filling` param) |
| `current_data_fetcher.py` | Parallel variable data fetch |
| `pattern_validator.py` | Threshold validation against current data |
| `asset_configs.py` | Per-asset variable lists (similar pattern to theme anchor variables) |

## Constraints

- Chains stay in the flat list — theme index is a layer on top, not a migration
- No LLM calls needed for chain assignment or theme indexing (deterministic)
- Existing query flow is unaffected — this is additive
- `skip_gap_filling` is the only modification to existing code
