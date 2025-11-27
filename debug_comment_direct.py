"""
Direct Playwright Comment Debugging

This script directly uses the existing Playwright client from async_playwright_tools.py
to test commenting step-by-step on X.com
"""

import asyncio
import sys
import os

# Add current directory to path to import async_playwright_tools
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from async_playwright_tools import _global_client, ensure_patchright_session


async def debug_comment():
    print("\n" + "=" * 70)
    print("🔍 Direct Playwright Comment Debugging")
    print("=" * 70)
    print("\nThis script uses the existing Patchright session.")
    print("Make sure you're on X.com with a post open.\n")

    # Ensure Playwright session is initialized
    print("🔌 Initializing Patchright session...")
    await ensure_patchright_session()

    if not _global_client or not _global_client.page:
        print("❌ Patchright session not available")
        return

    page = _global_client.page

    print("✅ Connected to Patchright session\n")

    # Get current URL
    current_url = await page.evaluate("window.location.href")
    print(f"📍 Current URL: {current_url}")

    if "x.com" not in current_url and "twitter.com" not in current_url:
        print("\n⚠️  Not on X.com. Please navigate to a post on X.com")
        return

    # Get comment text
    comment_text = input("\n💬 Enter comment text to test (or press Enter for default): ").strip()
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
        'div[role="button"][aria-label*="Reply"]',
    ]

    found_selector = None
    for selector in selectors_to_test:
        try:
            exists = await page.query_selector(selector)
            status = "✅ FOUND" if exists else "❌ Not found"
            print(f"   {selector:50s} ... {status}")
            if exists and not found_selector:
                found_selector = selector
        except Exception as e:
            print(f"   {selector:50s} ... ⚠️  Error: {e}")

    if not found_selector:
        print("\n❌ Could not find reply button")
        return

    print(f"\n✅ Using selector: {found_selector}")

    # Click reply button
    proceed = input("\nPress ENTER to click reply button (or 'n' to exit): ").strip().lower()
    if proceed == 'n':
        return

    try:
        print("\n🖱️  Clicking reply button...")
        await page.click(found_selector)
        await asyncio.sleep(1.5)
        print("✅ Reply button clicked")
    except Exception as e:
        print(f"❌ Failed to click: {e}")
        return

    # STEP 2: Check for dialog
    print("\n" + "=" * 70)
    print("STEP 2: Checking for reply dialog...")
    print("=" * 70)

    dialog = await page.query_selector('[role="dialog"]')
    if dialog:
        print("✅ Reply dialog appeared")
    else:
        print("❌ Reply dialog did not appear")
        return

    # STEP 3: Find textarea
    print("\n" + "=" * 70)
    print("STEP 3: Finding textarea in dialog...")
    print("=" * 70)

    textarea_selectors = [
        '[data-testid="tweetTextarea_0"]',
        '[role="dialog"] [data-testid="tweetTextarea_0"]',
        '[role="textbox"]',
        '[contenteditable="true"]',
    ]

    textarea_selector = None
    for selector in textarea_selectors:
        try:
            exists = await page.query_selector(selector)
            status = "✅ FOUND" if exists else "❌ Not found"
            print(f"   {selector:50s} ... {status}")
            if exists and not textarea_selector:
                textarea_selector = selector
        except Exception as e:
            print(f"   {selector:50s} ... ⚠️  Error: {e}")

    if not textarea_selector:
        print("\n❌ Could not find textarea")
        return

    print(f"\n✅ Using selector: {textarea_selector}")

    # Focus textarea
    print("\n🖱️  Focusing textarea...")
    await page.click(textarea_selector)
    await asyncio.sleep(0.5)

    # STEP 4: Test typing methods
    print("\n" + "=" * 70)
    print("STEP 4: Testing typing methods...")
    print("=" * 70)
    print("\nWhich method would you like to test?")
    print("1. Playwright .type() with 50ms delay")
    print("2. Playwright .type() with 100ms delay")
    print("3. Playwright .fill()")
    print("4. Playwright .press_sequentially()")
    print("5. JavaScript insertText (execCommand)")
    print("6. JavaScript textContent + input event")
    print("7. JavaScript innerText + InputEvent")
    print("8. Keyboard.type() character by character")

    method = input("\nEnter method number (1-8): ").strip() or "1"

    try:
        if method == "1":
            print("\n🔤 Method 1: .type() with 50ms delay")
            await page.type(textarea_selector, comment_text, delay=50)

        elif method == "2":
            print("\n🔤 Method 2: .type() with 100ms delay")
            await page.type(textarea_selector, comment_text, delay=100)

        elif method == "3":
            print("\n🔤 Method 3: .fill()")
            await page.fill(textarea_selector, comment_text)

        elif method == "4":
            print("\n🔤 Method 4: .press_sequentially()")
            textarea_elem = await page.query_selector(textarea_selector)
            await textarea_elem.press_sequentially(comment_text, delay=50)

        elif method == "5":
            print("\n🔤 Method 5: JavaScript insertText (execCommand)")
            await page.evaluate(f"""
                const textarea = document.querySelector('{textarea_selector}');
                textarea.focus();
                document.execCommand('insertText', false, `{comment_text}`);
            """)

        elif method == "6":
            print("\n🔤 Method 6: JavaScript textContent + input event")
            await page.evaluate(f"""
                const textarea = document.querySelector('{textarea_selector}');
                textarea.focus();
                textarea.textContent = `{comment_text}`;
                textarea.dispatchEvent(new Event('input', {{ bubbles: true }}));
                textarea.dispatchEvent(new Event('change', {{ bubbles: true }}));
            """)

        elif method == "7":
            print("\n🔤 Method 7: JavaScript innerText + InputEvent")
            await page.evaluate(f"""
                const textarea = document.querySelector('{textarea_selector}');
                textarea.focus();
                textarea.innerText = `{comment_text}`;
                const inputEvent = new InputEvent('input', {{
                    bubbles: true,
                    inputType: 'insertText',
                    data: `{comment_text}`
                }});
                textarea.dispatchEvent(inputEvent);
            """)

        elif method == "8":
            print("\n🔤 Method 8: Keyboard.type() character by character")
            for char in comment_text:
                await page.keyboard.press(char)
                await asyncio.sleep(0.05)

        await asyncio.sleep(1)

        # Verify text
        print("\n🔍 Verifying text was entered...")
        current_text = await page.evaluate(f"""
            document.querySelector('{textarea_selector}')?.textContent || ''
        """)

        if comment_text in current_text:
            print(f"✅ Text successfully entered!")
            print(f"   Content: '{current_text}'")
        else:
            print(f"⚠️  Text mismatch")
            print(f"   Expected: '{comment_text}'")
            print(f"   Got:      '{current_text}'")

    except Exception as e:
        print(f"❌ Typing failed: {e}")
        return

    # STEP 5: Check submit button
    print("\n" + "=" * 70)
    print("STEP 5: Checking submit button...")
    print("=" * 70)

    submit_selectors = [
        '[role="dialog"] [data-testid="tweetButton"]',
        '[data-testid="tweetButton"]',
        '[role="dialog"] button[data-testid="tweetButtonInline"]',
    ]

    submit_selector = None
    for selector in submit_selectors:
        try:
            exists = await page.query_selector(selector)
            status = "✅ FOUND" if exists else "❌ Not found"
            print(f"   {selector:50s} ... {status}")
            if exists and not submit_selector:
                submit_selector = selector
        except Exception as e:
            print(f"   {selector:50s} ... ⚠️  Error: {e}")

    if not submit_selector:
        print("\n❌ Could not find submit button")
        return

    # Check if disabled
    is_disabled = await page.evaluate(f"""
        const btn = document.querySelector('{submit_selector}');
        btn?.disabled || btn?.getAttribute('aria-disabled') === 'true'
    """)

    print(f"\n   Submit button disabled: {is_disabled}")

    # STEP 6: Submit
    print("\n" + "=" * 70)
    print("STEP 6: Submit comment")
    print("=" * 70)

    submit_confirm = input("\n⚠️  Press ENTER to click submit (or 'n' to skip): ").strip().lower()

    if submit_confirm != 'n':
        try:
            print("\n🖱️  Clicking submit button...")
            await page.click(submit_selector)
            await asyncio.sleep(2)
            print("✅ Submit clicked")

            # Check if dialog closed
            dialog_still_exists = await page.query_selector('[role="dialog"]')
            if not dialog_still_exists:
                print("✅ Dialog closed - Comment posted successfully!")
            else:
                print("⚠️  Dialog still open - Comment may not have posted")

        except Exception as e:
            print(f"❌ Submit failed: {e}")
    else:
        print("⏭️  Skipped submit")

    print("\n" + "=" * 70)
    print("✅ DEBUGGING COMPLETE")
    print("=" * 70)
    print("\nIf a method worked, we'll update async_playwright_tools.py to use it.")


if __name__ == "__main__":
    asyncio.run(debug_comment())
