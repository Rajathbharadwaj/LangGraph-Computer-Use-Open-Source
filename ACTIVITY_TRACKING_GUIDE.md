# Activity Tracking System Guide

## Overview

The activity tracking system logs all agent actions (posts, comments, likes, unlikes, web searches) to the LangGraph Store for display on the dashboard's "Recent Activity" section.

## Architecture

### Components

1. **ActivityLogger** (`activity_logger.py`)
   - Logs activities to LangGraph PostgreSQL Store
   - Stores as JSON documents in namespace: `(user_id, "activity")`
   - Provides methods for logging and retrieving activities

2. **Agent Integration** (`x_growth_deep_agent.py`)
   - Wraps X automation tools with activity logging
   - Automatically logs after each tool execution
   - Parses results to determine success/failure

3. **API Endpoint** (`backend_websocket_server.py`)
   - `GET /api/activity/recent/{user_id}?limit=50`
   - Retrieves recent activities from Store
   - Returns sorted list (newest first)

## Data Structure

### Activity JSON Format

```json
{
  "id": "post_20250115_143022_123456",
  "timestamp": "2025-01-15T14:30:22.123456",
  "action_type": "post|comment|like|unlike|web_search",
  "status": "success|failed",
  "details": {
    "content": "Post or comment text (truncated to 200 chars)",
    "post_url": "https://x.com/username/status/123...",
    "error": "Error message if failed",
    "query": "Search query (for web_search)",
    "results_count": 5
  },
  "target": "@username or post_id (if applicable)"
}
```

### Action Types

| Action Type | Description | Details Keys |
|------------|-------------|--------------|
| `post` | Created a post on X | `content`, `post_url`, `error` |
| `comment` | Commented on a post | `content`, `on_post`, `error` |
| `like` | Liked a post | `error` |
| `unlike` | Unliked a post | `error` |
| `web_search` | Searched the web | `query`, `results_count` |

## How It Works

### 1. Tool Execution

When the agent executes a tool (e.g., `create_post_on_x`):

```python
# x_growth_deep_agent.py
@tool
async def _styled_create_post_on_x(topic_or_context: str) -> str:
    # Step 1: Generate content in user's style
    generated_post = generate_styled_content(topic_or_context)

    # Step 2: Execute the tool
    result = await original_post_tool.ainvoke({"post_text": generated_post})

    # Step 3: Log activity
    status = "success" if ("successfully" in result.lower() or "✅" in result) else "failed"
    activity_logger.log_post(
        content=generated_post,
        status=status,
        post_url=extract_url(result),
        error=result if status == "failed" else None
    )

    return result
```

### 2. Storage in LangGraph Store

Activities are stored in PostgreSQL via LangGraph Store:

```python
# activity_logger.py
def log_activity(self, action_type, status, details, target=None):
    timestamp = datetime.utcnow()
    activity_id = f"{action_type}_{timestamp.strftime('%Y%m%d_%H%M%S_%f')}"

    activity_data = {
        "id": activity_id,
        "timestamp": timestamp.isoformat(),
        "action_type": action_type,
        "status": status,
        "details": details,
        "target": target
    }

    # Save to Store under (user_id, "activity") namespace
    self.store.put(
        (self.user_id, "activity"),
        activity_id,
        activity_data
    )
```

### 3. Retrieval for Dashboard

Dashboard fetches activities via API:

```typescript
// Frontend code
const response = await fetch(`/api/activity/recent/${userId}?limit=50`);
const data = await response.json();

// data.activities = [
//   {
//     id: "post_20250115_143022_123456",
//     timestamp: "2025-01-15T14:30:22.123456",
//     action_type: "post",
//     status: "success",
//     details: { content: "Just posted about AI...", post_url: "..." },
//     target: null
//   },
//   ...
// ]
```

## API Usage

### Get Recent Activity

```bash
curl "http://localhost:8000/api/activity/recent/user_123?limit=50"
```

**Response:**

```json
{
  "success": true,
  "activities": [
    {
      "id": "comment_20250115_143500_789012",
      "timestamp": "2025-01-15T14:35:00.789012",
      "action_type": "comment",
      "status": "success",
      "details": {
        "content": "Great insights! 🚀",
        "on_post": "@elonmusk's latest post"
      },
      "target": "@elonmusk"
    },
    {
      "id": "post_20250115_143022_123456",
      "timestamp": "2025-01-15T14:30:22.123456",
      "action_type": "post",
      "status": "success",
      "details": {
        "content": "Just posted about AI transforming software development",
        "post_url": "https://x.com/username/status/123..."
      },
      "target": null
    }
  ],
  "count": 2
}
```

## Adding Activity Logging to New Tools

To add activity logging to a new tool:

### 1. Create Wrapper Function

```python
# In x_growth_deep_agent.py
from activity_logger import ActivityLogger

activity_logger = ActivityLogger(store, user_id)

# Original tool
original_like_tool = tool_dict["like_post"]

# Wrapped tool with logging
@tool
async def _tracked_like_post(post_identifier: str) -> str:
    """Like a post (with activity tracking)"""

    # Execute original tool
    result = await original_like_tool.ainvoke({"post_identifier": post_identifier})

    # Log activity
    status = "success" if ("successfully" in result.lower() or "❤️" in result) else "failed"
    activity_logger.log_like(
        target=post_identifier,
        status=status,
        error=result if status == "failed" else None
    )

    return result

# Replace in tool dict
tool_dict["like_post"] = _tracked_like_post
```

