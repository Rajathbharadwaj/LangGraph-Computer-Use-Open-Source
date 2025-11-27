#!/usr/bin/env python3
"""
Supervisor-Agent Architecture for Playwright CUA
A supervisor that breaks down complex queries into atomic actions for the Playwright agent.
"""

import asyncio
from typing import Annotated, List, Dict, Any, TypedDict, Literal
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

# Import our async Playwright tools
from async_playwright_tools import get_async_playwright_tools


class AtomicAction(BaseModel):
    """Represents a single atomic action that the agent can perform"""
    action_type: Literal["navigate", "click", "type", "scroll", "screenshot", "analyze_page", "wait"]
    description: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    expected_outcome: str


class TaskPlan(BaseModel):
    """Represents a plan of atomic actions to complete a task"""
    task_description: str
    atomic_actions: List[AtomicAction]
    success_criteria: str


class SupervisorState(TypedDict):
    """State for the supervisor-agent system"""
    messages: Annotated[List[Any], add_messages]
    original_query: str
    task_plan: TaskPlan
    current_action_index: int
    completed_actions: List[Dict[str, Any]]
    page_context: Dict[str, Any]
    task_complete: bool
    final_result: str


def ensure_message_format(messages: List[Any]) -> List[BaseMessage]:
    """Ensure all messages are properly formatted as LangChain messages"""
    formatted_messages = []
    
    for msg in messages:
        if isinstance(msg, BaseMessage):
            formatted_messages.append(msg)
        elif isinstance(msg, dict):
            if 'role' in msg and 'content' in msg:
                if msg['role'] == 'user' or msg['role'] == 'human':
                    formatted_messages.append(HumanMessage(content=msg['content']))
                elif msg['role'] == 'assistant' or msg['role'] == 'ai':
                    formatted_messages.append(AIMessage(content=msg['content']))
                elif msg['role'] == 'system':
                    formatted_messages.append(SystemMessage(content=msg['content']))
            else:
                content = str(msg)
                formatted_messages.append(HumanMessage(content=content))
        elif isinstance(msg, str):
            formatted_messages.append(HumanMessage(content=msg))
        else:
            formatted_messages.append(HumanMessage(content=str(msg)))
    
    return formatted_messages


