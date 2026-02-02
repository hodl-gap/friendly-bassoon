"""
Answer Generation Module

Extracts logic chains from retrieved context and generates connected chain answers.
"""

import sys
import re
import json
from pathlib import Path

# Add parent directory for models import
sys.path.append(str(Path(__file__).parent.parent))

from models import call_claude_sonnet, call_claude_haiku
from states import RetrieverState
from answer_generation_prompts import LOGIC_CHAIN_PROMPT, SYNTHESIS_PROMPT, CONTRADICTION_PROMPT
from config import (
    MAX_CHUNKS_FOR_ANSWER,
    SKIP_CONTRADICTION_FOR_DATA_LOOKUP,
    SKIP_CONTRADICTION_CONFIDENCE_THRESHOLD,
    ENABLE_CHAIN_EXPANSION,
    MIN_CHUNKS_BEFORE_EXPANSION,
    MAX_DANGLING_TO_FOLLOW,
    USE_STRUCTURED_SYNTHESIS
)


def generate_answer(state: RetrieverState) -> RetrieverState:
    """
    Generate logic chain answer from retrieved chunks (two-stage + conditional Stage 3).

    Stage 1: Extract and organize logic chains
    Stage 2: Synthesize consensus and extract variables
    Stage 3: Identify contradicting evidence (conditional - skipped for data_lookup or high confidence)

    Input: query, retrieved_chunks, query_temporal_reference, query_type
    Output: synthesized_context, answer, synthesis, data_temporal_summary
    """
    query = state.get("query", "")
    chunks = state.get("retrieved_chunks", [])
    query_temporal_ref = state.get("query_temporal_reference", {})
    query_type = state.get("query_type", "research_question")

    # Limit chunks to preserve LLM reasoning quality
    chunks = chunks[:MAX_CHUNKS_FOR_ANSWER]

    # Chain expansion: detect and follow dangling effects
    dangling_followed = []
    if ENABLE_CHAIN_EXPANSION and len(chunks) >= MIN_CHUNKS_BEFORE_EXPANSION:
        print(f"[answer_generation] Detecting dangling chains...")
        dangling = detect_dangling_chains(chunks)

        if dangling:
            print(f"[answer_generation] Found {len(dangling)} dangling effects: {dangling[:5]}...")
            additional_chunks, dangling_followed = expand_dangling_chains(
                dangling,
                chunks,
                max_to_follow=MAX_DANGLING_TO_FOLLOW
            )

            if additional_chunks:
                chunks = chunks + additional_chunks
                # Allow slightly more chunks for follow-ups
                chunks = chunks[:MAX_CHUNKS_FOR_ANSWER + 5]
                print(f"[answer_generation] Expanded to {len(chunks)} total chunks")
        else:
            print(f"[answer_generation] No dangling chains detected")
    else:
        if not ENABLE_CHAIN_EXPANSION:
            print(f"[answer_generation] Chain expansion disabled")
        else:
            print(f"[answer_generation] Too few chunks ({len(chunks)}) for chain expansion")

    print(f"[answer_generation] Stage 1: Extracting logic chains from {len(chunks)} chunks...")

    # Summarize temporal context from data
    data_temporal_summary = summarize_data_temporal_context(chunks)
    print(f"[answer_generation] Data temporal summary: {data_temporal_summary}")

    # Check for temporal mismatch
    query_year = query_temporal_ref.get("reference_year") if query_temporal_ref else None
    if query_year and data_temporal_summary['data_years']:
        if str(query_year) not in set(data_temporal_summary['data_years']):
            print(f"[answer_generation] TEMPORAL MISMATCH: Query asks about {query_year}, data is from {data_temporal_summary['data_years']}")
            print(f"[answer_generation] LLM will focus on logic chains over absolute values")

    # Synthesize context with full extracted_data and temporal reference
    context = synthesize_context(chunks, query_temporal_ref)

    # Stage 1: Generate logic chains
    answer = generate_logic_chains(query, context)

    print(f"[answer_generation] Stage 1 complete: {answer[:200]}...")

    # Stage 2: Synthesize consensus and variables
    print(f"[answer_generation] Stage 2: Synthesizing consensus and variables...")
    synthesis_result = synthesize_chains(query, answer)

    synthesis_text = synthesis_result["synthesis_text"]
    confidence_metadata = synthesis_result["confidence_metadata"]

    print(f"[answer_generation] Stage 2 complete: {synthesis_text[:200]}...")

    # Stage 3: Identify contradicting evidence (CONDITIONAL)
    # Skip if: (1) data_lookup query, or (2) high confidence score
    should_skip_contradictions = should_skip_contradiction_detection(
        query_type, confidence_metadata
    )

    if should_skip_contradictions:
        skip_reason = get_contradiction_skip_reason(query_type, confidence_metadata)
        print(f"[answer_generation] Stage 3: SKIPPED - {skip_reason}")
        contradictions = f"Skipped: {skip_reason}"
    else:
        print(f"[answer_generation] Stage 3: Identifying contradicting evidence...")
        contradictions = identify_contradictions(query, synthesis_text, context)
        print(f"[answer_generation] Stage 3 complete: {contradictions[:200]}...")

    return {
        **state,
        "synthesized_context": context,
        "answer": answer,
        "synthesis": synthesis_text,
        "confidence_metadata": confidence_metadata,
        "contradictions": contradictions,
        "data_temporal_summary": data_temporal_summary,
        "dangling_effects_followed": dangling_followed
    }


