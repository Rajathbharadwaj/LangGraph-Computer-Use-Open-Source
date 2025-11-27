"""
Debug script for testing comment_on_post functionality step-by-step.

This script will:
1. Launch a Patchright browser session
2. Navigate to X.com (you'll need to login manually)
3. Test each step of the comment process individually
4. Log detailed success/failure for each step
"""

import asyncio
from patchright.async_api import async_playwright
import sys


async def debug_comment_on_post():
    print("🚀 Starting Patchright debugging session...\n")

    async with async_playwright() as p:
        # Launch browser with GUI so user can login
        print("📱 Launching browser...")
        browser = await p.chromium.launch(
            headless=False,  # Show browser window
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
            ]
        )

        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )

        page = await context.new_page()

        # Navigate to X.com
        print("🌐 Navigating to X.com...")
        await page.goto('https://x.com/home', wait_until='networkidle')

        print("\n" + "="*60)
        print("⏸️  MANUAL STEP: Please login to X.com if not already logged in")
        print("   Press ENTER when you're on the home timeline...")
        print("="*60 + "\n")
        input()

        # Ask user for a post URL to test
        print("\n" + "="*60)
        print("📍 Please provide a post URL to test commenting on:")
        print("   Example: https://x.com/username/status/1234567890")
        print("="*60)
        post_url = input("Post URL: ").strip()

        if not post_url:
            print("❌ No URL provided. Exiting.")
            await browser.close()
            return

        # Navigate to the post
        print(f"\n🔗 Navigating to post: {post_url}")
        await page.goto(post_url, wait_until='networkidle')
        await asyncio.sleep(2)

        # Get comment text
        print("\n" + "="*60)
        comment_text = input("💬 Enter comment text to post: ").strip()
        if not comment_text:
            comment_text = "Great post! 🚀"
            print(f"   Using default: {comment_text}")
        print("="*60 + "\n")

        # Step 1: Find and click reply button
        print("=" * 60)
        print("STEP 1: Finding reply button...")
        print("=" * 60)

        try:
            # Try different selectors for reply button
            selectors = [
                '[data-testid="reply"]',
                '[aria-label*="Reply"]',
                'button[aria-label*="Reply"]',
            ]

            reply_button = None
            for selector in selectors:
                try:
                    reply_button = await page.wait_for_selector(selector, timeout=3000)
                    if reply_button:
                        print(f"✅ Found reply button with selector: {selector}")
                        break
                except:
                    print(f"⏭️  Selector '{selector}' not found, trying next...")

            if not reply_button:
                print("❌ FAILED: Could not find reply button")
                await browser.close()
                return

            print("🖱️  Clicking reply button...")
            await reply_button.click()
            await asyncio.sleep(1.5)
            print("✅ Reply button clicked successfully\n")

        except Exception as e:
            print(f"❌ FAILED at Step 1: {str(e)}\n")
            await browser.close()
            return

        # Step 2: Wait for reply dialog to appear
        print("=" * 60)
        print("STEP 2: Waiting for reply dialog...")
        print("=" * 60)

        try:
            dialog = await page.wait_for_selector('[role="dialog"]', timeout=5000)
            if dialog:
                print("✅ Reply dialog appeared\n")
            else:
                print("❌ FAILED: Reply dialog did not appear\n")
                await browser.close()
                return
        except Exception as e:
            print(f"❌ FAILED at Step 2: {str(e)}\n")
            await browser.close()
            return

        # Step 3: Find textarea in dialog
        print("=" * 60)
        print("STEP 3: Finding textarea in dialog...")
        print("=" * 60)

        try:
            textarea_selectors = [
                '[data-testid="tweetTextarea_0"]',
                '[role="dialog"] [data-testid="tweetTextarea_0"]',
                '[role="textbox"]',
                '[contenteditable="true"][data-testid="tweetTextarea_0"]',
            ]

            textarea = None
            for selector in textarea_selectors:
                try:
                    textarea = await page.wait_for_selector(selector, timeout=3000)
                    if textarea:
                        print(f"✅ Found textarea with selector: {selector}")
                        break
                except:
                    print(f"⏭️  Selector '{selector}' not found, trying next...")

            if not textarea:
                print("❌ FAILED: Could not find textarea")
                await browser.close()
                return

            # Check if textarea is visible and enabled
            is_visible = await textarea.is_visible()
            is_enabled = await textarea.is_enabled()
            print(f"   Visible: {is_visible}, Enabled: {is_enabled}\n")

        except Exception as e:
            print(f"❌ FAILED at Step 3: {str(e)}\n")
            await browser.close()
            return

        # Step 4: Focus on textarea
        print("=" * 60)
        print("STEP 4: Focusing on textarea...")
        print("=" * 60)

        try:
            await textarea.click()
            await asyncio.sleep(0.5)
            print("✅ Textarea focused\n")
        except Exception as e:
            print(f"❌ FAILED at Step 4: {str(e)}\n")
            await browser.close()
            return

        # Step 5: Type comment - METHOD TEST
        print("=" * 60)
        print("STEP 5: Testing different typing methods...")
        print("=" * 60)

        # Ask user which method to test
        print("\nWhich method would you like to test?")
        print("1. Playwright .type() with 50ms delay (recommended)")
        print("2. Playwright .type() with 100ms delay")
        print("3. Playwright .fill()")
        print("4. Playwright .press_sequentially()")
        print("5. JavaScript insertText")
        print("6. JavaScript value setter")

        method = input("\nEnter method number (1-6): ").strip() or "1"

        try:
            if method == "1":
                print("\n🔤 Method 1: .type() with 50ms delay")
                await textarea.type(comment_text, delay=50)

            elif method == "2":
                print("\n🔤 Method 2: .type() with 100ms delay")
                await textarea.type(comment_text, delay=100)

            elif method == "3":
                print("\n🔤 Method 3: .fill()")
                await textarea.fill(comment_text)

            elif method == "4":
                print("\n🔤 Method 4: .press_sequentially()")
                await textarea.press_sequentially(comment_text, delay=50)

            elif method == "5":
                print("\n🔤 Method 5: JavaScript insertText")
                await page.evaluate(f"""
                    const textarea = document.querySelector('[data-testid="tweetTextarea_0"]');
                    textarea.focus();
                    document.execCommand('insertText', false, '{comment_text}');
                """)

            elif method == "6":
                print("\n🔤 Method 6: JavaScript value setter + input event")
                await page.evaluate(f"""
                    const textarea = document.querySelector('[data-testid="tweetTextarea_0"]');
                    textarea.focus();
                    textarea.textContent = '{comment_text}';
                    textarea.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    textarea.dispatchEvent(new Event('change', {{ bubbles: true }}));
                """)

            await asyncio.sleep(1)

            # Verify text was entered
            current_text = await page.evaluate("""
                document.querySelector('[data-testid="tweetTextarea_0"]')?.textContent || ''
            """)

            if comment_text in current_text:
                print(f"✅ Text successfully entered: '{current_text}'\n")
            else:
                print(f"⚠️  Text in textarea: '{current_text}'")
                print(f"   Expected: '{comment_text}'\n")

        except Exception as e:
            print(f"❌ FAILED at Step 5: {str(e)}\n")
            await browser.close()
            return

        # Step 6: Find submit button
        print("=" * 60)
        print("STEP 6: Finding submit button...")
        print("=" * 60)

        try:
            submit_selectors = [
                '[role="dialog"] [data-testid="tweetButton"]',
                '[data-testid="tweetButton"]',
                '[role="dialog"] button[data-testid="tweetButtonInline"]',
            ]

            submit_button = None
            for selector in submit_selectors:
                try:
                    submit_button = await page.wait_for_selector(selector, timeout=3000)
                    if submit_button:
                        is_disabled = await submit_button.get_attribute('disabled')
                        print(f"✅ Found submit button with selector: {selector}")
                        print(f"   Disabled: {is_disabled is not None}\n")
                        break
                except:
                    print(f"⏭️  Selector '{selector}' not found, trying next...")

            if not submit_button:
                print("❌ FAILED: Could not find submit button")
                await browser.close()
                return

        except Exception as e:
            print(f"❌ FAILED at Step 6: {str(e)}\n")
            await browser.close()
            return

        # Step 7: Ask user if they want to click submit
        print("=" * 60)
        print("⚠️  READY TO SUBMIT COMMENT")
        print("=" * 60)
        print(f"\nComment text: '{comment_text}'")
        submit_confirm = input("\nPress ENTER to click submit (or 'n' to skip): ").strip().lower()

        if submit_confirm != 'n':
            try:
                print("\n🖱️  Clicking submit button...")
                await submit_button.click()
                await asyncio.sleep(2)
                print("✅ Submit button clicked\n")

                # Check if dialog closed (indicates success)
                dialog_exists = await page.query_selector('[role="dialog"]')
                if dialog_exists:
                    print("⚠️  Dialog still open - comment may not have posted")
                else:
                    print("✅ Dialog closed - comment likely posted successfully!")

            except Exception as e:
                print(f"❌ FAILED at Step 7: {str(e)}\n")
        else:
            print("⏭️  Skipped submit step\n")

        print("\n" + "=" * 60)
        print("✅ DEBUGGING COMPLETE")
        print("=" * 60)
        print("\nPress ENTER to close browser...")
        input()

        await browser.close()


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("🔍 X.com Comment Debugging Tool")
    print("=" * 60 + "\n")

    asyncio.run(debug_comment_on_post())
