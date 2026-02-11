"""
Pipeline Run Logger

Captures all pipeline output (stdout) to a timestamped log file.
Also tracks LLM call metadata (model, tokens, cost) per run.

Usage:
    from shared.run_logger import RunLogger

    with RunLogger(query="What caused the SaaS meltdown?") as run:
        # All print() output is teed to the log file
        result = run_btc_impact_analysis(query)

    # After context manager exits:
    # - Log file saved to logs/run_YYYYMMDD_HHMMSS.log
    # - LLM summary printed and appended to log
"""

import sys
import os
import time
import threading
from datetime import datetime
from pathlib import Path
from io import StringIO

from .paths import PROJECT_ROOT

LOGS_DIR = PROJECT_ROOT / "logs"


class _TeeWriter:
    """Writes to both the original stream and a log file."""

    def __init__(self, original, log_file):
        self.original = original
        self.log_file = log_file

    def write(self, text):
        self.original.write(text)
        self.log_file.write(text)

    def flush(self):
        self.original.flush()
        self.log_file.flush()

    # Delegate any other attributes to the original stream
    def __getattr__(self, name):
        return getattr(self.original, name)


# Global per-run LLM call tracker
_llm_calls = []
_llm_lock = threading.Lock()
_logging_active = False


def log_llm_call(model: str, input_tokens: int, output_tokens: int,
                 cache_read: int = 0, cache_creation: int = 0):
    """Record an LLM call for the current run. Thread-safe."""
    if not _logging_active:
        return
    with _llm_lock:
        _llm_calls.append({
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read": cache_read,
            "cache_creation": cache_creation,
            "timestamp": datetime.now().isoformat(),
        })


# Pricing per 1M tokens (input, output)
_PRICING = {
    "claude-opus-4-5-20251101": (15.0, 75.0),
    "claude-sonnet-4-5-20250929": (3.0, 15.0),
    "claude-sonnet-4-20250514": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
}


def _estimate_cost(call: dict) -> float:
    """Estimate USD cost for a single LLM call."""
    model = call["model"]
    input_price, output_price = _PRICING.get(model, (3.0, 15.0))  # default to sonnet
    input_cost = call["input_tokens"] * input_price / 1_000_000
    output_cost = call["output_tokens"] * output_price / 1_000_000
    # Cache reads are 90% cheaper
    cache_discount = call.get("cache_read", 0) * input_price * 0.9 / 1_000_000
    return input_cost + output_cost - cache_discount


def _format_summary() -> str:
    """Format LLM usage summary for the run."""
    if not _llm_calls:
        return "\n--- LLM USAGE SUMMARY ---\nNo LLM calls recorded.\n"

    lines = ["\n" + "=" * 60, "LLM USAGE SUMMARY", "=" * 60]

    # Normalize model IDs to family names for grouping
    def _model_family(model_id: str) -> str:
        if "opus" in model_id:
            return "OPUS"
        if "sonnet" in model_id:
            return "SONNET"
        if "haiku" in model_id:
            return "HAIKU"
        return model_id

    # Group by model family
    by_model = {}
    for call in _llm_calls:
        family = _model_family(call["model"])
        if family not in by_model:
            by_model[family] = {"calls": 0, "input": 0, "output": 0, "cost": 0.0}
        by_model[family]["calls"] += 1
        by_model[family]["input"] += call["input_tokens"]
        by_model[family]["output"] += call["output_tokens"]
        by_model[family]["cost"] += _estimate_cost(call)

    total_calls = 0
    total_input = 0
    total_output = 0
    total_cost = 0.0

    for model, stats in sorted(by_model.items()):
        lines.append(f"\n  {model}:")
        lines.append(f"    Calls:  {stats['calls']}")
        lines.append(f"    Input:  {stats['input']:,} tokens")
        lines.append(f"    Output: {stats['output']:,} tokens")
        lines.append(f"    Cost:   ${stats['cost']:.4f}")
        total_calls += stats["calls"]
        total_input += stats["input"]
        total_output += stats["output"]
        total_cost += stats["cost"]

    lines.append(f"\n  TOTAL:")
    lines.append(f"    Calls:  {total_calls}")
    lines.append(f"    Tokens: {total_input + total_output:,} ({total_input:,} in + {total_output:,} out)")
    lines.append(f"    Cost:   ${total_cost:.4f}")
    lines.append("=" * 60)

    return "\n".join(lines)


class RunLogger:
    """Context manager that captures pipeline output to a timestamped log file."""

    def __init__(self, query: str = ""):
        self.query = query
        self.log_file = None
        self.log_path = None
        self.original_stdout = None
        self.original_stderr = None
        self.start_time = None

    def __enter__(self):
        global _llm_calls, _logging_active

        LOGS_DIR.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_path = LOGS_DIR / f"run_{timestamp}.log"
        self.log_file = open(self.log_path, "w", encoding="utf-8")

        # Write header
        self.log_file.write(f"Pipeline Run: {datetime.now().isoformat()}\n")
        self.log_file.write(f"Query: {self.query}\n")
        self.log_file.write("=" * 60 + "\n\n")
        self.log_file.flush()

        # Reset LLM call tracker
        with _llm_lock:
            _llm_calls = []
        _logging_active = True

        # Tee stdout and stderr
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
        sys.stdout = _TeeWriter(self.original_stdout, self.log_file)
        sys.stderr = _TeeWriter(self.original_stderr, self.log_file)

        self.start_time = time.time()

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        global _logging_active
        _logging_active = False

        elapsed = time.time() - self.start_time

        # Write summary
        summary = _format_summary()
        # Print to both stdout and log
        print(summary)
        print(f"\nPipeline duration: {elapsed:.1f}s")
        print(f"Log saved to: {self.log_path}")

        # Restore streams
        sys.stdout = self.original_stdout
        sys.stderr = self.original_stderr

        # Close log file
        if self.log_file:
            self.log_file.close()

        return False  # Don't suppress exceptions
