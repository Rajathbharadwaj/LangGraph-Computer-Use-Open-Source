#!/usr/bin/env python3
"""
Async Playwright CUA Tools for LangGraph ASGI Servers
Non-blocking computer use tools powered by Playwright stealth browser.
Designed specifically for LangGraph deployment without blocking the event loop.
"""

import asyncio
from typing import List, Dict, Any
import aiohttp
import json
from langchain_core.tools import StructuredTool, tool
from pydantic import BaseModel, Field


class AsyncPlaywrightClient:
    """Async HTTP client for Playwright CUA server - ASGI compatible"""
    
    def __init__(self, host: str = 'localhost', port: int = 8005):
        self.base_url = f"http://{host}:{port}"
        self._session = None
    
    async def get_session(self):
        """Get or create aiohttp session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            )
        return self._session
    
    async def _request(self, method: str, endpoint: str, data: dict = None) -> Dict[str, Any]:
        """Make async HTTP request to the Playwright CUA server"""
        url = f"{self.base_url}{endpoint}"
        try:
            session = await self.get_session()
            
            if method.upper() == "GET":
                async with session.get(url) as response:
                    return await response.json()
            elif method.upper() == "POST":
                async with session.post(url, json=data) as response:
                    return await response.json()
        except Exception as e:
            print(f"Async Playwright Client Request Error: {e}")
            return {"error": str(e), "success": False}
    
    async def close(self):
        """Close the session"""
        if self._session and not self._session.closed:
            await self._session.close()


# Global client instance
_global_client = AsyncPlaywrightClient()


def create_async_playwright_tools():
    """Create async-compatible Playwright tools for LangGraph ASGI servers"""
    
    # Use @tool decorator for proper async handling
    @tool
    async def take_browser_screenshot() -> str:
        """Take a screenshot of the Playwright stealth browser"""
        try:
            result = await _global_client._request("GET", "/screenshot")
            if result.get("success") and "image" in result:
                return "Screenshot captured successfully"
            else:
                return f"Screenshot failed: {result.get('error', 'Unknown error')}"
        except Exception as e:
            return f"Screenshot failed: {str(e)}"
    
    @tool
    async def navigate_to_url(url: str) -> str:
        """Navigate to a URL using the Playwright stealth browser"""
        try:
            result = await _global_client._request("POST", "/navigate", {"url": url})
            if result.get("success"):
                return f"Successfully navigated to {url}"
            else:
                return f"Navigation failed: {result.get('error', 'Unknown error')}"
        except Exception as e:
            return f"Navigation failed: {str(e)}"
    
    @tool
    async def click_at_coordinates(x: int, y: int) -> str:
        """CLICK anywhere on screen - buttons, links, like buttons, posts, menus. Use coordinates from DOM analysis."""
        try:
            result = await _global_client._request("POST", "/click", {"x": x, "y": y})
            if result.get("success"):
                return f"Successfully clicked at ({x}, {y})"
            else:
                return f"Click failed: {result.get('error', 'Unknown error')}"
        except Exception as e:
            return f"Click failed: {str(e)}"
    
    @tool
    async def type_text(text: str) -> str:
        """TYPE any text - usernames, passwords, comments, search terms. Works in any input field."""
        try:
            result = await _global_client._request("POST", "/type", {"text": text})
            if result.get("success"):
                return f"Successfully typed: {text}"
            else:
                return f"Type failed: {result.get('error', 'Unknown error')}"
        except Exception as e:
            return f"Type failed: {str(e)}"
    
    @tool
    async def press_key_combination(keys: List[str]) -> str:
        """Press key combinations using Playwright"""
        try:
            result = await _global_client._request("POST", "/key", {"keys": keys})
            if result.get("success"):
                return f"Successfully pressed keys: {'+'.join(keys)}"
            else:
                return f"Key press failed: {result.get('error', 'Unknown error')}"
        except Exception as e:
            return f"Key press failed: {str(e)}"
    
    @tool
    async def scroll_page(x: int, y: int, scroll_x: int = 0, scroll_y: int = 3) -> str:
        """Scroll page content using Playwright mouse wheel simulation"""
        try:
            result = await _global_client._request("POST", "/scroll", {
                "x": x, "y": y, "scroll_x": scroll_x, "scroll_y": scroll_y
            })
            if result.get("success"):
                return f"Successfully scrolled at ({x}, {y}) by ({scroll_x}, {scroll_y})"
            else:
                return f"Scroll failed: {result.get('error', 'Unknown error')}"
        except Exception as e:
            return f"Scroll failed: {str(e)}"
    
    @tool
    async def get_dom_elements() -> str:
        """Extract interactive DOM elements using Playwright"""
        try:
            result = await _global_client._request("GET", "/dom/elements")
            if result.get("success"):
                elements = result.get("elements", [])
                count = result.get("count", 0)
                
                # Format elements for LLM consumption
                element_info = []
                for el in elements[:15]:  # Limit for token efficiency
                    info = f"[{el['index']}] {el['tagName']}"
                    if el['text']:
                        info += f" '{el['text'][:40]}'"
                    if el['id']:
                        info += f" #{el['id']}"
                    info += f" @({el['x']},{el['y']})"
                    element_info.append(info)
                
                summary = f"Found {count} interactive elements:\n" + "\n".join(element_info)
                if count > 15:
                    summary += f"\n... and {count - 15} more elements"
                
                return summary
            else:
                return f"DOM extraction failed: {result.get('error', 'Unknown error')}"
        except Exception as e:
            return f"DOM extraction failed: {str(e)}"
    
    @tool
    async def get_page_info() -> str:
        """Get page information using Playwright with smart login status detection"""
        try:
            result = await _global_client._request("GET", "/dom/page_info")
            if result.get("success"):
                info = result.get("page_info", {})
                url = info.get('url', 'N/A')
                title = info.get('title', 'N/A')
                
                # Smart login status detection based on URL patterns
                login_status = ""
                if 'x.com/home' in url or 'twitter.com/home' in url:
                    login_status = " 🎉 LOGGED IN - Home page detected!"
                elif 'login' in url or 'sign' in url or 'flow' in url:
                    login_status = " 🔐 Not logged in - On login/signup page"
                elif 'x.com' in url and 'home' not in url and 'login' not in url:
                    login_status = " 🌐 On public X page"
                
                return f"Page: {title} | URL: {url} | Domain: {info.get('domain', 'N/A')} | Elements: {info.get('buttons', 0)} buttons, {info.get('links', 0)} links, {info.get('inputs', 0)} inputs{login_status}"
            else:
                return f"Page info failed: {result.get('error', 'Unknown error')}"
        except Exception as e:
            return f"Page info failed: {str(e)}"
    
    @tool
    async def get_enhanced_context() -> str:
        """Get enhanced context for agent analysis"""
        try:
            result = await _global_client._request("GET", "/dom/enhanced_context")
            if result.get("success"):
                page_info = result.get("page_info", {})
                element_count = result.get("element_count", 0)
                
                return f"""Enhanced Context Available:
