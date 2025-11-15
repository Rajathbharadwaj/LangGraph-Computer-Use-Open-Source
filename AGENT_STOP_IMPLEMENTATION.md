# Agent Stop/Cancel Implementation

## Overview

Implemented comprehensive agent stop/cancel functionality following LangGraph best practices for handling interruptions and graceful cancellation.

## Backend Implementation

### 1. Active Run Tracking (`backend_websocket_server.py`)

Added global tracking for active agent runs:

```python
# Track active runs for cancellation
# Format: {user_id: {"thread_id": str, "run_id": str, "task": asyncio.Task, "cancelled": bool}}
active_runs = {}
```

### 2. Modified `stream_agent_execution()` Function

**Key Changes:**
- Tracks each run in `active_runs` dictionary when started
- Checks `cancelled` flag on every stream iteration
- Breaks out of streaming loop if cancelled
- Sends `AGENT_CANCELLED` instead of `AGENT_COMPLETED` when cancelled
- Cleans up `active_runs` entry on completion/error

**Cancellation Check:**
```python
async for chunk in langgraph_client.runs.stream(...):
    # Check if cancelled
    if user_id in active_runs and active_runs[user_id].get("cancelled"):
        print(f"🛑 Run cancelled by user {user_id}")
        break
```

### 3. New Endpoints

#### `/api/agent/stop` (POST)
Cancels a running agent execution for a user.

**Request:**
```json
{
  "user_id": "user_xxx"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Agent stop signal sent",
  "thread_id": "thread_xxx",
  "run_id": "run_xxx"
}
```

**How it works:**
1. Sets `cancelled` flag to `true` in `active_runs[user_id]`
2. Sends `AGENT_STOPPING` WebSocket message to frontend
3. The streaming loop checks this flag and breaks gracefully

#### `/api/agent/status/{user_id}` (GET)
Checks if an agent is currently running for a user.

**Response:**
```json
{
  "is_running": true,
  "thread_id": "thread_xxx",
  "run_id": "run_xxx"
}
```

### 4. New WebSocket Message Types

- **`AGENT_STOPPING`**: Sent immediately when stop is requested
- **`AGENT_CANCELLED`**: Sent when the agent has fully stopped

## Frontend Implementation

### 1. Stop Handler (`agent-control-card.tsx`)

Added `handleStopAgent()` function:

```typescript
const handleStopAgent = async () => {
  if (!userId || !status.isRunning) return;

  try {
    const response = await fetch('http://localhost:8002/api/agent/stop', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId })
    });

    const data = await response.json();
    if (data.success) {
      console.log('✅ Agent stop signal sent');
    }
  } catch (error) {
    console.error('❌ Error stopping agent:', error);
  }
};
```

### 2. Dynamic Send/Stop Button

The button now changes based on agent status:

```tsx
{status.isRunning ? (
  <Button
    onClick={handleStopAgent}
    variant="destructive"
    className="h-[44px]"
  >
    <Square className="h-4 w-4 mr-2" />
    Stop
  </Button>
) : (
  <Button
    onClick={handleSendMessage}
    disabled={!input.trim()}
    className="bg-purple-500 hover:bg-purple-600 h-[44px]"
  >
    <Send className="h-4 w-4" />
  </Button>
)}
```

### 3. WebSocket Message Handlers

Added handlers for new message types:

```typescript
else if (data.type === 'AGENT_STOPPING') {
  console.log('🛑 Agent is stopping...');
  addMessage('system', `🛑 ${data.message || 'Stopping agent execution...'}`);
}
else if (data.type === 'AGENT_CANCELLED') {
  setStatus(prev => ({ ...prev, isRunning: false }));
  addMessage('system', '🛑 Agent execution cancelled');
  // Reset streaming state
  streamingStateRef.current.currentMessage = '';
  streamingStateRef.current.messageIndex = -1;
}
```

## How It Works (End-to-End)

### User Flow:

1. **User starts agent**: Sends message → Agent begins execution
2. **User clicks "Stop"**: Frontend calls `/api/agent/stop`
3. **Backend sets flag**: `active_runs[user_id]["cancelled"] = true`
4. **Backend notifies frontend**: Sends `AGENT_STOPPING` WebSocket message
5. **Streaming loop checks flag**: On next iteration, sees `cancelled = true`
6. **Loop breaks**: Exits streaming gracefully
7. **Cleanup**: Sends `AGENT_CANCELLED` message, removes from `active_runs`
8. **Frontend updates**: Shows cancellation message, re-enables input

### Technical Details:

- **Graceful Cancellation**: The agent stops at the next stream iteration, not mid-operation
- **State Cleanup**: All state (messages, streaming refs, active_runs) is properly cleaned up
- **User Feedback**: Clear visual feedback at each step (button changes, system messages)
- **Thread Preservation**: The thread and its history are preserved; only the current run is cancelled

## LangGraph Integration Notes

### Using Official Double-Texting Strategy

