#!/usr/bin/env python3
"""
Advanced Like Tool for Social Media Interactions
Handles liking posts across different platforms with intelligent detection and verification.
"""

import time
import re
from typing import Dict, Any, Optional, Tuple, List
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field
from datetime import datetime
import json

from langchain_cua_tools import SyncCUAClient
from omniparser_client import OmniParserClient
from enhanced_anthropic_cua_tool import EnhancedAnthropicCUATool


class LikeInput(BaseModel):
    """Input for the advanced like tool"""
    target_description: str = Field(
        description="Description of what to like (e.g., 'first post', 'post about AI', 'tweet by @username')"
    )
    platform: str = Field(
        default="auto",
        description="Platform type: 'twitter', 'facebook', 'instagram', 'linkedin', or 'auto' for auto-detection"
    )
    max_scroll_attempts: int = Field(
        default=5,
        description="Maximum number of scroll attempts to find the target"
    )


class AdvancedLikeTool(BaseTool):
    """Advanced tool for liking posts with intelligent detection and platform-specific handling"""
    
    name: str = "advanced_like_post"
    description: str = """
    🚀 ADVANCED LIKE TOOL - Intelligently finds and likes posts on social media platforms.
    
    Features:
    - Multi-platform support (Twitter/X, Facebook, Instagram, LinkedIn)
    - Smart scrolling to find target posts
    - Precise heart/like button detection using OmniParser V2
    - Verification of successful like actions
    - Handles different UI variations and states
    
    Use this when you need to like specific posts or content on social media.
    """
    args_schema: type = LikeInput
    
    def __init__(self):
        super().__init__()
        # Initialize clients as private attributes to avoid Pydantic field conflicts
        object.__setattr__(self, '_cua_client', SyncCUAClient())
        object.__setattr__(self, '_omniparser_client', OmniParserClient())
        object.__setattr__(self, '_enhanced_tool', EnhancedAnthropicCUATool())
        
        # Initialize state tracking
        object.__setattr__(self, '_like_state', {
            'total_likes': 0,
            'liked_posts': [],
            'session_start': datetime.now().isoformat(),
            'platforms_used': set(),
            'users_liked': set()
        })
    
    @property
    def cua_client(self):
        return self._cua_client
    
    @property
    def omniparser_client(self):
        return self._omniparser_client
    
    @property
    def enhanced_tool(self):
        return self._enhanced_tool
    
    def get_like_statistics(self) -> Dict[str, Any]:
        """Get current liking statistics"""
        state = self._like_state.copy()
        state['platforms_used'] = list(state['platforms_used'])
        state['users_liked'] = list(state['users_liked'])
        return state
    
    def _extract_post_info(self, analysis: str, platform: str) -> Dict[str, Any]:
        """Extract post information for state tracking"""
        
        # Extract username/author patterns
        username_patterns = {
            'twitter': [r'@(\w+)', r'by @(\w+)', r'(\w+) tweeted'],
            'facebook': [r'(\w+\s+\w+) posted', r'(\w+) shared'],
            'instagram': [r'@(\w+)', r'(\w+) posted'],
            'linkedin': [r'(\w+\s+\w+) posted', r'(\w+) shared']
        }
        
        patterns = username_patterns.get(platform, username_patterns['twitter'])
        username = None
        
        for pattern in patterns:
            match = re.search(pattern, analysis, re.IGNORECASE)
            if match:
                username = match.group(1).strip()
                break
        
        # Extract post content (first 100 characters)
        post_content = ""
        content_indicators = ["post content:", "tweet:", "says:", "posted:", "content:"]
        
        for indicator in content_indicators:
            if indicator in analysis.lower():
                start_idx = analysis.lower().find(indicator) + len(indicator)
                content_section = analysis[start_idx:start_idx + 200].strip()
                if content_section:
                    post_content = content_section[:100] + "..." if len(content_section) > 100 else content_section
                    break
        
        # If no specific content found, use a portion of the analysis
        if not post_content:
            post_content = analysis[:100] + "..." if len(analysis) > 100 else analysis
        
        return {
            'username': username or 'unknown_user',
            'content': post_content,
            'platform': platform,
            'timestamp': datetime.now().isoformat(),
            'coordinates': None  # Will be filled when like button is found
        }
    
    def _update_like_state(self, post_info: Dict[str, Any], button_coords: Tuple[int, int]) -> None:
        """Update the internal state after a successful like"""
        
        # Update coordinates
        post_info['coordinates'] = {'x': button_coords[0], 'y': button_coords[1]}
        
        # Update state
        self._like_state['total_likes'] += 1
        self._like_state['liked_posts'].append(post_info)
        self._like_state['platforms_used'].add(post_info['platform'])
        if post_info['username'] != 'unknown_user':
            self._like_state['users_liked'].add(post_info['username'])
        
        print(f"📊 STATE UPDATE: Total likes: {self._like_state['total_likes']}")
        print(f"👤 Users liked: {len(self._like_state['users_liked'])}")
        print(f"📱 Platforms: {list(self._like_state['platforms_used'])}")
    
    def _run(self, target_description: str, platform: str = "auto", max_scroll_attempts: int = 5) -> str:
        """Execute the advanced like operation"""
        
        print(f"\n🎯 ADVANCED LIKE: Looking for '{target_description}' on {platform}")
        
        try:
            # Step 1: Analyze current screen and detect platform
            detected_platform = self._detect_platform(platform)
            print(f"📱 Platform: {detected_platform}")
            
            # Step 2: Find the target post and extract post info
            post_location = self._find_target_post(target_description, max_scroll_attempts)
            if not post_location:
                return f"❌ Could not find post matching '{target_description}' after {max_scroll_attempts} scroll attempts"
            
            # Step 3: Extract post information for state tracking
            post_info = self._extract_post_info(post_location.get('analysis', ''), detected_platform)
            print(f"📝 Extracted post info: @{post_info['username']} - {post_info['content'][:50]}...")
            
            # Step 4: Find and click the like button
            like_result = self._find_and_click_like_button(post_location, detected_platform)
            if not like_result["success"]:
                return f"❌ {like_result['message']}"
            
            # Step 5: Verify the like action
            verification = self._verify_like_action(post_location)
            
            if verification["success"]:
                # Step 6: Update state with successful like
                button_coords = (like_result['button_info']['center_x'], like_result['button_info']['center_y'])
                self._update_like_state(post_info, button_coords)
                
                # Generate comprehensive success message
                stats = self.get_like_statistics()
                return (f"✅ Successfully liked post by @{post_info['username']}!\n"
                       f"📊 Session Stats: {stats['total_likes']} total likes, "
                       f"{len(stats['users_liked'])} unique users, "
                       f"platforms: {', '.join(stats['platforms_used'])}\n"
                       f"📝 Content: {post_info['content'][:80]}...")
            else:
                return f"⚠️ Like action may have failed: {verification['message']}"
                
        except Exception as e:
            return f"❌ Error during like operation: {str(e)}"
    
    def _detect_platform(self, platform_hint: str) -> str:
        """Detect the current social media platform"""
        
        if platform_hint != "auto":
            return platform_hint
        
        try:
            # Get current page analysis
            analysis = self.enhanced_tool._run("What social media platform is this? Look for platform-specific UI elements.")
            
            # Platform detection patterns
            platforms = {
                "twitter": ["twitter", "x.com", "tweet", "retweet", "𝕏"],
                "facebook": ["facebook", "facebook.com", "post", "share", "like", "comment"],
                "instagram": ["instagram", "instagram.com", "story", "reel", "explore"],
                "linkedin": ["linkedin", "linkedin.com", "connection", "professional", "network"]
            }
            
            analysis_lower = analysis.lower()
            for platform, keywords in platforms.items():
                if any(keyword in analysis_lower for keyword in keywords):
                    return platform
            
            return "unknown"
            
        except Exception as e:
            print(f"⚠️ Platform detection failed: {e}")
            return "unknown"
    
    def _find_target_post(self, target_description: str, max_attempts: int) -> Optional[Dict[str, Any]]:
        """Find the target post by scrolling and analyzing content"""
        
        print(f"🔍 Searching for post: {target_description}")
        
        for attempt in range(max_attempts):
            print(f"\n📖 Search attempt {attempt + 1}/{max_attempts}")
            
            # Analyze current screen content
            analysis = self.enhanced_tool._run(
                f"Look for a post that matches this description: '{target_description}'. "
                f"Identify the post location and any interaction elements (like/heart buttons) near it. "
                f"Provide specific coordinates if you find the target post."
            )
            
            # Check if we found the target
            if self._is_target_found(analysis, target_description):
                # Extract post location information
                post_info = self._extract_post_location(analysis)
                print(f"🎯 Found target post at area: {post_info}")
                return post_info
            
            # Scroll down to see more content
            if attempt < max_attempts - 1:
                print("📜 Scrolling to find more posts...")
                scroll_result = self.cua_client._request("POST", "/scroll", {
                    "x": 640, "y": 400, "scroll_x": 0, "scroll_y": 3
                })
                
                if scroll_result.get("success"):
                    time.sleep(1.5)  # Wait for content to load
                else:
                    print(f"⚠️ Scroll failed: {scroll_result}")
        
        return None
    
    def _is_target_found(self, analysis: str, target_description: str) -> bool:
        """Check if the target post was found in the analysis"""
        
        # Look for positive indicators in the analysis
        positive_indicators = [
            "found", "located", "identified", "matches", "target post",
            "post that", "corresponds to", "fits the description"
        ]
        
        # Look for the target description elements
        target_keywords = target_description.lower().split()
        
        analysis_lower = analysis.lower()
        
        # Check for positive indicators
        has_positive = any(indicator in analysis_lower for indicator in positive_indicators)
        
        # Check for target keywords
        keyword_matches = sum(1 for keyword in target_keywords if keyword in analysis_lower)
        has_keywords = keyword_matches >= len(target_keywords) * 0.6  # 60% of keywords must match
        
        # Look for coordinate indicators
        has_coordinates = bool(re.search(r'\d+,\s*\d+', analysis))
        
        return has_positive and (has_keywords or has_coordinates)
    
    def _extract_post_location(self, analysis: str) -> Dict[str, Any]:
        """Extract post location information from analysis"""
        
        # Extract coordinates if mentioned
        coord_pattern = r'\((\d+),\s*(\d+)\)'
        coord_matches = re.findall(coord_pattern, analysis)
        
        # Extract area descriptions
        area_pattern = r'(top|middle|bottom|left|right|center)'
        area_matches = re.findall(area_pattern, analysis.lower())
        
        location_info = {
            "coordinates": coord_matches,
            "areas": area_matches,
            "analysis": analysis[:200] + "..." if len(analysis) > 200 else analysis
        }
        
        return location_info
    
    def _find_and_click_like_button(self, post_location: Dict[str, Any], platform: str) -> Dict[str, Any]:
        """Find and click the like button near the target post"""
        
        print("👆 Looking for like button...")
        
        # Get current screen elements with OmniParser
        try:
            screenshot_result = self.cua_client._request("GET", "/screenshot")
            if not screenshot_result.get("success"):
                return {"success": False, "message": "Could not take screenshot"}
            
            # Parse with OmniParser
            base64_image = screenshot_result["image"]
            if base64_image.startswith("data:image/png;base64,"):
                base64_image = base64_image.replace("data:image/png;base64,", "")
            
            parsed = self.omniparser_client.parse_screenshot(base64_image)
            elements = self.omniparser_client.get_clickable_elements(parsed, 1280, 720)
            
            # Find like button candidates
            like_candidates = self._find_like_button_candidates(elements, platform)
            
            if not like_candidates:
                return {"success": False, "message": "No like buttons found on screen"}
            
            # Try clicking the best candidate
            best_candidate = self._select_best_like_candidate(like_candidates, post_location)
            
            if not best_candidate:
                return {"success": False, "message": "Could not determine best like button to click"}
            
            # Click the like button
            click_result = self.cua_client._request("POST", "/click", {
                "x": best_candidate["center_x"],
                "y": best_candidate["center_y"],
                "button": "left"
            })
            
            if click_result.get("success"):
                time.sleep(1)  # Wait for UI update
                return {
                    "success": True, 
                    "message": f"Clicked like button at ({best_candidate['center_x']}, {best_candidate['center_y']})",
                    "button_info": best_candidate
                }
            else:
                return {"success": False, "message": f"Click failed: {click_result}"}
                
        except Exception as e:
            return {"success": False, "message": f"Error finding like button: {str(e)}"}
    
    def _find_like_button_candidates(self, elements: List[Dict], platform: str) -> List[Dict]:
        """Find potential like button elements"""
        
        # Platform-specific like button patterns
        like_patterns = {
            "twitter": ["heart", "like", "♥", "❤️", "🤍"],
            "facebook": ["like", "👍", "reaction"],
            "instagram": ["heart", "like", "♥", "❤️"],
            "linkedin": ["like", "👍", "reaction"],
            "unknown": ["heart", "like", "♥", "❤️", "👍", "reaction"]
        }
        
        patterns = like_patterns.get(platform, like_patterns["unknown"])
        candidates = []
        
        for element in elements:
            if not element.get("interactable", True):
                continue
            
            desc = element.get("description", "").lower()
            
            # Check for like button indicators
            if any(pattern in desc for pattern in patterns):
                candidates.append(element)
                continue
            
            # Check for typical interaction area (buttons without text)
            center_y = element.get("center_y", 0)
            if 200 <= center_y <= 600:  # Typical post interaction area
                # Look for small clickable elements that could be like buttons
                if not desc or len(desc) < 10:
                    candidates.append(element)
        
        return candidates
    
    def _select_best_like_candidate(self, candidates: List[Dict], post_location: Dict[str, Any]) -> Optional[Dict]:
        """Select the best like button candidate based on post location"""
        
        if not candidates:
            return None
        
        # If we have coordinate information from post location, use proximity
        if post_location.get("coordinates"):
            # Find candidate closest to post coordinates
            post_coords = post_location["coordinates"][0]  # Use first coordinate pair
            post_x, post_y = int(post_coords[0]), int(post_coords[1])
            
            best_candidate = None
            min_distance = float('inf')
            
            for candidate in candidates:
                x, y = candidate["center_x"], candidate["center_y"]
                distance = ((x - post_x) ** 2 + (y - post_y) ** 2) ** 0.5
                
                if distance < min_distance:
                    min_distance = distance
                    best_candidate = candidate
            
            return best_candidate
        
        # Otherwise, prefer candidates with explicit like indicators
        explicit_likes = [c for c in candidates if any(
            keyword in c.get("description", "").lower() 
            for keyword in ["heart", "like", "♥", "❤️"]
        )]
        
        if explicit_likes:
            return explicit_likes[0]
        
        # Fallback to first candidate
        return candidates[0]
    
    def _verify_like_action(self, post_location: Dict[str, Any]) -> Dict[str, Any]:
        """Verify that the like action was successful"""
        
        print("✅ Verifying like action...")
        
        try:
            # Wait a moment for UI to update
            time.sleep(1)
            
            # Take another screenshot and analyze
            verification_analysis = self.enhanced_tool._run(
                "Check if there are any liked/favorited posts visible. "
                "Look for filled hearts, 'liked' text, or other indicators that a like action was successful. "
                "Also check for any like counts that may have increased."
            )
            
            # Look for success indicators
            success_indicators = [
                "liked", "favorited", "filled heart", "red heart", "increased",
                "successful", "active", "selected", "highlighted"
            ]
            
            analysis_lower = verification_analysis.lower()
            success_found = any(indicator in analysis_lower for indicator in success_indicators)
            
            if success_found:
                return {
                    "success": True,
                    "details": "Like action appears successful based on UI changes",
                    "analysis": verification_analysis[:150] + "..."
                }
            else:
                return {
                    "success": False,
                    "message": "No clear indication of successful like action",
                    "analysis": verification_analysis[:150] + "..."
                }
                
        except Exception as e:
            return {
                "success": False,
                "message": f"Verification failed: {str(e)}"
            }


# Create the tool instance
def create_advanced_like_tool():
    """Create and return the advanced like tool"""
    return AdvancedLikeTool()


if __name__ == "__main__":
    # Test the tool
    tool = AdvancedLikeTool()
    result = tool._run("first post visible", "auto", 3)
    print(f"\n🎯 Result: {result}")
