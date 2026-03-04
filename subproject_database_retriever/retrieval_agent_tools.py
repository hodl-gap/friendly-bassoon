"""Tool schemas and handlers for the retrieval agent."""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from models import call_claude_sonnet, call_claude_with_tools
from retrieval_agent_prompts import COVERAGE_ASSESSMENT_PROMPT
from edf_decomposer_prompts import EDF_COVERAGE_ASSESSMENT_PROMPT
from edf_decomposer import format_tree_items_for_scoring, compute_coverage_score
from vector_search_prompts import SAVED_CHAIN_RELEVANCE_PROMPT


# =============================================================================
# Tool Schemas (Anthropic tool_use format)
# =============================================================================

SEARCH_PINECONE_TOOL = {
    "name": "search_pinecone",
    "description": "Search the Pinecone vector database for institutional/Telegram research chunks (excludes web chains by default). Returns chunk summaries with source, score, and key content. Call multiple times with different queries for broader coverage.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query (semantic search). Use specific causal language for best results."
            },
            "top_k": {
                "type": "integer",
                "description": "Number of results to return (default: 8)",
                "default": 8
            },
            "exclude_web_chains": {
                "type": "boolean",
                "description": "If true (default), excludes previously persisted web chains and returns only institutional/Telegram research. Set to false to include all sources.",
                "default": True
            }
        },
        "required": ["query"]
    }
}

EXTRACT_WEB_CHAINS_TOOL = {
    "name": "extract_web_chains",
    "description": "Extract logic chains from trusted web sources using multi-angle search. Best for filling topic gaps where the vector database has insufficient coverage.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The research query to extract web chains for"
            },
            "angles": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional: specific search angles to use. If omitted, auto-generates angles."
            }
        },
        "required": ["query"]
    }
}

WEB_SEARCH_TOOL = {
    "name": "web_search",
    "description": "Search the web for factual information (dates, statistics, recent events). Best for filling specific factual gaps.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Specific factual search query"
            },
            "category": {
                "type": "string",
                "description": "Gap category being filled",
                "enum": ["historical_precedent_depth", "quantified_relationships", "monitoring_thresholds", "event_calendar", "mechanism_conditions", "exit_criteria", "general"]
            }
        },
        "required": ["query"]
    }
}

GENERATE_SYNTHESIS_TOOL = {
    "name": "generate_synthesis",
    "description": "Run the 3-stage chain extraction and synthesis pipeline on accumulated chunks. Call this after gathering sufficient material and before finishing.",
    "input_schema": {
        "type": "object",
        "properties": {
            "include_web_chains": {
                "type": "boolean",
                "description": "Whether to merge web chains into synthesis (default: true)",
                "default": True
            }
        },
    }
}

ASSESS_COVERAGE_TOOL = {
    "name": "assess_coverage",
    "description": "Assess whether gathered material is sufficient. Call periodically to check if you have enough for a quality insight report. Returns COMPLETE, ADEQUATE, or INSUFFICIENT with specific gap descriptions.",
    "input_schema": {
        "type": "object",
        "properties": {
            "notes": {
                "type": "string",
                "description": "Optional notes about what you've gathered so far"
            }
        },
    }
}

FINISH_RETRIEVAL_TOOL = {
    "name": "finish_retrieval",
    "description": "Signal that retrieval is complete. Call this after generating synthesis and confirming adequate coverage.",
    "input_schema": {
        "type": "object",
        "properties": {
            "coverage_rating": {
                "type": "string",
                "enum": ["COMPLETE", "ADEQUATE", "INSUFFICIENT"],
                "description": "Final coverage assessment"
            },
            "iterations_used": {
                "type": "integer",
                "description": "Number of search iterations performed"
            },
            "summary": {
                "type": "string",
                "description": "Brief summary of what was gathered"
            }
        },
        "required": ["coverage_rating", "summary"]
    }
}

ALL_TOOLS = [
    SEARCH_PINECONE_TOOL,
    EXTRACT_WEB_CHAINS_TOOL,
    WEB_SEARCH_TOOL,
    GENERATE_SYNTHESIS_TOOL,
    ASSESS_COVERAGE_TOOL,
    FINISH_RETRIEVAL_TOOL,
]


# =============================================================================
# Tool Handlers (stateful — bound to an AgentState instance)
# =============================================================================

