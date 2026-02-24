"""
Pipeline Log Viewer v2 — Human-readable gap analysis grouping.

Changes from v1:
  - Gap-related phases merged into single "Gap Analysis" visit
  - Steps reordered by gap category (not execution order)
  - Gap summary table from parsed JSON
  - Per-gap group headers with status badges

Usage:
    python tools/log_viewer_v2.py logs/run_20260220_020944.log
    python tools/log_viewer_v2.py logs/run_20260221_045642.log -o my_view_v2.html
"""

import re
import sys
import html
import json
from pathlib import Path


# ── Line classification (same as v1) ────────────────────────────────────

def classify_line(line: str) -> str:
    stripped = line.strip()
    if not stripped:
        return "blank"
    if stripped.startswith("=====") or stripped.startswith("-----") or stripped.startswith("#####"):
        return "separator"
    if re.match(r'^\[[\w\s./:\-]+\]', stripped) and not line.startswith(' '):
        return "step"
    if stripped.startswith("DIMENSION:"):
        return "dimension"
    if stripped.startswith("REASONING:"):
        return "reasoning"
    if stripped.startswith("QUERY:"):
        return "query_line"
    if stripped.startswith("**CHAIN:**") or stripped.startswith("**MECHANISM:**") or stripped.startswith("**SOURCE:**") or stripped.startswith("**CONNECTION:**"):
        return "chain_detail"
    if re.match(r'^2\d{3}-\d{2}-\d{2}.*httpx.*HTTP Request', stripped):
        return "httpx_noise"
    if stripped.startswith("Pipeline Run:") or stripped.startswith("Query:") and len(stripped) < 200:
        return "header"
    if stripped.startswith("Message(id="):
        return "raw_message"
    return "body"


def detect_module(line: str) -> str:
    m = re.match(r'^\[([\w\s./:]+)\]', line.strip())
    return m.group(1).strip() if m else ""


# ── Phase / module mappings (v2: Gap Analysis replaces separate phases) ──

PHASE_ORDER = [
    "Query Processing",
    "Vector Search",
    "Answer Generation",
    "Gap Analysis",
    "Historical Analogs",
    "Variable Extraction",
    "Data Collection",
    "Risk Intelligence",
    "Output",
]

PHASE_SHORT = {
    "Query Processing": "Query",
    "Vector Search": "Search",
    "Answer Generation": "Answer",
    "Gap Analysis": "Gap Analysis",
    "Historical Analogs": "Hist. Analog",
    "Variable Extraction": "Variables",
    "Data Collection": "Data Fetch",
    "Risk Intelligence": "Risk Intel",
    "Output": "Output",
}

PHASE_ICONS = {
    "Query Processing": "&#x1F50D;",
    "Vector Search": "&#x1F4BE;",
    "Answer Generation": "&#x1F4DD;",
    "Gap Analysis": "&#x26A0;",
    "Historical Analogs": "&#x1F4C5;",
    "Variable Extraction": "&#x1F4CA;",
    "Data Collection": "&#x1F4E5;",
    "Risk Intelligence": "&#x1F9E0;",
    "Output": "&#x2705;",
}

MODULE_TO_PHASE = {
    "query_processing": "Query Processing",
    "Retrieve": "Query Processing",
    "retrieval": "Query Processing",
    "vector_search": "Vector Search",
    "chain_expansion": "Vector Search",
    "answer_generation": "Answer Generation",
    # v2: all gap-related modules → Gap Analysis
    "Knowledge Gap": "Gap Analysis",
    "retriever.gap_detector": "Gap Analysis",
    "Gap: topic_not_covered": "Gap Analysis",
    "Gap: historical_precedent_depth": "Gap Analysis",
    "Gap: quantified_relationships": "Gap Analysis",
    "Gap: monitoring_thresholds": "Gap Analysis",
    "Gap: event_calendar": "Gap Analysis",
    "Gap: mechanism_conditions": "Gap Analysis",
    "Gap: exit_criteria": "Gap Analysis",
    "WebSearch": "Gap Analysis",
    "web_chain_persistence": "Gap Analysis",
    "Chain Merge": "Gap Analysis",
    "Chain Triggers": "Gap Analysis",
    "Chain Graph": "Gap Analysis",
    "Historical Analog": "Historical Analogs",
    "Historical Analogs": "Historical Analogs",
    "Historical Data": "Data Collection",
    "Historical Event": "Data Collection",
    "Variable Extraction": "Variable Extraction",
    "current_data": "Data Collection",
    "Current Data": "Data Collection",
    "data_fetching": "Data Collection",
    "claim_parsing": "Data Collection",
    "Claim Validation": "Data Collection",
    "validation": "Data Collection",
    "Pattern Validator": "Data Collection",
    "Impact Analysis": "Risk Intelligence",
    "orchestrator": "Risk Intelligence",
    "Regime State": "Risk Intelligence",
    "Regime Characterization": "Risk Intelligence",
    "Regime/Bitcoin": "Risk Intelligence",
    "Prediction Tracker": "Output",
    "Relationship Store": "Output",
    "output_formatter": "Output",
    "rss_adapter": "Output",
}

PHASE_COLORS = {
    "Query Processing": "#3b82f6",
    "Vector Search": "#8b5cf6",
    "Answer Generation": "#06b6d4",
    "Gap Analysis": "#f59e0b",
    "Historical Analogs": "#ec4899",
    "Variable Extraction": "#a855f7",
    "Data Collection": "#0ea5e9",
    "Risk Intelligence": "#ef4444",
    "Output": "#78716c",
}

