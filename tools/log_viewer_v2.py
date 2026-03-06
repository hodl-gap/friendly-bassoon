"""
Pipeline Log Viewer v2 — Agentic pipeline visualization.

Designed for the 4-phase ReAct agent architecture:
  Phase 1: Retrieval Agent (agentic search + coverage assessment)
  Phase 2: Data Grounding Agent (variable extraction + data fetching)
  Phase 3: Historical Context Agent (analog detection + regime characterization)
  Phase 4: Synthesis (Opus generate + Sonnet self-check)
  Output: Tracks, synthesis, current data, condensed summary, LLM usage

Groups by phases → iterations → tool calls instead of visits + steps.

Usage:
    python tools/log_viewer_v2.py logs/run_20260226_025056.log
    python tools/log_viewer_v2.py logs/run_20260226_025056.log -o my_view.html
"""

import re
import sys
import html
import json
from pathlib import Path
from dataclasses import dataclass, field


# ── Data model ───────────────────────────────────────────────────────────

@dataclass
class SubLog:
    tag: str
    text: str


@dataclass
class ToolCall:
    tool_name: str
    arguments: str
    result_preview: str = ""
    sub_logs: list[SubLog] = field(default_factory=list)


@dataclass
class Iteration:
    number: int
    max_iterations: int
    thinking: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass
class LogEntry:
    tag: str
    lines: list[str] = field(default_factory=list)


@dataclass
class CoverageResult:
    rating: str = ""
    flags_met: int = 0
    flags_total: int = 0
    flags: list[tuple[bool, str]] = field(default_factory=list)


@dataclass
class Phase:
    name: str
    phase_number: int
    iterations: list[Iteration] = field(default_factory=list)
    post_processing: list[LogEntry] = field(default_factory=list)
    completion_note: str = ""


@dataclass
class Track:
    number: int
    title: str
    confidence: int = 0
    mechanism: str = ""
    time_horizon: str = ""
    phase_num: int = 0
    evidence: str = ""
    asset_implications: list[str] = field(default_factory=list)
    monitor: list[str] = field(default_factory=list)


@dataclass
class OutputSection:
    asset: str = ""
    tracks: list[Track] = field(default_factory=list)
    synthesis: str = ""
    uncertainties: list[str] = field(default_factory=list)
    current_data: str = ""
    condensed: str = ""


@dataclass
class LLMModelUsage:
    model: str = ""
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0


@dataclass
class PipelineRun:
    query: str = ""
    timestamp: str = ""
    log_path: str = ""
    phases: list[Phase] = field(default_factory=list)
    output: OutputSection = field(default_factory=OutputSection)
    llm_usage: list[LLMModelUsage] = field(default_factory=list)
    total_cost: float = 0.0
    total_tokens: int = 0
    duration: str = ""


# ── Parser ───────────────────────────────────────────────────────────────

# Regex patterns
RE_PHASE_START = {
    1: re.compile(r'\[Retrieval Agent\] Starting agentic retrieval'),
    2: re.compile(r'\[Data Grounding Agent\] Starting agentic data grounding'),
    3: re.compile(r'\[Historical Context Agent\] Starting agentic historical'),
    4: re.compile(r'\[Synthesis Phase\] Starting'),
}
RE_ITERATION = re.compile(r'\[Agent Loop\] Iteration (\d+)/(\d+)')
RE_AGENT_THINK = re.compile(r'\[Agent Loop\] Agent: (.+)')
RE_TOOL_CALL = re.compile(r'\[Agent Loop\] Tool call: (\w+)\((.+)')
RE_TOOL_RESULT = re.compile(r'\[Agent Loop\] Result: (.+)')
RE_EXIT_TOOL = re.compile(r'\[Agent Loop\] Exit tool called after (\d+)')
RE_MAX_ITER = re.compile(r'\[Agent Loop\] Max iterations \((\d+)\) reached')
RE_PHASE_COMPLETE = re.compile(r'\[(Retrieval Agent|Data Grounding Agent|Historical Context Agent)\] Completed')
RE_COVERAGE = re.compile(r'\[Coverage\] (\w+) \((\d+)/(\d+) flags?\)')
RE_COVERAGE_FLAG = re.compile(r'^\s+\[(Y|N)\] (.+)')
RE_TRACK = re.compile(r'^TRACK (\d+): (.+)')
RE_CONFIDENCE = re.compile(r'^\s+Confidence: (\d+)%')
RE_MECHANISM = re.compile(r'^\s+Mechanism: (.+)')
RE_TIME_HORIZON = re.compile(r'^\s+Time Horizon: (.+)')
RE_PHASE_LINE = re.compile(r'^\s+Phase: (\d+)')
RE_EVIDENCE = re.compile(r'^\s+Evidence: (.+)')
RE_SUB_LOG = re.compile(r'^\[([^\]]+)\] (.+)')
RE_HTTPX = re.compile(r'^\d{4}-\d{2}-\d{2}.*httpx.*HTTP Request')
RE_LLM_MODEL = re.compile(r'^(HAIKU|OPUS|SONNET):$')
RE_LLM_CALLS = re.compile(r'^Calls:\s+(\d+)')
RE_LLM_INPUT = re.compile(r'^Input:\s+([\d,]+) tokens')
RE_LLM_OUTPUT = re.compile(r'^Output:\s+([\d,]+) tokens')
RE_LLM_COST = re.compile(r'^Cost:\s+\$([\d.]+)')
RE_TOTAL_COST = re.compile(r'^Cost:\s+\$([\d.]+)')
RE_TOTAL_TOKENS = re.compile(r'^Tokens:\s+([\d,]+)')
RE_DURATION = re.compile(r'^Pipeline duration: ([\d.]+)s')


def is_separator(line: str) -> bool:
    s = line.strip()
    return bool(s) and all(c in '=-#' for c in s) and len(s) >= 10


