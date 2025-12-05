"""
Weekly Content Generator Agent

This LangGraph agent generates weekly content ideas based on:
- User's writing style (from imported posts)
- Competitor analysis (high-quality posts)
- Web research (Perplexity API for latest trends)
- Growth-focused strategy (what drives follows)

The agent autonomously decides:
- Content depth (short tweet vs long thread)
- Voice/tone (educational, thought leader, storyteller)
- Topic selection (what will grow followers)
"""

from typing import TypedDict, List, Dict, Any, Annotated
from langgraph.graph import StateGraph, END
from langgraph.store.postgres import PostgresStore
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage
from openai import OpenAI  # Still needed for Perplexity API
import os
from datetime import datetime, timedelta
import json

# ============================================================================
# STATE DEFINITION
# ============================================================================

class ContentGeneratorState(TypedDict):
    """State for the weekly content generator"""
    user_id: str
    user_handle: str

    # User analysis
    user_posts: List[Dict[str, Any]]
    user_style: Dict[str, Any]  # Writing patterns, topics, tone
    user_niche: str

    # Competitor analysis
    top_competitors: List[Dict[str, Any]]
    successful_patterns: Dict[str, Any]
    growth_triggers: List[str]

    # Web research
    latest_trends: List[Dict[str, Any]]
    unique_insights: List[str]
    content_gaps: List[str]

    # Strategy
    content_ideas: List[Dict[str, Any]]  # 20-30 seed ideas
    selected_ideas: List[Dict[str, Any]]  # Top 7 for the week

    # Generated posts
    generated_posts: List[Dict[str, Any]]

    # Error handling
    error: str | None


# ============================================================================
# PERPLEXITY CLIENT
# ============================================================================

def get_perplexity_client():
    """Initialize Perplexity API client (OpenAI-compatible)"""
    api_key = os.getenv("PERPLEXITY_API_KEY")
    if not api_key:
        raise ValueError("PERPLEXITY_API_KEY not found in environment")

    return OpenAI(
        api_key=api_key,
        base_url="https://api.perplexity.ai"
    )


# ============================================================================
# AGENT NODES
# ============================================================================

async def analyze_user_profile(state: ContentGeneratorState) -> ContentGeneratorState:
    """
    Node 1: Analyze user's writing style and niche

    Loads user's imported posts and extracts:
    - Writing style patterns
    - Common topics
    - Tone/voice characteristics
    - Niche focus
    """
    print("📊 Analyzing user profile...")

    user_id = state["user_id"]

    # Get store connection (check POSTGRES_URI first for Cloud Run, then DATABASE_URL for local)
    conn_string = (os.getenv("POSTGRES_URI") or
                   os.getenv("DATABASE_URL") or
                   "postgresql://postgres:password@localhost:5433/xgrowth")

    with PostgresStore.from_conn_string(conn_string) as store:
        # Load user's imported posts
        posts_namespace = (user_id, "writing_samples")
        stored_posts = list(store.search(posts_namespace))

        if not stored_posts:
            state["error"] = "No imported posts found for user"
            return state

        # Extract post contents
        user_posts = [
            {
                "content": p.value.get("content", ""),
                "created_at": p.value.get("created_at"),
                "engagement": p.value.get("engagement", {})
            }
            for p in stored_posts
        ]

        state["user_posts"] = user_posts

        print(f"   ✅ Loaded {len(user_posts)} user posts")

    # Analyze style with AI
    from langchain_core.messages import SystemMessage, HumanMessage

    llm = ChatAnthropic(
        model="claude-sonnet-4-5-20250929",
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        temperature=0.7
    )

    posts_text = "\n\n---\n\n".join([p["content"] for p in user_posts[:20]])

    analysis_prompt = f"""Analyze these X/Twitter posts and extract:

1. Writing Style:
   - Tone (casual, professional, humorous, etc.)
   - Sentence structure (short punchy, detailed, mix)
   - Use of emojis, hashtags, formatting

2. Common Topics:
   - What subjects does this person tweet about?
   - What's their expertise area?

3. Voice Characteristics:
   - Are they educational, opinionated, storytelling, or mix?
   - Do they use personal anecdotes?
   - Technical depth level?

4. Niche:
   - What's the overall niche/industry?

Posts:
{posts_text}

Return ONLY a valid JSON object with keys: style, topics, voice, niche. No markdown, no explanation, just the JSON.
"""

    response = llm.invoke([
        SystemMessage(content="You are an expert at analyzing writing styles and extracting patterns. Always return valid JSON only."),
        HumanMessage(content=analysis_prompt)
    ])

    # Extract JSON from response (Claude might wrap it in markdown)
    content = response.content
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        content = content.split("```")[1].split("```")[0].strip()

    user_style = json.loads(content)
    state["user_style"] = user_style
    state["user_niche"] = user_style.get("niche", "technology")

    print(f"   ✅ Identified niche: {state['user_niche']}")
    print(f"   ✅ Voice: {user_style.get('voice', 'N/A')}")

    return state


