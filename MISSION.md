# Active Mission: Case Study Validation

## Goal
Run each of the 3 case studies through the FULL pipeline (Retriever → Risk Intelligence), repeatedly until each passes its rubric.

## Case Studies
| # | File | Query | Pass Threshold |
|---|------|-------|----------------|
| 01 | `test_cases/01_saas_meltdown.md` | "What caused the SaaS meltdown in Feb 2026?" | 8/13 (62%) + 3/4 categories |
| 02 | `test_cases/02_japan_election.md` | "How does the February 2026 Japan snap election (Takaichi) affect risk assets and yen carry trades?" | 11/18 (62%) + 2/3 categories |
| 03 | `test_cases/03_record_shorting.md` | "Goldman Sachs Prime Book shows the biggest shorting on record for US single stocks (week of Jan 30 - Feb 5, 2026, Z-score ~+3). What are the historical precedents for record short positioning, and what outcomes followed for risk assets?" | 14/22 (64%) + 4/5 categories |

## Pipeline
ALL cases run through full pipeline: Retriever → Risk Intelligence (insight mode, current default).

## Constraints
- **Minor adjustments OK**: prompt edits, small code changes, adding functions
- **Major refactoring NOT OK**: no new subprojects, no LangGraph overhaul, no DB source changes

## Logging Requirements (CRITICAL)
Every run MUST produce a complete debug log with:
- Every node entry/exit
- Every function call with source file
- ENTIRE LLM prompt (full context sent to API)
- ENTIRE LLM response (full response from API)
- ENTIRE web search results (no truncation)
- ENTIRE data fetch results (no truncation)
- NO TRUNCATION of any kind

Each run gets its own log file: `logs/debug_case{N}_run{M}_{timestamp}.log`

## Grading Criteria
Two conditions must BOTH be met:
1. **Output score**: Meets rubric threshold per case study
2. **Pipeline correctness**: Intermediate steps must be valid:
   - Retrieval found relevant chunks (not tangential content)
   - Gap detection correctly identified actual gaps
   - Web chain extraction returned real chains from real sources
   - Historical analogs are real events with real data
   - Data fetches returned actual values (not errors/nulls)
   - Final LLM synthesis used pipeline data (not hallucinated from training knowledge)

## Execution Order
Sequential: Case 01 → (loop until pass) → Case 02 → (loop until pass) → Case 03 → (loop until pass)

## Progress Tracking
| Case | Run | Score | Pass? | Log File | Notes |
|------|-----|-------|-------|----------|-------|
| | | | | | |