def parse_log(lines: list[str]) -> PipelineRun:
    run = PipelineRun()
    n = len(lines)
    i = 0

    # Parse header
    while i < n and i < 15:
        line = lines[i].strip()
        if line.startswith("Pipeline Run:"):
            run.timestamp = line.replace("Pipeline Run:", "").strip()
        elif line.startswith("Query:"):
            run.query = line[6:].strip()
            # Multi-line query
            i += 1
            while i < n and lines[i].strip() and not is_separator(lines[i]):
                if lines[i].strip().startswith("Trader query:"):
                    break
                run.query += "\n" + lines[i].strip()
                i += 1
            continue
        elif line.startswith("Trader query:"):
            pass  # Skip, already have the data query
        i += 1

    # State machine
    current_phase: Phase | None = None
    current_iter: Iteration | None = None
    current_tool: ToolCall | None = None
    in_post_processing = False
    in_output = False
    in_synthesis = False
    in_current_data = False
    in_uncertainties = False
    in_condensed = False
    in_llm_usage = False
    in_total = False
    current_track: Track | None = None
    current_track_section = ""  # "evidence", "implications", "monitor"
    current_llm_model: LLMModelUsage | None = None
    coverage_pending: CoverageResult | None = None
    synthesis_lines: list[str] = []
    current_data_lines: list[str] = []
    uncertainty_lines: list[str] = []
    condensed_lines: list[str] = []

    i = 0
    while i < n:
        line = lines[i]
        stripped = line.strip()

        # Skip httpx noise
        if RE_HTTPX.match(stripped):
            i += 1
            continue

        # Skip blank/separator in non-content contexts
        if not stripped and not (in_synthesis or in_current_data or in_condensed or in_output):
            i += 1
            continue

        # ── LLM USAGE SUMMARY ──
        if stripped == "LLM USAGE SUMMARY":
            in_llm_usage = True
            in_output = False
            in_synthesis = False
            in_current_data = False
            in_condensed = False
            if current_track:
                run.output.tracks.append(current_track)
                current_track = None
            i += 1
            continue

        if in_llm_usage:
            if stripped == "TOTAL:":
                in_total = True
                if current_llm_model:
                    run.llm_usage.append(current_llm_model)
                    current_llm_model = None
                i += 1
                continue

            if in_total:
                m = RE_TOTAL_COST.match(stripped)
                if m:
                    run.total_cost = float(m.group(1))
                m = RE_TOTAL_TOKENS.match(stripped)
                if m:
                    run.total_tokens = int(m.group(1).replace(",", ""))
                m = RE_DURATION.match(stripped)
                if m:
                    run.duration = m.group(1) + "s"
                i += 1
                continue

            m = RE_LLM_MODEL.match(stripped)
            if m:
                if current_llm_model:
                    run.llm_usage.append(current_llm_model)
                current_llm_model = LLMModelUsage(model=m.group(1))
                i += 1
                continue

            if current_llm_model:
                m = RE_LLM_CALLS.match(stripped)
                if m:
                    current_llm_model.calls = int(m.group(1))
                m = RE_LLM_INPUT.match(stripped)
                if m:
                    current_llm_model.input_tokens = int(m.group(1).replace(",", ""))
                m = RE_LLM_OUTPUT.match(stripped)
                if m:
                    current_llm_model.output_tokens = int(m.group(1).replace(",", ""))
                m = RE_LLM_COST.match(stripped)
                if m:
                    current_llm_model.cost = float(m.group(1))

            m = RE_DURATION.match(stripped)
            if m:
                run.duration = m.group(1) + "s"
                if current_llm_model:
                    run.llm_usage.append(current_llm_model)
                    current_llm_model = None

            i += 1
            continue

        # ── Duration after LLM usage ──
        m = RE_DURATION.match(stripped)
        if m:
            run.duration = m.group(1) + "s"
            i += 1
            continue

        # ── INSIGHT REPORT ──
        if "INSIGHT REPORT" in stripped and not stripped.startswith("["):
            in_output = True
            in_synthesis = False
            in_current_data = False
            in_condensed = False
            in_post_processing = False
            # Flush current phase
            if current_phase:
                if current_iter:
                    current_phase.iterations.append(current_iter)
                    current_iter = None
                run.phases.append(current_phase)
                current_phase = None
            # Extract asset name
            m2 = re.search(r'INSIGHT REPORT\s*--\s*(.+)', stripped)
            if m2:
                run.output.asset = m2.group(1).strip()
            i += 1
            continue

        # ── CONDENSED SUMMARY ──
        if "CONDENSED SUMMARY" in stripped and not stripped.startswith("["):
            if current_track:
                run.output.tracks.append(current_track)
                current_track = None
            if in_synthesis:
                run.output.synthesis = "\n".join(synthesis_lines).strip()
                in_synthesis = False
            if in_current_data:
                run.output.current_data = "\n".join(current_data_lines).strip()
                in_current_data = False
            if in_uncertainties:
                in_uncertainties = False
            in_condensed = True
            in_output = False
            i += 1
            continue

        # ── Inside condensed ──
        if in_condensed:
            if stripped == "LLM USAGE SUMMARY":
                run.output.condensed = "\n".join(condensed_lines).strip()
                in_condensed = False
                in_llm_usage = True
                i += 1
                continue
            if not is_separator(stripped):
                condensed_lines.append(line.rstrip())
            i += 1
            continue

        # ── Inside output section ──
        if in_output:
            # Track parsing
            m = RE_TRACK.match(stripped)
            if m:
                if current_track:
                    run.output.tracks.append(current_track)
                current_track = Track(number=int(m.group(1)), title=m.group(2))
                current_track_section = ""
                in_synthesis = False
                in_current_data = False
                in_uncertainties = False
                i += 1
                continue

            if current_track:
                m = RE_CONFIDENCE.match(line)
                if m:
                    current_track.confidence = int(m.group(1))
                    i += 1
                    continue
                m = RE_MECHANISM.match(line)
                if m:
                    current_track.mechanism = m.group(1).strip()
                    i += 1
                    continue
                m = RE_TIME_HORIZON.match(line)
                if m:
                    current_track.time_horizon = m.group(1).strip()
                    i += 1
                    continue
                m = RE_PHASE_LINE.match(line)
                if m:
                    current_track.phase_num = int(m.group(1))
                    i += 1
                    continue
                m = RE_EVIDENCE.match(line)
                if m:
                    current_track.evidence = m.group(1).strip()
                    current_track_section = "evidence"
                    i += 1
                    continue

                if stripped.startswith("Asset Implications:"):
                    current_track_section = "implications"
                    i += 1
                    continue
                if stripped.startswith("Monitor:"):
                    current_track_section = "monitor"
                    i += 1
                    continue

                # Track separator
                if stripped.startswith("----") and len(stripped) >= 10:
                    run.output.tracks.append(current_track)
                    current_track = None
                    current_track_section = ""
                    i += 1
                    continue

                # Track content by section
                if current_track_section == "evidence" and stripped:
                    current_track.evidence += "\n" + stripped
                elif current_track_section == "implications" and stripped.startswith("- "):
                    current_track.asset_implications.append(stripped[2:])
                elif current_track_section == "monitor" and stripped.startswith("- "):
                    current_track.monitor.append(stripped[2:])

                i += 1
                continue

            # SYNTHESIS section
            if stripped.startswith("SYNTHESIS:"):
                if current_track:
                    run.output.tracks.append(current_track)
                    current_track = None
                in_synthesis = True
                synthesis_lines = []
                i += 1
                continue

            if in_synthesis:
                if stripped.startswith("KEY UNCERTAINTIES:"):
                    run.output.synthesis = "\n".join(synthesis_lines).strip()
                    in_synthesis = False
                    in_uncertainties = True
                    i += 1
                    continue
                if stripped.startswith("CURRENT DATA:"):
                    run.output.synthesis = "\n".join(synthesis_lines).strip()
                    in_synthesis = False
                    in_current_data = True
                    i += 1
                    continue
                if not is_separator(stripped):
                    synthesis_lines.append(line.rstrip())
                i += 1
                continue

            # KEY UNCERTAINTIES section
            if stripped.startswith("KEY UNCERTAINTIES:"):
                in_uncertainties = True
                i += 1
                continue

            if in_uncertainties:
                if stripped.startswith("CURRENT DATA:"):
                    in_uncertainties = False
                    in_current_data = True
                    i += 1
                    continue
                if stripped.startswith("- "):
                    run.output.uncertainties.append(stripped[2:])
                elif is_separator(stripped):
                    in_uncertainties = False
                i += 1
                continue

            # CURRENT DATA section
            if stripped.startswith("CURRENT DATA:"):
                in_current_data = True
                i += 1
                continue

            if in_current_data:
                if is_separator(stripped) and current_data_lines:
                    run.output.current_data = "\n".join(current_data_lines).strip()
                    in_current_data = False
                    i += 1
                    continue
                current_data_lines.append(line.rstrip())
                i += 1
                continue

            i += 1
            continue

        # ── Phase start detection ──
        phase_started = False
        for pnum, regex in RE_PHASE_START.items():
            if regex.search(stripped):
                # Flush previous phase
                if current_phase:
                    if current_iter:
                        current_phase.iterations.append(current_iter)
                        current_iter = None
                    run.phases.append(current_phase)

                phase_names = {
                    1: "Retrieval",
                    2: "Data Grounding",
                    3: "Historical Context",
                    4: "Synthesis",
                }
                current_phase = Phase(name=phase_names[pnum], phase_number=pnum)
                in_post_processing = False
                phase_started = True
                break

        if phase_started:
            i += 1
            continue

        # ── Agent loop iteration ──
        m = RE_ITERATION.match(stripped)
        if m and current_phase:
            if current_iter:
                current_phase.iterations.append(current_iter)
            current_iter = Iteration(
                number=int(m.group(1)),
                max_iterations=int(m.group(2))
            )
            current_tool = None
            in_post_processing = False
            i += 1
            continue

        # ── Agent thinking ──
        m = RE_AGENT_THINK.match(stripped)
        if m and current_iter:
            current_iter.thinking = m.group(1).strip()
            i += 1
            continue

        # ── Tool call ──
        m = RE_TOOL_CALL.match(stripped)
        if m and current_iter:
            tool_name = m.group(1)
            args_raw = m.group(2)
            # Remove trailing ) if present
            if args_raw.endswith(")"):
                args_raw = args_raw[:-1]
            current_tool = ToolCall(tool_name=tool_name, arguments=args_raw)
            current_iter.tool_calls.append(current_tool)
            i += 1
            continue

        # ── Tool result ──
        m = RE_TOOL_RESULT.match(stripped)
        if m and current_iter:
            result_text = m.group(1).strip()
            if current_tool:
                current_tool.result_preview = result_text
            current_tool = None
            i += 1
            continue

        # ── Coverage assessment (special sub-log) ──
        m = RE_COVERAGE.match(stripped)
        if m:
            coverage = CoverageResult(
                rating=m.group(1),
                flags_met=int(m.group(2)),
                flags_total=int(m.group(3))
            )
            # Read flag lines
            j = i + 1
            while j < n:
                fm = RE_COVERAGE_FLAG.match(lines[j])
                if fm:
                    coverage.flags.append((fm.group(1) == "Y", fm.group(2).strip()))
                    j += 1
                else:
                    break
            i = j
            # Attach to current tool as sub-log
            if current_tool:
                flag_text = f"{coverage.rating} ({coverage.flags_met}/{coverage.flags_total} flags)\n"
                for passed, name in coverage.flags:
                    flag_text += f"  [{'Y' if passed else 'N'}] {name}\n"
                current_tool.sub_logs.append(SubLog(tag="Coverage", text=flag_text.strip()))
            continue

        # ── Exit / max iterations ──
        m = RE_EXIT_TOOL.match(stripped) or RE_MAX_ITER.match(stripped)
        if m and current_phase:
            if current_iter:
                current_phase.iterations.append(current_iter)
                current_iter = None
            current_tool = None
            i += 1
            continue

        # ── Phase completion note ──
        m = RE_PHASE_COMPLETE.match(stripped)
        if m and current_phase:
            current_phase.completion_note = stripped
            in_post_processing = True
            i += 1
            continue

        # ── Sub-logs (between tool call and result, or in post-processing) ──
        m = RE_SUB_LOG.match(stripped)
        if m:
            tag = m.group(1)
            text = m.group(2)

            # Check if this is a phase start or other special tag
            if tag in ("Retrieval Agent", "Data Grounding Agent", "Historical Context Agent", "Synthesis Phase"):
                # Don't consume, let the phase start detection handle it on next pass
                # Actually, the completion note was handled above, check if it's starting
                is_start = False
                for _, regex in RE_PHASE_START.items():
                    if regex.search(stripped):
                        is_start = True
                        break
                if is_start:
                    continue  # Let next iteration handle it

            if current_phase and (in_post_processing or current_iter is None):
                # Accumulate multi-line content for this log entry
                entry = LogEntry(tag=tag, lines=[text])
                j = i + 1
                while j < n:
                    next_line = lines[j].strip()
                    if not next_line:
                        j += 1
                        continue
                    if RE_HTTPX.match(next_line):
                        j += 1
                        continue
                    # Check if next line is a new sub-log or a phase start
                    if RE_SUB_LOG.match(next_line):
                        break
                    if any(r.search(next_line) for r in RE_PHASE_START.values()):
                        break
                    if is_separator(next_line):
                        # Check if this precedes INSIGHT REPORT or CONDENSED or LLM
                        peek = j + 1
                        while peek < n and (not lines[peek].strip() or is_separator(lines[peek].strip())):
                            peek += 1
                        if peek < n and ("INSIGHT REPORT" in lines[peek] or "CONDENSED" in lines[peek] or "LLM USAGE" in lines[peek]):
                            break
                        # Check for another phase start
                        if peek < n and any(r.search(lines[peek].strip()) for r in RE_PHASE_START.values()):
                            break
                    entry.lines.append(lines[j].rstrip())
                    j += 1
                current_phase.post_processing.append(entry)
                i = j
                continue
            elif current_tool:
                current_tool.sub_logs.append(SubLog(tag=tag, text=text))
                i += 1
                continue
            elif current_iter and not current_tool:
                # Sub-log between tool calls (loose)
                i += 1
                continue

        # Skip separators
        if is_separator(stripped):
            i += 1
            continue

        # Accumulate body text for current tool's sub-logs (non-tagged lines)
        if current_tool and stripped and not stripped.startswith("Message(id="):
            # Lines that are part of tool execution but not tagged
            if current_tool.sub_logs:
                current_tool.sub_logs[-1].text += "\n" + stripped
            i += 1
            continue

        i += 1

    # Flush any remaining phase
    if current_phase:
        if current_iter:
            current_phase.iterations.append(current_iter)
        run.phases.append(current_phase)

    # Flush remaining LLM model
    if current_llm_model:
        run.llm_usage.append(current_llm_model)

    # Flush remaining output sections
    if in_synthesis:
        run.output.synthesis = "\n".join(synthesis_lines).strip()
    if in_current_data:
        run.output.current_data = "\n".join(current_data_lines).strip()
    if in_condensed:
        run.output.condensed = "\n".join(condensed_lines).strip()
    if current_track:
        run.output.tracks.append(current_track)

    return run


