"""
Activity Logger for X Growth Agent

Tracks all agent actions (posts, comments, likes, etc.) to the LangGraph Store
for display on the dashboard's "Recent Activity" section.

Activity logs are stored in the Store under namespace: (user_id, "activity")
Each activity is a JSON document with:
- id: Unique activity ID (timestamp-based)
- timestamp: ISO format timestamp
- action_type: "post", "comment", "like", "unlike", "search", etc.
- status: "success" or "failed"
- details: Action-specific details
- target: Target user/post (if applicable)
"""

import json
from datetime import datetime
from typing import Dict, Any, Optional
from langgraph.store.base import BaseStore


class ActivityLogger:
    """Logs agent activities to LangGraph Store for dashboard display"""

    def __init__(self, store: BaseStore, user_id: str):
        """
        Initialize activity logger

        Args:
            store: LangGraph Store instance (PostgresStore in production)
            user_id: User ID to namespace the activity logs
        """
        self.store = store
        self.user_id = user_id
        self.namespace = (user_id, "activity")

    def log_activity(
        self,
        action_type: str,
        status: str,
        details: Dict[str, Any],
        target: Optional[str] = None
    ) -> str:
        """
        Log an activity to the Store

        Args:
            action_type: Type of action ("post", "comment", "like", "unlike", "search", "web_search")
            status: "success" or "failed"
            details: Action-specific details (content, post_id, error message, etc.)
            target: Target user or post (e.g., "@elonmusk", "post_id_123")

        Returns:
            Activity ID (key in the store)
        """
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

        # Save to store
        print(f"🔍 [ActivityLogger] Storing to namespace={self.namespace}, key={activity_id}")
        print(f"🔍 [ActivityLogger] Data: {activity_data}")
        try:
            self.store.put(
                self.namespace,
                activity_id,
                activity_data
            )
            print(f"✅ [ActivityLogger] Successfully stored to database: {action_type} - {status}")
        except Exception as e:
            print(f"❌ [ActivityLogger] FAILED to store activity: {e}")
            import traceback
            traceback.print_exc()
            raise

        return activity_id

    def log_post(self, content: str, status: str, post_url: Optional[str] = None, error: Optional[str] = None):
        """Log a post creation"""
        details = {
            "content": content[:200],  # Truncate for storage
            "post_url": post_url
        }
        if error:
            details["error"] = error

        return self.log_activity(
            action_type="post",
            status=status,
            details=details
        )

    def log_comment(self, target: str, content: str, status: str, error: Optional[str] = None):
        """Log a comment"""
        details = {
            "content": content[:200],
            "on_post": target
        }
        if error:
            details["error"] = error

        return self.log_activity(
            action_type="comment",
            status=status,
            details=details,
            target=target
        )

    def log_like(self, target: str, status: str, error: Optional[str] = None):
        """Log a like"""
        details = {}
        if error:
            details["error"] = error

        return self.log_activity(
            action_type="like",
            status=status,
            details=details,
            target=target
        )

    def log_unlike(self, target: str, status: str, error: Optional[str] = None):
        """Log an unlike"""
        details = {}
        if error:
            details["error"] = error

        return self.log_activity(
            action_type="unlike",
            status=status,
            details=details,
            target=target
        )

    def log_web_search(self, query: str, results_count: int, status: str):
        """Log a web search"""
        details = {
            "query": query,
            "results_count": results_count
        }

        return self.log_activity(
            action_type="web_search",
            status=status,
            details=details
        )

    def get_recent_activity(self, limit: int = 50) -> list:
        """
        Get recent activity logs

        Args:
            limit: Maximum number of activities to return

        Returns:
            List of activity dictionaries, sorted by timestamp (newest first)
        """
        try:
            # Search all activities in this namespace
            items = list(self.store.search(
                self.namespace,
                limit=limit
            ))

            # Extract activity data and sort by timestamp
            activities = [item.value for item in items]
            activities.sort(
                key=lambda x: x.get("timestamp", ""),
                reverse=True  # Newest first
            )

            return activities[:limit]

        except Exception as e:
            print(f"❌ Error retrieving activity logs: {e}")
            return []

    def clear_old_activity(self, days_to_keep: int = 30):
        """
        Clear activity logs older than specified days

        Args:
            days_to_keep: Number of days to keep (default: 30)
        """
        try:
            cutoff_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            cutoff_timestamp = cutoff_date.isoformat()

            # Get all activities
            all_items = list(self.store.search(self.namespace, limit=1000))

            deleted_count = 0
            for item in all_items:
                activity = item.value
                if activity.get("timestamp", "") < cutoff_timestamp:
                    self.store.delete(self.namespace, activity["id"])
                    deleted_count += 1

            if deleted_count > 0:
                print(f"🗑️ Cleared {deleted_count} old activity logs (older than {days_to_keep} days)")

        except Exception as e:
            print(f"❌ Error clearing old activity logs: {e}")


# Utility functions for easy access

def create_activity_logger(store: BaseStore, user_id: str) -> ActivityLogger:
    """Create an activity logger instance"""
    return ActivityLogger(store, user_id)