MODULE_COLORS = {
    "query_processing": "#3b82f6",
    "vector_search": "#8b5cf6",
    "answer_generation": "#06b6d4",
    "chain_expansion": "#6366f1",
    "Knowledge Gap": "#f59e0b",
    "WebSearch": "#10b981",
    "Historical Analog": "#ec4899",
    "Historical Analogs": "#ec4899",
    "Historical Data": "#d946ef",
    "Historical Event": "#d946ef",
    "Chain Merge": "#f97316",
    "Chain Triggers": "#f97316",
    "Chain Graph": "#f97316",
    "web_chain_persistence": "#14b8a6",
    "retrieval": "#3b82f6",
    "retriever.gap_detector": "#f59e0b",
    "Retrieve": "#2563eb",
    "Variable Extraction": "#a855f7",
    "current_data": "#0ea5e9",
    "Current Data": "#0ea5e9",
    "Impact Analysis": "#ef4444",
    "orchestrator": "#ef4444",
    "claim_parsing": "#64748b",
    "Claim Validation": "#64748b",
    "data_fetching": "#64748b",
    "validation": "#64748b",
    "Pattern Validator": "#64748b",
    "Regime State": "#dc2626",
    "Regime Characterization": "#dc2626",
    "Regime/Bitcoin": "#dc2626",
    "Prediction Tracker": "#78716c",
    "Relationship Store": "#78716c",
    "output_formatter": "#78716c",
    "rss_adapter": "#78716c",
    "Gap: topic_not_covered": "#10b981",
    "Gap: historical_precedent_depth": "#8b5cf6",
    "Gap: quantified_relationships": "#3b82f6",
    "Gap: monitoring_thresholds": "#f59e0b",
    "Gap: event_calendar": "#06b6d4",
    "Gap: mechanism_conditions": "#ec4899",
    "Gap: exit_criteria": "#ef4444",
}

# v2: Gap group config
GAP_LABELS = {
    "topic_not_covered": "Topic Coverage",
    "historical_precedent_depth": "Historical Precedents",
    "quantified_relationships": "Quantified Relationships",
    "monitoring_thresholds": "Monitoring Thresholds",
    "event_calendar": "Event Calendar",
    "mechanism_conditions": "Mechanism Conditions",
    "exit_criteria": "Exit Criteria",
    "_overview": "Gap Detection",
    "_conclusion": "Summary & Merge",
}

GAP_GROUP_COLORS = {
    "topic_not_covered": "#10b981",
    "historical_precedent_depth": "#8b5cf6",
    "quantified_relationships": "#3b82f6",
    "monitoring_thresholds": "#f59e0b",
    "event_calendar": "#06b6d4",
    "mechanism_conditions": "#ec4899",
    "exit_criteria": "#ef4444",
    "_overview": "#f59e0b",
    "_conclusion": "#78716c",
}

GAP_CANONICAL_ORDER = [
    "_overview",
    "topic_not_covered",
    "historical_precedent_depth",
    "quantified_relationships",
    "monitoring_thresholds",
    "event_calendar",
    "mechanism_conditions",
    "exit_criteria",
    "_conclusion",
]


# ── Key step detection (same as v1) ─────────────────────────────────────

def is_key_step(line: str) -> bool:
    keywords = [
        "Gap split:", "Coverage:", "Gaps:", "FILLED", "UNFILL", "PARTIAL",
        "Confidence:", "confidence_level", "Stage 1 complete", "Stage 2 complete",
        "Stage 3:", "WEB CHAIN EXTRACTION NEEDED", "Injected web_chain_extraction",
        "Total:", "chains from", "merged", "Expanded to", "Extracted",
        "Final:", "chunks", "re-ranked", "Persisted", "direction=",
        "Summary:", "dominant_pattern", "episodes", "Status:",
        "CHAIN INCOMPLETE", "dangling", "resolution rate",
        "Query complexity:", "Temporal reference:", "Type:",
        "Processing query", "Querying:",
    ]
    return any(kw in line for kw in keywords)


# ── Gap Analysis helpers (v2 only) ──────────────────────────────────────

def extract_gap_json(body_lines: list[str]) -> dict | None:
    """Extract gap detection JSON from step body lines."""
    text = "\n".join(body_lines)
    start = text.find('{\n  "coverage_rating"')
    if start == -1:
        start = text.find('{"coverage_rating"')
    if start == -1:
        return None
    brace_count = 0
    for i in range(start, len(text)):
        if text[i] == '{':
            brace_count += 1
        elif text[i] == '}':
            brace_count -= 1
        if brace_count == 0:
            try:
                return json.loads(text[start:i + 1])
            except json.JSONDecodeError:
                return None
    return None


def tag_gap_step(step: dict, current_gap: str, seen_any_gap: bool) -> tuple[str, str]:
    """Tag a step with its gap group. Returns (group, new_current_gap)."""
    summary = step["summary"]
    body_text = "\n".join(step["body"])

    # 1. Explicit gap markers
    m = re.match(r'\[Gap:\s*([\w_]+)\]', summary.strip())
    if m:
        cat = m.group(1)
        return cat, cat

    # 2. Web chain content → topic_not_covered
    wc_markers = [
        "Searching for logic chains on:",
        "logic_chains with Haiku",
        "Web chain expansion response",
        "web chain queries",
        "trusted sources from",
        '"chain_count"',
        "chains from",
    ]
    if any(marker in body_text for marker in wc_markers):
        return "topic_not_covered", current_gap

    # 3. Conclusion markers
    conc_markers = ["Chain Merge", "chains extracted", "Web chain extraction:"]
    if any(marker in summary for marker in conc_markers):
        return "_conclusion", current_gap
    if re.search(r'\[Knowledge Gap\].*Summary:', summary):
        return "_conclusion", current_gap

    # 4. Data fetch errors
    if "yfinance" in body_text or "Data fetcher import" in body_text:
        return "quantified_relationships", current_gap

    # 5. Persistence
    if "Persisted" in summary or "persist" in summary.lower():
        return "_conclusion", current_gap

    # 6. Before any gap → overview
    if not seen_any_gap:
        return "_overview", current_gap

    # 7. "Attempting to fill" → overview
    if "Attempting to fill" in summary:
        return "_overview", current_gap

    # 8. Default: current gap
    return current_gap, current_gap


def organize_gap_steps(steps: list[dict]) -> tuple[list[tuple], dict | None]:
    """Organize gap steps into groups by category for nested rendering."""
    # Extract gap JSON
    gap_json = None
    for step in steps:
        gap_json = extract_gap_json(step["body"])
        if gap_json:
            break

    # Tag all steps
    current_gap = "_overview"
    seen_any_gap = False
    for step in steps:
        if re.match(r'\[Gap:\s*', step["summary"].strip()):
            seen_any_gap = True
        group, current_gap = tag_gap_step(step, current_gap, seen_any_gap)
        step["_gap_group"] = group

    # Build ordered groups
    groups = []
    seen = set()
    for group_name in GAP_CANONICAL_ORDER:
        group_steps = [s for s in steps if s.get("_gap_group") == group_name]
        if group_steps and group_name not in seen:
            groups.append((group_name, group_steps))
            seen.add(group_name)
    # Catch any unlisted groups
    for step in steps:
        g = step.get("_gap_group", "_overview")
        if g not in seen:
            gs = [s for s in steps if s.get("_gap_group") == g]
            groups.append((g, gs))
            seen.add(g)

    return groups, gap_json


