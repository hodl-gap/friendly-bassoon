"""
Answer Generation Module

Extracts logic chains from retrieved context and generates connected chain answers.
"""

import sys
import json
from pathlib import Path

# Add parent directory for models import
sys.path.append(str(Path(__file__).parent.parent))

from models import call_claude_sonnet
from states import RetrieverState
from answer_generation_prompts import LOGIC_CHAIN_PROMPT
from config import MAX_CHUNKS_FOR_ANSWER


def generate_answer(state: RetrieverState) -> RetrieverState:
    """
    Generate logic chain answer from retrieved chunks.

    Input: query, retrieved_chunks
    Output: synthesized_context, answer
    """
    query = state.get("query", "")
    chunks = state.get("retrieved_chunks", [])

    # Limit chunks to preserve LLM reasoning quality
    chunks = chunks[:MAX_CHUNKS_FOR_ANSWER]

    print(f"[answer_generation] Extracting logic chains from {len(chunks)} chunks...")

    # Synthesize context with full extracted_data
    context = synthesize_context(chunks)

    # Generate logic chain answer
    answer = generate_logic_chains(query, context)

    print(f"[answer_generation] Generated answer: {answer[:200]}...")

    return {
        **state,
        "synthesized_context": context,
        "answer": answer
    }


def synthesize_context(chunks: list) -> str:
    """Format chunks with full context for logic chain extraction."""
    if not chunks:
        return "No relevant context found."

    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        metadata = chunk.get("metadata", {})
        score = chunk.get("score", 0)

        # Parse extracted_data (JSON string)
        extracted_data = metadata.get("extracted_data", "{}")
        if isinstance(extracted_data, str):
            try:
                extracted_data = json.loads(extracted_data)
            except json.JSONDecodeError:
                extracted_data = {}

        # Extract fields
        source = extracted_data.get("source", metadata.get("tg_channel", "unknown"))
        what_happened = extracted_data.get("what_happened", "")
        interpretation = extracted_data.get("interpretation", "")
        used_data = extracted_data.get("used_data", "")
        logic_chains = extracted_data.get("logic_chains", [])

        # Format chunk context
        part = f"[Source {i}: {source}] (score: {score:.2f})\n"
        if what_happened:
            part += f"What happened: {what_happened}\n"
        if interpretation:
            part += f"Interpretation: {interpretation}\n"
        if used_data:
            part += f"Data: {used_data}\n"

        # Format logic chains
        if logic_chains:
            part += "Logic chains:\n"
            for rel in logic_chains:
                cause = rel.get("cause", "")
                effect = rel.get("effect", "")
                mechanism = rel.get("mechanism", "")
                direction = rel.get("direction", "")
                part += f"  - {cause} → {effect} ({direction}): {mechanism}\n"

        context_parts.append(part)

    return "\n---\n".join(context_parts)


def generate_logic_chains(query: str, context: str) -> str:
    """Generate connected logic chains using LLM."""
    if context == "No relevant context found.":
        return "I couldn't find relevant logic chains to answer this question."

    prompt = LOGIC_CHAIN_PROMPT.format(query=query, context=context)
    messages = [{"role": "user", "content": prompt}]

    response = call_claude_sonnet(messages, temperature=0.3, max_tokens=2000)

    print(f"[answer_generation] Full LLM response:\n{response}")

    return response
