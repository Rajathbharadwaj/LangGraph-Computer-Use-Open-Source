#!/usr/bin/env python3
"""
LangGraph Agent with Playwright CUA Tools
Enhanced computer use agent powered by Playwright stealth browser.
"""

import asyncio
from typing import Annotated, List, Dict, Any, TypedDict
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
import base64
from io import BytesIO
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langchain_core.messages import ToolMessage

# Import our new async Playwright tools
from async_playwright_tools import get_async_playwright_tools

def ensure_message_format(messages: List[Any]) -> List[BaseMessage]:
    """Ensure all messages are properly formatted as LangChain messages"""
    formatted_messages = []
    
    for msg in messages:
        if isinstance(msg, BaseMessage):
            # Already a proper message
            formatted_messages.append(msg)
        elif isinstance(msg, dict):
            # Handle dictionary inputs from LangGraph interface
            if 'role' in msg and 'content' in msg:
                # Standard message format
                if msg['role'] == 'user' or msg['role'] == 'human':
                    formatted_messages.append(HumanMessage(content=msg['content']))
                elif msg['role'] == 'assistant' or msg['role'] == 'ai':
                    formatted_messages.append(AIMessage(content=msg['content']))
                elif msg['role'] == 'system':
                    formatted_messages.append(SystemMessage(content=msg['content']))
            else:
                # Non-standard dict format - convert to string content
                content = str(msg)
                formatted_messages.append(HumanMessage(content=content))
        elif isinstance(msg, str):
            # String input
            formatted_messages.append(HumanMessage(content=msg))
        else:
            # Other types - convert to string
            formatted_messages.append(HumanMessage(content=str(msg)))
    
    return formatted_messages


class AgentState(TypedDict):
    """State for the Playwright CUA agent"""
    messages: Annotated[List[Any], add_messages]
    enhanced_context: Dict[str, Any]
    current_url: str
    task_complete: bool


