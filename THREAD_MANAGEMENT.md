# Thread Management Architecture for Workflows

## Overview

Our workflow system now uses **LangGraph Platform** with **automatic PostgreSQL persistence** for proper thread management and state persistence.

## Architecture Summary

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend (Next.js)                        │
│  - Workflow Builder (React Flow)                            │
│  - Workflow Library                                         │
│  - Execution Monitor (WebSocket)                            │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   │ HTTP/WebSocket (port 8002)
                   ▼
┌─────────────────────────────────────────────────────────────┐
│          Backend (backend_websocket_server.py)              │
│  - Workflow API Endpoints                                   │
│  - Uses LangGraph Client SDK                                │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   │ LangGraph SDK (port 8000)
                   ▼
┌─────────────────────────────────────────────────────────────┐
│            LangGraph Platform (langgraph up)                │
│  - x_growth_deep_agent (from langgraph.json)               │
│  - Automatic Checkpointing                                  │
│  - Thread Management                                         │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   │ Automatic Persistence
                   ▼
┌─────────────────────────────────────────────────────────────┐
│                    PostgreSQL Database                       │
│  - Threads (conversations/workflow instances)               │
│  - Checkpoints (state at each step)                         │
│  - Messages (input/output history)                          │
│  - TTL: 12 hours (configurable in langgraph.json)          │
└─────────────────────────────────────────────────────────────┘
```

## Thread Management Strategy

### What is a Thread?

A **thread** represents a single conversation or workflow execution instance. Each thread:
- Has a unique `thread_id`
- Persists state across multiple runs
- Stores checkpoints at each agent step
- Maintains full message history
- Automatically managed by PostgreSQL

### Thread Lifecycle

#### 1. **New Workflow Execution** (Default)
```python
# No thread_id provided → creates new thread
workflow_thread_id = f"workflow_{execution_id}"

# Each execution gets its own thread
# Perfect for: Independent workflow runs
```

#### 2. **Continue Existing Workflow** (Optional)
```python
# Provide existing thread_id → continues conversation
workflow_thread_id = "workflow_abc123"

# Reuses existing thread and state
# Perfect for: Multi-turn workflows, resuming failed runs
```

### Current Implementation

#### Workflow Execution (REST API)
```python
@app.post("/api/workflow/execute")
async def execute_workflow_endpoint(
    workflow_json: dict,
    user_id: Optional[str] = None,
    thread_id: Optional[str] = None  # ← Optional: reuse existing thread
):
    # Generate thread ID
    workflow_thread_id = thread_id or f"workflow_{execution_id}"

    # Use LangGraph Client SDK
    langgraph_client = get_client(url="http://localhost:8000")

    # Execute via deployed agent (PostgreSQL persistence automatic!)
    result = await langgraph_client.runs.create(
        thread_id=workflow_thread_id,
        assistant_id="x_growth_deep_agent",
        input={"messages": [{"role": "user", "content": prompt}]},
        config={"configurable": {"user_id": user_id}}
    )

    # PostgreSQL automatically:
    # ✅ Creates thread if it doesn't exist
    # ✅ Saves checkpoints at each step
    # ✅ Persists full state
    # ✅ Enables resumption/replay
```

#### Workflow Streaming (WebSocket)
```python
@app.websocket("/api/workflow/execute/stream")
async def execute_workflow_stream_endpoint(websocket: WebSocket):
    # Receive workflow + optional thread_id
    workflow_thread_id = thread_id or f"workflow_{execution_id}"

    # Stream execution via LangGraph Platform
    async for chunk in langgraph_client.runs.stream(
        thread_id=workflow_thread_id,
        assistant_id="x_growth_deep_agent",
        input=input_data,
        config=config,
        stream_mode="updates"
    ):
        # Real-time chunks with PostgreSQL persistence!
        await websocket.send_json({"type": "chunk", "data": chunk})
```

## PostgreSQL Persistence (Automatic!)

### What Gets Persisted?

1. **Threads**
   - `thread_id`: Unique identifier
   - `metadata`: User ID, workflow ID, etc.
   - `created_at`: Timestamp

2. **Checkpoints** (State Snapshots)
   - Agent state at each step
   - Message history
   - Tool calls and results
   - Subagent executions

3. **Messages**
   - User inputs
   - Agent responses
   - Tool outputs
   - Streaming chunks

### Configuration (langgraph.json)

```json
{
  "checkpointer": {
    "ttl": {
      "strategy": "delete",
      "sweep_interval_minutes": 120,
      "default_ttl": 43200  // 12 hours
    }
  },
  "store": {
    "ttl": {
      "refresh_on_read": true,
      "sweep_interval_minutes": 60,
      "default_ttl": 1440  // 24 hours
    }
  }
}
```

### Storage Cleanup
- **Checkpoints TTL**: 12 hours (43200 seconds)
- **Store TTL**: 24 hours (1440 minutes)
- **Sweep Interval**: Every 2 hours for checkpoints, 1 hour for store
- Old threads are automatically cleaned up

## Workflow Execution Patterns

### Pattern 1: One-Time Execution (Current Default)
```javascript
// Frontend calls execute without thread_id
const response = await fetch('/api/workflow/execute', {
  method: 'POST',
  body: JSON.stringify({
    workflow_json: workflow,
    user_id: null  // Optional
    // No thread_id → creates new thread
  })
});

