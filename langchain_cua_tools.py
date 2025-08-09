#!/usr/bin/env python3
"""
LangChain Tools for Computer Use Agent (CUA) Server
Converts the CUA server endpoints into LangChain tools for use with LangGraph agents.
"""

import asyncio
import base64
from typing import Optional, Tuple, List, Dict, Any, Literal
import aiohttp
import requests  # For sync HTTP requests
from langchain_core.tools import tool, BaseTool, StructuredTool
from pydantic import BaseModel, Field


class CUAClient:
    """Client for communicating with the CUA server"""
    
    def __init__(self, host: str = 'localhost', port: int = 8001):
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.session = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def _request(self, method: str, endpoint: str, data: dict = None) -> Dict[str, Any]:
        """Make HTTP request to the CUA server"""
        url = f"{self.base_url}{endpoint}"
        try:
            if method.upper() == "GET":
                async with self.session.get(url) as response:
                    return await response.json()
            elif method.upper() == "POST":
                async with self.session.post(url, json=data) as response:
                    return await response.json()
        except Exception as e:
            import traceback
            print(f"CUA Client Request Error: {e}")
            traceback.print_exc()
            return {"error": str(e), "success": False}


# Global CUA client instance
_cua_client = None

async def get_cua_client() -> CUAClient:
    """Get or create a global CUA client"""
    global _cua_client
    if _cua_client is None:
        _cua_client = CUAClient()
        await _cua_client.__aenter__()
    return _cua_client


# Tool Input Models
class ClickInput(BaseModel):
    x: int = Field(description="X coordinate to click")
    y: int = Field(description="Y coordinate to click")
    button: str = Field(default="left", description="Mouse button (left, right)")


class TypeInput(BaseModel):
    text: str = Field(description="Text to type")


class KeyPressInput(BaseModel):
    keys: List[str] = Field(description="List of keys to press (e.g., ['ctrl', 'c'] or ['Return'])")


class MoveInput(BaseModel):
    x: int = Field(description="X coordinate to move cursor to")
    y: int = Field(description="Y coordinate to move cursor to")


class ScrollInput(BaseModel):
    x: int = Field(description="X coordinate where to scroll")
    y: int = Field(description="Y coordinate where to scroll")
    scroll_x: int = Field(default=0, description="Horizontal scroll amount")
    scroll_y: int = Field(description="Vertical scroll amount")


# LangChain Tools using @tool decorator
@tool
async def take_screenshot() -> str:
    """Take a screenshot of the current screen and return base64 encoded image.
    
    Returns:
        Base64 encoded PNG image of the current screen
    """
    client = await get_cua_client()
    result = await client._request("GET", "/screenshot")
    
    if result.get("success") and "image" in result:
        # Remove data:image/png;base64, prefix if present
        image_str = result["image"]
        if image_str.startswith("data:image/png;base64,"):
            image_str = image_str.replace("data:image/png;base64,", "")
        return image_str
    else:
        return f"Screenshot failed: {result.get('error', 'Unknown error')}"


@tool
async def click_at_coordinates(x: int, y: int, button: str = "left") -> str:
    """Click at the specified coordinates.
    
    Args:
        x: X coordinate to click
        y: Y coordinate to click  
        button: Mouse button to use (left, right)
        
    Returns:
        Success message or error description
    """
    client = await get_cua_client()
    result = await client._request("POST", "/click", {"x": x, "y": y, "button": button})
    
    if result.get("success"):
        return f"Successfully clicked at ({x}, {y}) with {button} button"
    else:
        return f"Click failed: {result.get('error', 'Unknown error')}"


@tool
async def type_text(text: str) -> str:
    """Type the specified text.
    
    Args:
        text: Text to type
        
    Returns:
        Success message or error description
    """
    client = await get_cua_client()
    result = await client._request("POST", "/type", {"text": text})
    
    if result.get("success"):
        return f"Successfully typed: {text}"
    else:
        return f"Type failed: {result.get('error', 'Unknown error')}"