class RetrievalAgentState:
    """Mutable state accumulated across agent iterations."""

    def __init__(self, query: str, image_path: str = None, knowledge_tree: dict = None):
        self.query = query
        self.image_path = image_path
        self.knowledge_tree = knowledge_tree  # EDF knowledge tree (Phase 0 output)
        self.chunks = []          # All retrieved chunks (deduplicated by id)
        self.chunk_ids = set()    # Track seen chunk IDs
        self.web_chains = []      # Extracted web chains
        self.web_search_results = []
        self.synthesis = ""
        self.answer = ""
        self.logic_chains = []
        self.confidence_metadata = {}
        self.topic_coverage = {}
        self.coverage_history = []  # List of coverage percentages from assess_coverage calls
        self.best_item_scores = {}  # {item_id: "Y"|"P"|"N"} — monotonic best per item
        self.calls_since_last_assessment = 0  # Tool calls since last assess_coverage
        self.stall_detected = False  # Set when coverage stall detected; short-circuits further searches

    def add_chunks(self, new_chunks: list):
        """Add chunks, deduplicating by ID."""
        for chunk in new_chunks:
            cid = chunk.get("id", "")
            if cid and cid not in self.chunk_ids:
                self.chunks.append(chunk)
                self.chunk_ids.add(cid)

    def get_chunk_summaries(self, max_chunks: int = 15) -> str:
        lines = []
        for i, chunk in enumerate(self.chunks[:max_chunks], 1):
            meta = chunk.get("metadata", {})
            lines.append(
                f"{i}. [{meta.get('source', 'Unknown')}] "
                f"(score={chunk.get('score', 0):.2f}) "
                f"{meta.get('what_happened', '')[:100]} | "
                f"{meta.get('interpretation', '')[:100]}"
            )
        return "\n".join(lines) if lines else "(none)"

    def get_web_chain_summaries(self) -> str:
        lines = []
        for i, wc in enumerate(self.web_chains[:10], 1):
            lines.append(
                f"{i}. {wc.get('cause', '?')} -> {wc.get('effect', '?')} "
                f"[{wc.get('source_name', 'web')}] "
                f"(confidence={wc.get('confidence', 'unknown')})"
            )
        return "\n".join(lines) if lines else "(none)"

    def get_sources(self) -> str:
        sources = set()
        for c in self.chunks:
            src = c.get("metadata", {}).get("source", "")
            if src:
                sources.add(src)
        for wc in self.web_chains:
            src = wc.get("source_name", "")
            if src:
                sources.add(src)
        return ", ".join(sorted(sources)[:10]) if sources else "(none)"

    def get_web_search_summaries(self) -> str:
        lines = []
        for i, ws in enumerate(self.web_search_results[:10], 1):
            info = ws.get("extracted_info", {}) or {}
            facts = info.get("extracted_facts", [])
            for f in facts[:3]:
                lines.append(f"  WS{i}: {f.get('fact', '?')} (source: {f.get('source', '?')})")
        return "\n".join(lines) if lines else "(none)"


