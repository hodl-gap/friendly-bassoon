"""Debug script to see what message types the SDK returns"""
import asyncio
from pathlib import Path
from claude_agent_sdk import query, ClaudeAgentOptions

SCRIPT_DIR = Path(__file__).parent.resolve()

async def debug_messages():
    options = ClaudeAgentOptions(
        model="claude-sonnet-4-5",
        cwd=str(SCRIPT_DIR),
        permission_mode="bypassPermissions"
    )

    prompt = "Write a simple hello world python script to hello.py and run it."

    print("Starting debug test...\n")

    async for message in query(prompt=prompt, options=options):
        print(f"Message type: {type(message).__name__}")
        print(f"Message dir: {[x for x in dir(message) if not x.startswith('_')]}")
        print(f"Message repr: {repr(message)[:500]}")
        print("-" * 80)

if __name__ == "__main__":
    asyncio.run(debug_messages())
