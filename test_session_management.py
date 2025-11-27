"""
Test Session Management in Docker
Demonstrates how to use the new cookie-based authentication
"""

import asyncio
import aiohttp
import json
from cryptography.fernet import Fernet


class DockerSessionManager:
    """Manage X sessions via Docker stealth server"""
    
    def __init__(self, docker_url: str = "http://localhost:8005"):
        self.docker_url = docker_url
        self.encryption_key = Fernet.generate_key()
        self.fernet = Fernet(self.encryption_key)
    
    def encrypt_cookies(self, cookies: list) -> str:
        """Encrypt cookies for storage"""
        cookies_json = json.dumps(cookies)
        encrypted = self.fernet.encrypt(cookies_json.encode())
        return encrypted.decode()
    
    def decrypt_cookies(self, encrypted_data: str) -> list:
        """Decrypt cookies"""
        decrypted = self.fernet.decrypt(encrypted_data.encode())
        return json.loads(decrypted.decode())
    
    async def check_docker_status(self):
        """Check if Docker server is running"""
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"{self.docker_url}/status") as resp:
                    data = await resp.json()
                    return data
            except Exception as e:
                return {"success": False, "error": str(e)}
    
    async def navigate_to_login(self):
        """Navigate to X login page"""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.docker_url}/navigate",
                json={"url": "https://x.com/login"}
            ) as resp:
                return await resp.json()
    
    async def capture_session(self):
        """Capture cookies after user logs in"""
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.docker_url}/session/save") as resp:
                return await resp.json()
    
    async def load_session(self, cookies: list):
        """Load saved cookies into browser"""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.docker_url}/session/load",
                json={"cookies": cookies}
            ) as resp:
                return await resp.json()
    
    async def check_login_status(self):
        """Check if currently logged in"""
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.docker_url}/session/check") as resp:
                return await resp.json()