def _filter_saved_chains_by_relevance(query: str, saved_chunks: list, saved_chains: list) -> list:
    """
    LLM-filter saved web chains for topical relevance to the query.

    Embeddings can't distinguish "Japan 2026 bond crash" from "US 1994 bond crash"
    because they share concept vocabulary. This uses a single Haiku call to judge
    whether each saved chunk is actually about the same topic as the query.

    Args:
        query: The search query
        saved_chunks: Pinecone chunks (with metadata containing what_happened etc.)
        saved_chains: Flat chain dicts produced by _convert_saved_chunks_to_web_chains

    Returns:
        Filtered list of chains (only those from relevant chunks)
    """
    if not saved_chunks:
        return saved_chains

    # Format chunks compactly for the LLM
    lines = []
    for i, chunk in enumerate(saved_chunks):
        meta = chunk.get("metadata", {})
        source = meta.get("source", "unknown")
        what = meta.get("what_happened", "")[:150]
        interp = meta.get("interpretation", "")[:100]
        lines.append(f"[{i}] ({source}) {what}")
        if interp:
            lines.append(f"    Interpretation: {interp}")
    chains_text = "\n".join(lines)

    # Tool schema for structured output
    relevance_tool = {
        "name": "judge_chain_relevance",
        "description": "Submit relevance judgments for each saved chain.",
        "input_schema": {
            "type": "object",
            "properties": {
                "judgments": {
                    "type": "array",
                    "description": "One judgment per chain",
                    "items": {
                        "type": "object",
                        "properties": {
                            "chain_index": {
                                "type": "integer",
                                "description": "Index of the chain (0-based)"
                            },
                            "relevant": {
                                "type": "boolean",
                                "description": "True if chain is about the same topic as the query"
                            }
                        },
                        "required": ["chain_index", "relevant"]
                    }
                }
            },
            "required": ["judgments"]
        }
    }

    user_prompt = SAVED_CHAIN_RELEVANCE_PROMPT.format(query=query, chains_text=chains_text)

    try:
        response = call_claude_with_tools(
            messages=[{"role": "user", "content": user_prompt}],
            tools=[relevance_tool],
            tool_choice={"type": "tool", "name": "judge_chain_relevance"},
            model="haiku",
            temperature=0.0,
            max_tokens=1000,
        )

        # Parse judgments
        relevant_chunk_indices = set()
        for content_block in response.content:
            if content_block.type == "tool_use" and content_block.name == "judge_chain_relevance":
                for j in content_block.input.get("judgments", []):
                    if j.get("relevant", False):
                        relevant_chunk_indices.add(j["chain_index"])

        print(f"[extract_web_chains] LLM relevance filter: {len(relevant_chunk_indices)}/{len(saved_chunks)} chunks judged relevant")

        if not relevant_chunk_indices:
            return []

        # Map chunk indices back to chains.
        # _convert_saved_chunks_to_web_chains produces chains in chunk order:
        # it iterates saved_chunks, and each chunk may produce 0-N chains.
        # Re-derive that mapping by replaying the same iteration.
        filtered_chains = []
        chain_cursor = 0
        for chunk_idx, chunk in enumerate(saved_chunks):
            metadata = chunk.get("metadata", {})
            extracted_data = metadata.get("extracted_data", "")
            chains_from_chunk = 0

            if isinstance(extracted_data, str) and extracted_data:
                try:
                    parsed = json.loads(extracted_data)
                    for lc in parsed.get("logic_chains", []):
                        chains_from_chunk += len(lc.get("steps", []))
                except (json.JSONDecodeError, TypeError):
                    pass

            # Fallback: top-level metadata fields
            if chains_from_chunk == 0:
                cause = metadata.get("cause", "")
                effect = metadata.get("effect", "")
                if cause and effect:
                    chains_from_chunk = 1

            # Keep chains from this chunk if it was judged relevant
            if chunk_idx in relevant_chunk_indices:
                filtered_chains.extend(saved_chains[chain_cursor:chain_cursor + chains_from_chunk])

            chain_cursor += chains_from_chunk

        return filtered_chains

    except Exception as e:
        print(f"[extract_web_chains] WARNING: LLM relevance filter failed ({e}), using all chains (safe fallback)")
        return saved_chains