def should_skip_contradiction_detection(query_type: str, confidence_metadata: dict) -> bool:
    """
    Determine if Stage 3 (contradiction detection) should be skipped.

    Skip conditions:
    1. Query type is 'data_lookup' (simple factual queries don't need contradiction analysis)
    2. Confidence score is above threshold (high confidence = low value from contradiction check)

    Returns True if Stage 3 should be skipped.
    """
    # Condition 1: Skip for data_lookup queries
    if SKIP_CONTRADICTION_FOR_DATA_LOOKUP and query_type == "data_lookup":
        return True

    # Condition 2: Skip for high confidence scores
    confidence_score = confidence_metadata.get("overall_score", 0.0)
    if confidence_score >= SKIP_CONTRADICTION_CONFIDENCE_THRESHOLD:
        return True

    return False


def get_contradiction_skip_reason(query_type: str, confidence_metadata: dict) -> str:
    """Get human-readable reason for skipping contradiction detection."""
    if SKIP_CONTRADICTION_FOR_DATA_LOOKUP and query_type == "data_lookup":
        return "data_lookup query (simple factual lookup)"

    confidence_score = confidence_metadata.get("overall_score", 0.0)
    if confidence_score >= SKIP_CONTRADICTION_CONFIDENCE_THRESHOLD:
        return f"high confidence synthesis ({confidence_score:.2f} >= {SKIP_CONTRADICTION_CONFIDENCE_THRESHOLD})"

    return "unknown"


def parse_extracted_data(chunk: dict) -> dict:
    """Parse extracted_data JSON from chunk metadata."""
    metadata = chunk.get("metadata", {})
    extracted_data = metadata.get("extracted_data", "{}")
    if isinstance(extracted_data, str):
        try:
            return json.loads(extracted_data)
        except json.JSONDecodeError:
            return {}
    return extracted_data


def extract_chunk_temporal_context(chunk: dict) -> dict:
    """
    Extract temporal_context from a chunk's extracted_data.

    Returns dict with:
        - policy_regime: QE/QT/hold/transition or None
        - liquidity_regime: reserve_scarce/reserve_abundant/transitional or None
        - valid_from: YYYY-MM or None
        - valid_until: YYYY-MM or None
        - is_forward_looking: bool
    """
    extracted_data = parse_extracted_data(chunk)
    temporal = extracted_data.get("temporal_context", {})

    return {
        "policy_regime": temporal.get("policy_regime"),
        "liquidity_regime": temporal.get("liquidity_regime"),
        "valid_from": temporal.get("valid_from"),
        "valid_until": temporal.get("valid_until"),
        "is_forward_looking": temporal.get("is_forward_looking", False)
    }


