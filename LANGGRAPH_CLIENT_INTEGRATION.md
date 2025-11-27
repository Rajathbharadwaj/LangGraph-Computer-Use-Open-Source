# LangGraph Client API Integration Guide

This guide shows how to integrate the LangGraph SDK client to run and manage your X Growth Deep Agent from the backend.

## Overview

Your LangGraph server is running at `http://localhost:8124` with the agent `x_growth_deep_agent` defined in `langgraph.json`.

## Installation

```bash
# Already installed in newat environment
pip install langgraph-sdk
```

## Basic Client Setup

### 1. Get Client Instance

```python
from langgraph_sdk import get_client, get_sync_client

# Async client (recommended)
client = get_client(url="http://localhost:8124")

# Sync client (if needed)
client = get_sync_client(url="http://localhost:8124")
```

## Core Operations

### 1. Create a Thread (Conversation)

Threads persist state across multiple runs:

```python
# Create a new thread for a user
thread = await client.threads.create()
thread_id = thread["thread_id"]

print(f"Created thread: {thread_id}")
```

### 2. Run the Agent (Streaming)

**Recommended for real-time updates:**

```python
async for chunk in client.runs.stream(
    thread_id=thread_id,  # Or None for threadless run
    assistant_id="x_growth_deep_agent",  # From langgraph.json
    input={
        "messages": [{
            "role": "user",
            "content": "Find and engage with 5 posts about AI"
        }]
    },
    stream_mode="updates",  # Options: "values", "updates", "messages"
):
    print(f"Event: {chunk.event}")
    print(f"Data: {chunk.data}")
```

### 3. Run the Agent (Wait for Completion)

**For background tasks:**

```python
result = await client.runs.wait(
    thread_id=thread_id,
    assistant_id="x_growth_deep_agent",
    input={
        "messages": [{
            "role": "user", 
            "content": "Like 10 posts about machine learning"
        }]
    }
)

print(f"Final result: {result}")
```

### 4. Get Thread State

```python
# Get current state of a thread
state = await client.threads.get_state(
    thread_id=thread_id
)

print(f"Current state: {state}")
```

### 5. Get Thread History

```python
# Get execution history
history = await client.threads.get_history(
    thread_id=thread_id,
    limit=10  # Last 10 checkpoints
)

for checkpoint in history:
    print(f"Checkpoint: {checkpoint}")
```

### 6. Update Thread State (Human-in-the-Loop)

```python
# Modify the agent's state mid-execution
await client.threads.update_state(
    thread_id=thread_id,
    values={"approval_status": "approved"},
    as_node="human_approval"  # Which node to resume from
)
```

## Integration with Backend

### Example: Add to `backend_websocket_server.py`

```python
from langgraph_sdk import get_client
import asyncio

# Initialize LangGraph client
langgraph_client = get_client(url="http://localhost:8124")

@app.post("/api/agent/run")
async def run_agent(data: dict):
    """
    Run the X Growth Deep Agent for a user
    """
    user_id = data.get("user_id")
    task = data.get("task", "Engage with posts about AI")
    
    try:
        # Create or get thread for this user
        if user_id not in user_threads:
            thread = await langgraph_client.threads.create()
            user_threads[user_id] = thread["thread_id"]
        
        thread_id = user_threads[user_id]
        
        # Stream agent execution
        async for chunk in langgraph_client.runs.stream(
            thread_id=thread_id,
            assistant_id="x_growth_deep_agent",
            input={
                "messages": [{
                    "role": "user",
                    "content": task
                }]
            },
            stream_mode="updates"
        ):
            # Send updates to frontend via WebSocket
            if user_id in active_connections:
                await active_connections[user_id].send_json({
                    "type": "AGENT_UPDATE",
                    "event": chunk.event,
                    "data": chunk.data
                })
        
        return {"success": True, "thread_id": thread_id}
        
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/agent/stop")
async def stop_agent(data: dict):
    """
    Stop a running agent
    """
    thread_id = data.get("thread_id")
    
    try:
        # Cancel the run
        await langgraph_client.runs.cancel(thread_id)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/agent/history/{thread_id}")
async def get_agent_history(thread_id: str):
    """
    Get agent execution history
    """
    try:
        history = await langgraph_client.threads.get_history(
            thread_id=thread_id,
            limit=50
        )
        return {"success": True, "history": list(history)}
    except Exception as e:
        return {"success": False, "error": str(e)}
```