📄 Page: {page_info.get('title', 'Unknown')} ({page_info.get('domain', 'Unknown')})
🎯 Interactive Elements: {element_count} found
📊 Content: {page_info.get('buttons', 0)} buttons, {page_info.get('links', 0)} links
🔍 Ready for analysis and interaction"""
            else:
                return f"Enhanced context failed: {result.get('error', 'Unknown error')}"
        except Exception as e:
            return f"Enhanced context failed: {str(e)}"

    @tool
    async def find_form_fields() -> str:
        """Find and categorize form fields (username, password, email, etc.) using semantic analysis"""
        try:
            result = await _global_client._request("GET", "/dom/elements")
            if result.get("success"):
                elements = result.get("elements", [])
                
                # Categorize form fields semantically
                form_fields = {
                    "username_fields": [],
                    "password_fields": [], 
                    "email_fields": [],
                    "text_fields": [],
                    "buttons": []
                }
                
                for el in elements:
                    tag = el.get('tagName', '').lower()
                    field_type = el.get('type', '').lower()
                    text = el.get('text', '').lower()
                    placeholder = el.get('placeholder', '').lower()
                    css_selector = el.get('cssSelector', '')
                    
                    field_info = {
                        "index": el['index'],
                        "selector": css_selector,
                        "coordinates": f"({el['x']}, {el['y']})",
                        "text": el.get('text', ''),
                        "placeholder": el.get('placeholder', '')
                    }
                    
                    if tag == 'input':
                        if field_type == 'password':
                            form_fields["password_fields"].append(field_info)
                        elif field_type == 'email' or 'email' in placeholder:
                            form_fields["email_fields"].append(field_info)
                        elif field_type == 'text' or field_type == '':
                            # Detect username fields by context
                            if any(keyword in placeholder + text for keyword in ['username', 'user', 'login', 'account']):
                                form_fields["username_fields"].append(field_info)
                            else:
                                form_fields["text_fields"].append(field_info)
                    elif tag == 'button':
                        if any(keyword in text for keyword in ['login', 'sign in', 'next', 'submit']):
                            form_fields["buttons"].append(field_info)
                
                # Format results
                result_lines = []
                for category, fields in form_fields.items():
                    if fields:
                        result_lines.append(f"\n🔍 {category.upper().replace('_', ' ')} ({len(fields)}):")
                        for field in fields:
                            result_lines.append(f"  [{field['index']}] CSS: {field['selector'][:60]}...")
                            if field['text']:
                                result_lines.append(f"      Text: '{field['text']}'")
                            if field['placeholder']:
                                result_lines.append(f"      Placeholder: '{field['placeholder']}'")
                
                return "Form Field Analysis:" + "\n".join(result_lines) if result_lines else "No form fields found"
                
            else:
                return f"Failed to analyze form fields: {result.get('error', 'Unknown error')}"
        except Exception as e:
            return f"Form field analysis failed: {str(e)}"

    @tool
    async def click_element_by_selector(css_selector: str) -> str:
        """CLICK any element using CSS selector - like buttons, posts, links, forms. More reliable than coordinates!"""
        try:
            # Use the enhanced click_selector endpoint
            result = await _global_client._request("POST", "/click_selector", {
                "selector": css_selector,
                "selector_type": "css"
            })
            if result.get("success"):
                return f"Successfully clicked element: {css_selector}"
            else:
                return f"Click by selector failed: {result.get('error', 'Unknown error')}"
        except Exception as e:
            return f"Click by selector failed: {str(e)}"

    @tool
    async def click_button_by_text(button_text: str) -> str:
        """CLICK a button by its visible text content. Much more reliable than CSS selectors!
        
        Args:
            button_text: The exact text on the button (e.g., "Next", "Sign in", "Close", "Submit")
        
        Examples:
        - click_button_by_text("Next") -> Clicks the Next button
        - click_button_by_text("Sign in") -> Clicks the Sign in button
        - click_button_by_text("Close") -> Clicks the Close button
        """
        try:
            # Use XPath to find button by exact text (using . which works better than text())
            xpath_selector = f"//button[.='{button_text}']"
            
            print(f"🎯 Looking for button with text: '{button_text}'")
            print(f"🔍 Using XPath: {xpath_selector}")
            
            result = await _global_client._request("POST", "/click_selector", {
                "selector": xpath_selector,
                "selector_type": "xpath"
            })
            
            if result.get("success"):
                return f"✅ Successfully clicked '{button_text}' button using XPath!"
            else:
                # Fallback: Try case-insensitive partial match
                partial_xpath = f"//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{button_text.lower()}')]"
                print(f"⚠️ Exact match failed, trying case-insensitive partial match...")
                
                fallback_result = await _global_client._request("POST", "/click_selector", {
                    "selector": partial_xpath,
                    "selector_type": "xpath"
                })
                
                if fallback_result.get("success"):
                    return f"✅ Successfully clicked '{button_text}' button using case-insensitive XPath match!"
                else:
                    return f"❌ Could not find button with text '{button_text}'. Available buttons might have different text."
        except Exception as e:
            return f"Click button by text failed: {str(e)}"

    @tool
    async def fill_input_field(css_selector: str, text: str) -> str:
        """Fill an input field using its CSS selector and text. Falls back to coordinates if CSS fails."""
        try:
            # First try CSS selector approach
            selector_and_text = f"{css_selector}|||{text}"
            result = await _global_client._request("POST", "/fill_selector", {
                "selector": selector_and_text,
                "selector_type": "css"
            })
            
            if result.get("success"):
                return f"✅ Successfully filled field with CSS selector with text: {text}"
            else:
                print(f"⚠️ CSS selector failed, trying coordinate fallback...")
                
                # Fallback: Find the input field by CSS and use coordinates
                dom_result = await _global_client._request("GET", "/dom/elements")
                if dom_result.get("success"):
                    elements = dom_result.get("elements", [])
                    
                    # Find input field that matches (approximately) the CSS selector
                    target_input = None
                    for el in elements:
                        if el.get("tagName") == "input":
                            el_css = el.get("cssSelector", "")
                            # Simple match: if selector contains key classes from our target
                            if any(cls in el_css for cls in css_selector.split(".")[:3]):
                                target_input = el
                                break
                    
                    if target_input:
                        # Click on the input field first
                        x, y = target_input.get("x"), target_input.get("y")
                        click_result = await _global_client._request("POST", "/click", {"x": x, "y": y})
                        
                        if click_result.get("success"):
                            # Then type the text
                            type_result = await _global_client._request("POST", "/type", {"text": text})
                            if type_result.get("success"):
                                return f"✅ Successfully filled field using coordinates ({x}, {y}) with text: {text}"
                            else:
                                return f"❌ Coordinate click succeeded but typing failed: {type_result.get('error')}"
                        else:
                            return f"❌ Coordinate click failed: {click_result.get('error')}"
                    else:
                        return f"❌ Could not find input field for CSS selector: {css_selector}"
                else:
                    return f"❌ CSS selector failed and could not get DOM for fallback: {result.get('error', 'Unknown error')}"
                    
        except Exception as e:
            return f"Fill field failed: {str(e)}"
    
    @tool
    async def enter_username(username: str) -> str:
        """
        ENTER USERNAME into login forms intelligently.
        
        This tool combines smart form detection with robust input methods:
        1. Automatically finds username/email input fields
        2. Uses CSS selector filling (preferred)
        3. Falls back to coordinate-based clicking + typing
        4. Handles various input field types (text, email, tel)
        
        Args:
            username: The username/email to enter (e.g., "rajath_db", "user@example.com")
        
        Examples:
        - enter_username("rajath_db") -> Enters username into login form
        - enter_username("user@domain.com") -> Enters email into email field
        
        More reliable than using type_text alone as it intelligently locates the correct input field.
        """
        try:
            print(f"🔐 ENTER USERNAME: '{username}'")
            
            # Step 1: Find form fields to identify username/email inputs
            print("🔍 Step 1: Analyzing form fields...")
            form_result = await find_form_fields.arun({})
            
            # Parse the form analysis to get username field info
            username_field = None
            email_field = None
            
            # Get DOM elements for detailed analysis
            dom_result = await _global_client._request("GET", "/dom/elements")
            if not dom_result.get("success"):
                return f"❌ Failed to get page elements: {dom_result.get('error')}"
            
            elements = dom_result.get("elements", [])
            
            # Find the best input field for username
            candidate_fields = []
            
            for el in elements:
                if el.get('tagName') == 'input':
                    field_type = el.get('type', '').lower()
                    placeholder = el.get('placeholder', '').lower()
                    aria_label = el.get('ariaLabel', '').lower()
                    css_selector = el.get('cssSelector', '')
                    
                    # Score this field for username suitability
                    score = 0
                    field_purpose = "unknown"
                    
                    # Check for username indicators
                    username_keywords = ['username', 'user', 'login', 'account', 'handle']
                    email_keywords = ['email', 'mail']
                    phone_keywords = ['phone', 'tel', 'mobile']
                    
                    if field_type in ['text', 'email', 'tel', '']:
                        if field_type == 'email':
                            score += 10
                            field_purpose = "email"
                        elif field_type == 'tel':
                            score += 8
                            field_purpose = "phone"
                        elif field_type == 'text' or field_type == '':
                            score += 6
                            field_purpose = "text"
                        
                        # Check placeholder text
                        for keyword in username_keywords:
                            if keyword in placeholder:
                                score += 15
                                field_purpose = "username"
                                break
                        
                        for keyword in email_keywords:
                            if keyword in placeholder:
                                score += 12
                                field_purpose = "email"
                                break
                        
                        for keyword in phone_keywords:
                            if keyword in placeholder:
                                score += 10
                                field_purpose = "phone"
                                break
                        
                        # Check aria-label
                        for keyword in username_keywords + email_keywords:
                            if keyword in aria_label:
                                score += 8
                                break
                        
                        if score > 0:
                            candidate_fields.append({
                                'element': el,
                                'score': score,
                                'purpose': field_purpose,
                                'css_selector': css_selector,
                                'placeholder': placeholder,
                                'type': field_type,
                                'coordinates': (el.get('x'), el.get('y'))
                            })
            
            # Sort by score (highest first)
            candidate_fields.sort(key=lambda x: x['score'], reverse=True)
            
            print(f"📊 Found {len(candidate_fields)} potential username fields:")
            for i, field in enumerate(candidate_fields[:3]):
                print(f"  {i+1}. {field['purpose']} field (score: {field['score']}) - {field['type']} - '{field['placeholder']}'")
            
            if not candidate_fields:
                return f"❌ No suitable username/email input fields found on the page"
            
            # Step 2: Try to fill the best candidate field
            best_field = candidate_fields[0]
            css_selector = best_field['css_selector']
            coordinates = best_field['coordinates']
            
            print(f"🎯 Step 2: Using {best_field['purpose']} field (score: {best_field['score']})")
            print(f"   CSS: {css_selector}")
            print(f"   Coordinates: {coordinates}")
            
            # Method 1: Try CSS selector approach (preferred)
            if css_selector:
                print("🔧 Method 1: Trying CSS selector approach...")
                fill_result = await fill_input_field.arun({
                    "css_selector": css_selector,
                    "text": username
                })
                
                if "Successfully filled field" in fill_result:
                    return f"✅ Successfully entered username '{username}' using CSS selector! 🔐"
                else:
                    print(f"⚠️ CSS approach failed: {fill_result}")
            
            # Method 2: Fallback to coordinates + click + type
            print("🔧 Method 2: Trying coordinate-based approach...")
            x, y = coordinates
            
            if x is not None and y is not None:
                # Click on the input field first
                click_result = await _global_client._request("POST", "/click", {"x": x, "y": y})
                if click_result.get("success"):
                    print(f"✅ Clicked on input field at ({x}, {y})")
                    
                    # Wait a moment for focus
                    await asyncio.sleep(0.5)
                    
                    # Clear any existing content (Ctrl+A, Delete)
                    await _global_client._request("POST", "/key", {"keys": ["ctrl", "a"]})
                    await asyncio.sleep(0.2)
                    
                    # Type the username
                    type_result = await _global_client._request("POST", "/type", {"text": username})
                    if type_result.get("success"):
                        return f"✅ Successfully entered username '{username}' using coordinates! 🔐"
                    else:
                        return f"❌ Clicked field but typing failed: {type_result.get('error')}"
                else:
                    return f"❌ Failed to click on input field: {click_result.get('error')}"
            else:
                return f"❌ Invalid coordinates for input field: {coordinates}"
                
        except Exception as e:
            return f"Enter username failed: {str(e)}"

    @tool
    async def enter_password(password: str) -> str:
        """
        ENTER PASSWORD into login forms intelligently.
        
        This tool specifically targets password input fields:
        1. Automatically finds password input fields (type="password")
        2. Uses CSS selector filling (preferred)
        3. Falls back to coordinate-based clicking + typing
        4. Handles password field security properly
        
        Args:
            password: The password to enter
        
        Examples:
        - enter_password("mySecretPass123") -> Enters password into password field
        
        More reliable than type_text as it specifically targets password fields.
        """
        try:
            print(f"🔐 ENTER PASSWORD: {'*' * len(password)}")
            
            # Get DOM elements to find password fields
            print("🔍 Looking for password input fields...")
            dom_result = await _global_client._request("GET", "/dom/elements")
            if not dom_result.get("success"):
                return f"❌ Failed to get page elements: {dom_result.get('error')}"
            
            elements = dom_result.get("elements", [])
            
            # Find password input fields
            password_fields = []
            for el in elements:
                if (el.get('tagName') == 'input' and 
                    el.get('type', '').lower() == 'password'):
                    password_fields.append(el)
            
            print(f"📊 Found {len(password_fields)} password fields")
            
            if not password_fields:
                return f"❌ No password input fields found on the page"
            
            # Use the first (and typically only) password field
            password_field = password_fields[0]
            css_selector = password_field.get('cssSelector', '')
            x = password_field.get('x')
            y = password_field.get('y')
            
            print(f"🎯 Using password field at ({x}, {y})")
            
            # Method 1: Try CSS selector approach (preferred)
            if css_selector:
                print("🔧 Method 1: Trying CSS selector approach...")
                fill_result = await fill_input_field.arun({
                    "css_selector": css_selector,
                    "text": password
                })
                
                if "Successfully filled field" in fill_result:
                    return f"✅ Successfully entered password using CSS selector! 🔐"
                else:
                    print(f"⚠️ CSS approach failed: {fill_result}")
            
            # Method 2: Fallback to coordinates + click + type
            print("🔧 Method 2: Trying coordinate-based approach...")
            
            if x is not None and y is not None:
                # Click on the password field
                click_result = await _global_client._request("POST", "/click", {"x": x, "y": y})
                if click_result.get("success"):
                    print(f"✅ Clicked on password field at ({x}, {y})")
                    
                    # Wait a moment for focus
                    await asyncio.sleep(0.5)
                    
                    # Clear any existing content
                    await _global_client._request("POST", "/key", {"keys": ["ctrl", "a"]})
                    await asyncio.sleep(0.2)
                    
                    # Type the password
                    type_result = await _global_client._request("POST", "/type", {"text": password})
                    if type_result.get("success"):
                        return f"✅ Successfully entered password using coordinates! 🔐"
                    else:
                        return f"❌ Clicked field but typing failed: {type_result.get('error')}"
                else:
                    return f"❌ Failed to click on password field: {click_result.get('error')}"
            else:
                return f"❌ Invalid coordinates for password field: ({x}, {y})"
                
        except Exception as e:
            return f"Enter password failed: {str(e)}"

    @tool
    async def check_login_success() -> str:
        """Check if login was successful by analyzing URL and page content"""
        try:
            result = await _global_client._request("GET", "/dom/page_info")
            if result.get("success"):
                info = result.get("page_info", {})
                url = info.get('url', '')
                title = info.get('title', '')
                
                # Multiple indicators of successful login
                success_indicators = []
                
                if 'x.com/home' in url or 'twitter.com/home' in url:
                    success_indicators.append("✅ URL shows home page")
                
                if 'home' in title.lower() and 'x' in title.lower():
                    success_indicators.append("✅ Page title indicates home")
                
                # Check for typical logged-in elements
                dom_result = await _global_client._request("GET", "/dom/elements")
                if dom_result.get("success"):
                    elements = dom_result.get("elements", [])
                    for el in elements:
                        text = el.get('text', '').lower()
                        if any(phrase in text for phrase in ['compose', 'tweet', 'timeline', 'for you', 'following']):
                            success_indicators.append("✅ Logged-in interface elements detected")
                            break
                
                if success_indicators:
                    return f"🎉 LOGIN SUCCESSFUL!\n" + "\n".join(success_indicators) + f"\n📍 Current URL: {url}"
                else:
                    return f"❌ Login appears unsuccessful or still in progress\n📍 Current URL: {url}\n📄 Page title: {title}"
            
            else:
                return f"Failed to check login status: {result.get('error', 'Unknown error')}"
        except Exception as e:
            return f"Login check failed: {str(e)}"

    @tool
    async def get_comprehensive_context() -> str:
        """
        Enhanced workflow: Take screenshot -> OmniParser analysis -> Playwright DOM -> Combined context
        This is the main tool for getting complete visual and semantic understanding of the page.
        """
        try:
            print("🔍 Starting comprehensive context analysis...")
            
            # Step 1: Take screenshot using Playwright
            screenshot_result = await _global_client._request("GET", "/screenshot")
            if not screenshot_result.get("success"):
                return f"Failed to take screenshot: {screenshot_result.get('error', 'Unknown error')}"
            
            # Clean base64 image
            screenshot_b64 = screenshot_result.get("image", "")
            if screenshot_b64.startswith("data:image/png;base64,"):
                screenshot_b64 = screenshot_b64.replace("data:image/png;base64,", "")
            
            print("📸 Screenshot captured")
            
            # Step 2: Get OmniParser visual analysis
            omni_context = ""
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        "http://localhost:8003/parse/",
                        json={"base64_image": screenshot_b64},
                        timeout=aiohttp.ClientTimeout(total=30)
                    ) as response:
                        if response.status == 200:
                            omni_data = await response.json()
                            
                            # Extract OmniParser elements
                            omni_elements = omni_data.get("parsed_content_list", [])
                            annotated_image = omni_data.get("som_image_base64", "")
                            latency = omni_data.get("latency", 0)
                            
                            print(f"🎯 OmniParser detected {len(omni_elements)} visual elements")
                            
                            omni_context = f"\\n🔍 OMNIPARSER VISUAL ANALYSIS ({len(omni_elements)} elements):\\n"
                            for i, elem in enumerate(omni_elements[:10]):  # Top 10 elements
                                elem_text = elem.get('text', '').strip()
                                elem_type = elem.get('element_type', 'unknown')
                                bbox = elem.get('bbox', [0, 0, 0, 0])
                                
                                omni_context += f"  [{i+1}] {elem_type}: '{elem_text}' @bbox{bbox}\\n"
                            
                            if annotated_image:
                                omni_context += "✅ Annotated image with bounding boxes available\\n"
                        else:
                            print(f"⚠️ OmniParser failed: {response.status}")
                            omni_context = "⚠️ OmniParser visual analysis not available\\n"
            
            except Exception as e:
                print(f"⚠️ OmniParser error: {e}")
                omni_context = f"⚠️ OmniParser error: {str(e)}\\n"
            
            # Step 3: Get Playwright DOM analysis  
            page_info_result = await _global_client._request("GET", "/dom/page_info")
            dom_result = await _global_client._request("GET", "/dom/elements")
            
            # Step 3.5: Get actual page text content directly from Playwright
            page_text_result = await _global_client._request("GET", "/page_text")
            
            page_context = ""
            if page_info_result.get("success"):
                info = page_info_result.get("page_info", {})
                page_context = f"\\n📄 PAGE INFO:\\nURL: {info.get('url', 'Unknown')}\\nTitle: {info.get('title', 'Unknown')}\\nDomain: {info.get('domain', 'Unknown')}\\n"
            
            dom_context = ""
            page_text_content = ""
            if dom_result.get("success"):
                elements = dom_result.get("elements", [])
                dom_context = f"\\n🌐 PLAYWRIGHT DOM ANALYSIS ({len(elements)} interactive elements):\\n"
                
                # Categorize DOM elements
                input_fields = [el for el in elements if el.get('tagName') == 'input']
                buttons = [el for el in elements if el.get('tagName') == 'button']
                links = [el for el in elements if el.get('tagName') == 'a']
                
                dom_context += f"  📝 Input fields: {len(input_fields)}\\n"
                dom_context += f"  🔘 Buttons: {len(buttons)}\\n"
                dom_context += f"  🔗 Links: {len(links)}\\n"
                
                # Show key interactive elements with CSS selectors
                key_elements = input_fields[:3] + buttons[:3] + links[:3]
                if key_elements:
                    dom_context += "\\n🎯 Key Interactive Elements:\\n"
                    for i, el in enumerate(key_elements):
                        tag = el.get('tagName', 'unknown')
                        text = el.get('text', '')[:50]
                        css_sel = el.get('cssSelector', 'No CSS selector')
                        dom_context += f"  [{i+1}] {tag}: '{text}' | CSS: {css_sel[:60]}...\\n"
                
            # Extract page text content from direct Playwright call
            page_text_content = ""
            if page_text_result.get("success"):
                # Use direct Playwright page text extraction
                page_text = page_text_result.get("text", "")
                if page_text:
                    # Limit to reasonable size for LLM context
                    if len(page_text) > 2000:
                        page_text_content = f"\\n📄 PAGE TEXT CONTENT (first 2000 chars from Playwright):\\n{page_text[:2000]}...\\n"
                    else:
                        page_text_content = f"\\n📄 PAGE TEXT CONTENT (from Playwright):\\n{page_text}\\n"
            else:
                # Fallback: Extract from DOM elements if direct method fails
                if dom_result.get("success"):
                    elements = dom_result.get("elements", [])
                    all_text_elements = []
                    for el in elements:
                        text = el.get('text', '').strip()
                        if text and len(text) > 3:  # Filter meaningful text
                            all_text_elements.append(text)
                    
                    # Combine all text content
                    combined_text = ' '.join(all_text_elements)
                    if combined_text:
                        # Limit to reasonable size for LLM context
                        if len(combined_text) > 2000:
                            page_text_content = f"\\n📄 PAGE TEXT CONTENT (fallback from DOM):\\n{combined_text[:2000]}...\\n"
                        else:
                            page_text_content = f"\\n📄 PAGE TEXT CONTENT (fallback from DOM):\\n{combined_text}\\n"
            
            # Step 4: Combine everything into comprehensive context
            comprehensive_context = f"""🔍 COMPREHENSIVE PAGE CONTEXT
{page_context}
{omni_context}
{dom_context}
{page_text_content}
📸 SCREENSHOT: Available as base64 data for visual analysis