LangGraph provides a **built-in solution** for handling concurrent runs through the **double-texting** feature. We use the `multitask_strategy="rollback"` parameter for clean cancellation.

**Why `rollback` over `interrupt`?**

From the LangGraph docs, there are two strategies:

1. **`interrupt`**: Keeps the cancelled run in database with status `"interrupted"` and preserves partial progress
2. **`rollback`**: **Completely deletes** the cancelled run from the database

For a "Stop" button, **`rollback` is better** because:
- ✅ User expects the cancelled task to be gone (not just paused)
- ✅ Cleaner thread history (no partial interrupted runs)
- ✅ No pollution from dummy cancellation messages

**From the LangGraph docs:**
> "The rollback option interrupts the prior run of the graph and starts a new one with the double-text. This option is very similar to the interrupt option, but in this case the first run is completely deleted from the database and cannot be restarted."

### Our Hybrid Approach:

We combine LangGraph's official rollback strategy with local state management:

1. **Track active runs** in memory (for quick status checks)
2. **Create rollback run** using `client.runs.create()` with `multitask_strategy="rollback"`
3. **Set local cancellation flag** so the streaming loop exits immediately
4. **LangGraph deletes the cancelled run** from the database
5. **Clean up local state** when the loop exits

**Code:**
```python
rollback_run = await langgraph_client.runs.create(
    thread_id=thread_id,
    assistant_id="x_growth_deep_agent",
    input={"messages": [{"role": "user", "content": "[CANCELLED]"}]},
    multitask_strategy="rollback"  # Official LangGraph feature - deletes previous run
)
```

**Known Limitation:**
The dummy `[CANCELLED]` message will appear in the thread state. In production, you might want to:
- Use a special system message type that the UI filters out
- Immediately delete the rollback run after it cancels the original
- Implement a custom cleanup mechanism

This approach:
- ✅ Uses official LangGraph double-texting feature
- ✅ Cancelled run is completely removed from database
- ✅ Provides immediate user feedback via local flag
- ✅ Gracefully stops without corrupting state
- ✅ Clean conversation history (except dummy message)
- ✅ Follows LangGraph best practices

## Future Enhancements

### 1. Interrupt-Based Cancellation
If LangGraph adds a `client.runs.cancel()` method, we can enhance this to:
```python
# Set interrupted status in LangGraph
await langgraph_client.runs.cancel(thread_id, run_id)
```

### 2. Timeout Handling
Add automatic cancellation after a timeout:
```python
async def stream_with_timeout(user_id, thread_id, task, timeout=300):
    try:
        await asyncio.wait_for(
            stream_agent_execution(user_id, thread_id, task),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        # Auto-cancel after timeout
        active_runs[user_id]["cancelled"] = True
```

### 3. Pause/Resume
Implement pause/resume using LangGraph interrupts:
```python
# In agent graph
from langgraph.types import interrupt

def pausable_node(state):
    # Check if pause requested
    if should_pause():
        interrupt({"reason": "User requested pause"})
    return state
```

## Testing

### Manual Test Steps:

1. **Start the backend**: `make backend` or restart manually
2. **Open dashboard**: http://localhost:3000
3. **Start a long-running task**: 
   - Type: "Generate 10 post ideas about AI"
   - Click Send
4. **Observe agent running**: Button changes to "Stop"
5. **Click "Stop"**: Should see:
   - System message: "🛑 Stopping agent execution..."
   - System message: "🛑 Agent execution cancelled"
   - Button changes back to "Send"
6. **Verify state**: Input should be re-enabled, can send new messages

### Backend Logs:

Look for these log messages:
```
🛑 Stop requested for user user_xxx
🛑 Cancellation flag set for user user_xxx
   Thread: thread_xxx
   Run ID: run_xxx
🛑 Run cancelled by user user_xxx
✅ Agent completed for user user_xxx
```

## Files Modified

### Backend:
- `/home/rajathdb/cua/backend_websocket_server.py`
  - Added `active_runs` tracking
  - Modified `stream_agent_execution()` for cancellation support
  - Added `/api/agent/stop` endpoint
  - Added `/api/agent/status/{user_id}` endpoint
  - Added `AGENT_STOPPING` and `AGENT_CANCELLED` WebSocket messages

### Frontend:
- `/home/rajathdb/cua-frontend/components/agent-control-card.tsx`
  - Added `handleStopAgent()` function
  - Modified button to show "Stop" when running
  - Added handlers for `AGENT_STOPPING` and `AGENT_CANCELLED` messages

## Summary

✅ **Implemented**: Full agent stop/cancel functionality
✅ **Graceful**: Stops at next iteration, no state corruption
✅ **User-Friendly**: Clear visual feedback and system messages
✅ **LangGraph Compatible**: Works with current SDK limitations
✅ **Extensible**: Easy to enhance with future LangGraph features

The implementation follows best practices from the LangGraph docs on interrupts and human-in-the-loop patterns, adapted for manual cancellation use cases.

