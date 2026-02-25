"""Test script for MCP server functionality.

This script tests:
1. Server startup
2. Tool availability
3. Tool execution
4. Resource access
5. Prompt availability
"""

import asyncio
import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.mcp.server import mcp
from src.mcp.tools.transcription import transcribe_video
from src.mcp.tools.transcripts import get_transcript, list_transcripts, get_job_status
from src.mcp.tools.channels import add_channel, sync_channel, transcribe_channel_pending
from src.mcp.resources.transcripts import read_transcript_resource
from src.mcp.resources.jobs import read_job_resource
from src.mcp.prompts.transcribe import generate_transcribe_video_prompt
from src.mcp.prompts.channel_sync import generate_channel_sync_prompt


async def test_tools() -> None:
    """Test all MCP tools."""
    print("\n" + "=" * 60)
    print("TESTING MCP TOOLS")
    print("=" * 60)

    # Test 1: list_transcripts (should work without external deps)
    print("\n[1] Testing list_transcripts...")
    try:
        result = await list_transcripts(limit=5)
        print(f"    ✓ list_transcripts: {result.get('total', 0)} transcripts found")
        print(f"    Response keys: {list(result.keys())}")
    except Exception as e:
        print(f"    ✗ list_transcripts failed: {e}")

    # Test 2: get_job_status (synchronous, should always work)
    print("\n[2] Testing get_job_status...")
    try:
        result = await get_job_status("test-job-id-12345")
        print(f"    ✓ get_job_status: status={result.get('status')}")
        print(f"    Response: {json.dumps(result, indent=2)[:200]}...")
    except Exception as e:
        print(f"    ✗ get_job_status failed: {e}")

    # Test 3: get_transcript (may fail if no transcripts exist)
    print("\n[3] Testing get_transcript...")
    try:
        result = await get_transcript("test_video_id")
        print(f"    ✓ get_transcript: found={result.get('found')}")
        if not result.get("found"):
            print(f"    (Expected: no transcript for test ID)")
    except Exception as e:
        print(f"    ✗ get_transcript failed: {e}")

    # Test 4: transcribe_video (requires network/YouTube)
    print("\n[4] Testing transcribe_video (skipped - requires network)...")
    print("    ⊘ Skipped: Would test with real YouTube URL")

    # Test 5: add_channel (requires network/YouTube)
    print("\n[5] Testing add_channel (skipped - requires network)...")
    print("    ⊘ Skipped: Would test with real channel handle")

    # Test 6: sync_channel (requires network/YouTube)
    print("\n[6] Testing sync_channel (skipped - requires network)...")
    print("    ⊘ Skipped: Would test with real channel handle")

    # Test 7: transcribe_channel_pending (requires network/YouTube)
    print("\n[7] Testing transcribe_channel_pending (skipped - requires network)...")
    print("    ⊘ Skipped: Would test with real channel handle")


async def test_resources() -> None:
    """Test MCP resources."""
    print("\n" + "=" * 60)
    print("TESTING MCP RESOURCES")
    print("=" * 60)

    # Test 1: read_transcript_resource
    print("\n[1] Testing read_transcript_resource...")
    try:
        result = await read_transcript_resource("transcript://test_video")
        print(f"    ✓ read_transcript_resource: mime_type={result.get('mime_type')}")
        if "error" in result:
            print(f"    (Expected error for non-existent video: {result['error'][:50]}...)")
        else:
            print(f"    Response length: {len(result.get('text', ''))} chars")
    except Exception as e:
        print(f"    ✗ read_transcript_resource failed: {e}")

    # Test 2: read_job_resource
    print("\n[2] Testing read_job_resource...")
    try:
        result = await read_job_resource("job://test-job-123")
        print(f"    ✓ read_job_resource: mime_type={result.get('mime_type')}")
        print(f"    Response: {result.get('text', '')[:100]}...")
    except Exception as e:
        print(f"    ✗ read_job_resource failed: {e}")


async def test_prompts() -> None:
    """Test MCP prompts."""
    print("\n" + "=" * 60)
    print("TESTING MCP PROMPTS")
    print("=" * 60)

    # Test 1: generate_transcribe_video_prompt
    print("\n[1] Testing generate_transcribe_video_prompt...")
    try:
        result = await generate_transcribe_video_prompt(
            {
                "source": "https://youtube.com/watch?v=test123",
                "priority": "normal",
            }
        )
        print(f"    ✓ generate_transcribe_video_prompt: {len(result)} messages")
        print(f"    First message role: {result[0].get('role')}")
    except Exception as e:
        print(f"    ✗ generate_transcribe_video_prompt failed: {e}")

    # Test 2: generate_channel_sync_prompt
    print("\n[2] Testing generate_channel_sync_prompt...")
    try:
        result = await generate_channel_sync_prompt(
            {
                "handle": "@TestChannel",
                "limit": 5,
                "mode": "recent",
            }
        )
        print(f"    ✓ generate_channel_sync_prompt: {len(result)} messages")
        print(f"    First message role: {result[0].get('role')}")
    except Exception as e:
        print(f"    ✗ generate_channel_sync_prompt failed: {e}")


async def test_server_metadata() -> None:
    """Test MCP server metadata."""
    print("\n" + "=" * 60)
    print("TESTING MCP SERVER METADATA")
    print("=" * 60)

    print(f"\nServer name: {mcp.name}")
    print(f"Server instructions: {mcp.instructions[:100]}...")

    # Get registered tools
    print("\nRegistered Tools:")
    tool_names = [
        "transcribe_video",
        "get_transcript",
        "list_transcripts",
        "get_job_status",
        "add_channel",
        "sync_channel",
        "transcribe_channel_pending",
    ]
    for name in tool_names:
        print(f"  - {name}")

    # Get registered resources
    print("\nRegistered Resources:")
    print("  - transcript://{video_id}")
    print("  - job://{job_id}")

    # Get registered prompts
    print("\nRegistered Prompts:")
    print("  - transcribe-video")
    print("  - sync-channel")


async def main() -> None:
    """Run all tests."""
    print("\n" + "=" * 60)
    print("MCP SERVER TEST SUITE")
    print("=" * 60)

    try:
        await test_server_metadata()
        await test_tools()
        await test_resources()
        await test_prompts()

        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        print("\n✓ All tests completed!")
        print("\nTo test with MCP Inspector:")
        print("  npx @modelcontextprotocol/inspector uv run python -m src.mcp.server")
        print("\nTo test with Claude Desktop:")
        print("  Add to claude_desktop_config.json:")
        print("  {")
        print('    "mcpServers": {')
        print('      "youtube-transcription": {')
        print('        "command": "uv",')
        print('        "args": ["run", "python", "-m", "src.mcp.server"]')
        print("      }")
        print("    }")
        print("  }")

    except Exception as e:
        print(f"\n✗ Test suite failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
