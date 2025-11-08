# 💾 User-Specific Long-Term Memory Guide

## **Overview**

The X Growth Agent now supports **user-specific long-term memory** using LangGraph Store with namespaces. This enables:
- ✅ **Personalized preferences** per user
- ✅ **Engagement history** that persists across sessions
- ✅ **Learning** what works for each user
- ✅ **Cached account research** for efficiency

---

## 🏗️ **Architecture**

### **Memory Namespaces**

Each user gets their own namespace for different types of data:

```
(user_id, "preferences")        → User settings
(user_id, "engagement_history")  → Past engagements
(user_id, "learnings")           → What works
(user_id, "account_profiles")    → Cached account research
```

### **Storage Backends**

```python
# Development: In-Memory Store
from langgraph.store.memory import InMemoryStore
store = InMemoryStore()

# Production: PostgreSQL Store
from langgraph.store.postgres import PostgresStore
store = PostgresStore(connection_string=os.environ["DATABASE_URL"])
```

---

## 📊 **Memory Types**

### **1. User Preferences**

```python
@dataclass
class UserPreferences:
    user_id: str
    niche: List[str]  # ["AI", "LangChain", "agents"]
    target_audience: str  # "AI/ML practitioners"
    growth_goal: str  # "build authority"
    engagement_style: str  # "thoughtful_expert"
    tone: str  # "professional"
    daily_limits: Dict[str, int]  # {"likes": 50, "comments": 20}
    optimal_times: List[str]  # ["9-11am EST", "7-9pm EST"]
    avoid_topics: List[str]  # ["politics", "religion"]
```

**Usage:**
```python
# Save preferences
preferences = UserPreferences(
    user_id="user_123",
    niche=["AI", "LangChain"],
    target_audience="AI/ML practitioners",
    growth_goal="build authority",
    engagement_style="thoughtful_expert",
    tone="professional",
    daily_limits={"likes": 50, "comments": 20},
    optimal_times=["9-11am EST", "7-9pm EST"],
    avoid_topics=["politics"]
)
user_memory.save_preferences(preferences)

# Get preferences
prefs = user_memory.get_preferences()
```

---

### **2. Engagement History**

```python
@dataclass
class EngagementMemory:
    memory_id: str
    timestamp: str
    action: str  # "liked", "commented", "followed", "dm"
    target_username: str
    target_post_id: Optional[str]
    target_post_url: Optional[str]
    comment_text: Optional[str]
    result: str  # "success", "failed"
    engagement_received: Optional[int]  # likes/replies received
```

**Usage:**
```python
# Save engagement
engagement = EngagementMemory(
    memory_id=str(uuid.uuid4()),
    timestamp=datetime.now().isoformat(),
    action="commented",
    target_username="ai_researcher",
    target_post_id="123456",
    target_post_url="https://x.com/ai_researcher/status/123456",
    comment_text="Great insight!",
    result="success",
    engagement_received=5
)
user_memory.save_engagement(engagement)

# Check if already engaged
already_engaged = user_memory.check_already_engaged("ai_researcher", "123456")

# Get engagement history
history = user_memory.get_engagement_history(limit=100, action="commented")

# Get daily stats
stats = user_memory.get_daily_stats()  # {"likes": 15, "comments": 3, ...}
```

---

### **3. Account Profiles (Cached Research)**

```python
@dataclass
class AccountProfile:
    username: str
    follower_count: int
    engagement_rate: float
    quality_score: float
    niche_relevance: float
    last_researched: str
    engagement_count: int  # How many times we've engaged
    last_engagement: Optional[str]
    notes: str
```

**Usage:**
```python
# Save account profile
profile = AccountProfile(
    username="ai_researcher",
    follower_count=5000,
    engagement_rate=0.03,
    quality_score=0.85,
    niche_relevance=0.9,
    last_researched=datetime.now().isoformat(),
    engagement_count=1,
    last_engagement=datetime.now().isoformat(),
    notes="High quality AI researcher, very responsive"
)
user_memory.save_account_profile(profile)

# Get cached profile
profile = user_memory.get_account_profile("ai_researcher")

# Update engagement count
user_memory.update_account_engagement("ai_researcher")
```

---

### **4. Learnings (What Works)**

```python
@dataclass
class Learning:
    learning_id: str
    timestamp: str
    category: str  # "engagement_strategy", "comment_style", "timing"
    insight: str  # "Questions get 2x more replies than statements"
    evidence: str  # "10 question comments got 20 replies, ..."
    confidence: float  # 0-1
```

**Usage:**
```python
# Save learning
learning = Learning(
    learning_id=str(uuid.uuid4()),
    timestamp=datetime.now().isoformat(),
    category="comment_style",
    insight="Questions get 2x more replies than statements",
    evidence="10 question comments got 20 replies, 10 statements got 10",
    confidence=0.8
)
user_memory.save_learning(learning)

# Get learnings by category
learnings = user_memory.get_learnings(category="comment_style", min_confidence=0.7)

# Semantic search for learnings
learnings = user_memory.search_learnings("best time to post")
```

---

## 🚀 **Usage Examples**

### **Example 1: Create Agent with User Memory**

```python
from langgraph.store.memory import InMemoryStore
from x_growth_deep_agent import create_x_growth_agent
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

# Create agent with user memory
agent, user_memory = create_x_growth_agent(
    user_id=user_id,
    store=store,
    use_longterm_memory=True
)

# Agent now has access to user preferences and memory!
```

---

### **Example 2: Agent Uses Memory to Avoid Duplicates**

