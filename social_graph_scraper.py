"""
Social Graph Scraper - Programmatic Competitor Discovery

This module builds a social graph by analyzing who users follow and finding
accounts with high overlap (likely competitors in the same niche).

Flow:
1. Scrape user's following list
2. For each followed account, sample their followers
3. Find accounts that follow multiple same people
4. Rank by overlap score → These are competitors
5. Store in PostgreSQL via LangGraph Store

NO agent involvement - pure deterministic scraping.
"""

import asyncio
from datetime import datetime
from typing import List, Dict, Set, Optional
from langgraph.store.base import BaseStore


# ============================================================================
# SOCIAL GRAPH SCRAPER
# ============================================================================

class SocialGraphScraper:
    """
    Programmatic scraper that builds a social graph.
    Uses existing Playwright stealth browser.
    """

    def __init__(self, browser_client):
        """
        Initialize scraper with browser client.

        Args:
            browser_client: The async Playwright client (from async_playwright_tools)
        """
        self.client = browser_client

    async def scrape_following_list(
        self,
        username: str,
        max_count: int = 100
    ) -> List[str]:
        """
        Scrape the list of accounts that @username follows.

        Algorithm:
        1. Navigate to https://x.com/{username}/following
        2. Wait for list to load
        3. Scroll to trigger infinite scroll
        4. Extract usernames from DOM
        5. Repeat scroll until max_count or no new accounts

        Args:
            username: Twitter/X handle (without @)
            max_count: Maximum accounts to scrape

        Returns:
            List of usernames (without @)
        """
        print(f"\n📊 Scraping following list for @{username}...")

        # Navigate to following page
        url = f"https://x.com/{username}/following"
        result = await self.client._request("POST", "/navigate", {"url": url})

        if not result.get("success"):
            raise Exception(f"Failed to navigate to {url}: {result.get('error')}")

        await asyncio.sleep(3)  # Wait for initial load

        following = []
        last_count = 0
        stall_count = 0
        max_scrolls = 50  # Prevent infinite loops
        scroll_count = 0

        print(f"   Starting scroll loop (max {max_scrolls} scrolls)...")

        while len(following) < max_count and scroll_count < max_scrolls:
            # Get current DOM
            dom_result = await self.client._request("GET", "/dom/elements")

            if not dom_result.get("success"):
                print(f"   ⚠️ Failed to get DOM: {dom_result.get('error')}")
                break

            # Extract usernames from DOM
            new_accounts = self._extract_usernames_from_dom(dom_result)

            # Add to list (dedupe automatically)
            for account in new_accounts:
                if account not in following:
                    following.append(account)

            # Check if we're making progress
            current_count = len(following)
            if current_count == last_count:
                stall_count += 1
                if stall_count >= 3:
                    print(f"   ⚠️ No new accounts after 3 scrolls, stopping at {current_count}")
                    break
            else:
                stall_count = 0
                last_count = current_count
                print(f"   Found {current_count} accounts so far...")

            # Scroll down to load more
            await self.client._request("POST", "/scroll", {
                "x": 500,
                "y": 800,
                "scroll_x": 0,
                "scroll_y": 5  # Scroll down
            })

            scroll_count += 1
            await asyncio.sleep(2)  # Rate limit friendly delay

        result_list = following[:max_count]
        print(f"✅ Scraped {len(result_list)} following accounts")

        return result_list

    async def scrape_followers_sample(
        self,
        username: str,
        sample_size: int = 50
    ) -> List[str]:
        """
        Scrape a SAMPLE of accounts that follow @username.

        We don't need ALL followers (could be millions for popular accounts).
        A sample is sufficient to find overlaps.

        Args:
            username: Twitter/X handle (without @)
            sample_size: Number of followers to sample

        Returns:
            List of usernames (without @)
        """
        print(f"   📊 Sampling {sample_size} followers of @{username}...")

        # Navigate to followers page
        url = f"https://x.com/{username}/followers"
        result = await self.client._request("POST", "/navigate", {"url": url})

        if not result.get("success"):
            print(f"      ⚠️ Failed to navigate: {result.get('error')}")
            return []

        await asyncio.sleep(3)

        followers = []
        scroll_count = 0
        max_scrolls = 10  # Limit scrolls for sampling

        while len(followers) < sample_size and scroll_count < max_scrolls:
            # Get DOM
            dom_result = await self.client._request("GET", "/dom/elements")

            if not dom_result.get("success"):
                break

            # Extract usernames
            new_accounts = self._extract_usernames_from_dom(dom_result)

            for account in new_accounts:
                if account not in followers:
                    followers.append(account)

            # Scroll for more
            await self.client._request("POST", "/scroll", {
                "x": 500, "y": 800, "scroll_x": 0, "scroll_y": 5
            })

            scroll_count += 1
            await asyncio.sleep(2)

        result_list = followers[:sample_size]
        print(f"      ✅ Sampled {len(result_list)} followers")

        return result_list

    async def scrape_competitor_posts(
        self,
        username: str,
        max_posts: int = 30
    ) -> tuple[List[Dict], int]:
        """
        Scrape recent posts from a competitor's profile.

        Args:
            username: Twitter/X handle (without @)
            max_posts: Maximum posts to scrape

        Returns:
            Tuple of (posts list, follower_count)
        """
        # Navigate to profile
        url = f"https://x.com/{username}"
        result = await self.client._request("POST", "/navigate", {"url": url})

        if not result.get("success"):
            print(f"   ⚠️ Failed to navigate: {result.get('error')}")
            return [], 0

        await asyncio.sleep(3)

        # Extract follower count from profile page (we're already here!)
        follower_count = 0
        try:
            dom_result = await self.client._request("GET", "/dom/elements")
            if dom_result.get("success"):
                follower_count = self._extract_follower_count(dom_result)
                if follower_count > 0:
                    print(f"   📊 Follower count: {follower_count:,}")
        except Exception as e:
            print(f"   ⚠️ Could not extract follower count: {e}")

        posts = []
        scroll_count = 0
        max_scrolls = 8  # Scroll more to get more posts

        while len(posts) < max_posts and scroll_count < max_scrolls:
            # Get DOM
            dom_result = await self.client._request("GET", "/dom/elements")

            if not dom_result.get("success"):
                break

            # Extract posts
            new_posts = self._extract_posts_from_dom(dom_result)

            for post in new_posts:
                # Deduplicate by text
                if not any(p['text'] == post['text'] for p in posts):
                    posts.append(post)

            # Scroll for more
            await self.client._request("POST", "/scroll", {
                "x": 500, "y": 800, "scroll_x": 0, "scroll_y": 3
            })

            scroll_count += 1
            await asyncio.sleep(2)

        result_posts = posts[:max_posts]
        print(f"   ✅ Scraped {len(result_posts)} posts")

        return result_posts, follower_count

    def _extract_posts_from_dom(self, dom_result: Dict) -> List[Dict]:
        """
        Extract post content from X DOM with engagement metrics.

        X tweets are in <article> tags. Each article contains:
        - Tweet text
        - Engagement buttons with aria-labels like "123 Likes. Like"

        Returns posts with text and engagement metrics.
        """
        import re

        posts = []
        elements = dom_result.get("elements", [])

        # Find all article elements (tweets)
        articles = [el for el in elements if el.get("tagName", "").lower() == "article"]

        print(f"      Found {len(articles)} article elements")

        for article in articles:
            article_text = article.get("text", "").strip()
            article_y = article.get("y", 0)

            # Skip if article is too short
            if len(article_text) < 30:
                continue

            # Extract clean tweet text
            # Article text contains: username, timestamp, and tweet content
            # We want just the tweet content
            post_text = article_text

            # Find engagement buttons near this article (within 500px vertically)
            likes = 0
            retweets = 0
            replies = 0
            views = 0

            for el in elements:
                el_y = el.get("y", 0)
                # Check if element is near this article
                if abs(el_y - article_y) > 500:
                    continue

                aria_label = el.get("ariaLabel", "").lower()

                # Parse likes: "123 likes. like" or "1.2k likes. like"
                if "like" in aria_label and el.get("tagName") == "button":
                    match = re.search(r'(\d+\.?\d*[km]?)\s*like', aria_label)
                    if match:
                        new_likes = self._parse_metric(match.group(1))
                        likes = max(likes, new_likes)  # Take highest value found

                # Parse retweets: "45 retweets. repost"
                if "retweet" in aria_label or "repost" in aria_label:
                    match = re.search(r'(\d+\.?\d*[km]?)\s*(?:retweet|repost)', aria_label)
                    if match:
                        new_retweets = self._parse_metric(match.group(1))
                        retweets = max(retweets, new_retweets)

                # Parse replies: "10 replies. reply"
                if "repl" in aria_label:
                    match = re.search(r'(\d+\.?\d*[km]?)\s*repl', aria_label)
                    if match:
                        new_replies = self._parse_metric(match.group(1))
                        replies = max(replies, new_replies)

                # Parse views from aria-label: "59226 views. View post analytics"
                if "view" in aria_label and el.get("tagName") == "a":
                    match = re.search(r'(\d+\.?\d*[km]?)\s*views?\.\s*view', aria_label)
                    if match:
                        new_views = self._parse_metric(match.group(1))
                        views = max(views, new_views)

            posts.append({
                "text": post_text,
                "likes": likes,
                "retweets": retweets,
                "replies": replies,
                "views": views,
                "scraped_at": datetime.utcnow().isoformat()
            })

        # Dedupe and filter
        seen_texts = set()
        unique_posts = []

        for post in posts:
            # Simple dedup by first 100 chars
            text_sig = post["text"][:100]
            if text_sig in seen_texts:
                continue
            seen_texts.add(text_sig)

            # Filter out obvious junk
            text_lower = post["text"].lower()
            if any(junk in text_lower for junk in [
                "followed by", "you might like", "show this thread",
                "trending in", "live on x"
            ]):
                continue

            unique_posts.append(post)

        # Sort by engagement
        unique_posts.sort(key=lambda p: p.get("likes", 0) + p.get("retweets", 0) + p.get("replies", 0), reverse=True)

        print(f"      Extracted {len(unique_posts)} unique posts")

        return unique_posts

    def _parse_metric(self, metric_str: str) -> int:
        """
        Parse engagement metric string like '1.2K' or '123' to integer.

        Examples:
        - "123" -> 123
        - "1.2K" -> 1200
        - "1.5M" -> 1500000
        """
        metric_str = metric_str.strip().upper()

        if 'K' in metric_str:
            return int(float(metric_str.replace('K', '')) * 1000)
        elif 'M' in metric_str:
            return int(float(metric_str.replace('M', '')) * 1000000)
        else:
            try:
                return int(float(metric_str))
            except ValueError:
                return 0

    def _extract_follower_count(self, dom_result: Dict) -> int:
        """
        Extract follower count from X profile page DOM.

        On profile pages, X displays follower count with text like:
        "1.2K Followers" or "123 Followers"

        Returns:
            Follower count as integer (0 if not found)
        """
        import re

        elements = dom_result.get("elements", [])

        # Look for elements containing "Follower" text
        for el in elements:
            text = el.get("text", "").strip()

            # Match patterns like "1.2K Followers" or "123 Followers"
            match = re.search(r'([\d,.]+[KM]?)\s+Followers?', text, re.IGNORECASE)
            if match:
                follower_str = match.group(1)
                count = self._parse_metric(follower_str)
                if count > 0:
                    return count

        # Also check aria-labels which sometimes contain follower info
        for el in elements:
            aria_label = el.get("ariaLabel", "")
            match = re.search(r'([\d,.]+[KM]?)\s+Followers?', aria_label, re.IGNORECASE)
            if match:
                follower_str = match.group(1)
                count = self._parse_metric(follower_str)
                if count > 0:
                    return count

        return 0

    def _extract_usernames_from_dom(self, dom_result: Dict) -> List[str]:
        """
        Extract usernames from X's DOM structure.

        X (Twitter) uses structure like:
        <div data-testid="UserCell">
          <a href="/username">@username</a>
        </div>

        We look for links matching the pattern /username (no subdirectories).

        Args:
            dom_result: DOM data from browser

        Returns:
            List of unique usernames
        """
        usernames = []
        elements = dom_result.get("elements", [])

        # System pages to exclude (not real users)
        excluded = {
            "home", "explore", "notifications", "messages",
            "compose", "i", "settings", "search"
        }

        for el in elements:
            # Check href attribute
            href = el.get("href", "")

            # Username links are like: /username (single path segment)
            if href.startswith("/") and len(href) > 1:
                # Remove leading slash
                potential_username = href[1:]

                # Make sure it's a single segment (no more slashes)
                if "/" not in potential_username:
                    # Not a system page
                    if potential_username not in excluded:
                        usernames.append(potential_username)

            # Also check text content for @username patterns
            text = el.get("text", "")
            if text.startswith("@"):
                username = text[1:].split()[0]  # Get first word after @
                if username and username not in excluded:
                    usernames.append(username)

        # Deduplicate and return
        return list(set(usernames))


