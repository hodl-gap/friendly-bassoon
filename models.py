import os
import asyncio
from pathlib import Path
from openai import OpenAI, AsyncOpenAI
from anthropic import Anthropic, AsyncAnthropic
from dotenv import load_dotenv
from typing import List, Dict, Any
import json

# Load .env from the same directory as this file
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path)

# Initialize sync clients
openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY')) if os.getenv('OPENAI_API_KEY') else None
anthropic_client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY')) if os.getenv('ANTHROPIC_API_KEY') else None

# Initialize async clients (for parallel processing)
async_openai_client = AsyncOpenAI(api_key=os.getenv('OPENAI_API_KEY')) if os.getenv('OPENAI_API_KEY') else None
async_anthropic_client = AsyncAnthropic(api_key=os.getenv('ANTHROPIC_API_KEY')) if os.getenv('ANTHROPIC_API_KEY') else None

# =============================================================================
# RATE LIMITS DOCUMENTATION
# =============================================================================
#
# OPENAI RATE LIMITS (as of Nov 2025):
# - Tier 1: 500 RPM (requests/min), 30,000 TPM (tokens/min)
# - Tier 2: 5,000 RPM, 450,000 TPM
# - Tier 3: 5,000 RPM, 800,000 TPM
# - Tier 4: 10,000 RPM, 2,000,000 TPM
# - Tier 5: 10,000 RPM, 10,000,000 TPM
#
# GPT-5 models have same limits as GPT-4 tier
# Check your tier: https://platform.openai.com/account/limits
#
# ANTHROPIC RATE LIMITS (as of Nov 2025):
# - Tier 1: 50 RPM, 40,000 TPM, 1,000 RPD (requests/day)
# - Tier 2: 1,000 RPM, 80,000 TPM, 10,000 RPD
# - Tier 3: 2,000 RPM, 160,000 TPM, 20,000 RPD
# - Tier 4: 4,000 RPM, 400,000 TPM, 50,000 RPD
#
# For parallel processing, recommended concurrent requests:
# - Conservative: 5-10 concurrent requests
# - Moderate: 10-20 concurrent requests (Tier 2+)
# - Aggressive: 20-50 concurrent requests (Tier 3+)
#
# BATCH API (50% cost savings, async processing):
# - OpenAI: Up to 50,000 requests per batch, 24hr completion window
# - Anthropic: Up to 10,000 requests per batch, 24hr completion window
# =============================================================================

# =============================================================================
# OPENAI MODELS - GPT-4.1 Series (Previous Generation)
# =============================================================================

def call_gpt41(messages, temperature=0.7, max_tokens=4000):
    """Call GPT-4.1 (previous flagship model)"""
    response = openai_client.chat.completions.create(
        model="gpt-4.1",
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens
    )
    return response.choices[0].message.content

def call_gpt41_mini(messages, temperature=0.7, max_tokens=4000):
    """Call GPT-4.1-mini (cheaper, faster)"""
    response = openai_client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens
    )
    return response.choices[0].message.content

# =============================================================================
# OPENAI MODELS - GPT-5 Series (Latest Generation - Nov 2025)
# =============================================================================

def call_gpt5(messages, temperature=1.0, max_tokens=8000):
    """
    Call GPT-5 (flagship model - released Nov 2025)

    Capabilities:
    - Advanced reasoning and analysis
    - Complex instruction following
    - Extended context understanding
    - Best for: complex extraction, analysis, research tasks

    Note: GPT-5 only supports temperature=1.0 (parameter ignored)
    Pricing: ~$15/1M input tokens, ~$60/1M output tokens (estimate)
    """
    response = openai_client.chat.completions.create(
        model="gpt-5",
        messages=messages,
        # GPT-5 only supports temperature=1.0, so we don't pass it
        max_completion_tokens=max_tokens  # GPT-5 uses max_completion_tokens
    )
    return response.choices[0].message.content