### 2. Add Custom Logger Method (Optional)

```python
# In activity_logger.py
def log_custom_action(self, action_name: str, details: Dict[str, Any], status: str):
    """Log a custom action"""
    return self.log_activity(
        action_type=action_name,
        status=status,
        details=details
    )
```

## Storage Configuration

### PostgreSQL Store

The Store is configured in `langgraph.json`:

```json
{
  "store": {
    "ttl": {
      "refresh_on_read": true,
      "sweep_interval_minutes": 60,
      "default_ttl": 1440  // 24 hours (in minutes)
    }
  }
}
```

### TTL (Time To Live)

- Activities older than `default_ttl` (24 hours) are automatically cleaned up
- `refresh_on_read`: true - Reading an activity extends its TTL
- `sweep_interval_minutes`: 60 - Cleanup runs every hour

### Manual Cleanup

```python
from activity_logger import ActivityLogger

logger = ActivityLogger(store, user_id)
logger.clear_old_activity(days_to_keep=30)  # Keep last 30 days
```

## Testing

### 1. Test Activity Logging

```python
import asyncio
from langgraph.store.postgres import PostgresStore
from activity_logger import ActivityLogger

# Initialize
store = PostgresStore(connection_string="postgresql://...")
logger = ActivityLogger(store, "test_user")

# Log test activity
logger.log_post(
    content="Test post content",
    status="success",
    post_url="https://x.com/test/status/123"
)

# Retrieve activities
activities = logger.get_recent_activity(limit=10)
print(f"Found {len(activities)} activities")
for activity in activities:
    print(f"- {activity['action_type']}: {activity['status']}")
```

### 2. Test API Endpoint

```bash
# Start backend
python backend_websocket_server.py

# Test endpoint
curl "http://localhost:8000/api/activity/recent/test_user?limit=10"
```

## Dashboard Integration

### Frontend Component Example

```typescript
// components/RecentActivity.tsx
import { useEffect, useState } from 'react';

interface Activity {
  id: string;
  timestamp: string;
  action_type: string;
  status: string;
  details: Record<string, any>;
  target?: string;
}

export function RecentActivity({ userId }: { userId: string }) {
  const [activities, setActivities] = useState<Activity[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchActivities() {
      const res = await fetch(`/api/activity/recent/${userId}?limit=50`);
      const data = await res.json();
      if (data.success) {
        setActivities(data.activities);
      }
      setLoading(false);
    }
    fetchActivities();
  }, [userId]);

  if (loading) return <div>Loading...</div>;

  return (
    <div className="recent-activity">
      <h2>Recent Activity</h2>
      {activities.map((activity) => (
        <ActivityItem key={activity.id} activity={activity} />
      ))}
    </div>
  );
}

function ActivityItem({ activity }: { activity: Activity }) {
  const icon = {
    post: '📝',
    comment: '💬',
    like: '❤️',
    unlike: '💔',
    web_search: '🔍',
  }[activity.action_type] || '📌';

  const timestamp = new Date(activity.timestamp).toLocaleString();

  return (
    <div className="activity-item">
      <span className="icon">{icon}</span>
      <div>
        <div className="action">
          {activity.action_type} - {activity.status}
        </div>
        <div className="time">{timestamp}</div>
        {activity.target && <div className="target">Target: {activity.target}</div>}
      </div>
    </div>
  );
}
```

## Troubleshooting

### Activities Not Showing Up

1. **Check Store Connection**
   ```python
   # Test Store connectivity
   from langgraph.store.postgres import PostgresStore
   store = PostgresStore(connection_string=os.getenv("DATABASE_URL"))
   items = list(store.search(("test_user", "activity"), limit=1))
   print(f"Store working: {len(items) >= 0}")
   ```

2. **Check Agent Logs**
   ```bash
   docker logs langgraph_api_1 | grep "📝 Logged activity"
   ```

3. **Verify API Endpoint**
   ```bash
   curl "http://localhost:8000/api/activity/recent/your_user_id"
   ```

### Activities Disappearing

- Check TTL settings in `langgraph.json`
- Default is 24 hours (1440 minutes)
- Increase `default_ttl` to keep activities longer

### Performance Issues

- Limit query results: `?limit=20` instead of `?limit=500`
- Add indexes to PostgreSQL Store (handled automatically by LangGraph)
- Run cleanup periodically: `logger.clear_old_activity(days_to_keep=7)`

## Next Steps

1. **Add more activity types**: Expand to track follows, unfollows, retweets, etc.
2. **Add filtering**: Filter by action type, status, date range
3. **Add analytics**: Success rate, activity trends, most active times
4. **Add export**: Export activities to CSV/JSON
5. **Add notifications**: Real-time activity updates via WebSocket

## References

- [LangGraph Store Docs](https://python.langchain.com/docs/langgraph/persistence)
- [DeepAgents Memory](https://python.langchain.com/docs/deepagents/long-term-memory)
- [PostgresStore API](https://python.langchain.com/docs/langgraph/reference/store)