class PlaywrightCUAAgent:
    """LangGraph agent with enhanced Playwright browser automation"""
    
    def __init__(self, model_name: str = "claude-sonnet-4-5"):  # Use Claude-3.5-Sonnet for excellent tool usage
        self.model = ChatAnthropic(model=model_name, temperature=0)
        self.tools = get_async_playwright_tools()
        self.model_with_tools = self.model.bind_tools(self.tools)
        
        # Create the graph
        self.graph = self._create_graph()
    
    def _create_graph(self) -> StateGraph:
        """Create the LangGraph workflow"""
        
        # Define the graph
        workflow = StateGraph(AgentState)
        
        # Add nodes
        workflow.add_node("validate_messages", self._validate_messages)
        workflow.add_node("enhanced_context", self._get_enhanced_context)
        workflow.add_node("agent", self._call_model)
        workflow.add_node("tools", self._execute_tools)
        
        # Add edges
        workflow.add_edge(START, "validate_messages")
        workflow.add_edge("validate_messages", "enhanced_context")
        workflow.add_edge("enhanced_context", "agent")
        workflow.add_conditional_edges(
            "agent",
            self._should_continue,
            {"continue": "tools", "end": END}
        )
        workflow.add_edge("tools", "agent")
        
        return workflow.compile()
    
    async def _validate_messages(self, state: AgentState) -> AgentState:
        """Validate and format all messages to ensure proper LangChain message format"""
        try:
            # Get current messages
            current_messages = state.get("messages", [])
            
            # Ensure they're properly formatted
            validated_messages = ensure_message_format(current_messages)
            
            return {
                **state,
                "messages": validated_messages
            }
        except Exception as e:
            print(f"Error validating messages: {e}")
            # If validation fails, create a default message
            return {
                **state,
                "messages": [HumanMessage(content="Please help me with computer automation tasks.")]
            }
    
    async def _get_enhanced_context(self, state: AgentState) -> AgentState:
        """Get comprehensive context with visual screenshot for multimodal LLM"""
        try:
            print("🔍 Getting comprehensive context with visual screenshot for user query...")
            
            # Get both text analysis and actual screenshot
            comprehensive_tool = next(t for t in self.tools if t.name == "get_comprehensive_context")
            screenshot_tool = next(t for t in self.tools if t.name == "take_browser_screenshot")
            
            # Get comprehensive text analysis
            comprehensive_result = await comprehensive_tool.arun({})
            
            # Get actual screenshot for vision model
            screenshot_result = await screenshot_tool.arun({})
            
            # Also get the raw screenshot data for multimodal input
            from async_playwright_tools import _global_client
            raw_screenshot = await _global_client._request("GET", "/screenshot")
            screenshot_b64 = ""
            if raw_screenshot.get("success") and "image" in raw_screenshot:
                screenshot_b64 = raw_screenshot["image"]
                if screenshot_b64.startswith("data:image/png;base64,"):
                    screenshot_b64 = screenshot_b64.replace("data:image/png;base64,", "")
            
            print("✅ Comprehensive context + visual screenshot gathered - ready for multimodal LLM")
            
            enhanced_context = {
                "comprehensive_analysis": comprehensive_result,
                "screenshot_base64": screenshot_b64,
                "has_visual_screenshot": bool(screenshot_b64),
                "context_type": "multimodal_comprehensive",
                "includes": [
                    "visual_screenshot",
                    "omniparser_visual_analysis", 
                    "playwright_dom_elements", 
                    "page_text_content"
                ],
                "timestamp": "current"
            }
            
            return {
                **state,
                "enhanced_context": enhanced_context
            }
        except Exception as e:
            print(f"Error getting comprehensive context: {e}")
            # Fallback to basic context if comprehensive fails
            try:
                print("🔄 Falling back to basic context...")
                context_tool = next(t for t in self.tools if t.name == "get_enhanced_context")
                fallback_result = await context_tool.arun({})
                
                return {
                    **state,
                    "enhanced_context": {
                        "fallback_analysis": fallback_result,
                        "context_type": "fallback_basic",
                        "error": f"Comprehensive context failed: {str(e)}"
                    }
                }
            except Exception as fallback_error:
                return {
                    **state,
                    "enhanced_context": {"error": f"All context methods failed: {str(e)}, {str(fallback_error)}"}
                }
    
    async def _call_model(self, state: AgentState) -> AgentState:
        """Call the multimodal LLM with enhanced context and visual screenshot"""
        
        # Prepare the system message with enhanced context
        enhanced_context = state.get("enhanced_context", {})
        
        system_prompt = f"""You are a FULLY CAPABLE computer use agent with Playwright browser automation and VISION abilities.

🔍 CURRENT PAGE ANALYSIS:
{enhanced_context.get('comprehensive_analysis', enhanced_context.get('fallback_analysis', 'No context available'))}

CONTEXT TYPE: {enhanced_context.get('context_type', 'unknown')}
INCLUDES: {', '.join(enhanced_context.get('includes', ['basic_context']))}

🎯 CRITICAL: You can see the actual screenshot AND you have FULL INTERACTION CAPABILITIES.

🚀 YOUR POWERFUL TOOLS - USE THEM CONFIDENTLY:
- take_browser_screenshot: Capture current browser screen
- navigate_to_url: Navigate to any URL  
- click_at_coordinates: CLICK ANYWHERE on screen - buttons, links, posts, likes, etc.
- click_element_by_selector: CLICK using CSS selectors (preferred for reliability)
- type_text: TYPE any text into input fields
- press_key_combination: Use keyboard shortcuts (Ctrl+C, etc.)
- scroll_page: SCROLL to see more content
- get_dom_elements: Get clickable elements with coordinates
- find_form_fields: Find login forms, input fields, buttons
- fill_input_field: FILL any input field with text
- 🔐 enter_username: SMART USERNAME entry - auto-finds and fills username/email fields
- 🔐 enter_password: SMART PASSWORD entry - auto-finds and fills password fields
- check_login_success: Verify login status
- like_post: 👍 LIKE any post by keywords (e.g., "OCR model", "AI", "LangChain")
- unlike_post: 💔 UNLIKE any post by keywords
- comment_on_post: 💬 COMMENT on any post
- delete_own_comment: 🗑️ DELETE your own comments
- like_specific_post_by_keywords: 👍 LIKE posts using flexible keyword search

🎯 INTERACTION EXAMPLES - DO THESE CONFIDENTLY:
✅ Login forms: Use enter_username("rajath_db") then enter_password("mypass123")
✅ Like posts: Use like_post("OCR model") or like_specific_post_by_keywords("AI") 
✅ Click links: Navigate by clicking any link  
✅ Fill forms: Use specialized tools (enter_username/enter_password) or type_text
✅ Social actions: Like, share, comment, follow
✅ Navigate: Click menus, tabs, buttons
✅ Scroll & explore: Move around the page

MANDATORY INSTRUCTIONS:
1. 👁️ ANALYZE the visual screenshot to see exactly what's on screen
2. 🎯 IDENTIFY specific elements (posts, buttons, links) you can interact with
3. 🤖 TAKE ACTION when users request interactions - don't hesitate!
4. ❤️ FOR LIKING POSTS: Use like_post() or like_specific_post_by_keywords() tools!
5. 💬 DESCRIBE what you see and what you're doing
6. ⚡ BE PROACTIVE - if user asks to like something, DO IT immediately

🚨 CRITICAL: ALWAYS USE TOOLS FOR ACTIONS - NEVER JUST SAY YOU DID SOMETHING!
❌ WRONG: "I've scrolled down" (just text response)
✅ CORRECT: Actually call scroll_page() tool then say "I've scrolled down"
❌ WRONG: "I've clicked the button" (just text response)  
✅ CORRECT: Actually call click_button_by_text() then say "I've clicked the button"

REMEMBER: If user asks for an action, you MUST use the appropriate tool!

🚀 LIKE POST EXAMPLES:
- User: "like that AI post" → like_post("AI") or like_specific_post_by_keywords("OCR model")
- User: "like the OCR post" → like_post("OCR") 
- User: "like that LangChain post" → like_post("LangChain")

🔍 CRITICAL: TEXT CONTENT vs VISUAL CONTENT
When using like_post() or unlike_post(), ONLY use text that appears in the HTML post content, NOT text you see in images!

EXAMPLE ISSUE:
❌ WRONG: If you see "Vectorless PDF Chatbot" in an image, don't use like_post("Vectorless PDF Chatbot")
✅ CORRECT: Use the actual post text like like_post("PDF chatbot") or like_post("tom_doerr")

HOW TO CHOOSE SEARCH TERMS:
1. 🎯 Use AUTHOR NAMES (most reliable): like_post("tom_doerr"), like_post("akshay")  
2. 📝 Use SHORT PHRASES from post text: like_post("PDF chatbot"), like_post("OCR model")
3. 🏢 Use COMPANY/BRAND names: like_post("LangChain"), like_post("OpenAI")
4. ❌ AVOID long phrases or text you only see in images

REMEMBER: The tools search HTML text content, not image text content!

You are NOT just an observer - you are a FULL BROWSER AUTOMATION AGENT. Act with confidence!"""

        messages = [SystemMessage(content=system_prompt)]
        
        # Add user messages
        messages.extend(state["messages"])
        
        # Add screenshot to the last user message if available
        screenshot_b64 = enhanced_context.get("screenshot_base64")
        if screenshot_b64 and enhanced_context.get("has_visual_screenshot"):
            # Create a multimodal message with both text and image
            last_user_message = state["messages"][-1]
            if isinstance(last_user_message, HumanMessage):
                # Create multimodal content
                multimodal_content = [
                    {"type": "text", "text": last_user_message.content},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{screenshot_b64}",
                            "detail": "high"
                        }
                    }
                ]
                
                # Replace the last message with multimodal version
                messages[-1] = HumanMessage(content=multimodal_content)
                print("🖼️ Added visual screenshot to LLM input")
        
        response = await self.model_with_tools.ainvoke(messages)
        
        # Properly append the response to existing messages
        return {**state, "messages": state["messages"] + [response]}
    
    async def _execute_tools(self, state: AgentState) -> AgentState:
        """Execute tools and ensure proper message formatting"""
        last_message = state["messages"][-1]
        
        if not hasattr(last_message, 'tool_calls') or not last_message.tool_calls:
            return state
        
        tool_messages = []
        
        for tool_call in last_message.tool_calls:
            try:
                # Find the tool by name
                tool = next((t for t in self.tools if t.name == tool_call["name"]), None)
                if tool is None:
                    result = f"Error: Tool {tool_call['name']} not found"
                else:
                    # Execute the tool (async)
                    result = await tool.arun(tool_call["args"])
                
                # Create a proper ToolMessage
                tool_message = ToolMessage(
                    content=str(result),
                    tool_call_id=tool_call["id"]
                )
                tool_messages.append(tool_message)
                
            except Exception as e:
                # Create error message
                error_message = ToolMessage(
                    content=f"Error executing {tool_call['name']}: {str(e)}",
                    tool_call_id=tool_call["id"]
                )
                tool_messages.append(error_message)
        
        # Append tool messages to the conversation
        return {**state, "messages": state["messages"] + tool_messages}
    
    def _should_continue(self, state: AgentState) -> str:
        """Decide whether to continue with tools or end"""
        last_message = state["messages"][-1]
        
        # If the last message has tool calls, continue to tools
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            return "continue"
        else:
            return "end"
    
    async def run_task(self, task: str) -> Dict[str, Any]:
        """Run a specific task using the Playwright agent"""
        try:
            initial_state = {
                "messages": [HumanMessage(content=task)],
                "enhanced_context": {},
                "current_url": "",
                "task_complete": False
            }
            
            # Run the graph
            result = await self.graph.ainvoke(initial_state)
            
            return {
                "success": True,
                "final_message": result["messages"][-1].content,
                "enhanced_context": result.get("enhanced_context", {}),
                "message_count": len(result["messages"])
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": f"Task failed: {task}"
            }


