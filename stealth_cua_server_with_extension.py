#!/usr/bin/env python3
"""
Enhanced CUA Server with Playwright Stealth + Chrome Extension Integration
Loads the X automation extension for persistent session management
"""

import os
import subprocess
import base64
import shlex
import asyncio
from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from playwright_stealth import Stealth
import json
from typing import Optional

os.environ['DISPLAY'] = ':98'
app = FastAPI(title='Stealth CUA Server with Extension')

# Global Playwright instances
playwright_instance = None
browser: Optional[Browser] = None
context: Optional[BrowserContext] = None 
page: Optional[Page] = None
stealth_mode = True

# Request Models
class ClickRequest(BaseModel):
    x: int
    y: int

class TypeRequest(BaseModel):
    text: str

class KeyPressRequest(BaseModel):
    keys: list

class ScrollRequest(BaseModel):
    x: int
    y: int
    scroll_x: int = 0
    scroll_y: int = 3

class NavigateRequest(BaseModel):
    url: str

class ClickSelectorRequest(BaseModel):
    selector: str
    selector_type: str = "css"

async def initialize_stealth_browser():
    """Initialize Playwright stealth browser WITH Chrome extension"""
    global playwright_instance, browser, context, page
    
    if browser is not None:
        return True
    
    try:
        print("🥷 Initializing Playwright stealth browser with extension in Docker...")
        
        # Create stealth configuration
        stealth = Stealth(
            navigator_languages_override=("en-US", "en"),
            navigator_vendor_override="Google Inc.",
            navigator_platform_override="Linux x86_64",
            navigator_user_agent_override="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            navigator_webdriver=True,
            navigator_permissions=True,
            webgl_vendor=True,
            navigator_plugins=True,
            media_codecs=True
        )
        
        # Start playwright
        playwright_instance = await async_playwright().start()
        
        # Extension path inside Docker
        extension_path = "/app/x-automation-extension"
        
        # Launch browser WITH extension
        browser = await playwright_instance.chromium.launch(
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage", 
                "--disable-blink-features=AutomationControlled",
                "--disable-features=VizDisplayCompositor,TranslateUI",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
                "--no-first-run",
                "--no-default-browser-check",
                f"--disable-extensions-except={extension_path}",
                f"--load-extension={extension_path}",
                "--display=:98"
            ]
        )
        
        print(f"✅ Browser launched with extension from: {extension_path}")
        
        # Create context with stealth
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent=stealth.navigator_user_agent_override,
            locale='en-US'
        )
        
        await stealth.apply_stealth_async(context)
        page = await context.new_page()
        
        # Navigate to a default page
        await page.goto("https://www.google.com/", wait_until="domcontentloaded")
        
        print("✅ Stealth browser with extension ready in Docker!")
        print("📦 Extension should now be active and connecting to backend")
        return True
        
    except Exception as e:
        print(f"❌ Failed to initialize stealth browser: {e}")
        return False

# ... (rest of the endpoints remain the same as stealth_cua_server.py)
# Copy all the endpoints from stealth_cua_server.py here

@app.get("/screenshot")
async def take_screenshot():
    """Take screenshot"""
    try:
        if page is None:
            await initialize_stealth_browser()
        
        if page:
            screenshot_bytes = await page.screenshot(full_page=False)
            image_data = base64.b64encode(screenshot_bytes).decode()
            return {
                "success": True, 
                "image": f"data:image/png;base64,{image_data}",
                "mode": "stealth_with_extension"
            }
        else:
            return {"success": False, "error": "Browser not initialized"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/click")
async def click(request: ClickRequest):
    """Click at coordinates"""
    try:
        if stealth_mode and page:
            await page.mouse.click(request.x, request.y)
            return {
                "success": True, 
                "message": f"Clicked at ({request.x}, {request.y})"
            }
        else:
            return {"success": False, "error": "Browser not ready"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/type")
async def type_text(request: TypeRequest):
    """Type text"""
    try:
        if stealth_mode and page:
            await page.keyboard.type(request.text, delay=50)
            return {
                "success": True, 
                "message": f"Typed: {request.text}"
            }
        else:
            return {"success": False, "error": "Browser not ready"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/navigate")
async def navigate(request: NavigateRequest):
    """Navigate to URL"""
    try:
        if stealth_mode and page:
            await page.goto(request.url, wait_until="domcontentloaded")
            return {
                "success": True, 
                "message": f"Navigated to: {request.url}"
            }
        else:
            return {"success": False, "error": "Browser not ready"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/dom/elements")
async def get_dom_elements():
    """Get all interactive elements from DOM"""
    try:
        if stealth_mode and page:
            elements = await page.evaluate("""
                () => {
                    function generateCSSSelector(el) {
                        if (el.id) return '#' + el.id;
                        let selector = el.tagName.toLowerCase();
                        if (el.className) {
                            const classes = el.className.split(' ').filter(c => c.trim());
                            if (classes.length > 0) {
                                selector += '.' + classes.join('.');
                            }
                        }
                        if (el.type) {
                            selector += `[type="${el.type}"]`;
                        }
                        return selector;
                    }
                    
                    const clickable = document.querySelectorAll('button, a, input, select, textarea, [onclick], [role="button"], [role="link"]');
                    return Array.from(clickable).map((el, index) => {
                        const rect = el.getBoundingClientRect();
                        const styles = window.getComputedStyle(el);
                        return {
                            index: index,
                            tagName: el.tagName.toLowerCase(),
                            text: el.textContent?.trim() || '',
                            id: el.id || '',
                            className: el.className || '',
                            href: el.href || '',
                            type: el.type || '',
                            ariaLabel: el.getAttribute('aria-label') || '',
                            testId: el.getAttribute('data-testid') || '',
                            cssSelector: generateCSSSelector(el),
                            x: Math.round(rect.x + rect.width/2),
                            y: Math.round(rect.y + rect.height/2),
                            visible: styles.display !== 'none' && styles.visibility !== 'hidden'
                        };
                    }).filter(el => el.visible);
                }
            """)
            return {"success": True, "elements": elements, "count": len(elements)}
        else:
            return {"success": False, "error": "Browser not ready"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/status")
async def get_status():
    """Get current server status"""
    return {
        "success": True,
        "mode": "stealth_with_extension",
        "browser_ready": browser is not None,
        "current_url": page.url if page else None,
        "extension_loaded": True,
        "message": "Stealth CUA Server with Extension running"
    }

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "🥷 Stealth CUA Server with Extension", 
        "mode": "stealth_with_extension",
        "browser_ready": browser is not None,
        "features": [
            "Browser automation",
            "Chrome extension integration",
            "Session management",
            "X authentication support"
        ]
    }

async def startup():
    """Initialize stealth browser on startup"""
    print("🚀 Starting Stealth CUA Server with Extension...")
    await initialize_stealth_browser()

if __name__ == "__main__":
    uvicorn.run(
        "stealth_cua_server_with_extension:app",
        host="0.0.0.0", 
        port=8005,
        reload=False
    )

