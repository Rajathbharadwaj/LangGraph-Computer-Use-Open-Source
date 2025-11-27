"""
Interactive Comment Debugging - Connect to existing Playwright session

This script connects to your existing Playwright server and lets you
interactively test the comment functionality step-by-step.

You navigate to X.com and a post manually, then I'll test each step.
"""

import asyncio
import aiohttp
import json


class PlaywrightClient:
    def __init__(self, base_url="http://localhost:8002"):
        self.base_url = base_url
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()

    async def _request(self, method, endpoint, data=None):
        """Make request to Playwright server"""
        url = f"{self.base_url}{endpoint}"

        try:
            async with self.session.request(method, url, json=data) as response:
                result = await response.json()
                return result
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_current_url(self):
        """Get current page URL"""
        result = await self._request("POST", "/playwright/evaluate", {
            "expression": "window.location.href"
        })
        return result.get("result")

    async def get_page_title(self):
        """Get current page title"""
        result = await self._request("POST", "/playwright/evaluate", {
            "expression": "document.title"
        })
        return result.get("result")

    async def click(self, selector, timeout=5000):
        """Click an element"""
        result = await self._request("POST", "/playwright/click", {
            "selector": selector,
            "timeout": timeout
        })
        return result

    async def type_text(self, selector, text, delay=50, timeout=5000):
        """Type text into an element"""
        result = await self._request("POST", "/playwright/type", {
            "selector": selector,
            "text": text,
            "delay": delay,
            "timeout": timeout
        })
        return result

    async def fill(self, selector, text, timeout=5000):
        """Fill an element (fast)"""
        result = await self._request("POST", "/playwright/fill", {
            "selector": selector,
            "text": text,
            "timeout": timeout
        })
        return result

    async def evaluate(self, expression):
        """Execute JavaScript"""
        result = await self._request("POST", "/playwright/evaluate", {
            "expression": expression
        })
        return result

    async def wait_for_selector(self, selector, timeout=5000):
        """Wait for selector to appear"""
        result = await self._request("POST", "/playwright/wait_for_selector", {
            "selector": selector,
            "timeout": timeout
        })
        return result

    async def query_selector(self, selector):
        """Check if selector exists"""
        result = await self.evaluate(f"!!document.querySelector('{selector}')")
        return result.get("result", False)


