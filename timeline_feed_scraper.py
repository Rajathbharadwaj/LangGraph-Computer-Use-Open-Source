"""
Timeline Feed Scraper - Get Posts from Following Tab

Scrapes the authenticated user's "Following" timeline (not "For You")
for high signal-to-noise training data in the Learning Engine.

The "Following" tab shows posts ONLY from accounts you follow,
making it ideal for preference learning since these are accounts
you've already explicitly chosen to follow.
"""

import asyncio
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass


@dataclass
class TimelinePost:
    """A post from the Following timeline with full metadata."""
    url: str
    author: str
    author_display_name: str
    author_followers: int
    content: str
    likes: int
    retweets: int
    replies: int
    views: int
    hours_ago: float
    scraped_at: str

    def to_dict(self) -> Dict:
        """Convert to dict format expected by Learning Engine."""
        return {
            "url": self.url,
            "author": self.author,
            "author_display_name": self.author_display_name,
            "author_followers": self.author_followers,
            "content": self.content,
            "likes": self.likes,
            "retweets": self.retweets,
            "replies": self.replies,
            "views": self.views,
            "hours_ago": self.hours_ago,
            "scraped_at": self.scraped_at,
        }


class TimelineFeedScraper:
    """
    Scrapes posts from the "Following" timeline tab.

    Uses existing Playwright stealth browser for X.com automation.
    """

    def __init__(self, browser_client):
        """
        Initialize with async Playwright client.

        Args:
            browser_client: AsyncPlaywrightClient instance
        """
        self.client = browser_client

    async def scrape_following_feed(
        self,
        max_posts: int = 30,
        min_engagement: int = 10,
        max_hours_ago: int = 48
    ) -> List[TimelinePost]:
        """
        Scrape posts from the Following tab.

        Algorithm:
        1. Navigate to x.com/home
        2. Click "Following" tab (not "For You")
        3. Scroll and extract posts
        4. Filter by engagement and recency
        5. Extract author info for each post

        Args:
            max_posts: Maximum posts to return
            min_engagement: Minimum likes+retweets+replies to include
            max_hours_ago: Maximum age of posts in hours

        Returns:
            List of TimelinePost objects
        """
        print(f"\n📰 Scraping Following timeline feed...")

        # Navigate to home
        result = await self.client._request("POST", "/navigate", {"url": "https://x.com/home"})

        if not result.get("success"):
            raise Exception(f"Failed to navigate to home: {result.get('error')}")

        await asyncio.sleep(3)  # Wait for page load

        # Click the "Following" tab
        clicked = await self._click_following_tab()
        if not clicked:
            print("   ⚠️ Could not click Following tab, trying to proceed anyway...")

        await asyncio.sleep(2)  # Wait for feed to update

        # Scrape posts with scrolling
        posts = []
        scroll_count = 0
        max_scrolls = 15  # ~15 scrolls should get 30+ posts
        stall_count = 0
        last_count = 0

        print(f"   Starting scroll loop (target: {max_posts} posts)...")

        while len(posts) < max_posts * 2 and scroll_count < max_scrolls:  # Get 2x to filter later
            # Get DOM elements
            dom_result = await self.client._request("GET", "/dom/elements")

            if not dom_result.get("success"):
                print(f"   ⚠️ Failed to get DOM: {dom_result.get('error')}")
                break

            # Extract posts from DOM
            new_posts = self._extract_posts_from_dom(dom_result)

            # Add new posts (dedupe by URL)
            existing_urls = {p.url for p in posts}
            for post in new_posts:
                if post.url and post.url not in existing_urls:
                    posts.append(post)
                    existing_urls.add(post.url)

            # Check progress
            current_count = len(posts)
            if current_count == last_count:
                stall_count += 1
                if stall_count >= 3:
                    print(f"   ⚠️ No new posts after 3 scrolls, stopping at {current_count}")
                    break
            else:
                stall_count = 0
                last_count = current_count
                print(f"   Found {current_count} posts so far...")

            # Scroll down
            await self.client._request("POST", "/scroll", {
                "x": 500,
                "y": 800,
                "scroll_x": 0,
                "scroll_y": 3
            })

            scroll_count += 1
            await asyncio.sleep(1.5)  # Rate limit friendly

        # Filter by engagement and recency
        filtered_posts = []
        for post in posts:
            total_engagement = post.likes + post.retweets + post.replies

            if total_engagement < min_engagement:
                continue

            if post.hours_ago > max_hours_ago:
                continue

            filtered_posts.append(post)

        # Sort by engagement (higher first)
        filtered_posts.sort(
            key=lambda p: p.likes + p.retweets * 2 + p.replies * 3,
            reverse=True
        )

        result_posts = filtered_posts[:max_posts]
        print(f"✅ Scraped {len(result_posts)} posts from Following feed")

        return result_posts

    async def _click_following_tab(self) -> bool:
        """
        Click the "Following" tab on the home page.

        X.com home has two tabs: "For you" and "Following"
        We want "Following" for high signal-to-noise data.

        Returns:
            True if clicked successfully
        """
        try:
            # Get DOM to find the Following tab
            dom_result = await self.client._request("GET", "/dom/elements")

            if not dom_result.get("success"):
                return False

            elements = dom_result.get("elements", [])

            # Find the Following tab - it's usually a link or button with text "Following"
            following_tab = None
            for el in elements:
                text = el.get("text", "").strip().lower()
                tag = el.get("tagName", "").lower()

                # Match "Following" tab (not "For you")
                if text == "following" and tag in ["a", "button", "div", "span"]:
                    following_tab = el
                    break

            if not following_tab:
                print("   Could not find Following tab element")
                return False

            # Click the tab
            x = following_tab.get("x", 0) + following_tab.get("width", 0) / 2
            y = following_tab.get("y", 0) + following_tab.get("height", 0) / 2

            click_result = await self.client._request("POST", "/click", {
                "x": int(x),
                "y": int(y),
                "button": "left"
            })

            if click_result.get("success"):
                print("   ✅ Clicked Following tab")
                return True

            return False

        except Exception as e:
            print(f"   ⚠️ Error clicking Following tab: {e}")
            return False

    def _extract_posts_from_dom(self, dom_result: Dict) -> List[TimelinePost]:
        """
        Extract posts from X.com DOM with full metadata.

        Extracts:
        - Post URL (from status link)
        - Author username and display name
        - Post content
        - Engagement metrics (likes, retweets, replies, views)
        - Timestamp (converted to hours_ago)
        """
        posts = []
        elements = dom_result.get("elements", [])

        # Find all article elements (tweets)
        articles = [el for el in elements if el.get("tagName", "").lower() == "article"]

        for article in articles:
            try:
                post = self._parse_article(article, elements)
                if post:
                    posts.append(post)
            except Exception as e:
                # Skip malformed articles
                continue

        return posts

    def _parse_article(self, article: Dict, all_elements: List[Dict]) -> Optional[TimelinePost]:
        """
        Parse a single article element into a TimelinePost.
        """
        article_text = article.get("text", "").strip()
        article_y = article.get("y", 0)
        article_height = article.get("height", 500)

        # Skip very short articles
        if len(article_text) < 30:
            return None

        # Skip junk
        text_lower = article_text.lower()
        junk_patterns = [
            "followed by", "you might like", "show this thread",
            "trending in", "live on x", "promoted", "ad"
        ]
        if any(junk in text_lower for junk in junk_patterns):
            return None

        # Extract post URL from nearby link elements
        post_url = ""
        author = ""
        author_display_name = ""
        timestamp_text = ""

        for el in all_elements:
            el_y = el.get("y", 0)

            # Only look at elements within this article's bounds
            if el_y < article_y - 50 or el_y > article_y + article_height + 50:
                continue

            href = el.get("href", "")
            el_text = el.get("text", "").strip()

            # Find status URL (post link)
            if "/status/" in href and not post_url:
                post_url = f"https://x.com{href}" if href.startswith("/") else href
                # Extract author from URL: /username/status/123
                parts = href.split("/")
                if len(parts) >= 2:
                    author = parts[1]

            # Find @username mention (author)
            if el_text.startswith("@") and not author:
                author = el_text[1:]  # Remove @

            # Find timestamp (e.g., "2h", "1d", "Jan 5")
            if el.get("tagName") == "time" or self._looks_like_timestamp(el_text):
                timestamp_text = el_text

        # Skip if no URL found
        if not post_url:
            return None

        # Extract engagement metrics
        likes, retweets, replies, views = self._extract_engagement(article_y, all_elements)

        # Parse timestamp to hours_ago
        hours_ago = self._parse_timestamp(timestamp_text)

        # Extract clean content (remove username, timestamp from article text)
        content = self._extract_content(article_text, author)

        # Skip if content is too short after cleaning
        if len(content) < 20:
            return None

        return TimelinePost(
            url=post_url,
            author=author,
            author_display_name=author_display_name or author,
            author_followers=0,  # Would need separate profile lookup
            content=content,
            likes=likes,
            retweets=retweets,
            replies=replies,
            views=views,
            hours_ago=hours_ago,
            scraped_at=datetime.utcnow().isoformat()
        )

    def _extract_engagement(self, article_y: int, elements: List[Dict]) -> Tuple[int, int, int, int]:
        """
        Extract engagement metrics from elements near the article.
        """
        likes = 0
        retweets = 0
        replies = 0
        views = 0

        for el in elements:
            el_y = el.get("y", 0)

            # Check if element is near this article (within 500px)
            if abs(el_y - article_y) > 500:
                continue

            aria_label = el.get("ariaLabel", "").lower()

            # Parse likes
            if "like" in aria_label and el.get("tagName") == "button":
                match = re.search(r'(\d+\.?\d*[km]?)\s*like', aria_label)
                if match:
                    likes = max(likes, self._parse_metric(match.group(1)))

            # Parse retweets/reposts
            if "retweet" in aria_label or "repost" in aria_label:
                match = re.search(r'(\d+\.?\d*[km]?)\s*(?:retweet|repost)', aria_label)
                if match:
                    retweets = max(retweets, self._parse_metric(match.group(1)))

            # Parse replies
            if "repl" in aria_label:
                match = re.search(r'(\d+\.?\d*[km]?)\s*repl', aria_label)
                if match:
                    replies = max(replies, self._parse_metric(match.group(1)))

            # Parse views
            if "view" in aria_label and el.get("tagName") == "a":
                match = re.search(r'(\d+\.?\d*[km]?)\s*views?\.\s*view', aria_label)
                if match:
                    views = max(views, self._parse_metric(match.group(1)))

        return likes, retweets, replies, views

    def _parse_metric(self, metric_str: str) -> int:
        """
        Parse engagement metric string like '1.2K' to integer.
        """
        metric_str = metric_str.strip().upper()

        try:
            if 'K' in metric_str:
                return int(float(metric_str.replace('K', '')) * 1000)
            elif 'M' in metric_str:
                return int(float(metric_str.replace('M', '')) * 1000000)
            else:
                return int(float(metric_str))
        except:
            return 0

    def _looks_like_timestamp(self, text: str) -> bool:
        """
        Check if text looks like a timestamp.
        Examples: "2h", "1d", "5m", "Jan 5", "Dec 30"
        """
        text = text.strip().lower()

        # Relative timestamps
        if re.match(r'^\d+[hdms]$', text):
            return True

        # Date timestamps
        months = ['jan', 'feb', 'mar', 'apr', 'may', 'jun',
                  'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
        for month in months:
            if text.startswith(month):
                return True

        return False

    def _parse_timestamp(self, timestamp_text: str) -> float:
        """
        Parse timestamp text to hours ago.

        Examples:
        - "2h" -> 2.0
        - "1d" -> 24.0
        - "5m" -> 0.083
        - "Jan 5" -> hours since Jan 5
        """
        text = timestamp_text.strip().lower()

        # Relative: "2h", "1d", "5m", "30s"
        match = re.match(r'^(\d+)([hdms])$', text)
        if match:
            value = int(match.group(1))
            unit = match.group(2)

            if unit == 'h':
                return float(value)
            elif unit == 'd':
                return float(value * 24)
            elif unit == 'm':
                return float(value) / 60
            elif unit == 's':
                return float(value) / 3600

        # Date format: "Jan 5"
        months = {
            'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
            'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
        }

        for month_name, month_num in months.items():
            if text.startswith(month_name):
                try:
                    day = int(re.search(r'\d+', text).group())
                    now = datetime.utcnow()
                    year = now.year

                    # Handle year rollover
                    post_date = datetime(year, month_num, day)
                    if post_date > now:
                        post_date = datetime(year - 1, month_num, day)

                    delta = now - post_date
                    return delta.total_seconds() / 3600
                except:
                    pass

        # Default: assume recent
        return 12.0

    def _extract_content(self, article_text: str, author: str) -> str:
        """
        Extract clean post content from article text.

        Article text includes username, timestamp, and buttons.
        We want just the actual post content.
        """
        # Remove common noise patterns
        lines = article_text.split('\n')
        content_lines = []

        skip_patterns = [
            'show more', 'show this thread', 'translate',
            'quote', 'repost', 'like', 'bookmark', 'share',
            'more', 'copy link', 'reply', 'follows you'
        ]

        for line in lines:
            line = line.strip()

            # Skip empty lines
            if not line:
                continue

            # Skip usernames
            if line.startswith('@'):
                continue

            # Skip timestamps
            if self._looks_like_timestamp(line):
                continue

            # Skip noise
            if line.lower() in skip_patterns:
                continue

            # Skip very short fragments
            if len(line) < 3:
                continue

            # Skip if it's just the author name
            if author and line.lower() == author.lower():
                continue

            content_lines.append(line)

        # Join and clean
        content = ' '.join(content_lines)

        # Remove duplicate spaces
        content = re.sub(r'\s+', ' ', content).strip()

        return content


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

async def get_following_timeline_posts(
    browser_client,
    max_posts: int = 30,
    min_engagement: int = 10,
    max_hours_ago: int = 48
) -> List[Dict]:
    """
    Convenience function to get Following timeline posts.

    Args:
        browser_client: AsyncPlaywrightClient instance
        max_posts: Maximum posts to return
        min_engagement: Minimum total engagement to include
        max_hours_ago: Maximum age in hours

    Returns:
        List of post dicts ready for Learning Engine
    """
    scraper = TimelineFeedScraper(browser_client)
    posts = await scraper.scrape_following_feed(
        max_posts=max_posts,
        min_engagement=min_engagement,
        max_hours_ago=max_hours_ago
    )

    return [post.to_dict() for post in posts]
