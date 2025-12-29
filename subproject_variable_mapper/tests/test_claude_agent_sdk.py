"""
Claude Agent SDK Example with Workflow Extraction
Task: Find monthly S&P 500 constituents from 2020-01-01 to 2025-01-01

This version:
1. Provides context from previous successful run
2. Asks Claude to output a reusable workflow definition
3. Logs all execution steps to a file
"""

import asyncio
import sys
import json
from pathlib import Path
from datetime import datetime
from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    AssistantMessage,
    UserMessage,
    SystemMessage,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    ToolResultBlock
)

# Get the directory where this script is located
SCRIPT_DIR = Path(__file__).parent.resolve()


class TeeLogger:
    """Write to both stdout and a log file."""
    def __init__(self, log_path):
        self.terminal = sys.stdout
        self.log = open(log_path, 'w', encoding='utf-8')

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
        self.log.flush()

    def flush(self):
        self.terminal.flush()
        self.log.flush()

    def close(self):
        self.log.close()


async def get_snp500_constituents():
    """
    Ask Claude Agent to find S&P 500 constituents data.
    This version provides context from previous successful run and
    asks Claude to output a workflow definition.
    """

    # Configure the agent
    options = ClaudeAgentOptions(
        model="claude-sonnet-4-5",
        cwd=str(SCRIPT_DIR),
        permission_mode="bypassPermissions"
    )

    prompt = """
PREVIOUS SUCCESSFUL RUN CONTEXT:
- Task: Fetched S&P 500 constituents from 2020-01-01 to 2025-01-01
- Method that worked:
  1. Scrape Wikipedia (https://en.wikipedia.org/wiki/List_of_S%26P_500_companies)
  2. Get current constituents from table[0] (column: 'Symbol')
  3. Get historical changes from table[1] (columns: Date, Added.Ticker, Removed.Ticker)
  4. Reconstruct backwards by reversing changes for each month
- Key fix: Must use User-Agent header to avoid 403 error
- Output: snp500_constituents.json (61 months)
- Dependencies: pandas, requests, python-dateutil

NEW TASK:
Repeat the same task but ALSO produce a WORKFLOW DEFINITION file.

Please do the following:
1. Fetch S&P 500 constituents from 2020-01-01 to 2025-01-01 (use the method that worked before)
2. Save results to snp500_constituents.json
3. IMPORTANT: Also create workflow_definition.json as a FULL EXECUTABLE SPEC with this structure:
   {
     "workflow_name": "sp500_constituents_fetcher",
     "version": "1.0",
     "description": "Fetch historical S&P 500 constituents from Wikipedia",
     "created_at": "<ISO timestamp>",

     "inputs": {
       "start_date": {"type": "string", "format": "YYYY-MM-DD", "default": "2020-01-01"},
       "end_date": {"type": "string", "format": "YYYY-MM-DD", "default": "2025-01-01"}
     },

     "steps": [
       {
         "step": 1,
         "name": "fetch_wikipedia_page",
         "action": "http_get",
         "config": {
           "url": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
           "headers": {"User-Agent": "Mozilla/5.0 ..."}
         },
         "output_var": "html_content",
         "error_handling": "raise_on_403"
       },
       {
         "step": 2,
         "name": "parse_current_constituents",
         "action": "parse_html_table",
         "config": {
           "input_var": "html_content",
           "table_index": 0,
           "extract_column": "Symbol"
         },
         "output_var": "current_tickers"
       },
       {
         "step": 3,
         "name": "parse_changes_table",
         "action": "parse_html_table",
         "config": {
           "input_var": "html_content",
           "table_index": 1,
           "columns": {"date": "Date", "added": "Added.Ticker", "removed": "Removed.Ticker"}
         },
         "output_var": "changes_df"
       },
       {
         "step": 4,
         "name": "reconstruct_historical",
         "action": "custom_function",
         "config": {
           "function": "reconstruct_backwards",
           "description": "Start from current list, for each month go backwards. For changes after that month, reverse them.",
           "inputs": ["current_tickers", "changes_df", "start_date", "end_date"]
         },
         "output_var": "monthly_constituents"
       },
       {
         "step": 5,
         "name": "save_output",
         "action": "write_json",
         "config": {"input_var": "monthly_constituents", "output_file": "snp500_constituents.json", "indent": 2}
       }
     ],

     "outputs": {
       "primary": {"file": "snp500_constituents.json", "format": "json", "schema": {"<YYYY-MM>": ["ticker1", "..."]}}
     },

     "dependencies": {"python": ">=3.8", "packages": ["pandas", "requests", "python-dateutil"]},

     "executable_script": "fetch_sp500_constituents.py",
     "rerun_command": "python3 fetch_sp500_constituents.py",

     "notes": [
       "Wikipedia may block requests without User-Agent header",
       "Historical accuracy depends on Wikipedia's change log completeness"
     ]
   }

The workflow_definition.json should be detailed enough that:
- A script could parse and execute it programmatically
- A human could manually replicate the steps
- It documents all learned fixes and gotchas

4. Show me a summary of what you accomplished
"""

    print("🚀 Starting Claude Agent SDK (with workflow extraction)...")
    print("=" * 80)
    print("Task: Fetch S&P 500 constituents + Generate workflow definition")
    print("=" * 80)
    print("\n📊 Claude will now iterate through multiple steps...")
    print("   Context provided from previous successful run.\n")

    step_count = 0
    current_tool = None

    async for message in query(prompt=prompt, options=options):

        if isinstance(message, SystemMessage):
            if message.subtype == 'init':
                print(f"📋 Session initialized. Available tools: {len(message.data.get('tools', []))} tools")
                print(f"   Model: {message.data.get('model')}\n")

        elif isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    text = block.text.strip()
                    if text:
                        if len(text) > 300:
                            print(f"\n💭 Claude: {text[:300]}...")
                        else:
                            print(f"\n💭 Claude: {text}")

                elif isinstance(block, ToolUseBlock):
                    step_count += 1
                    current_tool = block.name
                    tool_input = block.input

                    print(f"\n🔧 Step {step_count}: Using tool '{block.name}'")

                    if block.name == 'WebSearch':
                        print(f"   🔍 Searching: {tool_input.get('query', '')}")
                    elif block.name == 'Bash':
                        cmd = tool_input.get('command', '')
                        desc = tool_input.get('description', '')
                        if desc:
                            print(f"   📝 {desc}")
                        if len(cmd) > 100:
                            print(f"   💻 $ {cmd[:100]}...")
                        else:
                            print(f"   💻 $ {cmd}")
                    elif block.name == 'Write':
                        print(f"   📝 Creating file: {tool_input.get('file_path', 'unknown')}")
                    elif block.name == 'Read':
                        print(f"   👀 Reading: {tool_input.get('file_path', 'unknown')}")
                    elif block.name == 'Edit':
                        print(f"   ✏️  Editing: {tool_input.get('file_path', 'unknown')}")
                    elif block.name == 'Glob':
                        print(f"   🔎 Finding files: {tool_input.get('pattern', '')}")
                    elif block.name == 'Grep':
                        print(f"   🔎 Searching for: {tool_input.get('pattern', '')}")
                    elif block.name == 'WebFetch':
                        print(f"   🌐 Fetching: {tool_input.get('url', '')[:80]}...")
                    else:
                        print(f"   📎 Input: {str(tool_input)[:100]}...")

        elif isinstance(message, UserMessage):
            for block in message.content:
                if isinstance(block, ToolResultBlock):
                    content = str(block.content)
                    is_error = block.is_error

                    if is_error:
                        print(f"   ❌ Error occurred (Claude will debug this)")
                        if len(content) < 200:
                            print(f"      {content}")
                    else:
                        if 'error' in content.lower() or 'traceback' in content.lower():
                            print(f"   ⚠️  Execution issue (Claude will handle this)")
                        else:
                            print(f"   ✅ Done")
                            if current_tool in ['WebSearch', 'Grep', 'Glob']:
                                if len(content) > 150:
                                    print(f"      Result: {content[:150]}...")
                                else:
                                    print(f"      Result: {content}")

        elif isinstance(message, ResultMessage):
            print(f"\n{'=' * 80}")
            print(f"✅ Task completed!")
            print(f"   Total steps: {step_count}")
            print(f"   Duration: {message.duration_ms / 1000:.1f}s")
            print(f"   Cost: ${message.total_cost_usd:.4f}")
            print(f"   Turns: {message.num_turns}")
            print(f"{'=' * 80}")