@tool  
async def press_keys(keys: List[str]) -> str:
    """Press the specified key combination.
    
    Args:
        keys: List of keys to press (e.g., ['ctrl', 'c'] for Ctrl+C, ['Return'] for Enter)
        
    Returns:
        Success message or error description
    """
    client = await get_cua_client()
    result = await client._request("POST", "/key_press", {"keys": keys})
    
    if result.get("success"):
        return f"Successfully pressed keys: {'+'.join(keys)}"
    else:
        return f"Key press failed: {result.get('error', 'Unknown error')}"


@tool
async def move_cursor(x: int, y: int) -> str:
    """Move the mouse cursor to the specified coordinates.
    
    Args:
        x: X coordinate to move to
        y: Y coordinate to move to
        
    Returns:
        Success message or error description
    """
    client = await get_cua_client()
    result = await client._request("POST", "/move", {"x": x, "y": y})
    
    if result.get("success"):
        return f"Successfully moved cursor to ({x}, {y})"
    else:
        return f"Move failed: {result.get('error', 'Unknown error')}"


@tool
async def scroll_at_location(x: int, y: int, scroll_x: int = 0, scroll_y: int = -3) -> str:
    """Scroll at the specified location.
    
    Args:
        x: X coordinate where to scroll
        y: Y coordinate where to scroll
        scroll_x: Horizontal scroll amount (positive = right, negative = left)
        scroll_y: Vertical scroll amount (positive = down, negative = up)
        
    Returns:
        Success message or error description
    """
    client = await get_cua_client()
    result = await client._request("POST", "/scroll", {
        "x": x, "y": y, "scroll_x": scroll_x, "scroll_y": scroll_y
    })
    
    if result.get("success"):
        return f"Successfully scrolled at ({x}, {y}) by ({scroll_x}, {scroll_y})"
    else:
        return f"Scroll failed: {result.get('error', 'Unknown error')}"


@tool
async def double_click_at_coordinates(x: int, y: int) -> str:
    """Double-click at the specified coordinates.
    
    Args:
        x: X coordinate to double-click
        y: Y coordinate to double-click
        
    Returns:
        Success message or error description
    """
    client = await get_cua_client()
    result = await client._request("POST", "/double_click", {"x": x, "y": y})
    
    if result.get("success"):
        return f"Successfully double-clicked at ({x}, {y})"
    else:
        return f"Double-click failed: {result.get('error', 'Unknown error')}"


@tool
async def get_screen_dimensions() -> str:
    """Get the current screen dimensions.
    
    Returns:
        Screen dimensions as "width x height"
    """
    client = await get_cua_client()
    result = await client._request("GET", "/dimensions")
    
    if result.get("success"):
        width = result.get("width", 0)
        height = result.get("height", 0)
        return f"Screen dimensions: {width} x {height}"
    else:
        return f"Failed to get dimensions: {result.get('error', 'Unknown error')}"


# Advanced tool with return artifacts
@tool(response_format="content_and_artifact")
async def take_screenshot_with_metadata() -> Tuple[str, Dict[str, Any]]:
    """Take a screenshot and return both description and full metadata.
    
    Returns:
        Tuple of (description, metadata_dict) where metadata contains the full screenshot data
    """
    client = await get_cua_client()
    result = await client._request("GET", "/screenshot")
    
    if result.get("success") and "image" in result:
        image_str = result["image"]
        if image_str.startswith("data:image/png;base64,"):
            image_str = image_str.replace("data:image/png;base64,", "")
        
        # Get dimensions for metadata
        dims_result = await client._request("GET", "/dimensions")
        width = dims_result.get("width", 0) if dims_result.get("success") else 0
        height = dims_result.get("height", 0) if dims_result.get("success") else 0
        
        content = f"Screenshot taken successfully ({width}x{height})"
        artifact = {
            "image_base64": image_str,
            "width": width,
            "height": height,
            "format": "PNG"
        }
        return content, artifact
    else:
        error_msg = f"Screenshot failed: {result.get('error', 'Unknown error')}"
        return error_msg, {"error": True, "message": error_msg}


