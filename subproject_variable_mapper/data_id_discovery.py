"""
Data ID Discovery Module

Uses Claude Agent SDK to discover data sources for unmapped financial variables.
Stand-alone, runnable function that searches APIs and web for data sources.
"""

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

from claude_code_sdk import (
    query,
    ClaudeCodeOptions,
    AssistantMessage,
    UserMessage,
    SystemMessage,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    ToolResultBlock,
)

from data_id_discovery_prompts import DISCOVERY_SYSTEM_PROMPT, DISCOVERY_USER_PROMPT
from data_id_validation import validate_api_mapping
from config import PROJECT_ROOT, DISCOVERED_MAPPINGS_FILE

# Setup logging - both file and console
LOGS_DIR = PROJECT_ROOT / "logs"
LOGS_DIR.mkdir(exist_ok=True)

LOG_FILE = LOGS_DIR / f"discovery_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logger = logging.getLogger("discovery")
logger.setLevel(logging.DEBUG)

# File handler - full debug logs
file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)s | %(message)s'))

# Console handler - same as file
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(logging.Formatter('%(message)s'))

logger.addHandler(file_handler)
logger.addHandler(console_handler)


def log(msg: str, level: str = "info"):
    """Log to both file and console."""
    if level == "debug":
        logger.debug(msg)
    elif level == "warning":
        logger.warning(msg)
    elif level == "error":
        logger.error(msg)
    else:
        logger.info(msg)


