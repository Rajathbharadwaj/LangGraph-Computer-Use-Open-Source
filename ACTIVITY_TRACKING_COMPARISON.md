# Activity Tracking: Manual Logging vs Streaming

## Comparison

| Aspect | Manual Logging (Current) | Streaming Events (Better) |
|--------|-------------------------|---------------------------|
| **Setup Complexity** | Wrap every tool | Add `emit_activity_event()` calls |
| **Coupling** | High - tools depend on logger | Low - tools just emit events |
| **Maintainability** | Hard - changes need wrapper updates | Easy - modify tools directly |
| **Code Changes** | Wrapper functions for each tool | Single line per tool |
| **Performance** | Minimal overhead | Minimal overhead |
| **Real-time Updates** | No | Yes - can stream to dashboard live! |
| **Debugging** | Must check logs | Can see events in stream |

## Approach 1: Manual Logging (What I Built First)

### How It Works

```python
# x_growth_deep_agent.py
from activity_logger import ActivityLogger

# Wrap the tool
@tool
async def _styled_comment_on_post(author: str, post_content: str = "") -> str:
    # Generate content
    generated_comment = generate_comment(...)

    # Execute original tool
    result = await original_comment_tool.ainvoke({...})

    # MANUAL LOGGING - Tight coupling!
    status = "success" if "successfully" in result.lower() else "failed"
    activity_logger.log_comment(
        target=author,
        content=generated_comment,
        status=status
    )

    return result
```

### Pros
- Simple to understand
- Works immediately
- No streaming setup needed

### Cons
- ❌ Must wrap EVERY tool
- ❌ Tight coupling between tools and logging
- ❌ Hard to maintain
- ❌ Can't stream activities in real-time
- ❌ Activities only saved after tool completes

## Approach 2: Streaming Events (Better)

### How It Works

```python
# async_playwright_tools.py (or wherever tools are defined)
from langgraph.config import get_stream_writer

@tool
async def comment_on_post(author: str, comment_text: str) -> str:
    """Comment on a post"""

    # Execute the comment
    result = await do_comment(author, comment_text)

    # EMIT EVENT - Backend will capture it!
    writer = get_stream_writer()
    writer({
        "type": "activity_complete",
        "action": "comment",
        "status": "success" if "successfully" in result.lower() else "failed",
        "target": author,
        "details": {
            "content": comment_text[:200],
            "result_preview": result[:100]
        }
    })

    return result
```

```python
# backend_websocket_server.py - Capture events from stream
from activity_tracking_streaming import StreamActivityCapture

capture = StreamActivityCapture(store, user_id)

async for chunk in client.runs.stream(
    thread_id,
    graph_name,
    input={...},
    stream_mode=["messages", "custom"]  # Include "custom"!
):
    # Capture activity events
    if chunk.event == "custom":
        await capture.handle_event(chunk.data)

    # Also stream to dashboard for real-time updates!
    if chunk.event == "messages":
        await websocket.send_json(chunk.data)
```

### Pros
- ✅ Clean separation of concerns
- ✅ Tools just emit events
- ✅ Backend handles storage
- ✅ Real-time activity streaming to dashboard
- ✅ Easy to add/remove tracking
- ✅ No wrapper functions needed
- ✅ Can capture events from ANY stream consumer

### Cons
- Requires understanding LangGraph streaming
- Need to add streaming mode to backend

## Implementation Guide: Streaming Approach

### Step 1: Modify Tools to Emit Events

```python
# async_playwright_tools.py
from langgraph.config import get_stream_writer

@tool
async def create_post_on_x(post_text: str) -> str:
    """Create a post on X"""
    writer = get_stream_writer()

    # Emit start event (optional)
    writer({"type": "activity_start", "action": "post"})

    # Execute
    result = await browser.create_post(post_text)

    # Extract post URL
    post_url = extract_url_from_result(result)

    # Emit completion event
    writer({
        "type": "activity_complete",
        "action": "post",
        "status": "success" if "successfully" in result.lower() else "failed",
        "details": {
            "content": post_text[:200],
            "post_url": post_url
        }
    })

    return result


@tool
async def comment_on_post(author: str, comment_text: str) -> str:
    """Comment on a post"""
    writer = get_stream_writer()

    result = await browser.comment(author, comment_text)

    writer({
        "type": "activity_complete",
        "action": "comment",
        "status": "success" if "successfully" in result.lower() else "failed",
        "target": author,
        "details": {
            "content": comment_text[:200]
        }
    })

    return result


@tool
async def like_post(post_identifier: str) -> str:
    """Like a post"""
    writer = get_stream_writer()

    result = await browser.like(post_identifier)

    writer({
        "type": "activity_complete",
        "action": "like",
        "status": "success" if ("successfully" in result.lower() or "❤️" in result) else "failed",
        "target": post_identifier
    })

    return result
```

### Step 2: Update Backend Streaming Code