# Class-based tool example
class NavigateToURL(BaseTool):
    """Tool for navigating to a URL using the CUA interface"""
    
    name: str = "navigate_to_url"
    description: str = "Navigate to a URL by focusing address bar, typing URL, and pressing Enter"
    
    async def _arun(self, url: str) -> str:
        """Navigate to the specified URL"""
        client = await get_cua_client()
        
        try:
            # Step 1: Press Ctrl+L to focus address bar
            result1 = await client._request("POST", "/key_press", {"keys": ["ctrl", "l"]})
            if not result1.get("success"):
                return f"Failed to focus address bar: {result1.get('error', 'Unknown error')}"
            
            # Step 2: Type the URL
            result2 = await client._request("POST", "/type", {"text": url})
            if not result2.get("success"):
                return f"Failed to type URL: {result2.get('error', 'Unknown error')}"
            
            # Step 3: Press Enter
            result3 = await client._request("POST", "/key_press", {"keys": ["Return"]})
            if not result3.get("success"):
                return f"Failed to press Enter: {result3.get('error', 'Unknown error')}"
            
            return f"Successfully navigated to {url}"
            
        except Exception as e:
            return f"Navigation failed: {str(e)}"
    
    def _run(self, url: str) -> str:
        """Sync version - not recommended, use async version"""
        raise NotImplementedError("Use the async version _arun instead")


# Sync HTTP client for LangGraph compatibility
class SyncCUAClient:
    """Sync HTTP client for CUA server - no event loop conflicts"""
    
    def __init__(self, host: str = 'localhost', port: int = 8001):
        self.base_url = f"http://{host}:{port}"
    
    def _request(self, method: str, endpoint: str, data: dict = None) -> Dict[str, Any]:
        """Make sync HTTP request to the CUA server"""
        url = f"{self.base_url}{endpoint}"
        try:
            if method.upper() == "GET":
                response = requests.get(url, timeout=10)
                return response.json()
            elif method.upper() == "POST":
                response = requests.post(url, json=data, timeout=10)
                return response.json()
        except Exception as e:
            print(f"Sync CUA Client Request Error: {e}")
            return {"error": str(e), "success": False}


