"""
Simple test script to try different comment methods using the existing tools

This just makes a simple HTTP request to test commenting
"""

import asyncio
import requests

# Test using the agent to comment with different methods
def test_comment_via_agent(post_url: str, comment_text: str):
    """
    Test commenting by asking the agent to do it
    """
    print(f"\n{'='*70}")
    print(f"Testing comment on: {post_url}")
    print(f"Comment text: {comment_text}")
    print(f"{'='*70}\n")

    # The agent will use whatever method is currently in async_playwright_tools.py
    # We'll modify that file to test different methods

    print("To test different methods:")
    print("1. I'll modify async_playwright_tools.py with a specific method")
    print("2. Restart backend_websocket_server.py")
    print("3. Use the frontend to ask agent to comment")
    print("4. Check if it works")
    print("\nWhich method do you want to test?")
    print("1. .type() with 50ms delay (current)")
    print("2. .type() with 100ms delay")
    print("3. .fill()")
    print("4. .press_sequentially()")
    print("5. JavaScript insertText")
    print("6. JavaScript textContent + events")
    print("7. JavaScript innerText + InputEvent")

    return input("\nEnter method number (1-7): ").strip() or "1"


if __name__ == "__main__":
    print("\n" + "="*70)
    print("🧪 Comment Method Tester")
    print("="*70)
    print("\nThis will help us test different typing methods.")
    print("\nFirst, navigate to a post on X.com in your VNC viewer (localhost:5900)")

    input("\nPress ENTER when you're on a post...")

    post_url = input("\nEnter the post URL (or just the status ID): ").strip()
    comment_text = input("Enter comment text to test: ").strip() or "Testing comment 🚀"

    method = test_comment_via_agent(post_url, comment_text)

    print(f"\n✅ You selected method {method}")
    print("\nI'll now update async_playwright_tools.py to use this method...")
