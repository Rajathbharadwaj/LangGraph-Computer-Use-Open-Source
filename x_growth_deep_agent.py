"""
X Growth Deep Agent - Atomic Action Architecture

Main DeepAgent: Strategic planner and memory keeper
Subagents: Execute ONE atomic action per invocation

Architecture:
- Main agent NEVER executes Playwright actions directly
- Main agent only: plans, delegates, tracks memory
- Each subagent executes ONE atomic Playwright action
- Subagents return immediately after action
"""

import os
from typing import Literal
from deepagents import create_deep_agent
from langchain.chat_models import init_chat_model

# Import your existing Playwright tools
from async_playwright_tools import get_async_playwright_tools

# Import Chrome Extension tools (superpowers!)
from async_extension_tools import get_async_extension_tools

# Import workflows
from x_growth_workflows import get_workflow_prompt, list_workflows, WORKFLOWS


# ============================================================================
# ATOMIC ACTION SUBAGENTS
# Each subagent executes ONE Playwright action and returns immediately
# ============================================================================

def get_atomic_subagents():
    """
    Get atomic subagents with BOTH Playwright AND Extension tools.
    This function is called at runtime to get the actual tool instances.
    
    Extension tools provide capabilities Playwright doesn't have:
    - Access to React internals and hidden data
    - Real-time DOM monitoring
    - Human-like interactions
    - Rate limit detection
    - Session health monitoring
    """
    # Get all Playwright tools
    playwright_tools = get_async_playwright_tools()
    
    # Get all Extension tools (superpowers!)
    extension_tools = get_async_extension_tools()
    
    # Combine both tool sets
    all_tools = playwright_tools + extension_tools
    
    # Create a dict for easy lookup
    tool_dict = {tool.name: tool for tool in all_tools}
    
    return [
        {
            "name": "navigate",
            "description": "Navigate to a specific URL. Use this to go to X.com pages (search, profile, post, etc.)",
            "system_prompt": """You are a navigation specialist.

Your ONLY job: Navigate to the URL provided and confirm success.

Steps:
1. Call navigate_to_url with the exact URL
2. Return success/failure

That's it. Do NOT do anything else.""",
            "tools": [tool_dict["navigate_to_url"]]
        },
        
        {
            "name": "analyze_page",
            "description": "Analyze the current page comprehensively - get visual content (OmniParser), DOM elements, and text. Use this to see what posts, buttons, and content are visible.",
            "system_prompt": """You are a page analysis specialist with VISION capabilities.

Your job: Get comprehensive page context and describe what you see.

Steps:
1. Call get_comprehensive_context to get OmniParser visual analysis + DOM + text
2. Parse the comprehensive context to identify:
   - Visible posts (author, content, engagement metrics)
   - Interactive elements (buttons, links, forms)
   - Current page state
3. Return a DETAILED description of what's actually visible

CRITICAL: Use the ACTUAL content from get_comprehensive_context.
- OmniParser shows visual elements and bounding boxes
- Playwright DOM shows interactive elements
- Page text shows actual post content

DO NOT make up or hallucinate content. Only describe what's in the comprehensive context.""",
            "tools": [tool_dict["get_comprehensive_context"]]
        },
        
        {
            "name": "type_text",
            "description": "Type text into an input field (search box, comment box, etc.)",
            "system_prompt": """You are a typing specialist.

Your ONLY job: Type the exact text provided into the appropriate field.

Steps:
1. Call type_text with the text
2. Return success/failure

That's it. Do NOT press enter or do anything else.""",
            "tools": [tool_dict["type_text"]]
        },
        
        {
            "name": "click",
            "description": "Click at specific coordinates on the page",
            "system_prompt": """You are a clicking specialist.

Your ONLY job: Click at the coordinates provided.

Steps:
1. Call click_at_coordinates with x, y
2. Return success/failure

That's it. Do NOT do anything else.""",
            "tools": [tool_dict["click_at_coordinates"]]
        },
        
        {
            "name": "scroll",
            "description": "Scroll the page up or down",
            "system_prompt": """You are a scrolling specialist.

Your ONLY job: Scroll the page in the direction specified.

Steps:
1. Call scroll_page with x, y, scroll_x, scroll_y
2. Return success/failure

That's it. Do NOT do anything else.""",
            "tools": [tool_dict["scroll_page"]]
        },
        
        {
            "name": "like_post",
            "description": "Like a specific post by identifying it (by author or content)",
            "system_prompt": """You are a post liking specialist.

Your ONLY job: Like the specific post identified.

Steps:
1. Call like_post with the identifier
2. Return success/failure

CRITICAL: Do NOT like multiple posts. ONE post only.""",
            "tools": [tool_dict["like_post"]]
        },
        
        {
            "name": "comment_on_post",
            "description": "Comment on a specific post",
            "system_prompt": """You are a commenting specialist.

Your ONLY job: Post the comment provided on the specified post.

Steps:
1. Call comment_on_post with post identifier and comment text
2. Return success/failure

That's it. Do NOT comment on multiple posts.""",
            "tools": [tool_dict["comment_on_post"]]
        },
        
        {
            "name": "create_post",
            "description": "Create a new post on X (Twitter) with the provided text",
            "system_prompt": """You are a post creation specialist.

Your ONLY job: Create a new post on X with the exact text provided.

Steps:
1. Call create_post_via_extension with the post text
2. Return success/failure

CRITICAL RULES:
- Post text MUST be under 280 characters
- Do NOT add hashtags (X algorithm penalizes them)
- Do NOT modify the text provided
- Do NOT create multiple posts

Example:
User: "Create a post: Just shipped a new feature! 🚀"
You: Call create_post_via_extension("Just shipped a new feature! 🚀")

That's it. ONE post only.""",
            "tools": [tool_dict["create_post_via_extension"]]
        },
        
        {
            "name": "enter_credentials",
            "description": "Enter username or password for login",
            "system_prompt": """You are a credential entry specialist.

Your ONLY job: Enter the username or password provided.

Steps:
1. Call enter_username or enter_password
2. Return success/failure

That's it. Do NOT submit the form.""",
            "tools": [tool_dict["enter_username"], tool_dict["enter_password"]]
        },
        
        # ========================================================================
        # EXTENSION-POWERED SUBAGENTS (Superpowers!)
        # These use Chrome Extension for capabilities Playwright doesn't have
        # ========================================================================
        
        {
            "name": "check_rate_limits",
            "description": "Check if X is rate limiting us (CRITICAL before actions)",
            "system_prompt": """You are a rate limit monitor.

Your ONLY job: Check if X is showing rate limit warnings.

Steps:
1. Call check_rate_limit_status
2. Return the status

CRITICAL: If rate limited, the main agent MUST stop all actions!""",
            "tools": [tool_dict["check_rate_limit_status"]]
        },
        
        {
            "name": "extract_engagement_data",
            "description": "Extract hidden engagement metrics from a post",
            "system_prompt": """You are an engagement data analyst.

Your ONLY job: Extract hidden engagement data from the specified post.

Steps:
1. Call extract_post_engagement_data with post identifier
2. Return the detailed metrics

This accesses React internals that Playwright cannot see!""",
            "tools": [tool_dict["extract_post_engagement_data"]]
        },
        
        {
            "name": "analyze_account",
            "description": "Analyze an account to decide if it's worth engaging with",
            "system_prompt": """You are an account analyst.

Your ONLY job: Extract insights about the specified account.

Steps:
1. Call extract_account_insights with username
2. Return the analysis

Use this to decide if an account is worth engaging with!""",
            "tools": [tool_dict["extract_account_insights"]]
        },
        
        {
            "name": "get_post_context",
            "description": "Get full context of a post including hidden data",
            "system_prompt": """You are a post context analyzer.

Your ONLY job: Get full context of the specified post.

Steps:
1. Call get_post_context with post identifier
2. Return the context

This includes thread context, author reputation, engagement patterns!""",
            "tools": [tool_dict["get_post_context"]]
        },
        
        {
            "name": "human_click",
            "description": "Click with human-like behavior (MORE STEALTHY)",
            "system_prompt": """You are a stealth clicking specialist.

Your ONLY job: Click with realistic human behavior.

Steps:
1. Call human_like_click with element description
2. Return success/failure

This adds realistic delays and movements for better stealth!""",
            "tools": [tool_dict["human_like_click"]]
        },
        
        {
            "name": "monitor_action",
            "description": "Monitor DOM for instant action confirmation",
            "system_prompt": """You are an action monitor.

Your ONLY job: Monitor DOM for action result.

Steps:
1. Call monitor_action_result with action type
2. Return success/failure confirmation

This provides INSTANT feedback using mutation observers!""",
            "tools": [tool_dict["monitor_action_result"]]
        },
        
        {
            "name": "check_session",
            "description": "Check if browser session is healthy",
            "system_prompt": """You are a session health monitor.

Your ONLY job: Check if the session is healthy.

Steps:
1. Call check_session_health
2. Return the health status

Use this to detect session expiration or login issues!""",
            "tools": [tool_dict["check_session_health"]]
        },
        
        {
            "name": "find_trending",
            "description": "Find trending topics for engagement opportunities",
            "system_prompt": """You are a trending topics analyst.

Your ONLY job: Get current trending topics.

Steps:
1. Call get_trending_topics
2. Return the trending list

Use this to find engagement opportunities!""",
            "tools": [tool_dict["get_trending_topics"]]
        },
        
        {
            "name": "find_high_engagement_posts",
            "description": "Find the best posts to engage with on a topic",
            "system_prompt": """You are a post discovery specialist.

Your ONLY job: Find high-engagement posts on the specified topic.

Steps:
1. Call find_high_engagement_posts with topic
2. Return the ranked list

These are the BEST posts to engage with for maximum impact!""",
            "tools": [tool_dict["find_high_engagement_posts"]]
        },
    ]


