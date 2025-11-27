#!/usr/bin/env python3
"""
Playwright + CUA Integration for Agentic Action Tracking
Enhanced browser automation with intelligent action coordination
"""

import asyncio
import json
import time
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable
from playwright.async_api import async_playwright, Page, Browser, BrowserContext
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field
import aiohttp


class PlaywrightCUAIntegration:
    """Advanced integration between Playwright and CUA for agentic action tracking"""
    
    def __init__(self, cua_host: str = "localhost", cua_port: int = 8001):
        self.cua_host = cua_host
        self.cua_port = cua_port
        self.cua_base_url = f"http://{cua_host}:{cua_port}"
        
        # Playwright instances
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        
        # Action tracking
        self.action_history = []
        self.element_interactions = {}
        self.page_states = []
        
        # Event listeners
        self.event_handlers = {
            'navigation': [],
            'click': [],
            'type': [],
            'scroll': [],
            'screenshot': []
        }
    
    async def connect_to_cua_firefox(self) -> Dict[str, Any]:
        """Connect Playwright to the CUA Firefox instance with enhanced tracking"""
        
        try:
            print("🎭 Connecting Playwright to CUA Firefox...")
            
            # Launch Playwright
            self.playwright = await async_playwright().start()
            
            # Connect to existing Firefox via CDP
            try:
                self.browser = await self.playwright.firefox.connect_over_cdp("http://localhost:9222")
                connection_method = "CDP"
            except Exception as e:
                print(f"⚠️ CDP connection failed: {e}")
                print("🔄 Falling back to new browser instance...")
                self.browser = await self.playwright.firefox.launch(headless=False)
                connection_method = "New Instance"
            
            # Get or create context
            contexts = self.browser.contexts
            if contexts:
                self.context = contexts[0]
                print("📄 Using existing browser context")
            else:
                self.context = await self.browser.new_context(
                    viewport={'width': 1280, 'height': 720},
                    user_agent='Mozilla/5.0 (X11; Linux x86_64) Playwright CUA Integration'
                )
                print("📄 Created new browser context")
            
            # Get or create page
            pages = self.context.pages
            if pages:
                self.page = pages[0]
                print("📖 Using existing page")
            else:
                self.page = await self.context.new_page()
                print("📖 Created new page")
            
            # Set up comprehensive event tracking
            await self._setup_event_tracking()
            
            # Initial state capture
            await self._capture_initial_state()
            
            return {
                "success": True,
                "connection_method": connection_method,
                "page_url": self.page.url,
                "viewport": await self.page.viewport_size(),
                "tracking_enabled": True
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _setup_event_tracking(self):
        """Set up comprehensive event tracking for agentic actions"""
        
        # Track navigation events
        self.page.on("framenavigated", self._on_navigation)
        
        # Track network requests (for API calls, form submissions)
        self.page.on("response", self._on_response)
        
        # Track console messages (for debugging)
        self.page.on("console", self._on_console)
        
        # Track page errors
        self.page.on("pageerror", self._on_page_error)
        
        # Track dialog events (alerts, confirms)
        self.page.on("dialog", self._on_dialog)
        
        print("📊 Event tracking initialized for agentic action monitoring")
    
    async def _capture_initial_state(self):
        """Capture initial page state for comparison"""
        
        initial_state = await self._get_page_state()
        self.page_states.append({
            "timestamp": datetime.now().isoformat(),
            "event": "initial_state",
            "state": initial_state
        })
        
        print(f"📸 Initial state captured: {initial_state['url']}")
    
    async def _on_navigation(self, frame):
        """Handle navigation events"""
        if frame == self.page.main_frame:
            nav_data = {
                "timestamp": datetime.now().isoformat(),
                "event": "navigation",
                "url": frame.url,
                "title": await self.page.title()
            }
            
            self.action_history.append(nav_data)
            await self._trigger_event_handlers('navigation', nav_data)
            
            print(f"🧭 Navigation: {frame.url}")
    
    async def _on_response(self, response):
        """Handle network responses"""
        # Track important API calls and form submissions
        if response.request.method in ['POST', 'PUT', 'PATCH'] or 'api' in response.url.lower():
            response_data = {
                "timestamp": datetime.now().isoformat(),
                "event": "network_request",
                "method": response.request.method,
                "url": response.url,
                "status": response.status,
                "headers": dict(response.headers)
            }
            
            self.action_history.append(response_data)
            print(f"🌐 API Call: {response.request.method} {response.url} -> {response.status}")
    
    async def _on_console(self, msg):
        """Handle console messages"""
        if msg.type in ['error', 'warning']:
            console_data = {
                "timestamp": datetime.now().isoformat(),
                "event": "console",
                "type": msg.type,
                "text": msg.text
            }
            
            self.action_history.append(console_data)
            print(f"🖥️ Console {msg.type}: {msg.text}")
    
    async def _on_page_error(self, error):
        """Handle page errors"""
        error_data = {
            "timestamp": datetime.now().isoformat(),
            "event": "page_error",
            "message": str(error)
        }
        
        self.action_history.append(error_data)
        print(f"❌ Page Error: {error}")
    
    async def _on_dialog(self, dialog):
        """Handle dialogs (alerts, confirms)"""
        dialog_data = {
            "timestamp": datetime.now().isoformat(),
            "event": "dialog",
            "type": dialog.type,
            "message": dialog.message
        }
        
        self.action_history.append(dialog_data)
        print(f"💬 Dialog {dialog.type}: {dialog.message}")
        
        # Auto-handle dialog (can be customized)
        await dialog.accept()
    
    async def _trigger_event_handlers(self, event_type: str, data: Dict[str, Any]):
        """Trigger registered event handlers"""
        for handler in self.event_handlers.get(event_type, []):
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(data)
                else:
                    handler(data)
            except Exception as e:
                print(f"⚠️ Event handler error: {e}")
    
    def register_event_handler(self, event_type: str, handler: Callable):
        """Register custom event handlers for agentic coordination"""
        if event_type in self.event_handlers:
            self.event_handlers[event_type].append(handler)
            print(f"📝 Registered handler for {event_type} events")
    
    async def enhanced_click(self, selector: str, options: Dict[str, Any] = None) -> Dict[str, Any]:
        """Enhanced click with tracking and CUA coordination"""
        
        start_time = time.time()
        
        try:
            # Pre-click state
            pre_state = await self._get_page_state()
            
            # Perform click with Playwright
            element = await self.page.wait_for_selector(selector, timeout=10000)
            
            if not element:
                return {"success": False, "error": f"Element not found: {selector}"}
            
            # Get element details
            element_info = await self._get_element_info(element)
            
            # Perform the click
            await element.click(**(options or {}))
            
            # Wait for potential navigation/changes
            await asyncio.sleep(0.5)
            
            # Post-click state
            post_state = await self._get_page_state()
            
            # Record the action
            click_data = {
                "timestamp": datetime.now().isoformat(),
                "event": "enhanced_click",
                "selector": selector,
                "element_info": element_info,
                "pre_state": pre_state,
                "post_state": post_state,
                "duration": time.time() - start_time,
                "options": options
            }
            
            self.action_history.append(click_data)
            self.element_interactions[selector] = self.element_interactions.get(selector, 0) + 1
            
            # Trigger event handlers
            await self._trigger_event_handlers('click', click_data)
            
            print(f"👆 Enhanced Click: {selector} -> {element_info.get('text', 'N/A')[:50]}")
            
            return {
                "success": True,
                "element_info": element_info,
                "state_change": pre_state['url'] != post_state['url'],
                "action_data": click_data
            }
            
        except Exception as e:
            error_data = {
                "timestamp": datetime.now().isoformat(),
                "event": "enhanced_click_error",
                "selector": selector,
                "error": str(e),
                "duration": time.time() - start_time
            }
            
            self.action_history.append(error_data)
            
            return {
                "success": False,
                "error": str(e),
                "action_data": error_data
            }
    
    async def enhanced_type(self, selector: str, text: str, options: Dict[str, Any] = None) -> Dict[str, Any]:
        """Enhanced typing with tracking"""
        
        start_time = time.time()
        
        try:
            # Find and focus element
            element = await self.page.wait_for_selector(selector, timeout=10000)
            element_info = await self._get_element_info(element)
            
            # Clear existing content if specified
            if options and options.get('clear', True):
                await element.fill('')
            
            # Type the text
            await element.type(text, delay=options.get('delay', 50) if options else 50)
            
            # Record the action
            type_data = {
                "timestamp": datetime.now().isoformat(),
                "event": "enhanced_type",
                "selector": selector,
                "text": text,
                "element_info": element_info,
                "duration": time.time() - start_time,
                "options": options
            }
            
            self.action_history.append(type_data)
            
            # Trigger event handlers
            await self._trigger_event_handlers('type', type_data)
            
            print(f"⌨️ Enhanced Type: {selector} -> '{text[:30]}...'")
            
            return {
                "success": True,
                "element_info": element_info,
                "action_data": type_data
            }
            
        except Exception as e:
            error_data = {
                "timestamp": datetime.now().isoformat(),
                "event": "enhanced_type_error",
                "selector": selector,
                "text": text,
                "error": str(e),
                "duration": time.time() - start_time
            }
            
            self.action_history.append(error_data)
            
            return {
                "success": False,
                "error": str(e),
                "action_data": error_data
            }
    
    async def smart_wait_and_verify(self, condition: str, timeout: int = 10000) -> Dict[str, Any]:
        """Smart waiting with verification for agentic actions"""
        
        start_time = time.time()
        
        try:
            # Different wait conditions
            if condition.startswith('selector:'):
                selector = condition.replace('selector:', '')
                await self.page.wait_for_selector(selector, timeout=timeout)
                result = {"type": "selector", "selector": selector}
                
            elif condition.startswith('url:'):
                url_pattern = condition.replace('url:', '')
                await self.page.wait_for_url(url_pattern, timeout=timeout)
                result = {"type": "url", "pattern": url_pattern, "current_url": self.page.url}
                
            elif condition.startswith('text:'):
                text = condition.replace('text:', '')
                await self.page.wait_for_function(f'document.body.innerText.includes("{text}")', timeout=timeout)
                result = {"type": "text", "text": text}
                
            elif condition == 'networkidle':
                await self.page.wait_for_load_state('networkidle', timeout=timeout)
                result = {"type": "networkidle"}
                
            else:
                # Custom JavaScript condition
                await self.page.wait_for_function(condition, timeout=timeout)
                result = {"type": "javascript", "condition": condition}
            
            wait_data = {
                "timestamp": datetime.now().isoformat(),
                "event": "smart_wait",
                "condition": condition,
                "duration": time.time() - start_time,
                "success": True,
                "result": result
            }
            
            self.action_history.append(wait_data)
            
            print(f"⏳ Smart Wait: {condition} -> ✅ ({wait_data['duration']:.2f}s)")
            
            return {
                "success": True,
                "duration": wait_data['duration'],
                "result": result
            }
            
        except Exception as e:
            error_data = {
                "timestamp": datetime.now().isoformat(),
                "event": "smart_wait_error",
                "condition": condition,
                "error": str(e),
                "duration": time.time() - start_time
            }
            
            self.action_history.append(error_data)
            
            return {
                "success": False,
                "error": str(e),
                "duration": error_data['duration']
            }
    
    async def extract_structured_data(self, extraction_config: Dict[str, Any]) -> Dict[str, Any]:
        """Extract structured data to help the CUA agent make decisions"""
        
        try:
            extraction_script = self._build_extraction_script(extraction_config)
            extracted_data = await self.page.evaluate(extraction_script)
            
            extraction_result = {
                "timestamp": datetime.now().isoformat(),
                "event": "data_extraction",
                "config": extraction_config,
                "data": extracted_data,
                "page_url": self.page.url
            }
            
            self.action_history.append(extraction_result)
            
            print(f"📊 Data Extracted: {len(extracted_data)} items from {self.page.url}")
            
            return {
                "success": True,
                "data": extracted_data,
                "metadata": extraction_result
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def _build_extraction_script(self, config: Dict[str, Any]) -> str:
        """Build JavaScript extraction script from configuration"""
        
        if config["type"] == "social_media_posts":
            return """
            () => {
                const posts = Array.from(document.querySelectorAll('[data-testid="tweet"], .post, article'));
                return posts.map((post, index) => ({
                    index: index,
                    text: post.querySelector('[data-testid="tweetText"], .post-content, .content')?.textContent?.trim() || '',
                    author: post.querySelector('[data-testid="User-Names"], .author, .username')?.textContent?.trim() || '',
                    likes: post.querySelector('[data-testid="like"], .like-count, [aria-label*="like"]')?.textContent?.trim() || '0',
                    timestamp: post.querySelector('time, .timestamp')?.getAttribute('datetime') || '',
                    url: post.querySelector('a[href*="/status/"], a[href*="/post/"]')?.href || '',
                    hasLiked: post.querySelector('[aria-pressed="true"], .liked, .active')?.length > 0 || false,
                    element_id: `post_${index}`,
                    position: post.getBoundingClientRect()
                }));
            }
            """
        
        elif config["type"] == "ecommerce_products":
            return """
            () => {
                const products = Array.from(document.querySelectorAll('.product, [data-testid*="product"], .item'));
                return products.map((product, index) => ({
                    index: index,
                    name: product.querySelector('.product-title, .name, h2, h3')?.textContent?.trim() || '',
                    price: product.querySelector('.price, .cost, [data-testid*="price"]')?.textContent?.trim() || '',
                    rating: product.querySelector('.rating, .stars, [aria-label*="star"]')?.textContent?.trim() || '',
                    availability: product.querySelector('.stock, .availability, .in-stock')?.textContent?.trim() || '',
                    image: product.querySelector('img')?.src || '',
                    url: product.querySelector('a')?.href || '',
                    element_id: `product_${index}`,
                    position: product.getBoundingClientRect()
                }));
            }
            """
        
        elif config["type"] == "form_fields":
            return """
            () => {
                const fields = Array.from(document.querySelectorAll('input, textarea, select'));
                return fields.map((field, index) => ({
                    index: index,
                    type: field.type || field.tagName.toLowerCase(),
                    name: field.name || field.id || '',
                    label: document.querySelector(`label[for="${field.id}"]`)?.textContent?.trim() || '',
                    placeholder: field.placeholder || '',
                    required: field.required,
                    value: field.value || '',
                    element_id: `field_${index}`,
                    position: field.getBoundingClientRect()
                }));
            }
            """
        
        else:
            # Custom extraction
            return config.get("script", "() => { return []; }")
    
    async def _get_element_info(self, element) -> Dict[str, Any]:
        """Get comprehensive element information"""
        
        try:
            element_info = await element.evaluate("""
                (el) => ({
                    tagName: el.tagName,
                    text: el.textContent?.trim() || '',
                    id: el.id || '',
                    className: el.className || '',
                    href: el.href || '',
                    type: el.type || '',
                    value: el.value || '',
                    placeholder: el.placeholder || '',
                    ariaLabel: el.getAttribute('aria-label') || '',
                    dataTestId: el.getAttribute('data-testid') || '',
                    position: el.getBoundingClientRect(),
                    isVisible: el.offsetWidth > 0 && el.offsetHeight > 0
                })
            """)
            
            return element_info
            
        except Exception as e:
            return {"error": str(e)}
    
    async def _get_page_state(self) -> Dict[str, Any]:
        """Get current page state for comparison"""
        
        try:
            state = await self.page.evaluate("""
                () => ({
                    url: window.location.href,
                    title: document.title,
                    readyState: document.readyState,
                    activeElement: document.activeElement?.tagName || '',
                    scrollPosition: {
                        x: window.scrollX,
                        y: window.scrollY
                    },
                    viewport: {
                        width: window.innerWidth,
                        height: window.innerHeight
                    },
                    elementCounts: {
                        clickable: document.querySelectorAll('button, a, [onclick]').length,
                        inputs: document.querySelectorAll('input, textarea, select').length,
                        images: document.querySelectorAll('img').length,
                        forms: document.querySelectorAll('form').length
                    }
                })
            """)
            
            return state
            
        except Exception as e:
            return {"error": str(e)}
    
    async def coordinate_with_cua(self, cua_action: str, playwright_enhancement: Dict[str, Any] = None) -> Dict[str, Any]:
        """Coordinate Playwright actions with CUA agent"""
        
        print(f"🤝 Coordinating: CUA='{cua_action}' + Playwright Enhancement")
        
        coordination_start = time.time()
        
        try:
            # Step 1: Capture pre-action state
            pre_state = await self._get_page_state()
            
            # Step 2: Execute CUA action via API
            cua_result = await self._execute_cua_action(cua_action)
            
            # Step 3: Wait for CUA action to complete
            await asyncio.sleep(1)
            
            # Step 4: Apply Playwright enhancement if specified
            playwright_result = None
            if playwright_enhancement:
                playwright_result = await self._apply_playwright_enhancement(playwright_enhancement)
            
            # Step 5: Capture post-action state
            post_state = await self._get_page_state()
            
            # Step 6: Record coordination
            coordination_data = {
                "timestamp": datetime.now().isoformat(),
                "event": "cua_playwright_coordination",
                "cua_action": cua_action,
                "cua_result": cua_result,
                "playwright_enhancement": playwright_enhancement,
                "playwright_result": playwright_result,
                "pre_state": pre_state,
                "post_state": post_state,
                "duration": time.time() - coordination_start,
                "state_changed": pre_state['url'] != post_state['url']
            }
            
            self.action_history.append(coordination_data)
            
            print(f"✅ Coordination complete ({coordination_data['duration']:.2f}s)")
            
            return {
                "success": True,
                "coordination_data": coordination_data,
                "cua_result": cua_result,
                "playwright_result": playwright_result
            }
            
        except Exception as e:
            error_data = {
                "timestamp": datetime.now().isoformat(),
                "event": "coordination_error",
                "cua_action": cua_action,
                "error": str(e),
                "duration": time.time() - coordination_start
            }
            
            self.action_history.append(error_data)
            
            return {
                "success": False,
                "error": str(e),
                "error_data": error_data
            }
    
    async def _execute_cua_action(self, action: str) -> Dict[str, Any]:
        """Execute CUA action via API"""
        
        try:
            async with aiohttp.ClientSession() as session:
                # This would be replaced with actual CUA API calls
                # For now, simulate the call
                await asyncio.sleep(0.5)  # Simulate API call time
                
                return {
                    "success": True,
                    "action": action,
                    "simulated": True
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _apply_playwright_enhancement(self, enhancement: Dict[str, Any]) -> Dict[str, Any]:
        """Apply Playwright enhancement after CUA action"""
        
        enhancement_type = enhancement.get("type")
        
        if enhancement_type == "verify_click":
            selector = enhancement.get("selector")
            expected_state = enhancement.get("expected_state")
            
            element = await self.page.query_selector(selector)
            if element:
                actual_state = await element.get_attribute("aria-pressed") == "true"
                return {
                    "type": "verification",
                    "selector": selector,
                    "expected": expected_state,
                    "actual": actual_state,
                    "success": actual_state == expected_state
                }
        
        elif enhancement_type == "extract_data":
            config = enhancement.get("extraction_config")
            return await self.extract_structured_data(config)
        
        elif enhancement_type == "smart_wait":
            condition = enhancement.get("condition")
            return await self.smart_wait_and_verify(condition)
        
        return {"type": "unknown", "success": False}
    
    def get_action_history(self, event_types: List[str] = None, limit: int = None) -> List[Dict[str, Any]]:
        """Get filtered action history for analysis"""
        
        history = self.action_history
        
        if event_types:
            history = [action for action in history if action.get("event") in event_types]
        
        if limit:
            history = history[-limit:]
        
        return history
    
    def get_interaction_analytics(self) -> Dict[str, Any]:
        """Get analytics on element interactions for agent optimization"""
        
        total_actions = len(self.action_history)
        event_counts = {}
        
        for action in self.action_history:
            event_type = action.get("event", "unknown")
            event_counts[event_type] = event_counts.get(event_type, 0) + 1
        
        return {
            "total_actions": total_actions,
            "event_distribution": event_counts,
            "element_interactions": self.element_interactions,
            "most_interacted_elements": sorted(
                self.element_interactions.items(),
                key=lambda x: x[1],
                reverse=True
            )[:10],
            "session_duration": (
                datetime.fromisoformat(self.action_history[-1]["timestamp"]) - 
                datetime.fromisoformat(self.action_history[0]["timestamp"])
            ).total_seconds() if self.action_history else 0
        }
    
    async def cleanup(self):
        """Clean up Playwright resources"""
        
        try:
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
                
            print("🧹 Playwright cleanup completed")
            
        except Exception as e:
            print(f"⚠️ Cleanup error: {e}")


# Example usage functions
async def demo_cua_playwright_coordination():
    """Demonstrate CUA + Playwright coordination for agentic action tracking"""
    
    print("🎭 CUA + Playwright Coordination Demo")
    print("=" * 50)
    
    integration = PlaywrightCUAIntegration()
    
    try:
        # Connect to CUA Firefox
        connection_result = await integration.connect_to_cua_firefox()
        print(f"✅ Connection: {connection_result}")
        
        # Register event handlers for coordination
        def on_navigation(data):
            print(f"🧭 Navigation Event: {data['url']}")
        
        def on_click(data):
            print(f"👆 Click Event: {data['selector']} -> {data['element_info'].get('text', 'N/A')[:30]}")
        
        integration.register_event_handler('navigation', on_navigation)
        integration.register_event_handler('click', on_click)
        
        # Coordinate actions
        coordination_scenarios = [
            {
                "cua_action": "navigate to https://example.com",
                "playwright_enhancement": {
                    "type": "extract_data",
                    "extraction_config": {"type": "form_fields"}
                }
            },
            {
                "cua_action": "click the first button",
                "playwright_enhancement": {
                    "type": "verify_click",
                    "selector": "button",
                    "expected_state": True
                }
            }
        ]
        
        for scenario in coordination_scenarios:
            print(f"\n🎯 Scenario: {scenario['cua_action']}")
            result = await integration.coordinate_with_cua(
                scenario["cua_action"],
                scenario["playwright_enhancement"]
            )
            print(f"📊 Result: {result['success']}")
        
        # Get analytics
        analytics = integration.get_interaction_analytics()
        print(f"\n📈 Analytics: {analytics['total_actions']} actions, {analytics['session_duration']:.2f}s session")
        
    finally:
        await integration.cleanup()


if __name__ == "__main__":
    asyncio.run(demo_cua_playwright_coordination())