def call_gpt5_diagnostic(messages, max_tokens=8000):
    """
    Diagnostic version of call_gpt5 that prints full response details.
    Use this to debug empty response issues.
    """
    print("\n" + "=" * 60)
    print("GPT-5 DIAGNOSTIC CALL")
    print("=" * 60)

    response = openai_client.chat.completions.create(
        model="gpt-5",
        messages=messages,
        max_completion_tokens=max_tokens
    )

    # Print full diagnostic info
    print(f"Model: {response.model}")
    print(f"ID: {response.id}")
    print(f"Finish reason: {response.choices[0].finish_reason}")
    print("-" * 40)
    print("TOKEN USAGE:")
    print(f"  prompt_tokens: {response.usage.prompt_tokens}")
    print(f"  completion_tokens: {response.usage.completion_tokens}")
    print(f"  total_tokens: {response.usage.total_tokens}")

    # Check for detailed token breakdown (reasoning tokens)
    if hasattr(response.usage, 'completion_tokens_details') and response.usage.completion_tokens_details:
        print(f"  completion_tokens_details: {response.usage.completion_tokens_details}")
    if hasattr(response.usage, 'prompt_tokens_details') and response.usage.prompt_tokens_details:
        print(f"  prompt_tokens_details: {response.usage.prompt_tokens_details}")

    # Print raw response object for inspection
    print("-" * 40)
    print("RAW RESPONSE OBJECT:")
    print(f"  choices count: {len(response.choices)}")
    print(f"  choice[0].message: {response.choices[0].message}")

    # Print content
    content = response.choices[0].message.content
    print("-" * 40)
    print("CONTENT:")
    print(f"  Type: {type(content)}")
    print(f"  Length: {len(content) if content else 0}")
    if content:
        print(f"  Preview (first 500 chars): {content[:500]}")
    else:
        print("  Content is EMPTY or None!")

    print("=" * 60 + "\n")

    return content


def call_gpt51(messages, temperature=1.0, max_tokens=8000):
    """
    Call GPT-5.1 (latest flagship model - Nov 2025)

    Capabilities:
    - Most advanced reasoning
    - Best performance on benchmarks
    - Enhanced instruction following
    - Best for: most demanding tasks requiring highest accuracy

    Note: GPT-5 series only supports temperature=1.0 (parameter ignored)
    Pricing: ~$20/1M input tokens, ~$80/1M output tokens (estimate)
    """
    response = openai_client.chat.completions.create(
        model="gpt-5.1",
        messages=messages,
        # GPT-5 series only supports temperature=1.0, so we don't pass it
        max_completion_tokens=max_tokens  # GPT-5 series uses max_completion_tokens
    )
    return response.choices[0].message.content

def call_gpt5_mini(messages, temperature=1.0, max_tokens=4000):
    """
    Call GPT-5-mini (cost-effective reasoning model)

    Capabilities:
    - Good reasoning at lower cost
    - Faster response times
    - Best for: moderate complexity tasks, high volume processing

    Note: GPT-5 series only supports temperature=1.0 (parameter ignored)
    Pricing: ~$3/1M input tokens, ~$12/1M output tokens (estimate)
    """
    response = openai_client.chat.completions.create(
        model="gpt-5-mini",
        messages=messages,
        # GPT-5 series only supports temperature=1.0, so we don't pass it
        max_completion_tokens=max_tokens  # GPT-5 series uses max_completion_tokens
    )
    return response.choices[0].message.content

def call_gpt5_nano(messages, temperature=1.0, max_tokens=2000):
    """
    Call GPT-5-nano (lightweight, fastest)

    Capabilities:
    - Basic tasks at minimal cost
    - Fastest response times
    - Best for: simple tasks, categorization, quick lookups

    Note: GPT-5 series only supports temperature=1.0 (parameter ignored)
    Pricing: ~$0.5/1M input tokens, ~$2/1M output tokens (estimate)
    """
    response = openai_client.chat.completions.create(
        model="gpt-5-nano",
        messages=messages,
        # GPT-5 series only supports temperature=1.0, so we don't pass it
        max_completion_tokens=max_tokens  # GPT-5 series uses max_completion_tokens
    )
    return response.choices[0].message.content

# =============================================================================
# ANTHROPIC MODELS - Claude 4.5 Series (Latest - Nov 2025)
# =============================================================================

def call_claude_opus(messages, temperature=0.7, max_tokens=8000):
    """
    Call Claude Opus 4.5 (most powerful Claude model - released Nov 24, 2025)

    Capabilities:
    - Most advanced reasoning and analysis
    - Best performance on complex tasks
    - Extended thinking capabilities
    - Best for: research, complex analysis, demanding tasks

    Pricing: $15/1M input tokens, $75/1M output tokens
    Model ID: claude-opus-4-5-20251101
    """
    response = anthropic_client.messages.create(
        model="claude-opus-4-5-20251101",
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens
    )
    return response.content[0].text

