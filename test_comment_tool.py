"""
Test the comment_on_post tool in isolation
"""

import asyncio
import sys

# Import the tool
from async_playwright_tools import create_async_playwright_tools

async def test_comment():
    print("\n" + "="*70)
    print("🧪 Testing comment_on_post tool in isolation")
    print("="*70)

    # Get the tools
    tools = create_async_playwright_tools()

    # Find the comment tool
    comment_tool = None
    for tool in tools:
        if hasattr(tool, 'name') and tool.name == 'comment_on_post':
            comment_tool = tool
            break

    if not comment_tool:
        print("❌ Could not find comment_on_post tool")
        return

    print(f"✅ Found tool: {comment_tool.name}")
    print(f"📝 Description: {comment_tool.description}\n")

    # Get input from user
    author_or_content = input("Enter author handle or post content to comment on: ").strip()
    if not author_or_content:
        author_or_content = "@chloetaylor"
        print(f"Using default: {author_or_content}")

    comment_text = input("Enter comment text: ").strip()
    if not comment_text:
        comment_text = "Great post! 🚀"
        print(f"Using default: {comment_text}")

    print("\n" + "="*70)
    print("🚀 Invoking comment_on_post tool...")
    print("="*70)
    print(f"Target: {author_or_content}")
    print(f"Comment: {comment_text}\n")

    # Invoke the tool
    try:
        result = await comment_tool.ainvoke({
            "author_or_content": author_or_content,
            "comment_text": comment_text
        })

        print("\n" + "="*70)
        print("📊 RESULT:")
        print("="*70)
        print(result)
        print("="*70)

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_comment())
