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
from langgraph.graph import StateGraph, MessagesState
from langgraph.checkpoint.sqlite import SqliteSaver
from dotenv import load_dotenv

load_dotenv()

# Import our complete CUA tools with Anthropic vision
from final_anthropic_cua_tool import create_complete_anthropic_cua_tools
from langchain_cua_tools import cleanup_cua_client


def create_cua_agent():
    """Create a LangGraph agent with CUA tools"""
    
    # Initialize the LLM (you can use any LangChain-compatible LLM)
    llm = ChatOpenAI(
        model="gpt-4o",  # or "gpt-3.5-turbo", "claude-3-sonnet", etc.
        temperature=0.1
    )
    
    # Get all CUA tools with Anthropic vision
    tools = create_complete_anthropic_cua_tools()
    
    # Create system message for computer control
    system_message = """You are a computer control agent that can interact with a desktop environment through various tools.

Available tools:
- take_screenshot_and_analyze: Take a screenshot and analyze it with Anthropic Claude vision AI
- click_at_coordinates: Click at specific coordinates
- type_text: Type text at current cursor position
- press_keys: Press key combinations (e.g., ['ctrl', 'c'], ['Return'])
- navigate_to_url: Navigate to a URL in browser
- scroll_at_location: SCROLL page content using mouse wheel (NOT move cursor) - use to scroll through feeds, pages, documents

Best practices:
1. Always take a screenshot first to see the current state - the tool will analyze what's on screen
2. Use the vision analysis to understand what elements are available
3. Be precise with click coordinates based on the vision analysis
4. Complete tasks efficiently - don't repeat the same action multiple times
5. If something doesn't work after 2-3 attempts, try a different approach
6. When a task is complete, provide a final summary and stop

IMPORTANT: Be decisive and efficient. Avoid loops by:
- Not taking excessive screenshots of the same content
- Not clicking the same element repeatedly
- Stopping when the task is clearly complete
- Providing a final response when the objective is met

When interacting with the computer:
- The screenshot tool uses Anthropic Claude to analyze what's on screen
- You'll get detailed descriptions of UI elements and their locations
- Coordinates are in pixels from top-left (0,0)
- Always verify actions worked, but don't over-verify
"""
    
    # Create the agent with better configuration
    # Use SqliteSaver for file-based persistence instead of in-memory storage
    memory = SqliteSaver.from_conn_string("checkpoints.sqlite")
    agent = create_react_agent(
        llm,
        tools,
        prompt=system_message,
        checkpointer=memory
    )
    
    return agent


async def run_cua_agent_task(task: str, config: Optional[Dict[str, Any]] = None):
    """Run a task using the CUA agent"""
    
    if config is None:
        config = {"configurable": {"thread_id": "cua-session-1"}}
    
    # Create the agent
    agent = create_cua_agent()
    
    try:
        print(f"🤖 Starting task: {task}")
        print("=" * 60)
        
        # Set reasonable recursion limit to prevent infinite loops
        config["recursion_limit"] = 15  # Lower limit forces more efficient execution
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
    
    config = {"configurable": {"thread_id": "interactive-session"}}
    agent = create_cua_agent()
    
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
