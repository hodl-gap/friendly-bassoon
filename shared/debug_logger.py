"""
Debug Logger — Full Pipeline Tracing

Provides comprehensive logging of ALL API calls, data fetches, and pipeline steps.
When enabled, monkey-patches Anthropic and OpenAI SDK clients so that every call
is logged with full request/response. No truncation.

Usage:
    from shared.debug_logger import init_debug_log, close_debug_log

    init_debug_log("logs/debug_case1_run1.log")
    # ... run pipeline ...
    close_debug_log()
"""

import json
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

_debug_file = None
_debug_lock = threading.Lock()
_patches_applied = False


def init_debug_log(log_path: str) -> None:
    """Open debug log file and apply SDK monkey-patches."""
    global _debug_file, _patches_applied
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _debug_file = open(path, "w", encoding="utf-8")
    _debug_file.write(f"DEBUG LOG STARTED: {datetime.now().isoformat()}\n")
    _debug_file.write(f"Log file: {log_path}\n")
    _debug_file.write("=" * 120 + "\n\n")
    _debug_file.flush()

    if not _patches_applied:
        _apply_patches()
        _patches_applied = True


def close_debug_log() -> None:
    """Close the debug log file."""
    global _debug_file
    if _debug_file:
        _debug_file.write(f"\n\nDEBUG LOG ENDED: {datetime.now().isoformat()}\n")
        _debug_file.close()
        _debug_file = None


def debug_log(section: str, content: str) -> None:
    """Write a section to the debug log. Thread-safe. No truncation."""
    if not _debug_file:
        return
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    with _debug_lock:
        _debug_file.write(f"\n{'=' * 120}\n")
        _debug_file.write(f"[{timestamp}] {section}\n")
        _debug_file.write(f"{'=' * 120}\n")
        _debug_file.write(content)
        _debug_file.write("\n")
        _debug_file.flush()


def debug_log_node(node_name: str, direction: str = "ENTER", details: str = "") -> None:
    """Log pipeline node entry/exit."""
    if not _debug_file:
        return
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    marker = ">>>" if direction == "ENTER" else "<<<"
    with _debug_lock:
        _debug_file.write(f"\n{'#' * 120}\n")
        _debug_file.write(f"[{timestamp}] {marker} NODE: {node_name} ({direction})\n")
        if details:
            _debug_file.write(f"    {details}\n")
        _debug_file.write(f"{'#' * 120}\n")
        _debug_file.flush()


def debug_log_data_fetch(source: str, endpoint: str, params: dict, result: Any) -> None:
    """Log a data fetch (FRED, Yahoo, CoinGecko, Pinecone, etc.)."""
    if not _debug_file:
        return
    content = f"Source: {source}\nEndpoint: {endpoint}\n"
    content += f"Params: {json.dumps(params, default=str, indent=2)}\n"
    content += f"Result:\n{_serialize(result)}\n"
    debug_log(f"DATA_FETCH [{source}]", content)


def debug_log_web_search(query: str, results: Any) -> None:
    """Log a web search query and full results."""
    if not _debug_file:
        return
    content = f"Query: {query}\n\nResults:\n{_serialize(results)}\n"
    debug_log("WEB_SEARCH", content)


def _serialize(obj: Any) -> str:
    """Serialize any object to string for logging. No truncation."""
    if isinstance(obj, str):
        return obj
    try:
        return json.dumps(obj, default=str, indent=2, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(obj)


# =============================================================================
# SDK Monkey-Patches
# =============================================================================

def _apply_patches() -> None:
    """Monkey-patch Anthropic and OpenAI SDKs to log all API calls."""
    _patch_anthropic()
    _patch_openai()


def _patch_anthropic() -> None:
    """Wrap anthropic.resources.messages.Messages.create to log full request/response."""
    try:
        import anthropic.resources.messages

        original_create = anthropic.resources.messages.Messages.create

        def patched_create(self, *args, **kwargs):
            call_id = f"anthropic_{int(time.time()*1000) % 100000}"
            start = time.time()

            # Log the full request
            request_data = {}
            request_data["model"] = kwargs.get("model", "unknown")
            request_data["temperature"] = kwargs.get("temperature")
            request_data["max_tokens"] = kwargs.get("max_tokens")

            # System prompt
            system = kwargs.get("system")
            if system:
                request_data["system"] = system

            # Messages (full content, no truncation)
            messages = kwargs.get("messages", [])
            request_data["messages"] = messages

            # Tools
            tools = kwargs.get("tools")
            if tools:
                request_data["tools"] = tools

            tool_choice = kwargs.get("tool_choice")
            if tool_choice:
                request_data["tool_choice"] = tool_choice

            debug_log(
                f"ANTHROPIC_REQUEST [{call_id}] model={request_data['model']}",
                _serialize(request_data)
            )

            # Make the actual call
            response = original_create(self, *args, **kwargs)
            elapsed = time.time() - start

            # Log the full response
            response_data = {}
            response_data["elapsed_seconds"] = round(elapsed, 2)
            response_data["stop_reason"] = getattr(response, "stop_reason", None)

            # Usage
            usage = getattr(response, "usage", None)
            if usage:
                response_data["usage"] = {
                    "input_tokens": getattr(usage, "input_tokens", 0),
                    "output_tokens": getattr(usage, "output_tokens", 0),
                    "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", 0),
                    "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", 0),
                }

            # Content blocks (full, no truncation)
            content_blocks = getattr(response, "content", [])
            response_data["content"] = []
            for block in content_blocks:
                block_type = getattr(block, "type", "unknown")
                if block_type == "text":
                    response_data["content"].append({
                        "type": "text",
                        "text": getattr(block, "text", ""),
                    })
                elif block_type == "tool_use":
                    response_data["content"].append({
                        "type": "tool_use",
                        "id": getattr(block, "id", ""),
                        "name": getattr(block, "name", ""),
                        "input": getattr(block, "input", {}),
                    })
                else:
                    response_data["content"].append({"type": block_type, "raw": str(block)})

            debug_log(
                f"ANTHROPIC_RESPONSE [{call_id}] {elapsed:.1f}s",
                _serialize(response_data)
            )

            return response

        anthropic.resources.messages.Messages.create = patched_create

    except ImportError:
        pass  # anthropic not installed
    except Exception as e:
        debug_log("PATCH_ERROR", f"Failed to patch Anthropic: {e}")