async def analyze_competitors(state: ContentGeneratorState) -> ContentGeneratorState:
    """
    Node 2: Analyze competitor posts for successful patterns

    Loads high-quality competitors and identifies:
    - What posts drove engagement/follows
    - Successful content patterns
    - Growth triggers
    """
    print("🔍 Analyzing competitors...")

    user_id = state["user_id"]

    # Get store connection (check POSTGRES_URI first for Cloud Run, then DATABASE_URL for local)
    conn_string = (os.getenv("POSTGRES_URI") or
                   os.getenv("DATABASE_URL") or
                   "postgresql://postgres:password@localhost:5433/xgrowth")

    with PostgresStore.from_conn_string(conn_string) as store:
        # Load social graph
        graph_namespace = (user_id, "social_graph")
        # Try different possible keys
        graph_item = (store.get(graph_namespace, "graph_data") or
                     store.get(graph_namespace, "latest") or
                     store.get(graph_namespace, "current"))

        if not graph_item:
            print("   ⚠️ No competitor data found, skipping competitor analysis")
            state["top_competitors"] = []
            state["successful_patterns"] = {}
            state["growth_triggers"] = []
            return state

        graph = graph_item.value
        # Try different possible keys for competitors list
        all_competitors = (graph.get("top_competitors") or
                          graph.get("all_competitors_raw") or
                          graph.get("competitors", []))

        # Filter high-quality competitors with posts (50%+ quality score)
        high_quality = [
            c for c in all_competitors
            if c.get("quality_score", 0) >= 50 and c.get("posts") and len(c.get("posts", [])) > 0
        ]

        # Take top 10 by quality
        high_quality.sort(key=lambda x: x.get("quality_score", 0), reverse=True)
        top_competitors = high_quality[:10]

        state["top_competitors"] = top_competitors

        print(f"   ✅ Loaded {len(top_competitors)} high-quality competitors")

    if not top_competitors:
        state["successful_patterns"] = {}
        state["growth_triggers"] = []
        return state

    # Analyze patterns with AI
    from langchain_core.messages import SystemMessage, HumanMessage

    llm = ChatAnthropic(
        model="claude-sonnet-4-5-20250929",
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        temperature=0.7
    )

    # Collect top posts from each competitor
    all_posts = []
    for comp in top_competitors:
        posts = comp.get("posts", [])[:5]  # Top 5 posts from each
        for post in posts:
            all_posts.append({
                "username": comp["username"],
                "content": post.get("text", ""),
                "likes": post.get("likes", 0),
                "retweets": post.get("retweets", 0),
                "replies": post.get("replies", 0)
            })

    # Sort by engagement
    all_posts.sort(key=lambda x: x["likes"] + x["retweets"] * 2, reverse=True)
    top_posts = all_posts[:20]  # Top 20 most engaging

    # Clean post content to avoid JSON issues
    posts_summary = "\n\n".join([
        f"@{p['username']}: {p['content'][:200].replace(chr(34), chr(39)).replace(chr(10), ' ')} (👍 {p['likes']}, 🔁 {p['retweets']})"
        for p in top_posts
    ])

    pattern_prompt = f"""Analyze these high-performing X/Twitter posts and identify:

1. Successful Content Patterns:
   - What types of content get the most engagement?
   - Common formats (threads, questions, tips, stories, data)
   - Hook structures (how do they grab attention?)

2. Growth Triggers:
   - What makes people want to follow (not just like)?
   - Value propositions in the content
   - Authority signals

3. Topic Clusters:
   - What topics are trending?
   - What angles are working?

Posts:
{posts_summary}

CRITICAL: Return ONLY a valid JSON object. No markdown code blocks, no explanation, no extra text.
Ensure all strings are properly escaped. Use double quotes for JSON strings.
Format: {{"patterns": {{}}, "growth_triggers": [], "topics": []}}
"""

    response = llm.invoke([
        SystemMessage(content="You are a JSON generator. Return ONLY valid, parseable JSON. No markdown, no code blocks, no explanations. Escape all quotes and special characters properly."),
        HumanMessage(content=pattern_prompt)
    ])

    # Extract JSON from response
    content = response.content
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        content = content.split("```")[1].split("```")[0].strip()

    analysis = json.loads(content)
    state["successful_patterns"] = analysis.get("patterns", {})
    state["growth_triggers"] = analysis.get("growth_triggers", [])

    print(f"   ✅ Identified {len(state['growth_triggers'])} growth triggers")

    return state


