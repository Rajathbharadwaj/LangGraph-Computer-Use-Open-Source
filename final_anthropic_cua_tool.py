#!/usr/bin/env python3
"""
Final Production-Ready LangChain CUA Tool with Anthropic Vision
"""

import requests
import os
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage
from langchain_core.tools import BaseTool
from pydantic import BaseModel

load_dotenv()

class AnthropicScreenshotInput(BaseModel):
    """Input for Anthropic screenshot tool"""
    prompt: str = "Describe what you see in this screenshot"

class AnthropicCUAScreenshotTool(BaseTool):
    """Production-ready CUA screenshot tool with Anthropic Claude vision"""
    
    name: str = "take_screenshot_and_analyze"
    description: str = "Take a screenshot of the current screen and analyze it with Anthropic Claude vision AI"
    args_schema: type[BaseModel] = AnthropicScreenshotInput
    
    def _run(self, prompt: str = "Describe what you see in this screenshot") -> str:
        """Take screenshot and analyze with Anthropic Claude"""
        
        try:
            # Get fresh screenshot from CUA server
            response = requests.get("http://localhost:8001/screenshot", timeout=10)
            result = response.json()
            
            if not result.get("success") or "image" not in result:
                return f"❌ Failed to capture screenshot: {result.get('error', 'Unknown error')}"
            
            # Clean base64 string
            image_str = result["image"]
            if image_str.startswith("data:image/png;base64,"):
                image_str = image_str.replace("data:image/png;base64,", "")
            
            # Initialize Anthropic Claude
            llm = init_chat_model('anthropic:claude-3-5-sonnet-latest')
            
            # Create message with correct Anthropic format
            message = HumanMessage(
                content=[
                    {
                        'type': 'text',
                        'text': prompt,
                    },
                    {
                        'type': 'image',
                        'source': {
                            'type': 'base64',
                            'media_type': 'image/png',
                            'data': image_str,
                        }
                    },
                ],
            )
            
            # Get vision analysis
            response = llm.invoke([message])
            return response.content
            
        except Exception as e:
            return f"❌ Screenshot analysis failed: {str(e)}"
    
    async def _arun(self, prompt: str = "Describe what you see in this screenshot") -> str:
        """Async version"""
        return self._run(prompt)


# Import other CUA tools
from langchain_cua_tools import create_sync_tools

def create_complete_anthropic_cua_tools():
    """Create complete set of CUA tools with Anthropic vision"""
    
    # Get basic CUA tools (click, type, navigate, etc.)
    basic_tools = create_sync_tools()
    
    # Add Anthropic vision tool
    vision_tool = AnthropicCUAScreenshotTool()
    
    # Filter out basic screenshot tools
    filtered_tools = []
    for tool in basic_tools:
        if tool.name not in ["take_screenshot", "take_screenshot_text"]:
            filtered_tools.append(tool)
    
    # Add Anthropic vision tool
    filtered_tools.append(vision_tool)
    
    return filtered_tools


def test_anthropic_cua_integration():
    """Test the complete Anthropic CUA integration"""
    
    print("🎯 Final Anthropic CUA Integration Test")
    print("=" * 50)
    
    # Test individual tool
    vision_tool = AnthropicCUAScreenshotTool()
    
    prompts = [
        "What website or page is currently displayed?",
        "List all clickable buttons and interactive elements you can see.",
        "What is the URL shown in the address bar?",
        "Describe the overall layout and design of this page."
    ]
    
    for i, prompt in enumerate(prompts, 1):
        print(f"\n📋 Test {i}: {prompt}")
        print("-" * 40)
        
        result = vision_tool._run(prompt)
        print(f"🤖 Claude: {result}")
        print()


if __name__ == "__main__":
    print("🚀 Testing Final Anthropic CUA Integration")
    
    # Check if ANTHROPIC_API_KEY is set
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("⚠️  Warning: ANTHROPIC_API_KEY not found in environment")
        print("   Add it to your .env file to use Anthropic Claude vision")
        print()
    
    # Test the integration
    test_anthropic_cua_integration()
    
    print("🎉 Anthropic + LangChain + CUA integration complete!")
    print("✨ Ready for production use with LangGraph agents!")