class SupervisorPlaywrightAgent:
    """Supervisor-agent system with task planning and atomic action execution"""
    
    def __init__(self, model_name: str = "gpt-4o-mini"):
        self.model = ChatOpenAI(model=model_name, temperature=0)
        self.tools = get_async_playwright_tools()
        
        # Create the supervisor graph
        self.graph = self._create_graph()
    
    def _create_graph(self) -> StateGraph:
        """Create the supervisor-agent workflow"""
        
        workflow = StateGraph(SupervisorState)
        
        # Add nodes
        workflow.add_node("validate_messages", self._validate_messages)
        workflow.add_node("plan_task", self._plan_task)
        workflow.add_node("get_page_context", self._get_page_context)
        workflow.add_node("execute_action", self._execute_action)
        workflow.add_node("evaluate_progress", self._evaluate_progress)
        workflow.add_node("finalize_result", self._finalize_result)
        
        # Add edges
        workflow.add_edge(START, "validate_messages")
        workflow.add_edge("validate_messages", "plan_task")
        workflow.add_edge("plan_task", "get_page_context")
        workflow.add_edge("get_page_context", "execute_action")
        workflow.add_edge("execute_action", "evaluate_progress")
        
        # Conditional routing from evaluate_progress
        workflow.add_conditional_edges(
            "evaluate_progress",
            self._should_continue_execution,
            {
                "continue": "get_page_context",  # Get fresh context before next action
                "complete": "finalize_result",
                "end": END
            }
        )
        workflow.add_edge("finalize_result", END)
        
        return workflow.compile()
    
    async def _validate_messages(self, state: SupervisorState) -> SupervisorState:
        """Validate and format all messages"""
        try:
            current_messages = state.get("messages", [])
            validated_messages = ensure_message_format(current_messages)
            
            # Extract the original query from the first user message
            original_query = ""
            for msg in validated_messages:
                if isinstance(msg, HumanMessage):
                    original_query = msg.content
                    break
            
            return {
                **state,
                "messages": validated_messages,
                "original_query": original_query,
                "current_action_index": 0,
                "completed_actions": [],
                "page_context": {},
                "task_complete": False,
                "final_result": ""
            }
        except Exception as e:
            print(f"Error validating messages: {e}")
            return {
                **state,
                "messages": [HumanMessage(content="Please help me with computer automation tasks.")],
                "original_query": "Help with automation",
                "current_action_index": 0,
                "completed_actions": [],
                "page_context": {},
                "task_complete": False,
                "final_result": ""
            }
    
    async def _plan_task(self, state: SupervisorState) -> SupervisorState:
        """Break down the user query into atomic actions"""
        try:
            planning_prompt = f"""You are a task planning supervisor for web automation. Break down the user's request into atomic actions.

USER REQUEST: {state['original_query']}

Create a detailed plan with atomic actions. Each action should be:
1. Specific and executable by a browser automation agent
2. Have clear parameters and expected outcomes
3. Be ordered logically

Available action types:
- navigate: Go to a URL
- analyze_page: Get current page context and elements
- click: Click at coordinates or on elements
- type: Type text into input fields
- scroll: Scroll the page
- screenshot: Take a screenshot
- wait: Wait for elements or conditions

Output format:
Task Description: [brief description]
Actions:
1. [action_type]: [description] - Parameters: {{key: value}} - Expected: [outcome]
2. [action_type]: [description] - Parameters: {{key: value}} - Expected: [outcome]
...
Success Criteria: [how to know the task is complete]

Example for "login to X with username test@email.com and password secret123":
Task Description: Login to X.com with provided credentials
Actions:
1. navigate: Go to X.com login page - Parameters: {{"url": "https://x.com"}} - Expected: Login page loads
2. analyze_page: Get current page elements - Parameters: {{}} - Expected: Find username/password fields
3. click: Click on username field - Parameters: {{"element_type": "input", "field_type": "username"}} - Expected: Username field focused
4. type: Enter username - Parameters: {{"text": "test@email.com"}} - Expected: Username appears in field
5. click: Click on password field - Parameters: {{"element_type": "input", "field_type": "password"}} - Expected: Password field focused
6. type: Enter password - Parameters: {{"text": "secret123"}} - Expected: Password appears as dots
7. click: Click login button - Parameters: {{"element_type": "button", "text": "log in"}} - Expected: Attempt login
8. analyze_page: Check if login successful - Parameters: {{}} - Expected: Either logged in or error message
Success Criteria: Successfully logged into X.com account or identified login error

Now plan for: {state['original_query']}"""

            system_message = SystemMessage(content=planning_prompt)
            user_message = HumanMessage(content=f"Plan this task: {state['original_query']}")
            
            response = await self.model.ainvoke([system_message, user_message])
            
            # Parse the response into a TaskPlan (simplified parsing)
            plan_text = response.content
            
            # For now, create a basic plan structure
            # In production, you'd want more sophisticated parsing
            task_plan = TaskPlan(
                task_description=state['original_query'],
                atomic_actions=[
                    AtomicAction(
                        action_type="analyze_page",
                        description="Get current page context",
                        parameters={},
                        expected_outcome="Current page elements and context"
                    )
                ],
                success_criteria="Task execution planned"
            )
            
            # Try to extract actions from the response
            lines = plan_text.split('\n')
            actions = []
            
            for line in lines:
                line = line.strip()
                if line.startswith(('1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.')):
                    # Simple parsing - in production you'd want more robust parsing
                    if 'navigate:' in line:
                        actions.append(AtomicAction(
                            action_type="navigate",
                            description=line,
                            parameters={"url": "https://x.com"},
                            expected_outcome="Page loaded"
                        ))
                    elif 'analyze_page:' in line or 'analyze' in line.lower():
                        actions.append(AtomicAction(
                            action_type="analyze_page",
                            description=line,
                            parameters={},
                            expected_outcome="Page context obtained"
                        ))
                    elif 'click:' in line:
                        actions.append(AtomicAction(
                            action_type="click",
                            description=line,
                            parameters={},
                            expected_outcome="Element clicked"
                        ))
                    elif 'type:' in line:
                        actions.append(AtomicAction(
                            action_type="type",
                            description=line,
                            parameters={},
                            expected_outcome="Text entered"
                        ))
                    elif 'screenshot:' in line:
                        actions.append(AtomicAction(
                            action_type="screenshot",
                            description=line,
                            parameters={},
                            expected_outcome="Screenshot taken"
                        ))
            
            if actions:
                task_plan.atomic_actions = actions
            
            return {
                **state,
                "task_plan": task_plan,
                "messages": state["messages"] + [response]
            }
            
        except Exception as e:
            print(f"Error planning task: {e}")
            # Default plan
            default_plan = TaskPlan(
                task_description=state['original_query'],
                atomic_actions=[
                    AtomicAction(
                        action_type="analyze_page",
                        description="Get current page context",
                        parameters={},
                        expected_outcome="Current page elements"
                    ),
                    AtomicAction(
                        action_type="screenshot",
                        description="Take screenshot",
                        parameters={},
                        expected_outcome="Visual confirmation"
                    )
                ],
                success_criteria="Basic task analysis complete"
            )
            return {
                **state,
                "task_plan": default_plan
            }
    
    async def _get_page_context(self, state: SupervisorState) -> SupervisorState:
        """Get current page context before executing actions"""
        try:
            # Get enhanced context
            context_tool = next(t for t in self.tools if t.name == "get_enhanced_context")
            context_result = await context_tool.arun({})
            
            # Get DOM elements
            dom_tool = next(t for t in self.tools if t.name == "get_dom_elements")
            dom_result = await dom_tool.arun({})
            
            # Get page info
            page_tool = next(t for t in self.tools if t.name == "get_page_info")
            page_result = await page_tool.arun({})
            
            page_context = {
                "enhanced_context": context_result,
                "dom_elements": dom_result,
                "page_info": page_result,
                "timestamp": "current"
            }
            
            return {
                **state,
                "page_context": page_context
            }
        except Exception as e:
            print(f"Error getting page context: {e}")
            return {
                **state,
                "page_context": {"error": str(e)}
            }
    
    async def _execute_action(self, state: SupervisorState) -> SupervisorState:
        """Execute the current atomic action"""
        try:
            current_index = state.get("current_action_index", 0)
            actions = state["task_plan"].atomic_actions
            
            if current_index >= len(actions):
                return {
                    **state,
                    "task_complete": True
                }
            
            current_action = actions[current_index]
            
            # Execute based on action type
            result = ""
            
            if current_action.action_type == "navigate":
                url = current_action.parameters.get("url", "https://x.com")
                nav_tool = next(t for t in self.tools if t.name == "navigate_to_url")
                result = await nav_tool.arun({"url": url})
                
            elif current_action.action_type == "screenshot":
                screenshot_tool = next(t for t in self.tools if t.name == "take_browser_screenshot")
                result = await screenshot_tool.arun({})
                
            elif current_action.action_type == "analyze_page":
                result = f"Page analysis: {state['page_context'].get('enhanced_context', 'No context')}"
                
            elif current_action.action_type == "click":
                # For now, we'll need to parse coordinates from page context
                # This would be enhanced with better element selection
                click_tool = next(t for t in self.tools if t.name == "click_at_coordinates")
                # Default click coordinates - in production, parse from DOM
                result = await click_tool.arun({"x": 640, "y": 400})
                
            elif current_action.action_type == "type":
                text = current_action.parameters.get("text", "")
                type_tool = next(t for t in self.tools if t.name == "type_text")
                result = await type_tool.arun({"text": text})
                
            elif current_action.action_type == "scroll":
                scroll_tool = next(t for t in self.tools if t.name == "scroll_page")
                result = await scroll_tool.arun({"x": 640, "y": 400, "scroll_y": 3})
                
            else:
                result = f"Unknown action type: {current_action.action_type}"
            
            # Record the completed action
            action_record = {
                "index": current_index,
                "action": current_action.dict(),
                "result": result,
                "timestamp": "current"
            }
            
            completed_actions = state.get("completed_actions", [])
            completed_actions.append(action_record)
            
            return {
                **state,
                "completed_actions": completed_actions,
                "current_action_index": current_index + 1
            }
            
        except Exception as e:
            print(f"Error executing action: {e}")
            # Record the error and continue
            action_record = {
                "index": state.get("current_action_index", 0),
                "action": "error",
                "result": f"Error: {str(e)}",
                "timestamp": "current"
            }
            
            completed_actions = state.get("completed_actions", [])
            completed_actions.append(action_record)
            
            return {
                **state,
                "completed_actions": completed_actions,
                "current_action_index": state.get("current_action_index", 0) + 1
            }
    
    async def _evaluate_progress(self, state: SupervisorState) -> SupervisorState:
        """Evaluate if the task is complete or should continue"""
        try:
            current_index = state.get("current_action_index", 0)
            total_actions = len(state["task_plan"].atomic_actions)
            
            # Check if all actions are complete
            if current_index >= total_actions:
                return {
                    **state,
                    "task_complete": True
                }
            
            # Could add more sophisticated evaluation here
            # For now, just continue until all actions are done
            return state
            
        except Exception as e:
            print(f"Error evaluating progress: {e}")
            return {
                **state,
                "task_complete": True
            }
    
    def _should_continue_execution(self, state: SupervisorState) -> str:
        """Decide whether to continue execution, complete, or end"""
        if state.get("task_complete", False):
            return "complete"
        
        current_index = state.get("current_action_index", 0)
        total_actions = len(state["task_plan"].atomic_actions)
        
        if current_index < total_actions:
            return "continue"
        else:
            return "complete"
    
    async def _finalize_result(self, state: SupervisorState) -> SupervisorState:
        """Finalize the task result"""
        try:
            completed_actions = state.get("completed_actions", [])
            task_plan = state["task_plan"]
            
            # Create a summary of what was accomplished
            summary = f"""Task: {task_plan.task_description}

Planned Actions: {len(task_plan.atomic_actions)}
Completed Actions: {len(completed_actions)}

Action Results:
"""
            for action in completed_actions:
                summary += f"- {action.get('action', {}).get('description', 'Unknown')}: {action.get('result', 'No result')}\n"
            
            summary += f"\nSuccess Criteria: {task_plan.success_criteria}"
            
            final_message = AIMessage(content=summary)
            
            return {
                **state,
                "final_result": summary,
                "messages": state["messages"] + [final_message]
            }
            
        except Exception as e:
            error_summary = f"Task execution completed with errors: {str(e)}"
            return {
                **state,
                "final_result": error_summary,
                "messages": state["messages"] + [AIMessage(content=error_summary)]
            }
    
    async def run_task(self, query: str) -> Dict[str, Any]:
        """Run a task using the supervisor-agent system"""
        try:
            initial_state = {
                "messages": [HumanMessage(content=query)],
                "original_query": query,
                "task_plan": None,
                "current_action_index": 0,
                "completed_actions": [],
                "page_context": {},
                "task_complete": False,
                "final_result": ""
            }
            
            # Run the graph
            result = await self.graph.ainvoke(initial_state)
            
            return {
                "success": True,
                "query": query,
                "final_result": result.get("final_result", ""),
                "completed_actions": result.get("completed_actions", []),
                "task_plan": result.get("task_plan", {}).dict() if result.get("task_plan") else {},
                "message_count": len(result.get("messages", []))
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "query": query
            }