def summarize_data_temporal_context(chunks: list) -> dict:
    """
    Summarize temporal context across all retrieved chunks.

    Returns:
        - data_years: Set of years referenced in the data
        - forward_looking_count: Number of chunks with forward-looking forecasts
        - time_bound_count: Number of chunks with specific valid_from/until
        - structural_count: Number of chunks without time bounds (timeless patterns)
        - earliest_valid_from: Earliest valid_from date
        - latest_valid_until: Latest valid_until date
    """
    data_years = set()
    forward_looking_count = 0
    time_bound_count = 0
    structural_count = 0
    valid_froms = []
    valid_untils = []

    for chunk in chunks:
        temporal = extract_chunk_temporal_context(chunk)

        if temporal.get("is_forward_looking"):
            forward_looking_count += 1

        valid_from = temporal.get("valid_from")
        valid_until = temporal.get("valid_until")

        if valid_from:
            valid_froms.append(valid_from)
            # Extract year
            if len(valid_from) >= 4:
                data_years.add(valid_from[:4])

        if valid_until:
            valid_untils.append(valid_until)
            if len(valid_until) >= 4:
                data_years.add(valid_until[:4])

        # Classify as time-bound or structural
        if valid_from or valid_until or temporal.get("is_forward_looking"):
            time_bound_count += 1
        else:
            structural_count += 1

    return {
        "data_years": sorted(list(data_years)),
        "forward_looking_count": forward_looking_count,
        "time_bound_count": time_bound_count,
        "structural_count": structural_count,
        "earliest_valid_from": min(valid_froms) if valid_froms else None,
        "latest_valid_until": max(valid_untils) if valid_untils else None,
        "total_chunks": len(chunks)
    }


def find_chain_connections(chunks: list) -> dict:
    """
    Build a map of normalized effects to their source chunks.
    Enables explicit chain connection during synthesis.

    Returns: {effect_normalized: [chunk_ids that have this as effect]}
    """
    effect_map = {}

    for chunk in chunks:
        chunk_id = chunk.get("id", "unknown")
        extracted_data = parse_extracted_data(chunk)
        logic_chains = extracted_data.get("logic_chains", [])

        for chain in logic_chains:
            for step in chain.get("steps", []):
                effect_norm = step.get("effect_normalized", "")
                if effect_norm:
                    if effect_norm not in effect_map:
                        effect_map[effect_norm] = []
                    if chunk_id not in effect_map[effect_norm]:
                        effect_map[effect_norm].append(chunk_id)

    return effect_map


def detect_dangling_chains(chunks: list) -> list:
    """
    Find effects that aren't explained in retrieved chunks.
    Returns effects sorted by frequency (most common first).

    A chain is "dangling" if:
    - An effect_normalized appears in retrieved chunks
    - But NO chunk has that effect as a cause_normalized

    This enables chain-of-retrievals: follow up on unexplained effects
    to get complete causal chains.
    """
    effect_counts = {}  # Track frequency of each effect
    causes = set()      # Track all causes

    for chunk in chunks:
        extracted_data = parse_extracted_data(chunk)
        for chain in extracted_data.get("logic_chains", []):
            for step in chain.get("steps", []):
                effect_norm = step.get("effect_normalized", "")
                cause_norm = step.get("cause_normalized", "")
                if effect_norm:
                    effect_counts[effect_norm] = effect_counts.get(effect_norm, 0) + 1
                if cause_norm:
                    causes.add(cause_norm)

    # Dangling = effects that don't appear as causes anywhere
    dangling = {e: count for e, count in effect_counts.items() if e not in causes}

    # Sort by frequency (descending) - prioritize most common effects
    sorted_dangling = sorted(dangling.keys(), key=lambda e: dangling[e], reverse=True)
    return sorted_dangling


