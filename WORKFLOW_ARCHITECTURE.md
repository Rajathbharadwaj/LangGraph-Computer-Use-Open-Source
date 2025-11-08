# 🎯 X Growth Agent - Workflow-Based Architecture

## **Core Principle: Deterministic Workflows + Atomic Actions**

Instead of giving the agent vague instructions, we define **5 pre-determined workflows** for specific goals. Each workflow is a sequence of atomic actions that the DeepAgent orchestrates.

---

## 🏗️ **Architecture**

```
USER: "Run engagement workflow for AI agents"
    ↓
DEEPAGENT: Receives workflow with pre-defined steps
    ↓
DEEPAGENT: Executes steps IN ORDER by delegating to subagents
    ↓
    ├─ Step 1: task("navigate", "Go to X search")
    ├─ Step 2: task("screenshot", "See page")
    ├─ Step 3: task("type_text", "Type 'AI agents'")
    ├─ Step 4: task("click", "Click search")
    ├─ Step 5: task("screenshot", "See results")
    ├─ Step 6: task("scroll", "Load more posts")
    ├─ Step 7: task("screenshot", "See more posts")
    ├─ Step 8: Read action_history.json (check memory)
    ├─ Step 9: task("like_post", "Like post #1")
    ├─ Step 10: Write to action_history.json
    ├─ Step 11: task("like_post", "Like post #2")
    └─ ... (repeat for all workflow steps)
    ↓
DEEPAGENT: Workflow complete!
```

---

## 📋 **5 Pre-Defined Workflows**

### **1. Engagement Workflow**
**Goal**: Find and engage with posts (likes + comments)

**Steps** (17 total):
1. Navigate to X search
2. Screenshot
3. Type search keywords
4. Click search
5. Screenshot results
6. Scroll to load more
7. Screenshot (check memory)
8-12. Like 5 posts (check + update memory each time)
13-14. Comment on 2 best posts (check + update memory)

**Usage**:
```python
run_workflow("engagement", keywords="AI agents", num_likes=5, num_comments=2)
```

---

### **2. Reply to Thread Workflow**
**Goal**: Find viral thread and reply to comments

**Steps** (11 total):
1. Navigate to home feed
2. Screenshot
3. Scroll to find viral threads
4. Screenshot viral thread
5. Click to open thread
6. Screenshot replies
7. Scroll through replies
8. Screenshot interesting replies (check memory)
9-11. Reply to 3 comments (check + update memory)

**Usage**:
```python
run_workflow("reply_to_thread", thread_url="https://x.com/user/status/123")
```

---

### **3. Profile Engagement Workflow**
**Goal**: Engage with specific user's content

**Steps** (7 total):
1. Navigate to user's profile
2. Screenshot (check memory - have we engaged before?)
3. Scroll to see recent posts
4. Screenshot recent posts
5-6. Like 2 best posts (check + update memory)
7. Comment on best post (check + update memory)

**Usage**:
```python
run_workflow("profile_engagement", target_user="@elonmusk")
```

---

### **4. Content Posting Workflow**
**Goal**: Create and post original content

**Steps** (6 total):
1. Navigate to home
2. Screenshot
3. Click compose box
4. Type post content (LLM-generated)
5. Screenshot to verify
6. Click Post button (update memory)

**Usage**:
```python
run_workflow("content_posting", post_topic="AI agents", tone="insightful")
```

---

### **5. DM Outreach Workflow**
**Goal**: Send personalized DMs