def detect_group_status(group_steps: list[dict]) -> str | None:
    """Detect FILLED/UNFILLABLE/ERROR status from a gap group's steps."""
    for step in group_steps:
        body = "\n".join(step["body"])
        if "Status: FILLED" in body:
            return "FILLED"
        if "Status: UNFILLABLE" in body:
            return "UNFILLABLE"
        if "Status: PARTIAL" in body:
            return "PARTIAL"
    for step in group_steps:
        body = "\n".join(step["body"])
        if "not installed" in body or "import failed" in body:
            return "ERROR"
    return None


def get_gap_info(gap_json: dict | None, category: str) -> dict:
    """Get gap info from JSON for a category."""
    if not gap_json:
        return {}
    for gap in gap_json.get("gaps", []):
        if gap.get("category") == category:
            return gap
    return {}


# ── Parser (same as v1) ─────────────────────────────────────────────────

def parse_log(lines: list[str]) -> list[dict]:
    steps = []
    i = 0
    n = len(lines)

    # Header
    header_lines = []
    while i < n and i < 10:
        cl = classify_line(lines[i])
        if cl in ("header", "separator", "blank"):
            header_lines.append(lines[i])
            i += 1
        elif cl == "step" and "[Retrieve]" in lines[i]:
            break
        else:
            header_lines.append(lines[i])
            i += 1

    if header_lines:
        steps.append({
            "type": "header", "module": "Pipeline", "phase": "Query Processing",
            "summary": next((l.strip() for l in header_lines if l.strip().startswith("Query:")), "Pipeline Start"),
            "body": header_lines, "is_key": True,
        })

    while i < n:
        line = lines[i]
        cl = classify_line(line)

        if cl == "httpx_noise":
            i += 1
            continue

        if cl == "separator":
            j = i + 1
            while j < n and classify_line(lines[j]) == "blank":
                j += 1
            if j < n:
                next_line = lines[j].strip()
                if next_line.startswith("IMPACT ANALYSIS") or next_line.startswith("LLM USAGE") or next_line.startswith("CURRENT MARKET") or next_line.startswith("CONDENSED SUMMARY"):
                    has_real_steps = any(s["type"] == "step" for s in steps)
                    if not has_real_steps:
                        i = j + 1
                        while i < n and classify_line(lines[i]) in ("separator", "blank"):
                            i += 1
                        continue
                    body = []
                    while i < n and classify_line(lines[i]) in ("separator", "blank"):
                        i += 1
                    section_title = lines[i].strip() if i < n else "Section"
                    body.append(lines[i])
                    i += 1
                    # For content-heavy sections (CONDENSED SUMMARY), capture all
                    # body lines until next === separator or EOF
                    if "CONDENSED" in section_title:
                        while i < n and classify_line(lines[i]) in ("separator", "blank"):
                            i += 1
                        while i < n:
                            if classify_line(lines[i]) == "separator":
                                # Check if this separator starts a new named section
                                peek = i + 1
                                while peek < n and classify_line(lines[peek]) == "blank":
                                    peek += 1
                                if peek < n and (lines[peek].strip().startswith("LLM USAGE") or
                                                 lines[peek].strip().startswith("CONDENSED") or
                                                 lines[peek].strip().startswith("Pipeline")):
                                    break
                            body.append(lines[i])
                            i += 1
                    else:
                        while i < n and classify_line(lines[i]) in ("separator", "blank"):
                            i += 1
                    phase = "Risk Intelligence" if "IMPACT" in section_title else "Output"
                    steps.append({"type": "section", "module": section_title, "phase": phase,
                                  "summary": section_title, "body": body, "is_key": True})
                    continue
            i += 1
            continue

        if cl == "blank":
            i += 1
            continue

        if cl == "step":
            module = detect_module(line)
            phase = MODULE_TO_PHASE.get(module, "Risk Intelligence")
            summary_text = line.strip()
            body = [line]
            is_key = is_key_step(line)
            i += 1
            while i < n:
                next_cl = classify_line(lines[i])
                if next_cl == "step":
                    break
                if next_cl == "separator":
                    j = i + 1
                    while j < n and classify_line(lines[j]) in ("blank", "separator"):
                        j += 1
                    if j < n and classify_line(lines[j]) == "step":
                        i = j
                        break
                    break
                if next_cl == "httpx_noise":
                    i += 1
                    continue
                body.append(lines[i])
                i += 1
            steps.append({"type": "step", "module": module, "phase": phase,
                          "summary": summary_text, "body": body, "is_key": is_key})
            continue

        if cl == "dimension":
            body = [line]
            i += 1
            while i < n and classify_line(lines[i]) in ("reasoning", "query_line", "blank", "body"):
                body.append(lines[i])
                i += 1
            steps.append({"type": "dimension", "module": "query_processing", "phase": "Query Processing",
                          "summary": line.strip(), "body": body, "is_key": False})
            continue

        if cl == "raw_message":
            body = [line]
            i += 1
            steps.append({"type": "raw", "module": "LLM Response", "phase": "Risk Intelligence",
                          "summary": "Raw LLM tool_use response (click to expand)", "body": body, "is_key": False})
            continue

        if cl in ("chain_detail", "body"):
            if steps and steps[-1]["type"] in ("step", "dimension"):
                steps[-1]["body"].append(line)
            i += 1
            continue

        i += 1

    return steps


# ── Visit merging (v2 only) ─────────────────────────────────────────────