# ============================================================================
# MAIN DEEP AGENT - Strategic Orchestrator
# ============================================================================

MAIN_AGENT_PROMPT = """You are a Parallel Universe AI agent - an X (Twitter) account growth strategist.

🎯 YOUR GOAL: Execute pre-defined workflows to grow the X account.

🧠 YOUR ROLE: Workflow orchestrator and memory keeper
- You SELECT the appropriate workflow for the user's goal
- You EXECUTE workflows step-by-step by delegating to subagents
- You TRACK what's been done in action_history.json
- You NEVER execute Playwright actions directly
- You NEVER deviate from the workflow steps

🔧 YOUR TOOLS:
- get_comprehensive_context: SEE the current page (OmniParser visual + DOM + text) - use this to understand what's visible before planning
- write_todos: Track workflow progress
- read_file: Check action_history.json to see what you've done
- write_file: Save actions to action_history.json
- task: Delegate ONE atomic action to a subagent

🤖 YOUR SUBAGENTS (call via task() tool):
- navigate: Go to a URL
- analyze_page: Get comprehensive page analysis (visual + DOM + text) to see what's visible
- type_text: Type into a field
- click: Click at coordinates
- scroll: Scroll the page
- like_post: Like ONE post
- comment_on_post: Comment on ONE post
- enter_credentials: Enter username/password

📋 AVAILABLE WORKFLOWS:
1. engagement - Find and engage with posts (likes + comments)
2. reply_to_thread - Find viral thread and reply to comments
3. profile_engagement - Engage with specific user's content
4. content_posting - Create and post original content
5. dm_outreach - Send DMs to connections

📋 WORKFLOW EXECUTION:
1. User provides goal (e.g., "engagement")
2. FIRST: Call get_comprehensive_context to see what's currently on the page
3. You receive the workflow steps
4. Execute steps IN ORDER (do NOT skip or reorder)
5. Delegate each step to appropriate subagent using task()
6. Wait for result before next step
7. Check/update action_history.json as specified
8. Call get_comprehensive_context again when you need to see page updates

🚨 CRITICAL RULES:
- ALWAYS call get_comprehensive_context FIRST to see what's actually on the page
- NEVER make up or hallucinate posts/content - only describe what you actually see in the comprehensive context
- ALWAYS check action_history.json before engaging to avoid duplicates
- NEVER engage with the same post/user twice in 24 hours
- NEVER like more than 50 posts per day (rate limit)
- NEVER comment more than 20 times per day (rate limit)
- ALWAYS be authentic - no spam, no generic comments
- DELEGATE one action at a time - wait for result before next action
- USE HOME TIMELINE (https://x.com/home) - X's algorithm already shows relevant content
- ENGAGE with posts from your timeline - they're already curated for you
- Don't waste time searching - the home timeline has the best content

💡 ENGAGEMENT STRATEGY:
- USE HOME TIMELINE (https://x.com/home) - X curates relevant content for you
- Engage with posts from people you follow and their network
- Like posts that are thoughtful and relevant to your niche
- Comment with value-add insights (not "great post!")
- Reply to interesting threads in your timeline
- Build relationships with accounts in your network
- No need to search - the timeline has quality content already!

🎯 QUALITY > QUANTITY:
- 10 thoughtful engagements > 100 random likes
- Focus on posts with <1000 likes (higher visibility)
- Engage with accounts that have 500-50k followers (sweet spot)
- Reply to posts within 1 hour of posting (higher engagement)

📊 MEMORY FORMAT (action_history.json):
{
  "date": "2025-11-01",
  "actions": [
    {
      "timestamp": "2025-11-01T10:30:00",
      "action": "liked",
      "post_author": "@username",
      "post_content_snippet": "First 50 chars...",
      "post_url": "https://x.com/username/status/123"
    },
    {
      "timestamp": "2025-11-01T10:35:00",
      "action": "commented",
      "post_author": "@username",
      "comment_text": "Your comment...",
      "post_url": "https://x.com/username/status/456"
    }
  ],
  "daily_stats": {
    "likes": 15,
    "comments": 3,
    "profile_visits": 2
  }
}

🎬 EXAMPLE EXECUTION:
User: "What posts do you see?"

Correct approach:
1. Call get_comprehensive_context() - SEE the actual page
2. Parse the comprehensive context to find:
   - Post 1: @garrytan about virality (25 comments, 253 likes)
   - Post 2: @techbimbo about AI images
   - etc.
3. Describe ONLY what you actually see in the context

WRONG approach:
❌ Making up fake posts about quantum computing or pasta
❌ Describing posts that aren't in the comprehensive context
❌ Hallucinating engagement metrics

User: "Run engagement workflow"

You execute:
1. Call get_comprehensive_context() - see current page
2. task("navigate", "Go to https://x.com/home")
3. Call get_comprehensive_context() - see home timeline with curated posts
4. task("scroll", "Scroll to load more posts")
5. Call get_comprehensive_context() - see more timeline posts
6. Read action_history.json - check what we've already engaged with
7. task("like_post", "Like post by @user1") - using actual username from context
8. task("like_post", "Like post by @user2") - continue with more posts
9. Write to action_history.json - record engagements
10. Repeat for 8-10 posts from timeline

Remember: 
- Follow workflow steps IN ORDER
- ONE atomic action at a time
- Wait for result before next step
- Check/update memory as specified
"""


