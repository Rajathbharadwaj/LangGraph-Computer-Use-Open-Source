#!/usr/bin/env python3
"""
OmniParser Client for Enhanced GUI Element Detection
Integrates Microsoft OmniParser V2 for precise UI element identification and action grounding.
"""

import base64
import io
import requests
from typing import Dict, List, Any, Tuple, Optional
from PIL import Image
import json


class OmniParserClient:
    """Client for communicating with OmniParser server for GUI element detection"""
    
    def __init__(self, host: str = 'localhost', port: int = 8003):
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
    
    def parse_screenshot(self, base64_image: str) -> Dict[str, Any]:
        """
        Parse a screenshot using OmniParser to detect GUI elements
        
        Args:
            base64_image: Base64 encoded PNG image
            
        Returns:
            Dictionary containing:
            - som_image_base64: Annotated image with element bounding boxes
            - parsed_content_list: List of detected elements with coordinates and descriptions
            - latency: Processing time
        """
        try:
            # Clean base64 string
            if base64_image.startswith("data:image/png;base64,"):
                base64_image = base64_image.replace("data:image/png;base64,", "")
            
            response = requests.post(
                f"{self.base_url}/parse/",
                json={"base64_image": base64_image},
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {
                    "error": f"OmniParser request failed: {response.status_code}",
                    "som_image_base64": "",
                    "parsed_content_list": [],
                    "latency": 0
                }
                
        except Exception as e:
            return {
                "error": f"OmniParser client error: {str(e)}",
                "som_image_base64": "",
                "parsed_content_list": [],
                "latency": 0
            }
    
    def get_clickable_elements(self, base64_image: str, screen_width: int = 1280, screen_height: int = 720) -> List[Dict[str, Any]]:
        """
        Get list of clickable elements from screenshot
        
        Args:
            base64_image: Screenshot to analyze
            screen_width: Screen width in pixels (default 1280)
            screen_height: Screen height in pixels (default 720)
        
        Returns:
            List of elements with coordinates, descriptions, and interactability
        """
        result = self.parse_screenshot(base64_image)
        
        if "error" in result:
            print(f"OmniParser error: {result['error']}")
            return []
        
        elements = []
        for item in result.get("parsed_content_list", []):
            # Handle OmniParser V2 format
            bbox = item.get("bbox", [])
            content = item.get("content", "")
            interactivity = item.get("interactivity", True)
            element_type = item.get("type", "unknown")
            
            # Convert normalized coordinates to pixel coordinates
            pixel_coords = []
            if len(bbox) >= 4:
                # bbox format: [x1, y1, x2, y2] normalized (0-1)
                x1 = int(bbox[0] * screen_width)
                y1 = int(bbox[1] * screen_height)
                x2 = int(bbox[2] * screen_width)
                y2 = int(bbox[3] * screen_height)
                pixel_coords = [x1, y1, x2, y2]
            
            element = {
                "coordinates": pixel_coords,
                "description": content,
                "interactable": interactivity,
                "type": element_type,
                "center_x": 0,
                "center_y": 0
            }
            
            # Calculate center point for clicking
            if len(pixel_coords) >= 4:
                element["center_x"] = int((pixel_coords[0] + pixel_coords[2]) / 2)
                element["center_y"] = int((pixel_coords[1] + pixel_coords[3]) / 2)
            
            elements.append(element)
        
        return elements
    
    def find_element_by_description(self, base64_image: str, target_description: str) -> Optional[Dict[str, Any]]:
        """
        Find a specific element by matching description keywords
        
        Args:
            base64_image: Screenshot to analyze
            target_description: Description to search for (e.g., "login button", "search box")
            
        Returns:
            Element dict with coordinates if found, None otherwise
        """
        elements = self.get_clickable_elements(base64_image)
        
        target_lower = target_description.lower()
        
        for element in elements:
            desc_lower = element["description"].lower()
            
            # Check for keyword matches
            if any(keyword in desc_lower for keyword in target_lower.split()):
                return element
        
        return None
    
    def get_annotated_image(self, base64_image: str) -> str:
        """
        Get the annotated image with bounding boxes around detected elements
        
        Returns:
            Base64 encoded annotated image with bounding boxes
        """
        result = self.parse_screenshot(base64_image)
        # Try the new field first, fall back to som_image_base64
        return result.get("annotated_image_base64", result.get("som_image_base64", ""))
    
    def health_check(self) -> bool:
        """Check if OmniParser server is healthy"""
        try:
            response = requests.get(f"{self.base_url}/probe/", timeout=5)
            return response.status_code == 200
        except:
            return False


def test_omniparser_client():
    """Test the OmniParser client"""
    client = OmniParserClient()
    
    print("Testing OmniParser client...")
    
    # Health check
    if client.health_check():
        print("✅ OmniParser server is healthy")
    else:
        print("❌ OmniParser server is not responding")
        return
    
    # Test with a simple base64 image (you would get this from CUA screenshot)
    print("OmniParser client ready for integration!")


if __name__ == "__main__":
    test_omniparser_client()