## Stream Modes

Different ways to receive agent updates:

| Mode | Description | Use Case |
|------|-------------|----------|
| `values` | Full state after each node | See complete state |
| `updates` | Only what changed in each node | Efficient updates |
| `messages` | Just the messages | Chat-like interface |
| `messages-tuple` | Messages with metadata | Detailed message info |

## Thread Management

### Per-User Threads

```python
# Store thread IDs per user
user_threads = {}

def get_or_create_thread(user_id: str):
    if user_id not in user_threads:
        thread = await langgraph_client.threads.create()
        user_threads[user_id] = thread["thread_id"]
    return user_threads[user_id]
```

### Thread Cleanup

```python
# Delete old threads
await langgraph_client.threads.delete(thread_id)
```

## Error Handling

```python
from langgraph_sdk.exceptions import GraphException

try:
    result = await client.runs.wait(
        thread_id=thread_id,
        assistant_id="x_growth_deep_agent",
        input={"messages": [{"role": "user", "content": "task"}]}
    )
except GraphException as e:
    print(f"Graph error: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

## Configuration

Pass configuration to the agent:

```python
result = await client.runs.wait(
    thread_id=thread_id,
    assistant_id="x_growth_deep_agent",
    input={"messages": [{"role": "user", "content": "task"}]},
    config={
        "configurable": {
            "model": "claude-3-5-sonnet-20241022",
            "max_iterations": 10,
            "user_id": user_id
        }
    }
)
```

## Monitoring & Debugging

### Check Agent Status

```python
# Get all threads
threads = await client.threads.search()

# Get specific thread state
state = await client.threads.get_state(thread_id)
print(f"Current node: {state['next']}")
print(f"Values: {state['values']}")
```

### LangSmith Integration

Your agent automatically logs to LangSmith if `LANGSMITH_API_KEY` is set:

```bash
export LANGSMITH_API_KEY="your-key"
export LANGSMITH_PROJECT="x-growth-automation"
```

View traces at: https://smith.langchain.com

## Best Practices

1. **Use Threads for Conversations**: Create one thread per user session
2. **Stream for Real-Time**: Use `client.runs.stream()` for live updates
3. **Handle Errors Gracefully**: Wrap calls in try-except blocks
4. **Clean Up**: Delete old threads periodically
5. **Monitor Performance**: Use LangSmith for debugging
6. **Persist Thread IDs**: Store in database for long-term conversations

## Example: Full Integration

```python
from langgraph_sdk import get_client
from fastapi import FastAPI, WebSocket

app = FastAPI()
langgraph_client = get_client(url="http://localhost:8124")
user_threads = {}
active_connections = {}

@app.websocket("/ws/agent/{user_id}")
async def agent_websocket(websocket: WebSocket, user_id: str):
    await websocket.accept()
    active_connections[user_id] = websocket
    
    try:
        while True:
            # Receive task from frontend
            data = await websocket.receive_json()
            task = data.get("task")
            
            # Get or create thread
            if user_id not in user_threads:
                thread = await langgraph_client.threads.create()
                user_threads[user_id] = thread["thread_id"]
            
            thread_id = user_threads[user_id]
            
            # Stream agent execution
            async for chunk in langgraph_client.runs.stream(
                thread_id=thread_id,
                assistant_id="x_growth_deep_agent",
                input={
                    "messages": [{
                        "role": "user",
                        "content": task
                    }]
                },
                stream_mode="updates"
            ):
                # Send to frontend
                await websocket.send_json({
                    "type": "AGENT_UPDATE",
                    "event": chunk.event,
                    "data": chunk.data
                })
    
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        del active_connections[user_id]
```

## Next Steps

1. Add agent endpoints to `backend_websocket_server.py`
2. Create frontend UI to trigger agent tasks
3. Display agent progress in real-time
4. Add human-in-the-loop approval for actions
5. Store thread IDs in database for persistence

## Resources

- [LangGraph SDK Docs](https://docs.langchain.com/langgraph-platform/langgraph-server)
- [LangSmith Studio](https://smith.langchain.com)
- [API Reference](https://docs.langchain.com/langgraph-platform/api-reference)