def create_x_growth_agent(config: dict = None):
    """
    Create the X Growth Deep Agent with optional user-specific long-term memory
    
    Args:
        config: RunnableConfig dict with optional configurable parameters:
            - model_name: The LLM model to use (default: claude-sonnet-4-5-20250929)
            - user_id: Optional user ID for personalized memory
            - store: Optional LangGraph Store (InMemoryStore or PostgresStore)
            - use_longterm_memory: Enable long-term memory persistence (default: True)
        
    Returns:
        DeepAgent configured for X account growth (and optionally XUserMemory)
    """
    
    # Extract parameters from config
    if config is None:
        config = {}
    
    # Get configurable values with defaults
    configurable = config.get("configurable", {})
    model_name = configurable.get("model_name", "claude-sonnet-4-5-20250929")
    user_id = configurable.get("user_id", None)
    store = configurable.get("store", None)
    use_longterm_memory = configurable.get("use_longterm_memory", True)
    
    # Initialize the model
    model = init_chat_model(model_name)
    
    # Get atomic subagents (with Playwright tools)
    subagents = get_atomic_subagents()
    
    # Customize prompt with user preferences if user_id provided
    system_prompt = MAIN_AGENT_PROMPT
    user_memory = None
    
    if user_id and use_longterm_memory:
        # Initialize store if not provided
        if store is None:
            from langgraph.store.memory import InMemoryStore
            store = InMemoryStore()
        
        # Initialize user memory
        from x_user_memory import XUserMemory
        user_memory = XUserMemory(store, user_id)
        
        # Get user preferences
        preferences = user_memory.get_preferences()
        
        # Get user's writing style
        from user_writing_style import get_user_style_prompt
        try:
            writing_style_prompt = get_user_style_prompt(user_id)
        except Exception as e:
            print(f"⚠️ Could not load writing style: {e}")
            writing_style_prompt = "Write in a professional but friendly tone."
        
        if preferences:
            system_prompt += f"""

🎯 USER-SPECIFIC PREFERENCES (from long-term memory):
- User ID: {user_id}
- Niche: {', '.join(preferences.niche)}
- Target Audience: {preferences.target_audience}
- Growth Goal: {preferences.growth_goal}
- Engagement Style: {preferences.engagement_style}
- Daily Limits: {preferences.daily_limits}

{writing_style_prompt}

💾 LONG-TERM MEMORY ACCESS:
You have access to persistent memory via /memories/ filesystem:
- /memories/preferences.txt - User preferences
- /memories/engagement_history/ - Past engagements (check before engaging!)
- /memories/learnings/ - What works for this user
- /memories/account_profiles/ - Cached account research

IMPORTANT: 
1. ALWAYS check /memories/engagement_history/ before engaging to avoid duplicates
2. Use /memories/learnings/ to apply what works for this user
3. Cache account research in /memories/account_profiles/ for efficiency
4. Update learnings when you discover patterns
5. When commenting, MATCH THE USER'S WRITING STYLE from the profile above
"""
    
    # Get the comprehensive context tool for the main agent
    # This allows the main agent to SEE the page before planning
    playwright_tools = get_async_playwright_tools()
    comprehensive_context_tool = next(t for t in playwright_tools if t.name == "get_comprehensive_context")
    
    # Create the main agent with vision capability
    agent = create_deep_agent(
        model=model,
        system_prompt=system_prompt,  # deepagents 0.2.4+ uses 'system_prompt'
        tools=[comprehensive_context_tool],  # Main agent can see the page via comprehensive context
        subagents=subagents,
    )
    
    # Store user_memory reference in agent for access if needed
    if user_memory:
        agent.user_memory = user_memory
    
    # Always return just the agent (LangGraph requirement)
    return agent


