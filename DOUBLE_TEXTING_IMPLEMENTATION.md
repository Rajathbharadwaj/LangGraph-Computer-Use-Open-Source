# Double-Texting Implementation

## What is Double-Texting?

**Double-texting** is when a user sends a new message before the agent has finished responding to the previous one.

**Example:**
```
User: "Generate 10 post ideas about AI"
Agent: *thinking... generating...*
User: "Actually, just give me 5 ideas about cats" ← DOUBLE-TEXT
→ Agent should stop the first task and start the new one
```

## LangGraph's Built-in Solution

LangGraph provides the `multitask_strategy` parameter for handling concurrent runs:

### **Strategy: `rollback`** (What We Use) ✅
- Stops the previous run
- **DELETES** it completely from the database
- Clean conversation history (no interrupted runs)
- Thread state only includes the new message and response

**From the docs:**
> "The rollback option interrupts the prior run of the graph and starts a new one with the double-text. This option is very similar to the interrupt option, but in this case the first run is completely deleted from the database and cannot be restarted."

**Why `rollback` over `interrupt`?**
- ✅ Cleaner database (no interrupted runs)
- ✅ Simpler conversation history
- ✅ User expects cancelled task to be gone
- ✅ No partial/incomplete responses in history

## Our Implementation

### 1. Detection in `/api/agent/run`

When a new message comes in, we check if there's already a run in progress:

```python
# Check if agent is already running
is_double_texting = user_id in active_runs and not active_runs[user_id].get("cancelled")

if is_double_texting:
    print(f"⚡ Double-texting detected!")
    # Set cancellation flag for old streaming loop
    active_runs[user_id]["cancelled"] = True
```

### 2. Use Rollback Strategy

Pass the `use_rollback` flag to the streaming function:

```python
task_obj = asyncio.create_task(
    stream_agent_execution(user_id, thread_id, task, use_rollback=is_double_texting)
)
```

### 3. LangGraph Handles the Rest

In `stream_agent_execution`, we add `multitask_strategy="rollback"`:

```python
stream_kwargs = {
    "thread_id": thread_id,
    "assistant_id": "x_growth_deep_agent",
    "input": {"messages": [{"role": "user", "content": task}]},
    "stream_mode": "messages"
}

# Add rollback strategy if double-texting
if use_rollback:
    stream_kwargs["multitask_strategy"] = "rollback"

async for chunk in langgraph_client.runs.stream(**stream_kwargs):
    # ... stream tokens ...
```

## Complete Workflow Example

### Scenario: User Double-Texts

```
Time: 0s
User: "Generate 10 post ideas about AI"
→ Backend: Start run-123 on thread-abc
→ Agent: Starts generating...

Time: 2s
Agent: "1. AI-powered content creation\n2. Machine learning..."
→ Frontend: Displays tokens in real-time

Time: 3s
User: "Actually, just give me 5 ideas about cats" ← DOUBLE-TEXT!
→ Backend detects: is_double_texting = True
→ Backend sets: active_runs[user_id]["cancelled"] = True
→ Backend starts: run-456 with multitask_strategy="interrupt"

Time: 3.1s
LangGraph:
  ✅ Stops run-123
  ✅ DELETES run-123 from database completely
  ✅ Starts run-456 with new message

Time: 3.2s
Old streaming loop (run-123):
  → Checks: active_runs[user_id]["cancelled"] == True
  → Breaks out of loop
  → Sends: AGENT_CANCELLED

New streaming loop (run-456):
  → Starts streaming new response
  → "1. Playful cat behavior\n2. Cat nutrition..."

Time: 8s
Agent completes run-456
→ Frontend shows: "1. Playful cat behavior\n2. Cat nutrition\n..."
```

### Database State After Double-Texting

```sql
-- threads table
thread_id: "abc-123"
messages: [
  {role: "user", content: "Generate 10 post ideas about AI"},
  {role: "user", content: "Actually, just give me 5 ideas about cats"},
  {role: "assistant", content: "1. Playful cat behavior\n2. Cat nutrition\n..."}  ← Complete
]

-- runs table
run-123: DELETED ✅ (completely removed by rollback)
run-456: status="success" ✅
```

**Note:** The partial response from run-123 is gone! Only the new conversation remains.

## Key Features

### ✅ Automatic Detection
No special UI needed - just send a new message while agent is running

### ✅ Official LangGraph Feature
Uses `multitask_strategy="interrupt"` from the docs

### ✅ Preserves History
Both the interrupted and new messages are in the thread

### ✅ Fast Cancellation
Local flag stops old streaming loop immediately

### ✅ Clean UX
User sees the new response start immediately

## No Stop Button Needed!

We removed the Stop button entirely. Just use **double-texting**:

### How to "Stop" the Agent:
**Just send a new message!**

Examples:
- User: "Generate 10 ideas" → Agent running...
- User: "stop" → Agent stops and responds to "stop"
- User: "never mind" → Agent stops and responds to "never mind"
- User: "Actually, do something else" → Agent stops and does the new thing

**Benefits:**
- ✅ Natural conversation flow
- ✅ No extra UI needed
- ✅ Uses official LangGraph `rollback` strategy
- ✅ Clean database (no interrupted runs)

## Frontend Behavior

The frontend doesn't need to change! It just:

1. Sends new message via `/api/agent/run`
2. Backend automatically detects double-texting
3. Old run is cancelled, new run starts
4. Frontend receives `AGENT_CANCELLED` for old run
5. Frontend receives `AGENT_STARTED` for new run
6. Tokens stream for the new response

## Configuration

No configuration needed! Double-texting is automatically detected based on:

```python
is_double_texting = user_id in active_runs and not active_runs[user_id].get("cancelled")
```

## Testing

### Manual Test:

1. Start backend: `make backend`
2. Open dashboard: http://localhost:3000
3. Send message: "Generate 10 post ideas about AI"
4. Wait 2 seconds
5. Send new message: "Actually, just give me 5 ideas about cats"
6. Observe:
   - Old response stops
   - New response starts immediately
   - Both messages in chat history

### Expected Logs:

```
🤖 Starting agent for user user_xxx with task: Generate 10 post ideas about AI
🔄 Starting agent stream for user user_xxx, thread thread_abc
📝 Tracking run_id: run-123
📤 Sent new token: 1. AI-powered...
📤 Sent new token: content creation\n2...

⚡ Double-texting detected! User sent new message while agent is running
   Previous task will be interrupted
🤖 Starting agent for user user_xxx with task: Actually, just give me 5 ideas about cats
🔄 Starting agent stream for user user_xxx, thread thread_abc
   Using interrupt strategy (double-texting)
🛑 Run cancelled by user user_xxx
✅ Agent completed for user user_xxx

📝 Tracking run_id: run-456
📤 Sent new token: 1. Playful cat...
```

## Summary

✅ **Automatic**: No UI changes needed
✅ **Official**: Uses LangGraph's `multitask_strategy="interrupt"`
✅ **Fast**: Local flag + LangGraph interrupt
✅ **Clean**: Preserves conversation history
✅ **Reliable**: Works even if interrupt fails (local flag fallback)

Double-texting is now fully implemented following LangGraph best practices! 🚀