def expand_dangling_chains(
    dangling_effects: list,
    original_chunks: list,
    max_to_follow: int = 3
) -> tuple:
    """
    Run follow-up queries for dangling effects (already sorted by frequency).

    Uses metadata-first search: queries by exact cause_normalized metadata match
    first, then falls back to semantic search if insufficient matches.

    Args:
        dangling_effects: List of effect names to follow up on (sorted by frequency)
        original_chunks: Original retrieved chunks (for deduplication)
        max_to_follow: Maximum number of effects to follow up on

    Returns: (additional_chunks, effects_followed)
    """
    from vector_search import search_for_chain_continuation

    additional_chunks = []
    effects_followed = []
    seen_ids = {c["id"] for c in original_chunks}

    # Take top N by frequency (already sorted)
    effects_to_follow = dangling_effects[:max_to_follow]

    for effect in effects_to_follow:
        print(f"[chain_expansion] Following dangling effect '{effect}'")

        # Use metadata-first search (deterministic match before semantic fallback)
        new_chunks = search_for_chain_continuation(effect)

        chunks_added = 0
        metadata_count = 0
        semantic_count = 0

        for chunk in new_chunks:
            if chunk["id"] not in seen_ids:
                chunk["is_followup"] = True
                chunk["followed_effect"] = effect
                additional_chunks.append(chunk)
                seen_ids.add(chunk["id"])
                chunks_added += 1

                # Track match types for logging
                if chunk.get("match_type") == "metadata":
                    metadata_count += 1
                else:
                    semantic_count += 1

        if chunks_added > 0:
            effects_followed.append(effect)
            print(f"[chain_expansion] Added {chunks_added} chunks for '{effect}' ({metadata_count} metadata, {semantic_count} semantic)")

    print(f"[chain_expansion] Total: {len(additional_chunks)} new chunks from {len(effects_followed)} follow-ups")
    return additional_chunks, effects_followed