🎯 ANALYSIS READY: This context combines visual (OmniParser) + semantic (Playwright DOM) + actual page content.

⚠️ IMPORTANT DISTINCTION:
- 👁️ VISUAL CONTENT (OmniParser): Text you see in images, graphics, screenshots
- 📝 HTML TEXT CONTENT (Playwright): Actual selectable, searchable text in the page
- 🎯 FOR INTERACTIONS: Use HTML text content for like_post(), unlike_post(), and other tools
- 👀 FOR DESCRIPTION: Use visual content to describe what you see to users

Use this information to understand what's visible, interactable, and readable on the current page."""
            
            return comprehensive_context
            
        except Exception as e:
            return f"Comprehensive context failed: {str(e)}"

    @tool
    async def get_screenshot_with_analysis() -> str:
        """Get screenshot with visual analysis for multimodal LLMs that can see images"""
        try:
            # Take screenshot
            screenshot_result = await _global_client._request("GET", "/screenshot")
            if not screenshot_result.get("success"):
                return f"Failed to take screenshot: {screenshot_result.get('error', 'Unknown error')}"
            
            # Get the base64 image
            screenshot_b64 = screenshot_result.get("image", "")
            
            # Get comprehensive text analysis
            comprehensive_result = await get_comprehensive_context.arun({})
            
            # Return format that works with multimodal LLMs
            return f"""SCREENSHOT WITH ANALYSIS:

{comprehensive_result}

SCREENSHOT_DATA: {screenshot_b64}

🎯 This includes both the visual screenshot and comprehensive text analysis."""
            
        except Exception as e:
            return f"Screenshot with analysis failed: {str(e)}"

    @tool
    async def like_post(author_or_content: str) -> str:
        """
        LIKE a specific post on social media by identifying it precisely.
        
        Args:
            author_or_content: Specific identifier for the post:
                             - Author name: "akshay", "@akshay_pachaar" 
                             - Specific content: "dots-ocr 1.7B vision-language"
                             - Company: "LangChain", "OpenAI", "Anthropic"
                             - Unique phrases: "100+ languages", "open-source OCR"
        
        Examples:
        - like_post("akshay") -> Likes Akshay's post about dots-ocr
        - like_post("dots-ocr vision-language") -> Likes the specific OCR model post
        - like_post("LangChain DeepAgent") -> Likes LangChain's DeepAgent post
        
        This tool finds the exact post and clicks its corresponding like button.
        """
        try:
            print(f"🔍 Looking for post by: '{author_or_content}'")
            
            # Get DOM elements to find like buttons
            result = await _global_client._request("GET", "/dom/elements")
            if not result.get("success"):
                return f"Failed to get page elements: {result.get('error', 'Unknown error')}"
            
            elements = result.get("elements", [])
            
            # Find like buttons and posts more precisely
            like_buttons = []
            individual_posts = []
            
            for el in elements:
                # Look for like buttons using data-testid (more reliable)
                test_id = el.get('testId', '')
                aria_label = el.get('ariaLabel', '').lower()
                
                # Primary method: Use data-testid="like"
                if test_id == 'like' or (test_id == '' and 'like' in aria_label and 'likes' in aria_label):
                    like_buttons.append(el)
                
                # Look for individual posts (articles or substantial content blocks)
                tag_name = el.get('tagName', '').lower()
                text = el.get('text', '')
                
                # Focus on article tags or substantial content that looks like individual posts
                if tag_name == 'article' or (len(text) > 100 and len(text) < 2000):
                    # Exclude navigation/timeline aggregations
                    if not ('for you' in text.lower() and 'following' in text.lower() and len(text) > 1000):
                        individual_posts.append(el)
            
            print(f"📊 Found {len(like_buttons)} like buttons and {len(individual_posts)} individual posts")
            
            # Find the specific post with better matching
            target_post = None
            target_like_button = None
            
            search_term = author_or_content.lower()
            
            print(f"🔍 Searching through {len(individual_posts)} posts for: '{search_term}'")
            
            for i, post_el in enumerate(individual_posts):
                content_text = post_el.get('text', '').lower()
                
                # Enhanced matching - check for author names, content, or specific phrases
                is_match = False
                match_reason = ""
                
                if search_term in content_text:
                    is_match = True
                    match_reason = f"Contains '{search_term}'"
                
                # Special handling for author matching
                if '@' in search_term or any(name in search_term for name in ['akshay', 'langchain', 'openai', 'anthropic']):
                    # Check for author mentions
                    if search_term.replace('@', '') in content_text:
                        is_match = True
                        match_reason = f"Author match: '{search_term}'"
                
                if is_match:
                    target_post = post_el
                    print(f"✅ Found target post #{i+1}: {match_reason}")
                    print(f"📍 Post position: ({post_el.get('x')}, {post_el.get('y')})")
                    print(f"📝 Post preview: '{content_text[:200]}...'")
                    
                    # Find the closest like button to this specific post
                    post_y = post_el.get('y', 0)
                    post_x = post_el.get('x', 0)
                    closest_button = None
                    min_distance = float('inf')
                    
                    print(f"🔍 Looking for like buttons near this post at y={post_y}")
                    
                    for like_btn in like_buttons:
                        btn_y = like_btn.get('y', 0)
                        btn_x = like_btn.get('x', 0)
                        
                        # Like buttons should be close to the post (within ~600px vertically, below the post)
                        y_distance = btn_y - post_y  # Distance below the post
                        
                        print(f"  Like button '{like_btn.get('ariaLabel', '')}' at ({btn_x}, {btn_y}) - distance: {abs(y_distance)}px {'below' if y_distance > 0 else 'above'}")
                        
                        # Like buttons are typically BELOW posts, within reasonable range
                        if 0 < y_distance < 600 and y_distance < min_distance:
                            min_distance = y_distance
                            closest_button = like_btn
                    
                    if closest_button:
                        target_like_button = closest_button
                        print(f"🎯 Selected like button: '{closest_button.get('ariaLabel')}' at ({closest_button.get('x')}, {closest_button.get('y')}) - {min_distance}px away")
                        
                        # Ensure the post is visible by scrolling to it if needed
                        if post_y < 0 or post_y > 1000:
                            print(f"📜 Post is off-screen (y={post_y}), scrolling to make it visible...")
                            scroll_result = await _global_client._request("POST", "/scroll", {
                                "x": 500, "y": 500, "scroll_x": 0, "scroll_y": -3 if post_y < 0 else 3
                            })
                            print(f"Scroll result: {scroll_result.get('success', False)}")
                            
                            # Wait a moment for scroll to complete
                            await asyncio.sleep(1)
                            
                            # Re-get DOM elements after scrolling
                            print("🔄 Re-getting elements after scroll...")
                            new_result = await _global_client._request("GET", "/dom/elements")
                            if new_result.get("success"):
                                new_elements = new_result.get("elements", [])
                                # Find the like button again
                                for el in new_elements:
                                    if el.get('ariaLabel') == closest_button.get('ariaLabel'):
                                        # Update coordinates
                                        target_like_button = el
                                        print(f"🔄 Updated like button position: ({el.get('x')}, {el.get('y')})")
                                        break
                        
                        break
                    else:
                        print(f"❌ No like button found within 400px of this post")
                        # Continue searching other posts
                        target_post = None
            
            if not target_post:
                return f"❌ Could not find a post by '{author_or_content}'. Try being more specific (e.g., 'akshay', 'dots-ocr', '@username')."
            
            if not target_like_button:
                return f"❌ Found the post by '{author_or_content}' but couldn't locate its like button."
            
            # Use COORDINATES (CSS selectors are too generic on X/Twitter)
            x = target_like_button.get('x')
            y = target_like_button.get('y')
            aria_label = target_like_button.get('ariaLabel', '')
            
            print(f"🎯 Clicking like button: '{aria_label}' at coordinates ({x}, {y})")
            
            # Validate coordinates are reasonable for a like button
            if x is None or y is None:
                return f"❌ Invalid coordinates for like button"
            
            if x < 400 or x > 600 or y < -2000 or y > 3000:
                print(f"⚠️ WARNING: Coordinates ({x}, {y}) seem unusual for a like button")
            
            print(f"🔧 Using precise coordinates: ({x}, {y})")
            click_result = await _global_client._request("POST", "/click", {"x": x, "y": y})
            
            if click_result.get("success"):
                # Wait a moment for the UI to update
                await asyncio.sleep(1)
                
                # Verify the like actually worked by checking button state
                dom_check = await _global_client._request("GET", "/dom/elements")
                if dom_check.get("success"):
                    elements = dom_check.get("elements", [])
                    for el in elements:
                        # Find the same button by proximity
                        if (abs(el.get('x', 0) - x) < 10 and abs(el.get('y', 0) - y) < 10 and 
                            'like' in el.get('ariaLabel', '').lower()):
                            new_aria_label = el.get('ariaLabel', '')
                            if 'liked' in new_aria_label.lower():
                                return f"✅ Successfully liked the post by '{author_or_content}'! 👍 (Button: {new_aria_label})"
                            else:
                                return f"⚠️ Clicked like button but status unclear. Button shows: {new_aria_label}"
                            break
                
                # Fallback response if verification fails
                return f"✅ Clicked like button for post by '{author_or_content}' - please check visually! (Button: {aria_label})"
            else:
                return f"❌ Failed to click like button: {click_result.get('error', 'Unknown error')}"
                
        except Exception as e:
            return f"Like post failed: {str(e)}"

    @tool
    async def unlike_post(author_or_content: str) -> str:
        """
        UNLIKE a specific post on social media by identifying it precisely.
        
        Args:
            author_or_content: Specific identifier for the post:
                             - Author name: "akshay", "@akshay_pachaar" 
                             - Specific content: "dots-ocr 1.7B vision-language"
                             - Company: "LangChain", "OpenAI", "Anthropic"
                             - Unique phrases: "100+ languages", "open-source OCR"
        
        Examples:
        - unlike_post("akshay") -> Unlikes Akshay's post about dots-ocr
        - unlike_post("PDF chatbot") -> Unlikes the PDF chatbot post
        - unlike_post("LangChain DeepAgent") -> Unlikes LangChain's DeepAgent post
        
        This tool finds posts that are already liked and unlikes them.
        """
        try:
            print(f"🔍 Looking for LIKED post by: '{author_or_content}' to unlike")
            
            # Get DOM elements to find like buttons
            result = await _global_client._request("GET", "/dom/elements")
            if not result.get("success"):
                return f"Failed to get page elements: {result.get('error', 'Unknown error')}"
            
            elements = result.get("elements", [])
            
            # Find like buttons and posts more precisely
            liked_buttons = []  # Only buttons that show "Liked" status
            individual_posts = []
            
            for el in elements:
                # Look for LIKED buttons (showing "Liked" status)
                test_id = el.get('testId', '')
                aria_label = el.get('ariaLabel', '').lower()
                if (test_id == 'like' and 'liked' in aria_label) or ('liked' in aria_label and 'like' in aria_label):
                    liked_buttons.append(el)
                
                # Look for individual posts (articles or substantial content blocks)
                tag_name = el.get('tagName', '').lower()
                text = el.get('text', '')
                
                # Focus on article tags or substantial content that looks like individual posts
                if tag_name == 'article' or (len(text) > 100 and len(text) < 2000):
                    # Exclude navigation/timeline aggregations
                    if not ('for you' in text.lower() and 'following' in text.lower() and len(text) > 1000):
                        individual_posts.append(el)
            
            print(f"📊 Found {len(liked_buttons)} already liked buttons and {len(individual_posts)} individual posts")
            
            if not liked_buttons:
                return f"❌ No liked posts found to unlike. All posts might already be unliked."
            
            # Find the specific post with better matching
            target_post = None
            target_unlike_button = None
            
            search_term = author_or_content.lower()
            
            print(f"🔍 Searching through {len(individual_posts)} posts for: '{search_term}'")
            
            for i, post_el in enumerate(individual_posts):
                content_text = post_el.get('text', '').lower()
                
                # Enhanced matching - check for author names, content, or specific phrases
                is_match = False
                match_reason = ""
                
                if search_term in content_text:
                    is_match = True
                    match_reason = f"Contains '{search_term}'"
                
                # Special handling for author matching
                if '@' in search_term or any(name in search_term for name in ['akshay', 'langchain', 'openai', 'anthropic']):
                    # Check for author mentions
                    if search_term.replace('@', '') in content_text:
                        is_match = True
                        match_reason = f"Author match: '{search_term}'"
                
                if is_match:
                    target_post = post_el
                    print(f"✅ Found target post #{i+1}: {match_reason}")
                    print(f"📍 Post position: ({post_el.get('x')}, {post_el.get('y')})")
                    print(f"📝 Post preview: '{content_text[:200]}...'")
                    
                    # Find the closest LIKED button to this specific post
                    post_y = post_el.get('y', 0)
                    post_x = post_el.get('x', 0)
                    closest_button = None
                    min_distance = float('inf')
                    
                    print(f"🔍 Looking for LIKED buttons near this post at y={post_y}")
                    
                    for like_btn in liked_buttons:
                        btn_y = like_btn.get('y', 0)
                        btn_x = like_btn.get('x', 0)
                        
                        # Like buttons should be close to the post (within ~600px vertically, below the post)
                        y_distance = btn_y - post_y  # Distance below the post
                        
                        print(f"  Liked button '{like_btn.get('ariaLabel', '')}' at ({btn_x}, {btn_y}) - distance: {abs(y_distance)}px {'below' if y_distance > 0 else 'above'}")
                        
                        # Like buttons are typically BELOW posts, within reasonable range
                        if 0 < y_distance < 600 and y_distance < min_distance:
                            min_distance = y_distance
                            closest_button = like_btn
                    
                    if closest_button:
                        target_unlike_button = closest_button
                        print(f"🎯 Selected liked button to unlike: '{closest_button.get('ariaLabel')}' at ({closest_button.get('x')}, {closest_button.get('y')}) - {min_distance}px away")
                        
                        # Ensure the post is visible by scrolling to it if needed
                        if post_y < 0 or post_y > 1000:
                            print(f"📜 Post is off-screen (y={post_y}), scrolling to make it visible...")
                            scroll_result = await _global_client._request("POST", "/scroll", {
                                "x": 500, "y": 500, "scroll_x": 0, "scroll_y": -3 if post_y < 0 else 3
                            })
                            print(f"Scroll result: {scroll_result.get('success', False)}")
                            
                            # Wait a moment for scroll to complete
                            await asyncio.sleep(1)
                            
                            # Re-get DOM elements after scrolling
                            print("🔄 Re-getting elements after scroll...")
                            new_result = await _global_client._request("GET", "/dom/elements")
                            if new_result.get("success"):
                                new_elements = new_result.get("elements", [])
                                # Find the like button again
                                for el in new_elements:
                                    if el.get('ariaLabel') == closest_button.get('ariaLabel'):
                                        # Update coordinates
                                        target_unlike_button = el
                                        print(f"🔄 Updated like button position: ({el.get('x')}, {el.get('y')})")
                                        break
                        
                        break
                    else:
                        print(f"❌ No liked button found within 600px of this post")
                        # Continue searching other posts
                        target_post = None
            
            if not target_post:
                return f"❌ Could not find a liked post by '{author_or_content}'. Try being more specific or the post might not be liked."
            
            if not target_unlike_button:
                return f"❌ Found the post by '{author_or_content}' but couldn't locate a liked button to unlike."
            
            # Use COORDINATES to unlike the post
            x = target_unlike_button.get('x')
            y = target_unlike_button.get('y')
            aria_label = target_unlike_button.get('ariaLabel', '')
            
            print(f"🎯 Clicking unlike button: '{aria_label}' at coordinates ({x}, {y})")
            
            # Validate coordinates are reasonable for a like button
            if x is None or y is None:
                return f"❌ Invalid coordinates for unlike button"
            
            if x < 400 or x > 600 or y < -2000 or y > 3000:
                print(f"⚠️ WARNING: Coordinates ({x}, {y}) seem unusual for a like button")
            
            print(f"🔧 Using precise coordinates: ({x}, {y})")
            click_result = await _global_client._request("POST", "/click", {"x": x, "y": y})
            
            if click_result.get("success"):
                # Wait a moment for the UI to update
                await asyncio.sleep(1)
                
                # Verify the unlike actually worked by checking button state
                dom_check = await _global_client._request("GET", "/dom/elements")
                if dom_check.get("success"):
                    elements = dom_check.get("elements", [])
                    for el in elements:
                        # Find the same button by proximity
                        if (abs(el.get('x', 0) - x) < 10 and abs(el.get('y', 0) - y) < 10 and 
                            'like' in el.get('ariaLabel', '').lower()):
                            new_aria_label = el.get('ariaLabel', '')
                            if 'liked' not in new_aria_label.lower() and 'like' in new_aria_label.lower():
                                return f"✅ Successfully unliked the post by '{author_or_content}'! 💔 (Button: {new_aria_label})"
                            else:
                                return f"⚠️ Clicked unlike button but status unclear. Button shows: {new_aria_label}"
                            break
                
                # Fallback response if verification fails
                return f"✅ Clicked unlike button for post by '{author_or_content}' - please check visually! (Button: {aria_label})"
            else:
                return f"❌ Failed to click unlike button: {click_result.get('error', 'Unknown error')}"
                
        except Exception as e:
            return f"Unlike post failed: {str(e)}"

    @tool
    async def comment_on_post(author_or_content: str, comment_text: str) -> str:
        """
        COMMENT on a specific post on social media by identifying it precisely.
        
        Args:
            author_or_content: Specific identifier for the post:
                             - Author name: "akshay", "@akshay_pachaar" 
                             - Specific content: "dots-ocr 1.7B vision-language"
                             - Company: "LangChain", "OpenAI", "Anthropic"
                             - Unique phrases: "100+ languages", "open-source OCR"
            comment_text: The text to comment/reply with (e.g., "Great work!", "This is amazing!")
        
        Examples:
        - comment_on_post("akshay", "Amazing work on the OCR model!")
        - comment_on_post("PDF chatbot", "Love this idea! How can I try it?")
        - comment_on_post("LangChain DeepAgent", "When will this be available?")
        
        This tool finds the exact post, clicks its reply button, and posts a comment.
        """
        try:
            print(f"💬 Looking for post by: '{author_or_content}' to comment: '{comment_text}'")
            
            # Get DOM elements to find reply buttons and posts
            result = await _global_client._request("GET", "/dom/elements")
            if not result.get("success"):
                return f"Failed to get page elements: {result.get('error', 'Unknown error')}"
            
            elements = result.get("elements", [])
            
            # Find reply buttons and posts
            reply_buttons = []
            individual_posts = []
            
            for el in elements:
                # Look for reply buttons using data-testid (most reliable)
                test_id = el.get('testId', '')
                aria_label = el.get('ariaLabel', '').lower()
                
                # Primary method: Use data-testid="reply"
                if test_id == 'reply' or ('reply' in aria_label and 'replies' in aria_label):
                    reply_buttons.append(el)
                
                # Look for individual posts (articles or substantial content blocks)
                tag_name = el.get('tagName', '').lower()
                text = el.get('text', '')
                
                # Focus on article tags or substantial content that looks like individual posts
                if tag_name == 'article' or (len(text) > 100 and len(text) < 2000):
                    # Exclude navigation/timeline aggregations
                    if not ('for you' in text.lower() and 'following' in text.lower() and len(text) > 1000):
                        individual_posts.append(el)
            
            print(f"📊 Found {len(reply_buttons)} reply buttons and {len(individual_posts)} individual posts")
            
            # Find the specific post with enhanced matching
            target_post = None
            target_reply_button = None
            
            search_term = author_or_content.lower()
            
            print(f"🔍 Searching through {len(individual_posts)} posts for: '{search_term}'")
            
            for i, post_el in enumerate(individual_posts):
                content_text = post_el.get('text', '').lower()
                
                # Enhanced matching - check for author names, content, or specific phrases
                is_match = False
                match_reason = ""
                
                if search_term in content_text:
                    is_match = True
                    match_reason = f"Contains '{search_term}'"
                
                # Special handling for author matching
                if '@' in search_term or any(name in search_term for name in ['akshay', 'langchain', 'openai', 'anthropic']):
                    # Check for author mentions
                    if search_term.replace('@', '') in content_text:
                        is_match = True
                        match_reason = f"Author match: '{search_term}'"
                
                if is_match:
                    target_post = post_el
                    print(f"✅ Found target post #{i+1}: {match_reason}")
                    print(f"📍 Post position: ({post_el.get('x')}, {post_el.get('y')})")
                    print(f"📝 Post preview: '{content_text[:200]}...'")
                    
                    # Find the closest reply button to this specific post
                    post_y = post_el.get('y', 0)
                    post_x = post_el.get('x', 0)
                    closest_button = None
                    min_distance = float('inf')
                    
                    print(f"🔍 Looking for reply buttons near this post at y={post_y}")
                    
                    for reply_btn in reply_buttons:
                        btn_y = reply_btn.get('y', 0)
                        btn_x = reply_btn.get('x', 0)
                        
                        # Reply buttons should be close to the post (within ~600px vertically, below the post)
                        y_distance = btn_y - post_y  # Distance below the post
                        
                        print(f"  Reply button '{reply_btn.get('ariaLabel', '')}' at ({btn_x}, {btn_y}) - distance: {abs(y_distance)}px {'below' if y_distance > 0 else 'above'}")
                        
                        # Reply buttons are typically BELOW posts, within reasonable range
                        if 0 < y_distance < 600 and y_distance < min_distance:
                            min_distance = y_distance
                            closest_button = reply_btn
                    
                    if closest_button:
                        target_reply_button = closest_button
                        print(f"🎯 Selected reply button: '{closest_button.get('ariaLabel')}' at ({closest_button.get('x')}, {closest_button.get('y')}) - {min_distance}px away")
                        break
                    else:
                        print(f"❌ No reply button found within 600px of this post")
                        # Continue searching other posts
                        target_post = None
            
            if not target_post:
                return f"❌ Could not find a post by '{author_or_content}'. Try being more specific."
            
            if not target_reply_button:
                return f"❌ Found the post by '{author_or_content}' but couldn't locate its reply button."
            
            # Step 1: Click the reply button to open comment composer
            x = target_reply_button.get('x')
            y = target_reply_button.get('y')
            aria_label = target_reply_button.get('ariaLabel', '')
            
            print(f"🎯 Step 1: Clicking reply button: '{aria_label}' at coordinates ({x}, {y})")
            
            # Validate coordinates
            if x is None or y is None:
                return f"❌ Invalid coordinates for reply button"
            
            # Ensure post is visible by scrolling if needed
            if y < 0 or y > 1000:
                print(f"📜 Reply button is off-screen (y={y}), scrolling to make it visible...")
                scroll_result = await _global_client._request("POST", "/scroll", {
                    "x": 500, "y": 500, "scroll_x": 0, "scroll_y": -3 if y < 0 else 3
                })
                print(f"Scroll result: {scroll_result.get('success', False)}")
                await asyncio.sleep(1)
            
            click_result = await _global_client._request("POST", "/click", {"x": x, "y": y})
            
            if not click_result.get("success"):
                return f"❌ Failed to click reply button: {click_result.get('error', 'Unknown error')}"
            
            print("✅ Step 1 complete: Reply button clicked")
            
            # Step 2: Wait for comment composer to appear and type the comment
            await asyncio.sleep(2)  # Wait for reply dialog to open
            
            print(f"💬 Step 2: Typing comment: '{comment_text}'")
            type_result = await _global_client._request("POST", "/type", {"text": comment_text})
            
            if not type_result.get("success"):
                return f"❌ Failed to type comment: {type_result.get('error', 'Unknown error')}"
            
            print("✅ Step 2 complete: Comment text typed")
            
            # Step 3: Find and click the "Reply" or "Post" button to submit
            await asyncio.sleep(1)  # Wait for UI to update
            
            # Get updated DOM after opening reply dialog
            updated_result = await _global_client._request("GET", "/dom/elements")
            if not updated_result.get("success"):
                return f"❌ Failed to get updated DOM: {updated_result.get('error')}"
            
            updated_elements = updated_result.get("elements", [])
            
            # Look for submit button (usually "Reply" or "Post")
            submit_button = None
            potential_buttons = []
            
            for el in updated_elements:
                if el.get('tagName') == 'button':
                    text = el.get('text', '').strip()
                    aria_label = el.get('ariaLabel', '').lower()
                    
                    # Look for reply/post submit buttons
                    if (text.lower() in ['reply', 'post'] or 
                        'reply' in aria_label or 'post' in aria_label):
                        # Make sure it's visible on screen
                        y_pos = el.get('y', 0)
                        if y_pos > 0:
                            potential_buttons.append({
                                'element': el,
                                'text': text,
                                'aria_label': aria_label,
                                'y': y_pos
                            })
                            print(f"  Found potential submit button: '{text}' / '{aria_label}' at ({el.get('x')}, {y_pos})")
            
            # Prefer buttons with exact "Reply" text, then by position (rightmost/bottommost)
            if potential_buttons:
                # Sort by: 1) Exact "Reply" text first, 2) Then by y position (bottom), 3) Then by x position (right)
                potential_buttons.sort(key=lambda b: (
                    0 if b['text'].lower() == 'reply' else 1,  # Exact "Reply" first
                    -b['y'],  # Bottom-most (higher y values)
                    -b['element'].get('x', 0)  # Right-most (higher x values)
                ))
                
                submit_button = potential_buttons[0]['element']
                print(f"🎯 Selected submit button: '{potential_buttons[0]['text']}' at ({submit_button.get('x')}, {submit_button.get('y')})")
            
            if not submit_button:
                # Fallback: try Enter key to submit
                print("⚠️ Submit button not found, trying Enter key...")
                key_result = await _global_client._request("POST", "/key", {"keys": ["Enter"]})
                if key_result.get("success"):
                    return f"✅ Comment posted on '{author_or_content}' post using Enter key! 💬"
                else:
                    return f"⚠️ Comment typed but couldn't submit. Please check manually."
            
            # Click submit button
            submit_x = submit_button.get('x')
            submit_y = submit_button.get('y')
            submit_text = submit_button.get('text', '')
            
            print(f"🎯 Step 3: Clicking submit button: '{submit_text}' at ({submit_x}, {submit_y})")
            
            submit_click = await _global_client._request("POST", "/click", {"x": submit_x, "y": submit_y})
            
            if submit_click.get("success"):
                print("✅ Step 3 complete: Comment submitted!")
                return f"✅ Successfully commented on '{author_or_content}' post! 💬\nComment: \"{comment_text}\""
            else:
                return f"⚠️ Comment typed but submit failed: {submit_click.get('error')}. Try submitting manually."
                
        except Exception as e:
            return f"Comment failed: {str(e)}"

    @tool
    async def get_current_username() -> str:
        """
        Get the current logged-in user's username by finding the Profile link.
        
        Returns the username (e.g., 'Rajath_DB') which can be used to navigate to the user's profile.
        """
        try:
            print("🔍 Looking for Profile link to extract username...")
            
            # Get DOM elements to find Profile link
            result = await _global_client._request("GET", "/dom/elements")
            if not result.get("success"):
                return f"Failed to get page elements: {result.get('error', 'Unknown error')}"
            
            elements = result.get("elements", [])
            
            # Find Profile link
            profile_link = None
            for el in elements:
                if (el.get('tagName') == 'a' and 
                    el.get('ariaLabel', '').lower() == 'profile' and
                    el.get('href', '').startswith('https://x.com/')):
                    profile_link = el
                    break
            
            if not profile_link:
                return "❌ Could not find Profile link. Make sure you're logged in to X/Twitter."
            
            # Extract username from href
            href = profile_link.get('href', '')
            if href.startswith('https://x.com/'):
                username = href.replace('https://x.com/', '').split('/')[0]
                print(f"✅ Found current username: {username}")
                return f"✅ Current username: {username}"
            else:
                return f"❌ Could not extract username from Profile link: {href}"
                
        except Exception as e:
            return f"Get username failed: {str(e)}"

    @tool
    async def navigate_to_user_replies(username: str = None) -> str:
        """
        Navigate to the user's replies page to view/manage their comments.
        
        Args:
            username: Optional username. If not provided, will auto-detect current user.
        
        This navigates to https://x.com/{username}/with_replies where you can see and manage your own comments.
        """
        try:
            if not username:
                # Auto-detect current username
                username_result = await get_current_username.arun({})
                if "Current username:" in username_result:
                    username = username_result.split("Current username: ")[1].strip()
                else:
                    return f"❌ Could not auto-detect username: {username_result}"
            
            replies_url = f"https://x.com/{username}/with_replies"
            print(f"🔗 Navigating to user replies: {replies_url}")
            
            # Navigate to the replies page
            navigate_result = await _global_client._request("POST", "/navigate", {"url": replies_url})
            
            if navigate_result.get("success"):
                # Wait for page to load
                await asyncio.sleep(3)
                return f"✅ Successfully navigated to {username}'s replies page"
            else:
                return f"❌ Failed to navigate to replies page: {navigate_result.get('error', 'Unknown error')}"
                
        except Exception as e:
            return f"Navigate to replies failed: {str(e)}"

    @tool
    async def delete_own_comment(target_post_author_or_content: str, comment_text_to_delete: str) -> str:
        """
        Delete your own comment from a specific post.
        
        Args:
            target_post_author_or_content: Identifier for the original post you commented on
            comment_text_to_delete: The exact text of your comment to delete
        
        This function:
        1. Navigates to your replies page
        2. Finds your comment on the specified post
        3. Deletes the comment using the more options menu
        
        Examples:
        - delete_own_comment("John Rush", "Great comprehensive list! Thanks for sharing this.")
        - delete_own_comment("Alex", "Interesting perspective! 🤔")
        """
        try:
            print(f"🗑️ STARTING DELETION: Looking to delete comment '{comment_text_to_delete}' on post by '{target_post_author_or_content}'")
            
            # Step 1: Navigate to user's replies page
            replies_result = await navigate_to_user_replies.arun({})
            if not replies_result.startswith("✅"):
                return f"❌ Failed to navigate to replies page: {replies_result}"
            
            print("✅ Step 1: Successfully navigated to replies page")
            
            # Step 2: Find the specific comment to delete
            await asyncio.sleep(2)  # Wait for page to load
            
            # Get page elements to find the comment
            result = await _global_client._request("GET", "/dom/elements")
            if not result.get("success"):
                return f"Failed to get page elements: {result.get('error', 'Unknown error')}"
            
            elements = result.get("elements", [])
            
            # Look for articles/posts that contain both the original post content and our comment
            target_comment_element = None
            
            print(f"🔍 Step 2: Searching for comment containing: '{comment_text_to_delete}'")
            print(f"📊 Total elements found: {len(elements)}")
            
            # Count articles first
            article_count = sum(1 for el in elements if el.get('tagName') == 'article')
            print(f"📄 Article elements found: {article_count}")
            
            # First, find our comment article (replies page has separate articles)
            comment_candidates = []
            for el in elements:
                if el.get('tagName') == 'article':
                    text_content = el.get('text', '')
                    
                    # Check if this article contains our comment text (with emoji-tolerant matching)
                    # Remove emojis from both strings for comparison
                    import re
                    emoji_pattern = re.compile(r'[^\w\s.,!?;:\'"()-]', re.UNICODE)
                    comment_clean = emoji_pattern.sub('', comment_text_to_delete.lower()).strip()
                    content_clean = emoji_pattern.sub('', text_content.lower()).strip()
                    
                    # Also try exact match first
                    exact_match = comment_text_to_delete.lower() in text_content.lower()
                    emoji_tolerant_match = comment_clean in content_clean
                    
                    if exact_match or emoji_tolerant_match:
                        comment_candidates.append(el)
                        match_type = "exact" if exact_match else "emoji-tolerant"
                        print(f"✅ Found comment candidate ({match_type}, index {el.get('index')}): '{text_content[:150]}...'")
            
            print(f"📋 Total comment candidates found: {len(comment_candidates)}")
            
            # Look for the comment that belongs to our user
            # First get our username dynamically
            print("👤 Getting current username...")
            username_result = await get_current_username.arun({})
            current_username = None
            if "Current username:" in username_result:
                current_username = username_result.split("Current username: ")[1].strip()
                print(f"✅ Current user detected: @{current_username}")
            else:
                print(f"❌ Failed to get username: {username_result}")
                return f"❌ Could not detect current username: {username_result}"
            
            for i, candidate in enumerate(comment_candidates):
                text_content = candidate.get('text', '')
                print(f"🔍 Checking candidate {i+1}: '{text_content[:100]}...'")
                print(f"   Looking for '@{current_username}' in text...")
                
                # Check if this is our comment (should contain our username)
                if current_username and f'@{current_username}' in text_content:
                    target_comment_element = candidate
                    print(f"✅ MATCH! Found our comment (index {candidate.get('index')})")
                    print(f"   Full text: {text_content[:300]}...")
                    break
                else:
                    print(f"   ❌ No match - doesn't contain '@{current_username}'")
            
            if len(comment_candidates) == 0:
                print(f"❌ No articles found containing comment text: '{comment_text_to_delete}'")
                return f"❌ Could not find any comments with text '{comment_text_to_delete}' on the replies page."
            
            if not target_comment_element:
                return f"❌ Could not find your comment '{comment_text_to_delete}' on a post by '{target_post_author_or_content}'. Make sure you're on the correct replies page."
            
            print("✅ Step 2: Successfully found target comment")
            
            # Step 3: Find the "more options" menu (three dots) near this comment
            comment_y = target_comment_element.get('y', 0)
            comment_x = target_comment_element.get('x', 0)
            comment_index = target_comment_element.get('index', 'unknown')
            more_options_button = None
            
            print(f"🔍 Step 3: Looking for More options button near comment")
            print(f"   Comment position: ({comment_x}, {comment_y}), index: {comment_index}")
            
            # Look for more options buttons (usually have aria-label like "More" or are near the comment)
            more_candidates = []
            for el in elements:
                if (el.get('tagName') == 'button' and 
                    'more' in el.get('ariaLabel', '').lower()):
                    btn_y = el.get('y', 0)
                    btn_x = el.get('x', 0)
                    btn_index = el.get('index', 'unknown')
                    distance = abs(btn_y - comment_y)
                    
                    more_candidates.append({
                        'element': el,
                        'distance': distance,
                        'position': (btn_x, btn_y),
                        'index': btn_index
                    })
                    
                    print(f"   Found More button: ({btn_x}, {btn_y}), index: {btn_index}, distance: {distance}")
            
            print(f"📋 Total More button candidates: {len(more_candidates)}")
            
            # Sort by distance and pick the closest one within reasonable range
            more_candidates.sort(key=lambda x: x['distance'])
            
            # Look for a More button that's actually in the comment's action bar
            # These are typically at x-coordinate around 755 (right side of comment actions)
            for candidate in more_candidates:
                distance = candidate['distance']
                position = candidate['position']
                
                if distance < 50:  # Must be very close
                    # Check if this looks like a comment action button (x around 700-800)
                    x_coord = position[0]
                    if 700 <= x_coord <= 800:  # This should be in the comment action bar
                        more_options_button = candidate['element']
                        print(f"   ✅ Selected comment action More button at {position} (distance: {distance})")
                        break
                    else:
                        print(f"   ❓ More button at {position} might not be comment action (x={x_coord})")
                else:
                    print(f"   ❌ More button too far: {distance}px at {position}")
            
            # Fallback: if no button in action bar range, try closest one
            if not more_options_button and more_candidates:
                closest = more_candidates[0]
                if closest['distance'] < 100:
                    more_options_button = closest['element']
                    print(f"   ⚠️ Fallback: Using closest More button at {closest['position']} (distance: {closest['distance']})")
            
            if not more_options_button:
                print(f"❌ No More buttons found within 100px of comment at y={comment_y}")
                if more_candidates:
                    print("Available More buttons:")
                    for i, candidate in enumerate(more_candidates):
                        print(f"  {i+1}. Position: {candidate['position']}, distance: {candidate['distance']}")
                return f"❌ Could not find more options menu for the comment. The comment might not be deletable or the page structure changed."
            
            more_x = more_options_button.get('x')
            more_y = more_options_button.get('y')
            more_index = more_options_button.get('index')
            
            print(f"✅ Step 3: Selected More options button")
            print(f"   Position: ({more_x}, {more_y}), index: {more_index}")
            
            # Step 4: Click more options menu
            print(f"👆 Step 4: Clicking More options button at ({more_x}, {more_y})")
            click_result = await _global_client._request("POST", "/click", {
                "x": more_x, 
                "y": more_y
            })
            
            if not click_result.get("success"):
                return f"❌ Failed to click more options menu: {click_result.get('error')}"
            
            print("✅ Step 4: Successfully clicked more options menu")
            
            # Step 5: Wait for menu to appear and find "Delete" option
            print("⏳ Step 5: Waiting for menu to appear...")
            await asyncio.sleep(2)  # Increased wait time
            
            # Get updated DOM to find delete option
            print("🔍 Step 5: Getting updated DOM to find Delete option...")
            updated_result = await _global_client._request("GET", "/dom/elements")
            if not updated_result.get("success"):
                return f"❌ Failed to get updated DOM: {updated_result.get('error')}"
            
            updated_elements = updated_result.get("elements", [])
            print(f"📊 Updated DOM: {len(updated_elements)} elements found")
            
            delete_button = None
            potential_delete_buttons = []
            
            print("🔍 Searching for Delete buttons...")
            for el in updated_elements:
                text = el.get('text', '').strip()
                aria_label = el.get('ariaLabel', '').strip()
                tag_name = el.get('tagName', '')
                
                # Log all buttons for debugging
                if tag_name == 'button':
                    potential_delete_buttons.append({
                        'text': text,
                        'aria_label': aria_label,
                        'position': (el.get('x'), el.get('y')),
                        'index': el.get('index')
                    })
                
                # Look for delete elements (buttons, divs, spans, etc.)
                is_delete_element = False
                if tag_name in ['button', 'div', 'span', 'a']:
                    # Check for exact "Delete" text
                    if text.strip() == 'Delete':
                        is_delete_element = True
                        print(f"✅ Found Delete element ({tag_name}): '{text}' at ({el.get('x')}, {el.get('y')})")
                    # Check for aria-label containing delete
                    elif 'delete' in aria_label.lower():
                        is_delete_element = True
                        print(f"✅ Found Delete element ({tag_name}, aria-label): '{aria_label}' at ({el.get('x')}, {el.get('y')})")
                    # Check for text containing delete
                    elif 'delete' in text.lower():
                        is_delete_element = True
                        print(f"✅ Found Delete element ({tag_name}, text contains): '{text}' at ({el.get('x')}, {el.get('y')})")
                
                if is_delete_element:
                    delete_button = el
                    break
            
            print(f"📋 Total buttons found in menu: {len(potential_delete_buttons)}")
            if len(potential_delete_buttons) > 0:
                print("All available buttons in menu:")
                for i, btn in enumerate(potential_delete_buttons):  # Show ALL buttons
                    print(f"  {i+1}. Text: '{btn['text']}', Aria: '{btn['aria_label']}', Position: {btn['position']}")
            
            # Also check for menu items/links that might contain delete
            menu_items = []
            for el in updated_elements:
                tag_name = el.get('tagName', '')
                text = el.get('text', '').strip()
                aria_label = el.get('ariaLabel', '').strip()
                
                # Look for any element that might be a delete option
                if tag_name in ['a', 'div', 'span', 'li'] and text:
                    if 'delete' in text.lower() or 'delete' in aria_label.lower():
                        menu_items.append({
                            'tag': tag_name,
                            'text': text,
                            'aria': aria_label,
                            'position': (el.get('x'), el.get('y')),
                            'index': el.get('index')
                        })
            
            if menu_items:
                print(f"🔍 Found {len(menu_items)} non-button elements with 'delete':")
                for item in menu_items:
                    print(f"  - {item['tag']}: '{item['text']}' / '{item['aria']}' at {item['position']}")
            
            if not delete_button:
                return f"⚠️ More options menu opened but could not find Delete option. Found {len(potential_delete_buttons)} buttons total. This comment might not be deletable."
            
            delete_x = delete_button.get('x')
            delete_y = delete_button.get('y')
            delete_index = delete_button.get('index')
            
            print(f"✅ Step 5: Selected Delete button")
            print(f"   Text: '{delete_button.get('text')}', Position: ({delete_x}, {delete_y}), Index: {delete_index}")
            
            # Step 6: Click delete button
            delete_click = await _global_client._request("POST", "/click", {
                "x": delete_button.get('x'),
                "y": delete_button.get('y')
            })
            
            if delete_click.get("success"):
                print("✅ Step 6: Clicked delete button")
                
                # Wait a moment for any confirmation dialog
                await asyncio.sleep(1)
                
                # Check if there's a confirmation dialog and handle it
                confirm_result = await _global_client._request("GET", "/dom/elements")
                if confirm_result.get("success"):
                    confirm_elements = confirm_result.get("elements", [])
                    
                    # Look for confirmation button (usually "Delete" again)
                    confirm_button = None
                    for el in confirm_elements:
                        if (el.get('tagName') == 'button' and
                            el.get('text', '').strip() == 'Delete'):
                            confirm_button = el
                            break
                    
                    if confirm_button:
                        print(f"✅ Found confirmation Delete button at ({confirm_button.get('x')}, {confirm_button.get('y')})")
                        # Click confirmation
                        final_click = await _global_client._request("POST", "/click", {
                            "x": confirm_button.get('x'),
                            "y": confirm_button.get('y')
                        })
                        if final_click.get("success"):
                            print("✅ Step 7: Confirmed deletion")
                            await asyncio.sleep(2)  # Wait for deletion to complete
                        else:
                            print(f"❌ Failed to click confirmation: {final_click.get('error')}")
                    else:
                        print("⚠️ No confirmation dialog found, deletion may have completed")
                
                # Step 8: Navigate back to home page
                print("🏠 Navigating back to home page...")
                home_result = await _global_client._request("POST", "/navigate", {"url": "https://x.com/home"})
                if home_result.get("success"):
                    await asyncio.sleep(2)  # Wait for home page to load
                    print("✅ Step 8: Returned to home page")
                
                return f"✅ Successfully deleted comment '{comment_text_to_delete}' from post by '{target_post_author_or_content}' and returned to home 🗑️🏠"
            else:
                return f"❌ Failed to click delete button: {delete_click.get('error')}"
                
        except Exception as e:
            return f"Delete comment failed: {str(e)}"

    @tool 
    async def like_specific_post_by_keywords(keywords: str) -> str:
        """
        LIKE a post by searching for specific keywords in the post content.
        
        Args:
            keywords: Key phrases to identify the post (e.g., "OCR model", "AI research", "open source")
        
        More flexible version of like_post that searches through visible posts.
        """
        try:
            # Get comprehensive context to see all posts
            comprehensive_result = await get_comprehensive_context.arun({})
            
            # Also get DOM elements for precise clicking
            dom_result = await _global_client._request("GET", "/dom/elements")
            if not dom_result.get("success"):
                return f"Failed to get DOM elements: {dom_result.get('error')}"
            
            elements = dom_result.get("elements", [])
            
            # Find like buttons
            like_buttons = [el for el in elements 
                          if 'like' in el.get('ariaLabel', '').lower() and 'likes' in el.get('ariaLabel', '').lower()]
            
            print(f"🔍 Searching for post with keywords: '{keywords}'")
            print(f"📊 Found {len(like_buttons)} like buttons on page")
            
            if comprehensive_result and keywords.lower() in comprehensive_result.lower():
                print(f"✅ Found post containing '{keywords}' in page content")
                
                # For social media, like buttons are typically in the order posts appear
                # Use the first like button for now (can be enhanced with position matching)
                if like_buttons:
                    target_button = like_buttons[0]  # Most visible/recent post
                    
                    # Check if it has a reasonable number of likes (not a promoted post)
                    aria_label = target_button.get('ariaLabel', '')
                    
                    x = target_button.get('x')
                    y = target_button.get('y') 
                    
                    print(f"🎯 Clicking like button: {aria_label} at ({x}, {y})")
                    
                    click_result = await _global_client._request("POST", "/click", {"x": x, "y": y})
                    
                    if click_result.get("success"):
                        return f"✅ Successfully liked the post containing '{keywords}'! 👍"
                    else:
                        return f"❌ Failed to click like: {click_result.get('error')}"
                else:
                    return f"❌ Found the post but no like buttons detected"
            else:
                return f"❌ Could not find a post containing '{keywords}' on current page"
                
        except Exception as e:
            return f"Like by keywords failed: {str(e)}"
    
    # Return the @tool decorated functions
    return [
        take_browser_screenshot,
        navigate_to_url,
        click_at_coordinates,
        type_text,
        press_key_combination,
        scroll_page,
        get_dom_elements,
        get_page_info,
        get_enhanced_context,
        find_form_fields,
        click_element_by_selector,
        click_button_by_text,
        fill_input_field,
        enter_username,
        enter_password,
        check_login_success,
        get_comprehensive_context,
        get_screenshot_with_analysis,
        like_post,
        unlike_post,
        comment_on_post,
        get_current_username,
        navigate_to_user_replies,
        delete_own_comment,
        like_specific_post_by_keywords
    ]


# Main function to get all async tools
def get_async_playwright_tools() -> List[Any]:
    """Get all async Playwright CUA tools for LangGraph ASGI deployment"""
    return create_async_playwright_tools()


if __name__ == "__main__":
    # Test the async tools
    async def test_async_tools():
        """Test the async Playwright tools"""
        print("🧪 Testing Async Playwright Tools...")
        
        tools = get_async_playwright_tools()
        print(f"✅ Created {len(tools)} async tools")
        
        # Test one tool
        screenshot_tool = next(t for t in tools if t.name == "take_browser_screenshot")
        result = await screenshot_tool.arun({})
        print(f"📸 Screenshot test: {result}")
        
        # Cleanup
        await _global_client.close()
    
    asyncio.run(test_async_tools())
