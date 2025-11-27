#!/usr/bin/env python3
"""
Like Statistics Tool - Query liking activity and statistics
"""

from typing import Dict, Any
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field
import json


class StatsInput(BaseModel):
    """Input for the stats tool"""
    format_type: str = Field(
        default="summary",
        description="Format type: 'summary', 'detailed', 'json', or 'count'"
    )


class LikeStatsQueryTool(BaseTool):
    """Tool to query current like statistics and activity"""
    
    name: str = "get_like_statistics"
    description: str = """
    📊 GET LIKE STATISTICS - Query current liking activity and statistics.
    
    Returns information about:
    - Total number of posts liked in this session
    - List of users whose posts were liked
    - Platforms where likes occurred
    - Recent post content and details
    - Timestamps and coordinates
    
    Use this to check your liking activity or get a summary of actions taken.
    """
    args_schema: type = StatsInput
    
    def __init__(self, like_tool_instance=None):
        super().__init__()
        object.__setattr__(self, '_like_tool', like_tool_instance)
    
    def set_like_tool(self, like_tool_instance):
        """Set the like tool instance to query stats from"""
        object.__setattr__(self, '_like_tool', like_tool_instance)
    
    def _run(self, format_type: str = "summary") -> str:
        """Get like statistics in the requested format"""
        
        if not self._like_tool:
            return "❌ No like tool instance available for statistics"
        
        try:
            stats = self._like_tool.get_like_statistics()
            
            if format_type == "count":
                return f"📊 Total likes: {stats['total_likes']}"
            
            elif format_type == "json":
                return json.dumps(stats, indent=2)
            
            elif format_type == "detailed":
                return self._format_detailed_stats(stats)
            
            else:  # summary (default)
                return self._format_summary_stats(stats)
                
        except Exception as e:
            return f"❌ Error retrieving statistics: {str(e)}"
    
    def _format_summary_stats(self, stats: Dict[str, Any]) -> str:
        """Format statistics as a summary"""
        
        if stats['total_likes'] == 0:
            return "📊 No posts liked yet in this session."
        
        recent_posts = stats['liked_posts'][-3:] if len(stats['liked_posts']) > 3 else stats['liked_posts']
        recent_summary = []
        
        for post in recent_posts:
            user = post.get('username', 'unknown')
            content = post.get('content', 'No content')[:40] + "..."
            platform = post.get('platform', 'unknown')
            recent_summary.append(f"  • @{user} on {platform}: {content}")
        
        summary = f"""📊 **LIKE STATISTICS SUMMARY**
        
🎯 **Session Overview:**
  • Total likes: {stats['total_likes']}
  • Unique users: {len(stats['users_liked'])}
  • Platforms: {', '.join(stats['platforms_used'])}
  • Session started: {stats['session_start'][:19]}

👤 **Users Liked:** {', '.join(list(stats['users_liked'])[:5])}{"..." if len(stats['users_liked']) > 5 else ""}

📝 **Recent Activity:**
{chr(10).join(recent_summary)}
        """
        
        return summary
    
    def _format_detailed_stats(self, stats: Dict[str, Any]) -> str:
        """Format statistics with full details"""
        
        if stats['total_likes'] == 0:
            return "📊 No posts liked yet in this session."
        
        detailed = f"""📊 **DETAILED LIKE STATISTICS**

🎯 **Session Overview:**
  • Total likes: {stats['total_likes']}
  • Unique users liked: {len(stats['users_liked'])}
  • Platforms used: {', '.join(stats['platforms_used'])}
  • Session started: {stats['session_start']}

👥 **All Users Liked:** 
{', '.join(stats['users_liked'])}

📝 **All Liked Posts:**
        """
        
        for i, post in enumerate(stats['liked_posts'], 1):
            user = post.get('username', 'unknown')
            content = post.get('content', 'No content')[:60] + "..."
            platform = post.get('platform', 'unknown')
            timestamp = post.get('timestamp', '')[:19]
            coords = post.get('coordinates', {})
            
            detailed += f"""
{i}. @{user} on {platform} at {timestamp}
   Content: {content}
   Clicked at: ({coords.get('x', '?')}, {coords.get('y', '?')})
            """
        
        return detailed


# Factory function to create the stats tool
def create_like_stats_tool(like_tool_instance=None):
    """Create a like statistics tool"""
    return LikeStatsQueryTool(like_tool_instance)


if __name__ == "__main__":
    # Test the tool
    tool = LikeStatsQueryTool()
    result = tool._run("summary")
    print(result)
