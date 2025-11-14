#!/usr/bin/env python3
"""
Enhanced CUA Server with Playwright Stealth Integration
Maintains FastAPI compatibility while adding stealth browser capabilities
"""

import os
import subprocess
import base64
import shlex
import asyncio
from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn
from patchright.async_api import async_playwright, Browser, BrowserContext, Page
# playwright_stealth not needed with patchright - it has built-in stealth
import json
from typing import Optional

# Patchright has built-in stealth - no need for playwright_stealth

# os.environ['DISPLAY'] = ':98'  # Not needed for headless mode
app = FastAPI(title='Stealth CUA Server')

# Global Playwright instances
playwright_instance = None
browser: Optional[Browser] = None
context: Optional[BrowserContext] = None 
page: Optional[Page] = None
main_page: Optional[Page] = None  # Track the main working page
stealth_mode = True  # Toggle between stealth browser and xdotool

# Request Models (same as original)
class ClickRequest(BaseModel):
    x: int
    y: int

class MoveRequest(BaseModel):
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

class ModeRequest(BaseModel):
    stealth: bool = True

async def handle_new_page(new_page: Page):
    """
    Handle new tabs/pages: close them immediately and switch back to main page.
    This prevents the agent from opening new tabs accidentally.
    """
    global main_page, page
    
    try:
        # If this is not the main page, close it
        if new_page != main_page:
            print(f"🚫 New tab detected! Closing it and staying on main tab...")
            await new_page.close()
            
            # Ensure we're on the main page
            if main_page and not main_page.is_closed():
                await main_page.bring_to_front()
                # Update the global page reference
                page = main_page
                print("✅ Switched back to main working tab")
    except Exception as e:
        print(f"⚠️ Error handling new page: {e}")

async def ensure_main_tab():
    """Ensure we're always on the main working tab"""
    global main_page, page, context
    
    try:
        if not main_page or main_page.is_closed():
            print("⚠️ Main page lost, recreating...")
            if context:
                main_page = await context.new_page()
                # Patchright automatically applies stealth
                page = main_page
                return True
            return False
        
        # Get all pages
        pages = context.pages if context else []
        
        # Close any extra tabs
        for p in pages:
            if p != main_page and not p.is_closed():
                print(f"🚫 Closing extra tab: {p.url}")
                await p.close()
        
        # Bring main page to front
        await main_page.bring_to_front()
        page = main_page
        return True
        
    except Exception as e:
        print(f"⚠️ Error ensuring main tab: {e}")
        return False

async def initialize_stealth_browser():
    """Initialize Playwright stealth browser"""
    global playwright_instance, browser, context, page
    
    # Check if already initialized (context is the key for persistent context)
    if context is not None and page is not None:
        print("⚠️ Browser already initialized, skipping...")
        return True
    
    try:
        print("🥷 Initializing Playwright stealth browser in Docker...")
        
        # Stealth will be applied to pages after creation
        
        # Start playwright
        playwright_instance = await async_playwright().start()
        
        # Check if extension exists
        extension_path = "/app/x-automation-extension"
        import os
        extension_exists = os.path.exists(extension_path)
        
        if extension_exists:
            print(f"✅ Extension found at {extension_path}")
            # Launch with extension using persistent context
            context = await playwright_instance.chromium.launch_persistent_context(
                user_data_dir="/tmp/playwright_profile",
                headless=False,  # Show browser in VNC (Docker has display :98)
                viewport={'width': 1280, 'height': 720},
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale='en-US',
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--display=:98",  # Use Docker's X display
                    f"--disable-extensions-except={extension_path}",
                    f"--load-extension={extension_path}"
                ]
            )
            browser = None  # Not used with persistent context
        else:
            print(f"⚠️ Extension not found, launching without it")
            # Launch without extension
            browser = await playwright_instance.chromium.launch(
                headless=False,  # Show browser in VNC (Docker has display :98)
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--no-first-run",
                    "--display=:98"  # Use Docker's X display
                ]
            )
            context = await browser.new_context(
                viewport={'width': 1280, 'height': 720},
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale='en-US'
            )
        
        page = await context.new_page()
        # Patchright automatically applies stealth
        
        # Set as main page
        global main_page
        main_page = page
        
        # Add listener to close any new tabs and switch back to main
        context.on("page", handle_new_page)
        
        # Navigate to a default page
        await page.goto("https://www.google.com/", wait_until="domcontentloaded")
        
        print("✅ Stealth browser ready in Docker with tab management!")
        return True
        
    except Exception as e:
        print(f"❌ Failed to initialize stealth browser: {e}")
        return False

