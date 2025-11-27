"""
X Session Manager - Cookie-based Authentication
Handles saving, loading, and managing user X sessions
"""

import json
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from cryptography.fernet import Fernet
import aiohttp
from playwright.async_api import async_playwright, BrowserContext, Page


class XSessionManager:
    """Manage X authentication sessions using cookies"""
    
    def __init__(self, encryption_key: bytes, cua_server_url: str = "http://localhost:8005"):
        self.encryption_key = encryption_key
        self.fernet = Fernet(encryption_key)
        self.cua_server_url = cua_server_url
    
    def encrypt_cookies(self, cookies: List[Dict]) -> str:
        """Encrypt cookies for secure storage"""
        cookies_json = json.dumps(cookies)
        encrypted = self.fernet.encrypt(cookies_json.encode())
        return encrypted.decode()
    
    def decrypt_cookies(self, encrypted_data: str) -> List[Dict]:
        """Decrypt cookies from storage"""
        decrypted = self.fernet.decrypt(encrypted_data.encode())
        return json.loads(decrypted.decode())
    
    async def capture_session_after_login(self, page: Page) -> Dict:
        """
        Capture X session cookies after user logs in
        Call this after user completes login in guided flow
        """
        
        print("🔍 Waiting for login to complete...")
        
        # Wait for user to be redirected to home page
        try:
            await page.wait_for_url("**/home", timeout=300000)  # 5 min timeout
            print("✅ Login detected - user redirected to home")
        except Exception as e:
            return {
                "success": False,
                "error": f"Login timeout or failed: {str(e)}"
            }
        
        # Verify login by checking for user profile button
        try:
            await page.wait_for_selector('[data-testid="SideNav_AccountSwitcher_Button"]', timeout=10000)
            print("✅ Login verified - profile button found")
        except Exception as e:
            return {
                "success": False,
                "error": "Login verification failed - profile button not found"
            }
        
        # Extract username
        try:
            profile_link = await page.locator('a[href^="/"][aria-label*="Profile"]').first.get_attribute('href')
            username = profile_link.strip('/') if profile_link else "unknown"
            print(f"👤 Detected username: @{username}")
        except Exception as e:
            username = "unknown"
            print(f"⚠️ Could not extract username: {e}")
        
        # Get all cookies
        context = page.context
        all_cookies = await context.cookies()
        
        # Filter X-related cookies
        x_cookies = [
            cookie for cookie in all_cookies
            if any(domain in cookie.get('domain', '') for domain in ['x.com', 'twitter.com'])
        ]
        
        print(f"🍪 Captured {len(x_cookies)} X cookies")
        
        # Calculate expiry (use shortest cookie expiry or default 30 days)
        min_expiry = None
        for cookie in x_cookies:
            if 'expires' in cookie and cookie['expires'] > 0:
                cookie_expiry = datetime.fromtimestamp(cookie['expires'])
                if min_expiry is None or cookie_expiry < min_expiry:
                    min_expiry = cookie_expiry
        
        if min_expiry is None:
            min_expiry = datetime.now() + timedelta(days=30)
        
        return {
            "success": True,
            "username": username,
            "cookies": x_cookies,
            "cookies_count": len(x_cookies),
            "expires_at": min_expiry.isoformat()
        }
    
    async def load_session_to_browser(self, context: BrowserContext, cookies: List[Dict]) -> Dict:
        """
        Load saved cookies into browser context to restore session
        """
        
        try:
            # Add cookies to context
            await context.add_cookies(cookies)
            print(f"✅ Loaded {len(cookies)} cookies into browser")
            
            # Create page and navigate to X
            page = await context.new_page()
            await page.goto("https://x.com/home", wait_until="networkidle")
            
            # Verify login status
            try:
                await page.wait_for_selector('[data-testid="SideNav_AccountSwitcher_Button"]', timeout=5000)
                is_logged_in = True
                print("✅ Session restored - user is logged in")
            except:
                is_logged_in = False
                print("❌ Session invalid - user not logged in")
            
            # Extract current username if logged in
            username = "unknown"
            if is_logged_in:
                try:
                    profile_link = await page.locator('a[href^="/"][aria-label*="Profile"]').first.get_attribute('href')
                    username = profile_link.strip('/') if profile_link else "unknown"
                except:
                    pass
            
            return {
                "success": is_logged_in,
                "username": username,
                "logged_in": is_logged_in,
                "page": page
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "logged_in": False
            }
    
    async def check_session_validity(self, cookies: List[Dict]) -> bool:
        """
        Check if saved session cookies are still valid
        """
        
        print("🔍 Checking session validity...")
        
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context()
        
        try:
            result = await self.load_session_to_browser(context, cookies)
            is_valid = result.get("logged_in", False)
            
            print(f"{'✅' if is_valid else '❌'} Session is {'valid' if is_valid else 'invalid'}")
            
            await browser.close()
            await playwright.stop()
            
            return is_valid
            
        except Exception as e:
            print(f"❌ Session check failed: {e}")
            await browser.close()
            await playwright.stop()
            return False
    
    async def guided_login_flow(self, user_id: str, headless: bool = False) -> Dict:
        """
        Complete guided login flow for new user
        Opens browser, waits for login, captures cookies
        """
        
        print(f"🚀 Starting guided login for user: {user_id}")
        
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=headless)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        
        page = await context.new_page()
        
        # Navigate to X login
        await page.goto("https://x.com/login")
        print("📱 Opened X login page")
        print("⏳ Waiting for user to complete login...")
        
        # Capture session after login
        result = await self.capture_session_after_login(page)
        
        if result["success"]:
            # Encrypt cookies for storage
            encrypted_cookies = self.encrypt_cookies(result["cookies"])
            result["encrypted_cookies"] = encrypted_cookies
            print(f"✅ Session captured for @{result['username']}")
        
        await browser.close()
        await playwright.stop()
        
        return result