async def interactive_debug():
    print("\n" + "=" * 70)
    print("🔍 Interactive Comment Debugging Tool")
    print("=" * 70)
    print("\nThis tool connects to your existing Playwright session.")
    print("Make sure backend_websocket_server.py is running on port 8002.\n")

    async with PlaywrightClient() as client:
        # Check connection
        print("🔌 Testing connection to Playwright server...")
        url = await client.get_current_url()

        if not url:
            print("❌ Could not connect to Playwright server.")
            print("   Make sure backend_websocket_server.py is running.")
            return

        print(f"✅ Connected! Current URL: {url}\n")

        # Check if on X.com
        if "x.com" not in url and "twitter.com" not in url:
            print("⚠️  You're not on X.com")
            print("   Please navigate to X.com and a specific post in your browser.")
            print("   Then run this script again.\n")
            return

        print("=" * 70)
        print("📍 CURRENT PAGE INFO")
        print("=" * 70)
        title = await client.get_page_title()
        print(f"Title: {title}")
        print(f"URL: {url}\n")

        # Check if on a post
        if "/status/" not in url:
            print("⚠️  You don't appear to be on a specific post.")
            print("   Please navigate to a post (URL should contain /status/)")
            print("   Then run this script again.\n")
            return

        print("✅ You're on a post! Let's start debugging...\n")

        # Get comment text
        comment_text = input("💬 Enter comment text to test (or press Enter for default): ").strip()
        if not comment_text:
            comment_text = "Great post! 🚀"
            print(f"   Using default: {comment_text}\n")

        # STEP 1: Find reply button
        print("\n" + "=" * 70)
        print("STEP 1: Finding reply button...")
        print("=" * 70)

        selectors_to_test = [
            '[data-testid="reply"]',
            '[aria-label*="Reply"]',
            'button[aria-label*="Reply"]',
        ]

        found_selector = None
        for selector in selectors_to_test:
            exists = await client.query_selector(selector)
            print(f"   Testing: {selector} ... {'✅ FOUND' if exists else '❌ Not found'}")
            if exists and not found_selector:
                found_selector = selector

        if not found_selector:
            print("\n❌ Could not find reply button. X.com may have changed selectors.")
            return

        print(f"\n✅ Will use selector: {found_selector}")

        proceed = input("\nPress ENTER to click reply button (or 'n' to skip): ").strip().lower()
        if proceed != 'n':
            result = await client.click(found_selector)
            if result.get("success"):
                print("✅ Reply button clicked!")
                await asyncio.sleep(1.5)
            else:
                print(f"❌ Failed to click: {result.get('error')}")
                return

        # STEP 2: Wait for dialog
        print("\n" + "=" * 70)
        print("STEP 2: Checking for reply dialog...")
        print("=" * 70)

        dialog_exists = await client.query_selector('[role="dialog"]')
        print(f"   Dialog exists: {'✅ YES' if dialog_exists else '❌ NO'}")

        if not dialog_exists:
            print("\n❌ Reply dialog did not appear.")
            return

        # STEP 3: Find textarea
        print("\n" + "=" * 70)
        print("STEP 3: Finding textarea...")
        print("=" * 70)

        textarea_selectors = [
            '[data-testid="tweetTextarea_0"]',
            '[role="dialog"] [data-testid="tweetTextarea_0"]',
            '[role="textbox"]',
        ]

        textarea_selector = None
        for selector in textarea_selectors:
            exists = await client.query_selector(selector)
            print(f"   Testing: {selector} ... {'✅ FOUND' if exists else '❌ Not found'}")
            if exists and not textarea_selector:
                textarea_selector = selector

        if not textarea_selector:
            print("\n❌ Could not find textarea.")
            return

        print(f"\n✅ Will use selector: {textarea_selector}")

        # STEP 4: Test different typing methods
        print("\n" + "=" * 70)
        print("STEP 4: Testing typing methods...")
        print("=" * 70)
        print("\nWhich method would you like to test?")
        print("1. Playwright .type() with 50ms delay")
        print("2. Playwright .type() with 100ms delay")
        print("3. Playwright .fill() (fast)")
        print("4. JavaScript insertText")
        print("5. JavaScript textContent + events")
        print("6. JavaScript innerText + events")

        method = input("\nEnter method number (1-6): ").strip() or "1"

        # First, click/focus the textarea
        print(f"\n🖱️  Clicking textarea to focus...")
        await client.click(textarea_selector)
        await asyncio.sleep(0.5)

        if method == "1":
            print(f"\n🔤 Method 1: .type() with 50ms delay")
            result = await client.type_text(textarea_selector, comment_text, delay=50)

        elif method == "2":
            print(f"\n🔤 Method 2: .type() with 100ms delay")
            result = await client.type_text(textarea_selector, comment_text, delay=100)

        elif method == "3":
            print(f"\n🔤 Method 3: .fill()")
            result = await client.fill(textarea_selector, comment_text)

        elif method == "4":
            print(f"\n🔤 Method 4: JavaScript insertText")
            result = await client.evaluate(f"""
                const textarea = document.querySelector('{textarea_selector}');
                textarea.focus();
                document.execCommand('insertText', false, `{comment_text}`);
                true
            """)

        elif method == "5":
            print(f"\n🔤 Method 5: JavaScript textContent + events")
            result = await client.evaluate(f"""
                const textarea = document.querySelector('{textarea_selector}');
                textarea.focus();
                textarea.textContent = `{comment_text}`;
                textarea.dispatchEvent(new Event('input', {{ bubbles: true }}));
                textarea.dispatchEvent(new Event('change', {{ bubbles: true }}));
                true
            """)

        elif method == "6":
            print(f"\n🔤 Method 6: JavaScript innerText + events")
            result = await client.evaluate(f"""
                const textarea = document.querySelector('{textarea_selector}');
                textarea.focus();
                textarea.innerText = `{comment_text}`;
                textarea.dispatchEvent(new InputEvent('input', {{ bubbles: true, inputType: 'insertText', data: `{comment_text}` }}));
                true
            """)

        if result.get("success") or result.get("result"):
            print("✅ Typing method executed")
        else:
            print(f"⚠️  Typing may have failed: {result.get('error', 'Unknown error')}")

        await asyncio.sleep(1)

        # Verify text
        print("\n🔍 Verifying text was entered...")
        verify_result = await client.evaluate(f"""
            document.querySelector('{textarea_selector}')?.textContent || ''
        """)
        current_text = verify_result.get("result", "")

        if comment_text in current_text:
            print(f"✅ Text successfully entered: '{current_text}'")
        else:
            print(f"⚠️  Text in textarea: '{current_text}'")
            print(f"   Expected: '{comment_text}'")

        # STEP 5: Check submit button
        print("\n" + "=" * 70)
        print("STEP 5: Checking submit button...")
        print("=" * 70)

        submit_selectors = [
            '[role="dialog"] [data-testid="tweetButton"]',
            '[data-testid="tweetButton"]',
        ]

        submit_selector = None
        for selector in submit_selectors:
            exists = await client.query_selector(selector)
            print(f"   Testing: {selector} ... {'✅ FOUND' if exists else '❌ Not found'}")
            if exists and not submit_selector:
                submit_selector = selector

        if not submit_selector:
            print("\n❌ Could not find submit button.")
            return

        # Check if button is disabled
        is_disabled = await client.evaluate(f"""
            document.querySelector('{submit_selector}')?.disabled ||
            document.querySelector('{submit_selector}')?.getAttribute('aria-disabled') === 'true'
        """)

        print(f"\n   Submit button disabled: {is_disabled.get('result', 'Unknown')}")

        # STEP 6: Submit
        print("\n" + "=" * 70)
        print("STEP 6: Submit comment")
        print("=" * 70)

        submit_confirm = input("\n⚠️  Press ENTER to click submit (or 'n' to skip): ").strip().lower()

        if submit_confirm != 'n':
            print("\n🖱️  Clicking submit button...")
            result = await client.click(submit_selector)

            if result.get("success"):
                print("✅ Submit clicked!")
                await asyncio.sleep(2)

                # Check if dialog closed
                dialog_still_exists = await client.query_selector('[role="dialog"]')
                if not dialog_still_exists:
                    print("✅ Dialog closed - Comment likely posted!")
                else:
                    print("⚠️  Dialog still open - Comment may not have posted")
            else:
                print(f"❌ Failed to click submit: {result.get('error')}")
        else:
            print("⏭️  Skipped submit")

        print("\n" + "=" * 70)
        print("✅ DEBUGGING COMPLETE")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(interactive_debug())
