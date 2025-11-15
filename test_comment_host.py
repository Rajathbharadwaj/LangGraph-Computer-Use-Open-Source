"""
Test commenting on YOUR HOST MACHINE with Patchright

You'll login to X.com yourself, navigate to a post, then we test different comment methods.
"""

import asyncio
from patchright.async_api import async_playwright


async def main():
    print("\n" + "="*70)
    print("🧪 Comment Testing on Host Machine")
    print("="*70)
    print("\nLaunching Patchright browser on YOUR host machine...")
    print("You'll login to X.com and navigate to a post.\n")

    async with async_playwright() as p:
        # Launch visible browser on YOUR host machine
        browser = await p.chromium.launch(
            headless=False,
            args=[
                '--disable-blink-features=AutomationControlled',
            ]
        )

        context = await browser.new_context(
            viewport={'width': 1280, 'height': 900},
        )

        page = await context.new_page()

        # Navigate to X.com
        print("🌐 Navigating to X.com...")
        await page.goto('https://x.com/home')

        print("\n" + "="*70)
        print("⏸️  LOGIN AND NAVIGATE TO A POST")
        print("="*70)
        print("1. Login to X.com in the browser window")
        print("2. Navigate to ANY post you want to test commenting on")
        print("3. Come back here and press ENTER\n")
        input("Press ENTER when you're ready...")

        # Get current URL
        current_url = await page.evaluate("window.location.href")
        print(f"\n📍 Current URL: {current_url}")

        # Get comment text
        comment_text = input("\n💬 Enter comment text to test: ").strip()
        if not comment_text:
            comment_text = "Great post! 🚀"
            print(f"   Using default: {comment_text}")

        # Find reply button
        print("\n" + "="*70)
        print("STEP 1: Finding reply button...")
        print("="*70)

        reply_button = await page.query_selector('[data-testid="reply"]')
        if not reply_button:
            print("❌ Reply button not found. Are you on a post?")
            await browser.close()
            return

        print("✅ Found reply button")
        print("\n🖱️  Clicking reply button...")
        await reply_button.click()
        await asyncio.sleep(2)

        # Check dialog appeared
        dialog = await page.query_selector('[role="dialog"]')
        if not dialog:
            print("❌ Reply dialog didn't appear")
            await browser.close()
            return

        print("✅ Reply dialog opened")

        # Find textarea
        print("\n" + "="*70)
        print("STEP 2: Finding textarea...")
        print("="*70)

        textarea = await page.query_selector('[data-testid="tweetTextarea_0"]')
        if not textarea:
            print("❌ Textarea not found")
            await browser.close()
            return

        print("✅ Found textarea")

        # Focus it
        await textarea.click()
        await asyncio.sleep(0.5)

        # Test methods
        print("\n" + "="*70)
        print("STEP 3: Testing typing methods...")
        print("="*70)
        print("\n1. .type() with 50ms delay")
        print("2. .type() with 100ms delay")
        print("3. .fill()")
        print("4. JavaScript insertText")
        print("5. Keyboard.type()")

        method = input("\nWhich method to test (1-5)? ").strip() or "1"

        try:
            if method == "1":
                print("\n🔤 Testing: .type() with 50ms delay")
                await page.type('[data-testid="tweetTextarea_0"]', comment_text, delay=50)

            elif method == "2":
                print("\n🔤 Testing: .type() with 100ms delay")
                await page.type('[data-testid="tweetTextarea_0"]', comment_text, delay=100)

            elif method == "3":
                print("\n🔤 Testing: .fill()")
                await page.fill('[data-testid="tweetTextarea_0"]', comment_text)

            elif method == "4":
                print("\n🔤 Testing: JavaScript insertText")
                await page.evaluate(f"""
                    const el = document.querySelector('[data-testid="tweetTextarea_0"]');
                    el.focus();
                    document.execCommand('insertText', false, `{comment_text}`);
                """)

            elif method == "5":
                print("\n🔤 Testing: Keyboard.type()")
                for char in comment_text:
                    await page.keyboard.type(char)
                    await asyncio.sleep(0.05)

            await asyncio.sleep(1)

            # Verify
            text_in_box = await page.evaluate("""
                document.querySelector('[data-testid="tweetTextarea_0"]')?.textContent || ''
            """)

            print(f"\n🔍 Text in textarea: '{text_in_box}'")

            if comment_text in text_in_box:
                print("✅ SUCCESS! Text was entered correctly!")
            else:
                print("❌ FAILED! Text not in textarea")

            # Check submit button
            submit_disabled = await page.evaluate("""
                document.querySelector('[data-testid="tweetButton"]')?.disabled ||
                document.querySelector('[data-testid="tweetButton"]')?.getAttribute('aria-disabled') === 'true'
            """)

            print(f"\nSubmit button disabled: {submit_disabled}")

            # Ask if they want to submit
            submit = input("\n⚠️  Submit the comment? (y/n): ").strip().lower()

            if submit == 'y':
                await page.click('[data-testid="tweetButton"]')
                await asyncio.sleep(2)

                dialog_gone = not await page.query_selector('[role="dialog"]')
                if dialog_gone:
                    print("✅ Comment posted successfully!")
                else:
                    print("⚠️  Dialog still open, may have failed")

        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()

        print("\n" + "="*70)
        print("✅ TEST COMPLETE")
        print("="*70)

        input("\nPress ENTER to close browser...")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
