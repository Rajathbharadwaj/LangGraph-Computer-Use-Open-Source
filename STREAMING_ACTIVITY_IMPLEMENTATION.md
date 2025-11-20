# Streaming Activity Tracking - Complete Implementation Guide

## Overview

This guide shows you exactly what to change to get real-time activity tracking working on your dashboard.

## What You Get

- ✅ Real-time activity feed on dashboard
- ✅ Activities automatically saved to PostgreSQL Store
- ✅ Live updates as agent performs actions
- ✅ No need to refresh the page
- ✅ Clean architecture with no wrapper functions

## Architecture

```
X Tool (emit event)
    ↓
LangGraph Stream (custom mode)
    ↓
Backend WebSocket (capture & save)
    ↓
Frontend Dashboard (real-time display)
```

## Files Created/Modified

### ✅ Already Created:
1. `activity_logger.py` - Store persistence logic
2. `activity_tracking_streaming.py` - Stream event capture
3. `backend_websocket_server.py` - API + WebSocket endpoints
4. `cua-frontend/components/recent-activity-live.tsx` - Live dashboard component

### 🔧 Need to Modify:
1. `async_playwright_tools.py` - Add event emission to tools
2. `cua-frontend/app/page.tsx` - Use live component

## Step-by-Step Implementation

### Step 1: Modify X Automation Tools

Add event emission to each tool. Here's how:

#### Example: comment_on_post Tool

**File**: `async_playwright_tools.py`

**BEFORE** (No events):
```python
@tool
async def comment_on_post(author_or_content: str, comment_text: str) -> str:
    """Comment on a post"""

    # Navigate and post comment
    page = await get_browser_page()
    # ... posting logic ...

    result = "✅ Successfully posted comment!" if success else "❌ Failed to comment"
    return result
```

**AFTER** (With streaming events):
```python
from langgraph.config import get_stream_writer

@tool
async def comment_on_post(author_or_content: str, comment_text: str) -> str:
    """Comment on a post"""

    # Get stream writer
    try:
        writer = get_stream_writer()
    except:
        writer = None  # Gracefully handle if not in streaming context

    # Navigate and post comment
    page = await get_browser_page()
    # ... posting logic ...

    # Determine success
    success = await check_if_posted()
    result = "✅ Successfully posted comment!" if success else "❌ Failed to comment"

    # EMIT ACTIVITY EVENT
    if writer:
        writer({
            "type": "activity_complete",
            "action": "comment",
            "status": "success" if success else "failed",
            "target": author_or_content,
            "details": {
                "content": comment_text[:200],
                "result_preview": result[:100]
            }
        })

    return result
```

#### Example: create_post_on_x Tool

**File**: `async_playwright_tools.py`

**Add to create_post_on_x**:
```python
from langgraph.config import get_stream_writer
import re

@tool
async def create_post_on_x(post_text: str) -> str:
    """Create a post on X"""

    try:
        writer = get_stream_writer()
    except:
        writer = None

    # Create the post
    page = await get_browser_page()
    # ... posting logic ...

    # Check success
    success = await page.locator('text="Your post was sent"').is_visible()

    # Extract post URL if successful
    post_url = None
    if success:
        try:
            url_elem = page.locator('a[href*="/status/"]').first
            post_url = await url_elem.get_attribute('href')
            if post_url and not post_url.startswith('http'):
                post_url = f"https://x.com{post_url}"
        except:
            pass

    result = f"✅ Successfully posted! URL: {post_url}" if success else "❌ Failed to post"

    # EMIT ACTIVITY EVENT
    if writer:
        writer({
            "type": "activity_complete",
            "action": "post",
            "status": "success" if success else "failed",
            "details": {
                "content": post_text[:200],
                "post_url": post_url
            }
        })

    return result
```

#### Example: like_post Tool

**File**: `async_playwright_tools.py`

**Add to like_post**:
```python
from langgraph.config import get_stream_writer

@tool
async def like_post(post_identifier: str) -> str:
    """Like a post"""

    try:
        writer = get_stream_writer()
    except:
        writer = None

    # Like the post
    # ... liking logic ...

    success = # check if liked
    result = "❤️ Successfully liked post!" if success else "❌ Failed to like"

    # EMIT ACTIVITY EVENT
    if writer:
        writer({
            "type": "activity_complete",
            "action": "like",
            "status": "success" if success else "failed",
            "target": post_identifier
        })

    return result
```

#### Example: unlike_post Tool

**File**: `async_playwright_tools.py`