def call_claude_sonnet(messages, temperature=0.7, max_tokens=8000):
    """
    Call Claude Sonnet 4.5 (balanced performance - Oct 2025)

    Capabilities:
    - Strong reasoning and analysis
    - Good balance of speed and capability
    - Best for: most production tasks, extraction, analysis

    Pricing: $3/1M input tokens, $15/1M output tokens
    Model ID: claude-sonnet-4-5-20250929
    """
    response = anthropic_client.messages.create(
        model="claude-sonnet-4-5-20250929",
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens
    )
    return response.content[0].text

def call_claude_haiku(messages, temperature=0.7, max_tokens=4000):
    """
    Call Claude Haiku 4.5 (fast, cost-effective - Nov 2025)

    Capabilities:
    - Fast responses
    - Cost-effective for high volume
    - Good for simpler tasks
    - Best for: categorization, simple extraction, quick lookups

    Pricing: $0.80/1M input tokens, $4/1M output tokens
    Model ID: claude-haiku-4-5-20251101
    """
    response = anthropic_client.messages.create(
        model="claude-haiku-4-5-20251101",
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens
    )
    return response.content[0].text

# =============================================================================
# ASYNC VERSIONS FOR PARALLEL PROCESSING
# =============================================================================

async def call_gpt5_async(messages, temperature=1.0, max_tokens=8000):
    """Async version of call_gpt5 for parallel processing (temperature ignored, GPT-5 only supports 1.0)"""
    response = await async_openai_client.chat.completions.create(
        model="gpt-5",
        messages=messages,
        # GPT-5 only supports temperature=1.0, so we don't pass it
        max_completion_tokens=max_tokens  # GPT-5 series uses max_completion_tokens
    )
    return response.choices[0].message.content

async def call_gpt51_async(messages, temperature=1.0, max_tokens=8000):
    """Async version of call_gpt51 for parallel processing (temperature ignored, GPT-5 only supports 1.0)"""
    response = await async_openai_client.chat.completions.create(
        model="gpt-5.1",
        messages=messages,
        # GPT-5 series only supports temperature=1.0, so we don't pass it
        max_completion_tokens=max_tokens  # GPT-5 series uses max_completion_tokens
    )
    return response.choices[0].message.content

async def call_gpt5_mini_async(messages, temperature=1.0, max_tokens=4000):
    """Async version of call_gpt5_mini for parallel processing (temperature ignored, GPT-5 only supports 1.0)"""
    response = await async_openai_client.chat.completions.create(
        model="gpt-5-mini",
        messages=messages,
        # GPT-5 series only supports temperature=1.0, so we don't pass it
        max_completion_tokens=max_tokens  # GPT-5 series uses max_completion_tokens
    )
    return response.choices[0].message.content

async def call_claude_opus_async(messages, temperature=0.7, max_tokens=8000):
    """Async version of call_claude_opus for parallel processing"""
    response = await async_anthropic_client.messages.create(
        model="claude-opus-4-5-20251101",
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens
    )
    return response.content[0].text

async def call_claude_sonnet_async(messages, temperature=0.7, max_tokens=8000):
    """Async version of call_claude_sonnet for parallel processing"""
    response = await async_anthropic_client.messages.create(
        model="claude-sonnet-4-5-20250929",
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens
    )
    return response.content[0].text

async def call_claude_haiku_async(messages, temperature=0.7, max_tokens=4000):
    """Async version of call_claude_haiku for parallel processing"""
    response = await async_anthropic_client.messages.create(
        model="claude-haiku-4-5-20251101",
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens
    )
    return response.content[0].text

# =============================================================================
# PARALLEL BATCH PROCESSING UTILITIES
# =============================================================================