```python
# backend_websocket_server.py
from activity_tracking_streaming import StreamActivityCapture
from langgraph.store.postgres import PostgresStore

@app.websocket("/ws/agent/{user_id}")
async def agent_websocket(websocket: WebSocket, user_id: str):
    await websocket.accept()

    # Initialize activity capture
    database_uri = os.getenv("DATABASE_URL")
    store = PostgresStore(connection_string=database_uri)
    activity_capture = StreamActivityCapture(store, user_id)

    try:
        # Receive task from user
        data = await websocket.receive_json()
        task = data.get("task")

        # Create thread
        thread = await client.threads.create()
        thread_id = thread["thread_id"]

        # Stream with CUSTOM mode enabled
        async for chunk in client.runs.stream(
            thread_id,
            "x_growth_deep_agent",
            input={"messages": [{"role": "user", "content": task}]},
            config={"configurable": {"user_id": user_id}},
            stream_mode=["messages", "custom"]  # Enable custom events!
        ):
            # Capture activity events
            if chunk.event == "custom":
                await activity_capture.handle_event(chunk.data)

                # BONUS: Stream to dashboard in real-time!
                await websocket.send_json({
                    "type": "activity",
                    "data": chunk.data
                })

            # Stream messages to dashboard
            if chunk.event == "messages":
                await websocket.send_json({
                    "type": "message",
                    "data": chunk.data
                })

    except WebSocketDisconnect:
        pass
```

### Step 3: Update Dashboard to Show Real-Time Activities

```typescript
// Frontend (React/Next.js)
const ActivityFeed = ({ userId }: { userId: string }) => {
  const [activities, setActivities] = useState<Activity[]>([]);

  useEffect(() => {
    const ws = new WebSocket(`ws://localhost:8000/ws/agent/${userId}`);

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === "activity") {
        // Real-time activity update!
        const activity = data.data;
        if (activity.type === "activity_complete") {
          setActivities(prev => [activity, ...prev]);
        }
      }
    };

    return () => ws.close();
  }, [userId]);

  return (
    <div>
      <h2>Recent Activity (Live)</h2>
      {activities.map(activity => (
        <ActivityItem key={activity.timestamp} activity={activity} />
      ))}
    </div>
  );
};
```

## Migration Path

### Option 1: Keep Manual Logging (Quick)
- ✅ Already implemented
- ✅ Works now
- ❌ Technical debt

### Option 2: Migrate to Streaming (Better)
1. Add `emit_activity_event()` calls to tools
2. Update backend streaming to capture custom events
3. Update dashboard to show real-time activities
4. Remove wrapper functions from `x_growth_deep_agent.py`
5. Remove `activity_logger.py` (no longer needed!)

## Recommendation

**Use Streaming Approach** because:

1. **Cleaner Code**: No wrapper functions, tools emit events directly
2. **Real-Time Updates**: Dashboard can show activities as they happen
3. **Better Architecture**: Separation of concerns
4. **Future-Proof**: Easier to extend with more event types

## What Needs to Change

### For Streaming Approach:

**Files to Modify:**
1. `async_playwright_tools.py` - Add `writer()` calls to each tool
2. `backend_websocket_server.py` - Add custom stream mode and activity capture
3. Dashboard frontend - Add real-time activity feed (optional but cool!)

**Files to Remove (after migration):**
1. `activity_logger.py` - No longer needed
2. Wrapper functions in `x_growth_deep_agent.py` - Simplify back to original tools

**New Files:**
1. `activity_tracking_streaming.py` - Stream capture logic (already created!)

## Example: Full Tool with Streaming

```python
# async_playwright_tools.py
from langgraph.config import get_stream_writer
import re

@tool
async def create_post_on_x(post_text: str) -> str:
    """
    Create a post on X (Twitter) using real browser automation.

    This tool uses Playwright to type the post text character-by-character
    with realistic delays, then clicks the Post button.
    """
    try:
        writer = get_stream_writer()
    except:
        writer = None  # Gracefully handle if not in streaming context

    page = await get_browser_page()

    # Navigate to X home
    await page.goto("https://x.com/home")
    await page.wait_for_timeout(2000)

    # Find and click the compose box
    compose_button = page.locator('[data-testid="tweetTextarea_0"]')
    await compose_button.click()
    await page.wait_for_timeout(500)

    # Type the post with realistic delays
    await compose_button.type(post_text, delay=random.randint(50, 150))
    await page.wait_for_timeout(1000)

    # Click Post button
    post_button = page.locator('[data-testid="tweetButton"]')
    await post_button.click()
    await page.wait_for_timeout(3000)

    # Check for success
    success = await page.locator('text="Your post was sent"').is_visible()

    # Extract post URL if successful
    post_url = None
    if success:
        # Try to get the post URL from the page
        try:
            url_elem = page.locator('a[href*="/status/"]').first
            post_url = await url_elem.get_attribute('href')
            if post_url and not post_url.startswith('http'):
                post_url = f"https://x.com{post_url}"
        except:
            pass

    result = f"✅ Successfully posted to X! URL: {post_url}" if success else "❌ Failed to post"

    # EMIT ACTIVITY EVENT
    if writer:
        writer({
            "type": "activity_complete",
            "action": "post",
            "status": "success" if success else "failed",
            "details": {
                "content": post_text[:200],
                "post_url": post_url,
                "full_result": result
            }
        })

    return result
```

## Summary

- **Current**: Manual logging with wrapper functions ✅ Works but not ideal
- **Better**: Streaming events from tools ⭐ Recommended
- **Migration**: Add `writer()` calls to tools, update backend streaming
- **Benefit**: Cleaner code + real-time dashboard updates!