async def web_research(state: ContentGeneratorState) -> ContentGeneratorState:
    """
    Node 3: Web research using Perplexity API

    Searches for:
    - Latest trends in the niche
    - Unique insights/data
    - Content gaps/opportunities
    """
    print("🌐 Conducting web research...")

    niche = state["user_niche"]
    user_topics = state["user_style"].get("topics", [])

    try:
        client = get_perplexity_client()

        # Research query 1: Latest trends
        trends_query = f"What are the latest trends, news, and breakthroughs in {niche} in the last 7 days? Focus on topics related to {', '.join(user_topics[:3]) if user_topics else niche}."

        print(f"   🔍 Searching: Latest trends in {niche}...")

        trends_response = client.chat.completions.create(
            model="llama-3.1-sonar-large-128k-online",
            messages=[
                {
                    "role": "system",
                    "content": "You are a research assistant. Provide factual, up-to-date information with specific examples and data."
                },
                {
                    "role": "user",
                    "content": trends_query
                }
            ]
        )

        latest_trends = trends_response.choices[0].message.content

        # Research query 2: Unique insights
        insights_query = f"What are some unique insights, data, or research findings about {niche} that most people don't know about? Include recent case studies or surprising statistics."

        print(f"   🔍 Searching: Unique insights...")

        insights_response = client.chat.completions.create(
            model="llama-3.1-sonar-large-128k-online",
            messages=[
                {
                    "role": "system",
                    "content": "You are a research assistant. Focus on lesser-known insights and surprising findings."
                },
                {
                    "role": "user",
                    "content": insights_query
                }
            ]
        )

        unique_insights = insights_response.choices[0].message.content

        # Research query 3: Content gaps
        gaps_query = f"What important questions or topics in {niche} are under-discussed or lack good explanations? What do people struggle to understand?"

        print(f"   🔍 Searching: Content gaps...")

        gaps_response = client.chat.completions.create(
            model="llama-3.1-sonar-large-128k-online",
            messages=[
                {
                    "role": "system",
                    "content": "You are a research assistant. Identify knowledge gaps and underserved topics."
                },
                {
                    "role": "user",
                    "content": gaps_query
                }
            ]
        )

        content_gaps = gaps_response.choices[0].message.content

        state["latest_trends"] = [{"type": "trends", "content": latest_trends}]
        state["unique_insights"] = [unique_insights]
        state["content_gaps"] = [content_gaps]

        print(f"   ✅ Research complete")

    except Exception as e:
        print(f"   ⚠️ Web research failed: {e}")
        print(f"   ⚠️ Continuing without web research...")
        state["latest_trends"] = []
        state["unique_insights"] = []
        state["content_gaps"] = []

    return state


async def strategize_content(state: ContentGeneratorState) -> ContentGeneratorState:
    """
    Node 4: Strategize weekly content

    Combines all inputs to create:
    - 20-30 content seed ideas
    - Selects top 7 for the week
    - Decides depth, format, positioning for each
    """
    print("🎯 Strategizing content...")

    from langchain_core.messages import SystemMessage, HumanMessage

    llm = ChatAnthropic(
        model="claude-sonnet-4-5-20250929",
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        temperature=0.8
    )

    # Build context
    context = f"""
User Niche: {state['user_niche']}
User Topics: {', '.join(state['user_style'].get('topics', []))}
User Voice: {state['user_style'].get('voice', 'N/A')}

Competitor Patterns:
{json.dumps(state.get('successful_patterns', {}), indent=2)}

Growth Triggers:
{json.dumps(state.get('growth_triggers', []), indent=2)}

Latest Trends:
{state.get('latest_trends', [{}])[0].get('content', 'N/A') if state.get('latest_trends') else 'N/A'}

Unique Insights Available:
{state.get('unique_insights', ['N/A'])[0] if state.get('unique_insights') else 'N/A'}

Content Gaps:
{state.get('content_gaps', ['N/A'])[0] if state.get('content_gaps') else 'N/A'}
"""

    strategy_prompt = f"""You are a content strategist for X/Twitter. Create a weekly content strategy.

Context:
{context}

Generate 7 content ideas for next week (one per day) that will:
1. Grow followers (not just get likes)
2. Build authority in the niche
3. Provide unique value
4. Match the user's voice

For each idea, decide:
- Topic/angle
- Content type (thread, single tweet, question, tip, insight)
- Depth (quick win or deep dive)
- Hook strategy
- Why it will drive follows

Distribute across the week:
- Mix of educational (40%), unique insights (30%), thought leadership (20%), engagement (10%)
- Vary depth and format

Return ONLY a valid JSON object with key "ideas" containing an array of 7 objects, each having:
- day: "Monday" through "Sunday"
- topic: Brief topic description
- content_type: "thread" | "tweet" | "question" | "tip" | "insight"
- depth: "quick" | "medium" | "deep"
- hook: How to grab attention
- value_prop: What value does it provide
- follow_trigger: Why someone would follow for more
- reasoning: Why this idea will work

No markdown, no explanation, just the JSON.
"""

    response = llm.invoke([
        SystemMessage(content="You are an expert content strategist focused on growth. Always return valid JSON only."),
        HumanMessage(content=strategy_prompt)
    ])

    # Extract JSON from response
    content = response.content
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        content = content.split("```")[1].split("```")[0].strip()

    strategy = json.loads(content)
    selected_ideas = strategy.get("ideas", [])[:7]

    state["selected_ideas"] = selected_ideas

    print(f"   ✅ Created strategy for {len(selected_ideas)} posts")
    for i, idea in enumerate(selected_ideas, 1):
        print(f"      {i}. {idea.get('day', 'Day?')}: {idea.get('topic', 'No topic')[:50]}...")

    return state