def xdotool_screenshot():
    """Take screenshot using xdotool (fallback)"""
    try:
        result = subprocess.run(['scrot', '-'], capture_output=True, check=True)
        return base64.b64encode(result.stdout).decode()
    except Exception as e:
        print(f"Screenshot error: {e}")
        return None

async def playwright_screenshot():
    """Take screenshot using Playwright stealth browser"""
    try:
        if page is None:
            await initialize_stealth_browser()
        
        if page:
            screenshot_bytes = await page.screenshot(full_page=False)
            return base64.b64encode(screenshot_bytes).decode()
        else:
            return xdotool_screenshot()
    except Exception as e:
        print(f"Playwright screenshot error: {e}")
        return xdotool_screenshot()

@app.get("/screenshot")
async def take_screenshot():
    """Take screenshot - stealth browser or xdotool fallback"""
    try:
        if stealth_mode:
            image_data = await playwright_screenshot()
        else:
            image_data = xdotool_screenshot()
        
        if image_data:
            return {
                "success": True, 
                "image": f"data:image/png;base64,{image_data}",
                "mode": "stealth" if stealth_mode else "xdotool"
            }
        else:
            return {"success": False, "error": "Failed to capture screenshot"}
    except Exception as e:
        return {"success": False, "error": str(e)}

class ClickSelectorRequest(BaseModel):
    selector: str
    selector_type: str = "css"  # "css" or "xpath"

