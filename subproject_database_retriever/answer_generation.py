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
from config import MAX_CHUNKS_FOR_ANSWER


def generate_answer(state: RetrieverState) -> RetrieverState:
    """
    Generate logic chain answer from retrieved chunks (two-stage).

    Stage 1: Extract and organize logic chains
    Stage 2: Synthesize consensus and extract variables

    Input: query, retrieved_chunks, query_temporal_reference
    Output: synthesized_context, answer, synthesis, data_temporal_summary
    """
    query = state.get("query", "")
    chunks = state.get("retrieved_chunks", [])
    query_temporal_ref = state.get("query_temporal_reference", {})

    # Limit chunks to preserve LLM reasoning quality
    chunks = chunks[:MAX_CHUNKS_FOR_ANSWER]

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

    # Stage 3: Identify contradicting evidence (runs on EVERY query per user decision)
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
        "data_temporal_summary": data_temporal_summary
    }


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