# ── HTML Renderer ────────────────────────────────────────────────────────

PHASE_COLORS = {
    "Retrieval": "#3b82f6",
    "Data Grounding": "#06b6d4",
    "Historical Context": "#a855f7",
    "Synthesis": "#f59e0b",
    "Output": "#10b981",
}

PHASE_ICONS = {
    "Retrieval": "1",
    "Data Grounding": "2",
    "Historical Context": "3",
    "Synthesis": "4",
    "Output": "&#x2713;",
}

TOOL_COLORS = {
    "search_pinecone": "#3b82f6",
    "extract_web_chains": "#10b981",
    "assess_coverage": "#f59e0b",
    "generate_synthesis": "#ef4444",
    "finish_retrieval": "#6366f1",
    "extract_variables": "#a855f7",
    "fetch_variable_data": "#06b6d4",
    "validate_claim": "#ec4899",
    "validate_patterns": "#ec4899",
    "compute_derived": "#8b5cf6",
    "finish_grounding": "#6366f1",
    "detect_analogs": "#d946ef",
    "fetch_analog_data": "#f97316",
    "aggregate_analogs": "#f97316",
    "characterize_regime": "#ef4444",
    "load_theme_chains": "#a855f7",
    "fetch_additional_data": "#0ea5e9",
    "finish_historical": "#6366f1",
}


def esc(text: str) -> str:
    return html.escape(str(text))


def truncate(text: str, max_len: int = 200) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


def format_json_preview(text: str) -> str:
    """Try to pretty-print JSON, fall back to raw text."""
    text = text.strip()
    if not text.startswith("{") and not text.startswith("["):
        return esc(truncate(text, 500))
    try:
        obj = json.loads(text)
        formatted = json.dumps(obj, indent=2, ensure_ascii=False)
        if len(formatted) > 2000:
            formatted = formatted[:2000] + "\n..."
        return esc(formatted)
    except (json.JSONDecodeError, ValueError):
        return esc(truncate(text, 500))