@app.post("/click")
async def click(request: ClickRequest):
    """Click at coordinates - stealth browser or xdotool"""
    try:
        if stealth_mode and page:
            # Ensure we're on the main tab before clicking
            await ensure_main_tab()

            # Log what element is at these coordinates BEFORE clicking
            element_info = await page.evaluate(f"""
                () => {{
                    const element = document.elementFromPoint({request.x}, {request.y});
                    if (element) {{
                        return {{
                            tag: element.tagName,
                            class: element.className,
                            testId: element.getAttribute('data-testid'),
                            ariaLabel: element.getAttribute('aria-label'),
                            text: element.innerText?.substring(0, 50)
                        }};
                    }}
                    return null;
                }}
            """)
            print(f"🎯 Clicking at ({request.x}, {request.y}) on element: {element_info}")

            # Use Playwright's mouse click - this properly triggers all event handlers
            # including React's synthetic events
            await page.mouse.click(request.x, request.y)

            # Longer delay to ensure click is processed
            await asyncio.sleep(0.5)

            print(f"✅ Click completed at ({request.x}, {request.y})")

            return {
                "success": True,
                "message": f"Stealth clicked at ({request.x}, {request.y})",
                "element": element_info
            }
        else:
            # Fallback to xdotool
            result = subprocess.run([
                'xdotool', 'mousemove', str(request.x), str(request.y), 'click', '1'
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                return {
                    "success": True, 
                    "message": f"XDoTool clicked at ({request.x}, {request.y})"
                }
            else:
                return {"success": False, "error": result.stderr}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/click_selector")
async def click_selector(request: ClickSelectorRequest):
    """Click element using CSS selector or XPath - better than coordinates"""
    try:
        if stealth_mode and page:
            if request.selector_type == "css":
                await page.click(request.selector)
            elif request.selector_type == "xpath":
                await page.locator(f"xpath={request.selector}").click()
            else:
                return {"success": False, "error": "Invalid selector_type. Use 'css' or 'xpath'"}
            
            return {
                "success": True, 
                "message": f"Clicked element using {request.selector_type} selector: {request.selector}"
            }
        else:
            return {"success": False, "error": "Stealth mode not active"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/fill_selector")
async def fill_selector(request: ClickSelectorRequest):
    """Fill input field using CSS selector - much better than coordinates + typing"""
    try:
        if stealth_mode and page:
            # Extract text from selector (assuming it's passed in a combined format)
            parts = request.selector.split('|||')  # Use ||| as separator
            selector = parts[0]
            text = parts[1] if len(parts) > 1 else ""
            
            if request.selector_type == "css":
                await page.fill(selector, text)
            elif request.selector_type == "xpath":
                await page.locator(f"xpath={selector}").fill(text)
            
            return {
                "success": True, 
                "message": f"Filled field using {request.selector_type} selector: {selector} with: {text}"
            }
        else:
            return {"success": False, "error": "Stealth mode not active"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/type")
async def type_text(request: TypeRequest):
    """Type text - stealth browser or xdotool"""
    try:
        if stealth_mode and page:
            await page.keyboard.type(request.text, delay=50)
            return {
                "success": True, 
                "message": f"Stealth typed: {request.text}"
            }
        else:
            # Fallback to xdotool
            escaped_text = shlex.quote(request.text)
            result = subprocess.run([
                'xdotool', 'type', '--delay', '100', escaped_text
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                return {
                    "success": True, 
                    "message": f"XDoTool typed: {request.text}"
                }
            else:
                return {"success": False, "error": result.stderr}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/key")
async def press_keys(request: KeyPressRequest):
    """Press key combination - stealth browser or xdotool"""
    try:
        if stealth_mode and page:
            # Convert to Playwright format
            key_combination = "+".join(request.keys)
            await page.keyboard.press(key_combination)
            return {
                "success": True, 
                "message": f"Stealth pressed: {key_combination}"
            }
        else:
            # Fallback to xdotool
            xdotool_keys = []
            for key in request.keys:
                if key.lower() == 'ctrl':
                    xdotool_keys.append('ctrl')
                elif key.lower() == 'alt':
                    xdotool_keys.append('alt')
                elif key.lower() == 'shift':
                    xdotool_keys.append('shift')
                elif key.lower() == 'return':
                    xdotool_keys.append('Return')
                else:
                    xdotool_keys.append(key)
            
            cmd = ['xdotool', 'key'] + xdotool_keys
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                return {
                    "success": True, 
                    "message": f"XDoTool pressed: {xdotool_keys}"
                }
            else:
                return {"success": False, "error": result.stderr}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/navigate")
async def navigate(request: NavigateRequest):
    """Navigate to URL - stealth browser or Firefox"""
    try:
        if stealth_mode and page:
            # Ensure we're on the main tab before navigating
            await ensure_main_tab()
            
            # Navigate on the main page
            await page.goto(request.url, wait_until="domcontentloaded")
            
            # Close any popups/extra tabs that might have opened
            await ensure_main_tab()
            
            return {
                "success": True, 
                "message": f"Stealth navigated to: {request.url}"
            }
        else:
            # Fallback: Focus Firefox and navigate
            # Focus Firefox window
            subprocess.run(['xdotool', 'search', '--name', 'firefox', 'windowactivate'], 
                         capture_output=True)
            
            # Press Ctrl+L for address bar
            subprocess.run(['xdotool', 'key', 'ctrl+l'], capture_output=True)
            subprocess.run(['sleep', '0.5'])
            
            # Type URL
            escaped_url = shlex.quote(request.url)
            subprocess.run(['xdotool', 'type', escaped_url], capture_output=True)
            
            # Press Enter
            subprocess.run(['xdotool', 'key', 'Return'], capture_output=True)
            
            return {
                "success": True, 
                "message": f"Firefox navigated to: {request.url}"
            }
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/scroll")
async def scroll(request: ScrollRequest):
    """Scroll at location - stealth browser or xdotool"""
    try:
        if stealth_mode and page:
            # Move to position and scroll
            await page.mouse.move(request.x, request.y)
            await page.mouse.wheel(request.scroll_x * 100, request.scroll_y * 100)
            return {
                "success": True, 
                "message": f"Stealth scrolled at ({request.x}, {request.y})"
            }
        else:
            # Fallback to xdotool
            # Move to position
            subprocess.run(['xdotool', 'mousemove', str(request.x), str(request.y)], 
                         capture_output=True)
            
            # Scroll
            if request.scroll_y > 0:
                button = '5'  # Scroll down
            else:
                button = '4'  # Scroll up
            
            for _ in range(abs(request.scroll_y)):
                subprocess.run(['xdotool', 'click', button], capture_output=True)
                subprocess.run(['sleep', '0.1'])
            
            return {
                "success": True, 
                "message": f"XDoTool scrolled at ({request.x}, {request.y})"
            }
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/mode")
async def set_mode(request: ModeRequest):
    """Switch between stealth mode and xdotool mode"""
    global stealth_mode
    
    stealth_mode = request.stealth
    
    if stealth_mode:
        success = await initialize_stealth_browser()
        if success:
            return {
                "success": True, 
                "message": "Switched to stealth browser mode",
                "mode": "stealth"
            }
        else:
            stealth_mode = False
            return {
                "success": False, 
                "message": "Failed to initialize stealth browser, using xdotool",
                "mode": "xdotool"
            }
    else:
        return {
            "success": True, 
            "message": "Switched to xdotool mode",
            "mode": "xdotool"
        }

@app.get("/dom/elements")
async def get_dom_elements():
    """Get all interactive elements from Playwright DOM with proper selectors"""
    try:
        if stealth_mode and page:
            elements = await page.evaluate("""
                () => {
                    // Helper function to generate CSS selector
                    function generateCSSSelector(el) {
                        if (el.id) return '#' + el.id;
                        
                        let selector = el.tagName.toLowerCase();
                        if (el.className) {
                            const classes = el.className.split(' ').filter(c => c.trim());
                            if (classes.length > 0) {
                                selector += '.' + classes.join('.');
                            }
                        }
                        
                        // Add type for inputs
                        if (el.type) {
                            selector += `[type="${el.type}"]`;
                        }
                        
                        // Add other distinguishing attributes
                        if (el.placeholder) {
                            selector += `[placeholder*="${el.placeholder.slice(0, 20)}"]`;
                        }
                        
                        return selector;
                    }
                    
                    const clickable = document.querySelectorAll('button, a, input, select, textarea, [onclick], [role="button"], [role="link"], [tabindex]:not([tabindex="-1"])');
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
                            role: el.getAttribute('role') || '',
                            ariaLabel: el.getAttribute('aria-label') || '',
                            placeholder: el.placeholder || '',
                            value: el.value || '',
                            testId: el.getAttribute('data-testid') || '',
                            
                            // Better selectors for proper interaction
                            cssSelector: generateCSSSelector(el),
                            
                            // Coordinates as fallback only
                            x: Math.round(rect.x + rect.width/2),
                            y: Math.round(rect.y + rect.height/2),
                            width: Math.round(rect.width),
                            height: Math.round(rect.height),
                            visible: styles.display !== 'none' && styles.visibility !== 'hidden' && rect.width > 0 && rect.height > 0,
                            interactable: !el.disabled && styles.pointerEvents !== 'none'
                        };
                    }).filter(el => el.visible && el.interactable);
                }
            """)
            return {"success": True, "elements": elements, "count": len(elements)}
        else:
            return {"success": False, "error": "Stealth mode not active"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/dom/page_info")
async def get_page_info():
    """Get current page information from Playwright"""
    try:
        if stealth_mode and page:
            info = await page.evaluate("""
                () => ({
                    title: document.title,
                    url: window.location.href,
                    domain: window.location.hostname,
                    forms: Array.from(document.forms).length,
                    links: Array.from(document.links).length,
                    buttons: Array.from(document.querySelectorAll('button')).length,
                    inputs: Array.from(document.querySelectorAll('input')).length,
                    readyState: document.readyState,
                    scrollHeight: document.documentElement.scrollHeight,
                    scrollTop: document.documentElement.scrollTop,
                    windowHeight: window.innerHeight,
                    windowWidth: window.innerWidth
                })
            """)
            return {"success": True, "page_info": info}
        else:
            return {"success": False, "error": "Stealth mode not active"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/dom/enhanced_context")
async def get_enhanced_context():
    """Get comprehensive page context: DOM elements + page info + screenshot"""
    try:
        if stealth_mode and page:
            # Get DOM elements
            elements = await page.evaluate("""
                () => {
                    const clickable = document.querySelectorAll('button, a, input, select, textarea, [onclick], [role="button"], [role="link"], [tabindex]:not([tabindex="-1"])');
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
                            role: el.getAttribute('role') || '',
                            ariaLabel: el.getAttribute('aria-label') || '',
                            placeholder: el.placeholder || '',
                            value: el.value || '',
                            x: Math.round(rect.x + rect.width/2),
                            y: Math.round(rect.y + rect.height/2),
                            width: Math.round(rect.width),
                            height: Math.round(rect.height),
                            visible: styles.display !== 'none' && styles.visibility !== 'hidden' && rect.width > 0 && rect.height > 0,
                            interactable: !el.disabled && styles.pointerEvents !== 'none'
                        };
                    }).filter(el => el.visible && el.interactable);
                }
            """)
            
            # Get page info
            page_info = await page.evaluate("""
                () => ({
                    title: document.title,
                    url: window.location.href,
                    domain: window.location.hostname,
                    forms: Array.from(document.forms).length,
                    links: Array.from(document.links).length,
                    buttons: Array.from(document.querySelectorAll('button')).length,
                    inputs: Array.from(document.querySelectorAll('input')).length,
                    readyState: document.readyState,
                    scrollHeight: document.documentElement.scrollHeight,
                    scrollTop: document.documentElement.scrollTop,
                    windowHeight: window.innerHeight,
                    windowWidth: window.innerWidth
                })
            """)
            
            # Take screenshot
            screenshot_bytes = await page.screenshot(full_page=False)
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode()
            
            return {
                "success": True,
                "page_info": page_info,
                "dom_elements": elements,
                "element_count": len(elements),
                "screenshot": f"data:image/png;base64,{screenshot_b64}"
            }
        else:
            return {"success": False, "error": "Stealth mode not active"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/status")
async def get_status():
    """Get current server status"""
    return {
        "success": True,
        "mode": "stealth" if stealth_mode else "xdotool",
        "stealth_browser_ready": context is not None and page is not None,
        "current_url": page.url if page else None,
        "message": "Stealth CUA Server running"
    }

@app.get("/page_text")
async def get_page_text():
    """Get all page text content directly from Playwright"""
    try:
        if stealth_mode and page:
            # Get all text content using document.body.innerText (clean, readable text)
            page_text = await page.evaluate("document.body.innerText")
            return {
                "success": True, 
                "text": page_text,
                "length": len(page_text)
            }
        else:
            return {"success": False, "error": "Stealth mode not active"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/execute")
async def execute_script(request: dict):
    """Execute arbitrary JavaScript in the page and return the result"""
    try:
        script = request.get("script")
        if not script:
            return {"success": False, "error": "No script provided"}
        
        if stealth_mode and page:
            result = await page.evaluate(script)
            return {
                "success": True,
                "result": result
            }
        else:
            return {"success": False, "error": "Stealth mode not active"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/session/save")
async def save_session():
    """
    Save current browser session cookies
    Returns cookies that can be stored in database (encrypted!)
    """
    try:
        if not context:
            return {"success": False, "error": "No active browser context"}
        
        # Get all cookies
        all_cookies = await context.cookies()
        
        # Filter X-related cookies
        x_cookies = [
            cookie for cookie in all_cookies
            if any(domain in cookie.get('domain', '') for domain in ['x.com', 'twitter.com'])
        ]
        
        # Try to get username
        username = "unknown"
        if page:
            try:
                profile_link = await page.locator('a[href^="/"][aria-label*="Profile"]').first.get_attribute('href', timeout=5000)
                username = profile_link.strip('/') if profile_link else "unknown"
            except:
                pass
        
        return {
            "success": True,
            "cookies": x_cookies,
            "cookies_count": len(x_cookies),
            "username": username,
            "message": f"Captured {len(x_cookies)} cookies"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/session/load")
async def load_session(request: dict):
    """
    Load cookies into browser context to restore session
    Request body: {"cookies": [...]}
    """
    try:
        # Initialize browser if not already done
        if not context:
            print("🔄 Browser not initialized, initializing now...")
            init_result = await initialize_stealth_browser()
            if not init_result or not context:
                return {"success": False, "error": "Failed to initialize browser"}
        
        cookies = request.get("cookies", [])
        if not cookies:
            return {"success": False, "error": "No cookies provided"}
        
        # Add cookies to context
        await context.add_cookies(cookies)
        
        # Navigate to X to activate session
        if page:
            await page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=15000)
            
            # Verify login status
            try:
                await page.wait_for_selector('[data-testid="SideNav_AccountSwitcher_Button"]', timeout=5000)
                is_logged_in = True
                
                # Get username
                try:
                    profile_link = await page.locator('a[href^="/"][aria-label*="Profile"]').first.get_attribute('href')
                    username = profile_link.strip('/') if profile_link else "unknown"
                except:
                    username = "unknown"
            except:
                is_logged_in = False
                username = "unknown"
            
            return {
                "success": True,
                "logged_in": is_logged_in,
                "username": username,
                "message": "Session loaded" if is_logged_in else "Session invalid - not logged in"
            }
        
        return {"success": False, "error": "No active page"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/session/check")
async def check_session():
    """
    Check if current session is logged in to X
    """
    try:
        if not page:
            return {"success": False, "error": "No active page"}
        
        # Navigate to X home
        await page.goto("https://x.com/home", wait_until="networkidle")
        
        # Check for login indicator
        try:
            await page.wait_for_selector('[data-testid="SideNav_AccountSwitcher_Button"]', timeout=5000)
            is_logged_in = True
            
            # Get username
            try:
                profile_link = await page.locator('a[href^="/"][aria-label*="Profile"]').first.get_attribute('href')
                username = profile_link.strip('/') if profile_link else "unknown"
            except:
                username = "unknown"
        except:
            is_logged_in = False
            username = "unknown"
        
        return {
            "success": True,
            "logged_in": is_logged_in,
            "username": username
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "🥷 Stealth CUA Server", 
        "mode": "stealth" if stealth_mode else "xdotool",
        "stealth_ready": browser is not None,
        "features": [
            "Browser automation",
            "Session management (cookies)",
            "X authentication support"
        ]
    }

@app.on_event("startup")
async def startup():
    """Initialize stealth browser on startup"""
    print("🚀 Starting Stealth CUA Server...")
    try:
        result = await initialize_stealth_browser()
        if result:
            print("✅ Stealth browser initialized successfully on startup")
        else:
            print("❌ Stealth browser initialization failed on startup")
    except Exception as e:
        print(f"❌ Error during stealth browser initialization: {e}")
        import traceback
        traceback.print_exc()

@app.post("/initialize")
async def manual_initialize():
    """Manually trigger browser initialization"""
    try:
        result = await initialize_stealth_browser()
        if result:
            return {"success": True, "message": "Browser initialized"}
        else:
            return {"success": False, "error": "Initialization failed"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/inject-cookies")
async def inject_cookies(data: dict):
    """Inject cookies into the browser context"""
    global context
    
    if not context:
        return {"success": False, "error": "Browser not initialized"}
    
    try:
        cookies = data.get("cookies", [])
        if not cookies:
            return {"success": False, "error": "No cookies provided"}
        
        # Fix cookie format for Playwright
        fixed_cookies = []
        for cookie in cookies:
            fixed_cookie = cookie.copy()
            # Playwright expects sameSite to be one of: Strict, Lax, None (capitalized)
            if 'sameSite' in fixed_cookie:
                same_site = fixed_cookie['sameSite']
                if same_site and same_site.lower() in ['strict', 'lax', 'none']:
                    fixed_cookie['sameSite'] = same_site.capitalize()
                elif same_site == 'no_restriction':
                    fixed_cookie['sameSite'] = 'None'
                elif same_site == 'unspecified':
                    fixed_cookie['sameSite'] = 'Lax'
                else:
                    # Remove invalid sameSite values
                    del fixed_cookie['sameSite']
            fixed_cookies.append(fixed_cookie)
        
        # Add cookies to the browser context
        await context.add_cookies(fixed_cookies)
        
        return {
            "success": True,
            "message": f"Injected {len(fixed_cookies)} cookies",
            "count": len(fixed_cookies)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/create-post-playwright")
async def create_post_playwright(data: dict):
    """Create a post using Playwright - types like a real user"""
    global page
    
    if not page:
        return {"success": False, "error": "Browser not initialized"}
    
    try:
        post_text = data.get("text", "")
        if not post_text:
            return {"success": False, "error": "No text provided"}
        
        print(f"🎯 Creating post with Playwright: {post_text}")
        
        # Click the compose box
        compose_box = page.locator('[data-testid="tweetTextarea_0"]')
        await compose_box.click()
        await page.wait_for_timeout(500)
        
        # Type the text (this sends real keyboard events!)
        await compose_box.type(post_text, delay=50)  # 50ms between keypresses
        await page.wait_for_timeout(1000)
        
        # Click the Post button
        post_button = page.locator('[data-testid="tweetButtonInline"]')
        await post_button.click()
        
        # Wait for post to be published
        await page.wait_for_timeout(2000)
        
        return {
            "success": True,
            "message": "Post created successfully",
            "post_text": post_text
        }
    except Exception as e:
        print(f"❌ Error creating post: {e}")
        return {"success": False, "error": str(e)}

@app.post("/playwright/click")
async def playwright_click(data: dict):
    """Click an element using Playwright's locator"""
    global page
    
    if not page:
        return {"success": False, "error": "Browser not initialized"}
    
    try:
        selector = data.get("selector", "")
        timeout = data.get("timeout", 5000)
        
        if not selector:
            return {"success": False, "error": "No selector provided"}
        
        print(f"🖱️ Clicking element: {selector}")
        
        locator = page.locator(selector)
        await locator.click(timeout=timeout)
        
        return {"success": True, "message": f"Clicked {selector}"}
    except Exception as e:
        print(f"❌ Error clicking element: {e}")
        return {"success": False, "error": str(e)}

@app.post("/playwright/type")
async def playwright_type(data: dict):
    """Type text using keyboard.type() - works with X.com React components"""
    global page

    if not page:
        return {"success": False, "error": "Browser not initialized"}

    try:
        selector = data.get("selector", "")
        text = data.get("text", "")
        delay = data.get("delay", 50)
        timeout = data.get("timeout", 5000)

        if not text:
            return {"success": False, "error": "No text provided"}

        print(f"⌨️ Typing with keyboard.type(): {text}")

        # If selector provided, click it first to focus
        if selector:
            try:
                locator = page.locator(selector)
                await locator.click(timeout=timeout)
                await asyncio.sleep(0.3)
            except Exception as e:
                print(f"⚠️  Could not click selector: {e}, typing anyway...")

        # Use keyboard.type() character by character (this works with X.com!)
        for char in text:
            await page.keyboard.type(char)
            await asyncio.sleep(delay / 1000)  # Convert ms to seconds

        return {"success": True, "message": f"Typed text using keyboard"}
    except Exception as e:
        print(f"❌ Error typing text: {e}")
        return {"success": False, "error": str(e)}

@app.post("/playwright/evaluate")
async def playwright_evaluate(data: dict):
    """Evaluate JavaScript in the page context"""
    global page
    
    if not page:
        return {"success": False, "error": "Browser not initialized"}
    
    try:
        script = data.get("script", "")
        
        if not script:
            return {"success": False, "error": "No script provided"}
        
        print(f"🔧 Evaluating script: {script[:100]}...")
        
        result = await page.evaluate(script)
        
        return {"success": True, "result": result}
    except Exception as e:
        print(f"❌ Error evaluating script: {e}")
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    # Run the server
    uvicorn.run(
        "stealth_cua_server:app",
        host="0.0.0.0", 
        port=8005,  # Changed to 8005 to avoid conflicts
        reload=False
    )
