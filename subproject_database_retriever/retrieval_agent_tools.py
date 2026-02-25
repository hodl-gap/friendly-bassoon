"""Tool schemas and handlers for the retrieval agent."""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from models import call_claude_sonnet
from retrieval_agent_prompts import COVERAGE_ASSESSMENT_PROMPT


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

    def __init__(self, query: str, image_path: str = None):
        self.query = query
        self.image_path = image_path
        self.chunks = []          # All retrieved chunks (deduplicated by id)
        self.chunk_ids = set()    # Track seen chunk IDs
        self.web_chains = []      # Extracted web chains
        self.web_search_results = []
        self.synthesis = ""
        self.answer = ""
        self.logic_chains = []
        self.confidence_metadata = {}
        self.topic_coverage = {}

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


def build_tool_handlers(agent_state: RetrievalAgentState) -> dict:
    """Build tool handler dict bound to agent state."""

    def handle_search_pinecone(query: str, top_k: int = 8, exclude_web_chains: bool = True) -> dict:
        from vector_search import search_single_query, EXCLUDE_WEB_CHAINS_FILTER
        pinecone_filter = EXCLUDE_WEB_CHAINS_FILTER if exclude_web_chains else None
        chunks = search_single_query(query, top_k=top_k, filter=pinecone_filter)
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

        return {
            "chunks_returned": len(chunks),
            "total_chunks": len(agent_state.chunks),
            "results": summaries,
        }

    def handle_extract_web_chains(query: str, angles: list = None) -> dict:
        from vector_search import search_saved_web_chains
        from knowledge_gap_detector import fill_gaps_with_web_chains, _convert_saved_chunks_to_web_chains

        # Step 1: Check saved web chains in Pinecone first
        saved_chunks = search_saved_web_chains(query)
        saved_chains = _convert_saved_chunks_to_web_chains(saved_chunks) if saved_chunks else []

        if len(saved_chunks) >= 3 and saved_chains:
            # Sufficient saved chains — skip Tavily extraction
            agent_state.web_chains.extend(saved_chains)
            print(f"[extract_web_chains] Using {len(saved_chains)} saved web chains from Pinecone (skipping Tavily)")

            chain_summaries = []
            for wc in saved_chains[:10]:
                chain_summaries.append({
                    "cause": wc.get("cause", ""),
                    "effect": wc.get("effect", ""),
                    "mechanism": wc.get("mechanism", "")[:150],
                    "source": wc.get("source_name", "web (saved)"),
                    "confidence": wc.get("confidence", "unknown"),
                })

            return {
                "chains_extracted": len(saved_chains),
                "total_web_chains": len(agent_state.web_chains),
                "chains": chain_summaries,
                "source": "saved_web_chains",
            }

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

        return {
            "chains_extracted": len(all_chains),
            "total_web_chains": len(agent_state.web_chains),
            "chains": chain_summaries,
            "source": "tavily" + (f" (+{len(saved_chains)} saved)" if saved_chains else ""),
        }

    def handle_web_search(query: str, category: str = "general") -> dict:
        try:
            from knowledge_gap_detector import _get_web_search_adapter, _search_and_evaluate
            adapter = _get_web_search_adapter()
            if adapter is None:
                return {"error": "WebSearchAdapter not available"}
            result = _search_and_evaluate(adapter, query, category, query)
            agent_state.web_search_results.append(result)
            return {
                "found": result.get("found", False),
                "content": result.get("content", "")[:1000],
                "source": result.get("source", ""),
            }
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

    def handle_assess_coverage(notes: str = "") -> dict:
        prompt = COVERAGE_ASSESSMENT_PROMPT.format(
            query=agent_state.query,
            chunk_count=len(agent_state.chunks),
            web_chain_count=len(agent_state.web_chains),
            web_search_count=len(agent_state.web_search_results),
            sources=agent_state.get_sources(),
            chunk_summaries=agent_state.get_chunk_summaries(),
            web_chain_summaries=agent_state.get_web_chain_summaries(),
        )

        response = call_claude_sonnet(
            [{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=300,
        )

        # Parse JSON from response
        try:
            import re
            json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
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