def render_html(run: PipelineRun) -> str:
    # Compute stats
    total_iters = sum(len(p.iterations) for p in run.phases)
    total_tools = sum(
        len(tc.tool_calls)
        for p in run.phases
        for tc in p.iterations
    )

    # Build navigation items: list of (phase_idx, iter_idx_or_special, label, tool_count)
    nav_items = []
    for pi, phase in enumerate(run.phases):
        for ii, iteration in enumerate(phase.iterations):
            tc = len(iteration.tool_calls)
            nav_items.append({
                "phase_idx": pi,
                "iter_idx": ii,
                "type": "iteration",
                "label": f"Ph{phase.phase_number} It{iteration.number}",
                "tool_count": tc,
                "phase_name": phase.name,
            })
        if phase.post_processing:
            nav_items.append({
                "phase_idx": pi,
                "iter_idx": -1,
                "type": "post",
                "label": f"Ph{phase.phase_number} Post",
                "tool_count": len(phase.post_processing),
                "phase_name": phase.name,
            })
    # Output section
    nav_items.append({
        "phase_idx": -1,
        "iter_idx": -1,
        "type": "output",
        "label": "Output",
        "tool_count": len(run.output.tracks),
        "phase_name": "Output",
    })

    nav_items_js = json.dumps(nav_items)

    # Phase data for JS
    phase_data = []
    for p in run.phases:
        phase_data.append({
            "name": p.name,
            "number": p.phase_number,
            "iterations": len(p.iterations),
            "tools": sum(len(it.tool_calls) for it in p.iterations),
            "has_post": bool(p.post_processing),
        })
    phase_data_js = json.dumps(phase_data)

    parts = []

    # ── HTML Head + CSS ──
    parts.append(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Pipeline Trace — {esc(run.query[:60])}</title>
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
.nav-label {{
    font-size: 11px; padding: 3px 10px; border-radius: 4px;
    font-weight: 600; min-width: 200px; text-align: center;
}}
.sep {{ width: 1px; height: 18px; background: #334155; }}

/* ── Main layout ── */
.main {{ display: flex; flex: 1; overflow: hidden; }}

/* ── Left panel ── */
.left-panel {{
    width: 240px; min-width: 240px;
    display: flex; flex-direction: column;
    border-right: 1px solid #1e293b;
    flex-shrink: 0;
}}

/* Flowchart */
.flowchart {{ padding: 10px 8px; flex-shrink: 0; }}

.flow-node {{
    position: relative;
    padding: 7px 10px; margin: 0;
    border-radius: 7px;
    border: 2px solid #1e293b;
    cursor: pointer;
    transition: all 0.3s ease;
    display: flex; align-items: center; gap: 8px;
    z-index: 1;
}}
.flow-node:hover {{ border-color: #475569; background: #1e293b; }}
.flow-node.active {{
    border-color: var(--pc);
    border-width: 2.5px;
    background: color-mix(in srgb, var(--pc) 15%, #0f172a);
    box-shadow: 0 0 16px color-mix(in srgb, var(--pc) 50%, transparent);
    animation: pulse-glow 2s ease-in-out infinite;
}}
@keyframes pulse-glow {{
    0%, 100% {{ box-shadow: 0 0 12px color-mix(in srgb, var(--pc) 40%, transparent); }}
    50% {{ box-shadow: 0 0 22px color-mix(in srgb, var(--pc) 65%, transparent), 0 0 8px color-mix(in srgb, var(--pc) 35%, transparent); }}
}}
.flow-node.visited {{ border-color: #334155; background: #1e293b44; }}
.flow-node.visited .flow-label {{ color: #64748b; }}
.flow-node.visited .flow-num {{ opacity: 0.5; }}
.flow-num {{
    width: 22px; height: 22px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 11px; font-weight: 700; flex-shrink: 0;
    border: 2px solid #475569; color: #94a3b8;
}}
.flow-node.active .flow-num {{ border-color: var(--pc); color: var(--pc); }}
.flow-node.visited .flow-num {{ border-color: #334155; }}
.flow-node.visited .flow-num::after {{ content: '\\2713'; position: absolute; font-size: 10px; color: #475569; }}
.flow-label {{ font-size: 10px; font-weight: 600; color: #94a3b8; line-height: 1.2; flex: 1; }}
.flow-node.active .flow-label {{ color: var(--pc); font-weight: 700; }}
.flow-stats {{ font-size: 9px; color: #475569; white-space: nowrap; text-align: right; }}
.flow-node.active .flow-stats {{ color: var(--pc); opacity: 0.8; }}

.flow-connector {{
    display: flex; align-items: center; justify-content: center;
    height: 16px; position: relative; margin: 0;
}}
.flow-connector::before {{
    content: '';
    position: absolute; left: 19px; top: 0; bottom: 0;
    width: 2px; background: #1e293b;
}}
.flow-connector.active::before {{ background: var(--pc); opacity: 0.6; }}

/* ── Trail ── */
.trail-divider {{ height: 1px; background: #1e293b; margin: 4px 8px; }}
.trail-header {{ font-size: 9px; color: #475569; padding: 4px 10px; text-transform: uppercase; letter-spacing: 0.1em; }}
.trail {{ flex: 1; overflow-y: auto; padding: 0 4px 8px; }}

.trail-item {{
    display: flex; align-items: center; gap: 6px;
    padding: 3px 8px; margin: 1px 0;
    border-left: 3px solid transparent;
    border-radius: 0 4px 4px 0;
    cursor: pointer; font-size: 10px;
    transition: all 0.15s;
}}
.trail-item:hover {{ background: #1e293b; }}
.trail-item.active {{
    background: color-mix(in srgb, var(--tc) 12%, #0f172a);
    border-left-color: var(--tc);
}}
.trail-item.past {{ opacity: 0.45; }}
.trail-num {{ color: #475569; width: 18px; text-align: right; font-size: 9px; }}
.trail-item.active .trail-num {{ color: var(--tc); font-weight: 700; }}
.trail-label {{ color: #94a3b8; flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.trail-item.active .trail-label {{ color: var(--tc); font-weight: 600; }}
.trail-count {{ color: #475569; font-size: 9px; }}
.trail-item.active .trail-count {{ color: var(--tc); }}

/* ── Right panel ── */
.right-panel {{ flex: 1; overflow-y: auto; padding: 12px 16px 80px; }}

.content-block {{ display: none; }}
.content-block.active {{ display: block; }}

.phase-header {{
    padding: 8px 12px; border-radius: 6px; margin-bottom: 10px;
    font-size: 12px; font-weight: 600;
    display: flex; align-items: center; gap: 8px;
}}
.phase-header .ph-name {{ flex: 1; }}
.phase-header .ph-meta {{ font-size: 10px; font-weight: 400; opacity: 0.7; }}

/* Iteration block */
.iter-block {{
    border: 1px solid #1e293b; border-radius: 8px;
    margin-bottom: 10px; overflow: hidden;
}}
.iter-header {{
    padding: 6px 12px; background: #1e293b;
    display: flex; align-items: center; gap: 8px;
    font-size: 11px; font-weight: 600; color: #94a3b8;
}}
.iter-num {{ color: var(--pc); }}
.iter-tools {{ font-size: 9px; color: #64748b; margin-left: auto; }}

/* Thinking block */
.thinking {{
    padding: 8px 12px; margin: 6px 8px;
    background: #1e1b4b; border-radius: 6px;
    border-left: 3px solid #6366f1;
    font-size: 11px; color: #a5b4fc; line-height: 1.5;
    white-space: pre-wrap;
}}

/* Tool call card */
.tool-card {{
    margin: 4px 8px; border-left: 3px solid #334155;
    padding: 6px 10px; cursor: pointer;
    transition: all 0.15s;
}}
.tool-card:hover {{ background: #1e293b; }}
.tool-card.expanded {{ background: #1e293b; }}

.tool-header {{ display: flex; align-items: center; gap: 8px; }}
.tool-badge {{
    font-size: 10px; padding: 2px 8px; border-radius: 4px;
    font-weight: 600; white-space: nowrap;
}}
.tool-summary {{ font-size: 10px; color: #64748b; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}

.tool-details {{ display: none; margin-top: 6px; }}
.tool-card.expanded .tool-details {{ display: block; }}

.tool-section-label {{ font-size: 9px; color: #475569; text-transform: uppercase; margin: 6px 0 2px; letter-spacing: 0.05em; }}
.tool-content {{
    padding: 6px 8px; background: #0f172a; border-radius: 4px;
    border: 1px solid #1e293b; white-space: pre-wrap; font-size: 10px;
    color: #94a3b8; max-height: 300px; overflow-y: auto; line-height: 1.5;
}}

/* Sub-log badges */
.sub-log {{ margin: 4px 0; }}
.sub-log-tag {{
    font-size: 9px; padding: 1px 6px; border-radius: 3px;
    font-weight: 600; display: inline-block; margin-right: 4px;
}}
.sub-log-text {{ font-size: 10px; color: #94a3b8; }}

/* Coverage special rendering */
.coverage-grid {{
    display: grid; grid-template-columns: 18px 1fr; gap: 2px 6px;
    padding: 6px 8px; background: #0f172a; border-radius: 4px;
    border: 1px solid #1e293b; font-size: 11px;
}}
.coverage-check {{ color: #10b981; text-align: center; }}
.coverage-cross {{ color: #ef4444; text-align: center; }}
.coverage-name {{ color: #cbd5e1; }}
.coverage-rating {{
    font-size: 11px; padding: 2px 10px; border-radius: 10px;
    font-weight: 600; display: inline-block; margin-bottom: 6px;
}}

/* Post-processing section */
.post-section {{
    border: 1px solid #1e293b; border-radius: 8px;
    margin-bottom: 10px; overflow: hidden;
}}
.post-header {{
    padding: 6px 12px; background: #1e293b;
    font-size: 11px; font-weight: 600; color: #94a3b8;
}}
.post-entry {{
    margin: 3px 8px; padding: 4px 8px;
    border-left: 3px solid #334155; cursor: pointer;
    transition: all 0.15s;
}}
.post-entry:hover {{ background: #1e293b; }}
.post-entry.expanded {{ background: #1e293b; }}
.post-tag {{
    font-size: 9px; padding: 1px 6px; border-radius: 3px;
    font-weight: 600; display: inline-block; margin-right: 6px;
}}
.post-preview {{ font-size: 10px; color: #64748b; }}
.post-body {{ display: none; margin-top: 4px; }}
.post-entry.expanded .post-body {{ display: block; }}

/* ── Output section styles ── */
.track-card {{
    border: 1px solid #1e293b; border-radius: 8px;
    margin-bottom: 10px; overflow: hidden;
    cursor: pointer; transition: all 0.15s;
}}
.track-card:hover {{ border-color: #334155; }}
.track-card.expanded {{ border-color: #475569; }}

.track-header {{
    padding: 8px 12px; display: flex; align-items: center; gap: 10px;
}}
.track-num {{
    width: 28px; height: 28px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 12px; font-weight: 700;
    background: #10b98120; color: #10b981;
    flex-shrink: 0;
}}
.track-title {{ font-size: 11px; font-weight: 600; color: #e2e8f0; flex: 1; }}
.track-conf {{ font-size: 11px; font-weight: 700; white-space: nowrap; }}

.conf-bar {{
    height: 4px; background: #1e293b; border-radius: 2px;
    margin: 0 12px 4px; overflow: hidden;
}}
.conf-fill {{ height: 100%; border-radius: 2px; transition: width 0.5s; }}

.track-details {{ display: none; padding: 0 12px 10px; }}
.track-card.expanded .track-details {{ display: block; }}
.track-field {{ margin: 6px 0; }}
.track-field-label {{ font-size: 9px; color: #475569; text-transform: uppercase; margin-bottom: 2px; }}
.track-field-value {{ font-size: 11px; color: #cbd5e1; line-height: 1.5; }}

.track-implication {{
    display: flex; gap: 8px; padding: 3px 0;
    font-size: 11px; align-items: baseline;
}}
.impl-asset {{ font-weight: 600; color: #e2e8f0; min-width: 80px; }}
.impl-detail {{ color: #94a3b8; }}

.track-monitor-item {{
    padding: 3px 0; font-size: 11px; color: #94a3b8;
    border-left: 2px solid #334155; padding-left: 8px; margin: 3px 0;
}}

/* Synthesis block */
.synth-block {{
    border: 1px solid #1e293b; border-radius: 8px;
    padding: 12px; margin-bottom: 10px;
}}
.synth-title {{ font-size: 12px; font-weight: 600; color: #f59e0b; margin-bottom: 8px; }}
.synth-content {{ font-size: 11px; color: #cbd5e1; line-height: 1.6; white-space: pre-wrap; }}
.synth-content h2, .synth-content h3 {{ color: #f8fafc; margin: 12px 0 6px; font-size: 12px; }}

/* Uncertainties */
.uncertainty-item {{
    padding: 4px 0 4px 10px; font-size: 11px; color: #94a3b8;
    border-left: 2px solid #f59e0b; margin: 4px 0;
}}

/* Current data */
.data-block {{
    border: 1px solid #1e293b; border-radius: 8px;
    padding: 10px 12px; margin-bottom: 10px;
    font-size: 11px; color: #cbd5e1; line-height: 1.6;
    white-space: pre-wrap;
}}

/* LLM usage table */
.llm-table {{
    width: 100%; border-collapse: collapse;
    font-size: 11px; margin-top: 6px;
}}
.llm-table th {{
    text-align: left; padding: 4px 8px; color: #64748b;
    border-bottom: 1px solid #334155; font-size: 10px;
}}
.llm-table td {{
    padding: 4px 8px; border-bottom: 1px solid #1e293b;
}}
.llm-table td:nth-child(n+2) {{ text-align: right; }}
.llm-table .total-row {{ font-weight: 600; color: #f8fafc; }}
.llm-table .total-row td {{ border-top: 2px solid #334155; }}
</style>
</head>
<body>
""")

    # ── Top bar ──
    cost_text = f"${run.total_cost:.2f}" if run.total_cost else ""
    duration_text = run.duration if run.duration else ""
    stats_parts = [
        f"{len(run.phases)} phases",
        f"{total_iters} iters",
        f"{total_tools} tools",
    ]
    if cost_text:
        stats_parts.append(cost_text)
    if duration_text:
        stats_parts.append(duration_text)
    stats_text = " · ".join(stats_parts)

    parts.append(f"""
<div class="top-bar">
    <h1>Pipeline Trace</h1>
    <div class="query">{esc(run.query)}</div>
    <div class="stats">{esc(stats_text)} · {esc(Path(run.log_path).name)}</div>
</div>
""")

    # ── Controls bar ──
    parts.append(f"""
<div class="controls">
    <button class="btn" onclick="navPhase(-1)" title="h">&#9664; Phase</button>
    <button class="btn" onclick="navPhase(1)" title="l">Phase &#9654;</button>
    <div class="nav-label" id="navLabel" style="background:#33415520;color:#94a3b8;">Loading...</div>
    <div class="sep"></div>
    <button class="btn" onclick="navIter(-1)" title="k">&#9650; Iter</button>
    <button class="btn" onclick="navIter(1)" title="j">&#9660; Iter</button>
    <button class="btn" onclick="navKey(-1)" title="p">&#9664; Key</button>
    <button class="btn" onclick="navKey(1)" title="n">Key &#9654;</button>
    <span style="flex:1"></span>
</div>
""")

    # ── Main layout ──
    parts.append('<div class="main">\n')

    # ── Left panel ──
    parts.append('<div class="left-panel">\n<div class="flowchart">\n')

    # Flow nodes for phases + output
    all_nodes = list(run.phases) + [None]  # None = output
    for idx, phase in enumerate(all_nodes):
        if phase is None:
            name = "Output"
            pnum = "Output"
            color = PHASE_COLORS["Output"]
            icon = PHASE_ICONS["Output"]
            it_count = len(run.output.tracks)
            tc_count = 0
            stats_str = f"{it_count} tracks"
        else:
            name = phase.name
            color = PHASE_COLORS.get(name, "#64748b")
            icon = PHASE_ICONS.get(name, str(phase.phase_number))
            it_count = len(phase.iterations)
            tc_count = sum(len(it.tool_calls) for it in phase.iterations)
            stats_str = f"{it_count}it {tc_count}tc"

        node_id = name.replace(" ", "_")
        parts.append(f'  <div class="flow-node" id="fn_{node_id}" style="--pc:{color};" data-phase="{esc(name)}" onclick="goToPhase(\'{esc(name)}\')">\n')
        parts.append(f'    <div class="flow-num">{icon}</div>\n')
        parts.append(f'    <span class="flow-label">{esc(name)}</span>\n')
        parts.append(f'    <span class="flow-stats">{stats_str}</span>\n')
        parts.append(f'  </div>\n')
        if idx < len(all_nodes) - 1:
            parts.append(f'  <div class="flow-connector" id="fc_{node_id}" style="--pc:{color};"></div>\n')

    parts.append('</div>\n')  # close flowchart

    # ── Trail ──
    parts.append('<div class="trail-divider"></div>\n')
    parts.append(f'<div class="trail-header">Execution Flow ({len(nav_items)} items)</div>\n')
    parts.append('<div class="trail" id="trail">\n')

    for ni, item in enumerate(nav_items):
        color = PHASE_COLORS.get(item["phase_name"], "#64748b")
        count = str(item["tool_count"])
        parts.append(f'  <div class="trail-item" id="ti_{ni}" style="--tc:{color};" data-nav="{ni}" onclick="goToNav({ni})">\n')
        parts.append(f'    <span class="trail-num">{ni + 1}</span>\n')
        parts.append(f'    <span class="trail-label">{esc(item["label"])}</span>\n')
        parts.append(f'    <span class="trail-count">{count}</span>\n')
        parts.append(f'  </div>\n')

    parts.append('</div>\n</div>\n')  # close trail, left-panel

    # ── Right panel ──
    parts.append('<div class="right-panel" id="rightPanel">\n')

    # Render content blocks for each nav item
    for ni, item in enumerate(nav_items):
        active = " active" if ni == 0 else ""
        parts.append(f'<div class="content-block{active}" data-nav="{ni}">\n')

        if item["type"] == "iteration":
            phase = run.phases[item["phase_idx"]]
            iteration = phase.iterations[item["iter_idx"]]
            color = PHASE_COLORS.get(phase.name, "#64748b")

            # Phase header
            parts.append(f'<div class="phase-header" style="background:{color}15; color:{color};">\n')
            parts.append(f'  <span class="ph-name">{esc(phase.name)} Agent</span>\n')
            parts.append(f'  <span class="ph-meta">Phase {phase.phase_number}</span>\n')
            parts.append(f'</div>\n')

            # Iteration block
            parts.append(f'<div class="iter-block" style="--pc:{color};">\n')
            parts.append(f'  <div class="iter-header">\n')
            parts.append(f'    <span class="iter-num">ITERATION {iteration.number}/{iteration.max_iterations}</span>\n')
            parts.append(f'    <span class="iter-tools">{len(iteration.tool_calls)} tool calls</span>\n')
            parts.append(f'  </div>\n')

            # Thinking
            if iteration.thinking:
                parts.append(f'  <div class="thinking">{esc(iteration.thinking)}</div>\n')

            # Tool calls
            for ti, tool in enumerate(iteration.tool_calls):
                tc_color = TOOL_COLORS.get(tool.tool_name, "#64748b")
                args_preview = truncate(tool.arguments, 80) if tool.arguments else ""

                parts.append(f'  <div class="tool-card" onclick="toggleTool(this)">\n')
                parts.append(f'    <div class="tool-header">\n')
                parts.append(f'      <span class="tool-badge" style="background:{tc_color}20; color:{tc_color};">{esc(tool.tool_name)}</span>\n')
                parts.append(f'      <span class="tool-summary">{esc(args_preview)}</span>\n')
                parts.append(f'    </div>\n')

                parts.append(f'    <div class="tool-details">\n')

                # Arguments
                if tool.arguments:
                    parts.append(f'      <div class="tool-section-label">Arguments</div>\n')
                    parts.append(f'      <div class="tool-content">{format_json_preview(tool.arguments)}</div>\n')

                # Sub-logs
                for sl in tool.sub_logs:
                    if sl.tag == "Coverage":
                        # Special coverage rendering
                        parts.append(f'      <div class="tool-section-label">Coverage Assessment</div>\n')
                        _render_coverage(parts, sl.text)
                    else:
                        tag_color = _sub_log_color(sl.tag)
                        parts.append(f'      <div class="sub-log">\n')
                        parts.append(f'        <span class="sub-log-tag" style="background:{tag_color}20; color:{tag_color};">{esc(sl.tag)}</span>\n')
                        parts.append(f'        <span class="sub-log-text">{esc(truncate(sl.text, 300))}</span>\n')
                        parts.append(f'      </div>\n')

                # Result
                if tool.result_preview:
                    parts.append(f'      <div class="tool-section-label">Result</div>\n')
                    parts.append(f'      <div class="tool-content">{format_json_preview(tool.result_preview)}</div>\n')

                parts.append(f'    </div>\n')  # tool-details
                parts.append(f'  </div>\n')  # tool-card

            parts.append(f'</div>\n')  # iter-block

        elif item["type"] == "post":
            phase = run.phases[item["phase_idx"]]
            color = PHASE_COLORS.get(phase.name, "#64748b")

            parts.append(f'<div class="phase-header" style="background:{color}15; color:{color};">\n')
            parts.append(f'  <span class="ph-name">{esc(phase.name)} — Post-Processing</span>\n')
            parts.append(f'  <span class="ph-meta">{len(phase.post_processing)} entries</span>\n')
            parts.append(f'</div>\n')

            parts.append(f'<div class="post-section">\n')
            parts.append(f'  <div class="post-header">Post-processing ({len(phase.post_processing)} items)</div>\n')

            for ei, entry in enumerate(phase.post_processing):
                tag_color = _sub_log_color(entry.tag)
                preview = truncate(entry.lines[0] if entry.lines else "", 100)
                body_text = esc("\n".join(entry.lines))

                parts.append(f'  <div class="post-entry" onclick="togglePost(this)">\n')
                parts.append(f'    <span class="post-tag" style="background:{tag_color}20; color:{tag_color};">{esc(entry.tag)}</span>\n')
                parts.append(f'    <span class="post-preview">{esc(preview)}</span>\n')
                parts.append(f'    <div class="post-body"><div class="tool-content">{body_text}</div></div>\n')
                parts.append(f'  </div>\n')

            parts.append(f'</div>\n')  # post-section

        elif item["type"] == "output":
            color = PHASE_COLORS["Output"]

            parts.append(f'<div class="phase-header" style="background:{color}15; color:{color};">\n')
            parts.append(f'  <span class="ph-name">Output — {esc(run.output.asset)}</span>\n')
            parts.append(f'  <span class="ph-meta">{len(run.output.tracks)} tracks</span>\n')
            parts.append(f'</div>\n')

            # Tracks
            for track in run.output.tracks:
                conf = track.confidence
                conf_color = "#10b981" if conf >= 65 else "#f59e0b" if conf >= 45 else "#ef4444"

                parts.append(f'<div class="track-card" onclick="toggleTrack(this)">\n')
                parts.append(f'  <div class="track-header">\n')
                parts.append(f'    <div class="track-num">{track.number}</div>\n')
                parts.append(f'    <div class="track-title">{esc(track.title)}</div>\n')
                parts.append(f'    <div class="track-conf" style="color:{conf_color};">{conf}%</div>\n')
                parts.append(f'  </div>\n')
                parts.append(f'  <div class="conf-bar"><div class="conf-fill" style="width:{conf}%; background:{conf_color};"></div></div>\n')

                parts.append(f'  <div class="track-details">\n')

                # Mechanism
                if track.mechanism:
                    parts.append(f'    <div class="track-field">\n')
                    parts.append(f'      <div class="track-field-label">Mechanism</div>\n')
                    parts.append(f'      <div class="track-field-value">{esc(track.mechanism)}</div>\n')
                    parts.append(f'    </div>\n')

                # Time Horizon
                if track.time_horizon:
                    parts.append(f'    <div class="track-field">\n')
                    parts.append(f'      <div class="track-field-label">Time Horizon</div>\n')
                    parts.append(f'      <div class="track-field-value">{esc(track.time_horizon)}</div>\n')
                    parts.append(f'    </div>\n')

                # Evidence
                if track.evidence:
                    parts.append(f'    <div class="track-field">\n')
                    parts.append(f'      <div class="track-field-label">Evidence</div>\n')
                    parts.append(f'      <div class="track-field-value" style="white-space:pre-wrap;">{esc(track.evidence)}</div>\n')
                    parts.append(f'    </div>\n')

                # Asset Implications
                if track.asset_implications:
                    parts.append(f'    <div class="track-field">\n')
                    parts.append(f'      <div class="track-field-label">Asset Implications</div>\n')
                    for imp in track.asset_implications:
                        parts.append(f'      <div class="track-implication">\n')
                        # Try to split "ASSET: direction (range)"
                        m_imp = re.match(r'^([^:]+):\s*(.+)', imp)
                        if m_imp:
                            parts.append(f'        <span class="impl-asset">{esc(m_imp.group(1))}</span>\n')
                            parts.append(f'        <span class="impl-detail">{esc(m_imp.group(2))}</span>\n')
                        else:
                            parts.append(f'        <span class="impl-detail">{esc(imp)}</span>\n')
                        parts.append(f'      </div>\n')
                    parts.append(f'    </div>\n')

                # Monitor
                if track.monitor:
                    parts.append(f'    <div class="track-field">\n')
                    parts.append(f'      <div class="track-field-label">Monitor</div>\n')
                    for mon in track.monitor:
                        parts.append(f'      <div class="track-monitor-item">{esc(mon)}</div>\n')
                    parts.append(f'    </div>\n')

                parts.append(f'  </div>\n')  # track-details
                parts.append(f'</div>\n')  # track-card

            # Synthesis
            if run.output.synthesis:
                parts.append(f'<div class="synth-block">\n')
                parts.append(f'  <div class="synth-title">Synthesis</div>\n')
                parts.append(f'  <div class="synth-content">{esc(run.output.synthesis)}</div>\n')
                parts.append(f'</div>\n')

            # Key Uncertainties
            if run.output.uncertainties:
                parts.append(f'<div class="synth-block">\n')
                parts.append(f'  <div class="synth-title">Key Uncertainties</div>\n')
                for unc in run.output.uncertainties:
                    parts.append(f'  <div class="uncertainty-item">{esc(unc)}</div>\n')
                parts.append(f'</div>\n')

            # Current Data
            if run.output.current_data:
                parts.append(f'<div class="synth-block">\n')
                parts.append(f'  <div class="synth-title">Current Data</div>\n')
                parts.append(f'  <div class="data-block">{esc(run.output.current_data)}</div>\n')
                parts.append(f'</div>\n')

            # Condensed Summary
            if run.output.condensed:
                parts.append(f'<div class="synth-block">\n')
                parts.append(f'  <div class="synth-title">Condensed Summary</div>\n')
                parts.append(f'  <div class="data-block">{esc(run.output.condensed)}</div>\n')
                parts.append(f'</div>\n')

            # LLM Usage
            if run.llm_usage:
                parts.append(f'<div class="synth-block">\n')
                parts.append(f'  <div class="synth-title">LLM Usage</div>\n')
                parts.append(f'  <table class="llm-table">\n')
                parts.append(f'    <tr><th>Model</th><th>Calls</th><th>Input</th><th>Output</th><th>Cost</th></tr>\n')
                for u in run.llm_usage:
                    parts.append(f'    <tr><td>{esc(u.model)}</td><td>{u.calls}</td><td>{u.input_tokens:,}</td><td>{u.output_tokens:,}</td><td>${u.cost:.4f}</td></tr>\n')
                parts.append(f'    <tr class="total-row"><td>TOTAL</td><td>{sum(u.calls for u in run.llm_usage)}</td><td>{sum(u.input_tokens for u in run.llm_usage):,}</td><td>{sum(u.output_tokens for u in run.llm_usage):,}</td><td>${run.total_cost:.4f}</td></tr>\n')
                parts.append(f'  </table>\n')
                if run.duration:
                    parts.append(f'  <div style="margin-top:6px;font-size:10px;color:#64748b;">Duration: {esc(run.duration)}</div>\n')
                parts.append(f'</div>\n')

        parts.append(f'</div>\n')  # content-block

    parts.append('</div>\n')  # right-panel
    parts.append('</div>\n')  # main

    # ── JavaScript ──
    parts.append(f"""
<script>
const navItems = {nav_items_js};
const phaseData = {phase_data_js};
const PHASE_COLORS = {json.dumps(PHASE_COLORS)};
const totalNav = navItems.length;
let currentNav = 0;

function phaseId(name) {{
    return name.replace(/ /g, '_');
}}

// ── Navigation ──

function goToNav(idx) {{
    if (idx < 0 || idx >= totalNav) return;
    currentNav = idx;

    document.querySelectorAll('.content-block').forEach(b => {{
        b.classList.toggle('active', parseInt(b.dataset.nav) === idx);
    }});

    document.querySelectorAll('.trail-item').forEach(item => {{
        const ni = parseInt(item.dataset.nav);
        item.classList.toggle('active', ni === idx);
        item.classList.toggle('past', ni < idx);
    }});
    const activeItem = document.getElementById('ti_' + idx);
    if (activeItem) activeItem.scrollIntoView({{ behavior: 'auto', block: 'nearest' }});

    highlightPhase(navItems[idx].phase_name);
    updateNavLabel();
    document.getElementById('rightPanel').scrollTop = 0;
}}

function goToPhase(phaseName) {{
    for (let i = 0; i < totalNav; i++) {{
        if (navItems[i].phase_name === phaseName) {{
            goToNav(i);
            return;
        }}
    }}
}}

function navPhase(dir) {{
    const curPhase = navItems[currentNav].phase_name;
    if (dir > 0) {{
        for (let i = currentNav + 1; i < totalNav; i++) {{
            if (navItems[i].phase_name !== curPhase) {{
                goToNav(i);
                return;
            }}
        }}
    }} else {{
        // Go to first item of previous phase
        let prevPhase = null;
        for (let i = currentNav - 1; i >= 0; i--) {{
            if (navItems[i].phase_name !== curPhase) {{
                prevPhase = navItems[i].phase_name;
                break;
            }}
        }}
        if (prevPhase) {{
            for (let i = 0; i < totalNav; i++) {{
                if (navItems[i].phase_name === prevPhase) {{
                    goToNav(i);
                    return;
                }}
            }}
        }}
    }}
}}

function navIter(dir) {{
    goToNav(currentNav + dir);
}}

function navKey(dir) {{
    // Jump to next/prev coverage assessment or phase boundary
    const keyTypes = ['post', 'output'];
    let i = currentNav + dir;
    while (i >= 0 && i < totalNav) {{
        if (keyTypes.includes(navItems[i].type)) {{
            goToNav(i);
            return;
        }}
        // Also stop at first iteration of a new phase
        if (i > 0 && navItems[i].phase_name !== navItems[i - 1].phase_name) {{
            goToNav(i);
            return;
        }}
        i += dir;
    }}
}}

// ── Flowchart ──

function highlightPhase(phaseName) {{
    const nodes = document.querySelectorAll('.flow-node');
    const connectors = document.querySelectorAll('.flow-connector');

    nodes.forEach(n => n.classList.remove('active', 'visited'));
    connectors.forEach(c => c.classList.remove('active'));

    const pid = phaseId(phaseName);
    const activeNode = document.getElementById('fn_' + pid);
    if (activeNode) activeNode.classList.add('active');

    // Mark visited phases
    const visitedPhases = new Set();
    for (let i = 0; i < currentNav; i++) {{
        visitedPhases.add(navItems[i].phase_name);
    }}
    visitedPhases.delete(phaseName);
    visitedPhases.forEach(p => {{
        const el = document.getElementById('fn_' + phaseId(p));
        if (el) el.classList.add('visited');
    }});

    // Activate connector before current phase
    const phaseNames = [...phaseData.map(p => p.name), 'Output'];
    const phaseIdx = phaseNames.indexOf(phaseName);
    if (phaseIdx > 0) {{
        const prevPid = phaseId(phaseNames[phaseIdx - 1]);
        const conn = document.getElementById('fc_' + prevPid);
        if (conn) {{
            conn.classList.add('active');
            conn.style.setProperty('--pc', PHASE_COLORS[phaseName] || '#64748b');
        }}
    }}
}}

// ── UI updates ──

function updateNavLabel() {{
    const item = navItems[currentNav];
    const color = PHASE_COLORS[item.phase_name] || '#64748b';
    const label = document.getElementById('navLabel');
    let text = '';
    if (item.type === 'iteration') {{
        text = item.phase_name + ' — Iteration ' + item.label.split('It')[1];
    }} else if (item.type === 'post') {{
        text = item.phase_name + ' — Post-Processing';
    }} else {{
        text = 'Output — {esc(run.output.asset)}';
    }}
    label.textContent = text;
    label.style.background = color + '20';
    label.style.color = color;
}}

// ── Toggles ──

function toggleTool(el) {{
    el.classList.toggle('expanded');
}}

function togglePost(el) {{
    el.classList.toggle('expanded');
}}

function toggleTrack(el) {{
    el.classList.toggle('expanded');
}}

// ── Keyboard ──

document.addEventListener('keydown', (e) => {{
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    switch (e.key) {{
        case 'ArrowRight': case 'l': e.preventDefault(); navPhase(1); break;
        case 'ArrowLeft': case 'h': e.preventDefault(); navPhase(-1); break;
        case 'ArrowDown': case 'j': e.preventDefault(); navIter(1); break;
        case 'ArrowUp': case 'k': e.preventDefault(); navIter(-1); break;
        case 'n': navKey(1); break;
        case 'p': navKey(-1); break;
        case 'Escape':
            // Collapse all expanded items
            document.querySelectorAll('.expanded').forEach(el => el.classList.remove('expanded'));
            break;
    }}
}});

// Initialize
goToNav(0);
</script>
</body>
</html>""")

    return "".join(parts)


def _sub_log_color(tag: str) -> str:
    colors = {
        "vector_search": "#8b5cf6",
        "extract_web_chains": "#10b981",
        "Coverage": "#f59e0b",
        "answer_generation": "#06b6d4",
        "chain_expansion": "#6366f1",
        "Knowledge Gap": "#f59e0b",
        "WebSearch": "#10b981",
        "Historical Analog": "#ec4899",
        "Chain Merge": "#f97316",
        "web_chain_persistence": "#14b8a6",
        "Variable Extraction": "#a855f7",
        "Retrieve": "#3b82f6",
        "retriever.gap_detector": "#f59e0b",
        "Gap": "#f59e0b",
        "Relationship Store": "#78716c",
        "Regime Characterization": "#dc2626",
        "Chain Graph": "#f97316",
        "Impact Analysis": "#ef4444",
        "Synthesis Phase": "#f59e0b",
        "Regime": "#dc2626",
    }
    # Check prefix matches
    for prefix, c in colors.items():
        if tag.startswith(prefix) or tag.startswith("Gap:"):
            return c
    return "#64748b"


def _render_coverage(parts: list[str], text: str) -> None:
    """Render coverage assessment with visual checkmarks."""
    lines = text.strip().split("\n")
    if not lines:
        return

    # First line: rating
    first = lines[0].strip()
    m = re.match(r'(\w+)\s*\((\d+)/(\d+)', first)
    if m:
        rating = m.group(1)
        met = m.group(2)
        total = m.group(3)
        r_color = {
            "ADEQUATE": "#10b981",
            "PARTIAL": "#f59e0b",
            "INSUFFICIENT": "#ef4444",
            "COMPLETE": "#10b981",
        }.get(rating, "#64748b")
        parts.append(f'      <span class="coverage-rating" style="background:{r_color}20; color:{r_color};">{esc(rating)} ({met}/{total} flags)</span>\n')

    # Flag lines
    parts.append(f'      <div class="coverage-grid">\n')
    for line in lines[1:]:
        fm = re.match(r'\s*\[(Y|N)\]\s*(.+)', line)
        if fm:
            passed = fm.group(1) == "Y"
            name = fm.group(2).strip()
            cls = "coverage-check" if passed else "coverage-cross"
            icon = "&#x2713;" if passed else "&#x2717;"
            parts.append(f'        <span class="{cls}">{icon}</span>\n')
            parts.append(f'        <span class="coverage-name">{esc(name)}</span>\n')
    parts.append(f'      </div>\n')


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

    run = parse_log(lines)
    run.log_path = log_path

    html_out = render_html(run)

    if not output_path:
        output_path = str(log_file.with_suffix("")) + "_v2.html"

    Path(output_path).write_text(html_out, encoding="utf-8")

    total_tools = sum(len(tc.tool_calls) for p in run.phases for tc in p.iterations)
    total_iters = sum(len(p.iterations) for p in run.phases)

    print(f"Generated: {output_path}")
    print(f"  Phases: {len(run.phases)}")
    print(f"  Iterations: {total_iters}")
    print(f"  Tool calls: {total_tools}")
    print(f"  Tracks: {len(run.output.tracks)}")
    if run.total_cost:
        print(f"  Cost: ${run.total_cost:.4f}")
    if run.duration:
        print(f"  Duration: {run.duration}")


if __name__ == "__main__":
    main()