# Graph factory function for LangGraph
def create_playwright_agent_graph():
    """Create and return the Playwright CUA agent graph for LangGraph deployment"""
    agent = PlaywrightCUAAgent()
    return agent.graph

# Convenience function for simple usage
async def run_playwright_agent_task(task: str) -> Dict[str, Any]:
    """Simple function to run a Playwright CUA agent task"""
    agent = PlaywrightCUAAgent()
    return await agent.run_task(task)


if __name__ == "__main__":
    async def demo():
        """Demo the Playwright CUA agent"""
        print("🚀 Starting Playwright CUA Agent Demo...")
        
        tasks = [
            "Take a screenshot and describe what's currently visible on the page",
            "Find and click on the 'Sign in' button or link", 
            "Tell me about the interactive elements available on this page"
        ]
        
        for i, task in enumerate(tasks, 1):
            print(f"\n📋 Task {i}: {task}")
            print("-" * 60)
            
            result = await run_playwright_agent_task(task)
            
            if result.get("success"):
                print(f"✅ Result: {result['final_message']}")
            else:
                print(f"❌ Error: {result.get('error', 'Unknown error')}")
            
            # Small delay between tasks
            await asyncio.sleep(2)
        
        print("\n🎉 Demo complete!")
    
    asyncio.run(demo())
