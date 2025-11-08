# X Growth Agent - Atomic Action Architecture

## 🎯 **Core Principle**

**DeepAgent delegates atomic actions. Subagents execute ONE action and return.**

---

## 🏗️ **Architecture Overview**

```
┌─────────────────────────────────────────────────────────────┐
│                    MAIN DEEP AGENT                          │
│                 (Strategic Orchestrator)                    │
│                                                             │
│  Role: Plan, delegate, track memory                        │
│  Tools: write_todos, read_file, write_file, task()        │
│  NEVER executes Playwright actions directly                │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ delegates via task()
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   ATOMIC SUBAGENTS                          │
│              (One action, immediate return)                 │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │  navigate    │  │  screenshot  │  │  type_text   │    │
│  │              │  │              │  │              │    │
│  │ Tool:        │  │ Tool:        │  │ Tool:        │    │
│  │ navigate_to  │  │ take_        │  │ type_text    │    │
│  │ _url         │  │ screenshot   │  │              │    │
│  └──────────────┘  └──────────────┘  └──────────────┘    │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │    click     │  │    scroll    │  │  like_post   │    │
│  │              │  │              │  │              │    │
│  │ Tool:        │  │ Tool:        │  │ Tool:        │    │
│  │ click_at_    │  │ scroll_page  │  │ like_post    │    │
│  │ coordinates  │  │              │  │              │    │
│  └──────────────┘  └──────────────┘  └──────────────┘    │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐                       │
│  │ comment_on   │  │   enter_     │                       │
│  │    _post     │  │ credentials  │                       │
│  │              │  │              │                       │
│  │ Tool:        │  │ Tools:       │                       │
│  │ comment_on   │  │ enter_       │                       │
│  │ _post        │  │ username,    │                       │
│  │              │  │ password     │                       │
│  └──────────────┘  └──────────────┘                       │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔄 **Execution Flow**

### **Example: "Engage with 5 AI posts"**

```
USER REQUEST
    ↓
MAIN AGENT: Plans strategy
    ├─ write_todos: Create task list
    ├─ read_file: Check action_history.json
    └─ Decides: Need to search for AI posts
    ↓
MAIN AGENT: task("navigate", "Go to https://x.com/search")
    ↓
SUBAGENT "navigate": 
    ├─ Calls navigate_to_url("https://x.com/search")
    ├─ Returns: "✅ Navigated successfully"
    └─ EXITS
    ↓
MAIN AGENT: Receives result, decides next action
    ↓
MAIN AGENT: task("screenshot", "See the page")
    ↓
SUBAGENT "screenshot":
    ├─ Calls take_browser_screenshot()
    ├─ Returns: [screenshot image]
    └─ EXITS
    ↓
MAIN AGENT: Analyzes screenshot, sees search box
    ↓
MAIN AGENT: task("type_text", "Type 'AI agents' in search")
    ↓
SUBAGENT "type_text":
    ├─ Calls type_text("AI agents")
    ├─ Returns: "✅ Typed successfully"
    └─ EXITS
    ↓
MAIN AGENT: task("click", "Click search button at (500, 300)")
    ↓
SUBAGENT "click":
    ├─ Calls click_at_coordinates(500, 300)
    ├─ Returns: "✅ Clicked successfully"
    └─ EXITS
    ↓
MAIN AGENT: task("screenshot", "See search results")
    ↓
SUBAGENT "screenshot":
    ├─ Calls take_browser_screenshot()
    ├─ Returns: [screenshot with posts]
    └─ EXITS
    ↓
MAIN AGENT: Analyzes screenshot, identifies posts
    ├─ Checks action_history.json
    └─ Decides: Like post by @user1
    ↓
MAIN AGENT: task("like_post", "Like post by @user1 about AI")
    ↓
SUBAGENT "like_post":
    ├─ Calls like_post("@user1")
    ├─ Returns: "✅ Liked post by @user1"
    └─ EXITS
    ↓
MAIN AGENT: Updates memory
    ├─ write_file: Add to action_history.json
    │   {
    │     "timestamp": "2025-11-01T10:30:00",
    │     "action": "liked",
    │     "post_author": "@user1",
    │     "post_url": "..."
    │   }
    └─ Updates todos: [✓] Like post 1
    ↓
MAIN AGENT: Repeats for 4 more posts
    ↓