async def process_batch_parallel(
    messages_list: List[List[Dict]],
    model_func: str = "gpt5",
    max_concurrent: int = 10,
    temperature: float = 0.7,
    max_tokens: int = 8000
) -> List[str]:
    """
    Process multiple messages in parallel with concurrency control.

    Args:
        messages_list: List of message arrays (each is a conversation)
        model_func: Model to use - "gpt5", "gpt51", "gpt5_mini", "claude_opus", "claude_sonnet", "claude_haiku"
        max_concurrent: Maximum concurrent requests (default 10, adjust based on rate limits)
        temperature: Model temperature
        max_tokens: Max tokens per response

    Returns:
        List of responses in same order as input

    Rate Limit Guidelines:
    - Tier 1 (new accounts): max_concurrent=5
    - Tier 2: max_concurrent=10-15
    - Tier 3+: max_concurrent=20-30
    - Add delays if hitting rate limits

    Example:
        messages_list = [
            [{"role": "user", "content": "Extract from message 1"}],
            [{"role": "user", "content": "Extract from message 2"}],
            [{"role": "user", "content": "Extract from message 3"}],
        ]
        results = await process_batch_parallel(messages_list, model_func="gpt5", max_concurrent=10)
    """

    # Map model names to async functions
    model_map = {
        "gpt5": call_gpt5_async,
        "gpt51": call_gpt51_async,
        "gpt5_mini": call_gpt5_mini_async,
        "claude_opus": call_claude_opus_async,
        "claude_sonnet": call_claude_sonnet_async,
        "claude_haiku": call_claude_haiku_async,
    }

    if model_func not in model_map:
        raise ValueError(f"Unknown model: {model_func}. Available: {list(model_map.keys())}")

    async_func = model_map[model_func]
    semaphore = asyncio.Semaphore(max_concurrent)

    async def process_single(idx: int, messages: List[Dict]) -> tuple:
        async with semaphore:
            try:
                result = await async_func(messages, temperature=temperature, max_tokens=max_tokens)
                return (idx, result, None)
            except Exception as e:
                return (idx, None, str(e))

    # Create tasks for all messages
    tasks = [process_single(i, msgs) for i, msgs in enumerate(messages_list)]

    # Run all tasks concurrently (semaphore controls actual concurrency)
    results = await asyncio.gather(*tasks)

    # Sort by index and extract results
    results.sort(key=lambda x: x[0])

    # Check for errors
    errors = [(r[0], r[2]) for r in results if r[2] is not None]
    if errors:
        print(f"WARNING: {len(errors)} requests failed:")
        for idx, err in errors[:5]:  # Show first 5 errors
            print(f"  - Request {idx}: {err}")

    return [r[1] for r in results]


async def process_batch_parallel_with_retry(
    messages_list: List[List[Dict]],
    model_func: str = "gpt5",
    max_concurrent: int = 10,
    temperature: float = 0.7,
    max_tokens: int = 8000,
    max_retries: int = 3,
    fallback_model: str = "claude_sonnet"
) -> List[str]:
    """
    Process multiple messages in parallel with retry logic and fallback.

    If a request fails or returns empty, it will:
    1. Retry up to max_retries times with exponential backoff
    2. If still failing, fallback to fallback_model

    Args:
        messages_list: List of message arrays
        model_func: Primary model to use
        max_concurrent: Maximum concurrent requests
        temperature: Model temperature
        max_tokens: Max tokens per response
        max_retries: Number of retry attempts before fallback
        fallback_model: Model to use if primary fails

    Returns:
        List of responses in same order as input
    """
    import time

    # Map model names to async functions
    model_map = {
        "gpt5": call_gpt5_async,
        "gpt51": call_gpt51_async,
        "gpt5_mini": call_gpt5_mini_async,
        "claude_opus": call_claude_opus_async,
        "claude_sonnet": call_claude_sonnet_async,
        "claude_haiku": call_claude_haiku_async,
    }

    if model_func not in model_map:
        raise ValueError(f"Unknown model: {model_func}. Available: {list(model_map.keys())}")
    if fallback_model not in model_map:
        raise ValueError(f"Unknown fallback model: {fallback_model}. Available: {list(model_map.keys())}")

    primary_func = model_map[model_func]
    fallback_func = model_map[fallback_model]
    semaphore = asyncio.Semaphore(max_concurrent)

    async def process_single_with_retry(idx: int, messages: List[Dict]) -> tuple:
        async with semaphore:
            last_error = None

            # Try primary model with retries
            for attempt in range(max_retries):
                try:
                    result = await primary_func(messages, temperature=temperature, max_tokens=max_tokens)
                    if result and len(result.strip()) > 0:
                        return (idx, result, None, model_func)
                    else:
                        last_error = "Empty response"
                        print(f"  [Batch {idx}] Attempt {attempt+1}/{max_retries}: Empty response, retrying...")
                except Exception as e:
                    last_error = str(e)
                    print(f"  [Batch {idx}] Attempt {attempt+1}/{max_retries}: {e}, retrying...")

                # Exponential backoff before retry
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)

            # Primary failed, try fallback
            print(f"  [Batch {idx}] Primary model failed after {max_retries} attempts, falling back to {fallback_model}")
            try:
                result = await fallback_func(messages, temperature=temperature, max_tokens=max_tokens)
                if result and len(result.strip()) > 0:
                    return (idx, result, None, fallback_model)
                else:
                    return (idx, None, "Fallback also returned empty", None)
            except Exception as e:
                return (idx, None, f"Fallback failed: {e}", None)

    # Create tasks for all messages
    tasks = [process_single_with_retry(i, msgs) for i, msgs in enumerate(messages_list)]

    # Run all tasks concurrently
    results = await asyncio.gather(*tasks)

    # Sort by index
    results.sort(key=lambda x: x[0])

    # Summary
    success_primary = sum(1 for r in results if r[3] == model_func)
    success_fallback = sum(1 for r in results if r[3] == fallback_model)
    failed = sum(1 for r in results if r[1] is None)

    print(f"\nBatch Processing Summary:")
    print(f"  Primary ({model_func}): {success_primary} succeeded")
    print(f"  Fallback ({fallback_model}): {success_fallback} succeeded")
    print(f"  Failed: {failed}")

    return [r[1] for r in results]


