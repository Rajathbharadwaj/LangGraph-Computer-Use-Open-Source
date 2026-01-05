"""
Comment Engagement Scraper Service

Periodically scrapes engagement metrics for:
1. Comments WE made on others' posts (likes, replies our comments receive)
2. Comments OTHERS leave on our posts (who commented, engagement on those comments)

Uses Playwright browser automation via the CUA server to fetch real-time metrics.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List, Any
import json


class CommentEngagementScraper:
    """
    Scrapes engagement metrics for comment tracking.

    Usage:
        scraper = CommentEngagementScraper(client, user_id)

        # Scrape engagement for comments we made
        await scraper.scrape_comments_we_made(max_comments=20)

        # Scrape comments on our posts
        await scraper.scrape_comments_on_our_posts(max_posts=10)
    """

    def __init__(self, cua_client, user_id: str):
        """
        Initialize the scraper.

        Args:
            cua_client: CUA client instance for browser automation
            user_id: User ID for database queries
        """
        self.client = cua_client
        self.user_id = user_id

    async def scrape_comments_we_made(
        self,
        max_comments: int = 20,
        hours_since_last_scrape: int = 6,
        max_age_days: int = 7
    ) -> Dict[str, Any]:
        """
        Scrape engagement metrics for comments WE made on others' posts.

        Updates UserComment records with current likes/replies counts.

        Args:
            max_comments: Maximum comments to scrape per run
            hours_since_last_scrape: Only re-scrape if last scrape was this many hours ago
            max_age_days: Only scrape comments made within this many days

        Returns:
            Dict with scrape statistics
        """
        from database.database import SessionLocal
        from database.models import UserComment, XAccount

        stats = {
            "total_scraped": 0,
            "successful": 0,
            "failed": 0,
            "not_found": 0,
            "skipped_no_url": 0,
            "errors": []
        }

        db = SessionLocal()
        try:
            # Find comments to scrape
            cutoff_scrape = datetime.now(timezone.utc) - timedelta(hours=hours_since_last_scrape)
            cutoff_age = datetime.now(timezone.utc) - timedelta(days=max_age_days)

            # Get comments that:
            # 1. Have a URL to scrape
            # 2. Haven't been scraped recently
            # 3. Were made within the age limit
            # 4. Belong to this user
            x_account = db.query(XAccount).filter(XAccount.user_id == self.user_id).first()
            if not x_account:
                print(f"⚠️ No X account found for user {self.user_id}")
                return stats

            comments = db.query(UserComment).filter(
                UserComment.x_account_id == x_account.id,
                UserComment.comment_url.isnot(None),
                UserComment.commented_at >= cutoff_age,
                (UserComment.last_scraped_at.is_(None)) | (UserComment.last_scraped_at < cutoff_scrape)
            ).order_by(UserComment.commented_at.desc()).limit(max_comments).all()

            print(f"📊 Found {len(comments)} comments to scrape")

            for comment in comments:
                if not comment.comment_url:
                    stats["skipped_no_url"] += 1
                    continue

                try:
                    print(f"🔍 Scraping engagement for: {comment.comment_url}")

                    # Navigate to the comment URL
                    nav_result = await self.client._request("POST", "/navigate", {
                        "url": comment.comment_url
                    })

                    if not nav_result.get("success"):
                        comment.scrape_status = "failed"
                        comment.scrape_error = f"Navigation failed: {nav_result.get('error')}"
                        stats["failed"] += 1
                        continue

                    await asyncio.sleep(2)  # Wait for page to load

                    # Extract engagement metrics
                    engagement = await self._extract_engagement_from_page()

                    if engagement.get("success"):
                        comment.likes = engagement.get("likes", 0)
                        comment.replies = engagement.get("replies", 0)
                        comment.retweets = engagement.get("retweets", 0)
                        comment.scrape_status = "success"
                        comment.scrape_error = None
                        comment.last_scraped_at = datetime.now(timezone.utc)
                        stats["successful"] += 1
                        print(f"✅ Updated: {comment.likes} likes, {comment.replies} replies")
                    elif engagement.get("error") == "not_found":
                        comment.scrape_status = "not_found"
                        comment.scrape_error = "Comment not found (may be deleted)"
                        stats["not_found"] += 1
                    else:
                        comment.scrape_status = "failed"
                        comment.scrape_error = engagement.get("error", "Unknown error")
                        stats["failed"] += 1

                    stats["total_scraped"] += 1

                except Exception as e:
                    comment.scrape_status = "failed"
                    comment.scrape_error = str(e)
                    stats["failed"] += 1
                    stats["errors"].append(str(e))
                    print(f"❌ Error scraping {comment.comment_url}: {e}")

            db.commit()
            print(f"📊 Scrape complete: {stats}")
            return stats

        finally:
            db.close()

    async def scrape_comments_on_our_posts(
        self,
        max_posts: int = 10,
        max_comments_per_post: int = 20
    ) -> Dict[str, Any]:
        """
        Scrape comments OTHERS left on our posts.

        Finds new comments and saves them to ReceivedComment table.

        Args:
            max_posts: Maximum number of our posts to check
            max_comments_per_post: Max comments to scrape per post

        Returns:
            Dict with scrape statistics
        """
        from database.database import SessionLocal
        from database.models import UserPost, ReceivedComment, XAccount

        stats = {
            "posts_checked": 0,
            "new_comments_found": 0,
            "errors": []
        }

        db = SessionLocal()
        try:
            # Get user's X account
            x_account = db.query(XAccount).filter(XAccount.user_id == self.user_id).first()
            if not x_account:
                print(f"⚠️ No X account found for user {self.user_id}")
                return stats

            # Get recent posts to check for comments
            posts = db.query(UserPost).filter(
                UserPost.x_account_id == x_account.id,
                UserPost.post_url.isnot(None)
            ).order_by(UserPost.posted_at.desc()).limit(max_posts).all()

            print(f"📊 Checking {len(posts)} posts for comments")

            for post in posts:
                if not post.post_url:
                    continue

                try:
                    print(f"🔍 Checking comments on: {post.post_url}")

                    # Navigate to the post
                    nav_result = await self.client._request("POST", "/navigate", {
                        "url": post.post_url
                    })

                    if not nav_result.get("success"):
                        stats["errors"].append(f"Navigation failed: {nav_result.get('error')}")
                        continue

                    await asyncio.sleep(2)  # Wait for page to load

                    # Extract comments from the page
                    comments = await self._extract_comments_on_post(max_comments_per_post)

                    for comment_data in comments:
                        # Check if this comment already exists
                        existing = db.query(ReceivedComment).filter(
                            ReceivedComment.user_post_id == post.id,
                            ReceivedComment.comment_url == comment_data.get("url")
                        ).first()

                        if not existing and comment_data.get("url"):
                            # Create new ReceivedComment
                            received_comment = ReceivedComment(
                                user_post_id=post.id,
                                x_account_id=x_account.id,
                                commenter_username=comment_data.get("username"),
                                commenter_display_name=comment_data.get("display_name"),
                                comment_url=comment_data.get("url"),
                                content=comment_data.get("content"),
                                likes=comment_data.get("likes", 0),
                                replies=comment_data.get("replies", 0),
                                last_scraped_at=datetime.now(timezone.utc)
                            )
                            db.add(received_comment)
                            stats["new_comments_found"] += 1
                            print(f"✅ New comment from @{comment_data.get('username')}")

                    stats["posts_checked"] += 1

                except Exception as e:
                    stats["errors"].append(str(e))
                    print(f"❌ Error checking post {post.post_url}: {e}")

            db.commit()
            print(f"📊 Scrape complete: {stats}")
            return stats

        finally:
            db.close()

    async def _extract_engagement_from_page(self) -> Dict[str, Any]:
        """
        Extract engagement metrics from the current page (a tweet/comment page).

        Returns:
            Dict with likes, replies, retweets, and success status
        """
        script = '''(() => {
            // Find the main article (the tweet we're viewing)
            const article = document.querySelector('article[data-testid="tweet"]');
            if (!article) {
                return { error: 'not_found', success: false };
            }

            // Helper to parse engagement numbers like "1,234", "1.2K", "12K", "1.5M"
            const parseEngagementNum = (label) => {
                if (!label) return 0;
                const match = label.match(/([\d,.]+)\s*([KkMm])?/);
                if (!match) return 0;
                let num = parseFloat(match[1].replace(/,/g, ''));
                const suffix = match[2]?.toUpperCase();
                if (suffix === 'K') num *= 1000;
                else if (suffix === 'M') num *= 1000000;
                return Math.round(num);
            };

            // Helper to extract count from aria-label
            const getCount = (testId) => {
                const btn = article.querySelector(`[data-testid="${testId}"]`);
                if (!btn) return 0;

                // Try aria-label first
                const label = btn.getAttribute('aria-label') || '';
                const parsed = parseEngagementNum(label);
                if (parsed > 0) return parsed;

                // Try inner text
                const span = btn.querySelector('span');
                if (span) {
                    const text = span.innerText;
                    if (text && /^\d/.test(text)) {
                        return parseEngagementNum(text);
                    }
                }

                return 0;
            };

            return {
                likes: getCount('like'),
                replies: getCount('reply'),
                retweets: getCount('retweet'),
                success: true
            };
        })()'''

        result = await self.client._request("POST", "/playwright/evaluate", {"script": script})

        if result.get("success"):
            return result.get("result", {"error": "No result", "success": False})
        else:
            return {"error": result.get("error", "Script execution failed"), "success": False}

    async def _extract_comments_on_post(self, max_comments: int = 20) -> List[Dict[str, Any]]:
        """
        Extract comments/replies on the current post page.

        Args:
            max_comments: Maximum comments to extract

        Returns:
            List of comment dicts with username, content, url, likes, replies
        """
        script = f'''(() => {{
            const comments = [];
            const articles = document.querySelectorAll('article');

            // Skip first article (it's the main post)
            for (let i = 1; i < articles.length && comments.length < {max_comments}; i++) {{
                const article = articles[i];

                // Get username
                const userLink = article.querySelector('a[href^="/"]');
                const username = userLink ? userLink.getAttribute('href')?.replace('/', '').split('/')[0] : null;

                // Get display name
                const displayNameEl = article.querySelector('[data-testid="User-Name"] span');
                const displayName = displayNameEl ? displayNameEl.innerText : null;

                // Get content
                const contentEl = article.querySelector('[data-testid="tweetText"]');
                const content = contentEl ? contentEl.innerText : null;

                // Get URL
                const timeLink = article.querySelector('a[href*="/status/"]');
                const url = timeLink ? 'https://x.com' + timeLink.getAttribute('href') : null;

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

                // Get engagement
                const getCount = (testId) => {{
                    const btn = article.querySelector(`[data-testid="${{testId}}"]`);
                    if (!btn) return 0;
                    const label = btn.getAttribute('aria-label') || '';
                    return parseEngagementNum(label);
                }};

                if (username && content) {{
                    comments.push({{
                        username,
                        display_name: displayName,
                        content,
                        url,
                        likes: getCount('like'),
                        replies: getCount('reply')
                    }});
                }}
            }}

            return comments;
        }})()'''

        result = await self.client._request("POST", "/playwright/evaluate", {"script": script})

        if result.get("success"):
            return result.get("result", [])
        else:
            print(f"⚠️ Failed to extract comments: {result.get('error')}")
            return []


async def run_comment_scraping(cua_client, user_id: str) -> Dict[str, Any]:
    """
    Convenience function to run both comment scraping tasks.

    Args:
        cua_client: CUA client instance
        user_id: User ID

    Returns:
        Combined results from both scraping operations
    """
    scraper = CommentEngagementScraper(cua_client, user_id)

    # Scrape comments we made
    made_result = await scraper.scrape_comments_we_made()

    # Scrape comments on our posts
    received_result = await scraper.scrape_comments_on_our_posts()

    return {
        "comments_made": made_result,
        "comments_received": received_result
    }
