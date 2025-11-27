# 🚀 Quick Start: X Growth Workflows

## **What You Have Now**

Instead of telling the agent "engage with posts" and hoping it figures it out, you now have **5 pre-defined workflows** that execute deterministic sequences of actions.

---

## 📋 **Available Workflows**

| Workflow | Goal | Steps | Use Case |
|----------|------|-------|----------|
| `engagement` | Like + comment on posts | 17 | Daily engagement routine |
| `reply_to_thread` | Reply to viral thread comments | 11 | Join trending conversations |
| `profile_engagement` | Engage with specific user | 7 | Build relationships |
| `content_posting` | Post original content | 6 | Share insights |
| `dm_outreach` | Send personalized DMs | 7 | Network building |

---

## 🎯 **How to Use**

### **1. Install Dependencies**
```bash
pip install deepagents
export ANTHROPIC_API_KEY="your-key-here"
```

### **2. Start Docker Browser**
```bash
cd /home/rajathdb/cua
./build_stealth_docker.sh
docker run -d -p 8005:8005 -p 5900:5900 --name cua-browser stealth-cua:latest
```

### **3. Run a Workflow**
```python
from x_growth_deep_agent import run_workflow

# Engagement: Like + comment on AI posts
result = run_workflow(
    "engagement",
    keywords="AI agents",
    num_likes=5,
    num_comments=2
)
```

---

## 🎬 **Example Workflows**

### **Engagement Workflow**
```python
# Find and engage with posts about LangChain
run_workflow(
    "engagement",
    keywords="LangChain",
    num_likes=10,
    num_comments=3
)
```

**What happens:**
1. ✅ Navigate to X search
2. ✅ Search for "LangChain"
3. ✅ Take screenshots to see posts
4. ✅ Scroll to load more
5. ✅ Check memory (avoid duplicates)
6. ✅ Like 10 posts
7. ✅ Comment on 3 best posts
8. ✅ Update memory

---

### **Reply to Thread Workflow**
```python
# Join a viral AI discussion
run_workflow(
    "reply_to_thread",
    thread_url="https://x.com/sama/status/123456789"
)
```

**What happens:**
1. ✅ Navigate to thread
2. ✅ Screenshot to see replies
3. ✅ Scroll through comments
4. ✅ Check memory (avoid duplicates)
5. ✅ Reply to 3 interesting comments
6. ✅ Update memory

---

### **Profile Engagement Workflow**
```python
# Engage with Elon Musk's recent posts
run_workflow(
    "profile_engagement",
    target_user="@elonmusk"
)
```

**What happens:**
1. ✅ Navigate to @elonmusk profile
2. ✅ Check memory (engaged before?)
3. ✅ Screenshot recent posts
4. ✅ Like 2 best posts
5. ✅ Comment on 1 post
6. ✅ Update memory

---

### **Content Posting Workflow**
```python
# Post about AI agents
run_workflow(
    "content_posting",
    post_topic="The future of AI agents",
    tone="insightful"
)
```

**What happens:**
1. ✅ Navigate to home
2. ✅ Click compose box
3. ✅ LLM generates post content
4. ✅ Type post
5. ✅ Screenshot to verify
6. ✅ Click Post button
7. ✅ Update memory

---

### **DM Outreach Workflow**
```python
# Send DM to potential collaborator
run_workflow(
    "dm_outreach",
    target_user="@sama",
    message_context="AI safety collaboration"
)
```