def synthesize_context(chunks: list, query_temporal_ref: dict = None) -> str:
    """
    Format chunks with full context for logic chain extraction.

    Args:
        chunks: Retrieved chunks with metadata
        query_temporal_ref: Query temporal reference from query_processing
    """
    if not chunks:
        return "No relevant context found."

    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        metadata = chunk.get("metadata", {})
        score = chunk.get("score", 0)
        chunk_id = chunk.get("id", f"chunk_{i}")

        extracted_data = parse_extracted_data(chunk)

        # Extract fields
        source = extracted_data.get("source", metadata.get("tg_channel", "unknown"))
        what_happened = extracted_data.get("what_happened", "")
        interpretation = extracted_data.get("interpretation", "")
        used_data = extracted_data.get("used_data", "")
        logic_chains = extracted_data.get("logic_chains", [])

        # Extract temporal context for this chunk
        temporal = extract_chunk_temporal_context(chunk)

        # Format chunk context
        part = f"[Source {i}: {source}] (id: {chunk_id}, score: {score:.2f})\n"
        if what_happened:
            part += f"What happened: {what_happened}\n"
        if interpretation:
            part += f"Interpretation: {interpretation}\n"
        if used_data:
            part += f"Data: {used_data}\n"

        # Add temporal context if available
        temporal_parts = []
        if temporal.get("valid_from") or temporal.get("valid_until"):
            valid_range = f"{temporal.get('valid_from', '?')} to {temporal.get('valid_until', 'ongoing')}"
            temporal_parts.append(f"valid: {valid_range}")
        if temporal.get("is_forward_looking"):
            temporal_parts.append("forward-looking forecast")
        if temporal.get("policy_regime"):
            temporal_parts.append(f"regime: {temporal['policy_regime']}")
        if temporal_parts:
            part += f"Temporal context: {', '.join(temporal_parts)}\n"

        # Format logic chains (FIXED: properly iterate over steps array)
        if logic_chains:
            part += "Logic chains:\n"
            for chain in logic_chains:
                steps = chain.get("steps", [])
                for step in steps:
                    cause = step.get("cause", "")
                    cause_norm = step.get("cause_normalized", "")
                    effect = step.get("effect", "")
                    effect_norm = step.get("effect_normalized", "")
                    mechanism = step.get("mechanism", "")
                    # Format with normalized names for cross-chunk linking
                    if cause_norm or effect_norm:
                        part += f"  - {cause} [{cause_norm}] → {effect} [{effect_norm}]: {mechanism}\n"
                    else:
                        part += f"  - {cause} → {effect}: {mechanism}\n"

        context_parts.append(part)

    # Build chain connections section
    effect_map = find_chain_connections(chunks)

    # Find potential cross-chunk connections
    connections = []
    seen_connections = set()
    for chunk in chunks:
        extracted_data = parse_extracted_data(chunk)
        for chain in extracted_data.get("logic_chains", []):
            for step in chain.get("steps", []):
                cause_norm = step.get("cause_normalized", "")
                if cause_norm and cause_norm in effect_map:
                    # This cause matches another chunk's effect - potential connection
                    conn_key = f"{cause_norm}"
                    if conn_key not in seen_connections:
                        connections.append(f"- {cause_norm}: appears as effect in {effect_map[cause_norm]}")
                        seen_connections.add(conn_key)

    context = "\n---\n".join(context_parts)

    if connections:
        context += "\n\n## CHAIN CONNECTIONS (use these for multi-hop reasoning):\n"
        context += "\n".join(connections)

    # Add temporal guidance section
    data_temporal = summarize_data_temporal_context(chunks)
    query_year = query_temporal_ref.get("reference_year") if query_temporal_ref else None

    temporal_guidance = []
    temporal_guidance.append(f"\n\n## TEMPORAL GUIDANCE")
    temporal_guidance.append(f"Data context: {data_temporal['total_chunks']} chunks")

    if data_temporal['data_years']:
        temporal_guidance.append(f"Data years: {', '.join(data_temporal['data_years'])}")

    if data_temporal['forward_looking_count'] > 0:
        temporal_guidance.append(f"Forward-looking forecasts: {data_temporal['forward_looking_count']} chunks")

    if data_temporal['structural_count'] > 0:
        temporal_guidance.append(f"Structural/timeless patterns: {data_temporal['structural_count']} chunks")

    if query_year and data_temporal['data_years']:
        data_year_set = set(data_temporal['data_years'])
        if str(query_year) not in data_year_set:
            temporal_guidance.append(f"\n**TEMPORAL MISMATCH**: Query references {query_year}, but data is from {', '.join(data_temporal['data_years'])}")
            temporal_guidance.append("- Focus on LOGIC CHAINS (cause → effect relationships) which remain applicable")
            temporal_guidance.append("- Treat specific numbers/values as historical examples, not current facts")
            temporal_guidance.append("- Structural patterns like 'QE → liquidity expansion' are timeless")
            temporal_guidance.append("- Absolute values like '$1.26T' or '83.4%' are time-bound to their data period")

    context += "\n".join(temporal_guidance)

    return context


def generate_logic_chains(query: str, context: str) -> str:
    """Generate connected logic chains using LLM."""
    if context == "No relevant context found.":
        return "I couldn't find relevant logic chains to answer this question."

    prompt = LOGIC_CHAIN_PROMPT.format(query=query, context=context)
    messages = [{"role": "user", "content": prompt}]

    response = call_claude_sonnet(messages, temperature=0.3, max_tokens=4000)

    print(f"[answer_generation] Full LLM response:\n{response}")

    return response


def synthesize_chains(query: str, chains: str) -> dict:
    """
    Stage 2: Synthesize consensus and extract variables.

    Returns dict with:
        - synthesis_text: The full synthesis response
        - confidence_metadata: Extracted confidence scores
    """
    if not chains or "couldn't find" in chains.lower():
        return {
            "synthesis_text": "No chains to synthesize.",
            "confidence_metadata": {"overall_score": 0.0, "path_count": 0, "source_diversity": 0}
        }

    # Use structured output if enabled (replaces fragile regex parsing)
    if USE_STRUCTURED_SYNTHESIS:
        return synthesize_chains_structured(query, chains)

    # Legacy: Free-form synthesis with regex extraction
    prompt = SYNTHESIS_PROMPT.format(query=query, chains=chains)
    messages = [{"role": "user", "content": prompt}]

    response = call_claude_sonnet(messages, temperature=0.3, max_tokens=3000)

    print(f"[answer_generation] Synthesis response:\n{response}")

    # Extract confidence metadata from response
    confidence_metadata = extract_confidence_metadata(response)

    return {
        "synthesis_text": response,
        "confidence_metadata": confidence_metadata
    }