async def generate_posts(state: ContentGeneratorState) -> ContentGeneratorState:
    """
    Node 5: Generate actual post content

    For each selected idea:
    - Writes full post in user's style
    - Includes unique research insights
    - Adds hooks and CTAs
    - Schedules at optimal times based on engagement data
    """
    print("✍️ Generating posts...")

    from langchain_core.messages import SystemMessage, HumanMessage
    from optimal_posting_times import OptimalPostingTimesAnalyzer
    from database import SessionLocal

    llm = ChatAnthropic(
        model="claude-sonnet-4-5-20250929",
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        temperature=0.9
    )

    user_posts_text = "\n\n---\n\n".join([p["content"] for p in state["user_posts"][:10]])

    generated_posts = []

    # Get optimal posting times using analytics
    db = SessionLocal()
    try:
        analyzer = OptimalPostingTimesAnalyzer(db)

        # Get optimal schedule for the next 7 days (3 posts per day)
        optimal_times = analyzer.get_weekly_optimal_schedule(
            user_id=state["user_id"],
            num_posts_per_day=1,  # 1 post per day for 7 days
            start_date=datetime.now() + timedelta(days=1)  # Start from tomorrow
        )

        print(f"   📊 Using optimal posting times based on engagement data")

    except Exception as e:
        print(f"   ⚠️ Could not calculate optimal times: {e}")
        print(f"   ⚠️ Falling back to industry best practices")

        # Fallback: use industry best times
        today = datetime.now()
        optimal_times = []
        industry_hours = [9, 8, 10, 12, 13, 14, 17]  # Best industry hours

        for idx in range(7):
            post_date = today + timedelta(days=idx + 1)
            hour = industry_hours[idx % len(industry_hours)]
            optimal_times.append(post_date.replace(hour=hour, minute=0, second=0, microsecond=0))
    finally:
        db.close()

    # Schedule for the next 7 days starting from tomorrow
    today = datetime.now()

    for idx, idea in enumerate(state["selected_ideas"]):
        # Use the pre-calculated optimal time for this post
        post_datetime = optimal_times[idx] if idx < len(optimal_times) else optimal_times[0] + timedelta(days=idx)

        # Get actual day name for the scheduled date
        actual_day_name = post_datetime.strftime("%A")

        generation_prompt = f"""Write an X/Twitter post based on this idea:

Idea:
- Topic: {idea.get('topic', '')}
- Type: {idea.get('content_type', 'tweet')}
- Depth: {idea.get('depth', 'medium')}
- Hook: {idea.get('hook', '')}
- Value: {idea.get('value_prop', '')}

Research Context:
{state.get('unique_insights', [''])[0][:500] if state.get('unique_insights') else ''}

User's Writing Style (match this):
{user_posts_text[:1000]}

Requirements:
1. Match the user's voice and style EXACTLY
2. Start with a strong hook (first line is crucial)
3. Provide unique value (use research insights if relevant)
4. If thread: Number each tweet (1/X format)
5. End with subtle follow trigger (curiosity for more)
6. Keep authentic to the user's personality

{'Create a thread (8-12 tweets)' if idea.get('content_type') == 'thread' else 'Create a single tweet (280 chars max)' if idea.get('content_type') == 'tweet' else 'Create 2-3 connected tweets'}

Return ONLY the post content, nothing else.
"""

        print(f"   📝 Writing: {actual_day_name} - {idea.get('topic', 'No topic')[:40]}...")

        response = llm.invoke([
            SystemMessage(content="You are a ghostwriter who perfectly mimics writing styles. Return only the post content with no extra commentary."),
            HumanMessage(content=generation_prompt)
        ])

        post_content = response.content.strip()

        # Calculate confidence based on idea quality
        confidence = 0.7 + (0.3 * (1 if idea.get('follow_trigger') else 0))

        # Get posting time rationale
        try:
            posting_rationale = analyzer.get_posting_rationale(post_datetime, state["user_id"])
        except:
            posting_rationale = f"{actual_day_name} {post_datetime.hour}:00 - Based on industry best practices"

        generated_posts.append({
            "content": post_content,
            "scheduled_at": post_datetime.isoformat(),
            "confidence": confidence,
            "ai_generated": True,
            "metadata": {
                "day": actual_day_name,
                "topic": idea.get("topic", ""),
                "content_type": idea.get("content_type", "tweet"),
                "reasoning": idea.get("reasoning", ""),
                "source": "weekly_content_generator",
                "posting_time_rationale": posting_rationale
            }
        })

    state["generated_posts"] = generated_posts

    print(f"   ✅ Generated {len(generated_posts)} posts")

    return state


