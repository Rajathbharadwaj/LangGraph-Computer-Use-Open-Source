"""
Direct Tool Testing Script

Tests all X growth tools to verify they work:
- comment_on_post
- create_post_on_x
- like_post
- unlike_post

This sends tasks directly to the agent and checks if tools execute successfully.
"""

import asyncio
import sys
from langgraph_sdk import get_client

# LangGraph API URL
LANGGRAPH_URL = "http://localhost:8124"

# Graph name
GRAPH_NAME = "x_growth_deep_agent"

# User ID for testing
USER_ID = "test_tool_verification"


async def test_comment_tool():
    """Test if comment_on_post tool works"""
    print("\n" + "="*80)
    print("TEST 1: comment_on_post tool")
    print("="*80)

    client = get_client(url=LANGGRAPH_URL)

    # Create a thread
    thread = await client.threads.create()
    thread_id = thread["thread_id"]
    print(f"Created thread: {thread_id}")

    # Test task: Comment on a post
    task = "Comment 'This is amazing! 🚀' on @elonmusk's latest post about AI"

    print(f"\nTask: {task}")
    print("\nRunning agent...")

    try:
        # Stream the agent execution
        async for chunk in client.runs.stream(
            thread_id,
            GRAPH_NAME,
            input={"messages": [{"role": "user", "content": task}]},
            config={"configurable": {"user_id": USER_ID}},
            stream_mode=["messages"]
        ):
            # Print any messages from the agent
            if hasattr(chunk, 'data'):
                if isinstance(chunk.data, list) and len(chunk.data) > 0:
                    msg = chunk.data[0]
                    if isinstance(msg, dict) and msg.get('type') == 'ai':
                        content = msg.get('content', '')
                        if content and isinstance(content, str):
                            print(f"Agent: {content[:200]}...")

        # Check the final state
        state = await client.threads.get_state(thread_id)
        messages = state.get('values', {}).get('messages', [])

        # Look for tool calls in messages
        tool_calls_found = False
        comment_success = False

        for msg in messages:
            if isinstance(msg, dict):
                # Check if comment tool was called
                if msg.get('type') == 'tool':
                    if msg.get('name') in ['comment_on_post', '_styled_comment_on_post']:
                        tool_calls_found = True
                        output = str(msg.get('content', ''))
                        print(f"\n✅ Tool called: {msg.get('name')}")
                        print(f"Output: {output[:300]}...")

                        # Check for success
                        if 'successfully' in output.lower() or '✅' in output:
                            comment_success = True
                            print("✅ COMMENT TOOL WORKS!")
                        else:
                            print("❌ Comment may have failed - check output")

        if not tool_calls_found:
            print("⚠️  No comment tool call found in messages")

        return comment_success

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_post_tool():
    """Test if create_post_on_x tool works"""
    print("\n" + "="*80)
    print("TEST 2: create_post_on_x tool")
    print("="*80)

    client = get_client(url=LANGGRAPH_URL)

    # Create a thread
    thread = await client.threads.create()
    thread_id = thread["thread_id"]
    print(f"Created thread: {thread_id}")

    # Test task: Create a post
    task = "Create a post about how automated testing improves software quality"

    print(f"\nTask: {task}")
    print("\nRunning agent...")

    try:
        # Stream the agent execution
        async for chunk in client.runs.stream(
            thread_id,
            GRAPH_NAME,
            input={"messages": [{"role": "user", "content": task}]},
            config={"configurable": {"user_id": USER_ID}},
            stream_mode=["messages"]
        ):
            # Print any messages from the agent
            if hasattr(chunk, 'data'):
                if isinstance(chunk.data, list) and len(chunk.data) > 0:
                    msg = chunk.data[0]
                    if isinstance(msg, dict) and msg.get('type') == 'ai':
                        content = msg.get('content', '')
                        if content and isinstance(content, str):
                            print(f"Agent: {content[:200]}...")

        # Check the final state
        state = await client.threads.get_state(thread_id)
        messages = state.get('values', {}).get('messages', [])

        # Look for tool calls in messages
        tool_calls_found = False
        post_success = False

        for msg in messages:
            if isinstance(msg, dict):
                # Check if post tool was called
                if msg.get('type') == 'tool':
                    if msg.get('name') in ['create_post_on_x', '_styled_create_post_on_x']:
                        tool_calls_found = True
                        output = str(msg.get('content', ''))
                        print(f"\n✅ Tool called: {msg.get('name')}")
                        print(f"Output: {output[:300]}...")

                        # Check for success
                        if 'successfully' in output.lower() or '✅' in output:
                            post_success = True
                            print("✅ POST TOOL WORKS!")
                        else:
                            print("❌ Post may have failed - check output")

        if not tool_calls_found:
            print("⚠️  No post tool call found in messages")

        return post_success

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_like_tool():
    """Test if like_post tool works"""
    print("\n" + "="*80)
    print("TEST 3: like_post tool")
    print("="*80)

    client = get_client(url=LANGGRAPH_URL)

    # Create a thread
    thread = await client.threads.create()
    thread_id = thread["thread_id"]
    print(f"Created thread: {thread_id}")

    # Test task: Like a post
    task = "Like @elonmusk's latest post"

    print(f"\nTask: {task}")
    print("\nRunning agent...")

    try:
        # Stream the agent execution
        async for chunk in client.runs.stream(
            thread_id,
            GRAPH_NAME,
            input={"messages": [{"role": "user", "content": task}]},
            config={"configurable": {"user_id": USER_ID}},
            stream_mode=["messages"]
        ):
            # Print any messages from the agent
            if hasattr(chunk, 'data'):
                if isinstance(chunk.data, list) and len(chunk.data) > 0:
                    msg = chunk.data[0]
                    if isinstance(msg, dict) and msg.get('type') == 'ai':
                        content = msg.get('content', '')
                        if content and isinstance(content, str):
                            print(f"Agent: {content[:200]}...")

        # Check the final state
        state = await client.threads.get_state(thread_id)
        messages = state.get('values', {}).get('messages', [])

        # Look for tool calls in messages
        tool_calls_found = False
        like_success = False

        for msg in messages:
            if isinstance(msg, dict):
                # Check if like tool was called
                if msg.get('type') == 'tool':
                    if msg.get('name') == 'like_post':
                        tool_calls_found = True
                        output = str(msg.get('content', ''))
                        print(f"\n✅ Tool called: {msg.get('name')}")
                        print(f"Output: {output[:300]}...")

                        # Check for success
                        if 'successfully' in output.lower() or '✅' in output or '❤️' in output:
                            like_success = True
                            print("✅ LIKE TOOL WORKS!")
                        else:
                            print("❌ Like may have failed - check output")

        if not tool_calls_found:
            print("⚠️  No like tool call found in messages")

        return like_success

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_unlike_tool():
    """Test if unlike_post tool works"""
    print("\n" + "="*80)
    print("TEST 4: unlike_post tool")
    print("="*80)

    client = get_client(url=LANGGRAPH_URL)

    # Create a thread
    thread = await client.threads.create()
    thread_id = thread["thread_id"]
    print(f"Created thread: {thread_id}")

    # Test task: Unlike a post
    task = "Unlike @elonmusk's latest post (the one I just liked)"

    print(f"\nTask: {task}")
    print("\nRunning agent...")

    try:
        # Stream the agent execution
        async for chunk in client.runs.stream(
            thread_id,
            GRAPH_NAME,
            input={"messages": [{"role": "user", "content": task}]},
            config={"configurable": {"user_id": USER_ID}},
            stream_mode=["messages"]
        ):
            # Print any messages from the agent
            if hasattr(chunk, 'data'):
                if isinstance(chunk.data, list) and len(chunk.data) > 0:
                    msg = chunk.data[0]
                    if isinstance(msg, dict) and msg.get('type') == 'ai':
                        content = msg.get('content', '')
                        if content and isinstance(content, str):
                            print(f"Agent: {content[:200]}...")

        # Check the final state
        state = await client.threads.get_state(thread_id)
        messages = state.get('values', {}).get('messages', [])

        # Look for tool calls in messages
        tool_calls_found = False
        unlike_success = False

        for msg in messages:
            if isinstance(msg, dict):
                # Check if unlike tool was called
                if msg.get('type') == 'tool':
                    if msg.get('name') == 'unlike_post':
                        tool_calls_found = True
                        output = str(msg.get('content', ''))
                        print(f"\n✅ Tool called: {msg.get('name')}")
                        print(f"Output: {output[:300]}...")

                        # Check for success
                        if 'successfully' in output.lower() or '✅' in output:
                            unlike_success = True
                            print("✅ UNLIKE TOOL WORKS!")
                        else:
                            print("❌ Unlike may have failed - check output")

        if not tool_calls_found:
            print("⚠️  No unlike tool call found in messages")

        return unlike_success

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tool tests"""
    print("="*80)
    print("X GROWTH TOOLS - COMPREHENSIVE TEST SUITE")
    print("="*80)
    print("\nTesting all tools to verify they work correctly...")
    print("This will send real requests to X, so make sure you're logged in!\n")

    results = {
        "comment_on_post": False,
        "create_post_on_x": False,
        "like_post": False,
        "unlike_post": False
    }

    # Run tests sequentially (to avoid conflicts)
    results["comment_on_post"] = await test_comment_tool()
    await asyncio.sleep(2)  # Wait between tests

    results["create_post_on_x"] = await test_post_tool()
    await asyncio.sleep(2)

    results["like_post"] = await test_like_tool()
    await asyncio.sleep(2)

    results["unlike_post"] = await test_unlike_tool()

    # Print summary
    print("\n" + "="*80)
    print("TEST RESULTS SUMMARY")
    print("="*80)

    for tool, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{tool:25} {status}")

    # Overall result
    all_passed = all(results.values())
    print("\n" + "="*80)
    if all_passed:
        print("🎉 ALL TOOLS WORKING! Your X automation is ready!")
    else:
        print("⚠️  Some tools failed - check the output above for details")
        print("💡 Tip: Make sure you're logged into X via the browser automation")
    print("="*80)

    # Check LangSmith evaluators
    print("\n📊 Your LangSmith evaluators should now have feedback data!")
    print("Go to: https://smith.langchain.com/")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