def synthesize_chains_structured(query: str, chains: str) -> dict:
    """
    Stage 2: Synthesize consensus using tool_use for guaranteed structured output.

    Uses Claude's tool_use feature to ensure confidence metadata is returned
    as valid JSON, replacing fragile regex parsing.

    Returns dict with:
        - synthesis_text: The full synthesis response
        - confidence_metadata: Extracted confidence scores (guaranteed JSON)
    """
    import os
    from anthropic import Anthropic
    from dotenv import load_dotenv

    # Load API key
    env_path = Path(__file__).parent.parent / '.env'
    load_dotenv(env_path)
    client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    # Define tool schema for structured output
    synthesis_tool = {
        "name": "submit_synthesis",
        "description": "Submit the synthesis of logic chains with confidence metadata.",
        "input_schema": {
            "type": "object",
            "properties": {
                "synthesis_text": {
                    "type": "string",
                    "description": "The full synthesis text including consensus conclusions and key variables to monitor"
                },
                "overall_score": {
                    "type": "number",
                    "description": "Confidence score from 0.0 to 1.0. High (0.8+): 3+ paths from 2+ sources. Medium (0.5-0.8): 2 paths OR single source. Low (<0.5): Single path or weak support."
                },
                "path_count": {
                    "type": "integer",
                    "description": "Number of supporting paths/chains that converge on the main conclusion"
                },
                "source_diversity": {
                    "type": "integer",
                    "description": "Number of unique institutions/sources supporting the conclusion"
                },
                "confidence_level": {
                    "type": "string",
                    "enum": ["High", "Medium", "Low"],
                    "description": "Categorical confidence level based on path count and source diversity"
                },
                "strongest_chain": {
                    "type": "string",
                    "description": "The most well-supported logic chain, formatted as 'A → B → C'"
                }
            },
            "required": ["synthesis_text", "overall_score", "path_count", "source_diversity", "confidence_level"]
        }
    }

    user_prompt = f"""You are synthesizing logic chains to identify consensus patterns and key monitoring variables.

Query: {query}

Logic Chains:
{chains}

Instructions:

## Part 1: Consensus Chains
Identify where MULTIPLE chains converge on the same conclusion through different paths.
- Look for different starting points that lead to the same end effect
- These represent higher-conviction conclusions supported by multiple reasoning paths
- Only include if 2+ chains support the same conclusion

## Part 2: Key Variables to Monitor
Extract specific, actionable variables/indicators mentioned across the chains.
- Group by category (e.g., Liquidity, Labor Market, Positioning)
- Include specific thresholds or levels if mentioned
- Note which chains reference each variable

## Confidence Scoring
Score the overall confidence based on:
- High (0.8+): 3+ paths from 2+ independent sources
- Medium (0.5-0.8): 2 paths OR single source with strong logic
- Low (<0.5): Single path, weak support, or contradictory evidence

Use the submit_synthesis tool to submit your analysis with confidence metadata."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            temperature=0.3,
            tools=[synthesis_tool],
            tool_choice={"type": "tool", "name": "submit_synthesis"},
            messages=[{"role": "user", "content": user_prompt}]
        )

        # Extract tool use result
        for content_block in response.content:
            if content_block.type == "tool_use" and content_block.name == "submit_synthesis":
                tool_input = content_block.input

                synthesis_text = tool_input.get("synthesis_text", "")
                confidence_metadata = {
                    "overall_score": float(tool_input.get("overall_score", 0.0)),
                    "path_count": int(tool_input.get("path_count", 0)),
                    "source_diversity": int(tool_input.get("source_diversity", 0)),
                    "confidence_level": tool_input.get("confidence_level", "Low"),
                    "strongest_chain": tool_input.get("strongest_chain", "")
                }

                print(f"[answer_generation] Structured synthesis complete:")
                print(f"[answer_generation] Confidence: {confidence_metadata}")
                print(f"[answer_generation] Synthesis text (first 300 chars): {synthesis_text[:300]}...")

                return {
                    "synthesis_text": synthesis_text,
                    "confidence_metadata": confidence_metadata
                }

        # Fallback if no tool_use found
        print("[answer_generation] WARNING: No tool_use in response, falling back to regex")
        return _fallback_synthesis(query, chains)

    except Exception as e:
        print(f"[answer_generation] Structured synthesis error: {e}, falling back to regex")
        return _fallback_synthesis(query, chains)


def _fallback_synthesis(query: str, chains: str) -> dict:
    """Fallback to regex-based extraction when structured output fails."""
    prompt = SYNTHESIS_PROMPT.format(query=query, chains=chains)
    messages = [{"role": "user", "content": prompt}]

    response = call_claude_sonnet(messages, temperature=0.3, max_tokens=3000)

    print(f"[answer_generation] Fallback synthesis response:\n{response}")

    confidence_metadata = extract_confidence_metadata(response)

    return {
        "synthesis_text": response,
        "confidence_metadata": confidence_metadata
    }


def extract_confidence_metadata(synthesis_response: str) -> dict:
    """
    Extract confidence metrics from synthesis response.

    Looks for patterns like:
    - **CONFIDENCE_SCORE:** 0.75
    - **PATH_COUNT:** 3
    - **SOURCE_DIVERSITY:** 2
    """
    metadata = {
        "overall_score": 0.0,
        "path_count": 0,
        "source_diversity": 0,
        "confidence_level": "Low"
    }

    # Extract CONFIDENCE_SCORE (0.0-1.0)
    score_match = re.search(r'\*\*CONFIDENCE_SCORE:\*\*\s*([0-9.]+)', synthesis_response)
    if score_match:
        try:
            metadata["overall_score"] = float(score_match.group(1))
        except ValueError:
            pass

    # Extract PATH_COUNT
    path_match = re.search(r'\*\*PATH_COUNT:\*\*\s*(\d+)', synthesis_response)
    if path_match:
        try:
            metadata["path_count"] = int(path_match.group(1))
        except ValueError:
            pass

    # Extract SOURCE_DIVERSITY
    source_match = re.search(r'\*\*SOURCE_DIVERSITY:\*\*\s*(\d+)', synthesis_response)
    if source_match:
        try:
            metadata["source_diversity"] = int(source_match.group(1))
        except ValueError:
            pass

    # Extract CONFIDENCE level (High/Medium/Low)
    conf_match = re.search(r'\*\*CONFIDENCE:\*\*\s*\[?(High|Medium|Low)\]?', synthesis_response, re.IGNORECASE)
    if conf_match:
        metadata["confidence_level"] = conf_match.group(1).capitalize()

    print(f"[answer_generation] Extracted confidence metadata: {metadata}")

    return metadata


def identify_contradictions(query: str, synthesis: str, context: str) -> str:
    """
    Stage 3: Find contradicting evidence (Issue 5: Negative Evidence Handling).

    Runs on EVERY query per user decision.

    Args:
        query: Original user query
        synthesis: The consensus synthesis from Stage 2
        context: The synthesized context from retrieved chunks

    Returns:
        Contradiction analysis text
    """
    if not synthesis or "No chains to synthesize" in synthesis:
        return "No synthesis available to check for contradictions."

    prompt = CONTRADICTION_PROMPT.format(
        query=query,
        synthesis=synthesis,
        context=context
    )
    messages = [{"role": "user", "content": prompt}]

    # Use Haiku for efficiency since this runs on every query
    response = call_claude_haiku(messages, temperature=0.3, max_tokens=2000)

    print(f"[answer_generation] Contradiction analysis:\n{response}")

    return response