# ============================================================================
# GRAPH CONSTRUCTION
# ============================================================================

def create_content_generator_graph():
    """Create the LangGraph state graph for content generation"""

    workflow = StateGraph(ContentGeneratorState)

    # Add nodes
    workflow.add_node("analyze_user_profile", analyze_user_profile)
    workflow.add_node("analyze_competitors", analyze_competitors)
    workflow.add_node("web_research", web_research)
    workflow.add_node("strategize_content", strategize_content)
    workflow.add_node("generate_posts", generate_posts)

    # Set entry point
    workflow.set_entry_point("analyze_user_profile")

    # Add edges (linear flow)
    workflow.add_edge("analyze_user_profile", "analyze_competitors")
    workflow.add_edge("analyze_competitors", "web_research")
    workflow.add_edge("web_research", "strategize_content")
    workflow.add_edge("strategize_content", "generate_posts")
    workflow.add_edge("generate_posts", END)

    return workflow.compile()


# ============================================================================
# MAIN EXECUTION
# ============================================================================

async def generate_weekly_content(user_id: str, user_handle: str) -> List[Dict[str, Any]]:
    """
    Main entry point for weekly content generation

    Args:
        user_id: User's unique identifier
        user_handle: User's X/Twitter handle

    Returns:
        List of 7 generated posts with metadata
    """
    print(f"\n🚀 Starting Weekly Content Generation for @{user_handle}")
    print("=" * 60)

    # Create graph
    app = create_content_generator_graph()

    # Initial state
    initial_state: ContentGeneratorState = {
        "user_id": user_id,
        "user_handle": user_handle,
        "user_posts": [],
        "user_style": {},
        "user_niche": "",
        "top_competitors": [],
        "successful_patterns": {},
        "growth_triggers": [],
        "latest_trends": [],
        "unique_insights": [],
        "content_gaps": [],
        "content_ideas": [],
        "selected_ideas": [],
        "generated_posts": [],
        "error": None
    }

    # Run the graph
    final_state = await app.ainvoke(initial_state)

    if final_state.get("error"):
        error_msg = final_state["error"] or "Content generation failed with unknown error"
        raise Exception(error_msg)

    print("\n" + "=" * 60)
    print(f"✅ Content Generation Complete!")
    print(f"   Generated {len(final_state['generated_posts'])} posts for next week")
    print("=" * 60 + "\n")

    return final_state["generated_posts"]


# ============================================================================
# TEST
# ============================================================================

if __name__ == "__main__":
    import asyncio

    # Test with a user
    async def test():
        posts = await generate_weekly_content(
            user_id="user_34wsv56iMdmN9jPXo6Pg6HeroFK",
            user_handle="Rajath_DB"
        )

        print("\n📋 Generated Posts Preview:")
        for i, post in enumerate(posts, 1):
            print(f"\n{i}. {post['metadata']['day']} ({post['metadata']['topic'][:40]}...)")
            print(f"   {post['content'][:100]}...")
            print(f"   Confidence: {post['confidence']:.0%}")

    asyncio.run(test())