def build_tool_handlers(agent_state: RetrievalAgentState) -> dict:
    """Build tool handler dict bound to agent state."""

    def handle_search_pinecone(query: str, top_k: int = 8, exclude_web_chains: bool = True) -> dict:
        short = _short_circuit_if_stalled("search_pinecone")
        if short:
            return short
        from vector_search import search_single_query, EXCLUDE_WEB_CHAINS_FILTER
        pinecone_filter = EXCLUDE_WEB_CHAINS_FILTER if exclude_web_chains else None
        chunks = search_single_query(query, top_k=top_k, threshold=0.50, filter=pinecone_filter)
        agent_state.add_chunks(chunks)

        summaries = []
        for c in chunks[:top_k]:
            meta = c.get("metadata", {})
            summaries.append({
                "id": c.get("id", ""),
                "score": round(c.get("score", 0), 3),
                "source": meta.get("source", "Unknown"),
                "what_happened": meta.get("what_happened", "")[:200],
                "interpretation": meta.get("interpretation", "")[:200],
            })

        result = {
            "chunks_returned": len(chunks),
            "total_chunks": len(agent_state.chunks),
            "results": summaries,
        }
        if len(chunks) == 0:
            result["note"] = "No relevant results found in database for this query. Try web_search or extract_web_chains instead."

        return _maybe_auto_assess(result)

    def handle_extract_web_chains(query: str, angles: list = None) -> dict:
        short = _short_circuit_if_stalled("extract_web_chains")
        if short:
            return short
        from vector_search import search_saved_web_chains
        from knowledge_gap_detector import fill_gaps_with_web_chains, _convert_saved_chunks_to_web_chains

        # Step 1: Check saved web chains in Pinecone first
        saved_chunks = search_saved_web_chains(query)
        saved_chains = _convert_saved_chunks_to_web_chains(saved_chunks) if saved_chunks else []

        if len(saved_chunks) >= 3 and saved_chains:
            # LLM-filter for topical relevance before deciding sufficiency
            relevant_chains = _filter_saved_chains_by_relevance(query, saved_chunks, saved_chains)

            if len(relevant_chains) >= 3:
                # Genuinely relevant — skip Tavily extraction
                agent_state.web_chains.extend(relevant_chains)
                print(f"[extract_web_chains] Using {len(relevant_chains)} relevant saved web chains from Pinecone (skipping Tavily)")

                chain_summaries = []
                for wc in relevant_chains[:10]:
                    chain_summaries.append({
                        "cause": wc.get("cause", ""),
                        "effect": wc.get("effect", ""),
                        "mechanism": wc.get("mechanism", "")[:150],
                        "source": wc.get("source_name", "web (saved)"),
                        "confidence": wc.get("confidence", "unknown"),
                    })

                return _maybe_auto_assess({
                    "chains_extracted": len(relevant_chains),
                    "total_web_chains": len(agent_state.web_chains),
                    "chains": chain_summaries,
                    "source": "saved_web_chains",
                })

            # Not enough relevant chains — fall through to Tavily
            # Keep any relevant ones for merging below
            saved_chains = relevant_chains
            print(f"[extract_web_chains] Only {len(relevant_chains)} relevant saved chains (need 3) — falling through to Tavily")

        # Step 2: Not enough saved chains — extract via Tavily
        # Build a synthetic gap for the web chain extraction function
        gaps = [{
            "category": "topic_not_covered",
            "status": "GAP",
            "missing": query,
            "fill_method": "web_chain_extraction",
        }]

        result = fill_gaps_with_web_chains(
            gaps=gaps,
            query=query,
            min_tier=2,
            min_trusted_sources=2,
            confidence_weight=0.7,
        )

        new_chains = result.get("extracted_chains", [])
        # Also include any saved chains found (even if < 3)
        all_chains = saved_chains + new_chains
        agent_state.web_chains.extend(all_chains)

        chain_summaries = []
        for wc in all_chains[:10]:
            chain_summaries.append({
                "cause": wc.get("cause", ""),
                "effect": wc.get("effect", ""),
                "mechanism": wc.get("mechanism", "")[:150],
                "source": wc.get("source_name", "web"),
                "confidence": wc.get("confidence", "unknown"),
            })

        return _maybe_auto_assess({
            "chains_extracted": len(all_chains),
            "total_web_chains": len(agent_state.web_chains),
            "chains": chain_summaries,
            "source": "tavily" + (f" (+{len(saved_chains)} saved)" if saved_chains else ""),
        })

    def handle_web_search(query: str, category: str = "general") -> dict:
        short = _short_circuit_if_stalled("web_search")
        if short:
            return short
        try:
            from knowledge_gap_detector import _get_web_search_adapter, _search_and_evaluate
            adapter = _get_web_search_adapter()
            if adapter is None:
                return {"error": "WebSearchAdapter not available"}
            result = _search_and_evaluate(adapter, query, category, query)
            agent_state.web_search_results.append(result)
            extracted_info = result.get("extracted_info", {}) or {}
            facts = extracted_info.get("extracted_facts", [])
            summary = extracted_info.get("summary", "")
            sources = result.get("sources", [])
            content = summary[:1000] if summary else "; ".join(f.get("fact", "") for f in facts[:3])
            return _maybe_auto_assess({
                "found": result.get("filled", False),
                "content": content,
                "source": sources[0] if sources else "",
            })
        except Exception as e:
            return {"error": str(e)}

    def handle_generate_synthesis(include_web_chains: bool = True) -> dict:
        from answer_generation import generate_answer
        from states import RetrieverState

        # Build a minimal state for generate_answer
        state = RetrieverState(
            query=agent_state.query,
            retrieved_chunks=agent_state.chunks,
            iteration_count=0,
            needs_refinement=False,
        )

        result_state = generate_answer(state)

        agent_state.answer = result_state.get("answer", "")
        agent_state.synthesis = result_state.get("synthesis", "")
        agent_state.confidence_metadata = result_state.get("confidence_metadata", {})
        agent_state.topic_coverage = result_state.get("topic_coverage", {})

        # Extract logic chains from answer
        from retrieval_orchestrator import _extract_logic_chains_from_chunks, _parse_logic_chains_from_answer
        db_chains = _extract_logic_chains_from_chunks(agent_state.chunks)
        answer_chains = _parse_logic_chains_from_answer(agent_state.answer)
        all_chains = db_chains + answer_chains

        # Merge web chains if requested
        if include_web_chains and agent_state.web_chains:
            from knowledge_gap_detector import merge_web_chains_with_db_chains
            merged = merge_web_chains_with_db_chains(all_chains, agent_state.web_chains)
            agent_state.logic_chains = merged
        else:
            agent_state.logic_chains = all_chains

        return {
            "synthesis_length": len(agent_state.synthesis),
            "chain_count": len(agent_state.logic_chains),
            "confidence": agent_state.confidence_metadata,
            "synthesis_preview": agent_state.synthesis[:500],
        }

    def _run_assessment() -> dict:
        """Run coverage assessment with stall detection."""
        if agent_state.knowledge_tree and agent_state.knowledge_tree.get("keywords"):
            result = _assess_coverage_edf(agent_state)
        else:
            result = _assess_coverage_generic(agent_state)

        # Stall detection: if 3+ assessments and no meaningful improvement, override to ADEQUATE
        history = agent_state.coverage_history
        if len(history) >= 5:
            delta = history[-1] - history[-2]
            if delta < 5.0 and result.get("rating") == "INSUFFICIENT":
                print(f"[Coverage] Stall detected: {history[-2]:.1f}% → {history[-1]:.1f}% "
                      f"(delta={delta:.1f}%). Overriding to ADEQUATE.")
                result["rating"] = "ADEQUATE"
                result["stall_detected"] = True

        agent_state.calls_since_last_assessment = 0
        return result

    def handle_assess_coverage(notes: str = "") -> dict:
        return _run_assessment()

    def _maybe_auto_assess(tool_result: dict) -> dict:
        """Auto-trigger coverage assessment after 3+ tool calls without one.
        If stall detected, directly run synthesis and short-circuit the agent."""
        agent_state.calls_since_last_assessment += 1
        if agent_state.calls_since_last_assessment >= 3 and agent_state.coverage_history:
            print(f"[Coverage] Auto-triggering assessment ({agent_state.calls_since_last_assessment} calls since last)")
            assessment = _run_assessment()
            if assessment.get("stall_detected"):
                # Directly generate synthesis — don't rely on agent to do it
                if not agent_state.synthesis:
                    print("[Coverage] Stall confirmed — generating synthesis directly")
                    handle_generate_synthesis()
                agent_state.stall_detected = True
                return {
                    "SYNTHESIS_COMPLETE": True,
                    "message": "Coverage stall detected. Synthesis has been generated. Call finish_retrieval now.",
                    "synthesis_length": len(agent_state.synthesis),
                }
            tool_result["auto_coverage_assessment"] = assessment
        return tool_result

    def _short_circuit_if_stalled(tool_name: str) -> dict | None:
        """Return a short-circuit result if stall was already detected."""
        if agent_state.stall_detected:
            return {
                "SKIPPED": f"{tool_name} skipped — coverage stall detected. Call generate_synthesis now.",
                "rating": "ADEQUATE",
            }
        return None

    def _assess_coverage_edf(state: RetrievalAgentState) -> dict:
        """Score gathered material against the EDF knowledge tree."""
        import re as re_mod

        tree_items_str = format_tree_items_for_scoring(state.knowledge_tree)

        prompt = EDF_COVERAGE_ASSESSMENT_PROMPT.format(
            query=state.query,
            tree_items=tree_items_str,
            chunk_count=len(state.chunks),
            chunk_summaries=state.get_chunk_summaries(),
            web_chain_count=len(state.web_chains),
            web_chain_summaries=state.get_web_chain_summaries(),
            web_search_count=len(state.web_search_results),
            web_search_summaries=state.get_web_search_summaries(),
        )

        response = call_claude_sonnet(
            [{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=2000,
        )

        # Parse JSON from response
        try:
            # Find the outermost JSON object
            first_brace = response.find('{')
            last_brace = response.rfind('}')
            if first_brace != -1 and last_brace > first_brace:
                result = json.loads(response[first_brace:last_brace + 1])
            else:
                result = {"rating": "INSUFFICIENT", "scores": {}, "essential_gaps": [], "suggested_queries": []}
        except (json.JSONDecodeError, ValueError):
            result = {"rating": "INSUFFICIENT", "scores": {}, "essential_gaps": [], "suggested_queries": []}

        # Monotonic score enforcement: never downgrade an item's best-seen score
        raw_scores = result.get("scores", {})
        score_rank = {"N": 0, "P": 1, "Y": 2}
        for item_id, new_score in raw_scores.items():
            prev = state.best_item_scores.get(item_id, "N")
            if score_rank.get(new_score, 0) > score_rank.get(prev, 0):
                state.best_item_scores[item_id] = new_score
            else:
                state.best_item_scores[item_id] = prev

        # Compute coverage from monotonic best scores (not raw Sonnet scores)
        coverage = compute_coverage_score(state.knowledge_tree, state.best_item_scores)

        # Track coverage percentage for stall detection
        state.coverage_history.append(coverage["percentage"])

        # Build item_id → source_hint lookup from the knowledge tree
        item_source_hints = {}
        for kw in state.knowledge_tree.get("keywords", []):
            for item in kw.get("items", []):
                item_source_hints[item.get("id", "")] = item.get("source_hint", "unknown")

        # Annotate essential_gaps with source_hint so the agent knows which tool to use
        essential_gaps = result.get("essential_gaps", coverage.get("essential_gaps", []))
        annotated_gaps = []
        for gap_id in essential_gaps:
            hint = item_source_hints.get(gap_id, "unknown")
            annotated_gaps.append({"id": gap_id, "source_hint": hint})

        # Log EDF coverage
        print(f"[Coverage EDF] {result.get('rating', 'UNKNOWN')} "
              f"({coverage['score']}/{coverage['max_score']} = {coverage['percentage']}%)")
        print(f"  Essential gaps: {[g['id'] + '(' + g['source_hint'] + ')' for g in annotated_gaps]}")
        if coverage.get("by_type"):
            for ktype, counts in coverage["by_type"].items():
                print(f"  {ktype}: {counts['covered']}Y + {counts['partial']}P + {counts['missing']}N / {counts['total']}")

        # Replace flat gap list with annotated version for the agent
        result["essential_gaps"] = annotated_gaps
        # Return result with both EDF scores and suggested queries for the agent
        result["coverage_metrics"] = coverage
        return result

    def _assess_coverage_generic(state: RetrievalAgentState) -> dict:
        """Original generic 6-flag coverage assessment (fallback when no EDF tree)."""
        import re as re_mod

        prompt = COVERAGE_ASSESSMENT_PROMPT.format(
            query=state.query,
            chunk_count=len(state.chunks),
            web_chain_count=len(state.web_chains),
            web_search_count=len(state.web_search_results),
            sources=state.get_sources(),
            chunk_summaries=state.get_chunk_summaries(),
            web_chain_summaries=state.get_web_chain_summaries(),
        )

        response = call_claude_sonnet(
            [{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=300,
        )

        # Parse JSON from response
        try:
            json_match = re_mod.search(r'\{[^{}]*\}', response, re_mod.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
            else:
                result = {"rating": "INSUFFICIENT", "has_causal_chains": False}
        except (json.JSONDecodeError, ValueError):
            result = {"rating": "INSUFFICIENT", "has_causal_chains": False}

        # Log checklist
        flags = ["has_causal_chains", "has_counter_argument", "has_monitoring_thresholds",
                 "has_event_calendar", "has_mechanism_conditions", "has_exit_criteria"]
        true_count = sum(1 for f in flags if result.get(f, False))

        # Track coverage percentage for stall detection
        state.coverage_history.append(true_count / len(flags) * 100)

        print(f"[Coverage] {result.get('rating', 'UNKNOWN')} ({true_count}/{len(flags)} flags)")
        for f in flags:
            status = "Y" if result.get(f, False) else "N"
            print(f"  [{status}] {f}")
        return result

    def handle_finish_retrieval(coverage_rating: str = "ADEQUATE", summary: str = "", iterations_used: int = 0) -> dict:
        return {"status": "completed", "coverage_rating": coverage_rating, "summary": summary}

    return {
        "search_pinecone": handle_search_pinecone,
        "extract_web_chains": handle_extract_web_chains,
        "web_search": handle_web_search,
        "generate_synthesis": handle_generate_synthesis,
        "assess_coverage": handle_assess_coverage,
        "finish_retrieval": handle_finish_retrieval,
    }