# Create sync versions of our tools using requests
def create_sync_tools():
    """Create sync-compatible versions of all CUA tools using requests"""
    
    sync_client = SyncCUAClient()
    
    def sync_screenshot() -> dict:
        """Sync version of take_screenshot - returns image content for multimodal LLMs"""
        try:
            result = sync_client._request("GET", "/screenshot")
            if result.get("success") and "image" in result:
                image_str = result["image"]
                if image_str.startswith("data:image/png;base64,"):
                    image_str = image_str.replace("data:image/png;base64,", "")
                
                # Return proper image content structure for multimodal LLMs
                return {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{image_str}"
                    }
                }
            else:
                return {"error": f"Screenshot failed: {result.get('error', 'Unknown error')}"}
        except Exception as e:
            return {"error": f"Screenshot failed: {str(e)}"}
    
    def sync_screenshot_description() -> str:
        """Alternative screenshot function that returns a text description"""
        try:
            result = sync_client._request("GET", "/screenshot")
            if result.get("success") and "image" in result:
                return "Screenshot captured successfully. The image shows the current state of the desktop/browser."
            else:
                return f"Screenshot failed: {result.get('error', 'Unknown error')}"
        except Exception as e:
            return f"Screenshot failed: {str(e)}"
    
    def sync_click(x: int, y: int, button: str = "left") -> str:
        """Sync version of click_at_coordinates"""
        try:
            result = sync_client._request("POST", "/click", {"x": x, "y": y, "button": button})
            if result.get("success"):
                return f"Successfully clicked at ({x}, {y}) with {button} button"
            else:
                return f"Click failed: {result.get('error', 'Unknown error')}"
        except Exception as e:
            return f"Click failed: {str(e)}"
    
    def sync_type(text: str) -> str:
        """Sync version of type_text"""
        try:
            result = sync_client._request("POST", "/type", {"text": text})
            if result.get("success"):
                return f"Successfully typed: {text}"
            else:
                return f"Type failed: {result.get('error', 'Unknown error')}"
        except Exception as e:
            return f"Type failed: {str(e)}"
    
    def sync_press_keys(keys: List[str]) -> str:
        """Sync version of press_keys"""
        try:
            result = sync_client._request("POST", "/key_press", {"keys": keys})
            if result.get("success"):
                return f"Successfully pressed keys: {'+'.join(keys)}"
            else:
                return f"Key press failed: {result.get('error', 'Unknown error')}"
        except Exception as e:
            return f"Key press failed: {str(e)}"
    
    def sync_navigate(url: str) -> str:
        """Sync version of navigate to URL"""
        try:
            # Step 1: Focus address bar
            result1 = sync_client._request("POST", "/key_press", {"keys": ["ctrl", "l"]})
            if not result1.get("success"):
                return f"Failed to focus address bar: {result1.get('error', 'Unknown error')}"
            
            # Step 2: Type URL
            result2 = sync_client._request("POST", "/type", {"text": url})
            if not result2.get("success"):
                return f"Failed to type URL: {result2.get('error', 'Unknown error')}"
            
            # Step 3: Press Enter
            result3 = sync_client._request("POST", "/key_press", {"keys": ["Return"]})
            if not result3.get("success"):
                return f"Failed to press Enter: {result3.get('error', 'Unknown error')}"
            
            return f"Successfully navigated to {url}"
        except Exception as e:
            return f"Navigation failed: {str(e)}"
    
    # Create StructuredTool instances for LangGraph
    screenshot_tool = StructuredTool.from_function(
        func=sync_screenshot,
        name="take_screenshot",
        description="Take a screenshot of the current screen and return image content for multimodal analysis"
    )
    
    screenshot_desc_tool = StructuredTool.from_function(
        func=sync_screenshot_description,
        name="take_screenshot_text",
        description="Take a screenshot and return a text description (for non-multimodal models)"
    )
    
    click_tool = StructuredTool.from_function(
        func=sync_click,
        name="click_at_coordinates",
        description="Click at specified coordinates"
    )
    
    type_tool = StructuredTool.from_function(
        func=sync_type,
        name="type_text", 
        description="Type the specified text"
    )
    
    keys_tool = StructuredTool.from_function(
        func=sync_press_keys,
        name="press_keys",
        description="Press key combinations like ['ctrl', 'c'] or ['Return']"
    )
    
    navigate_tool = StructuredTool.from_function(
        func=sync_navigate,
        name="navigate_to_url",
        description="Navigate to a URL in the browser"
    )
    
    return [screenshot_tool, screenshot_desc_tool, click_tool, type_tool, keys_tool, navigate_tool]


# Convenience function to get all tools
def get_all_cua_tools() -> List[Any]:
    """Get all CUA tools for use with LangGraph agents"""
    # Use the sync-compatible versions for LangGraph
    sync_tools = create_sync_tools()
    
    # Add the class-based tool
    sync_tools.append(NavigateToURL())
    
    return sync_tools


# Cleanup function
async def cleanup_cua_client():
    """Cleanup the global CUA client"""
    global _cua_client
    if _cua_client:
        await _cua_client.__aexit__(None, None, None)
        _cua_client = None


if __name__ == "__main__":
    # Example usage
    async def test_tools():
        """Test the CUA tools"""
        print("Testing CUA LangChain Tools...")
        
        # Test screenshot
        screenshot_result = await take_screenshot.ainvoke({})
        print(f"Screenshot: {screenshot_result[:50]}...")
        
        # Test dimensions
        dimensions = await get_screen_dimensions.ainvoke({})
        print(f"Dimensions: {dimensions}")
        
        # Test navigation
        nav_tool = NavigateToURL()
        nav_result = await nav_tool._arun("https://example.com")
        print(f"Navigation: {nav_result}")
        
        # Cleanup
        await cleanup_cua_client()
    
    asyncio.run(test_tools())
