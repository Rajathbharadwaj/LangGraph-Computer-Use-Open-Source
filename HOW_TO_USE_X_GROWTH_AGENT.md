STDIN
# 🚀 How to Use the X Growth Deep Agent

## 🎯 What It Does

The X Growth Deep Agent automates your X (Twitter) account growth through **5 pre-defined workflows**:

1. **Engagement** - Find and engage with trending posts (likes + comments)
2. **Reply to Thread** - Find viral threads and reply to comments
3. **Profile Engagement** - Engage with a specific user's content
4. **Content Posting** - Create and post original content
5. **DM Outreach** - Send DMs to potential connections

## 🧠 How It Works

### Architecture:

```
┌─────────────────────────────────────────────────────────┐
│              MAIN DEEP AGENT (Orchestrator)             │
│  - Receives your goal (e.g., "Engage with AI posts")   │
│  - Selects appropriate workflow                         │
│  - Plans and tracks progress                            │
│  - Delegates to subagents                               │
└─────────────────────────────────────────────────────────┘
                          ↓
        ┌─────────────────┴─────────────────┐
        ↓                                     ↓
┌──────────────────┐              ┌──────────────────────┐
│ STRATEGIC        │              │ ATOMIC SUBAGENTS     │
│ SUBAGENTS        │              │ (36 total)           │
│                  │              │                      │
│ - Post Analyzer  │              │ - navigate           │
│ - Account        │              │ - screenshot         │
│   Researcher     │              │ - type_text          │
│ - Comment        │              │ - click              │
│   Generator      │              │ - scroll             │
│ - Engagement     │              │ - like_post          │
│   Strategist     │              │ - comment_on_post    │
│ - Memory Manager │              │ - ... 29 more        │
└──────────────────┘              └──────────────────────┘
        ↓                                     ↓
    DECIDES                               EXECUTES
  (Analyzes,                           (ONE action,
   Scores,                              returns result)
   Recommends)
```

### Execution Flow:

```
1. User: "Engage with AI posts"
   ↓
2. Main Agent: Selects "engagement_workflow"
   ↓
3. Main Agent: Reads workflow steps (15 steps)
   ↓
4. Main Agent: Delegates Step 1 to "navigate" subagent
   ↓
5. Navigate Subagent: Executes ONE action (go to X.com/search)
   ↓ Returns result
6. Main Agent: Delegates Step 2 to "screenshot" subagent
   ↓
7. Screenshot Subagent: Takes screenshot
   ↓ Returns result
8. Main Agent: Continues through all 15 steps...
   ↓
9. Main Agent: Updates memory (action_history.json)
   ↓
10. Main Agent: Returns summary of what was done
```

## 📋 Workflow Example: Engagement

**Goal:** Find and engage with trending AI posts

**Steps (15 total):**
1. Navigate to X.com/search
2. Take screenshot (see the page)
3. Type search keywords ("AI agents")
4. Click search button
5. Take screenshot (see results)
6. Scroll down (load more posts)
7. Take screenshot (see more posts)
8. Like post #1 (check memory first)
9. Like post #2 (check memory first)
10. Like post #3 (check memory first)
11. Like post #4 (check memory first)
12. Like post #5 (check memory first)
13. Comment on best post (thoughtful, authentic)
14. Comment on second best post
15. Update memory (save what was done)

**Memory Tracking:**
- Before liking/commenting: Check `action_history.json`
- Prevents duplicate engagement (no re-liking same post)
- Tracks daily limits (max 50 likes, 20 comments)

## 🎮 How to Use It

### Option 1: Via LangGraph Studio (Recommended)

1. **Start LangGraph Studio:**
```bash
cd /home/rajathdb/cua
langgraph dev
```

2. **Open Studio:**
   - Go to http://localhost:8123
   - Select `x_growth_deep_agent`

3. **Send a Goal:**
```json
{
  "messages": [
    {
      "role": "user",
      "content": "Run engagement workflow for AI agents"
    }
  ]
}
```

