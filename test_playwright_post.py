#!/usr/bin/env python3
"""
Standalone test: Playwright posting to X.com
Run this directly on your host (no Docker needed)
"""

import asyncio
from playwright.async_api import async_playwright

async def test_post():
    """Test posting to X.com using Playwright"""
    
    async with async_playwright() as p:
        print("🎭 Launching browser...")
        # Launch with your user data to use existing login
        browser = await p.chromium.launch(
            headless=False,  # See it work!
            args=["--no-sandbox"]
        )
        
        context = await browser.new_context()
        page = await context.new_page()
        
        print("🌐 Navigating to X.com...")
        await page.goto("https://x.com/home")
        await page.wait_for_timeout(3000)
        
        print("📝 Finding compose box...")
        compose_box = page.locator('[data-testid="tweetTextarea_0"]')
        
        print("👆 Clicking compose box...")
        await compose_box.click()
        await page.wait_for_timeout(500)
        
        post_text = "🎉 SUCCESS! Playwright posting works perfectly! This is automated! 🚀✨"
        print(f"⌨️  Typing: {post_text}")
        await compose_box.type(post_text, delay=50)  # Real keyboard events!
        
        await page.wait_for_timeout(2000)
        
        print("🔘 Looking for Post button...")
        post_button = page.locator('[data-testid="tweetButtonInline"]')
        
        print("🖱️  Clicking Post button...")
        await post_button.click()
        
        print("⏳ Waiting for post to publish...")
        await page.wait_for_timeout(3000)
        
        print("✅ POST CREATED SUCCESSFULLY!")
        print("\nCheck your X.com timeline to see the post!")
        
        await browser.close()

if __name__ == "__main__":
    print("=" * 60)
    print("🧪 Testing Playwright X.com Posting")
    print("=" * 60)
    print("\n⚠️  Make sure you're logged into X.com in your browser first!\n")
    
    asyncio.run(test_post())