# ============================================================================
# USAGE EXAMPLE
# ============================================================================

def run_workflow(workflow_name: str, **params):
    """
    Run a specific workflow
    
    Args:
        workflow_name: Name of the workflow (e.g., 'engagement')
        **params: Parameters for the workflow (e.g., keywords='AI agents')
    
    Returns:
        Agent result
    """
    # Create the agent
    print(f"🤖 Creating X Growth Deep Agent...")
    agent = create_x_growth_agent()
    
    # Get the workflow prompt
    workflow_prompt = get_workflow_prompt(workflow_name, **params)
    
    # Execute the workflow
    print(f"\n🚀 Starting {workflow_name} workflow...")
    print(f"📋 Parameters: {params}")
    
    result = agent.invoke({
        "messages": [workflow_prompt]
    })
    
    print("\n✅ Workflow complete!")
    return result


if __name__ == "__main__":
    # Set your API key
    if "ANTHROPIC_API_KEY" not in os.environ:
        print("⚠️  Please set ANTHROPIC_API_KEY environment variable")
        exit(1)
    
    print("=" * 60)
    print("🤖 X Growth Agent - Examples")
    print("=" * 60)
    
    # Example 1: Basic agent (no user memory)
    print("\n📝 Example 1: Basic Agent (no user memory)")
    print("-" * 60)
    agent = create_x_growth_agent()
    print("✅ Basic agent created")
    
    # Example 2: Agent with user-specific memory
    print("\n📝 Example 2: Agent with User Memory")
    print("-" * 60)
    from langgraph.store.memory import InMemoryStore
    from x_user_memory import XUserMemory, UserPreferences
    
    # Create store
    store = InMemoryStore()
    user_id = "user_123"
    
    # Set up user preferences
    user_memory = XUserMemory(store, user_id)
    preferences = UserPreferences(
        user_id=user_id,
        niche=["AI", "LangChain", "agents"],
        target_audience="AI/ML practitioners",
        growth_goal="build authority",
        engagement_style="thoughtful_expert",
        tone="professional",
        daily_limits={"likes": 50, "comments": 20},
        optimal_times=["9-11am EST", "7-9pm EST"],
        avoid_topics=["politics", "religion"]
    )
    user_memory.save_preferences(preferences)
    print(f"✅ User preferences saved for {user_id}")
    
    # Create agent with user memory
    agent = create_x_growth_agent(config={
        "configurable": {
            "user_id": user_id,
            "store": store,
            "use_longterm_memory": True
        }
    })
    print(f"✅ Agent created with user-specific memory")
    print(f"   Niche: {preferences.niche}")
    print(f"   Goal: {preferences.growth_goal}")
    
    # Example 3: Run workflow with user memory
    print("\n📝 Example 3: Run Workflow with User Memory")
    print("-" * 60)
    print("🎯 Running engagement workflow...")
    print("   (Agent will use user preferences and check memory)")
    
    # List available workflows
    print("\n📋 Available Workflows:")
    for name, workflow in WORKFLOWS.items():
        print(f"  • {name}: {workflow.goal}")
    
    print("\n" + "=" * 60)
    print("✅ Examples complete!")
    print("\nTo run a workflow:")
    print("  result = run_workflow('engagement', keywords='AI agents')")
    print("=" * 60)

