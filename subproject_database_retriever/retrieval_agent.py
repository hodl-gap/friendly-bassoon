"""Agentic retrieval phase — replaces the fixed LangGraph flow when AGENT_RETRIEVAL flag is on.

The agent iteratively searches, assesses coverage, and fills gaps until
the coverage checker says ADEQUATE/COMPLETE or max iterations is reached.

Phase 0 (EDF Decomposition): When enabled, an Opus call decomposes the query into
a structured knowledge tree across 7 knowledge dimensions. This replaces generic
query expansion with targeted retrieval guided by the tree's searchable_query fields.

Phase 0.5 (Mechanical Pre-Fetch): Deterministically executes the EDF search plan
before the agent loop starts — runs all research_db queries against Pinecone and
ESSENTIAL web_search queries via web search. The agent loop then only handles
adaptive gap-filling, not initial retrieval.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from shared.agent_loop import run_agent_loop
from shared.feature_flags import retrieval_max_iterations, edf_enabled
from retrieval_agent_prompts import (
    RETRIEVAL_AGENT_SYSTEM_PROMPT,
    RETRIEVAL_AGENT_SYSTEM_PROMPT_EDF,
)
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
    from shared.debug_logger import debug_log_node
    debug_log_node("retrieval_agent", "ENTER", f"query={query[:100]}")
    print(f"\n[Retrieval Agent] Starting agentic retrieval for: {query[:100]}...")

    # Phase 0: EDF Decomposition (if enabled)
    knowledge_tree = None
    if edf_enabled():
        knowledge_tree = _run_edf_decomposition(query)

    # Initialize mutable state
    agent_state = RetrievalAgentState(
        query=query,
        image_path=image_path,
        knowledge_tree=knowledge_tree,
    )
    tool_handlers = build_tool_handlers(agent_state)

    # Phase 0.5: Mechanical pre-fetch using EDF search plan
    # Deterministically runs all research_db and ESSENTIAL web queries
    # before the agent loop, so the agent only does adaptive gap-filling
    if knowledge_tree and knowledge_tree.get("keywords"):
        _run_edf_prefetch(query, knowledge_tree, agent_state)
        initial_message = _build_edf_initial_message(query, knowledge_tree, agent_state)
        system_prompt = RETRIEVAL_AGENT_SYSTEM_PROMPT_EDF
    else:
        initial_message = (
            f"Research query: {query}\n\n"
            "Start by searching the Pinecone vector database with the original query "
            "and 2-3 alternative phrasings. Then assess coverage."
        )
        system_prompt = RETRIEVAL_AGENT_SYSTEM_PROMPT

    # Run the agent loop
    loop_result = run_agent_loop(
        system_prompt=system_prompt,
        tools=ALL_TOOLS,
        tool_handlers=tool_handlers,
        initial_message=initial_message,
        exit_tool_name="finish_retrieval",
        model="sonnet",
        max_iterations=retrieval_max_iterations(),
        temperature=0.2,
        max_tokens=4000,
        phase_label="Retrieval",
    )

    print(f"\n[Retrieval Agent] Completed: {loop_result['exit_reason']} "
          f"({loop_result['iterations']} iterations, "
          f"{len(loop_result['tool_calls'])} tool calls)")

    # If synthesis wasn't generated yet (agent hit max iterations), generate now
    if not agent_state.synthesis and agent_state.chunks:
        print("[Retrieval Agent] Generating synthesis (agent didn't finish synthesis step)...")
        tool_handlers["generate_synthesis"]()

    # Build return state compatible with RetrieverState
    debug_log_node("retrieval_agent", "EXIT", (
        f"exit_reason={loop_result['exit_reason']}, "
        f"iterations={loop_result['iterations']}, "
        f"chunks={len(agent_state.chunks)}, "
        f"chains={len(agent_state.logic_chains)}"
    ))
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
        # EDF metadata
        "_edf_knowledge_tree": knowledge_tree,
        # Agent metadata
        "_agent_iterations": loop_result["iterations"],
        "_agent_exit_reason": loop_result["exit_reason"],
        "_agent_tool_calls": len(loop_result["tool_calls"]),
    }


def _run_edf_decomposition(query: str) -> dict:
    """Run Phase 0: EDF query decomposition via Opus."""
    from edf_decomposer import decompose_query

    print(f"\n{'='*60}")
    print(f"[Phase 0] EDF Decomposition")
    print(f"{'='*60}")

    try:
        tree = decompose_query(query)
        keyword_count = len(tree.get("keywords", []))
        item_count = sum(len(kw.get("items", [])) for kw in tree.get("keywords", []))
        print(f"[Phase 0] Complete: {keyword_count} keywords, {item_count} items")
        return tree
    except Exception as e:
        print(f"[Phase 0] EDF decomposition failed: {e}")
        print("[Phase 0] Falling back to generic retrieval")
        return None


def _run_edf_prefetch(query: str, tree: dict, agent_state: RetrievalAgentState):
    """Phase 0.5: Mechanically execute the EDF search plan before the agent loop.

    Runs all research_db queries against Pinecone and ESSENTIAL web_search queries
    via web search. This is deterministic — no LLM decision-making about which
    queries to run. The agent loop then only needs to assess and fill gaps.
    """
    from edf_decomposer import get_search_plan
    from vector_search import search_single_query, EXCLUDE_WEB_CHAINS_FILTER

    plan = get_search_plan(tree)

    print(f"\n{'='*60}")
    print(f"[Phase 0.5] EDF Pre-Fetch")
    print(f"{'='*60}")

    # --- Pinecone: run ALL research_db queries ---
    db_queries = plan.get("research_db", [])
    if db_queries:
        # Deduplicate similar queries by keeping unique searchable_query strings
        seen_queries = set()
        unique_queries = []
        for q in db_queries:
            query_text = q["query"].strip().lower()
            if query_text and query_text not in seen_queries:
                seen_queries.add(query_text)
                unique_queries.append(q)

        print(f"[Pre-Fetch] Running {len(unique_queries)} Pinecone queries "
              f"(from {len(db_queries)} research_db items)")

        for q in unique_queries:
            try:
                chunks = search_single_query(
                    q["query"], top_k=5, threshold=0.50, filter=EXCLUDE_WEB_CHAINS_FILTER
                )
                agent_state.add_chunks(chunks)
                print(f"  [{q['priority']}] {q['id']}: \"{q['query'][:60]}\" → {len(chunks)} chunks")
            except Exception as e:
                print(f"  [{q['priority']}] {q['id']}: ERROR: {e}")

    # Also run the original query itself (often the best single search)
    try:
        chunks = search_single_query(query, top_k=8, threshold=0.50, filter=EXCLUDE_WEB_CHAINS_FILTER)
        before = len(agent_state.chunks)
        agent_state.add_chunks(chunks)
        added = len(agent_state.chunks) - before
        print(f"  [ORIGINAL] \"{query[:60]}\" → {len(chunks)} chunks ({added} new)")
    except Exception as e:
        print(f"  [ORIGINAL] ERROR: {e}")

    print(f"[Pre-Fetch] Total Pinecone chunks: {len(agent_state.chunks)}")

    # --- Web: run ESSENTIAL web_search queries ---
    web_queries = [q for q in plan.get("web_search", []) if q["priority"] == "ESSENTIAL"]
    if web_queries:
        print(f"[Pre-Fetch] Running {len(web_queries)} ESSENTIAL web searches")

        for q in web_queries:
            try:
                from knowledge_gap_detector import _get_web_search_adapter, _search_and_evaluate
                adapter = _get_web_search_adapter()
                if adapter is None:
                    print(f"  [{q['id']}]: WebSearchAdapter not available, skipping")
                    break
                result = _search_and_evaluate(adapter, q["query"], "general", query)
                agent_state.web_search_results.append(result)
                found = result.get("found", False)
                print(f"  [ESSENTIAL] {q['id']}: \"{q['query'][:60]}\" → {'found' if found else 'not found'}")
            except Exception as e:
                print(f"  [ESSENTIAL] {q['id']}: ERROR: {e}")

    # --- Web chains: extract for the main query ---
    # This is always valuable — provides causal mechanisms Pinecone lacks
    print(f"[Pre-Fetch] Extracting web chains for main query")
    try:
        from vector_search import search_saved_web_chains
        from knowledge_gap_detector import fill_gaps_with_web_chains, _convert_saved_chunks_to_web_chains

        saved_chunks = search_saved_web_chains(query)
        saved_chains = _convert_saved_chunks_to_web_chains(saved_chunks) if saved_chunks else []

        if len(saved_chunks) >= 3 and saved_chains:
            agent_state.web_chains.extend(saved_chains)
            print(f"  Using {len(saved_chains)} saved web chains from Pinecone")
        else:
            gaps = [{
                "category": "topic_not_covered",
                "status": "GAP",
                "missing": query,
                "fill_method": "web_chain_extraction",
            }]
            result = fill_gaps_with_web_chains(
                gaps=gaps, query=query,
                min_tier=2, min_trusted_sources=2, confidence_weight=0.7,
            )
            new_chains = result.get("extracted_chains", [])
            all_chains = saved_chains + new_chains
            agent_state.web_chains.extend(all_chains)
            print(f"  Extracted {len(new_chains)} new web chains "
                  f"(+{len(saved_chains)} saved = {len(all_chains)} total)")
    except Exception as e:
        print(f"  Web chain extraction failed: {e}")

    print(f"[Pre-Fetch] Complete: {len(agent_state.chunks)} chunks, "
          f"{len(agent_state.web_chains)} web chains, "
          f"{len(agent_state.web_search_results)} web search results")


def _build_edf_initial_message(query: str, tree: dict, agent_state: RetrievalAgentState) -> str:
    """Build the initial message for the agent after EDF pre-fetch.

    Tells the agent what was already gathered and instructs it to assess
    coverage then fill remaining gaps.
    """
    from edf_decomposer import format_search_plan_for_agent

    search_plan = format_search_plan_for_agent(tree)

    return (
        f"Research query: {query}\n\n"
        f"## Pre-Fetch Results\n\n"
        f"The EDF search plan has already been executed mechanically. Material gathered so far:\n"
        f"- Pinecone chunks: {len(agent_state.chunks)}\n"
        f"- Web chains: {len(agent_state.web_chains)}\n"
        f"- Web search results: {len(agent_state.web_search_results)}\n\n"
        f"## Knowledge Tree (for reference)\n\n"
        f"{search_plan}\n\n"
        f"## Instructions\n\n"
        f"1. Call assess_coverage FIRST to score the pre-fetched material against the knowledge tree\n"
        f"2. If INSUFFICIENT: use the essential_gaps and suggested_queries from the response to fill specific gaps\n"
        f"3. After filling gaps, call assess_coverage again\n"
        f"4. Once ADEQUATE or COMPLETE: call generate_synthesis immediately\n"
        f"5. After synthesis: call finish_retrieval"
    )