DONE
```

---

## 🧩 **Atomic Subagents**

### **1. navigate**
- **Purpose**: Go to a URL
- **Tool**: `navigate_to_url`
- **Returns**: Success/failure
- **Example**: `task("navigate", "Go to https://x.com/search")`

### **2. screenshot**
- **Purpose**: Capture current page state
- **Tool**: `take_browser_screenshot`
- **Returns**: Screenshot image
- **Example**: `task("screenshot", "See what's on the page")`

### **3. type_text**
- **Purpose**: Type into an input field
- **Tool**: `type_text`
- **Returns**: Success/failure
- **Example**: `task("type_text", "Type 'AI agents' in search box")`

### **4. click**
- **Purpose**: Click at coordinates
- **Tool**: `click_at_coordinates`
- **Returns**: Success/failure
- **Example**: `task("click", "Click search button at (500, 300)")`

### **5. scroll**
- **Purpose**: Scroll page
- **Tool**: `scroll_page`
- **Returns**: Success/failure
- **Example**: `task("scroll", "Scroll down 500px")`

### **6. like_post**
- **Purpose**: Like ONE post
- **Tool**: `like_post`
- **Returns**: Success/failure
- **Example**: `task("like_post", "Like post by @username about AI")`

### **7. comment_on_post**
- **Purpose**: Comment on ONE post
- **Tool**: `comment_on_post`
- **Returns**: Success/failure
- **Example**: `task("comment_on_post", "Comment 'Great insight!' on @user's post")`

### **8. enter_credentials**
- **Purpose**: Enter username/password
- **Tools**: `enter_username`, `enter_password`
- **Returns**: Success/failure
- **Example**: `task("enter_credentials", "Enter username")`

---

## 🧠 **Main Agent Responsibilities**

### **1. Strategic Planning**
```python
# Main agent uses write_todos
TODO:
[ ] Navigate to X search
[ ] Search for "AI agents"
[ ] Like 5 relevant posts
[ ] Comment on 2 best posts
[ ] Update memory
```

### **2. Memory Management**
```python
# Main agent reads/writes action_history.json
{
  "date": "2025-11-01",
  "actions": [
    {
      "timestamp": "2025-11-01T10:30:00",
      "action": "liked",
      "post_author": "@username",
      "post_content_snippet": "AI agents are...",
      "post_url": "https://x.com/username/status/123"
    }
  ],
  "daily_stats": {
    "likes": 15,
    "comments": 3
  }
}
```

### **3. Decision Making**
- Analyzes screenshots to decide next action
- Checks memory to avoid duplicates
- Adapts strategy based on results
- Enforces rate limits

### **4. Delegation**
- Calls subagents ONE at a time
- Waits for result
- Analyzes result
- Decides next action

---

## 🚨 **Critical Rules**

### **For Main Agent:**
1. ✅ **ALWAYS** check `action_history.json` before engaging
2. ✅ **ALWAYS** take screenshot before deciding on action
3. ✅ **ALWAYS** delegate ONE atomic action at a time
4. ✅ **ALWAYS** wait for subagent result before next action
5. ✅ **ALWAYS** update memory after each engagement
6. ❌ **NEVER** execute Playwright actions directly
7. ❌ **NEVER** engage with same post/user twice in 24h
8. ❌ **NEVER** exceed rate limits (50 likes, 20 comments per day)

### **For Subagents:**
1. ✅ **EXECUTE** the ONE action assigned
2. ✅ **RETURN** result immediately
3. ❌ **NEVER** do multiple actions
4. ❌ **NEVER** make decisions (main agent decides)

---

## 📊 **Rate Limits & Safety**

```python
DAILY_LIMITS = {
    "likes": 50,
    "comments": 20,
    "follows": 10,
    "profile_visits": 100
}

ENGAGEMENT_RULES = {
    "min_time_between_actions": 30,  # seconds
    "no_duplicate_engagement": True,
    "quality_over_quantity": True,
    "authentic_comments_only": True
}
```

---

## 🎯 **Quality Guidelines**

### **What to Like:**
- ✅ Thoughtful posts in your niche
- ✅ Posts with <1000 likes (higher visibility)
- ✅ Posts from accounts with 500-50k followers
- ✅ Posts within 1 hour of posting

### **What to Comment:**
- ✅ Value-add insights
- ✅ Thoughtful questions
- ✅ Personal experiences
- ❌ NOT: "Great post!", "Nice!", "👍"

### **What to Avoid:**
- ❌ Spam
- ❌ Generic comments
- ❌ Controversial topics
- ❌ Engagement bait

---

## 🚀 **Usage**

```python
from x_growth_deep_agent import create_x_growth_agent

# Create agent
agent = create_x_growth_agent()

# Run engagement task
result = agent.invoke({
    "messages": [
        "Engage with 10 posts about AI agents. "
        "Focus on thoughtful posts. "
        "Comment on the 3 best ones."
    ]
})
```

---

## 🔄 **Integration with Existing System**

### **1. Cookie Transfer (Already Built)**
- User logs in via Chrome extension
- Cookies transferred to Docker browser
- Agent uses authenticated session

### **2. VNC Viewer (Already Built)**
- User can watch agent in real-time
- Displayed on Next.js dashboard

### **3. WebSocket (Already Built)**
- Real-time updates to frontend
- Agent status and progress

### **4. NEW: DeepAgent Layer**
- Wraps existing Playwright tools
- Adds strategic planning
- Adds memory management
- Adds atomic action delegation

---

## 📈 **Benefits**

### **1. Atomic Actions**
- Each action is indivisible
- Easy to debug
- Easy to retry on failure
- Clear execution trace

### **2. Strategic Planning**
- Agent thinks before acting
- Adapts to results
- Learns from history

### **3. Memory**
- Never duplicates engagement
- Tracks daily stats
- Learns what works

### **4. Safety**
- Rate limiting built-in
- Quality checks
- Authentic engagement only

### **5. Observability**
- VNC viewer shows actions
- Logs show decision process
- Memory shows history

---

## 🎬 **Next Steps**

1. ✅ Install DeepAgents: `pip install deepagents`
2. ✅ Test with existing Playwright tools
3. ✅ Integrate with cookie transfer system
4. ✅ Add frontend controls for agent tasks
5. ✅ Monitor and iterate

---

**This architecture gives you:**
- ✅ Atomic, testable actions
- ✅ Strategic planning
- ✅ Memory and learning
- ✅ Safety and rate limiting
- ✅ Full observability
- ✅ Uses your existing tools!

🚀 **Ready to grow X accounts at scale!**

