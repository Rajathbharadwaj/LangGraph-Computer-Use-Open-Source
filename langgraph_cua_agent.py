#!/usr/bin/env python3
"""
LangGraph Agent using Computer Use Agent (CUA) Tools
Demonstrates how to create a LangGraph agent that can control a computer using CUA tools.
"""

import asyncio
import os
from typing import Dict, Any, List, Optional
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langgraph.graph import StateGraph, MessagesState, END, START
from langchain_anthropic import ChatAnthropic
import requests
import json

from dotenv import load_dotenv

load_dotenv()

# Import our complete CUA tools with Anthropic vision
from enhanced_anthropic_cua_tool import create_complete_anthropic_cua_tools
from langchain_cua_tools import cleanup_cua_client
from advanced_like_tool import create_advanced_like_tool
from like_stats_tool import create_like_stats_tool
from omniparser_client import OmniParserClient


class EnhancedState(MessagesState):
    """Enhanced state that includes page context"""
    page_context: Optional[Dict[str, Any]] = None
    dom_elements: Optional[List[Dict[str, Any]]] = None
    omni_analysis: Optional[Dict[str, Any]] = None
    enhanced_ready: bool = False


def gather_enhanced_context(state: EnhancedState) -> Dict[str, Any]:
    """
    Enhanced Context Gathering Node
    Combines OmniParser visual analysis + Playwright DOM data
    """
    print("🔍 Gathering enhanced context (OmniParser + Playwright DOM)...")
    
    try:
        # Step 1: Get comprehensive context from stealth server
        response = requests.get("http://localhost:8000/dom/enhanced_context")
        
        if not response.ok:
            print(f"❌ Failed to get enhanced context: {response.status_code}")
            return {"enhanced_ready": False}
        
        context_data = response.json()
        
        if not context_data.get("success"):
            print(f"❌ Enhanced context failed: {context_data.get('error')}")
            return {"enhanced_ready": False}
        
        # Step 2: Get OmniParser analysis of the screenshot
        screenshot_b64 = context_data["screenshot"]
        if screenshot_b64.startswith("data:image/png;base64,"):
            screenshot_b64 = screenshot_b64.replace("data:image/png;base64,", "")
        
        omni_client = OmniParserClient()
        if omni_client.health_check():
            omni_result = omni_client.parse_screenshot(screenshot_b64)
            omni_elements = omni_client.get_clickable_elements(screenshot_b64) if "error" not in omni_result else []
        else:
            print("⚠️ OmniParser not available, using DOM-only analysis")
            omni_result = {}
            omni_elements = []
        
        # Step 3: Combine the data
        enhanced_context = {
            "page_info": context_data["page_info"],
            "dom_elements": context_data["dom_elements"],
            "dom_element_count": context_data["element_count"],
            "omni_elements": omni_elements,
            "omni_element_count": len(omni_elements),
            "screenshot": context_data["screenshot"],
            "omni_latency": omni_result.get("latency", 0)
        }
        
        # Create context summary for LLM
        context_summary = f"""
🔍 **ENHANCED PAGE CONTEXT READY**

📄 **Page Information:**
- Title: {enhanced_context['page_info']['title']}
- URL: {enhanced_context['page_info']['url']}
- Domain: {enhanced_context['page_info']['domain']}
- Ready State: {enhanced_context['page_info']['readyState']}

📊 **Element Detection:**
- DOM Elements Found: {enhanced_context['dom_element_count']} (from Playwright)
- Visual Elements Found: {enhanced_context['omni_element_count']} (from OmniParser)
- Window Size: {enhanced_context['page_info']['windowWidth']}x{enhanced_context['page_info']['windowHeight']}
- Scroll Position: {enhanced_context['page_info']['scrollTop']}/{enhanced_context['page_info']['scrollHeight']}

🎯 **Available DOM Elements (Playwright):**
{chr(10).join([f"- {elem['tagName']}: '{elem['text'][:50]}...' at ({elem['x']}, {elem['y']})" for elem in enhanced_context['dom_elements'][:10]])}
{f"... and {enhanced_context['dom_element_count'] - 10} more elements" if enhanced_context['dom_element_count'] > 10 else ""}

🔍 **Available Visual Elements (OmniParser):**
{chr(10).join([f"- {elem.get('type', 'element')}: '{elem.get('description', elem.get('text', ''))[:50]}...' at ({elem.get('x')}, {elem.get('y')})" for elem in enhanced_context['omni_elements'][:10]])}
{f"... and {enhanced_context['omni_element_count'] - 10} more elements" if enhanced_context['omni_element_count'] > 10 else ""}

💡 **Context Usage:**
- Use DOM elements for precise programmatic interaction
- Use Visual elements for complex UI patterns OmniParser detected
- Both sources provide exact click coordinates
- Scroll information available for navigation
"""
        
        print("✅ Enhanced context gathered successfully!")
        print(f"📊 Found {enhanced_context['dom_element_count']} DOM + {enhanced_context['omni_element_count']} visual elements")
        
        # Add context summary to messages
        current_messages = state.get("messages", [])
        enhanced_message = HumanMessage(content=context_summary)
        
        return {
            "messages": current_messages + [enhanced_message],
            "page_context": enhanced_context,
            "dom_elements": enhanced_context["dom_elements"],
            "omni_analysis": omni_result,
            "enhanced_ready": True
        }
        
    except Exception as e:
        print(f"❌ Error gathering enhanced context: {e}")
        import traceback
        traceback.print_exc()
        return {"enhanced_ready": False}