# Graph factory function for LangGraph
def create_supervisor_agent_graph():
    """Create and return the Supervisor Playwright agent graph for LangGraph deployment"""
    agent = SupervisorPlaywrightAgent()
    return agent.graph


# Convenience function for simple usage
async def run_supervisor_task(query: str) -> Dict[str, Any]:
    """Simple function to run a supervisor task"""
    agent = SupervisorPlaywrightAgent()
    return await agent.run_task(query)


if __name__ == "__main__":
    async def demo():
        """Demo the supervisor-agent system"""
        print("🎯 Starting Supervisor-Agent Demo...")
        
        tasks = [
            "Take a screenshot and tell me what's on the page",
            "Navigate to x.com and find the login button",
            "Enter username 'rajath_db' in the username field"
        ]
        
        for i, task in enumerate(tasks, 1):
            print(f"\n📋 Supervisor Task {i}: {task}")
            print("-" * 60)
            
            result = await run_supervisor_task(task)
            
            if result.get("success"):
                print(f"✅ Result: {result['final_result']}")
                print(f"📊 Actions completed: {len(result.get('completed_actions', []))}")
            else:
                print(f"❌ Error: {result.get('error', 'Unknown error')}")
            
            # Small delay between tasks
            await asyncio.sleep(2)
        
        print("\n🎉 Supervisor demo complete!")
    
    asyncio.run(demo())