async def demo_workflow():
    """
    Demonstrate complete workflow:
    1. User logs in manually (via VNC)
    2. Capture cookies
    3. Store encrypted cookies
    4. Later: Load cookies to restore session
    """
    
    print("🚀 SESSION MANAGEMENT DEMO")
    print("=" * 60)
    
    manager = DockerSessionManager()
    
    # Step 1: Check Docker status
    print("\n1️⃣ Checking Docker server status...")
    status = await manager.check_docker_status()
    if not status.get("success"):
        print(f"❌ Docker server not running: {status.get('error')}")
        print("💡 Run: ./rebuild_stealth_with_auth.sh")
        return
    
    print(f"✅ Docker server running")
    print(f"   Mode: {status.get('mode')}")
    print(f"   Stealth ready: {status.get('stealth_browser_ready')}")
    
    # Step 2: Navigate to login
    print("\n2️⃣ Navigating to X login page...")
    nav_result = await manager.navigate_to_login()
    if nav_result.get("success"):
        print("✅ Navigated to login page")
        print("\n📺 MANUAL STEP:")
        print("   1. Open VNC viewer: vnc://localhost:5900")
        print("   2. Log in to your X account")
        print("   3. Wait until you see the home page")
        print("   4. Press Enter here to continue...")
        input()
    else:
        print(f"❌ Navigation failed: {nav_result.get('error')}")
        return
    
    # Step 3: Capture session
    print("\n3️⃣ Capturing session cookies...")
    capture_result = await manager.capture_session()
    
    if capture_result.get("success"):
        cookies = capture_result["cookies"]
        username = capture_result["username"]
        print(f"✅ Session captured!")
        print(f"   Username: @{username}")
        print(f"   Cookies: {len(cookies)}")
        
        # Encrypt for storage
        encrypted_cookies = manager.encrypt_cookies(cookies)
        print(f"\n🔐 Encrypted cookies (store in database):")
        print(f"   {encrypted_cookies[:100]}...")
        print(f"   Length: {len(encrypted_cookies)} bytes")
        
        # Simulate storing in database
        print("\n💾 Simulating database storage...")
        print("   await db.save_user_session(")
        print(f"       user_id='user_123',")
        print(f"       encrypted_cookies='{encrypted_cookies[:50]}...',")
        print(f"       username='@{username}'")
        print("   )")
        
        # Step 4: Test loading session (simulate new browser session)
        print("\n4️⃣ Testing session restore...")
        print("   Decrypting cookies...")
        decrypted_cookies = manager.decrypt_cookies(encrypted_cookies)
        print(f"   ✅ Decrypted {len(decrypted_cookies)} cookies")
        
        print("   Loading into browser...")
        load_result = await manager.load_session(decrypted_cookies)
        
        if load_result.get("success") and load_result.get("logged_in"):
            print(f"   ✅ Session restored successfully!")
            print(f"   Username: @{load_result.get('username')}")
            print(f"\n🎉 SUCCESS! You can now automate on behalf of @{username}")
        else:
            print(f"   ❌ Session restore failed: {load_result.get('message')}")
    
    else:
        print(f"❌ Capture failed: {capture_result.get('error')}")
        print("💡 Make sure you're logged in to X in the VNC viewer")
    
    # Step 5: Show usage in production
    print("\n" + "=" * 60)
    print("📚 PRODUCTION USAGE")
    print("=" * 60)
    print("""
# In your SaaS backend:

from cryptography.fernet import Fernet
import aiohttp

# Initialize
ENCRYPTION_KEY = os.getenv('COOKIE_ENCRYPTION_KEY').encode()
fernet = Fernet(ENCRYPTION_KEY)

# User onboarding endpoint
@app.post("/onboard/connect-x")
async def connect_x_account(user_id: str):
    # 1. Open VNC session for user to log in
    # 2. After login, capture cookies
    async with aiohttp.ClientSession() as session:
        async with session.post('http://localhost:8005/session/save') as resp:
            result = await resp.json()
    
    # 3. Encrypt and store
    encrypted = fernet.encrypt(json.dumps(result['cookies']).encode())
    await db.save_user_session(user_id, encrypted)
    
    return {"success": True, "username": result['username']}

# Automation endpoint
@app.post("/automate/like-post")
async def like_post(user_id: str, post_url: str):
    # 1. Get encrypted cookies from database
    encrypted_cookies = await db.get_user_session(user_id)
    
    # 2. Decrypt
    cookies = json.loads(fernet.decrypt(encrypted_cookies))
    
    # 3. Load into browser
    async with aiohttp.ClientSession() as session:
        async with session.post(
            'http://localhost:8005/session/load',
            json={'cookies': cookies}
        ) as resp:
            result = await resp.json()
    
    if not result['logged_in']:
        return {"error": "Session expired - please reconnect"}
    
    # 4. Perform automation
    # ... use your existing Playwright tools ...
    
    return {"success": True}
""")
    
    print("\n✅ Demo complete!")
    print("📖 See SAAS_AUTH_GUIDE.md for full implementation")


async def quick_test():
    """Quick test of endpoints"""
    print("🧪 QUICK ENDPOINT TEST")
    print("=" * 60)
    
    manager = DockerSessionManager()
    
    # Test status
    print("\n1. Testing /status:")
    status = await manager.check_docker_status()
    print(json.dumps(status, indent=2))
    
    # Test check (will fail if not logged in)
    print("\n2. Testing /session/check:")
    check = await manager.check_login_status()
    print(json.dumps(check, indent=2))
    
    if check.get("logged_in"):
        print(f"\n✅ Already logged in as @{check.get('username')}")
        print("   You can capture cookies now!")
    else:
        print("\n⚠️ Not logged in")
        print("   1. Run: ./rebuild_stealth_with_auth.sh")
        print("   2. Open VNC: vnc://localhost:5900")
        print("   3. Log in to X")
        print("   4. Run this script again")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "quick":
        asyncio.run(quick_test())
    else:
        asyncio.run(demo_workflow())