def create_enhanced_cua_agent(llm_name: str = "claude"):
    """Create enhanced LangGraph agent with context gathering + tools"""
    
    # Initialize the LLM
    if llm_name == "claude":
        llm = ChatAnthropic(
            model="claude-3-5-sonnet-20240620",
            temperature=0.1
        )
    else:
        llm = ChatOpenAI(
            model="gpt-4o",
            temperature=0.1
        )
    
    # Get all CUA tools
    tools = create_complete_anthropic_cua_tools()
    
    # Add advanced tools
    like_tool = create_advanced_like_tool()
    stats_tool = create_like_stats_tool(like_tool)
    tools.extend([like_tool, stats_tool])
    
    # Create the state graph
    workflow = StateGraph(EnhancedState)
    
    # Add nodes
    workflow.add_node("gather_context", gather_enhanced_context)
    
    # Create the agent node with tools
    agent_node = create_react_agent(llm, tools, prompt=get_enhanced_system_prompt())
    workflow.add_node("agent", agent_node)
    
    # Define the flow
    workflow.add_edge(START, "gather_context")
    workflow.add_edge("gather_context", "agent")
    workflow.add_edge("agent", END)
    
    return workflow.compile()


def get_enhanced_system_prompt() -> str:
    """Get the enhanced system prompt that works with combined context"""
    return """You are an enhanced computer control agent with access to both visual AI analysis and DOM structure data.

🎯 **ENHANCED CAPABILITIES**:
You receive COMPREHENSIVE page context including:
- **Playwright DOM Elements**: Real DOM structure with precise coordinates, IDs, classes, text content
- **OmniParser Visual Elements**: AI-detected visual elements from screenshot analysis  
- **Page Information**: URL, title, scroll position, window dimensions
- **Combined Intelligence**: Cross-reference visual and structural data for maximum accuracy

🔧 **AVAILABLE TOOLS**:
- click_at_coordinates: Click at specific coordinates (use exact coordinates from context)
- type_text: Type text at current cursor position  
- press_keys: Press key combinations (e.g., ['ctrl', 'c'], ['Return'])
- navigate_to_url: Navigate to a URL in browser
- scroll_at_location: Scroll page content using mouse wheel
- advanced_like_post: Multi-platform intelligent liking with auto-detection
- get_like_statistics: Query current session statistics

🚀 **ENHANCED WORKFLOW**:
1. **CONTEXT PROVIDED**: You receive rich page context automatically at start
2. **ANALYZE**: Review both DOM elements and visual elements for best interaction strategy
3. **CHOOSE**: Select most reliable element (DOM when available, visual for complex UI)
4. **ACT**: Use exact coordinates provided in context
5. **VERIFY**: Take action and verify results

⚡ **BEST PRACTICES**:
- **DOM Elements**: Prefer for standard web elements (buttons, inputs, links) - more reliable
- **Visual Elements**: Use for complex UI patterns, icons, or when DOM fails
- **Coordinates**: Always use exact coordinates from context - no guessing
- **Verification**: Check action results, scroll if elements not visible
- **Efficiency**: Don't request new context unless page has changed significantly

🎯 **INTERACTION STRATEGY**:
- **Forms/Inputs**: Use DOM elements with IDs, classes, or clear text content
- **Social Media**: Use visual elements for like buttons, share icons, interaction elements  
- **Navigation**: Use DOM elements for standard navigation, visual for custom UI
- **Complex UI**: Combine both sources - DOM for structure, visual for precise targeting

💡 **CONTEXT INTERPRETATION**:
The page context includes both DOM and visual elements. DOM elements are more reliable for programmatic interaction, while visual elements catch complex UI patterns that DOM might miss. Use both strategically based on the task.

IMPORTANT: Be decisive and efficient. The enhanced context provides everything needed for accurate interaction."""