def process_batch_parallel_sync(
    messages_list: List[List[Dict]],
    model_func: str = "gpt5",
    max_concurrent: int = 10,
    temperature: float = 0.7,
    max_tokens: int = 8000
) -> List[str]:
    """
    Synchronous wrapper for process_batch_parallel.
    Use this when not in an async context.

    Example:
        results = process_batch_parallel_sync(messages_list, model_func="gpt5")
    """
    return asyncio.run(process_batch_parallel(
        messages_list, model_func, max_concurrent, temperature, max_tokens
    ))


def process_batch_parallel_with_retry_sync(
    messages_list: List[List[Dict]],
    model_func: str = "gpt5",
    max_concurrent: int = 10,
    temperature: float = 0.7,
    max_tokens: int = 8000,
    max_retries: int = 3,
    fallback_model: str = "claude_sonnet"
) -> List[str]:
    """
    Synchronous wrapper for process_batch_parallel_with_retry.
    Use this when not in an async context.

    Example:
        results = process_batch_parallel_with_retry_sync(messages_list, model_func="gpt5")
    """
    return asyncio.run(process_batch_parallel_with_retry(
        messages_list, model_func, max_concurrent, temperature, max_tokens,
        max_retries, fallback_model
    ))


# =============================================================================
# OPENAI EMBEDDINGS
# =============================================================================

def call_openai_embedding(text: str, model: str = "text-embedding-3-large") -> List[float]:
    """
    Generate embedding vector for text using OpenAI embeddings API.

    Args:
        text: Text to embed
        model: Embedding model ("text-embedding-3-large" or "text-embedding-3-small")

    Returns:
        List of floats (embedding vector)

    Pricing: $0.13/1M tokens (large), $0.02/1M tokens (small)
    Dimensions: 3072 (large) or 1536 (small)
    """
    response = openai_client.embeddings.create(
        model=model,
        input=text
    )
    return response.data[0].embedding


def call_openai_embedding_batch(texts: List[str], model: str = "text-embedding-3-large") -> List[List[float]]:
    """
    Batch embed multiple texts in single API call.

    Args:
        texts: List of texts to embed (max 2048 texts per call)
        model: Embedding model ("text-embedding-3-large" or "text-embedding-3-small")

    Returns:
        List of embedding vectors (same order as input)

    Pricing: $0.13/1M tokens (large), $0.02/1M tokens (small)
    Dimensions: 3072 (large) or 1536 (small)
    """
    response = openai_client.embeddings.create(
        model=model,
        input=texts
    )
    return [item.embedding for item in response.data]