async def main():
    """Main execution with logging."""

    # Set up logging to file
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = SCRIPT_DIR / f"execution_log_{timestamp}.txt"

    # Create TeeLogger to capture all output
    logger = TeeLogger(log_file)
    sys.stdout = logger

    try:
        print(f"📁 Logging to: {log_file}\n")

        await get_snp500_constituents()

        # Check for data output
        output_file = SCRIPT_DIR / 'snp500_constituents.json'
        if output_file.exists():
            print("\n📄 Data output created successfully!")
            print(f"   Location: {output_file}")

            with open(output_file) as f:
                data = json.load(f)

            print(f"\n📊 Data Preview:")
            print(f"   Total months: {len(data)}")
            print(f"   First month: {list(data.keys())[0]}")
            print(f"   Last month: {list(data.keys())[-1]}")

            first_month = list(data.keys())[0]
            constituents = data[first_month][:10]
            print(f"   Sample from {first_month}: {', '.join(constituents)}...")

        # Check for workflow definition
        workflow_file = SCRIPT_DIR / 'workflow_definition.json'
        if workflow_file.exists():
            print("\n📋 Workflow definition created!")
            print(f"   Location: {workflow_file}")

            with open(workflow_file) as f:
                workflow = json.load(f)

            print(f"\n📋 Workflow Summary:")
            print(f"   Name: {workflow.get('workflow_name', 'N/A')}")
            print(f"   Version: {workflow.get('version', 'N/A')}")
            print(f"   Steps: {len(workflow.get('steps', []))}")
            if 'dependencies' in workflow:
                deps = workflow['dependencies']
                if isinstance(deps, dict) and 'packages' in deps:
                    print(f"   Dependencies: {', '.join(deps['packages'])}")
            print(f"   Rerun command: {workflow.get('rerun_command', 'N/A')}")
        else:
            print("\n⚠️  Workflow definition was NOT created!")
            print("   Expected: workflow_definition.json")

        print(f"\n📁 Full execution log saved to: {log_file}")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        print("\nMake sure you have:")
        print("  1. Installed: pip install claude-agent-sdk")
        print("  2. Set ANTHROPIC_API_KEY environment variable")

    finally:
        # Restore stdout and close logger
        sys.stdout = logger.terminal
        logger.close()
        print(f"\n✅ Log file saved: {log_file}")


if __name__ == "__main__":
    print("""
╔════════════════════════════════════════════════════════════════════╗
║     Claude Agent SDK - S&P 500 Constituents + Workflow Export      ║
║                                                                    ║
║  This version:                                                     ║
║  • Provides context from previous successful run                   ║
║  • Asks Claude to output a reusable workflow definition            ║
║  • Logs all execution steps to a file                              ║
╚════════════════════════════════════════════════════════════════════╝
    """)

    asyncio.run(main())
