# Deferred Issues — Requires Refactoring / New Implementation / Research

These issues were identified during the Feb 2026 audit but deferred because they require structural changes, new implementations, or manual research rather than pure bug fixes.

---

## ~~1. sys.path / sys.modules Race Condition (Refactor)~~ — BAND-AID APPLIED

**Files:** `knowledge_gap_detector.py:278-313,760-786`, `insight_orchestrator.py:22-23`, `shared/integration.py:17-18`

**Problem:** Subprojects insert themselves at `sys.path[0]`, causing `config.py` and `states.py` name collisions. The workaround (saving/restoring `sys.modules` entries) is not thread-safe — concurrent `ThreadPoolExecutor` calls can permanently corrupt imports mid-run.

**Band-aid applied:** Added `_import_lock = threading.Lock()` in `knowledge_gap_detector.py`, wrapping all 3 `sys.modules` manipulation blocks. Prevents the race condition but doesn't fix the architectural debt.

**Proper fix (still needed):** Convert subprojects into proper Python packages with namespaced imports (e.g., `from subproject_database_retriever.config import ...` instead of manipulating `sys.path`).

---

## 2. refine_query Stub (New Implementation)

**File:** `subproject_database_retriever/query_processing.py:188-192`

**Problem:** `refine_query()` is a stub that returns the original query unchanged. The agentic iteration loop can cycle up to MAX_ITERATIONS doing nothing, burning tokens on identical searches.

**Fix:** Implement actual query refinement logic that uses retrieved context to reformulate the query. Alternatively, remove the iteration loop entirely since chain-of-retrievals (dangling effect following) already compensates for this.

---

## ~~3. Hardcoded `asset_class="btc"` in Theme Refresh (Minor Refactor)~~ — FIXED

**File:** `subproject_risk_intelligence/theme_refresh.py`

**Fix applied:** Added `asset_class` parameter to `refresh_theme()` and `refresh_all_themes()`, propagated to `store_chains()` and `load_relationships()`. Defaults to `"btc"` for backward compatibility.

---

## 4. Private Method Access on WebSearchAdapter (Minor Refactor)

**File:** `subproject_risk_intelligence/historical_event_detector.py:381,388`

**Problem:** Calls `adapter._search_duckduckgo()` and `adapter._format_search_results()` — private methods. Any refactor of WebSearchAdapter breaks historical event detection silently (falls through to low-confidence fallback dates via `except Exception`).

**Fix:** Expose public methods on `WebSearchAdapter` for search + formatting, or extract a shared search utility.

---

## 5. Anchor Variables Missing Data Sources (Research Task)

**File:** `shared/data/anchor_variables.json`

**Problem:** 9 of 25 anchor variables have `"source": null` and `"series_id": null`:
- `gs_prime_book` (positioning)
- `cta_positioning` (positioning)
- `etf_flows` (positioning)
- `futures_oi` (positioning)
- `rate_expectations` (rates)
- `btc_etf_flows` (crypto_specific)
- `stablecoin_supply` (crypto_specific)
- `exchange_reserves` (crypto_specific)

The entire `positioning` and `crypto_specific` themes are non-functional for data-driven monitoring.

**Fix:** Research and find appropriate data sources (FRED series, Yahoo tickers, CoinGecko IDs, or custom scrapers) for each variable. Some may not have freely available API sources and require institutional data adapters.

---

## ~~6. CoinGecko Not Handled in Shared Integration Layer~~ — FIXED

**Files:** `shared/integration.py`

**Fix applied:** Added CoinGecko cases to both `_fetch_data()` and `get_adapter_for_source()`, mirroring the FRED/Yahoo pattern.

---

## 7. Active Chain Detection Uses Synthetic 5% Heuristic

**File:** `subproject_risk_intelligence/theme_refresh.py:98-104`

**Problem:** "Active chain" detection uses a hardcoded 5% threshold in either direction over 7 days. This has no relationship to the actual chain's trigger conditions — it flags chains as active based on any large market move, even if the chain's mechanism is completely different.

**Fix:** Extract actual pattern conditions from the chain's stored data and validate against those specific conditions instead of a one-size-fits-all percentage threshold.
