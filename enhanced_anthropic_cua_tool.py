#!/usr/bin/env python3
"""
Enhanced Anthropic CUA Tool with OmniParser Integration
Combines OmniParser V2 GUI element detection with Anthropic Claude vision analysis
"""

import base64
import requests
from typing import Dict, List, Any, Optional
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field
from langchain_cua_tools import SyncCUAClient
from omniparser_client import OmniParserClient
import os
from anthropic import Anthropic


class EnhancedAnthropicCUATool(BaseTool):
    """Enhanced screenshot tool with OmniParser GUI element detection + Anthropic vision analysis"""
    
    name: str = "take_screenshot_and_analyze_enhanced"
    description: str = """Take a screenshot, detect GUI elements with OmniParser V2, and analyze with Anthropic Claude vision.
    
    This tool provides:
    1. Current screen screenshot
    2. Precise bounding boxes around all interactive elements  
    3. Descriptions of each clickable element
    4. AI analysis of screen content and available actions
    5. Recommendations for next steps
    
    Returns comprehensive screen analysis with actionable element coordinates."""
    
    def __init__(self):
        super().__init__()
        # Initialize clients outside of Pydantic fields
        self._cua_client = SyncCUAClient()
        self._omniparser_client = OmniParserClient()
        self._anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    
    @property
    def cua_client(self):
        return self._cua_client
    
    @property
    def omniparser_client(self):
        return self._omniparser_client
    
    @property
    def anthropic_client(self):
        return self._anthropic_client
    
    def _run(self, analyze_task: str = "Analyze this screen and identify available actions") -> str:
        """
        Take enhanced screenshot with OmniParser element detection + Anthropic analysis
        
        Args:
            analyze_task: Specific analysis task (e.g., "Find login button", "Identify navigation options")
        
        Returns:
            Comprehensive analysis of screen with precise element locations
        """
        try:
            # Step 1: Take screenshot
            screenshot_result = self.cua_client._request("GET", "/screenshot")
            if not screenshot_result.get("success") or "image" not in screenshot_result:
                return f"Failed to take screenshot: {screenshot_result.get('error', 'Unknown error')}"
            
            # Clean base64 image
            base64_image = screenshot_result["image"]
            if base64_image.startswith("data:image/png;base64,"):
                base64_image = base64_image.replace("data:image/png;base64,", "")
            
            # Step 2: Parse GUI elements with OmniParser
            if not self.omniparser_client.health_check():
                return "⚠️ OmniParser server not available. Taking regular screenshot analysis."
            
            parse_result = self.omniparser_client.parse_screenshot(base64_image)
            
            if "error" in parse_result:
                # Fall back to regular analysis if OmniParser fails
                print(f"OmniParser failed: {parse_result['error']}")
                return self._fallback_analysis(base64_image, analyze_task)
            
            # Step 3: Get annotated image and processed element list
            # Try the new field first, fall back to som_image_base64 for compatibility
            annotated_image = parse_result.get("annotated_image_base64", parse_result.get("som_image_base64", ""))
            raw_elements = parse_result.get("parsed_content_list", [])
            latency = parse_result.get("latency", 0)
            
            # Convert raw elements to our format with pixel coordinates
            elements = self.omniparser_client.get_clickable_elements(base64_image)
            
            # DEBUG: Look for social media interaction elements
            like_elements = [e for e in elements if any(keyword in e.get("description", "").lower() for keyword in ["heart", "like", "favorite", "♥", "♡"])]
            
            # Also look for potential interaction buttons in post areas (small icons)
            interaction_buttons = []
            for elem in elements:
                if (elem.get("type", "").lower() == "icon" and 
                    elem.get("interactable", False) and
                    elem.get("center_y", 0) > 300 and elem.get("center_y", 0) < 500):  # Post interaction area
                    interaction_buttons.append(elem)
            
            if like_elements:
                print(f"\n❤️ Found explicit like elements: {len(like_elements)}")
                for elem in like_elements:
                    print(f"   • {elem.get('description', '')} at ({elem.get('center_x', 0)}, {elem.get('center_y', 0)})")
            else:
                print(f"\n🔍 No explicit like/heart elements found among {len(elements)} total elements")
            
            if interaction_buttons:
                print(f"\n📱 Found {len(interaction_buttons)} potential interaction buttons in post area:")
                for i, elem in enumerate(interaction_buttons):
                    center_x, center_y = elem.get('center_x', 0), elem.get('center_y', 0)
                    desc = elem.get('description', '')[:30]
                    print(f"   • [{center_x:4d},{center_y:3d}] {desc}")
            else:
                print(f"\n📱 No interaction buttons detected in post area")
            
            # DEBUG: Print ALL elements with their indices/bounding box numbers
            print(f"\n🔍 ALL DETECTED ELEMENTS (showing all {len(raw_elements)}):")
            for i, element in enumerate(raw_elements):
                type = element.get('type', '')
                bbox = element.get('bbox', [])
                content = element.get('content', '')[:40]
                interactivity = element.get('interactivity', False)
                if bbox and len(bbox) >= 4:
                    # Convert to pixel coordinates
                    x1 = int(bbox[0] * 1280)
                    y1 = int(bbox[1] * 720)
                    x2 = int(bbox[2] * 1280) 
                    y2 = int(bbox[3] * 720)
                    center_x = int((x1 + x2) / 2)
                    center_y = int((y1 + y2) / 2)
                    interactive_flag = "✅" if interactivity else "❌"
                    print(f"   #{i:2d}: [{center_x:4d},{center_y:3d}] {interactive_flag} [{type:8s}] \"{content}\"")
                else:
                    print(f"   #{i:2d}: [NO_COORDS] ❌ [{type:8s}] \"{content}\"")
            
            # DEBUG: Save annotated image for inspection
            if annotated_image:
                try:
                    import base64
                    import io
                    from PIL import Image
                    
                    # Decode and save the annotated image
                    img_data = base64.b64decode(annotated_image)
                    img = Image.open(io.BytesIO(img_data))
                    img.save('/tmp/omniparser_annotated.png')
                    print(f"\n💾 Saved annotated image to: /tmp/omniparser_annotated.png")
                except Exception as e:
                    print(f"\n⚠️ Could not save annotated image: {e}")
            else:
                print(f"\n⚠️ No annotated image available from OmniParser")
            
            # Step 4: Prepare analysis prompt for Anthropic
            elements_text = self._format_elements_for_analysis(elements)
            
            analysis_prompt = f"""Analyze this screenshot with detected GUI elements:

TASK: {analyze_task}

DETECTED INTERACTIVE ELEMENTS:
{elements_text}

Please provide:
1. Current screen description
2. Available actions with specific coordinates
3. Recommended next steps for the task
4. Any important UI state information

Focus on actionable elements with precise coordinate guidance."""

            # Step 5: Send to Anthropic for vision analysis with annotated image
            try:
                # Use annotated image with bounding boxes if available, otherwise use original
                image_to_analyze = annotated_image if annotated_image else base64_image
                
                # Enhanced prompt that tells Claude about the bounding boxes
                enhanced_prompt = f"""{analysis_prompt}

🎯 **IMPORTANT**: This image has been annotated by OmniParser V2 with colored bounding boxes around detected elements.
- Each colored box shows a detected interactive element with precise coordinates
- Social media interaction buttons (like, share, comment, retweet) are typically small icons in rows below posts
- Look for clusters of small icons/buttons in the post interaction area
- Heart/like buttons may appear as generic icons but are usually the FIRST in a row of interaction buttons
- Use the bounding boxes to identify exact pixel locations for clicking
- Pay special attention to small icon elements with coordinates around Y:330-400 (typical interaction button area)

**Focus on finding**: Heart/like buttons, share buttons, comment buttons, and other social media interactions."""

                response = self.anthropic_client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=1000,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": enhanced_prompt},
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": image_to_analyze
                                }
                            }
                        ]
                    }]
                )
                
                anthropic_analysis = response.content[0].text
                
                # Step 6: Combine results
                result = f"""🔍 **ENHANCED SCREEN ANALYSIS** (OmniParser V2 + Claude Vision)

📊 **Detection Stats**: {len(elements)} interactive elements found in {latency:.2f}s

🤖 **AI Analysis**:
{anthropic_analysis}

🎯 **Precise Element Coordinates**:
{self._format_clickable_elements(elements)}

💡 **Usage**: Use click_at_coordinates(x, y) with the exact coordinates above for precise interaction.
"""
                return result
                
            except Exception as e:
                return f"Anthropic analysis failed: {str(e)}. Using OmniParser results only.\n\n{elements_text}"
        
        except Exception as e:
            return f"Enhanced screenshot analysis failed: {str(e)}"
    
    def _format_elements_for_analysis(self, elements: List[Dict]) -> str:
        """Format detected elements for Anthropic analysis"""
        if not elements:
            return "No interactive elements detected."
        
        formatted = []
        for i, element in enumerate(elements, 1):
            coords = element.get("coordinates", [])
            desc = element.get("description", "Unknown element")
            interactable = element.get("interactable", True)
            
            if len(coords) >= 4:
                center_x = int((coords[0] + coords[2]) / 2)
                center_y = int((coords[1] + coords[3]) / 2)
                status = "✅ Clickable" if interactable else "ℹ️ Info only"
                formatted.append(f"{i}. {desc} - Center: ({center_x}, {center_y}) - {status}")
        
        return "\n".join(formatted)
    
    def _format_clickable_elements(self, elements: List[Dict]) -> str:
        """Format clickable elements with precise coordinates"""
        # Filter for interactive elements and elements with content
        clickable = []
        for e in elements:
            # Include if explicitly interactive OR if it has meaningful content (buttons, links, etc.)
            is_interactive = e.get("interactable", False) or e.get("interactivity", False)
            has_content = e.get("description", "").strip() != ""
            element_type = e.get("type", "")
            
            # Include interactive elements or elements that likely represent UI controls
            if is_interactive or (has_content and element_type in ["text", "icon", "button"]):
                clickable.append(e)
        
        if not clickable:
            return "No clickable elements detected."
        
        formatted = []
        for element in clickable[:15]:  # Limit to top 15 most relevant
            coords = element.get("coordinates", [])
            desc = element.get("description", "Unknown element")
            element_type = element.get("type", "")
            
            if len(coords) >= 4 and desc.strip():
                center_x = element.get("center_x", int((coords[0] + coords[2]) / 2))
                center_y = element.get("center_y", int((coords[1] + coords[3]) / 2))
                formatted.append(f"• {desc} ({element_type}): click_at_coordinates({center_x}, {center_y})")
        
        return "\n".join(formatted)

    def _fallback_analysis(self, base64_image: str, analyze_task: str) -> str:
        """Fallback to regular Anthropic vision analysis if OmniParser fails"""
        try:
            analysis_prompt = f"""Analyze this screenshot and provide guidance for computer automation:

TASK: {analyze_task}

Please provide:
1. Current screen description
2. Available interactive elements (estimate coordinates)
3. Recommended next steps
4. Any important UI state information

Focus on actionable elements that can be clicked or interacted with."""

            response = self.anthropic_client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1000,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": analysis_prompt},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png", 
                                "data": base64_image
                            }
                        }
                    ]
                }]
            )
            
            analysis = response.content[0].text
            
            return f"""📸 **STANDARD SCREEN ANALYSIS** (OmniParser fallback)

⚠️ **Note**: OmniParser V2 is temporarily unavailable, using standard vision analysis.

🤖 **AI Analysis**:
{analysis}

💡 **Usage**: Use approximate coordinates based on visual analysis. For precise targeting, ensure OmniParser V2 server is running properly.
"""
            
        except Exception as e:
            return f"Both OmniParser and fallback analysis failed: {str(e)}"