def merge_gap_visits(visits: list[tuple]) -> list[tuple]:
    """Merge gap-related visits into a single Gap Analysis visit."""
    GAP_PHASE = "Gap Analysis"

    # Find first and last gap visit
    first_gap = None
    last_gap = None
    for i, (phase, _) in enumerate(visits):
        if phase == GAP_PHASE:
            if first_gap is None:
                first_gap = i
            last_gap = i

    if first_gap is None:
        return visits  # No gap visits

    # Collect gap steps and defer interleaved non-gap visits
    result = list(visits[:first_gap])
    gap_steps = []
    deferred = []

    for i in range(first_gap, last_gap + 1):
        phase, group = visits[i]
        if phase == GAP_PHASE:
            gap_steps.extend(group)
        else:
            deferred.append((phase, group))

    result.append((GAP_PHASE, gap_steps))
    result.extend(deferred)
    result.extend(visits[last_gap + 1:])

    return result


# ── HTML Renderer (v2: gap-aware) ───────────────────────────────────────

def render_html(steps: list[dict], log_path: str, query: str) -> str:
    # Build visits (consecutive same-phase runs)
    visits = []
    cur_phase = None
    cur_group = []
    for step in steps:
        p = step["phase"]
        if p != cur_phase:
            if cur_group:
                visits.append((cur_phase, cur_group))
            cur_phase = p
            cur_group = [step]
        else:
            cur_group.append(step)
    if cur_group:
        visits.append((cur_phase, cur_group))

    # v2: merge gap visits
    visits = merge_gap_visits(visits)

    total_visits = len(visits)
    total_steps = sum(len(g) for _, g in visits)
    key_steps = sum(1 for _, g in visits for s in g if s.get("is_key"))

    # Visit metadata JSON for JS
    visit_meta_js = json.dumps([
        {"phase": phase, "count": len(group),
         "keys": sum(1 for s in group if s.get("is_key"))}
        for phase, group in visits
    ])

    # Phase stats (aggregate)
    phase_stats = {}
    for phase, group in visits:
        if phase not in phase_stats:
            phase_stats[phase] = {"total": 0, "key": 0, "visits": 0}
        phase_stats[phase]["total"] += len(group)
        phase_stats[phase]["key"] += sum(1 for s in group if s.get("is_key"))
        phase_stats[phase]["visits"] += 1

    parts = []
    parts.append(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Pipeline Trace v2 — {html.escape(query[:60])}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: 'SF Mono', 'Consolas', 'Monaco', monospace; background: #0f172a; color: #e2e8f0; font-size: 13px; display: flex; flex-direction: column; height: 100vh; overflow: hidden; }}

/* ── Top bar ── */
.top-bar {{
    background: #1e293b; border-bottom: 1px solid #334155;
    padding: 8px 16px;
    display: flex; align-items: center; gap: 12px; flex-shrink: 0;
}}
.top-bar h1 {{ font-size: 13px; color: #f8fafc; white-space: nowrap; }}
.top-bar .query {{ color: #94a3b8; font-size: 11px; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.top-bar .stats {{ color: #64748b; font-size: 10px; white-space: nowrap; }}

/* ── Controls bar ── */
.controls {{
    background: #1e293b; border-bottom: 1px solid #334155;
    padding: 5px 16px;
    display: flex; align-items: center; gap: 8px; flex-shrink: 0;
}}
.btn {{ background: #334155; color: #e2e8f0; border: 1px solid #475569; border-radius: 4px; padding: 3px 10px; font-size: 11px; cursor: pointer; font-family: inherit; }}
.btn:hover {{ background: #475569; }}
.visit-label {{
    font-size: 11px; padding: 3px 10px; border-radius: 4px;
    font-weight: 600; min-width: 260px; text-align: center;
}}
.step-counter {{ color: #64748b; font-size: 11px; }}
.sep {{ width: 1px; height: 18px; background: #334155; }}

/* ── Main layout ── */
.main {{ display: flex; flex: 1; overflow: hidden; }}

/* ── Left panel ── */
.left-panel {{
    width: 220px; min-width: 220px;
    display: flex; flex-direction: column;
    border-right: 1px solid #1e293b;
    flex-shrink: 0;
}}

/* Flowchart section */
.flowchart {{ padding: 10px 8px; flex-shrink: 0; }}

.flow-node {{
    position: relative;
    padding: 6px 8px; margin: 0;
    border-radius: 7px;
    border: 2px solid #1e293b;
    cursor: pointer;
    transition: all 0.3s ease;
    display: flex; align-items: center; gap: 6px;
    z-index: 1;
}}
.flow-node:hover {{ border-color: #475569; background: #1e293b; }}
.flow-node.active {{
    border-color: var(--phase-color);
    border-width: 2.5px;
    background: color-mix(in srgb, var(--phase-color) 15%, #0f172a);
    box-shadow: 0 0 16px color-mix(in srgb, var(--phase-color) 50%, transparent);
    animation: pulse-glow 2s ease-in-out infinite;
}}
@keyframes pulse-glow {{
    0%, 100% {{ box-shadow: 0 0 12px color-mix(in srgb, var(--phase-color) 40%, transparent); }}
    50% {{ box-shadow: 0 0 22px color-mix(in srgb, var(--phase-color) 65%, transparent), 0 0 8px color-mix(in srgb, var(--phase-color) 35%, transparent); }}
}}
.flow-node.visited {{ border-color: #334155; background: #1e293b44; }}
.flow-node.visited .flow-label {{ color: #64748b; }}
.flow-node.visited .flow-icon {{ opacity: 0.5; }}
.flow-icon {{ font-size: 13px; flex-shrink: 0; width: 18px; text-align: center; }}
.flow-label {{ font-size: 10px; font-weight: 600; color: #94a3b8; line-height: 1.2; }}
.flow-node.active .flow-label {{ color: var(--phase-color); font-weight: 700; }}
.flow-count {{ font-size: 9px; color: #475569; margin-left: auto; white-space: nowrap; }}
.flow-node.active .flow-count {{ color: var(--phase-color); opacity: 0.8; }}

.flow-connector {{
    display: flex; align-items: center; justify-content: center;
    height: 18px; position: relative; margin: 0;
}}
.flow-connector::before {{
    content: '';
    position: absolute; left: 50%; top: 0; bottom: 0;
    width: 2px; background: #1e293b;
    transform: translateX(-50%);
}}
.flow-connector .arrow-head {{
    width: 0; height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #334155;
    z-index: 1; position: relative;
}}
.flow-connector.active::before {{ background: var(--phase-color); opacity: 0.6; }}
.flow-connector.active .arrow-head {{ border-top-color: var(--phase-color); }}

.flow-progress {{
    position: absolute; bottom: 0; left: 0; height: 2px;
    background: var(--phase-color); border-radius: 0 0 6px 6px;
    transition: width 0.3s ease;
}}

/* ── Visit trail ── */
.trail-divider {{ height: 1px; background: #1e293b; margin: 4px 8px; }}
.trail-header {{ font-size: 9px; color: #475569; padding: 4px 10px; text-transform: uppercase; letter-spacing: 0.1em; }}
.visit-trail {{ flex: 1; overflow-y: auto; padding: 0 4px 8px; }}

.visit-item {{
    display: flex; align-items: center; gap: 6px;
    padding: 3px 8px; margin: 1px 0;
    border-left: 3px solid transparent;
    border-radius: 0 4px 4px 0;
    cursor: pointer; font-size: 10px;
    transition: all 0.15s;
}}
.visit-item:hover {{ background: #1e293b; }}
.visit-item.active {{
    background: color-mix(in srgb, var(--vc) 12%, #0f172a);
    border-left-color: var(--vc);
}}
.visit-item.past {{ opacity: 0.45; }}
.visit-num {{ color: #475569; width: 18px; text-align: right; font-size: 9px; }}
.visit-item.active .visit-num {{ color: var(--vc); font-weight: 700; }}
.visit-phase {{ color: #94a3b8; flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.visit-item.active .visit-phase {{ color: var(--vc); font-weight: 600; }}
.visit-steps {{ color: #475569; font-size: 9px; }}
.visit-item.active .visit-steps {{ color: var(--vc); }}

/* ── Right panel ── */
.right-panel {{ flex: 1; overflow-y: auto; padding: 12px 16px 80px; }}

.visit-block {{ display: none; }}
.visit-block.active {{ display: block; }}

.visit-header {{
    padding: 8px 12px; border-radius: 6px; margin-bottom: 8px;
    font-size: 12px; font-weight: 600;
    display: flex; align-items: center; gap: 8px;
}}
.visit-header .vh-icon {{ font-size: 16px; }}
.visit-header .vh-phase {{ flex: 1; }}
.visit-header .vh-meta {{ font-size: 10px; font-weight: 400; opacity: 0.7; }}

.step-card {{
    border-left: 3px solid #1e293b;
    margin: 0 0 1px 8px;
    padding: 3px 10px;
    transition: all 0.15s;
    cursor: pointer;
}}
.step-card:hover {{ background: #1e293b; }}
.step-card.key {{ border-left-color: #f59e0b; }}
.step-card.expanded {{ background: #1e293b; }}
.step-card.highlight {{ background: #172554; border-left-color: #60a5fa; }}

.step-summary {{ display: flex; align-items: baseline; gap: 6px; }}
.step-module {{
    font-size: 9px; padding: 1px 5px; border-radius: 3px;
    font-weight: 600; white-space: nowrap; flex-shrink: 0;
}}
.step-text {{
    font-size: 11px; color: #cbd5e1;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}}
.step-text.key-text {{ color: #fbbf24; font-weight: 600; }}

.step-body {{
    display: none; margin-top: 4px; padding: 6px 8px;
    background: #0f172a; border-radius: 4px; border: 1px solid #1e293b;
    white-space: pre-wrap; font-size: 10px; color: #94a3b8;
    max-height: 350px; overflow-y: auto; line-height: 1.5;
}}
.step-card.expanded .step-body {{ display: block; }}

.hidden {{ display: none !important; }}

/* ── v2: Gap Analysis styles ── */
.gap-summary {{
    background: #1e293b; border: 1px solid #334155; border-radius: 8px;
    padding: 10px 14px; margin-bottom: 12px;
}}
.gap-summary-title {{
    font-size: 12px; font-weight: 700; margin-bottom: 8px;
    display: flex; align-items: center; gap: 8px;
}}
.gap-summary-rating {{
    font-size: 10px; padding: 2px 8px; border-radius: 10px; font-weight: 600;
}}
.gap-table {{ width: 100%; border-collapse: collapse; }}
.gap-table td {{
    padding: 3px 6px; font-size: 10px; border-bottom: 1px solid #1e293b22;
}}
.gap-table td:first-child {{ width: 16px; text-align: center; }}
.gap-table td:nth-child(2) {{ color: #cbd5e1; }}
.gap-table td:nth-child(3) {{ text-align: right; font-weight: 600; font-size: 9px; }}
.gap-table td:nth-child(4) {{ color: #64748b; font-size: 9px; text-align: right; }}
.gap-row-covered td:first-child {{ color: #10b981; }}
.gap-row-covered td:nth-child(3) {{ color: #10b981; }}
.gap-row-gap td:first-child {{ color: #f59e0b; }}
.gap-row-gap td:nth-child(3) {{ color: #f59e0b; }}

.gap-group {{
    margin: 10px 0 4px;
    border-left: 3px solid var(--gc);
    padding-left: 6px;
}}
.gap-group-hdr {{
    display: flex; align-items: center; gap: 8px;
    padding: 5px 8px; border-radius: 4px;
    font-size: 11px; font-weight: 600;
    background: color-mix(in srgb, var(--gc) 10%, #0f172a);
    color: var(--gc);
}}
.gap-group-hdr .gg-label {{ flex: 1; }}
.gap-group-hdr .gg-method {{ font-size: 9px; font-weight: 400; opacity: 0.7; }}
.gap-group-hdr .gg-status {{
    font-size: 9px; padding: 2px 8px; border-radius: 10px; font-weight: 600;
}}
.gap-missing {{
    font-size: 10px; color: #94a3b8; padding: 2px 8px 4px; font-style: italic;
}}
</style>
</head>
<body>

<div class="top-bar">
    <h1>Pipeline Trace v2</h1>
    <div class="query">{html.escape(query)}</div>
    <div class="stats">{total_steps} steps &middot; {key_steps} key &middot; {total_visits} visits &middot; {html.escape(Path(log_path).name)}</div>
</div>

<div class="controls">
    <button class="btn" onclick="navVisit(-1)" title="Left / h">&#9664; Visit</button>
    <button class="btn" onclick="navVisit(1)" title="Right / l">Visit &#9654;</button>
    <div class="visit-label" id="visitLabel" style="background:#33415520;color:#94a3b8;">Visit 0/{total_visits}</div>
    <div class="sep"></div>
    <button class="btn" onclick="navStep(-1)" title="Up / k">&#9650; Step</button>
    <button class="btn" onclick="navStep(1)" title="Down / j">&#9660; Step</button>
    <button class="btn" onclick="navKey(-1)" title="p">&#9664; Key</button>
    <button class="btn" onclick="navKey(1)" title="n">Key &#9654;</button>
    <span class="step-counter" id="stepCounter"></span>
    <span style="flex:1"></span>
    <label style="color:#94a3b8;font-size:11px;cursor:pointer;"><input type="checkbox" id="showOnlyKey" onchange="filterSteps()" style="margin-right:2px;"> Key only</label>
</div>

<div class="main">

<!-- ── Left: Flowchart + Visit trail ── -->
<div class="left-panel">
<div class="flowchart" id="flowchart">
""")

    # Render flowchart nodes
    for idx, phase in enumerate(PHASE_ORDER):
        color = PHASE_COLORS.get(phase, "#64748b")
        icon = PHASE_ICONS.get(phase, "&#x25CB;")
        short = PHASE_SHORT.get(phase, phase)
        stats = phase_stats.get(phase, {"total": 0, "key": 0, "visits": 0})
        pid = phase.replace(" ", "_").replace("&", "").replace(".", "")

        parts.append(f'  <div class="flow-node" id="fn_{pid}" style="--phase-color:{color};" data-phase="{html.escape(phase)}" onclick="goToFirstVisit(\'{html.escape(phase)}\')">\n')
        parts.append(f'    <span class="flow-icon">{icon}</span>\n')
        parts.append(f'    <span class="flow-label">{html.escape(short)}</span>\n')
        parts.append(f'    <span class="flow-count">{stats["total"]}</span>\n')
        parts.append(f'    <div class="flow-progress" id="fp_{pid}" style="width:0%"></div>\n')
        parts.append(f'  </div>\n')

        if idx < len(PHASE_ORDER) - 1:
            parts.append(f'  <div class="flow-connector" id="fa_{pid}" style="--phase-color:{color};"><div class="arrow-head"></div></div>\n')

    parts.append('</div>\n')

    # Visit trail
    parts.append('<div class="trail-divider"></div>\n')
    parts.append(f'<div class="trail-header">Execution Flow ({total_visits} visits)</div>\n')
    parts.append('<div class="visit-trail" id="visitTrail">\n')

    for vi, (phase_name, group) in enumerate(visits):
        color = PHASE_COLORS.get(phase_name, "#64748b")
        short = PHASE_SHORT.get(phase_name, phase_name)
        kc = sum(1 for s in group if s.get("is_key"))
        count_text = str(len(group)) + (f"/{kc}\u2605" if kc else "")
        parts.append(f'  <div class="visit-item" id="vi_{vi}" style="--vc:{color};" data-visit="{vi}" onclick="goToVisit({vi})">\n')
        parts.append(f'    <span class="visit-num">{vi + 1}</span>\n')
        parts.append(f'    <span class="visit-phase">{html.escape(short)}</span>\n')
        parts.append(f'    <span class="visit-steps">{count_text}</span>\n')
        parts.append(f'  </div>\n')

    parts.append('</div>\n</div>\n\n')

    # ── Right panel: visit blocks ──
    parts.append('<!-- ── Right: Steps ── -->\n<div class="right-panel" id="rightPanel">\n')

    global_idx = 0
    for vi, (phase_name, group) in enumerate(visits):
        color = PHASE_COLORS.get(phase_name, "#64748b")
        icon = PHASE_ICONS.get(phase_name, "&#x25CB;")
        active_cls = " active" if vi == 0 else ""

        parts.append(f'<div class="visit-block{active_cls}" data-visit="{vi}">\n')
        parts.append(f'<div class="visit-header" style="background:{color}15; color:{color};">\n')
        parts.append(f'  <span class="vh-icon">{icon}</span>\n')
        parts.append(f'  <span class="vh-phase">{html.escape(phase_name)}</span>\n')
        parts.append(f'  <span class="vh-meta">Visit {vi + 1}/{total_visits} &middot; {len(group)} steps</span>\n')
        parts.append(f'</div>\n')

        if phase_name == "Gap Analysis":
            # v2: Render gap-organized content
            gap_groups, gap_json = organize_gap_steps(group)

            # Gap summary table
            if gap_json:
                rating = gap_json.get("coverage_rating", "?")
                gap_count = gap_json.get("gap_count", 0)
                r_color = {"COMPLETE": "#10b981", "PARTIAL": "#f59e0b", "INSUFFICIENT": "#ef4444"}.get(rating, "#64748b")
                parts.append(f'<div class="gap-summary">\n')
                parts.append(f'  <div class="gap-summary-title">Knowledge Gap Assessment '
                             f'<span class="gap-summary-rating" style="background:{r_color}20;color:{r_color};">'
                             f'{html.escape(rating)} ({gap_count} gaps)</span></div>\n')
                parts.append(f'  <table class="gap-table">\n')
                for gap in gap_json.get("gaps", []):
                    cat = gap.get("category", "?")
                    status = gap.get("status", "?")
                    fm = gap.get("fill_method", "")
                    label = GAP_LABELS.get(cat, cat)
                    row_cls = "gap-row-covered" if status == "COVERED" else "gap-row-gap"
                    check = "&#x2713;" if status == "COVERED" else "&#x2717;"
                    method_text = f"&rarr; {html.escape(fm)}" if status == "GAP" else ""
                    parts.append(f'    <tr class="{row_cls}"><td>{check}</td>'
                                 f'<td>{html.escape(label)}</td>'
                                 f'<td>{html.escape(status)}</td>'
                                 f'<td>{method_text}</td></tr>\n')
                parts.append(f'  </table>\n')
                parts.append(f'</div>\n')

            # Render each gap group with header
            for gname, gsteps in gap_groups:
                gc = GAP_GROUP_COLORS.get(gname, "#64748b")
                glabel = GAP_LABELS.get(gname, gname)
                gap_info = get_gap_info(gap_json, gname)
                fm = gap_info.get("fill_method", "")
                missing = gap_info.get("missing", "")
                status = detect_group_status(gsteps)

                parts.append(f'<div class="gap-group" style="--gc:{gc};">\n')
                parts.append(f'<div class="gap-group-hdr">\n')
                parts.append(f'  <span class="gg-label">{html.escape(glabel)}</span>\n')
                if fm:
                    parts.append(f'  <span class="gg-method">{html.escape(fm)}</span>\n')
                if status:
                    sc = {"FILLED": "#10b981", "UNFILLABLE": "#ef4444", "PARTIAL": "#f59e0b", "ERROR": "#ef4444"}.get(status, "#64748b")
                    parts.append(f'  <span class="gg-status" style="background:{sc}20;color:{sc};">{html.escape(status)}</span>\n')
                parts.append(f'</div>\n')
                if missing:
                    parts.append(f'<div class="gap-missing">{html.escape(missing[:200])}</div>\n')

                # Step cards within group
                for step in gsteps:
                    module = step["module"]
                    mod_color = MODULE_COLORS.get(module, PHASE_COLORS.get(phase_name, "#64748b"))
                    is_key = step.get("is_key", False)
                    key_cls = " key" if is_key else ""
                    text_cls = " key-text" if is_key else ""
                    summary = step["summary"]
                    if len(summary) > 180:
                        summary = summary[:177] + "..."
                    body_text = html.escape("\n".join(step["body"]))
                    parts.append(f'<div class="step-card{key_cls}" data-idx="{global_idx}" data-key="{1 if is_key else 0}" onclick="toggleStep(this)">\n')
                    parts.append(f'  <div class="step-summary">\n')
                    parts.append(f'    <span class="step-module" style="background:{mod_color}18; color:{mod_color};">{html.escape(module[:28])}</span>\n')
                    parts.append(f'    <span class="step-text{text_cls}">{html.escape(summary)}</span>\n')
                    parts.append(f'  </div>\n')
                    parts.append(f'  <div class="step-body">{body_text}</div>\n')
                    parts.append(f'</div>\n')
                    global_idx += 1

                parts.append(f'</div>\n')  # close gap-group
        else:
            # Normal visit rendering (same as v1)
            for step in group:
                module = step["module"]
                mod_color = MODULE_COLORS.get(module, PHASE_COLORS.get(phase_name, "#64748b"))
                is_key = step.get("is_key", False)
                key_cls = " key" if is_key else ""
                text_cls = " key-text" if is_key else ""
                summary = step["summary"]
                if len(summary) > 180:
                    summary = summary[:177] + "..."
                body_text = html.escape("\n".join(step["body"]))
                parts.append(f'<div class="step-card{key_cls}" data-idx="{global_idx}" data-key="{1 if is_key else 0}" onclick="toggleStep(this)">\n')
                parts.append(f'  <div class="step-summary">\n')
                parts.append(f'    <span class="step-module" style="background:{mod_color}18; color:{mod_color};">{html.escape(module[:28])}</span>\n')
                parts.append(f'    <span class="step-text{text_cls}">{html.escape(summary)}</span>\n')
                parts.append(f'  </div>\n')
                parts.append(f'  <div class="step-body">{body_text}</div>\n')
                parts.append(f'</div>\n')
                global_idx += 1

        parts.append('</div>\n')

    parts.append(f"""</div>
</div>

<script>
const visits = {visit_meta_js};
const totalVisits = {total_visits};
const PHASE_ORDER = {json.dumps(PHASE_ORDER)};
const PHASE_COLORS = {json.dumps(PHASE_COLORS)};
const PHASE_SHORT = {json.dumps(PHASE_SHORT)};
let currentVisit = 0;
let currentStep = -1;

function phaseId(phase) {{
    return phase.replace(/ /g, '_').replace(/&/g, '').replace(/\\./g, '');
}}

// ── Visit navigation ──

function goToVisit(idx) {{
    if (idx < 0 || idx >= totalVisits) return;
    currentVisit = idx;
    currentStep = -1;

    document.querySelectorAll('.visit-block').forEach(b => {{
        b.classList.toggle('active', parseInt(b.dataset.visit) === idx);
    }});

    document.querySelectorAll('.step-card.highlight, .step-card.expanded').forEach(c => {{
        c.classList.remove('highlight', 'expanded');
    }});

    document.querySelectorAll('.visit-item').forEach(item => {{
        const vi = parseInt(item.dataset.visit);
        item.classList.toggle('active', vi === idx);
        item.classList.toggle('past', vi < idx);
    }});
    const activeItem = document.getElementById('vi_' + idx);
    if (activeItem) activeItem.scrollIntoView({{ behavior: 'auto', block: 'nearest' }});

    highlightPhase(visits[idx].phase);
    updateVisitLabel();
    updateStepCounter();

    document.querySelectorAll('.flow-progress').forEach(b => b.style.width = '0%');
    document.getElementById('rightPanel').scrollTop = 0;
}}

function goToFirstVisit(phase) {{
    let idx = -1;
    for (let i = currentVisit; i < totalVisits; i++) {{
        if (visits[i].phase === phase) {{ idx = i; break; }}
    }}
    if (idx === -1) {{
        for (let i = 0; i < currentVisit; i++) {{
            if (visits[i].phase === phase) {{ idx = i; break; }}
        }}
    }}
    if (idx >= 0) goToVisit(idx);
}}

function navVisit(dir) {{ goToVisit(currentVisit + dir); }}

// ── Flowchart ──

function highlightPhase(phase) {{
    document.querySelectorAll('.flow-node').forEach(n => n.classList.remove('active', 'visited'));
    document.querySelectorAll('.flow-connector').forEach(a => {{
        a.classList.remove('active');
        a.style.removeProperty('--phase-color');
    }});

    if (!phase) return;

    const pid = phaseId(phase);
    const node = document.getElementById('fn_' + pid);
    if (node) {{
        node.classList.add('active');
        const visitedPhases = new Set();
        for (let i = 0; i < currentVisit; i++) visitedPhases.add(visits[i].phase);
        visitedPhases.delete(phase);
        visitedPhases.forEach(p => {{
            const el = document.getElementById('fn_' + phaseId(p));
            if (el) el.classList.add('visited');
        }});
        node.scrollIntoView({{ behavior: 'auto', block: 'nearest' }});
    }}

    const phaseIdx = PHASE_ORDER.indexOf(phase);
    if (phaseIdx > 0) {{
        const prevPid = phaseId(PHASE_ORDER[phaseIdx - 1]);
        const arrow = document.getElementById('fa_' + prevPid);
        if (arrow) {{
            arrow.classList.add('active');
            arrow.style.setProperty('--phase-color', PHASE_COLORS[phase] || '#64748b');
        }}
    }}
}}

// ── Step navigation (within visit) ──

function getVisibleSteps() {{
    const block = document.querySelector('.visit-block.active');
    if (!block) return [];
    const keyOnly = document.getElementById('showOnlyKey').checked;
    return [...block.querySelectorAll('.step-card')].filter(c => !keyOnly || c.dataset.key === '1');
}}

function activateStep(card, stepIdx) {{
    document.querySelectorAll('.step-card.highlight, .step-card.expanded').forEach(c => {{
        c.classList.remove('highlight', 'expanded');
    }});
    card.classList.add('highlight', 'expanded');
    card.scrollIntoView({{ behavior: 'auto', block: 'center' }});
    currentStep = stepIdx;

    const phase = visits[currentVisit].phase;
    const total = getVisibleSteps().length;
    const pid = phaseId(phase);
    const bar = document.getElementById('fp_' + pid);
    if (bar) bar.style.width = Math.min(100, Math.round(((stepIdx + 1) / total) * 100)) + '%';

    updateStepCounter();
}}

function toggleStep(el) {{
    if (el.classList.contains('expanded') && el.classList.contains('highlight')) {{
        el.classList.remove('expanded', 'highlight');
        currentStep = -1;
    }} else {{
        const cards = getVisibleSteps();
        activateStep(el, cards.indexOf(el));
    }}
    updateStepCounter();
}}

function navStep(dir) {{
    const cards = getVisibleSteps();
    if (!cards.length) return;
    const next = currentStep + dir;
    if (next < 0 || next >= cards.length) return;
    activateStep(cards[next], next);
}}

function navKey(dir) {{
    const allCards = getVisibleSteps();
    const keyCards = allCards.filter(c => c.dataset.key === '1');

    if (keyCards.length > 0) {{
        let pos = -1;
        if (currentStep >= 0) {{
            const currentCard = allCards[currentStep];
            pos = keyCards.indexOf(currentCard);
        }}
        const target = (pos === -1) ? (dir > 0 ? 0 : keyCards.length - 1) : pos + dir;
        if (target >= 0 && target < keyCards.length) {{
            activateStep(keyCards[target], allCards.indexOf(keyCards[target]));
            return;
        }}
    }}

    let vi = currentVisit + dir;
    while (vi >= 0 && vi < totalVisits) {{
        if (visits[vi].keys > 0) {{
            goToVisit(vi);
            const newAll = getVisibleSteps();
            const newKeys = newAll.filter(c => c.dataset.key === '1');
            if (newKeys.length) {{
                const pick = dir > 0 ? newKeys[0] : newKeys[newKeys.length - 1];
                activateStep(pick, newAll.indexOf(pick));
            }}
            return;
        }}
        vi += dir;
    }}
}}

function filterSteps() {{
    const keyOnly = document.getElementById('showOnlyKey').checked;
    document.querySelectorAll('.step-card').forEach(card => {{
        card.classList.toggle('hidden', keyOnly && card.dataset.key !== '1');
    }});
    currentStep = -1;
    updateStepCounter();
}}

// ── UI updates ──

function updateVisitLabel() {{
    const v = visits[currentVisit];
    const short = PHASE_SHORT[v.phase] || v.phase;
    const color = PHASE_COLORS[v.phase] || '#64748b';
    const label = document.getElementById('visitLabel');
    label.textContent = 'Visit ' + (currentVisit + 1) + '/' + totalVisits + ': ' + short + ' (' + v.count + ' steps)';
    label.style.background = color + '20';
    label.style.color = color;
}}

function updateStepCounter() {{
    const cards = getVisibleSteps();
    const counter = document.getElementById('stepCounter');
    if (currentStep >= 0 && currentStep < cards.length) {{
        counter.textContent = 'Step ' + (currentStep + 1) + '/' + cards.length;
    }} else {{
        counter.textContent = cards.length + ' steps';
    }}
}}

// ── Keyboard ──

document.addEventListener('keydown', (e) => {{
    if (e.target.tagName === 'INPUT') return;
    switch (e.key) {{
        case 'ArrowRight': case 'l': e.preventDefault(); navVisit(1); break;
        case 'ArrowLeft': case 'h': e.preventDefault(); navVisit(-1); break;
        case 'ArrowDown': case 'j': e.preventDefault(); navStep(1); break;
        case 'ArrowUp': case 'k': e.preventDefault(); navStep(-1); break;
        case 'n': navKey(1); break;
        case 'p': navKey(-1); break;
        case 'Escape': goToVisit(currentVisit); break;
    }}
}});

// Initialize
goToVisit(0);
</script>
</body>
</html>""")

    return "".join(parts)


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: python tools/log_viewer_v2.py <log_file> [-o output.html]")
        sys.exit(1)

    log_path = sys.argv[1]
    output_path = None
    if "-o" in sys.argv:
        idx = sys.argv.index("-o")
        if idx + 1 < len(sys.argv):
            output_path = sys.argv[idx + 1]

    log_file = Path(log_path)
    if not log_file.exists():
        print(f"File not found: {log_path}")
        sys.exit(1)

    lines = log_file.read_text(encoding="utf-8").splitlines()

    query = "Unknown query"
    for line in lines[:10]:
        if line.strip().startswith("Query:"):
            query = line.strip()[6:].strip()
            break

    steps = parse_log(lines)
    html_out = render_html(steps, log_path, query)

    if not output_path:
        output_path = str(log_file.with_suffix("")) + "_v2.html"

    Path(output_path).write_text(html_out, encoding="utf-8")

    # Count gap groups
    gap_groups = 0
    for step in steps:
        if step["phase"] == "Gap Analysis":
            gap_groups += 1

    print(f"Generated: {output_path}")
    print(f"  Steps: {len(steps)}")
    print(f"  Key steps: {sum(1 for s in steps if s.get('is_key'))}")
    print(f"  Phases: {len(set(s['phase'] for s in steps))}")
    print(f"  Gap-related steps: {gap_groups}")


if __name__ == "__main__":
    main()
