#!/usr/bin/env python3
"""
Smart Like Button Tool - Enhanced strategy for finding and clicking like buttons
"""

from langchain_core.tools import BaseTool
from langchain_cua_tools import SyncCUAClient
from enhanced_anthropic_cua_tool import EnhancedAnthropicCUATool
from dotenv import load_dotenv
import time

load_dotenv()

class SmartLikeTool(BaseTool):
    """Smart tool for finding and clicking like buttons with scrolling strategy"""
    
    name: str = "smart_like_button"
    description: str = """Find and click like/heart buttons on social media posts with intelligent scrolling.
    
    This tool:
    1. Scrolls to find posts and like buttons
    2. Centers the post on screen for better targeting
    3. Looks for heart icons, not just text
    4. Verifies the like action worked by checking visual changes
    
    Use this for liking posts, tweets, or any content with heart/like buttons."""
    
    def __init__(self):
        super().__init__()
        self._cua_client = SyncCUAClient()
        self._enhanced_tool = EnhancedAnthropicCUATool()
    
    @property
    def cua_client(self):
        return self._cua_client
    
    @property
    def enhanced_tool(self):
        return self._enhanced_tool
    
    def _run(self, post_description: str = "AI-related post") -> str:
        """Find and like a post using smart scrolling strategy"""
        try:
            step = 1
            max_scrolls = 5
            
            print(f"\n🎯 SMART LIKE STRATEGY: Looking for {post_description}")
            
            # Step 1: Take initial screenshot to see current state
            print(f"\n📸 Step {step}: Taking initial screenshot...")
            result = self.enhanced_tool._run(f"Find like/heart buttons for {post_description}. Look for heart icons ♥ 💖 not just text.")
            step += 1
            
            # Step 2: Smart scroll strategy to find like buttons for this specific post
            # We'll try multiple scroll positions to reveal the like button for the target post
            like_button_found = False
            
            for scroll_attempt in range(max_scrolls):
                print(f"\n🔍 Step {step}: Looking for like button (attempt {scroll_attempt + 1}/{max_scrolls})")
                
                # Look for the target post and its like button
                current_analysis = self.enhanced_tool._run(
                    f"Find the post about '{post_description}' and its like/heart button. "
                    "Look for small interactive icons below the post content. "
                    "The like button is typically the FIRST icon in a row of social interaction buttons. "
                    "If you see the post but the like button is cut off or hidden, note that we need to scroll."
                )
                
                # Check if we can find AND EXTRACT clickable coordinates for like button
                potential_found = ("Navigation" in current_analysis or "like" in current_analysis.lower() or 
                                 "heart" in current_analysis.lower() or "♥" in current_analysis or
                                 "Heart at (" in current_analysis or "❤️ Found explicit like elements" in current_analysis)
                
                if potential_found:
                    print(f"🎯 Potential like button detected in attempt {scroll_attempt + 1}")
                    
                    # Try to extract coordinates to verify we have actionable data
                    import re
                    test_patterns = [
                        r'Heart at \((\d+), (\d+)\)',  # Direct heart coordinates from our debug output
                        r'#\d+:\s*\[\s*(\d+),\s*(\d+)\].*?\[icon\s*\].*?"Heart"',  # Heart icon element
                        r'\[\s*(\d+),\s*(\d+)\].*Navigation',  # Navigation button coordinates
                        r'•\s*\[\s*(\d+),\s*(\d+)\]\s*Navigation',  # List format
                        r'Navigation.*?\[\s*(\d+),\s*(\d+)\]',  # Navigation with coordinates
                        r'#\d+:\s*\[\s*(\d+),\s*(\d+)\].*?K\s*"',  # Engagement numbers (like "49K")
                        r'\[\s*(\d+),\s*(\d+)\].*?\d+K',  # Pattern for like counts
                    ]
                    
                    coords_found = False
                    like_button_x, like_button_y = None, None
                    
                    # Look for engagement icon elements (not text!)
                    engagement_patterns = [
                        r'#\d+:\s*\[\s*(\d+),\s*(\d+)\].*?\[icon\s*\].*?"(\d+\.?\d*K?)"',  # Icon with K numbers
                        r'#\d+:\s*\[\s*(\d+),\s*(\d+)\].*?\[icon\s*\].*?"(\d+)"',  # Icon with any numbers
                    ]
                    
                    # Find all engagement numbers in the post interaction area
                    engagement_elements = []
                    for pattern in engagement_patterns:
                        for match in re.finditer(pattern, current_analysis):
                            x, y = int(match.group(1)), int(match.group(2))
                            text = match.group(3)
                            # Only consider elements in the post interaction area
                            if 400 <= y <= 500 and 300 <= x <= 800:
                                engagement_elements.append((x, y, text))
                    
                    if engagement_elements:
                        # Sort by X coordinate to find the leftmost engagement element
                        engagement_elements.sort(key=lambda e: e[0])
                        leftmost_x, leftmost_y, leftmost_text = engagement_elements[0]
                        
                        # Heart button is typically 30-50 pixels to the LEFT of the leftmost engagement number
                        # This is a reasonable estimate based on Twitter's UI layout
                        like_button_x = leftmost_x - 40  
                        like_button_y = leftmost_y
                        
                        print(f"✅ Found engagement element '{leftmost_text}' at ({leftmost_x}, {leftmost_y})")
                        print(f"🎯 Calculated heart button position: ({like_button_x}, {like_button_y}) [40px left of engagement]")
                        coords_found = True
                    else:
                        # Fallback to original patterns
                        for pattern in test_patterns:
                            test_match = re.search(pattern, current_analysis)
                            print(f"🔍 DEBUG: Testing pattern '{pattern[:40]}...': {'MATCHED' if test_match else 'FAILED'}")
                            if test_match:
                                test_x, test_y = int(test_match.group(1)), int(test_match.group(2))
                                print(f"🔍 DEBUG: Extracted coordinates: ({test_x}, {test_y})")
                                # Verify coordinates are in reasonable range for interaction buttons
                                if 300 <= test_x <= 800 and 250 <= test_y <= 600:
                                    print(f"✅ Valid coordinates found: ({test_x}, {test_y})")
                                    like_button_x, like_button_y = test_x, test_y
                                    coords_found = True
                                    break
                                else:
                                    print(f"❌ Coordinates ({test_x}, {test_y}) out of range: X must be 300-800, Y must be 250-600")
                    
                    if coords_found:
                        like_button_found = True
                        result = current_analysis
                        break
                    else:
                        print(f"⚠️ Found potential button but no valid coordinates, continuing to scroll...")
                else:
                    print(f"🔍 No like button indicators found in attempt {scroll_attempt + 1}")
                
                # If not found, scroll down slightly to reveal more of the post
                if scroll_attempt < max_scrolls - 1:
                    print(f"\n📜 Scrolling to reveal like button for the target post...")
                    scroll_result = self.cua_client._request("POST", "/scroll", {
                        "x": 640, "y": 400, "scroll_x": 0, "scroll_y": 2  # Smaller scroll
                    })
                    
                    if scroll_result.get("success"):
                        print(f"✅ Scrolled successfully")
                        time.sleep(1)  # Wait for content to load
                        step += 1
                    else:
                        print(f"❌ Scroll failed: {scroll_result}")
                        break
            
            if not like_button_found:
                return f"⚠️ Could not find like button for {post_description} after {max_scrolls} scroll attempts. The post might not be visible or have like functionality."
            
            # Step 3: Try to click based on visual analysis
            step += 1
            print(f"\n👆 Step {step}: Attempting to click like button...")
            
            # Use the analysis that successfully found the like button (from scroll loop)
            click_analysis = result
            
            # Extract coordinates using our improved spatial reasoning
            import re
            x, y = None, None
            
            # PRIORITY 1: Look for DIRECT heart coordinates first, then engagement elements
            direct_heart_patterns = [
                r'Heart at \((\d+), (\d+)\)',  # Direct heart coordinates from our debug output
                r'#\d+:\s*\[\s*(\d+),\s*(\d+)\].*?\[icon\s*\].*?"Heart"',  # Heart icon element
            ]
            
            # Check for direct heart coordinates first
            print(f"🔍 DEBUG: Searching for heart coordinates in click_analysis...")
            print(f"🔍 DEBUG: First 200 chars of click_analysis: {click_analysis[:200]}...")
            
            for i, pattern in enumerate(direct_heart_patterns):
                heart_match = re.search(pattern, click_analysis)
                print(f"🔍 DEBUG: Pattern {i+1} ({pattern[:30]}...): {'MATCHED' if heart_match else 'FAILED'}")
                if heart_match:
                    x, y = int(heart_match.group(1)), int(heart_match.group(2))
                    print(f"🎯 Found DIRECT heart coordinates: ({x}, {y})")
                    break
            
            # Fallback: Look for engagement elements to calculate heart position
            if x is None:
                engagement_patterns = [
                    r'#\d+:\s*\[\s*(\d+),\s*(\d+)\].*?\[icon\s*\].*?"(\d+\.?\d*K?)"',  # Icon with K numbers
                    r'#\d+:\s*\[\s*(\d+),\s*(\d+)\].*?\[icon\s*\].*?"(\d+)"',  # Icon with any numbers
                ]
            
            # Find all engagement numbers in the post interaction area
            engagement_elements = []
            for pattern in engagement_patterns:
                for match in re.finditer(pattern, click_analysis):
                    eng_x, eng_y = int(match.group(1)), int(match.group(2))
                    eng_text = match.group(3)
                    # Only consider elements in the post interaction area
                    if 400 <= eng_y <= 500 and 300 <= eng_x <= 800:
                        engagement_elements.append((eng_x, eng_y, eng_text))
            
            if engagement_elements:
                # Sort by X coordinate to find the leftmost engagement element  
                engagement_elements.sort(key=lambda e: e[0])
                leftmost_x, leftmost_y, leftmost_text = engagement_elements[0]
                
                # Heart button is 40 pixels to the LEFT of the leftmost engagement number
                x = leftmost_x - 40
                y = leftmost_y
                print(f"🎯 Using spatial reasoning: Found '{leftmost_text}' at ({leftmost_x}, {leftmost_y})")
                print(f"💖 Calculated heart button at: ({x}, {y}) [40px left of leftmost engagement]")
            else:
                # FALLBACK: Try other coordinate extraction patterns
                patterns = [
                    r'click_at_coordinates\((\d+),\s*(\d+)\)',  # click_at_coordinates(x, y)
                    r'\[\s*(\d+),\s*(\d+)\]',  # [x, y] format from our debug output
                    r'\(\s*(\d+),\s*(\d+)\)',  # (x, y) format
                    r'Navigation.*?\[\s*(\d+),\s*(\d+)\]',  # Navigation button coordinates
                    r'coordinates?\s*[:\-]\s*\(?(\d+),\s*(\d+)\)?'  # coordinates: x, y
                ]
                
                for pattern in patterns:
                    coord_match = re.search(pattern, click_analysis)
                    if coord_match:
                        x, y = int(coord_match.group(1)), int(coord_match.group(2))
                        print(f"🎯 Extracted coordinates using pattern '{pattern}': ({x}, {y})")
                        break
            
            if x is not None and y is not None:
                print(f"🎯 Clicking at coordinates: ({x}, {y})")
                
                # Perform the click
                click_result = self.cua_client._request("POST", "/click", {"x": x, "y": y})
                
                if click_result.get("success"):
                    time.sleep(1)  # Wait for visual change
                    
                    # Step 4: Verify the like action worked
                    step += 1
                    print(f"\n✅ Step {step}: Verifying like action...")
                    verification = self.enhanced_tool._run(
                        "Check if the like button changed state after clicking. "
                        "Look for visual changes: empty heart → filled heart, white → red color, etc. "
                        "Compare the current state with what you saw before."
                    )
                    
                    if any(word in verification.lower() for word in ["filled", "red", "liked", "changed", "activated"]):
                        return f"🎉 Successfully liked the {post_description}! The heart button changed state, indicating the like action worked."
                    else:
                        return f"⚠️ Clicked at ({x}, {y}) but no visual change detected. The like action may not have worked properly."
                else:
                    return f"❌ Failed to click at coordinates ({x}, {y}): {click_result.get('error', 'Unknown error')}"
            else:
                return f"❌ Could not extract coordinates from analysis. Response: {click_analysis[:200]}..."
                
        except Exception as e:
            return f"❌ Smart like tool failed: {str(e)}"


def test_smart_like_tool():
    """Test the smart like tool"""
    tool = SmartLikeTool()
    result = tool._run("AI-related post about Phala Cloud")
    print(f"\n🎯 Smart Like Tool Result:\n{result}")

if __name__ == "__main__":
    test_smart_like_tool()
