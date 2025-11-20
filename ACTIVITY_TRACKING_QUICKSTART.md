# Activity Tracking - Quick Setup Guide

## What You Get

Real-time activity tracking on your dashboard showing:
- Posts created
- Comments made
- Likes/unlikes
- Web searches
- Success/failure status
- Live updates (no refresh needed!)

## Quick Setup (5 Steps)

### 1. Update Frontend Component

**File**: `cua-frontend/app/page.tsx`

Change this line:
```tsx
import { RecentActivity } from "@/components/recent-activity";
```

To:
```tsx
import { RecentActivityLive } from "@/components/recent-activity-live";
```

And use the new component:
```tsx
<RecentActivityLive />
```

### 2. Restart Backend

```bash
cd /home/rajathdb/cua
python backend_websocket_server.py
```

The backend now has:
- ✅ `GET /api/activity/recent/{user_id}` - Fetch activities
- ✅ `WS /ws/activity/{user_id}` - Real-time streaming

### 3. Restart Frontend

```bash
cd /home/rajathdb/cua-frontend
npm run dev
```

### 4. Test It Out

The activity tracking already works with your current wrapped tools!

When the agent:
- Creates a post → Activity logged ✅
- Comments on a post → Activity logged ✅
- Likes a post → Activity logged ✅

### 5. (Optional) Migrate to Streaming Events

For cleaner code, migrate from wrapper functions to streaming events:

**Add to each tool in `async_playwright_tools.py`**:
```python
from langgraph.config import get_stream_writer

@tool
async def your_tool(...):
    writer = get_stream_writer() if get_stream_writer else None

    # ... do work ...

    # Emit event
    if writer:
        writer({
            "type": "activity_complete",
            "action": "post",  # or "comment", "like", etc.
            "status": "success" if success else "failed",
            "details": {"content": "..."}
        })

    return result
```

Then **remove wrapper functions** from `x_growth_deep_agent.py` (lines 82-178).

## How It Works

### Current Setup (Works Now!)

```
x_growth_deep_agent.py (wrapper functions)
    ↓
ActivityLogger.log_*()
    ↓
PostgreSQL Store
    ↓
Frontend API GET /api/activity/recent/{user_id}
    ↓
Dashboard displays activities
```

### Future Setup (After Migration)

```
async_playwright_tools.py (emit events)
    ↓
LangGraph Stream (custom mode)
    ↓
Backend WebSocket (capture & forward)
    ↓
PostgreSQL Store + Live Frontend
```

## Files Reference

### Backend
- `activity_logger.py` - Store persistence
- `activity_tracking_streaming.py` - Stream capture
- `backend_websocket_server.py` - API + WebSocket

### Frontend
- `components/recent-activity-live.tsx` - Live component
- `components/recent-activity.tsx` - Old component (mock data)

### Documentation
- `STREAMING_ACTIVITY_IMPLEMENTATION.md` - Full migration guide
- `ACTIVITY_TRACKING_COMPARISON.md` - Manual vs Streaming comparison
- `ACTIVITY_TRACKING_GUIDE.md` - Detailed technical docs

## Test URLs

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000/api/activity/recent/YOUR_USER_ID
- Backend WebSocket: ws://localhost:8000/ws/activity/YOUR_USER_ID

## Viewing Activities

### Via API (curl)
```bash
curl "http://localhost:8000/api/activity/recent/YOUR_USER_ID?limit=10"
```

### Via Frontend
1. Open http://localhost:3000
2. Look for "Recent Activity" section
3. Activities update in real-time!

## Troubleshooting

**No activities showing?**
1. Check if DATABASE_URL is set in `.env`
2. Run the agent on a task
3. Check backend logs for "📝 Logged activity"

**WebSocket not connecting?**
1. Check browser console for errors
2. Verify backend is running on port 8000
3. Check CORS settings in backend

**Activities not persisting?**
1. Verify PostgreSQL Store is initialized
2. Check `DATABASE_URL` environment variable
3. Look for Store errors in backend logs

## Next Steps

1. ✅ Use the dashboard - activities are already being logged!
2. 📊 Watch real-time updates as agent works
3. 🔧 (Optional) Migrate to streaming events for cleaner code
4. 📈 Add filters, analytics, export features

You're all set! The activity tracking is working now with the current setup.