4. **Watch It Work:**
   - See the agent plan and execute
   - View each subagent call
   - Monitor progress in real-time
   - Check VNC viewer (http://localhost:5900) to see browser

### Option 2: Via Python Script

```python
from x_growth_deep_agent import create_x_growth_agent, run_workflow

# Create the agent
agent = create_x_growth_agent()

# Run a workflow
result = run_workflow(
    workflow_name="engagement",
    keywords="AI agents"
)

print(result)
```

### Option 3: Via LangGraph API

```python
from langgraph_sdk import get_client

# Connect to LangGraph server
client = get_client(url="http://localhost:8123")

# Create a thread
thread = client.threads.create()

# Run the agent
run = client.runs.create(
    thread_id=thread["thread_id"],
    assistant_id="x_growth_deep_agent",
    input={
        "messages": [
            {
                "role": "user",
                "content": "Engage with trending posts about LangChain"
            }
        ]
    },
    config={
        "configurable": {
            "user_id": "user_123",
            "model_name": "claude-sonnet-4-5-20250929"
        }
    }
)

# Stream results
for chunk in client.runs.stream(thread_id=thread["thread_id"], run_id=run["run_id"]):
    print(chunk)
```

## 🎯 Available Workflows

### 1. Engagement Workflow
**Goal:** Find and engage with posts

**Usage:**
```python
run_workflow("engagement", keywords="AI agents")
```

**What it does:**
- Searches for posts with keywords
- Likes 5 relevant posts
- Comments on 2 best posts
- Updates memory

**Best for:** Daily engagement, building presence

---

### 2. Reply to Thread Workflow
**Goal:** Find viral thread and reply to comments

**Usage:**
```python
run_workflow("reply_to_thread", thread_url="https://x.com/user/status/123")
```

**What it does:**
- Opens the thread
- Reads all comments
- Finds best comments to reply to
- Writes thoughtful replies
- Updates memory

**Best for:** Joining conversations, visibility

---

### 3. Profile Engagement Workflow
**Goal:** Engage with a specific user's content

**Usage:**
```python
run_workflow("profile_engagement", username="elonmusk")
```

**What it does:**
- Goes to user's profile
- Likes their recent posts
- Comments on best posts
- Follows if high-quality
- Updates memory

**Best for:** Building relationships, networking

---

### 4. Content Posting Workflow
**Goal:** Create and post original content

**Usage:**
```python
run_workflow("content_posting", topic="AI agents", tone="insightful")
```

**What it does:**
- Generates content in YOUR style
- Reviews and refines
- Posts to X
- Monitors engagement
- Updates memory

**Best for:** Thought leadership, content creation

---

### 5. DM Outreach Workflow
**Goal:** Send DMs to potential connections

**Usage:**
```python
run_workflow("dm_outreach", targets=["user1", "user2"], message_template="...")
```

**What it does:**
- Goes to each user's profile
- Checks if already contacted
- Sends personalized DM
- Updates memory

**Best for:** Networking, partnerships

## 🧠 Strategic Decision Making

The agent uses **strategic subagents** to make smart decisions:

### Post Analyzer
**Scores posts 0-100 based on:**
- Engagement rate (likes, comments, retweets)
- Author credibility (followers, verification)
- Content quality (relevance, depth)
- Recency (posted within 24 hours?)
- Virality potential

**Example:**
```
Post: "AI agents are the future of software"
Score: 85/100
- Engagement: 500 likes, 50 comments (high)
- Author: 10k followers, verified (good)
- Content: Relevant to AI niche (perfect)
- Recency: Posted 2 hours ago (fresh)
→ Decision: ENGAGE
```

### Account Researcher
**Scores accounts 0-100 based on:**
- Follower count (500-50k sweet spot)
- Engagement rate (high interaction)
- Bio quality (clear niche, professional)
- Content quality (consistent, valuable)
- Reputation signals (verification, mentions)

**Example:**
```
Account: @ai_researcher
Score: 92/100
- Followers: 15k (perfect range)
- Engagement: 3% avg (excellent)
- Bio: "AI researcher at MIT" (credible)
- Content: Daily AI insights (consistent)
→ Decision: HIGH PRIORITY
```

### Comment Generator
**Generates comments that:**
- Match YOUR writing style (learned from your posts)
- Add value (not "great post!")
- Are authentic (no spam patterns)
- Fit the context (relevant to post)
- Encourage conversation

**Example:**
```
Post: "Just launched our new AI agent framework"
Generated Comment: "This looks promising! How does it handle 
multi-step reasoning? We've been exploring similar approaches 
with LangGraph and would love to compare notes."

Style: Professional, curious, collaborative
Tone: Matches your past comments
Length: 2-3 sentences (optimal)
```

## 💾 Memory System

The agent maintains memory in `action_history.json`:

```json
{
  "date": "2025-11-02",
  "actions": [
    {
      "timestamp": "2025-11-02T10:30:00",
      "action": "liked",
      "post_author": "@ai_researcher",
      "post_content_snippet": "AI agents are transforming...",
      "post_url": "https://x.com/ai_researcher/status/123"
    },
    {
      "timestamp": "2025-11-02T10:35:00",
      "action": "commented",
      "post_author": "@ml_engineer",
      "comment_text": "Great insights! How do you handle...",
      "post_url": "https://x.com/ml_engineer/status/456"
    }
  ],
  "daily_stats": {
    "likes": 15,
    "comments": 3,
    "follows": 2,
    "posts": 1
  }
}
```

**Prevents:**
- Re-engaging with same posts
- Exceeding daily limits (rate limits)
- Spam-like behavior

## 🎨 Writing Style Learning

The agent learns YOUR writing style:

1. **Import your past posts** (via extension)
2. **Analyze patterns:**
   - Tone (casual, professional, humorous)
   - Vocabulary (technical terms, emojis)
   - Sentence structure (short, long, varied)
   - Common phrases
3. **Generate content** that sounds like YOU

**Example:**
```
Your past posts:
- "Just shipped a new feature 🚀"
- "Hot take: AI agents > traditional automation"
- "Building in public is underrated"

Generated post:
"Just launched our X growth agent 🚀 Hot take: 
automated engagement > manual grinding. Building 
this in public has been wild!"

→ Matches your style: emoji usage, "hot take" 
   phrase, casual tone, excitement
```

## 🚦 Rate Limits & Safety

**Built-in limits:**
- Max 50 likes per day
- Max 20 comments per day
- Max 30 follows per day
- Check rate limit status before each action
- Pause if rate limited

**Quality over quantity:**
- Only engage with high-quality posts (score > 70)
- Only engage with reputable accounts (score > 60)
- Only comment when you can add value
- Avoid spam patterns

## 📊 Monitoring

**Watch the agent work:**
1. **VNC Viewer** (http://localhost:5900)
   - See the browser in real-time
   - Watch clicks, typing, scrolling
   - Visual confirmation of actions

2. **LangGraph Studio** (http://localhost:8123)
   - See agent reasoning
   - View subagent calls
   - Track progress through workflow

3. **Dashboard** (http://localhost:3000)
   - Connection status
   - Recent activity feed
   - Import posts feature

## 🎯 Best Practices

1. **Start small:** Run engagement workflow once per day
2. **Review results:** Check what the agent did
3. **Adjust parameters:** Tweak keywords, limits
4. **Learn from data:** See what works, iterate
5. **Stay authentic:** Agent uses YOUR voice
6. **Monitor quality:** Ensure high-quality engagement
7. **Respect limits:** Don't exceed rate limits

## 🔧 Customization

**Customize workflows:**
```python
from x_growth_workflows import Workflow, WorkflowStep

custom_workflow = Workflow(
    name="custom_engagement",
    goal="Your custom goal",
    steps=[
        WorkflowStep(
            subagent="navigate",
            action="Go to custom URL",
            description="Custom step"
        ),
        # ... more steps
    ]
)
```

**Customize principles:**
```python
from x_growth_principles import ACCOUNT_QUALITY_SCORING

# Adjust scoring thresholds
ACCOUNT_QUALITY_SCORING["min_followers"] = 1000
ACCOUNT_QUALITY_SCORING["max_followers"] = 100000
```

## 🎉 Example Session

```bash
# 1. Start everything
./START_COMPLETE_SYSTEM.sh

# 2. Open browser, install extension, login to X
# Extension auto-connects and sends cookies

# 3. Open LangGraph Studio
# http://localhost:8123

# 4. Run engagement workflow
{
  "messages": [
    {
      "role": "user",
      "content": "Engage with trending AI posts"
    }
  ]
}

# 5. Watch in VNC viewer
# http://localhost:5900

# 6. Results:
# - 5 posts liked
# - 2 thoughtful comments posted
# - Memory updated
# - No duplicates
# - All within rate limits
```

## 🚀 Ready to Grow!

The agent is now configured and ready to use. Start with the engagement 
workflow and watch your X account grow authentically! 🎯

