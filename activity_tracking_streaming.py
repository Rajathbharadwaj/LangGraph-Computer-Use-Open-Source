"""
Activity Tracking via LangGraph Streaming

This is a BETTER approach than manually wrapping tools.
Instead, tools emit custom events via stream_writer, and the backend
captures these events from the stream and saves them to the Store.

Benefits:
- No need to wrap every tool
- Clean separation of concerns
- Tools just emit events, backend handles storage
- Easy to add/remove activity tracking
"""

from datetime import datetime
from typing import Dict, Any, Optional
from langgraph.store.base import BaseStore


class StreamActivityCapture:
    """
    Captures activity events from LangGraph streams and saves to Store.

    Usage:
        # In your backend when streaming
        capture = StreamActivityCapture(store, user_id)

        async for chunk in client.runs.stream(..., stream_mode=["messages", "custom"]):
            if chunk.event == "custom":
                await capture.handle_event(chunk.data)
    """

    def __init__(self, store: BaseStore, user_id: str):
        self.store = store
        self.user_id = user_id
        self.namespace = (user_id, "activity")

    async def handle_event(self, event_data: Dict[str, Any]):
        """
        Handle a custom event from the stream.

        Expected event format:
        {
            "type": "activity_complete",
            "action": "post|comment|like|unlike|web_search",
            "status": "success|failed",
            "target": "@username or post_id (optional)",
            "details": {
                "content": "...",
                "post_url": "...",
                "error": "...",
                ...
            }
        }
        """
        # Only handle activity completion events
        if event_data.get("type") != "activity_complete":
            return

        action_type = event_data.get("action")
        status = event_data.get("status", "unknown")
        target = event_data.get("target")
        details = event_data.get("details", {})

        # Create activity log
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

        # Save to Store
        self.store.put(
            self.namespace,
            activity_id,
            activity_data
        )

        print(f"📝 [Stream] Logged activity: {action_type} - {status}")


# Helper function to emit activity events from tools
def emit_activity_event(
    action: str,
    status: str,
    target: Optional[str] = None,
    **details
):
    """
    Emit an activity event from within a tool.

    Usage in a tool:
        from langgraph.config import get_stream_writer
        from activity_tracking_streaming import emit_activity_event

        @tool
        async def my_tool(...):
            writer = get_stream_writer()

            # Do the work
            result = await do_work()

            # Emit activity event
            emit_activity_event(
                writer,
                action="post",
                status="success",
                target=None,
                content="Post text...",
                post_url="https://..."
            )

            return result

    Args:
        writer: Stream writer from get_stream_writer()
        action: Action type (post, comment, like, unlike, web_search)
        status: Status (success, failed)
        target: Target user/post (optional)
        **details: Additional details to include
    """
    from langgraph.config import get_stream_writer

    try:
        writer = get_stream_writer()
        writer({
            "type": "activity_complete",
            "action": action,
            "status": status,
            "target": target,
            "details": details
        })
    except Exception as e:
        print(f"⚠️ Failed to emit activity event: {e}")


# Example: How to modify a tool to emit events
"""
BEFORE (manual logging):
```python
@tool
async def comment_on_post(...):
    result = await do_comment(...)

    # Manual logging - TIGHT COUPLING!
    activity_logger.log_comment(...)

    return result
```

AFTER (streaming events):
```python
@tool
async def comment_on_post(author: str, comment_text: str) -> str:
    result = await do_comment(author, comment_text)

    # Emit event - backend will capture and log it!
    emit_activity_event(
        action="comment",
        status="success" if "successfully" in result.lower() else "failed",
        target=author,
        content=comment_text[:200],
        result_preview=result[:100]
    )

    return result
```

NO WRAPPING NEEDED! Just add emit_activity_event() calls.
"""