def create_cua_agent(llm : str = "claude"):
    """Legacy function - redirects to enhanced agent"""
    return create_enhanced_cua_agent(llm)


async def run_cua_agent_task(task: str, config: Optional[Dict[str, Any]] = None):
    """Run a task using the CUA agent"""
    
    if config is None:
        config = {"configurable": {"thread_id": "cua-session-1"}}
    
    # Create the agent
    agent = create_cua_agent(llm="claude")
    
    try:
        print(f"🤖 Starting task: {task}")
        print("=" * 60)
        
        # Set reasonable recursion limit to prevent infinite loops
        config["recursion_limit"] = 100  # Lower limit forces more efficient execution
        response = agent.invoke(
            {"messages": [HumanMessage(content=task)]},
            config
        )
        
        # Print the final response
        final_message = response["messages"][-1]
        print(f"\n✅ Task completed!")
        print(f"Final response: {final_message.content}")
        
        return response
        
    except Exception as e:
        print(f"❌ Error running task: {e}")
        import traceback
        print("Full traceback:")
        traceback.print_exc()
        raise
    finally:
        # Cleanup
        await cleanup_cua_client()


async def run_interactive_session():
    """Run an interactive session with the CUA agent"""
    
    config = {"configurable": {"thread_id": "interactive-session"}, "recursion_limit": 100}
    agent = create_cua_agent(llm="claude")
    
    print("🤖 CUA LangGraph Agent Interactive Session")
    print("Type 'quit' to exit, 'screenshot' for quick screenshot")
    print("=" * 60)
    
    try:
        while True:
            user_input = input("\n👤 You: ").strip()
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("👋 Goodbye!")
                break
                
            if user_input.lower() == 'screenshot':
                print("📸 Taking screenshot and analyzing...")
                from final_anthropic_cua_tool import AnthropicCUAScreenshotTool
                vision_tool = AnthropicCUAScreenshotTool()
                analysis = vision_tool._run("Describe what you see on the current screen")
                print(f"📊 Analysis: {analysis}")
                continue
            
            if not user_input:
                continue
            
            print(f"\n🤖 Agent working on: {user_input}")
            print("-" * 40)
            
            try:
                response = agent.invoke(
                    {"messages": [HumanMessage(content=user_input)]},
                    config
                )
                
                final_message = response["messages"][-1]
                print(f"\n🤖 Agent: {final_message.content}")
                
            except Exception as e:
                print(f"❌ Error: {e}")
                import traceback
                print("Full traceback:")
                traceback.print_exc()
                
    finally:
        await cleanup_cua_client()


# Example tasks
EXAMPLE_TASKS = [
    "Take a screenshot and describe what you see on the screen",
    "Navigate to google.com in the browser",
    "Open a new tab by pressing Ctrl+T",
    "Click on the search box and search for 'langchain'",
    "Scroll down the page to see more results"
]


async def run_example_tasks():
    """Run some example tasks"""
    
    print("🚀 Running Example CUA Agent Tasks")
    print("=" * 50)
    
    for i, task in enumerate(EXAMPLE_TASKS, 1):
        print(f"\n📋 Task {i}: {task}")
        print("-" * 40)
        
        try:
            await run_cua_agent_task(task)
            
            # Wait a bit between tasks
            await asyncio.sleep(2)
            
        except Exception as e:
            print(f"❌ Task {i} failed: {e}")
            import traceback
            print("Full traceback:")
            traceback.print_exc()
            continue


# Export the compiled graph for LangGraph Platform
graph = create_enhanced_cua_agent()


if __name__ == "__main__":
    # Set up OpenAI API key if not already set
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  Please set OPENAI_API_KEY environment variable")
        print("Example: export OPENAI_API_KEY='your-api-key-here'")
        exit(1)
    
    print("Choose an option:")
    print("1. Run example tasks")
    print("2. Interactive session")
    print("3. Single custom task")
    
    choice = input("Enter choice (1-3): ").strip()
    
    if choice == "1":
        asyncio.run(run_example_tasks())
    elif choice == "2":
        asyncio.run(run_interactive_session())
    elif choice == "3":
        task = input("Enter your task: ").strip()
        if task:
            asyncio.run(run_cua_agent_task(task))
    else:
        print("Invalid choice")