**What happens:**
1. ✅ Navigate to @sama profile
2. ✅ Check memory (already DM'd?)
3. ✅ Screenshot for personalization
4. ✅ Click Message button
5. ✅ LLM generates personalized DM
6. ✅ Type DM
7. ✅ Send
8. ✅ Update memory

---

## 🔄 **Daily Routine Example**

```python
# Morning: Engage with AI community
run_workflow("engagement", keywords="AI agents", num_likes=10, num_comments=3)

# Midday: Join trending discussion
run_workflow("reply_to_thread", thread_url="<viral_thread_url>")

# Afternoon: Build relationship with key account
run_workflow("profile_engagement", target_user="@karpathy")

# Evening: Share your insights
run_workflow("content_posting", post_topic="Today's AI learnings", tone="casual")
```

---

## 📊 **Memory System**

### **Automatic Tracking**
Every action is saved to `action_history.json`:

```json
{
  "date": "2025-11-01",
  "actions": [
    {
      "timestamp": "2025-11-01T10:30:00",
      "workflow": "engagement",
      "action": "liked",
      "post_author": "@username",
      "post_url": "https://x.com/username/status/123"
    }
  ],
  "daily_stats": {
    "likes": 15,
    "comments": 3,
    "dms": 1
  }
}
```

### **Duplicate Prevention**
- ✅ Never like same post twice
- ✅ Never comment on same post twice
- ✅ Never DM same user twice in 24h

### **Rate Limiting**
- ✅ Max 50 likes/day
- ✅ Max 20 comments/day
- ✅ Max 10 DMs/day

---

## 🎯 **Workflow Customization**

### **Modify Existing Workflow**
```python
from x_growth_workflows import ENGAGEMENT_WORKFLOW

# Change number of likes
ENGAGEMENT_WORKFLOW.steps[7].action = "Like 15 posts instead of 5"
```

### **Create New Workflow**
```python
from x_growth_workflows import Workflow, WorkflowStep, WORKFLOWS

# Define custom workflow
my_workflow = Workflow(
    name="morning_routine",
    goal="Check notifications and respond",
    steps=[
        WorkflowStep(
            subagent="navigate",
            action="Go to notifications",
            description="Check notifications"
        ),
        WorkflowStep(
            subagent="screenshot",
            action="See notifications",
            description="Capture notifications"
        ),
        # ... more steps
    ]
)

# Add to registry
WORKFLOWS["morning_routine"] = my_workflow

# Use it
run_workflow("morning_routine")
```

---

## 🚨 **Safety Features**

### **Built-in Protections**
- ✅ Memory checks before every action
- ✅ Rate limiting enforced
- ✅ Duplicate prevention
- ✅ Retry logic for failures
- ✅ Graceful error handling

### **Manual Override**
```python
# Check memory manually
from x_growth_deep_agent import read_file
memory = read_file("action_history.json")
print(memory)

# Clear memory (start fresh)
from x_growth_deep_agent import write_file
write_file("action_history.json", "{}")
```

---

## 📈 **Monitoring**

### **VNC Viewer**
Watch the agent in real-time:
1. Open browser: `http://localhost:3000`
2. Click "Show Browser" on dashboard
3. Watch agent execute workflow steps

### **Logs**
```bash
# Watch agent logs
tail -f agent.log

# Watch Docker logs
docker logs -f cua-browser
```

---

## 🎓 **Best Practices**

### **1. Start Small**
```python
# Start with 5 likes, not 50
run_workflow("engagement", keywords="AI", num_likes=5, num_comments=1)
```

### **2. Vary Your Activity**
```python
# Don't just like - comment and engage
run_workflow("engagement", num_likes=5, num_comments=3)
run_workflow("reply_to_thread", thread_url="...")
```

### **3. Target Niche Topics**
```python
# Specific keywords get better engagement
run_workflow("engagement", keywords="LangGraph agents", num_likes=10)
# Better than generic "AI"
```

### **4. Engage with Mid-Tier Accounts**
```python
# 500-50k followers = sweet spot
run_workflow("profile_engagement", target_user="@mid_tier_account")
# More likely to respond than mega-influencers
```

### **5. Post Consistently**
```python
# Daily posting builds presence
run_workflow("content_posting", post_topic="Daily AI insight", tone="casual")
```

---

## 🐛 **Troubleshooting**

### **Issue: "Docker browser not accessible"**
```bash
# Check if Docker is running
docker ps

# Restart Docker
docker restart cua-browser

# Check logs
docker logs cua-browser
```

### **Issue: "ANTHROPIC_API_KEY not set"**
```bash
export ANTHROPIC_API_KEY="your-key-here"
```

### **Issue: "Workflow failed at step X"**
- Check VNC viewer to see what's on screen
- Check `action_history.json` for recent actions
- Retry workflow (it will skip completed steps)

---

## 🎉 **You're Ready!**

**You now have:**
- ✅ 5 pre-defined workflows
- ✅ Deterministic execution
- ✅ Automatic memory tracking
- ✅ Rate limiting & safety
- ✅ Real-time monitoring

**Start with:**
```python
from x_growth_deep_agent import run_workflow

# Your first workflow
run_workflow("engagement", keywords="AI agents", num_likes=5, num_comments=2)
```

**Watch it work in VNC viewer at `http://localhost:3000`**

🚀 **Happy growing!**

