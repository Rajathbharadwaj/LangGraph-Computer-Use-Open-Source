#!/usr/bin/env python3
"""
Async Chrome Extension Tools for LangGraph Agents
Provides direct DOM manipulation and data extraction via Chrome extension running in Docker.
These tools complement Playwright by offering capabilities Playwright doesn't have.
"""

import asyncio
from typing import List, Dict, Any, Literal
import aiohttp
import json
import os
import hashlib
from datetime import datetime, timedelta
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from langchain.chat_models import init_chat_model


class AsyncExtensionClient:
    """Async HTTP client for Chrome Extension commands - ASGI compatible"""

    def __init__(self, host: str = None, port: int = 8001):
        # Check for full URL first (for Cloud Run deployments)
        extension_url = os.getenv('EXTENSION_BACKEND_URL')
        if extension_url:
            # Use full URL directly (e.g., https://extension-backend-service-xxx.run.app)
            self.base_url = extension_url.rstrip('/')
        else:
            # Use environment variable or default to host.docker.internal for Docker compatibility
            if host is None:
                host = os.getenv('EXTENSION_BACKEND_HOST', 'host.docker.internal')
            self.base_url = f"http://{host}:{port}"
        self._session = None
    
    async def get_session(self):
        """Get or create aiohttp session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self._session
    
    async def _request(self, method: str, endpoint: str, data: dict = None) -> Dict[str, Any]:
        """Make async HTTP request to the backend (which communicates with extension)"""
        url = f"{self.base_url}{endpoint}"
        try:
            session = await self.get_session()
            
            if method.upper() == "GET":
                async with session.get(url) as response:
                    return await response.json()
            elif method.upper() == "POST":
                async with session.post(url, json=data) as response:
                    return await response.json()
        except Exception as e:
            print(f"Extension Client Request Error: {e}")
            return {"error": str(e), "success": False}
    
    async def close(self):
        """Close the session"""
        if self._session and not self._session.closed:
            await self._session.close()


# Global client instance
_global_extension_client = AsyncExtensionClient()


# ============================================================================
# POST ANALYSIS MODELS & HELPERS (Issue #16: Better Post Understanding)
# ============================================================================

class PostAnalysis(BaseModel):
    """Structured analysis of post tone and intent using Claude's extended thinking"""
    tone: Literal["sarcastic", "serious", "humorous", "inspirational", "angry", "neutral"]
    tone_confidence: float = Field(ge=0.0, le=1.0, description="Confidence in tone detection")
    intent: Literal["educational", "viral_bait", "personal_story", "hot_take",
                    "promotion", "meme", "conversation_starter", "question"]
    intent_confidence: float = Field(ge=0.0, le=1.0, description="Confidence in intent detection")
    quality_score: int = Field(ge=0, le=100, description="Overall content quality")
    originality_score: int = Field(ge=0, le=100, description="How original/derivative")
    engagement_worthy: bool = Field(description="Should we engage with this post?")
    recommended_response_type: Literal["thoughtful_comment", "quick_reaction", "question", "skip"]
    reasoning: str = Field(description="Why this analysis was reached")
    confidence: float = Field(ge=0.0, le=1.0, description="Overall analysis confidence")
    thinking_summary: str = Field(default="", description="Claude's reasoning process")


def get_cached_analysis(cache_key: str, user_id: str = None):
    """Retrieve cached post analysis from LangGraph Store"""
    if not user_id or not hasattr(_global_extension_client, 'store') or _global_extension_client.store is None:
        return None

    try:
        namespace = (user_id, "post_analyses")
        result = _global_extension_client.store.get(namespace, cache_key)
        return result.value if result else None
    except Exception as e:
        print(f"⚠️  Cache retrieval failed: {e}")
        return None


def save_to_cache(cache_key: str, analysis: dict, thinking: str, user_id: str = None, action_taken: str = "pending"):
    """Save analysis to cache with extended thinking reasoning"""
    if not user_id or not hasattr(_global_extension_client, 'store') or _global_extension_client.store is None:
        return

    try:
        namespace = (user_id, "post_analyses")
        cache_data = {
            "analysis": analysis,
            "thinking_content": thinking,
            "cached_at": datetime.now().isoformat(),
            "action_taken": action_taken,
            "outcome": None  # Will be updated later
        }
        _global_extension_client.store.put(namespace, cache_key, cache_data)
        print(f"✅ Cached analysis: {cache_key[:20]}... (action: {action_taken})")
    except Exception as e:
        print(f"⚠️  Cache save failed: {e}")