**Steps** (7 total):
1. Navigate to target profile (check memory - already DM'd?)
2. Screenshot for personalization
3. Click Message button
4. Screenshot DM composer
5. Type personalized DM
6. Screenshot to verify
7. Click Send (update memory)

**Usage**:
```python
run_workflow("dm_outreach", target_user="@sama", message_context="AI safety")
```

---

## 🧩 **How It Works**

### **1. Workflow Definition** (`x_growth_workflows.py`)
```python
ENGAGEMENT_WORKFLOW = Workflow(
    name="engagement_workflow",
    goal="Find relevant posts and engage",
    steps=[
        WorkflowStep(
            subagent="navigate",
            action="Go to https://x.com/search",
            description="Navigate to X search page"
        ),
        WorkflowStep(
            subagent="screenshot",
            action="Take screenshot",
            description="Capture search page"
        ),
        # ... more steps
        WorkflowStep(
            subagent="like_post",
            action="Like first relevant post",
            description="Like post #1",
            check_memory=True,  # Check action_history.json first
            update_memory=True  # Update after action
        ),
    ]
)
```

### **2. DeepAgent Execution** (`x_growth_deep_agent.py`)
```python
# User runs workflow
result = run_workflow("engagement", keywords="AI agents")

# DeepAgent receives workflow prompt with steps
# DeepAgent executes steps IN ORDER:
for step in workflow.steps:
    # Delegate to subagent
    result = task(step.subagent, step.action)
    
    # Check memory if needed
    if step.check_memory:
        memory = read_file("action_history.json")
    
    # Update memory if needed
    if step.update_memory:
        write_file("action_history.json", new_action)
```

### **3. Atomic Subagents** (Execute ONE action)
```python
# Each subagent does ONE thing
task("navigate", "Go to X search")  # Returns immediately
task("screenshot", "See page")      # Returns immediately
task("like_post", "Like @user1")    # Returns immediately
```

---

## ✅ **Benefits**

### **1. Deterministic**
- ✅ Pre-defined steps (no guessing)
- ✅ Predictable execution
- ✅ Easy to debug
- ✅ Easy to test

### **2. Reliable**
- ✅ Agent can't "overthink" or skip steps
- ✅ Memory checks built-in (no duplicates)
- ✅ Rate limiting enforced
- ✅ Fallback logic for failures

### **3. Scalable**
- ✅ Easy to add new workflows
- ✅ Easy to modify existing workflows
- ✅ Workflows can be versioned
- ✅ A/B testing different workflows

### **4. Observable**
- ✅ See exactly which step is executing
- ✅ VNC viewer shows actions in real-time
- ✅ Logs show decision process
- ✅ Memory shows history

---

## 🚀 **Usage**

### **Basic Usage**
```python
from x_growth_deep_agent import run_workflow

# Run engagement workflow
result = run_workflow(
    "engagement",
    keywords="AI agents",
    num_likes=5,
    num_comments=2
)
```

### **List Available Workflows**
```python
from x_growth_workflows import list_workflows, WORKFLOWS

# List all workflows
workflows = list_workflows()
# ['engagement', 'reply_to_thread', 'profile_engagement', 'content_posting', 'dm_outreach']

# Get workflow details
for name, workflow in WORKFLOWS.items():
    print(f"{name}: {workflow.goal} ({len(workflow.steps)} steps)")
```

### **Custom Workflow**
```python
from x_growth_workflows import Workflow, WorkflowStep

# Define custom workflow
my_workflow = Workflow(
    name="custom_workflow",
    goal="My custom goal",
    steps=[
        WorkflowStep(
            subagent="navigate",
            action="Go to URL",
            description="Navigate"
        ),
        # ... more steps
    ]
)

# Add to registry
WORKFLOWS["custom"] = my_workflow
```

---

## 📊 **Memory System**

### **action_history.json Format**
```json
{
  "date": "2025-11-01",
  "actions": [
    {
      "timestamp": "2025-11-01T10:30:00",
      "workflow": "engagement",
      "action": "liked",
      "post_author": "@username",
      "post_content_snippet": "AI agents are...",
      "post_url": "https://x.com/username/status/123"
    },
    {
      "timestamp": "2025-11-01T10:35:00",
      "workflow": "engagement",
      "action": "commented",
      "post_author": "@username",
      "comment_text": "Great insight!",
      "post_url": "https://x.com/username/status/456"
    }
  ],
  "daily_stats": {
    "likes": 15,
    "comments": 3,
    "dms": 1,
    "posts": 2
  }
}
```

### **Memory Checks**
- **Before engaging**: Check if post/user already engaged with
- **Rate limiting**: Check daily limits (50 likes, 20 comments, 10 DMs)
- **After engaging**: Update memory with new action

---

## 🔄 **Workflow Execution Flow**

```
1. USER: "Run engagement workflow"
    ↓
2. SYSTEM: Get workflow from registry
    ↓
3. SYSTEM: Generate workflow prompt with steps
    ↓
4. DEEPAGENT: Receives prompt
    ↓
5. DEEPAGENT: Creates todos from workflow steps
    ↓
6. DEEPAGENT: For each step:
    ├─ Read action_history.json (if check_memory=True)
    ├─ Delegate to subagent via task()
    ├─ Wait for result
    ├─ Analyze result
    ├─ Update action_history.json (if update_memory=True)
    └─ Mark step complete
    ↓
7. DEEPAGENT: All steps complete
    ↓
8. SYSTEM: Return result to user
```

---

## 🎯 **Example: Engagement Workflow Execution**

### **User Input**:
```python
run_workflow("engagement", keywords="AI agents", num_likes=5, num_comments=2)
```

### **DeepAgent Receives**:
```
WORKFLOW: engagement_workflow
GOAL: Find relevant posts and engage

STEPS:
1. Navigate to X search → task('navigate', 'Go to https://x.com/search')
2. Screenshot → task('screenshot', 'See page')
3. Type search → task('type_text', 'Type AI agents')
4. Click search → task('click', 'Click search button')
5. Screenshot → task('screenshot', 'See results')
6. Scroll → task('scroll', 'Scroll down')
7. Screenshot → task('screenshot', 'See more posts') [CHECK MEMORY]
8. Like post #1 → task('like_post', 'Like @user1') [CHECK + UPDATE MEMORY]
9. Like post #2 → task('like_post', 'Like @user2') [CHECK + UPDATE MEMORY]
... (repeat for all steps)
```

### **DeepAgent Executes**:
```
✅ Step 1: task("navigate", "Go to https://x.com/search")
   → Subagent "navigate" executes navigate_to_url()
   → Returns: "Successfully navigated"

✅ Step 2: task("screenshot", "See page")
   → Subagent "screenshot" executes take_browser_screenshot()
   → Returns: [screenshot image]

✅ Step 3: task("type_text", "Type 'AI agents'")
   → Subagent "type_text" executes type_text("AI agents")
   → Returns: "Successfully typed"

... (continues for all steps)

✅ Step 8: task("like_post", "Like @user1")
   → First: read_file("action_history.json")
   → Check: Have we liked @user1 before? No
   → Subagent "like_post" executes like_post("@user1")
   → Returns: "Successfully liked"
   → Then: write_file("action_history.json", new_action)

✅ Workflow complete!
```

---

## 🚨 **Safety & Rate Limits**

### **Built-in Limits**:
- **Likes**: Max 50 per day
- **Comments**: Max 20 per day
- **DMs**: Max 10 per day
- **Posts**: Max 5 per day

### **Duplicate Prevention**:
- Check `action_history.json` before each engagement
- Never engage with same post/user twice in 24 hours

### **Failure Handling**:
- If step fails, retry ONCE
- If still fails, log error and continue to next step
- Workflow continues even if some steps fail

---

## 📈 **Next Steps**

1. ✅ **Test workflows**: `python3 x_growth_deep_agent.py`
2. ✅ **Add to dashboard**: Frontend controls for workflows
3. ✅ **Monitor execution**: Watch via VNC viewer
4. ✅ **Iterate**: Adjust workflows based on results
5. ✅ **Scale**: Add more workflows as needed

---

## 🎉 **Summary**

**You now have:**
- ✅ 5 pre-defined workflows for common goals
- ✅ Deterministic execution (no guessing)
- ✅ Atomic actions (one at a time)
- ✅ Memory system (no duplicates)
- ✅ Rate limiting (stay safe)
- ✅ Observable (VNC + logs)

**This is WAY better than:**
- ❌ Vague instructions ("engage with posts")
- ❌ Agent figuring it out on the fly
- ❌ No memory (duplicate engagement)
- ❌ No structure (unpredictable)

🚀 **Ready to grow X accounts reliably!**