# Example usage
async def example_usage():
    """Example: How to use XSessionManager"""
    
    # Generate encryption key (store this securely!)
    encryption_key = Fernet.generate_key()
    print(f"🔑 Encryption key: {encryption_key.decode()}")
    print("⚠️ SAVE THIS KEY SECURELY - YOU'LL NEED IT TO DECRYPT COOKIES!")
    
    manager = XSessionManager(encryption_key)
    
    # Scenario 1: New user onboarding
    print("\n" + "="*60)
    print("SCENARIO 1: NEW USER ONBOARDING")
    print("="*60)
    
    user_id = "user_123"
    result = await manager.guided_login_flow(user_id, headless=False)
    
    if result["success"]:
        print(f"\n✅ SUCCESS!")
        print(f"   Username: @{result['username']}")
        print(f"   Cookies captured: {result['cookies_count']}")
        print(f"   Expires: {result['expires_at']}")
        print(f"\n🔐 Encrypted cookies (store in database):")
        print(f"   {result['encrypted_cookies'][:100]}...")
        
        # Save to database (pseudo-code)
        # await db.save_user_session(user_id, result['encrypted_cookies'], result['expires_at'])
        
        # Scenario 2: Load existing session
        print("\n" + "="*60)
        print("SCENARIO 2: LOAD EXISTING SESSION")
        print("="*60)
        
        # Retrieve from database (pseudo-code)
        # encrypted_cookies = await db.get_user_session(user_id)
        encrypted_cookies = result['encrypted_cookies']
        
        # Decrypt cookies
        cookies = manager.decrypt_cookies(encrypted_cookies)
        print(f"🔓 Decrypted {len(cookies)} cookies")
        
        # Check if still valid
        is_valid = await manager.check_session_validity(cookies)
        
        if is_valid:
            print("✅ Session is still valid - ready to automate!")
        else:
            print("❌ Session expired - user needs to re-authenticate")
    
    else:
        print(f"\n❌ FAILED: {result.get('error')}")


if __name__ == "__main__":
    asyncio.run(example_usage())