# ============================================================================
# SOCIAL GRAPH BUILDER
# ============================================================================

class SocialGraphBuilder:
    """
    Builds the social graph from scraped data and stores in PostgreSQL.

    Storage structure:
    - (user_id, "social_graph") -> Latest graph data
    - (user_id, "competitor_profiles") -> Individual competitor profiles
    """

    def __init__(self, store: BaseStore, user_id: str):
        """
        Initialize graph builder.

        Args:
            store: LangGraph Store (PostgreSQL)
            user_id: User identifier
        """
        self.store = store
        self.user_id = user_id
        self.namespace_graph = (user_id, "social_graph")
        self.namespace_competitors = (user_id, "competitor_profiles")

    async def build_graph(
        self,
        user_handle: str,
        max_following: int = 200,
        analyze_count: int = 50,
        follower_sample_size: int = 100
    ) -> Dict:
        """
        Build social graph starting from user's account.

        Algorithm:
        1. Scrape user's following list (up to max_following)
        2. Sample analyze_count accounts from that list
        3. For each sampled account, get follower_sample_size followers
        4. Find accounts that appear in multiple follower lists
        5. Rank by overlap score (more overlaps = likely competitor)
        6. Store results in PostgreSQL

        Args:
            user_handle: User's Twitter/X handle (without @)
            max_following: Max accounts to scrape from user's following
            analyze_count: How many of those to analyze deeply
            follower_sample_size: How many followers to sample per account

        Returns:
            Graph data with competitor rankings
        """
        print(f"\n{'='*80}")
        print(f"🕸️  BUILDING SOCIAL GRAPH FOR @{user_handle}")
        print(f"{'='*80}\n")

        # Initialize scraper with global browser client
        from async_playwright_tools import _global_client
        scraper = SocialGraphScraper(_global_client)

        # STEP 1: Get who the user follows
        print(f"STEP 1: Scraping who @{user_handle} follows...")
        user_following = await scraper.scrape_following_list(
            user_handle,
            max_count=max_following
        )

        if not user_following:
            raise Exception(f"Failed to scrape following list for @{user_handle}")

        print(f"\n✅ User follows {len(user_following)} accounts")

        # STEP 2: Sample accounts to analyze
        # Deduplicate to ensure no account is analyzed twice
        unique_following = list(dict.fromkeys(user_following))  # Preserves order, removes duplicates
        sample_accounts = unique_following[:analyze_count]
        print(f"\nSTEP 2: Will analyze {len(sample_accounts)} of those accounts")

        # STEP 3: For each account, get sample of their followers
        print(f"\nSTEP 3: Finding overlaps (who else follows same people)...\n")

        overlap_counts = {}  # {username: count}
        overlap_details = {}  # {username: [accounts they follow]}
        cancel_namespace = (self.user_id, "discovery_control")

        for i, account in enumerate(sample_accounts, 1):
            # Update progress
            progress_namespace = (self.user_id, "discovery_progress")
            self.store.put(progress_namespace, "current", {
                "current": i,
                "total": len(sample_accounts),
                "current_account": account,
                "status": "analyzing",
                "stage": "analyzing_accounts"
            })

            # Check for cancellation
            cancel_items = list(self.store.search(cancel_namespace, limit=1))
            if cancel_items and cancel_items[0].value.get("cancelled"):
                print(f"\n⚠️ DISCOVERY CANCELLED by user!")
                print(f"   Processed {i-1}/{len(sample_accounts)} accounts")
                print(f"   Continuing with partial results...\n")
                break

            print(f"[{i}/{len(sample_accounts)}] Analyzing @{account}...")

            try:
                # Get followers of this account
                followers = await scraper.scrape_followers_sample(
                    account,
                    sample_size=follower_sample_size
                )

                # Track overlaps
                for follower in followers:
                    # Skip if it's the user themselves
                    if follower.lower() == user_handle.lower():
                        continue

                    # Increment overlap count
                    if follower not in overlap_counts:
                        overlap_counts[follower] = 0
                        overlap_details[follower] = []

                    overlap_counts[follower] += 1
                    overlap_details[follower].append(account)

                # Rate limit friendly delay
                await asyncio.sleep(3)

            except Exception as e:
                print(f"      ⚠️ Failed to analyze @{account}: {e}")
                continue

        # STEP 4: Rank by overlap score and FILTER by threshold
        # Define threshold first
        # With 50 analyzed accounts and 100 follower samples each,
        # 50% means appearing in 25+ follower lists = strong signal
        MIN_OVERLAP_PERCENTAGE = 50  # Require 50%+ match for high-quality competitors

        print(f"\nSTEP 4: Filtering high-quality competitors ({MIN_OVERLAP_PERCENTAGE}%+ overlap)...\n")

        # Sort by overlap count (descending)
        competitors_ranked = sorted(
            overlap_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )

        # Build competitor list with details
        # IMPORTANT: Only include high-quality matches
        competitors = []

        for username, overlap_count in competitors_ranked:
            overlap_percentage = round(overlap_count / len(sample_accounts) * 100, 1)

            # FILTER: Only include if overlap meets threshold
            if overlap_percentage >= MIN_OVERLAP_PERCENTAGE:
                competitors.append({
                    "username": username,
                    "overlap_score": overlap_count,
                    "overlap_percentage": overlap_percentage,
                    "common_follows": overlap_details[username],
                    "discovered_at": datetime.utcnow().isoformat()
                })

                print(f"   ✅ @{username}: {overlap_count} overlaps ({overlap_percentage}%)")
            else:
                # Log near-misses for debugging
                if overlap_percentage >= (MIN_OVERLAP_PERCENTAGE * 0.75):
                    print(f"   ⚠️  @{username}: {overlap_percentage}% (below {MIN_OVERLAP_PERCENTAGE}% threshold)")

        # STEP 5: Scrape posts from high-quality competitors
        if competitors:
            print(f"\nSTEP 5: Scraping posts from {len(competitors)} competitors...\n")

            for i, competitor in enumerate(competitors, 1):
                # Update progress
                progress_namespace = (self.user_id, "discovery_progress")
                self.store.put(progress_namespace, "current", {
                    "current": i,
                    "total": len(competitors),
                    "current_account": competitor['username'],
                    "status": "scraping_posts",
                    "stage": "scraping_posts"
                })

                print(f"[{i}/{len(competitors)}] Scraping posts from @{competitor['username']}...")

                try:
                    posts = await scraper.scrape_competitor_posts(
                        competitor['username'],
                        max_posts=30
                    )

                    competitor['posts'] = posts
                    competitor['post_count'] = len(posts)

                    # Rate limit
                    await asyncio.sleep(3)

                except Exception as e:
                    print(f"   ⚠️ Failed to scrape posts: {e}")
                    competitor['posts'] = []
                    competitor['post_count'] = 0

        # STEP 6: Store in database
        print(f"\nSTEP 6: Storing results in PostgreSQL...")

        # Build lookup for competitors with posts
        competitors_with_posts = {c['username']: c for c in competitors}

        # Build ALL potential competitors with raw overlap data
        # This allows re-filtering without re-scraping
        all_competitors_raw = []
        for username, overlap_count in competitors_ranked:
            overlap_percentage = round(overlap_count / len(sample_accounts) * 100, 1)

            # Base competitor data
            comp_data = {
                "username": username,
                "overlap_score": overlap_count,
                "overlap_percentage": overlap_percentage,
                "common_follows": overlap_details[username],
                "discovered_at": datetime.utcnow().isoformat()
            }

            # Merge in posts if we scraped them
            if username in competitors_with_posts:
                comp_data['posts'] = competitors_with_posts[username].get('posts', [])
                comp_data['post_count'] = competitors_with_posts[username].get('post_count', 0)

            all_competitors_raw.append(comp_data)

        graph_data = {
            "user_handle": user_handle,
            "user_following_count": len(user_following),
            "user_following": user_following,
            "analyzed_accounts": len(sample_accounts),
            "discovered_accounts": len(overlap_counts),
            "high_quality_competitors": len(competitors),
            "top_competitors": competitors,  # Filtered list
            "all_competitors_raw": all_competitors_raw,  # RAW unfiltered data
            "created_at": datetime.utcnow().isoformat(),
            "last_updated": datetime.utcnow().isoformat(),
            "config": {
                "max_following": max_following,
                "analyze_count": analyze_count,
                "follower_sample_size": follower_sample_size,
                "min_overlap_threshold": MIN_OVERLAP_PERCENTAGE
            }
        }

        # Store main graph data
        self.store.put(
            self.namespace_graph,
            "latest",
            graph_data
        )

        # Store individual competitor profiles
        for competitor in competitors:
            self.store.put(
                self.namespace_competitors,
                competitor["username"],
                {
                    **competitor,
                    "tracked_since": datetime.utcnow().isoformat(),
                    "status": "discovered"  # Can be: discovered, tracking, archived
                }
            )

        print(f"\n{'='*80}")
        print(f"✅ DISCOVERY COMPLETE!")
        print(f"   - Analyzed {len(sample_accounts)} accounts you follow")
        print(f"   - Found {len(overlap_counts)} total accounts in network")
        print(f"   - Filtered to {len(competitors)} high-quality competitors ({MIN_OVERLAP_PERCENTAGE}%+ overlap)")
        if competitors:
            print(f"   - Top match: @{competitors[0]['username']} ({competitors[0]['overlap_percentage']}% overlap)")
            total_posts = sum(c.get('post_count', 0) for c in competitors)
            if total_posts > 0:
                print(f"   - Scraped {total_posts} total posts from competitors")
        print(f"   - Stored in PostgreSQL")
        print(f"{'='*80}\n")

        return graph_data

    def get_graph(self) -> Optional[Dict]:
        """
        Retrieve the latest social graph from database.

        Returns:
            Graph data or None if not found
        """
        items = list(self.store.search(
            self.namespace_graph,
            limit=1
        ))

        if items:
            return items[0].value
        return None

    def get_competitor(self, username: str) -> Optional[Dict]:
        """
        Get a specific competitor's profile.

        Args:
            username: Competitor's handle (without @)

        Returns:
            Competitor data or None
        """
        items = list(self.store.search(
            self.namespace_competitors,
            filter={"username": username},
            limit=1
        ))

        if items:
            return items[0].value
        return None

    def list_competitors(self, limit: int = 50) -> List[Dict]:
        """
        List all discovered competitors.

        Args:
            limit: Max competitors to return

        Returns:
            List of competitor profiles
        """
        items = self.store.search(
            self.namespace_competitors,
            limit=limit
        )

        return [item.value for item in items]


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    """
    Example: How to use the social graph builder
    """

    print("=" * 80)
    print("📊 SOCIAL GRAPH SCRAPER - Example Usage")
    print("=" * 80)

    print("""
This module discovers competitors by analyzing social graph overlaps.

USAGE:

1. From backend API endpoint:

```python
from social_graph_scraper import SocialGraphBuilder

@app.post("/api/social-graph/discover/{user_id}")
async def discover_competitors(user_id: str, user_handle: str):
    # Initialize builder with PostgreSQL Store
    builder = SocialGraphBuilder(store, user_id)

    # Build the graph (takes 5-10 minutes)
    graph = await builder.build_graph(user_handle)

    return {
        "success": True,
        "competitors": graph["top_competitors"]
    }
```

2. From Python script:

```python
import asyncio
from psycopg_pool import ConnectionPool
from langgraph.store.postgres import PostgresStore
from social_graph_scraper import SocialGraphBuilder

async def main():
    # Initialize store
    conn_pool = ConnectionPool(
        conninfo="postgresql://postgres:password@localhost:5433/xgrowth",
        min_size=1,
        max_size=10
    )
    store = PostgresStore(conn=conn_pool)

    # Build graph
    builder = SocialGraphBuilder(store, "user_123")
    graph = await builder.build_graph("Rajath_DB")

    print(f"Found {len(graph['top_competitors'])} competitors!")

asyncio.run(main())
```

DATABASE STRUCTURE:

Store table (already exists):
- prefix: "user_123.social_graph"
- key: "latest"
- value: {user_handle, competitors, ...}

- prefix: "user_123.competitor_profiles"
- key: "competitor_username"
- value: {username, overlap_score, ...}

NEXT STEPS:

1. Add to backend_websocket_server.py ✓
2. Create frontend UI to trigger discovery ✓
3. Visualize graph on dashboard ✓
4. Start tracking competitor posts (Phase 2)
""")

    print("=" * 80)
