"""Generic ReAct loop runner for all agentic phases.

Implements a conversational tool-use loop using call_claude_with_tools().
Each iteration: send messages -> parse response -> if tool_use, execute handler,
append tool_result, continue. If exit tool called, return its input.

Step mode (STEP_MODE=1): pauses after each LLM decision and tool execution
for interactive inspection.
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from models import call_claude_with_tools


# =============================================================================
# Step Mode Helpers
# =============================================================================

def _step_show_decision(phase_label, iteration, max_iterations, text_blocks, tool_use_blocks):
    """Display full LLM reasoning and tool choices for step mode."""
    w = 80
    print(f"\n{'═' * w}")
    print(f"  STEP [{phase_label}] Iteration {iteration}/{max_iterations} — LLM Decision")
    print(f"{'═' * w}")

    if text_blocks:
        print(f"\n  REASONING:")
        print(f"  {'─' * (w - 4)}")
        for tb in text_blocks:
            for line in tb.text.split('\n'):
                print(f"  {line}")

    print(f"\n  TOOL CALLS ({len(tool_use_blocks)}):")
    print(f"  {'─' * (w - 4)}")
    for i, tb in enumerate(tool_use_blocks, 1):
        is_exit = hasattr(tb, '_is_exit') and tb._is_exit
        label = f"  [{i}] {tb.name}" + (" [EXIT TOOL]" if is_exit else "")
        print(label)
        input_str = json.dumps(tb.input, default=str, indent=2)
        for line in input_str.split('\n'):
            print(f"      {line}")

    print(f"{'═' * w}")


def _step_show_results(phase_label, iteration, results_data):
    """Display full tool results for step mode."""
    w = 80
    print(f"\n{'═' * w}")
    print(f"  STEP [{phase_label}] Iteration {iteration} — Tool Results")
    print(f"{'═' * w}")

    for tool_name, result_str in results_data:
        print(f"\n  {tool_name}:")
        print(f"  {'─' * (w - 4)}")
        for line in result_str.split('\n'):
            print(f"  {line}")

    print(f"{'═' * w}")


def _step_show_exit(phase_label, iteration, exit_tool_name, exit_input):
    """Display exit tool result for step mode."""
    w = 80
    print(f"\n{'═' * w}")
    print(f"  STEP [{phase_label}] Iteration {iteration} — Phase Complete ({exit_tool_name})")
    print(f"{'═' * w}")

    input_str = json.dumps(exit_input, default=str, indent=2)
    for line in input_str.split('\n'):
        print(f"  {line}")

    print(f"{'═' * w}")


_STEP_SIGNAL_FILE = Path("/tmp/claude_step_signal")


def _step_wait(action_desc):
    """Wait for signal file to advance. Write 'go' to /tmp/claude_step_signal to proceed."""
    # Clean up any leftover signal
    _STEP_SIGNAL_FILE.unlink(missing_ok=True)

    print(f"\n  >> PAUSED. Waiting for signal to {action_desc}...")
    print(f"  >> Write 'go' to {_STEP_SIGNAL_FILE} to advance")
    sys.stdout.flush()

    while True:
        if _STEP_SIGNAL_FILE.exists():
            _STEP_SIGNAL_FILE.unlink(missing_ok=True)
            print("  >> Advancing...")
            break
        time.sleep(0.5)


# =============================================================================
# Main Agent Loop
# =============================================================================

def run_agent_loop(
    system_prompt: str,
    tools: list,
    tool_handlers: dict,
    initial_message: str,
    exit_tool_name: str,
    model: str = "sonnet",
    max_iterations: int = 10,
    temperature: float = 0.2,
    max_tokens: int = 4000,
    phase_label: str = "Agent",
) -> dict:
    """
    Generic ReAct agent loop.

    Args:
        system_prompt: System prompt for the agent
        tools: Anthropic tool_use definitions
        tool_handlers: {tool_name: callable(**kwargs) -> serializable}
        initial_message: User message seeding the conversation
        exit_tool_name: Tool name that signals phase completion
        model: "sonnet", "opus", or "haiku"
        max_iterations: Maximum loop iterations
        temperature: Model temperature
        max_tokens: Max tokens per response
        phase_label: Label for this phase in debug logs (e.g., "Retrieval", "DataGrounding")

    Returns:
        {
            "result": <exit tool input dict>,
            "iterations": int,
            "tool_calls": [{"tool", "input", "iteration", "result_preview"}],
            "exit_reason": "exit_tool" | "max_iterations" | "text_response"
        }
    """
    from shared.debug_logger import debug_log, debug_log_node
    from shared.feature_flags import step_mode_enabled

    tag = f"AGENT_LOOP[{phase_label}]"
    stepping = step_mode_enabled()

    debug_log(f"{tag} START", (
        f"Phase: {phase_label}\n"
        f"Model: {model}\n"
        f"Max iterations: {max_iterations}\n"
        f"Exit tool: {exit_tool_name}\n"
        f"Tools available: {[t['name'] for t in tools]}\n"
        f"Step mode: {stepping}\n"
        f"Initial message:\n{initial_message}"
    ))

    messages = [{"role": "user", "content": initial_message}]
    tool_call_log = []
    loop_start = time.time()

    for iteration in range(1, max_iterations + 1):
        print(f"\n[Agent Loop] Iteration {iteration}/{max_iterations}")
        debug_log(f"{tag} ITERATION {iteration}/{max_iterations}", f"Starting iteration {iteration}")

        response = call_claude_with_tools(
            messages=messages,
            tools=tools,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            system=system_prompt,
        )

        assistant_content = response.content

        tool_use_blocks = [b for b in assistant_content if b.type == "tool_use"]
        text_blocks = [b for b in assistant_content if b.type == "text"]

        if text_blocks:
            for tb in text_blocks:
                if not stepping:
                    print(f"[Agent Loop] Agent: {tb.text[:300]}...")
                debug_log(f"{tag} AGENT_TEXT iter={iteration}", tb.text)

        if not tool_use_blocks:
            # No tool calls — agent responded with text only
            print("[Agent Loop] Agent responded with text only (no tool calls)")
            debug_log(f"{tag} EXIT text_response", f"Agent produced text-only response at iteration {iteration}")
            return {
                "result": {"text": " ".join(tb.text for tb in text_blocks)},
                "iterations": iteration,
                "tool_calls": tool_call_log,
                "exit_reason": "text_response",
            }

        # Step mode: show LLM decision before executing tools
        if stepping:
            _step_show_decision(phase_label, iteration, max_iterations, text_blocks, tool_use_blocks)
            _step_wait("execute tools")

        # Build assistant message with all content blocks
        assistant_message = {"role": "assistant", "content": []}
        for block in assistant_content:
            if block.type == "text":
                assistant_message["content"].append({
                    "type": "text",
                    "text": block.text,
                })
            elif block.type == "tool_use":
                assistant_message["content"].append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })
        messages.append(assistant_message)

        # Process each tool call
        tool_results = []
        exit_result = None
        step_results_data = []

        for tool_block in tool_use_blocks:
            tool_name = tool_block.name
            tool_input = tool_block.input
            tool_id = tool_block.id

            input_preview = json.dumps(tool_input, default=str)[:200]
            if not stepping:
                print(f"[Agent Loop] Tool call: {tool_name}({input_preview})")
            debug_log(f"{tag} TOOL_CALL iter={iteration} tool={tool_name}", (
                f"Tool: {tool_name}\n"
                f"Input: {json.dumps(tool_input, default=str, indent=2)}"
            ))

            # Check if this is the exit tool
            if tool_name == exit_tool_name:
                elapsed = time.time() - loop_start
                if not stepping:
                    print(f"[Agent Loop] Exit tool called after {iteration} iterations")
                debug_log(f"{tag} EXIT exit_tool", (
                    f"Exit tool '{exit_tool_name}' called at iteration {iteration}\n"
                    f"Total tool calls: {len(tool_call_log) + 1}\n"
                    f"Elapsed: {elapsed:.1f}s\n"
                    f"Exit input: {json.dumps(tool_input, default=str, indent=2)}"
                ))
                tool_call_log.append({
                    "tool": tool_name,
                    "input": tool_input,
                    "iteration": iteration,
                    "result_preview": "[exit]",
                })
                # Append a tool result for API compliance before returning
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": json.dumps({"status": "completed"}),
                })
                exit_result = tool_input
                continue

            # Execute tool handler
            handler = tool_handlers.get(tool_name)
            if handler is None:
                result_str = json.dumps({"error": f"Unknown tool: {tool_name}"})
            else:
                try:
                    result = handler(**tool_input)
                    result_str = json.dumps(result, default=str) if not isinstance(result, str) else result
                except Exception as e:
                    print(f"[Agent Loop] Tool error: {tool_name}: {e}")
                    result_str = json.dumps({"error": str(e)})

            # Truncate long results for context management
            if len(result_str) > 15000:
                result_str = result_str[:15000] + "\n... [truncated]"

            result_preview = result_str[:200] + "..." if len(result_str) > 200 else result_str
            if not stepping:
                print(f"[Agent Loop] Result: {result_preview}")
            debug_log(f"{tag} TOOL_RESULT iter={iteration} tool={tool_name}", (
                f"Tool: {tool_name}\n"
                f"Result ({len(result_str)} chars):\n{result_str}"
            ))

            # Collect for step mode display
            step_results_data.append((tool_name, result_str))

            tool_call_log.append({
                "tool": tool_name,
                "input": tool_input,
                "iteration": iteration,
                "result_preview": result_preview,
            })

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": result_str,
            })

        # If exit tool was called, return now
        if exit_result is not None:
            if stepping:
                _step_show_exit(phase_label, iteration, exit_tool_name, exit_result)
                _step_wait("finish this phase")
            return {
                "result": exit_result,
                "iterations": iteration,
                "tool_calls": tool_call_log,
                "exit_reason": "exit_tool",
            }

        # Step mode: show tool results before next LLM call
        if stepping and step_results_data:
            _step_show_results(phase_label, iteration, step_results_data)
            _step_wait("call LLM with results")

        # Append all tool results as a user message
        messages.append({"role": "user", "content": tool_results})

    # Max iterations reached
    elapsed = time.time() - loop_start
    print(f"[Agent Loop] Max iterations ({max_iterations}) reached")
    debug_log(f"{tag} EXIT max_iterations", (
        f"Hit max iterations ({max_iterations})\n"
        f"Total tool calls: {len(tool_call_log)}\n"
        f"Elapsed: {elapsed:.1f}s"
    ))
    return {
        "result": {},
        "iterations": max_iterations,
        "tool_calls": tool_call_log,
        "exit_reason": "max_iterations",
    }