def _patch_openai() -> None:
    """Wrap OpenAI chat completions and embeddings to log full request/response."""
    try:
        # Patch chat completions
        import openai.resources.chat.completions

        original_chat_create = openai.resources.chat.completions.Completions.create

        def patched_chat_create(self, *args, **kwargs):
            call_id = f"openai_chat_{int(time.time()*1000) % 100000}"
            start = time.time()

            request_data = {
                "model": kwargs.get("model", "unknown"),
                "temperature": kwargs.get("temperature"),
                "max_tokens": kwargs.get("max_tokens"),
                "max_completion_tokens": kwargs.get("max_completion_tokens"),
                "messages": kwargs.get("messages", []),
            }

            debug_log(
                f"OPENAI_CHAT_REQUEST [{call_id}] model={request_data['model']}",
                _serialize(request_data)
            )

            response = original_chat_create(self, *args, **kwargs)
            elapsed = time.time() - start

            response_data = {
                "elapsed_seconds": round(elapsed, 2),
                "model": getattr(response, "model", "unknown"),
            }

            # Usage
            usage = getattr(response, "usage", None)
            if usage:
                response_data["usage"] = {
                    "prompt_tokens": getattr(usage, "prompt_tokens", 0),
                    "completion_tokens": getattr(usage, "completion_tokens", 0),
                    "total_tokens": getattr(usage, "total_tokens", 0),
                }

            # Choices (full content)
            choices = getattr(response, "choices", [])
            response_data["choices"] = []
            for choice in choices:
                msg = getattr(choice, "message", None)
                if msg:
                    response_data["choices"].append({
                        "role": getattr(msg, "role", ""),
                        "content": getattr(msg, "content", ""),
                    })

            debug_log(
                f"OPENAI_CHAT_RESPONSE [{call_id}] {elapsed:.1f}s",
                _serialize(response_data)
            )

            return response

        openai.resources.chat.completions.Completions.create = patched_chat_create

        # Patch embeddings
        import openai.resources.embeddings

        original_embed_create = openai.resources.embeddings.Embeddings.create

        def patched_embed_create(self, *args, **kwargs):
            call_id = f"openai_embed_{int(time.time()*1000) % 100000}"

            input_data = kwargs.get("input", "")
            model = kwargs.get("model", "unknown")

            # Log request (full text, no truncation)
            request_data = {
                "model": model,
                "input": input_data,
            }
            debug_log(
                f"OPENAI_EMBEDDING_REQUEST [{call_id}] model={model}",
                _serialize(request_data)
            )

            response = original_embed_create(self, *args, **kwargs)

            # Log response (dimensions only for embeddings, not full vectors)
            data = getattr(response, "data", [])
            response_data = {
                "embedding_count": len(data),
                "dimensions": len(data[0].embedding) if data else 0,
            }
            usage = getattr(response, "usage", None)
            if usage:
                response_data["usage"] = {
                    "prompt_tokens": getattr(usage, "prompt_tokens", 0),
                    "total_tokens": getattr(usage, "total_tokens", 0),
                }

            debug_log(
                f"OPENAI_EMBEDDING_RESPONSE [{call_id}]",
                _serialize(response_data)
            )

            return response

        openai.resources.embeddings.Embeddings.create = patched_embed_create

    except ImportError:
        pass  # openai not installed
    except Exception as e:
        debug_log("PATCH_ERROR", f"Failed to patch OpenAI: {e}")
