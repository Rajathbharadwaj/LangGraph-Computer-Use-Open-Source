#!/usr/bin/env python3
"""
Test script for X media upload via Playwright

This script tests the /create-post-with-media endpoint.
Run this against a local stealth_cua_server with browser logged into X.

Usage:
    1. Start stealth_cua_server: python stealth_cua_server.py
    2. Log into X in the browser (navigate to x.com, login manually)
    3. Create a test image: convert -size 200x200 xc:blue /tmp/test_image.png
    4. Run this: python test_media_upload.py
"""

import asyncio
import aiohttp
import base64
from pathlib import Path

# Local stealth server URL
CUA_URL = "http://localhost:8005"


async def check_server():
    """Check if server is running"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{CUA_URL}/", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    print(f"✅ Server running: {data.get('service', 'unknown')}")
                    return True
    except Exception as e:
        print(f"❌ Cannot connect to server at {CUA_URL}: {e}")
        return False
    return False


async def test_post_with_media_url(image_url: str, post_text: str = "Testing media upload!"):
    """Test posting with a media URL (e.g., from GCS)"""
    print(f"\n{'='*60}")
    print("TEST: Post with media URL")
    print(f"{'='*60}")
    print(f"Image URL: {image_url}")
    print(f"Post text: {post_text}")

    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{CUA_URL}/create-post-with-media",
            json={
                "text": post_text,
                "media_urls": [image_url]
            },
            timeout=aiohttp.ClientTimeout(total=60)
        ) as resp:
            result = await resp.json()
            print(f"\nResult: {result}")
            return result


async def test_post_with_base64(image_path: str, post_text: str = "Testing base64 media upload!"):
    """Test posting with base64 encoded media"""
    print(f"\n{'='*60}")
    print("TEST: Post with base64 media")
    print(f"{'='*60}")

    # Read and encode image
    try:
        image_bytes = Path(image_path).read_bytes()
        image_b64 = base64.b64encode(image_bytes).decode()
        print(f"Image: {image_path} ({len(image_bytes)} bytes)")
        print(f"Post text: {post_text}")
    except Exception as e:
        print(f"❌ Could not read image: {e}")
        return None

    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{CUA_URL}/create-post-with-media",
            json={
                "text": post_text,
                "media_base64": [{
                    "name": "test_image.png",
                    "mimeType": "image/png",
                    "base64": image_b64
                }]
            },
            timeout=aiohttp.ClientTimeout(total=60)
        ) as resp:
            result = await resp.json()
            print(f"\nResult: {result}")
            return result


async def test_find_file_inputs():
    """Test finding file input elements on the page"""
    print(f"\n{'='*60}")
    print("TEST: Find file inputs on page")
    print(f"{'='*60}")

    js_code = """
    () => {
        const inputs = document.querySelectorAll('input[type="file"]');
        return Array.from(inputs).map(i => ({
            id: i.id || '(no id)',
            name: i.name || '(no name)',
            accept: i.accept || '(any)',
            testid: i.getAttribute('data-testid') || '(none)',
            visible: i.offsetParent !== null
        }));
    }
    """

    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{CUA_URL}/playwright/evaluate",
            json={"script": js_code},
            timeout=aiohttp.ClientTimeout(total=10)
        ) as resp:
            result = await resp.json()
            if result.get("success"):
                file_inputs = result.get("result", [])
                print(f"Found {len(file_inputs)} file input(s):")
                for fi in file_inputs:
                    print(f"  - testid={fi['testid']}, accept={fi['accept']}, visible={fi['visible']}")
            else:
                print(f"Error: {result.get('error')}")
            return result


async def navigate_to_compose():
    """Navigate to X compose page"""
    print(f"\n{'='*60}")
    print("Navigating to X compose...")
    print(f"{'='*60}")

    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{CUA_URL}/navigate",
            json={"url": "https://x.com/compose/tweet"},
            timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            result = await resp.json()
            print(f"Navigation: {result}")
            return result


async def take_screenshot(save_path: str = "/tmp/x_screenshot.png"):
    """Take a screenshot"""
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{CUA_URL}/screenshot") as resp:
            result = await resp.json()
            if result.get("success"):
                img_data = result.get("image", "").replace("data:image/png;base64,", "")
                if img_data:
                    Path(save_path).write_bytes(base64.b64decode(img_data))
                    print(f"📸 Screenshot saved: {save_path}")
            return result


async def main():
    """Run tests"""
    print("=" * 60)
    print("X Media Upload Test Suite")
    print("=" * 60)

    # Check server
    if not await check_server():
        print(f"\n⚠️ Start the server first:")
        print(f"   cd /home/rajathdb/cua && python stealth_cua_server.py")
        return

    # Navigate to compose page
    await navigate_to_compose()
    await asyncio.sleep(2)

    # Take screenshot to see current state
    await take_screenshot("/tmp/x_before_test.png")

    # Find file inputs
    await test_find_file_inputs()

    # Test with local file (if exists)
    test_image = "/tmp/test_image.png"
    if Path(test_image).exists():
        print(f"\n✅ Found test image: {test_image}")

        # Ask user before posting
        print("\n⚠️ This will POST to X! Press Enter to continue or Ctrl+C to cancel...")
        try:
            input()
            await test_post_with_base64(test_image, "Testing automated media upload! 🤖")
        except KeyboardInterrupt:
            print("\nCancelled.")
    else:
        print(f"\n⚠️ No test image at {test_image}")
        print("Create one with:")
        print(f"   convert -size 200x200 xc:blue {test_image}")
        print("   # or")
        print(f"   python -c \"from PIL import Image; Image.new('RGB', (200, 200), 'blue').save('{test_image}')\"")

    # Take final screenshot
    await take_screenshot("/tmp/x_after_test.png")


if __name__ == "__main__":
    asyncio.run(main())
