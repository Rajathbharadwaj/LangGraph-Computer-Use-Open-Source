#!/usr/bin/env python3
"""
Test Cookie Transfer System
Verifies that cookies flow from Extension → Backend → Docker → LangGraph
"""

import asyncio
import aiohttp
import json

async def test_cookie_transfer():
    """Test the complete cookie transfer flow"""
    
    print("🧪 Testing Cookie Transfer System\n")
    print("=" * 60)
    
    # Step 1: Check backend is running
    print("\n1️⃣ Checking Backend Server...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:8001/") as response:
                data = await response.json()
                print(f"   ✅ Backend running: {data['message']}")
    except Exception as e:
        print(f"   ❌ Backend not running: {e}")
        return
    
    # Step 2: Check Docker is running
    print("\n2️⃣ Checking Docker Stealth Browser...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:8005/status") as response:
                data = await response.json()
                print(f"   ✅ Docker running: {data['message']}")
                print(f"   Mode: {data['mode']}")
                print(f"   Browser ready: {data['stealth_browser_ready']}")
    except Exception as e:
        print(f"   ❌ Docker not running: {e}")
        print(f"   Start Docker with: docker run -p 5900:5900 -p 8005:8005 your-image")
        return
    
    # Step 3: Check extension status
    print("\n3️⃣ Checking Extension Connection...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:8001/api/extension/status") as response:
                data = await response.json()
                
                if data['connected']:
                    print(f"   ✅ Extension connected!")
                    print(f"   Active connections: {data['count']}")
                    
                    for user in data['users']:
                        print(f"\n   User: {user.get('userId')}")
                        if 'username' in user:
                            print(f"   Username: @{user['username']}")
                        if user.get('hasCookies'):
                            print(f"   🍪 Has cookies: YES")
                            
                            # Step 4: Test cookie injection
                            print(f"\n4️⃣ Testing Cookie Injection to Docker...")
                            
                            inject_response = await session.post(
                                "http://localhost:8001/api/inject-cookies-to-docker",
                                json={"user_id": user['userId']}
                            )
                            inject_data = await inject_response.json()
                            
                            if inject_data['success']:
                                print(f"   ✅ Cookies injected successfully!")
                                print(f"   Logged in: {inject_data.get('logged_in')}")
                                print(f"   Username: @{inject_data.get('username')}")
                                
                                # Step 5: Verify Docker session
                                print(f"\n5️⃣ Verifying Docker Session...")
                                
                                check_response = await session.get("http://localhost:8005/session/check")
                                check_data = await check_response.json()
                                
                                if check_data.get('logged_in'):
                                    print(f"   ✅ Docker browser is logged in!")
                                    print(f"   Username: @{check_data.get('username')}")
                                    
                                    print(f"\n{'=' * 60}")
                                    print("🎉 SUCCESS! Cookie transfer is working!")
                                    print("=" * 60)
                                    print("\n✨ Your LangGraph agent can now use this X session!")
                                    print("\nNext steps:")
                                    print("1. Test with: python3 langgraph_playwright_agent.py")
                                    print("2. Or use the dashboard to trigger automation")
                                    print("3. Agent will use your X account automatically!")
                                else:
                                    print(f"   ⚠️ Docker browser not logged in")
                                    print(f"   This might mean cookies are expired")
                            else:
                                print(f"   ❌ Cookie injection failed: {inject_data.get('error')}")
                        else:
                            print(f"   🍪 Has cookies: NO")
                            print(f"\n   ⚠️ Extension hasn't captured cookies yet")
                            print(f"   Steps to capture cookies:")
                            print(f"   1. Open https://x.com in Chrome")
                            print(f"   2. Make sure you're logged in")
                            print(f"   3. Click the extension icon")
                            print(f"   4. Extension will auto-capture cookies")
                else:
                    print(f"   ❌ No extension connected")
                    print(f"\n   Steps to connect extension:")
                    print(f"   1. Go to chrome://extensions/")
                    print(f"   2. Load unpacked: /home/rajathdb/x-automation-extension/")
                    print(f"   3. Click the extension icon")
                    print(f"   4. It should show 'Connected to Dashboard'")
    except Exception as e:
        print(f"   ❌ Error checking extension: {e}")

if __name__ == "__main__":
    asyncio.run(test_cookie_transfer())

