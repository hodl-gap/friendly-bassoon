"""Generic ReAct loop runner for all agentic phases.

Implements a conversational tool-use loop using call_claude_with_tools().
Each iteration: send messages -> parse response -> if tool_use, execute handler,
append tool_result, continue. If exit tool called, return its input.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from models import call_claude_with_tools


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

    Returns:
        {
            "result": <exit tool input dict>,
            "iterations": int,
            "tool_calls": [{"tool", "input", "iteration", "result_preview"}],
            "exit_reason": "exit_tool" | "max_iterations" | "text_response"
        }
    """
    messages = [{"role": "user", "content": initial_message}]
    tool_call_log = []

    for iteration in range(1, max_iterations + 1):
        print(f"\n[Agent Loop] Iteration {iteration}/{max_iterations}")

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
                print(f"[Agent Loop] Agent: {tb.text[:300]}...")

        if not tool_use_blocks:
            # No tool calls — agent responded with text only
            print("[Agent Loop] Agent responded with text only (no tool calls)")
            return {
                "result": {"text": " ".join(tb.text for tb in text_blocks)},
                "iterations": iteration,
                "tool_calls": tool_call_log,
                "exit_reason": "text_response",
            }

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

        for tool_block in tool_use_blocks:
            tool_name = tool_block.name
            tool_input = tool_block.input
            tool_id = tool_block.id

            input_preview = json.dumps(tool_input, default=str)[:200]
            print(f"[Agent Loop] Tool call: {tool_name}({input_preview})")

            # Check if this is the exit tool
            if tool_name == exit_tool_name:
                print(f"[Agent Loop] Exit tool called after {iteration} iterations")
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
            print(f"[Agent Loop] Result: {result_preview}")

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
            return {
                "result": exit_result,
                "iterations": iteration,
                "tool_calls": tool_call_log,
                "exit_reason": "exit_tool",
            }

        # Append all tool results as a user message
        messages.append({"role": "user", "content": tool_results})

    # Max iterations reached
    print(f"[Agent Loop] Max iterations ({max_iterations}) reached")
    return {
        "result": {},
        "iterations": max_iterations,
        "tool_calls": tool_call_log,
        "exit_reason": "max_iterations",
    }