def load_existing_mappings() -> Dict[str, Any]:
    """Load existing discovered mappings from JSON file."""
    if not DISCOVERED_MAPPINGS_FILE.exists():
        return {
            "metadata": {
                "last_updated": None,
                "total_mappings": 0,
                "known_apis": ["FRED", "World Bank", "BLS", "OECD", "IMF"]
            },
            "mappings": {}
        }

    with open(DISCOVERED_MAPPINGS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_mappings(data: Dict[str, Any]) -> None:
    """Save mappings to JSON file."""
    # Ensure mappings directory exists
    DISCOVERED_MAPPINGS_FILE.parent.mkdir(parents=True, exist_ok=True)

    data["metadata"]["last_updated"] = datetime.now(timezone.utc).isoformat()
    data["metadata"]["total_mappings"] = len(data["mappings"])

    with open(DISCOVERED_MAPPINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    log(f"[discovery] Saved {len(data['mappings'])} mappings to {DISCOVERED_MAPPINGS_FILE}")


def validate_discovery_result(result: dict) -> bool:
    """
    Validate discovery result has required fields including mapping_rationale.

    Returns True if valid, False if missing required fields or rationale too short.
    """
    # Required fields for all discovery types
    required_fields = ['normalized_name', 'type']

    # For non-failed discoveries, also require data_id and mapping_rationale
    if result.get('type') not in ['not_found', 'discovery_failed']:
        required_fields.extend(['data_id', 'mapping_rationale'])

    for field in required_fields:
        if not result.get(field):
            log(f"[validation] WARNING: Missing required field: {field}", "warning")
            return False

    # Rationale must be substantive (50+ characters) for successful discoveries
    rationale = result.get('mapping_rationale', '')
    if result.get('type') not in ['not_found', 'discovery_failed']:
        if len(rationale) < 50:
            log(f"[validation] WARNING: mapping_rationale too short ({len(rationale)} chars): {rationale}", "warning")
            return False

    return True


def extract_json_from_response(text: str) -> Optional[Dict]:
    """Extract JSON from agent response, handling markdown code blocks."""
    # Try to find JSON in markdown code blocks
    json_match = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', text)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find raw JSON object
    json_match = re.search(r'\{[\s\S]*\}', text)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass

    return None


async def discover_single_variable(
    normalized_name: str,
    description: str = "",
    context: str = ""
) -> Dict[str, Any]:
    """
    Discover data source for a single variable using Claude Agent SDK.

    Args:
        normalized_name: The normalized variable name (e.g., "tga", "vix")
        description: Optional description of what this variable measures
        context: Optional context about how this variable is used

    Returns:
        Discovery result dict with type, data_id, source, etc.
    """
    log(f"\n{'='*60}")
    log(f"[discovery] Discovering data source for: {normalized_name}")
    log(f"{'='*60}")

    # Build the prompt
    user_prompt = DISCOVERY_USER_PROMPT.format(
        normalized_name=normalized_name,
        description=description or "Financial metric",
        context=context or "Used in financial analysis"
    )

    # Full prompt includes system context
    full_prompt = f"{DISCOVERY_SYSTEM_PROMPT}\n\n{user_prompt}"

    # Debug: Print prompt (truncated)
    log(f"\n[discovery] INPUT PROMPT (truncated):")
    log(f"{full_prompt[:500]}...")

    # Configure Claude Agent SDK
    options = ClaudeCodeOptions(
        model="claude-sonnet-4-5",
        cwd=str(PROJECT_ROOT),
        permission_mode="bypassPermissions"
    )

    collected_text = ""
    step_count = 0
    current_tool = None

    try:
        async for message in query(prompt=full_prompt, options=options):

            # === SystemMessage: Session initialization ===
            if isinstance(message, SystemMessage):
                if message.subtype == 'init':
                    log(f"\n[discovery] Session initialized")
                    log(f"Available tools: {len(message.data.get('tools', []))} tools")
                    log(f"Model: {message.data.get('model')}")

            # === AssistantMessage: Claude's response ===
            elif isinstance(message, AssistantMessage):
                for block in message.content:

                    # TextBlock: Claude's reasoning/text
                    if isinstance(block, TextBlock):
                        text = block.text.strip()
                        collected_text += block.text

                        if text:
                            log(f"\n[discovery] Claude thinking:")
                            log(f"{text}")

                    # ToolUseBlock: Tool being called
                    elif isinstance(block, ToolUseBlock):
                        step_count += 1
                        current_tool = block.name
                        tool_input = block.input

                        log(f"\n[discovery] Step {step_count}: Using tool '{block.name}'")

                        # Log tool-specific inputs
                        if block.name == 'WebSearch':
                            log(f"Query: {tool_input.get('query', '')}")
                        elif block.name == 'WebFetch':
                            url = tool_input.get('url', '')
                            log(f"URL: {url[:80]}{'...' if len(url) > 80 else ''}")
                            log(f"Prompt: {tool_input.get('prompt', '')[:100]}...")
                        elif block.name == 'Bash':
                            cmd = tool_input.get('command', '')
                            desc = tool_input.get('description', '')
                            if desc:
                                log(f"Description: {desc}")
                            log(f"Command: {cmd[:100]}{'...' if len(cmd) > 100 else ''}")
                        elif block.name == 'Write':
                            log(f"File: {tool_input.get('file_path', 'unknown')}")
                            content = tool_input.get('content', '')
                            log(f"Content length: {len(content)} chars")
                        elif block.name == 'Read':
                            log(f"File: {tool_input.get('file_path', 'unknown')}")
                        elif block.name == 'Edit':
                            log(f"File: {tool_input.get('file_path', 'unknown')}")
                            log(f"Old: {tool_input.get('old_string', '')[:50]}...")
                            log(f"New: {tool_input.get('new_string', '')[:50]}...")
                        elif block.name == 'Glob':
                            log(f"Pattern: {tool_input.get('pattern', '')}")
                        elif block.name == 'Grep':
                            log(f"Pattern: {tool_input.get('pattern', '')}")
                            log(f"Path: {tool_input.get('path', 'cwd')}")
                        else:
                            # Generic tool input
                            input_str = str(tool_input)
                            log(f"Input: {input_str[:150]}{'...' if len(input_str) > 150 else ''}")

            # === UserMessage: Tool results ===
            elif isinstance(message, UserMessage):
                for block in message.content:
                    if isinstance(block, ToolResultBlock):
                        content = str(block.content)
                        is_error = block.is_error

                        if is_error:
                            log(f"\n[discovery] Tool ERROR:")
                            log(f"{content[:300]}{'...' if len(content) > 300 else ''}")
                        else:
                            # Check for execution issues
                            if 'error' in content.lower() or 'traceback' in content.lower():
                                log(f"\n[discovery] Tool execution issue (agent will handle):")
                                log(f"{content[:200]}...")
                            else:
                                log(f"\n[discovery] Tool result: SUCCESS")
                                # Show preview for search/read results
                                if current_tool in ['WebSearch', 'Grep', 'Glob', 'Read', 'WebFetch']:
                                    preview = content[:200] if len(content) > 200 else content
                                    log(f"Preview: {preview}{'...' if len(content) > 200 else ''}")

            # === ResultMessage: Final result ===
            elif isinstance(message, ResultMessage):
                log(f"\n{'='*60}")
                log(f"[discovery] Agent completed for '{normalized_name}'")
                log(f"Total steps: {step_count}")
                log(f"Duration: {message.duration_ms / 1000:.1f}s")
                log(f"Cost: ${message.total_cost_usd:.4f}")
                log(f"Turns: {message.num_turns}")
                log(f"{'='*60}")

        # Extract JSON result from collected text
        log(f"\n[discovery] Parsing agent response...")
        log(f"Collected text length: {len(collected_text)} chars")

        result = extract_json_from_response(collected_text)

        if result:
            log(f"\n[discovery] OUTPUT (parsed JSON):")
            log(json.dumps(result, indent=2))
            result["discovered_at"] = datetime.now(timezone.utc).isoformat()

            # Validate the discovery result
            is_valid = validate_discovery_result(result)
            result["rationale_validated"] = is_valid
            if not is_valid:
                log(f"[discovery] WARNING: Result failed validation (missing/short mapping_rationale)", "warning")

            return result
        else:
            log(f"\n[discovery] WARNING: Could not parse JSON from response")
            log(f"Raw response (first 500 chars): {collected_text[:500]}")
            return {
                "normalized_name": normalized_name,
                "type": "discovery_failed",
                "notes": "Could not parse agent response",
                "raw_response": collected_text[:500],
                "discovered_at": datetime.now(timezone.utc).isoformat()
            }

    except Exception as e:
        log(f"\n[discovery] EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        return {
            "normalized_name": normalized_name,
            "type": "discovery_failed",
            "notes": str(e),
            "discovered_at": datetime.now(timezone.utc).isoformat()
        }


async def discover_data_ids(
    unmapped_variables: List[str],
    skip_existing: bool = True,
    validate: bool = True
) -> Dict[str, Any]:
    """
    Discover data IDs for a list of unmapped variables.

    Args:
        unmapped_variables: List of normalized variable names to discover
        skip_existing: Skip variables already in discovered_data_ids.json
        validate: Validate API mappings by pinging the APIs

    Returns:
        Updated mappings dict
    """
    log(f"\n{'#'*60}")
    log(f"#DATA ID DISCOVERY")
    log(f"#Variables: {len(unmapped_variables)}")
    log(f"#Skip existing: {skip_existing}")
    log(f"#Validate: {validate}")
    log(f"{'#'*60}")

    # Load existing mappings
    data = load_existing_mappings()
    existing_mappings = data["mappings"]
    log(f"\n[discovery] Loaded {len(existing_mappings)} existing mappings")

    # Filter out already-mapped variables
    if skip_existing:
        to_discover = [v for v in unmapped_variables if v not in existing_mappings]
        skipped = len(unmapped_variables) - len(to_discover)
        if skipped > 0:
            log(f"[discovery] Skipping {skipped} already-mapped variables:")
            for v in unmapped_variables:
                if v in existing_mappings:
                    log(f"- {v}: {existing_mappings[v].get('type', 'unknown')}")
    else:
        to_discover = unmapped_variables

    if not to_discover:
        log("\n[discovery] No variables to discover")
        return data

    log(f"\n[discovery] Will discover {len(to_discover)} variables:")
    for v in to_discover:
        log(f"- {v}")

    # Discover each variable
    results = {
        "api": 0,
        "needs_registration": 0,
        "scrape": 0,
        "not_found": 0,
        "discovery_failed": 0,
        "rationale_validated": 0,
        "rationale_failed": 0
    }

    for i, var_name in enumerate(to_discover, 1):
        log(f"\n{'*'*60}")
        log(f"*Processing {i}/{len(to_discover)}: {var_name}")
        log(f"{'*'*60}")

        result = await discover_single_variable(var_name)

        # Validate API mappings
        if validate and result.get("type") == "api":
            log(f"\n[validation] Validating API mapping for {var_name}...")
            validation_result = validate_api_mapping(result)
            result["validated"] = validation_result
            if validation_result is True:
                log(f"[validation] SUCCESS: {result.get('data_id')} is valid")
            elif validation_result is False:
                log(f"[validation] FAILED: {result.get('data_id')} validation failed")
            else:
                log(f"[validation] SKIPPED: No validator available")

        # Store result
        existing_mappings[var_name] = result
        result_type = result.get("type", "unknown")
        if result_type in results:
            results[result_type] += 1

        # Track rationale validation
        if result.get("rationale_validated"):
            results["rationale_validated"] += 1
        elif result.get("type") not in ["not_found", "discovery_failed"]:
            results["rationale_failed"] += 1

        # Save after each discovery (in case of interruption)
        save_mappings(data)

    # Summary
    log(f"\n{'#'*60}")
    log(f"#DISCOVERY COMPLETE")
    log(f"{'#'*60}")
    log(f"\nResults:")
    log(f"API mapped:         {results['api']}")
    log(f"Needs registration: {results['needs_registration']}")
    log(f"Scrapable:          {results['scrape']}")
    log(f"Not found:          {results['not_found']}")
    log(f"Failed:             {results['discovery_failed']}")
    log(f"\nRationale Validation:")
    log(f"Validated:          {results['rationale_validated']}")
    log(f"Failed validation:  {results['rationale_failed']}")
    log(f"\nMappings saved to: {DISCOVERED_MAPPINGS_FILE}")

    return data


def discover_data_ids_sync(
    unmapped_variables: List[str],
    skip_existing: bool = True,
    validate: bool = True
) -> Dict[str, Any]:
    """Synchronous wrapper for discover_data_ids."""
    return asyncio.run(discover_data_ids(unmapped_variables, skip_existing, validate))


# CLI interface
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Discover data IDs for financial variables")
    parser.add_argument(
        "--variables", "-v",
        type=str,
        help="Comma-separated list of variables to discover (e.g., 'tga,vix,cpi')"
    )
    parser.add_argument(
        "--file", "-f",
        type=str,
        help="Path to file with variables (one per line)"
    )
    parser.add_argument(
        "--no-skip",
        action="store_true",
        help="Re-discover even if variable already exists in mappings"
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip API validation"
    )

    args = parser.parse_args()

    # Get variables to discover
    variables = []

    if args.variables:
        variables = [v.strip() for v in args.variables.split(",")]
    elif args.file:
        with open(args.file, 'r') as f:
            variables = [line.strip() for line in f if line.strip()]
    else:
        # Default test variables
        log("No variables specified. Running with test variables...")
        variables = ["tga", "vix", "unemployment_rate"]

    log(f"\n{'='*60}")
    log(f"DATA ID DISCOVERY CLI")
    log(f"{'='*60}")
    log(f"Variables to discover: {variables}")
    log(f"Skip existing: {not args.no_skip}")
    log(f"Validate: {not args.no_validate}")

    # Run discovery
    result = discover_data_ids_sync(
        variables,
        skip_existing=not args.no_skip,
        validate=not args.no_validate
    )

    # Print final results
    log(f"\n{'='*60}")
    log(f"FINAL DISCOVERY RESULTS")
    log(f"{'='*60}")

    for var_name in variables:
        mapping = result["mappings"].get(var_name, {})
        log(f"\n{var_name}:")
        log(f"Type: {mapping.get('type', 'unknown')}")
        if mapping.get("data_id"):
            log(f"Data ID: {mapping.get('data_id')}")
        if mapping.get("source"):
            log(f"Source: {mapping.get('source')}")
        if mapping.get("validated") is not None:
            log(f"API Validated: {mapping.get('validated')}")
        if mapping.get("rationale_validated") is not None:
            log(f"Rationale Validated: {mapping.get('rationale_validated')}")
        if mapping.get("mapping_rationale"):
            rationale = mapping.get('mapping_rationale', '')
            log(f"Rationale: {rationale[:100]}{'...' if len(rationale) > 100 else ''}")
        if mapping.get("description"):
            log(f"Description: {mapping.get('description')}")
        if mapping.get("notes"):
            log(f"Notes: {mapping.get('notes')}")
        if mapping.get("scrape_code"):
            log(f"Scrape code: (available)")
        if mapping.get("registration_url"):
            log(f"Registration URL: {mapping.get('registration_url')}")