def is_recent(cached_data: dict, hours: int = 24) -> bool:
    """Check if cached data is recent enough to use"""
    try:
        cached_at = datetime.fromisoformat(cached_data.get("cached_at", "2000-01-01"))
        age = datetime.now() - cached_at
        return age.total_seconds() < (hours * 3600)
    except Exception:
        return False


def create_async_extension_tools():
    """Create async-compatible Chrome Extension tools for LangGraph agents"""
    
    @tool
    async def extract_post_engagement_data(post_identifier: str) -> str:
        """
        Extract HIDDEN engagement data from a post using Chrome extension.
        This accesses React internals that Playwright cannot see.
        
        Args:
            post_identifier: Author name or content snippet to identify the post
        
        Returns detailed engagement metrics:
        - Impressions (how many people saw it)
        - Engagement rate (likes/impressions)
        - Audience demographics
        - Virality score
        - Reply sentiment
        
        Example: extract_post_engagement_data("akshay dots-ocr")
        """
        try:
            result = await _global_extension_client._request("POST", "/extension/extract_engagement", {
                "post_identifier": post_identifier
            })
            
            if result.get("success"):
                data = result.get("data", {})
                return f"""✅ Engagement Data Extracted:
Post: {post_identifier}
Impressions: {data.get('impressions', 'N/A')}
Engagement Rate: {data.get('engagement_rate', 'N/A')}%
Likes: {data.get('likes', 0)}
Replies: {data.get('replies', 0)}
Reposts: {data.get('reposts', 0)}
Audience Type: {data.get('audience_type', 'N/A')}
Virality Score: {data.get('virality_score', 'N/A')}
Best Time to Engage: {data.get('best_time', 'N/A')}"""
            else:
                return f"❌ Failed to extract engagement data: {result.get('error', 'Unknown error')}"
        except Exception as e:
            return f"❌ Extension tool failed: {str(e)}"
    
    @tool
    async def check_rate_limit_status() -> str:
        """
        Check if X is showing rate limit warnings using Chrome extension.
        Extension monitors DOM for rate limit messages in real-time.
        
        Returns:
        - Rate limit status (active/none)
        - Time until reset
        - Recommended pause duration
        - Actions remaining (if available)
        
        Use this BEFORE performing actions to avoid bans!
        """
        try:
            result = await _global_extension_client._request("GET", "/extension/rate_limit_status")
            
            if result.get("success"):
                status = result.get("status", {})
                is_limited = status.get("is_rate_limited", False)
                
                if is_limited:
                    return f"""⚠️ RATE LIMITED!
Status: Active rate limit detected
Time until reset: {status.get('reset_time', 'Unknown')}
Recommended pause: {status.get('pause_duration', 3600)} seconds
Message: {status.get('message', 'Rate limit active')}

🛑 STOP all actions immediately!"""
                else:
                    return f"""✅ No Rate Limits Detected
Actions remaining (estimated): {status.get('actions_remaining', 'Unknown')}
Safe to continue: Yes
Last check: {status.get('last_check', 'Just now')}"""
            else:
                return f"❌ Failed to check rate limit: {result.get('error', 'Unknown error')}"
        except Exception as e:
            return f"❌ Extension tool failed: {str(e)}"
    
    @tool
    async def get_post_context(post_identifier: str) -> str:
        """
        Get FULL context of a post including hidden data using Chrome extension.
        This includes thread context, author reputation, engagement patterns.
        
        Args:
            post_identifier: Author name or content snippet
        
        Returns:
        - Full post text (including truncated parts)
        - Thread context (parent posts, replies)
        - Author reputation score
        - Author follower count
        - Post timestamp
        - Engagement velocity (likes/hour)
        - Trending status
        
        Better than Playwright because it accesses React state!
        """
        try:
            result = await _global_extension_client._request("POST", "/extension/post_context", {
                "post_identifier": post_identifier
            })
            
            if result.get("success"):
                context = result.get("context", {})
                return f"""📊 Post Context:

CONTENT:
{context.get('full_text', 'N/A')}

AUTHOR:
- Name: {context.get('author_name', 'N/A')}
- Handle: @{context.get('author_handle', 'N/A')}
- Followers: {context.get('author_followers', 'N/A')}
- Reputation: {context.get('author_reputation', 'N/A')}/100

ENGAGEMENT:
- Likes: {context.get('likes', 0)}
- Replies: {context.get('replies', 0)}
- Reposts: {context.get('reposts', 0)}
- Velocity: {context.get('engagement_velocity', 'N/A')} likes/hour
- Trending: {context.get('is_trending', False)}

THREAD:
- Is part of thread: {context.get('is_thread', False)}
- Thread position: {context.get('thread_position', 'N/A')}
- Parent post: {context.get('parent_post', 'None')}

TIMING:
- Posted: {context.get('timestamp', 'N/A')}
- Age: {context.get('age', 'N/A')}"""
            else:
                return f"❌ Failed to get post context: {result.get('error', 'Unknown error')}"
        except Exception as e:
            return f"❌ Extension tool failed: {str(e)}"
    
    @tool
    async def human_like_click(element_description: str) -> str:
        """
        Click an element with HUMAN-LIKE behavior using Chrome extension.
        Adds realistic delays, micro-movements, and event sequences.
        
        Args:
            element_description: Description of element to click (e.g., "like button on post by akshay")
        
        This is MORE STEALTHY than Playwright because:
        - Random micro-movements before click
        - Realistic event sequence (mouseover → mousedown → click)
        - Human-like timing variations
        - Dispatches events that look natural
        
        Use this for important actions where stealth matters!
        """
        try:
            result = await _global_extension_client._request("POST", "/extension/human_click", {
                "element_description": element_description
            })
            
            if result.get("success"):
                details = result.get("details", {})
                return f"""✅ Human-like click executed!
Element: {element_description}
Click position: ({details.get('x', 'N/A')}, {details.get('y', 'N/A')})
Delay before click: {details.get('delay_ms', 'N/A')}ms
Event sequence: {details.get('event_sequence', 'N/A')}
Stealth score: {details.get('stealth_score', 'N/A')}/100

Action completed naturally! 🎭"""
            else:
                return f"❌ Failed to click: {result.get('error', 'Unknown error')}"
        except Exception as e:
            return f"❌ Extension tool failed: {str(e)}"
    
    @tool
    async def monitor_action_result(action_type: str, timeout_seconds: int = 5) -> str:
        """
        Monitor DOM for action result using Chrome extension's mutation observer.
        Provides INSTANT feedback when actions succeed/fail.
        
        Args:
            action_type: Type of action to monitor ("like", "comment", "repost", "follow")
            timeout_seconds: How long to wait for result
        
        Returns instant confirmation:
        - Success/failure status
        - UI changes detected
        - Error messages (if any)
        - New state of element
        
        Much FASTER than Playwright's wait + re-query approach!
        """
        try:
            result = await _global_extension_client._request("POST", "/extension/monitor_action", {
                "action_type": action_type,
                "timeout": timeout_seconds
            })
            
            if result.get("success"):
                monitoring = result.get("monitoring", {})
                action_succeeded = monitoring.get("action_succeeded", False)
                
                if action_succeeded:
                    return f"""✅ Action Confirmed: {action_type}
Status: Success
Detected changes: {monitoring.get('detected_changes', 'N/A')}
New state: {monitoring.get('new_state', 'N/A')}
Response time: {monitoring.get('response_time_ms', 'N/A')}ms

Action verified through DOM mutation observer! 🎯"""
                else:
                    return f"""❌ Action Failed: {action_type}
Status: Failed
Error detected: {monitoring.get('error_message', 'Unknown')}
UI state: {monitoring.get('ui_state', 'N/A')}
Possible reason: {monitoring.get('failure_reason', 'Unknown')}

Action did not complete successfully! ⚠️"""
            else:
                return f"❌ Failed to monitor action: {result.get('error', 'Unknown error')}"
        except Exception as e:
            return f"❌ Extension tool failed: {str(e)}"
    
    @tool
    async def extract_account_insights(username: str) -> str:
        """
        Extract detailed account insights using Chrome extension.
        Accesses data that Playwright cannot see.
        
        Args:
            username: X username (without @)
        
        Returns:
        - Follower growth rate
        - Engagement rate
        - Top performing post types
        - Posting frequency
        - Audience demographics
        - Best times to post
        - Account health score
        
        Use this to decide if an account is worth engaging with!
        """
        try:
            result = await _global_extension_client._request("POST", "/extension/account_insights", {
                "username": username
            })
            
            if result.get("success"):
                insights = result.get("insights", {})
                return f"""📈 Account Insights: @{username}

GROWTH:
- Followers: {insights.get('followers', 'N/A')}
- Growth rate: {insights.get('growth_rate', 'N/A')}%/month
- Follower quality: {insights.get('follower_quality', 'N/A')}/100

ENGAGEMENT:
- Average likes: {insights.get('avg_likes', 'N/A')}
- Average replies: {insights.get('avg_replies', 'N/A')}
- Engagement rate: {insights.get('engagement_rate', 'N/A')}%
- Reply rate: {insights.get('reply_rate', 'N/A')}%

CONTENT:
- Posting frequency: {insights.get('posting_frequency', 'N/A')} posts/day
- Top post type: {insights.get('top_post_type', 'N/A')}
- Best time to post: {insights.get('best_time', 'N/A')}
- Content quality: {insights.get('content_quality', 'N/A')}/100

AUDIENCE:
- Primary demographic: {insights.get('primary_demographic', 'N/A')}
- Geographic focus: {insights.get('geographic_focus', 'N/A')}
- Interest categories: {insights.get('interests', 'N/A')}

RECOMMENDATION:
- Worth engaging: {insights.get('worth_engaging', 'Unknown')}
- Engagement priority: {insights.get('priority', 'N/A')}/10
- Reason: {insights.get('recommendation_reason', 'N/A')}"""
            else:
                return f"❌ Failed to extract insights: {result.get('error', 'Unknown error')}"
        except Exception as e:
            return f"❌ Extension tool failed: {str(e)}"
    
    @tool
    async def check_session_health() -> str:
        """
        Check if browser session is healthy using Chrome extension.
        Monitors for session expiration, login issues, or bans.
        
        Returns:
        - Login status
        - Session validity
        - Account status (active/restricted/banned)
        - Cookies status
        - Recommended actions
        
        Use this periodically to ensure agent stays authenticated!
        """
        try:
            result = await _global_extension_client._request("GET", "/extension/session_health")
            
            if result.get("success"):
                health = result.get("health", {})
                is_healthy = health.get("is_healthy", False)
                
                if is_healthy:
                    return f"""✅ Session Healthy
Login status: Logged in
Account: @{health.get('username', 'Unknown')}
Session age: {health.get('session_age', 'N/A')}
Cookies valid: {health.get('cookies_valid', 'Unknown')}
Account status: {health.get('account_status', 'Active')}

Safe to continue operations! 🟢"""
                else:
                    return f"""⚠️ Session Issues Detected!
Login status: {health.get('login_status', 'Unknown')}
Issue: {health.get('issue', 'Unknown')}
Account status: {health.get('account_status', 'Unknown')}
Recommended action: {health.get('recommended_action', 'Re-authenticate')}

🛑 Session needs attention!"""
            else:
                return f"❌ Failed to check session: {result.get('error', 'Unknown error')}"
        except Exception as e:
            return f"❌ Extension tool failed: {str(e)}"

    @tool
    async def check_premium_status() -> str:
        """
        Check if the current X account has Premium/Blue subscription.
        This determines the character limit for posts and comments.

        Returns:
        - is_premium: Boolean indicating if account has Premium
        - character_limit: 280 for non-premium, 25000 for premium
        - detection_method: How premium status was detected

        IMPORTANT: Call this BEFORE posting or commenting to validate character limits!
        """
        try:
            result = await _global_extension_client._request("GET", "/extension/premium_status")

            if result.get("success"):
                is_premium = result.get("is_premium", False)
                char_limit = result.get("character_limit", 280)
                detection = result.get("detection_method", "none")

                if is_premium:
                    return f"""✅ X Premium Account Detected
Character Limit: {char_limit:,} characters
Detection Method: {detection}

You can post up to 25,000 characters! 💎"""
                else:
                    return f"""📝 Standard X Account
Character Limit: {char_limit} characters
Detection Method: {detection}

Posts and comments must be ≤ 280 characters."""
            else:
                # Default to non-premium if check fails (safer to be conservative)
                return f"""⚠️ Could not detect premium status: {result.get('error', 'Unknown error')}
Defaulting to standard account limits (280 characters) to be safe."""
        except Exception as e:
            # Default to non-premium if error (safer)
            return f"❌ Extension tool failed: {str(e)}. Defaulting to 280 character limit."

    @tool
    async def get_trending_topics() -> str:
        """
        Get current trending topics using Chrome extension.
        Accesses X's trending sidebar data.
        
        Returns:
        - Trending hashtags
        - Trending topics
        - Tweet volume for each
        - Category (politics, tech, entertainment, etc.)
        - Relevance to user's niche
        
        Use this to find opportunities for engagement!
        """
        try:
            result = await _global_extension_client._request("GET", "/extension/trending_topics")
            
            if result.get("success"):
                topics = result.get("topics", [])
                
                if topics:
                    trending_list = []
                    for i, topic in enumerate(topics[:10], 1):
                        trending_list.append(f"""
{i}. {topic.get('name', 'N/A')}
   Category: {topic.get('category', 'N/A')}
   Volume: {topic.get('volume', 'N/A')} posts
   Relevance: {topic.get('relevance_score', 'N/A')}/10""")
                    
                    return f"""🔥 Trending Now:\n{''.join(trending_list)}

Use these topics to find engagement opportunities!"""
                else:
                    return "No trending topics found"
            else:
                return f"❌ Failed to get trending topics: {result.get('error', 'Unknown error')}"
        except Exception as e:
            return f"❌ Extension tool failed: {str(e)}"
    
    @tool
    async def find_high_engagement_posts(topic: str, limit: int = 10) -> str:
        """
        Find high-engagement posts on a topic using Chrome extension.
        Searches and ranks posts by engagement potential.
        
        Args:
            topic: Topic or keyword to search for
            limit: Number of posts to return (default 10)
        
        Returns posts ranked by:
        - Engagement velocity (likes/hour)
        - Author reputation
        - Reply potential
        - Virality score
        
        Use this to find the BEST posts to engage with!
        """
        try:
            result = await _global_extension_client._request("POST", "/extension/find_posts", {
                "topic": topic,
                "limit": limit,
                "sort_by": "engagement"
            })
            
            if result.get("success"):
                posts = result.get("posts", [])
                
                if posts:
                    post_list = []
                    for i, post in enumerate(posts, 1):
                        post_list.append(f"""
{i}. @{post.get('author', 'Unknown')} ({post.get('author_followers', 'N/A')} followers)
   "{post.get('content_preview', 'N/A')[:100]}..."
   Engagement: {post.get('likes', 0)} likes, {post.get('replies', 0)} replies
   Velocity: {post.get('velocity', 'N/A')} likes/hour
   Engagement score: {post.get('engagement_score', 'N/A')}/100
   Reply potential: {post.get('reply_potential', 'N/A')}/10""")
                    
                    return f"""🎯 High-Engagement Posts on "{topic}":\n{''.join(post_list)}

These posts have the highest engagement potential!"""
                else:
                    return f"No high-engagement posts found for topic: {topic}"
            else:
                return f"❌ Failed to find posts: {result.get('error', 'Unknown error')}"
        except Exception as e:
            return f"❌ Extension tool failed: {str(e)}"

    @tool
    async def comment_on_post_via_extension(post_identifier: str, comment_text: str) -> str:
        """
        Comment on a post using Chrome extension - MORE RELIABLE than Playwright.
        Uses article context and data-testid selectors to avoid the issues with Y-coordinate matching.

        Args:
            post_identifier: Author name or content snippet to identify the post (e.g., "@elonmusk SpaceX")
            comment_text: The text of your comment/reply (max 280 characters for non-premium accounts)

        Returns:
        - Success/failure status
        - Verification that comment was posted
        - Error details if failed

        Example: comment_on_post_via_extension("akshay dots-ocr", "Great work on this!")

        ⚡ This is the PREFERRED method for commenting - much more accurate than Playwright!
        """
        try:
            # Check if comment is empty first
            if len(comment_text.strip()) == 0:
                return "❌ Comment is empty! Please provide text content."

            # Check premium status to determine character limit
            premium_check = await _global_extension_client._request("GET", "/extension/premium_status")
            char_limit = 280  # Default to non-premium
            if premium_check.get("success"):
                char_limit = premium_check.get("character_limit", 280)

            # Validate comment length BEFORE posting
            if len(comment_text) > char_limit:
                account_type = "premium" if char_limit == 25000 else "non-premium"
                return f"""❌ Comment Too Long!
Length: {len(comment_text)} characters
Max: {char_limit:,} characters (for {account_type} X accounts)
Exceeds by: {len(comment_text) - char_limit} characters

Please SHORTEN your comment and try again."""

            result = await _global_extension_client._request("POST", "/extension/comment", {
                "post_identifier": post_identifier,
                "comment_text": comment_text
            })

            if result.get("success"):
                verified = result.get("verified", False)
                status_emoji = "✅" if verified else "⚠️"

                return f"""{status_emoji} Comment Posted!
Post: "{post_identifier}"
Comment: "{comment_text}"
Verified in thread: {verified}

{result.get('message', 'Comment posted successfully')}"""
            else:
                error = result.get("error", "Unknown error")
                return f"""❌ Comment Failed!
Post: "{post_identifier}"
Comment: "{comment_text}"
Error: {error}

Common issues:
- Post not found in timeline (try scrolling to it first)
- Rate limit hit (wait a few minutes)
- Reply dialog didn't open (X UI issue)"""
        except Exception as e:
            return f"❌ Extension tool failed: {str(e)}"

    @tool
    async def create_post_via_extension(post_text: str) -> str:
        """
        Create a new post on X (Twitter) using Chrome extension - MOST RELIABLE method.
        
        This tool:
        - Navigates to X home timeline
        - Clicks the compose box
        - Types your post text
        - Clicks "Post" button
        - Verifies post was published
        
        Args:
            post_text: The text content of your post (max 280 characters)
        
        Returns:
        - Success/failure status
        - Post text and timestamp
        - Error details if failed
        
        Example: create_post_via_extension("Just shipped a new feature! 🚀")
        
        ⚡ This is the PREFERRED method for posting - uses the Docker VNC extension!
        """
        try:
            # Check if post is empty first
            if len(post_text.strip()) == 0:
                return "❌ Post is empty! Please provide text content."

            # Check premium status to determine character limit
            premium_check = await _global_extension_client._request("GET", "/extension/premium_status")
            char_limit = 280  # Default to non-premium
            if premium_check.get("success"):
                char_limit = premium_check.get("character_limit", 280)

            # Validate post length BEFORE posting
            if len(post_text) > char_limit:
                account_type = "premium" if char_limit == 25000 else "non-premium"
                return f"""❌ Post Too Long!
Length: {len(post_text)} characters
Max: {char_limit:,} characters (for {account_type} X accounts)
Exceeds by: {len(post_text) - char_limit} characters

Please SHORTEN your post and try again."""

            # Use the Docker VNC extension (the one without cookies) for automation
            # First, get status to find which extension is connected
            status = await _global_extension_client._request("GET", "/status", {})
            
            # Find the Docker VNC extension (the one without cookies - used for automation)
            docker_user_id = None
            if status.get("users_with_info"):
                for user in status["users_with_info"]:
                    # Docker VNC extension doesn't have cookies (gets them from host extension)
                    if not user.get("hasCookies", True):
                        docker_user_id = user["userId"]
                        break
            
            # Fallback to any connected user if no Docker extension found
            if not docker_user_id and status.get("connected_users"):
                docker_user_id = status["connected_users"][0]
            
            if not docker_user_id:
                return "❌ No Docker VNC extension connected! Please ensure the Docker VNC browser is running."
            
            result = await _global_extension_client._request("POST", "/extension/create-post", {
                "post_text": post_text,
                "user_id": docker_user_id
            })

            if result.get("success"):
                timestamp = result.get("timestamp", "")
                return f"""✅ Post Created Successfully!

Post: "{post_text}"
Length: {len(post_text)} characters
Timestamp: {timestamp}

{result.get('message', 'Your post is now live on X!')}"""
            else:
                error = result.get("error", "Unknown error")
                warning = result.get("warning", "")
                
                return f"""❌ Post Creation Failed!
Post: "{post_text}"
Error: {error}
{warning}

Common issues:
- Not on home timeline (extension navigates automatically)
- Post button disabled (check character count)
- Rate limit hit (wait a few minutes)
- Not logged in (check VNC viewer)"""
        except Exception as e:
            return f"❌ Extension tool failed: {str(e)}"

    @tool
    async def analyze_post_tone_and_intent(
        post_text: str,
        author_handle: str,
        author_followers: int = 0,
        engagement_metrics: str = None,
        post_age: str = "unknown",
        thread_context: str = None
    ) -> str:
        """
        Deeply analyze a post's tone, intent, and engagement-worthiness using Claude's extended thinking.

        This tool uses extended thinking to reason about:
        - Tone (sarcastic, serious, humorous, inspirational, angry, neutral)
        - Intent (educational, viral bait, meme, promotion, etc.)
        - Quality and originality
        - Whether the post is worth engaging with

        Returns JSON with structured analysis including thinking summary.
        """
        try:
            import time
            start_time = time.time()

            # Get user_id from runtime if available (for caching)
            user_id = None
            if hasattr(_global_extension_client, 'store') and _global_extension_client.store:
                # Try to extract user_id from store namespace
                user_id = "default"  # Fallback

            # Check cache first
            cache_key = f"{author_handle}_{hashlib.md5(post_text.encode()).hexdigest()[:16]}"
            cached = get_cached_analysis(cache_key, user_id)

            if cached and is_recent(cached, hours=24):
                print(f"✅ Using cached analysis for {author_handle} (saved API call)")
                duration = time.time() - start_time
                print(f"⏱️  Cache retrieval: {duration:.2f}s")
                return json.dumps(cached["analysis"], indent=2)

            # Initialize model with extended thinking (LangGraph way)
            print(f"🧠 Analyzing post from @{author_handle} with extended thinking...")

            model = init_chat_model(
                "claude-sonnet-4-5-20250929",
                model_provider="anthropic",
                temperature=0.7,
                model_kwargs={
                    "thinking": {
                        "type": "enabled",
                        "budget_tokens": 1500
                    }
                }
            )

            # Build analysis prompt
            analysis_prompt = f"""Analyze this X (Twitter) post deeply to determine if it's worth engaging with.

POST CONTENT:
"{post_text}"

AUTHOR: @{author_handle} ({author_followers:,} followers)
ENGAGEMENT: {engagement_metrics or 'Unknown'}
POSTED: {post_age}
{f"THREAD CONTEXT: {thread_context}" if thread_context else ""}

ANALYZE DEEPLY:

1. TONE: Is this sarcastic, serious, humorous, inspirational, angry, or neutral?
   - What emotional undertone exists?
   - Is the author being genuine or performative?

2. INTENT: What is the author trying to achieve?
   - Educational: Teaching something valuable
   - Viral Bait: Designed for engagement/outrage
   - Personal Story: Sharing experience
   - Hot Take: Controversial opinion
   - Promotion: Selling something
   - Meme: Joke/humor
   - Conversation Starter: Genuine question
   - Question: Asking for help/input

3. QUALITY: Is this original content or spam?
   - Does it provide value or noise?
   - Thoughtful or low-effort?
   - Original insight or derivative?

4. ENGAGEMENT DECISION: Should we engage?
   - If yes, what type of comment is appropriate?
   - If no, why not?

Think deeply about nuances, context, subtext, and what's NOT said. Consider cultural context, memes, and online communication patterns.

OUTPUT ONLY VALID JSON in this exact format (no markdown, no code blocks):
{{
    "tone": "sarcastic" | "serious" | "humorous" | "inspirational" | "angry" | "neutral",
    "tone_confidence": 0.0-1.0,
    "intent": "educational" | "viral_bait" | "personal_story" | "hot_take" | "promotion" | "meme" | "conversation_starter" | "question",
    "intent_confidence": 0.0-1.0,
    "quality_score": 0-100,
    "originality_score": 0-100,
    "engagement_worthy": true | false,
    "recommended_response_type": "thoughtful_comment" | "quick_reaction" | "question" | "skip",
    "reasoning": "2-3 sentence explanation of your analysis",
    "confidence": 0.0-1.0
}}"""

            # Invoke model with extended thinking
            response = model.invoke(analysis_prompt)

            # Extract thinking + analysis
            thinking_content = ""
            analysis_text = ""

            # Access content_blocks for extended thinking
            if hasattr(response, 'content'):
                # Handle different response formats
                if isinstance(response.content, list):
                    for block in response.content:
                        if isinstance(block, dict):
                            if block.get("type") == "thinking":
                                thinking_content = block.get("thinking", "")
                            elif block.get("type") == "text":
                                analysis_text = block.get("text", "")
                        else:
                            # Handle AIMessageChunk or similar
                            if hasattr(block, 'type') and block.type == "thinking":
                                thinking_content = getattr(block, 'thinking', '')
                            elif hasattr(block, 'type') and block.type == "text":
                                analysis_text = getattr(block, 'text', '')
                elif isinstance(response.content, str):
                    analysis_text = response.content

            # Fallback: if no analysis_text, try to get from response directly
            if not analysis_text and hasattr(response, 'content'):
                if isinstance(response.content, str):
                    analysis_text = response.content

            # Parse JSON response
            try:
                # Clean up any markdown code blocks if present
                if "```json" in analysis_text:
                    analysis_text = analysis_text.split("```json")[1].split("```")[0].strip()
                elif "```" in analysis_text:
                    analysis_text = analysis_text.split("```")[1].split("```")[0].strip()

                analysis = json.loads(analysis_text)
                analysis["thinking_summary"] = thinking_content[:500] if thinking_content else "Extended thinking not available"

                # Validate required fields
                required_fields = ["tone", "intent", "engagement_worthy", "confidence", "reasoning"]
                for field in required_fields:
                    if field not in analysis:
                        raise ValueError(f"Missing required field: {field}")

            except (json.JSONDecodeError, ValueError) as e:
                print(f"⚠️  JSON parsing failed: {e}")
                print(f"Raw response: {analysis_text[:200]}...")
                # Fallback heuristic analysis
                analysis = fallback_heuristic_analysis(post_text, thinking_content)

            # Log analysis duration
            duration = time.time() - start_time
            print(f"✅ Analysis complete: {duration:.2f}s")
            print(f"   Tone: {analysis.get('tone')} (confidence: {analysis.get('tone_confidence', 0):.2f})")
            print(f"   Intent: {analysis.get('intent')} (confidence: {analysis.get('intent_confidence', 0):.2f})")
            print(f"   Engagement worthy: {analysis.get('engagement_worthy')}")
            print(f"   Reasoning: {analysis.get('reasoning', '')[:100]}...")

            # Cache result
            save_to_cache(cache_key, analysis, thinking_content, user_id, action_taken="analyzed")

            return json.dumps(analysis, indent=2)

        except Exception as e:
            print(f"❌ analyze_post_tone_and_intent failed: {e}")
            import traceback
            traceback.print_exc()

            # Return fallback analysis
            fallback = {
                "tone": "neutral",
                "tone_confidence": 0.3,
                "intent": "conversation_starter",
                "intent_confidence": 0.3,
                "quality_score": 50,
                "originality_score": 50,
                "engagement_worthy": True,
                "recommended_response_type": "thoughtful_comment",
                "reasoning": f"Analysis failed with error: {str(e)}. Defaulting to neutral, low-confidence assessment.",
                "confidence": 0.3,
                "thinking_summary": "Error during analysis"
            }
            return json.dumps(fallback, indent=2)

    # Helper function for fallback heuristic analysis
    def fallback_heuristic_analysis(post_text: str, thinking_content: str = "") -> dict:
        """Simple rule-based analysis if extended thinking fails"""
        text_lower = post_text.lower()

        # Detect obvious spam/promotion
        if any(keyword in text_lower for keyword in ["link in bio", "dm me", "check out", "buy now", "limited time"]):
            return {
                "tone": "neutral",
                "tone_confidence": 0.7,
                "intent": "promotion",
                "intent_confidence": 0.8,
                "quality_score": 20,
                "originality_score": 10,
                "engagement_worthy": False,
                "recommended_response_type": "skip",
                "reasoning": "Detected promotional language - likely spam or self-promotion",
                "confidence": 0.7,
                "thinking_summary": thinking_content[:500] if thinking_content else "Fallback heuristic used"
            }

        # Detect questions
        if "?" in post_text and len(post_text) < 280:
            return {
                "tone": "serious",
                "tone_confidence": 0.6,
                "intent": "question",
                "intent_confidence": 0.7,
                "quality_score": 60,
                "originality_score": 50,
                "engagement_worthy": True,
                "recommended_response_type": "thoughtful_comment",
                "reasoning": "Question detected - likely seeking genuine input",
                "confidence": 0.6,
                "thinking_summary": thinking_content[:500] if thinking_content else "Fallback heuristic used"
            }

        # Default: neutral, moderate confidence
        return {
            "tone": "neutral",
            "tone_confidence": 0.5,
            "intent": "conversation_starter",
            "intent_confidence": 0.5,
            "quality_score": 50,
            "originality_score": 50,
            "engagement_worthy": True,
            "recommended_response_type": "thoughtful_comment",
            "reasoning": "Fallback analysis - no strong signals detected. Defaulting to cautious engagement.",
            "confidence": 0.5,
            "thinking_summary": thinking_content[:500] if thinking_content else "Fallback heuristic used"
        }

    # Return all extension tools
    return [
        extract_post_engagement_data,
        check_rate_limit_status,
        get_post_context,
        human_like_click,
        monitor_action_result,
        extract_account_insights,
        check_session_health,
        check_premium_status,
        get_trending_topics,
        find_high_engagement_posts,
        comment_on_post_via_extension,
        create_post_via_extension,
        analyze_post_tone_and_intent  # NEW: Issue #16 - Post tone analysis with extended thinking
    ]


# Main function to get all async extension tools
def get_async_extension_tools() -> List[Any]:
    """Get all async Chrome Extension tools for LangGraph agents"""
    return create_async_extension_tools()


if __name__ == "__main__":
    # Test the async tools
    async def test_async_extension_tools():
        """Test the async Chrome Extension tools"""
        print("🧪 Testing Async Chrome Extension Tools...")
        
        tools = get_async_extension_tools()
        print(f"✅ Created {len(tools)} async extension tools")
        
        # List all tools
        for tool in tools:
            print(f"  - {tool.name}: {tool.description[:80]}...")
        
        # Cleanup
        await _global_extension_client.close()
    
    asyncio.run(test_async_extension_tools())

