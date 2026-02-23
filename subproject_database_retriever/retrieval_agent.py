"""Agentic retrieval phase — replaces the fixed LangGraph flow when AGENT_RETRIEVAL flag is on.

The agent iteratively searches, assesses coverage, and fills gaps until
the coverage checker says ADEQUATE/COMPLETE or max iterations is reached.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from shared.agent_loop import run_agent_loop
from shared.feature_flags import retrieval_max_iterations
from retrieval_agent_prompts import RETRIEVAL_AGENT_SYSTEM_PROMPT
from retrieval_agent_tools import (
    ALL_TOOLS,
    RetrievalAgentState,
    build_tool_handlers,
)


def run_retrieval_agent(query: str, image_path: str = None) -> dict:
    """
    Agentic retrieval: iteratively gathers material until coverage is adequate.

    Returns: dict compatible with RetrieverState (same fields as run_retrieval).
    """
    print(f"\n[Retrieval Agent] Starting agentic retrieval for: {query[:100]}...")

    # Initialize mutable state
    agent_state = RetrievalAgentState(query=query, image_path=image_path)
    tool_handlers = build_tool_handlers(agent_state)

    # Build initial message
    initial_message = (
        f"Research query: {query}\n\n"
        "Start by searching the Pinecone vector database with the original query "
        "and 2-3 alternative phrasings. Then assess coverage."
    )

    # Run the agent loop
    loop_result = run_agent_loop(
        system_prompt=RETRIEVAL_AGENT_SYSTEM_PROMPT,
        tools=ALL_TOOLS,
        tool_handlers=tool_handlers,
        initial_message=initial_message,
        exit_tool_name="finish_retrieval",
        model="sonnet",
        max_iterations=retrieval_max_iterations(),
        temperature=0.2,
        max_tokens=4000,
    )

    print(f"\n[Retrieval Agent] Completed: {loop_result['exit_reason']} "
          f"({loop_result['iterations']} iterations, "
          f"{len(loop_result['tool_calls'])} tool calls)")

    # If synthesis wasn't generated yet (agent hit max iterations), generate now
    if not agent_state.synthesis and agent_state.chunks:
        print("[Retrieval Agent] Generating synthesis (agent didn't finish synthesis step)...")
        tool_handlers["generate_synthesis"]()

    # Build return state compatible with RetrieverState
    return {
        "query": query,
        "answer": agent_state.answer,
        "synthesis": agent_state.synthesis,
        "retrieved_chunks": agent_state.chunks,
        "logic_chains": agent_state.logic_chains,
        "confidence_metadata": agent_state.confidence_metadata,
        "topic_coverage": agent_state.topic_coverage,
        "knowledge_gaps": {},
        "gap_enrichment_text": "",
        "filled_gaps": [],
        "partially_filled_gaps": [],
        "unfillable_gaps": [],
        "extracted_web_chains": agent_state.web_chains,
        # Agent metadata
        "_agent_iterations": loop_result["iterations"],
        "_agent_exit_reason": loop_result["exit_reason"],
        "_agent_tool_calls": len(loop_result["tool_calls"]),
    }