class SmartElementFinder(BaseTool):
    """Tool to find specific elements using OmniParser + semantic matching"""
    
    name: str = "find_element_smart"
    description: str = """Find a specific UI element by description using OmniParser detection.
    
    Examples:
    - "login button"
    - "search box" 
    - "submit form"
    - "close window"
    
    Returns exact coordinates for the matching element."""
    
    def __init__(self):
        super().__init__()
        self._cua_client = SyncCUAClient()
        self._omniparser_client = OmniParserClient()
    
    @property
    def cua_client(self):
        return self._cua_client
    
    @property
    def omniparser_client(self):
        return self._omniparser_client
    
    def _run(self, element_description: str) -> str:
        """Find element by description and return coordinates"""
        try:
            # Take screenshot
            screenshot_result = self.cua_client._request("GET", "/screenshot")
            if not screenshot_result.get("success"):
                return f"Failed to take screenshot: {screenshot_result.get('error')}"
            
            base64_image = screenshot_result["image"]
            if base64_image.startswith("data:image/png;base64,"):
                base64_image = base64_image.replace("data:image/png;base64,", "")
            
            # Find element using OmniParser
            element = self.omniparser_client.find_element_by_description(base64_image, element_description)
            
            if element:
                x, y = element["center_x"], element["center_y"]
                desc = element["description"]
                return f"✅ Found '{element_description}': {desc} at coordinates ({x}, {y}). Use click_at_coordinates({x}, {y}) to interact."
            else:
                # List available elements as fallback
                elements = self.omniparser_client.get_clickable_elements(base64_image)
                available = [e["description"] for e in elements[:5]]  # Top 5
                return f"❌ Could not find '{element_description}'. Available elements: {', '.join(available)}"
        
        except Exception as e:
            return f"Element search failed: {str(e)}"


def create_complete_anthropic_cua_tools():
    """Create enhanced CUA tools with OmniParser integration"""
    from langchain_cua_tools import create_sync_tools
    from smart_like_tool import SmartLikeTool
    
    # Get base CUA tools
    base_tools = create_sync_tools()
    
    # Add enhanced tools
    enhanced_tools = [
        EnhancedAnthropicCUATool(),
        SmartElementFinder(),
        SmartLikeTool()
    ]
    
    return base_tools + enhanced_tools


if __name__ == "__main__":
    # Test the enhanced tool
    print("Testing Enhanced Anthropic CUA Tool...")
    
    tool = EnhancedAnthropicCUATool()
    result = tool._run("Analyze current screen and identify clickable elements")
    print(result)