```python
# Before engaging, agent checks memory
already_engaged = user_memory.check_already_engaged("ai_researcher", "123456")

if already_engaged:
    print("⚠️  Already engaged with this post, skipping...")
else:
    # Engage with post
    # ...
    
    # Save engagement to memory
    engagement = EngagementMemory(
        memory_id=str(uuid.uuid4()),
        timestamp=datetime.now().isoformat(),
        action="liked",
        target_username="ai_researcher",
        target_post_id="123456",
        target_post_url="https://x.com/ai_researcher/status/123456",
        result="success"
    )
    user_memory.save_engagement(engagement)
```

---

### **Example 3: Agent Caches Account Research**

```python
# Check if we have cached research
cached_profile = user_memory.get_account_profile("ai_researcher")

if cached_profile:
    # Use cached data (saves time!)
    print(f"Quality Score: {cached_profile.quality_score}")
    print(f"Last researched: {cached_profile.last_researched}")
else:
    # Research account (takes time)
    # ... navigate, screenshot, extract metrics ...
    
    # Cache the research
    profile = AccountProfile(
        username="ai_researcher",
        follower_count=5000,
        engagement_rate=0.03,
        quality_score=0.85,
        niche_relevance=0.9,
        last_researched=datetime.now().isoformat(),
        engagement_count=0,
        last_engagement=None,
        notes="High quality AI researcher"
    )
    user_memory.save_account_profile(profile)
```

---

### **Example 4: Agent Learns What Works**

```python
# After 10 engagements, agent analyzes results
question_comments = [e for e in history if "?" in e.comment_text]
statement_comments = [e for e in history if "?" not in e.comment_text]

question_replies = sum(e.engagement_received for e in question_comments)
statement_replies = sum(e.engagement_received for e in statement_comments)

if question_replies > statement_replies * 1.5:
    # Save learning
    learning = Learning(
        learning_id=str(uuid.uuid4()),
        timestamp=datetime.now().isoformat(),
        category="comment_style",
        insight="Questions get more engagement than statements",
        evidence=f"{len(question_comments)} questions got {question_replies} replies, "
                 f"{len(statement_comments)} statements got {statement_replies} replies",
        confidence=0.8
    )
    user_memory.save_learning(learning)
    
    # Agent will now prefer question-style comments!
```

---

## 🎯 **Integration with DeepAgent**

### **How Agent Accesses Memory**

The DeepAgent accesses long-term memory via the `/memories/` filesystem:

```python
# Agent system prompt includes:
"""
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
"""
```

### **Agent Workflow with Memory**

```
1. User: "Engage with AI posts"
    ↓
2. Agent reads /memories/preferences.txt
    → Sees: Niche = ["AI", "LangChain"]
    → Sees: Daily limits = {"likes": 50, "comments": 20}
    ↓
3. Agent reads /memories/engagement_history/
    → Sees: Already engaged with 15 posts today
    → Sees: Already engaged with @ai_researcher
    ↓
4. Agent reads /memories/learnings/
    → Sees: "Questions get 2x more engagement"
    → Decides: Use question-style comments
    ↓
5. Agent searches for AI posts
    ↓
6. Agent checks /memories/account_profiles/
    → Finds cached profile for @ml_expert
    → Uses cached data (saves time!)
    ↓
7. Agent engages with post
    ↓
8. Agent writes to /memories/engagement_history/
    → Records engagement
    ↓
9. Agent updates /memories/account_profiles/
    → Increments engagement count
```

---

## 📈 **Benefits**

### **1. Personalization**
- ✅ Each user has custom preferences
- ✅ Agent adapts to user's niche and style
- ✅ Respects user's daily limits

### **2. Efficiency**
- ✅ Cached account research (no re-research)
- ✅ Quick duplicate checks
- ✅ Fast daily stats lookup

### **3. Learning**
- ✅ Agent learns what works for each user
- ✅ Improves over time
- ✅ Applies user-specific patterns

### **4. Safety**
- ✅ Never duplicates engagement
- ✅ Respects rate limits
- ✅ Tracks all actions

---

## 🔧 **Production Setup**

### **PostgreSQL Store (Recommended)**

```python
from langgraph.store.postgres import PostgresStore
import os

# Create PostgreSQL store
store = PostgresStore(
    connection_string=os.environ["DATABASE_URL"]
)

# Create agent with persistent store
agent, user_memory = create_x_growth_agent(
    user_id="user_123",
    store=store,
    use_longterm_memory=True
)
```

### **Multi-User SaaS**

```python
# Each user gets their own namespace
users = ["user_123", "user_456", "user_789"]

for user_id in users:
    # Create agent for this user
    agent, user_memory = create_x_growth_agent(
        user_id=user_id,
        store=store,  # Shared store, different namespaces
        use_longterm_memory=True
    )
    
    # Run agent for this user
    result = agent.invoke({
        "messages": ["Grow my X account"]
    })
```

---

## 🎉 **Summary**

**You now have:**
- ✅ User-specific preferences (niche, goals, limits)
- ✅ Persistent engagement history (no duplicates)
- ✅ Cached account research (efficiency)
- ✅ Learning system (improves over time)
- ✅ Namespace isolation (multi-user support)
- ✅ Production-ready (PostgreSQL backend)

**The agent:**
- ✅ Remembers user preferences across sessions
- ✅ Never duplicates engagement
- ✅ Learns what works for each user
- ✅ Caches research for efficiency
- ✅ Scales to multiple users

🚀 **Ready for production SaaS deployment!**

