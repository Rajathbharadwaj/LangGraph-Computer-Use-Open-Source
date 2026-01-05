"""
Historical Data Importer

Scrapes and imports historical posts and comments from a user's X profile.
All imported data is marked with source='imported' (or 'manual' for non-agent content).

This allows tracking of engagement metrics for ALL content, not just agent-generated.

Usage:
    importer = HistoricalDataImporter(cua_client, user_id)

    # Import historical posts
    await importer.import_posts(max_posts=100)

    # Import historical comments/replies
    await importer.import_comments(max_comments=100)

    # Import both
    await importer.import_all()
"""

import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
import re


class HistoricalDataImporter:
    """
    Imports historical posts and comments from X into the database.

    Imported content is marked with source='imported' to distinguish from:
    - 'agent': AI-generated content
    - 'manual': User-posted directly (future: could be detected via timestamps)
    """

    def __init__(self, cua_client, user_id: str):
        """
        Initialize the importer.

        Args:
            cua_client: CUA client instance for browser automation
            user_id: User ID for database operations
        """
        self.client = cua_client
        self.user_id = user_id

    async def get_username(self) -> Optional[str]:
        """Get the logged-in user's X username."""
        script = """(() => {
            // Try profile link in nav
            const profileLink = document.querySelector('a[data-testid="AppTabBar_Profile_Link"]');
            if (profileLink) {
                const href = profileLink.getAttribute('href');
                return href ? href.replace('/', '') : null;
            }
            // Fallback: look in account switcher
            const accountDiv = document.querySelector('[data-testid="SideNav_AccountSwitcher_Button"]');
            if (accountDiv) {
                const spans = accountDiv.querySelectorAll('span');
                for (const span of spans) {
                    if (span.innerText.startsWith('@')) {
                        return span.innerText.slice(1);
                    }
                }
            }
            return null;
        })()"""

        result = await self.client._request("POST", "/playwright/evaluate", {"script": script})
        return result.get("result")

    async def import_posts(
        self,
        max_posts: int = 100,
        include_engagement: bool = True
    ) -> Dict[str, Any]:
        """
        Import historical posts from the user's X profile.

        Args:
            max_posts: Maximum number of posts to import
            include_engagement: Whether to scrape engagement metrics

        Returns:
            Dict with import statistics
        """
        from database.database import SessionLocal
        from database.models import UserPost, XAccount

        stats = {
            "total_found": 0,
            "imported": 0,
            "skipped_duplicate": 0,
            "errors": []
        }

        db = SessionLocal()
        try:
            # Get X account
            x_account = db.query(XAccount).filter(XAccount.user_id == self.user_id).first()
            if not x_account:
                stats["errors"].append(f"No X account found for user {self.user_id}")
                return stats

            # Get username
            username = await self.get_username()
            if not username:
                stats["errors"].append("Could not determine username")
                return stats

            print(f"📥 Importing posts for @{username}...")

            # Navigate to profile posts tab
            await self.client._request("POST", "/navigate", {"url": f"https://x.com/{username}"})
            await asyncio.sleep(3)

            imported_urls = set()
            scroll_attempts = 0
            max_scrolls = max_posts // 5 + 10  # Estimate ~5 posts per scroll

            while len(imported_urls) < max_posts and scroll_attempts < max_scrolls:
                # Extract posts from current view
                posts = await self._extract_posts_from_page(username)

                for post in posts:
                    if post.get("url") in imported_urls:
                        continue

                    imported_urls.add(post.get("url"))
                    stats["total_found"] += 1

                    # Check if already exists in our DB
                    existing = db.query(UserPost).filter(
                        UserPost.x_account_id == x_account.id,
                        UserPost.post_url == post.get("url")
                    ).first()

                    if existing:
                        # Update engagement metrics but KEEP the original source
                        # If it was created by agent, it stays as 'agent'
                        if include_engagement:
                            existing.likes = post.get("likes", 0)
                            existing.retweets = post.get("retweets", 0)
                            existing.replies = post.get("replies", 0)
                        stats["skipped_duplicate"] += 1
                        stats["updated_engagement"] = stats.get("updated_engagement", 0) + 1
                        continue

                    try:
                        # New post - check if content matches any agent post (by content similarity)
                        # This catches posts that were created by agent but URL wasn't captured
                        source = "imported"
                        content_match = db.query(UserPost).filter(
                            UserPost.x_account_id == x_account.id,
                            UserPost.source == "agent",
                            UserPost.content == post.get("content", "")
                        ).first()
                        if content_match:
                            # This post was made by agent, update it with the URL
                            content_match.post_url = post.get("url")
                            if include_engagement:
                                content_match.likes = post.get("likes", 0)
                                content_match.retweets = post.get("retweets", 0)
                                content_match.replies = post.get("replies", 0)
                            stats["matched_agent"] = stats.get("matched_agent", 0) + 1
                            continue

                        # Create new post record - truly new/manual post
                        user_post = UserPost(
                            x_account_id=x_account.id,
                            content=post.get("content", ""),
                            post_url=post.get("url"),
                            likes=post.get("likes", 0) if include_engagement else 0,
                            retweets=post.get("retweets", 0) if include_engagement else 0,
                            replies=post.get("replies", 0) if include_engagement else 0,
                            source="imported",  # Only truly new posts get 'imported'
                            posted_at=post.get("posted_at"),
                            imported_at=datetime.now(timezone.utc)
                        )
                        db.add(user_post)
                        stats["imported"] += 1

                        if stats["imported"] % 10 == 0:
                            db.commit()
                            print(f"📊 Imported {stats['imported']} posts...")

                    except Exception as e:
                        stats["errors"].append(f"Error importing post: {e}")

                # Scroll to load more
                await self.client._request("POST", "/playwright/evaluate", {
                    "script": "window.scrollBy(0, window.innerHeight * 2)"
                })
                await asyncio.sleep(2)
                scroll_attempts += 1

            db.commit()
            print(f"✅ Post import complete: {stats}")
            return stats

        finally:
            db.close()

    async def import_comments(
        self,
        max_comments: int = 100,
        include_engagement: bool = True
    ) -> Dict[str, Any]:
        """
        Import historical comments/replies from the user's X profile.

        Args:
            max_comments: Maximum number of comments to import
            include_engagement: Whether to scrape engagement metrics

        Returns:
            Dict with import statistics
        """
        from database.database import SessionLocal
        from database.models import UserComment, XAccount

        stats = {
            "total_found": 0,
            "imported": 0,
            "skipped_duplicate": 0,
            "errors": []
        }

        db = SessionLocal()
        try:
            # Get X account
            x_account = db.query(XAccount).filter(XAccount.user_id == self.user_id).first()
            if not x_account:
                stats["errors"].append(f"No X account found for user {self.user_id}")
                return stats

            # Get username
            username = await self.get_username()
            if not username:
                stats["errors"].append("Could not determine username")
                return stats

            print(f"📥 Importing comments/replies for @{username}...")

            # Navigate to profile replies tab
            await self.client._request("POST", "/navigate", {"url": f"https://x.com/{username}/with_replies"})
            await asyncio.sleep(3)

            imported_urls = set()
            scroll_attempts = 0
            max_scrolls = max_comments // 3 + 10  # Estimate ~3 replies per scroll

            while len(imported_urls) < max_comments and scroll_attempts < max_scrolls:
                # Extract replies from current view
                replies = await self._extract_replies_from_page(username)

                for reply in replies:
                    if reply.get("url") in imported_urls:
                        continue

                    imported_urls.add(reply.get("url"))
                    stats["total_found"] += 1

                    # Check if already exists in our DB (by URL)
                    existing = db.query(UserComment).filter(
                        UserComment.x_account_id == x_account.id,
                        UserComment.comment_url == reply.get("url")
                    ).first()

                    if existing:
                        # Update engagement metrics but KEEP the original source
                        # If it was created by agent, it stays as 'agent'
                        if include_engagement:
                            existing.likes = reply.get("likes", 0)
                            existing.replies = reply.get("replies", 0)
                            existing.retweets = reply.get("retweets", 0)
                            existing.last_scraped_at = datetime.now(timezone.utc)
                        stats["skipped_duplicate"] += 1
                        stats["updated_engagement"] = stats.get("updated_engagement", 0) + 1
                        continue

                    try:
                        # Check if content matches any agent comment (catches comments without captured URL)
                        content_match = db.query(UserComment).filter(
                            UserComment.x_account_id == x_account.id,
                            UserComment.source == "agent",
                            UserComment.content == reply.get("content", "")
                        ).first()
                        if content_match:
                            # This comment was made by agent, update it with the URL
                            content_match.comment_url = reply.get("url")
                            if include_engagement:
                                content_match.likes = reply.get("likes", 0)
                                content_match.replies = reply.get("replies", 0)
                                content_match.retweets = reply.get("retweets", 0)
                                content_match.last_scraped_at = datetime.now(timezone.utc)
                            stats["matched_agent"] = stats.get("matched_agent", 0) + 1
                            continue

                        # Create new comment record - truly new/manual comment
                        user_comment = UserComment(
                            x_account_id=x_account.id,
                            content=reply.get("content", ""),
                            comment_url=reply.get("url"),
                            target_post_url=reply.get("reply_to_url"),
                            target_post_author=reply.get("reply_to_author"),
                            target_post_content_preview=reply.get("reply_to_content"),
                            likes=reply.get("likes", 0) if include_engagement else 0,
                            replies=reply.get("replies", 0) if include_engagement else 0,
                            retweets=reply.get("retweets", 0) if include_engagement else 0,
                            source="imported",  # Only truly new comments get 'imported'
                            commented_at=reply.get("posted_at"),
                            scrape_status="imported",
                            last_scraped_at=datetime.now(timezone.utc)
                        )
                        db.add(user_comment)
                        stats["imported"] += 1

                        if stats["imported"] % 10 == 0:
                            db.commit()
                            print(f"📊 Imported {stats['imported']} comments...")

                    except Exception as e:
                        stats["errors"].append(f"Error importing comment: {e}")

                # Scroll to load more
                await self.client._request("POST", "/playwright/evaluate", {
                    "script": "window.scrollBy(0, window.innerHeight * 2)"
                })
                await asyncio.sleep(2)
                scroll_attempts += 1

            db.commit()
            print(f"✅ Comment import complete: {stats}")
            return stats

        finally:
            db.close()

    async def import_all(
        self,
        max_posts: int = 100,
        max_comments: int = 100
    ) -> Dict[str, Any]:
        """
        Import both posts and comments.

        Args:
            max_posts: Maximum posts to import
            max_comments: Maximum comments to import

        Returns:
            Combined results
        """
        posts_result = await self.import_posts(max_posts)
        comments_result = await self.import_comments(max_comments)

        return {
            "posts": posts_result,
            "comments": comments_result
        }

    async def _extract_posts_from_page(self, username: str) -> List[Dict[str, Any]]:
        """Extract posts from the current page view."""
        script = f'''(() => {{
            const posts = [];
            const articles = document.querySelectorAll('article[data-testid="tweet"]');

            for (const article of articles) {{
                // Check if this is user's own post (not a retweet)
                const userLink = article.querySelector('a[href="/{username}"]');
                if (!userLink) continue;

                // Skip retweets (check for both "reposted" and "retweeted")
                const retweetIndicator = article.querySelector('[data-testid="socialContext"]');
                if (retweetIndicator) {{
                    const indicatorText = retweetIndicator.innerText.toLowerCase();
                    if (indicatorText.includes('reposted') || indicatorText.includes('retweeted')) continue;
                }}

                // Get content
                const contentEl = article.querySelector('[data-testid="tweetText"]');
                const content = contentEl ? contentEl.innerText : '';

                // Also skip RT @ style retweets
                if (content.startsWith('RT @')) continue;

                // Get URL
                const timeLink = article.querySelector('time')?.parentElement;
                const url = timeLink ? 'https://x.com' + timeLink.getAttribute('href') : null;

                // Get timestamp
                const timeEl = article.querySelector('time');
                const datetime = timeEl ? timeEl.getAttribute('datetime') : null;

                // Helper to parse engagement numbers like "1,234", "1.2K", "12K", "1.5M"
                const parseEngagementNum = (label) => {{
                    if (!label) return 0;
                    const match = label.match(/([\\d,.]+)\\s*([KkMm])?/);
                    if (!match) return 0;
                    let num = parseFloat(match[1].replace(/,/g, ''));
                    const suffix = match[2]?.toUpperCase();
                    if (suffix === 'K') num *= 1000;
                    else if (suffix === 'M') num *= 1000000;
                    return Math.round(num);
                }};

                // Get engagement counts
                const getCount = (testId) => {{
                    const btn = article.querySelector(`[data-testid="${{testId}}"]`);
                    if (!btn) return 0;
                    const label = btn.getAttribute('aria-label') || '';
                    return parseEngagementNum(label);
                }};

                if (url && content) {{
                    posts.push({{
                        content,
                        url,
                        posted_at: datetime,
                        likes: getCount('like'),
                        retweets: getCount('retweet'),
                        replies: getCount('reply')
                    }});
                }}
            }}

            return posts;
        }})()'''

        result = await self.client._request("POST", "/playwright/evaluate", {"script": script})
        return result.get("result", []) if result.get("success") else []

    async def _extract_replies_from_page(self, username: str) -> List[Dict[str, Any]]:
        """Extract replies/comments from the current page view."""
        # Use case-insensitive matching for username
        script = f'''(() => {{
            const replies = [];
            const articles = document.querySelectorAll('article[data-testid="tweet"]');
            const targetUsername = "{username}".toLowerCase();

            for (const article of articles) {{
                // Check if this is user's tweet (case-insensitive)
                const allLinks = article.querySelectorAll('a[href^="/"]');
                let isUsersTweet = false;
                for (const link of allLinks) {{
                    const href = link.getAttribute('href') || '';
                    if (href.toLowerCase() === '/' + targetUsername) {{
                        isUsersTweet = true;
                        break;
                    }}
                }}
                if (!isUsersTweet) continue;

                // Check if it's a reply - look for reply context or "Replying to" in any form
                // On the with_replies page, replies show a thread indicator or parent tweet
                const hasReplyContext = article.querySelector('[data-testid="Tweet-User-Avatar-Container"]');
                const replyingToText = article.innerText.match(/Replying to|replying to|Reply to/i);
                const socialContext = article.querySelector('[data-testid="socialContext"]');

                // On with_replies page, we want ALL tweets (including replies shown in context)
                // The page itself filters to show replies, so we just extract everything by this user

                // Get content
                const contentEl = article.querySelector('[data-testid="tweetText"]');
                const content = contentEl ? contentEl.innerText : '';

                // Get URL
                const timeLink = article.querySelector('time')?.parentElement;
                const url = timeLink ? 'https://x.com' + timeLink.getAttribute('href') : null;

                // Get timestamp
                const timeEl = article.querySelector('time');
                const datetime = timeEl ? timeEl.getAttribute('datetime') : null;

                // Try to get who we're replying to from various sources
                let replyToAuthor = null;
                const replyMatch = article.innerText.match(/Replying to\\s*(@\\w+)/i);
                if (replyMatch) {{
                    replyToAuthor = replyMatch[1].slice(1);
                }}

                // Helper to parse engagement numbers like "1,234", "1.2K", "12K", "1.5M"
                const parseEngagementNum = (label) => {{
                    if (!label) return 0;
                    const match = label.match(/([\\d,.]+)\\s*([KkMm])?/);
                    if (!match) return 0;
                    let num = parseFloat(match[1].replace(/,/g, ''));
                    const suffix = match[2]?.toUpperCase();
                    if (suffix === 'K') num *= 1000;
                    else if (suffix === 'M') num *= 1000000;
                    return Math.round(num);
                }};

                // Get engagement counts
                const getCount = (testId) => {{
                    const btn = article.querySelector(`[data-testid="${{testId}}"]`);
                    if (!btn) return 0;
                    const label = btn.getAttribute('aria-label') || '';
                    return parseEngagementNum(label);
                }};

                if (url && content) {{
                    replies.push({{
                        content,
                        url,
                        posted_at: datetime,
                        reply_to_author: replyToAuthor,
                        reply_to_url: null,
                        reply_to_content: null,
                        likes: getCount('like'),
                        retweets: getCount('retweet'),
                        replies: getCount('reply'),
                        is_reply: !!replyingToText || !!replyToAuthor
                    }});
                }}
            }}

            return replies;
        }})()'''

        result = await self.client._request("POST", "/playwright/evaluate", {"script": script})
        return result.get("result", []) if result.get("success") else []


async def run_historical_import(cua_client, user_id: str, max_posts: int = 100, max_comments: int = 100) -> Dict[str, Any]:
    """
    Convenience function to run full historical import.

    Args:
        cua_client: CUA client instance
        user_id: User ID
        max_posts: Max posts to import
        max_comments: Max comments to import

    Returns:
        Combined import results
    """
    importer = HistoricalDataImporter(cua_client, user_id)
    return await importer.import_all(max_posts, max_comments)