// ✅ New thread created
// ✅ PostgreSQL persists state
// ✅ Thread_id returned in response
// ✅ Can be queried later
```

### Pattern 2: Continue Conversation
```javascript
// Frontend provides previous thread_id
const response = await fetch('/api/workflow/execute', {
  method: 'POST',
  body: JSON.stringify({
    workflow_json: workflow,
    user_id: "user_123",
    thread_id: "workflow_abc123"  // ← Reuse existing thread
  })
});

// ✅ Continues existing conversation
// ✅ Access to previous messages
// ✅ Maintains state across runs
```

### Pattern 3: Resume Failed Workflow
```javascript
// Get thread from failed execution
const failedExecution = await fetch('/api/workflow/execution/{execution_id}');
const thread_id = failedExecution.thread_id;

// Retry with same thread
const retry = await fetch('/api/workflow/execute', {
  method: 'POST',
  body: JSON.stringify({
    workflow_json: workflow,
    thread_id: thread_id  // ← Resume from checkpoint
  })
});

// ✅ Resumes from last checkpoint
// ✅ No duplicate work
// ✅ Fault tolerant
```

## Benefits of LangGraph Client SDK Approach

### Before (Local Compilation)
```python
# ❌ OLD WAY
from x_growth_deep_agent import create_x_growth_agent

agent = create_x_growth_agent(config={...})
result = await agent.ainvoke({...})

# Problems:
# ❌ No automatic persistence
# ❌ Threads not managed
# ❌ No PostgreSQL integration
# ❌ Can't resume failed workflows
# ❌ Manual checkpointer needed
```

### After (LangGraph Client SDK)
```python
# ✅ NEW WAY (Current Implementation)
from langgraph_sdk import get_client

client = get_client(url="http://localhost:8000")
result = await client.runs.create(
    thread_id=workflow_thread_id,
    assistant_id="x_growth_deep_agent",
    input={...}
)

# Benefits:
# ✅ Automatic PostgreSQL persistence
# ✅ Thread management built-in
# ✅ Checkpoints automatic
# ✅ Can resume from any checkpoint
# ✅ Scalable and distributed
# ✅ No manual configuration needed
```

## Querying Thread State

### Get Current State
```python
from langgraph_sdk import get_client

client = get_client(url="http://localhost:8000")

# Get thread state
state = await client.threads.get_state(thread_id)

# Returns:
# - Current values (messages, context, etc.)
# - Last checkpoint metadata
# - Next steps
```

### Get Historical State
```python
# Get state at specific checkpoint
state = await client.threads.get_state(
    thread_id,
    checkpoint_id="checkpoint_xyz"
)

# Time travel to any point in execution!
```

### List All Threads
```python
# Search threads (with filters)
threads = await client.threads.search(
    metadata={"workflow_id": "reply_guy_strategy"}
)

# Find specific user's workflows
threads = await client.threads.search(
    metadata={"user_id": "user_123"}
)
```

## Future Enhancements

### 1. Thread History UI
Show users their past workflow executions with ability to:
- View execution history
- Replay workflows
- Resume from checkpoints
- Time-travel debugging

### 2. Workflow Templates with Pre-seeded Threads
- Save successful workflow runs as templates
- Fork threads to create variants
- Share workflow patterns

### 3. Human-in-the-Loop
- Pause workflows for approval
- Thread persists waiting for input
- Resume when user provides feedback

### 4. Multi-User Collaboration
- Multiple users working on same thread
- Collaborative workflow building
- Shared execution context

## Key Takeaways

1. **Every workflow execution creates a thread** (or reuses one if `thread_id` provided)
2. **PostgreSQL automatically persists everything** (no manual configuration needed)
3. **Threads enable powerful features**: resume, replay, time-travel, fault tolerance
4. **LangGraph Client SDK is the right way** to interact with deployed agents
5. **Thread management is production-ready** and scalable

## Related Files

- `backend_websocket_server.py` - Workflow execution endpoints (lines 2205-2402)
- `langgraph.json` - LangGraph Platform configuration
- `x_growth_deep_agent.py` - Agent definition (deployed to LangGraph Platform)
- `WORKFLOWS_GUIDE.md` - Workflow system documentation
- `workflow_parser.py` - Workflow JSON → Agent instructions

## Resources

- [LangGraph Persistence Docs](https://docs.langchain.com/oss/python/langgraph/persistence)
- [LangGraph Client SDK](https://docs.langchain.com/langsmith/langgraph-client-sdk)
- [Thread Management Best Practices](https://docs.langchain.com/langsmith/threads)