**Add to unlike_post**:
```python
from langgraph.config import get_stream_writer

@tool
async def unlike_post(post_identifier: str) -> str:
    """Unlike a post"""

    try:
        writer = get_stream_writer()
    except:
        writer = None

    # Unlike the post
    # ... unliking logic ...

    success = # check if unliked
    result = "✅ Successfully unliked post!" if success else "❌ Failed to unlike"

    # EMIT ACTIVITY EVENT
    if writer:
        writer({
            "type": "activity_complete",
            "action": "unlike",
            "status": "success" if success else "failed",
            "target": post_identifier
        })

    return result
```

### Step 2: Remove Wrapper Functions

**File**: `x_growth_deep_agent.py`

**REMOVE** this section (lines 82-178):
```python
# WRAP comment_on_post and create_post_on_x with AUTOMATIC style transfer + activity logging
if store and user_id and model:
    from x_writing_style_learner import XWritingStyleManager
    from activity_logger import ActivityLogger

    # Initialize activity logger
    activity_logger = ActivityLogger(store, user_id)

    # ... ALL THE WRAPPER CODE ...
```

**KEEP** the style transfer logic but integrate it differently - you can move that into the tools themselves if needed, or create a separate function that the tools call.

### Step 3: Update Frontend Component

**File**: `cua-frontend/app/page.tsx` (or wherever RecentActivity is used)

**BEFORE**:
```tsx
import { RecentActivity } from "@/components/recent-activity";

export default function Dashboard() {
  return (
    <div>
      <RecentActivity />
    </div>
  );
}
```

**AFTER**:
```tsx
import { RecentActivityLive } from "@/components/recent-activity-live";

export default function Dashboard() {
  return (
    <div>
      <RecentActivityLive />
    </div>
  );
}
```

## Testing

### 1. Start Backend
```bash
cd /home/rajathdb/cua
python backend_websocket_server.py
```

### 2. Start Frontend
```bash
cd /home/rajathdb/cua-frontend
npm run dev
```

### 3. Open Dashboard
Open http://localhost:3000 in your browser

### 4. Trigger Agent Action
Send a task to the agent (e.g., "Comment on @elonmusk's latest post")

### 5. Watch Real-Time Updates
- Activity should appear instantly on the dashboard
- No page refresh needed
- Status badge shows success/failed
- Content preview visible

## Event Format Reference

All tools should emit events in this format:

```python
writer({
    "type": "activity_complete",      # Always "activity_complete"
    "action": str,                    # "post", "comment", "like", "unlike", "web_search"
    "status": str,                    # "success" or "failed"
    "target": str | None,             # Target user/post (optional)
    "details": {                      # Additional info
        "content": str,               # Post/comment text (truncated to 200 chars)
        "post_url": str,              # URL to the post (if available)
        "error": str,                 # Error message (if failed)
        "query": str,                 # Search query (for web_search)
        "results_count": int,         # Number of results (for web_search)
        # ... any other relevant data
    }
})
```

## Troubleshooting

### Activities Not Showing Up

**Check 1**: Stream mode enabled?
```python
# In backend_websocket_server.py
stream_mode=["messages", "custom"]  # Must include "custom"!
```

**Check 2**: Tools emitting events?
```python
# In your tool
writer = get_stream_writer()  # This should work
writer({"type": "activity_complete", ...})
```

**Check 3**: WebSocket connected?
```
# Browser console should show:
📡 Connected to activity stream
```

**Check 4**: Database configured?
```python
# Check .env file
DATABASE_URL=postgresql://...
```

### Events Not Persisting

**Check**: Store initialization in backend
```python
# In backend_websocket_server.py
database_uri = os.getenv("DATABASE_URL")
# Should print the connection string
```

### Frontend Not Updating

**Check 1**: WebSocket URL correct?
```tsx
// In recent-activity-live.tsx
ws://localhost:8000/ws/activity/${user.id}
```

**Check 2**: CORS enabled?
```python
# In backend_websocket_server.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    ...
)
```

## Next Steps

1. **Add More Tools**: Apply the same pattern to other automation tools
2. **Add Filters**: Filter activities by type, status, date
3. **Add Export**: Export activities to CSV/JSON
4. **Add Analytics**: Show success rates, activity trends
5. **Add Notifications**: Toast notifications for new activities

## Summary

**What Changed**:
- ✅ Added `writer()` calls to X automation tools
- ✅ Removed wrapper functions from `x_growth_deep_agent.py`
- ✅ Added WebSocket endpoint `/ws/activity/{user_id}`
- ✅ Created `RecentActivityLive` component
- ✅ Connected everything together

**Result**:
- Real-time activity tracking ⚡
- Clean architecture 🏗️
- Live dashboard updates 📊
- Persistent storage in PostgreSQL 💾
