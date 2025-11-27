"""
X Native Common Followers Discovery

GENIUS APPROACH:
Instead of scraping full following lists and comparing (slow),
use X's NATIVE "Followed by" feature that shows common connections!

When you visit someone's profile, X shows:
"Followed by @user1, @user2, and 5 others you follow"

We can extract this number directly - NO NEED to scrape following lists!

Algorithm:
1. Get YOUR followers list
2. For each follower, visit their profile
3. Extract "X people you follow" or "Followed by" count from DOM
4. Sort by this count = instant competitor ranking!

Speed: ~2 seconds per account vs ~20 seconds (no following list scraping!)

RATE LIMITING:
X aggressively rate limits automated browsing. This module implements:
- Exponential backoff when blocked
- Random jitter between requests
- Conservative limits (20 accounts max)
- Rate limit detection via page content
"""

import asyncio
import re
import random
from datetime import datetime
from typing import List, Dict, Set, Optional
from langgraph.store.base import BaseStore


class XNativeCommonFollowersDiscovery:
    """
    Ultra-fast competitor discovery using X's native "Followed by" feature.
    Includes rate limiting protection with exponential backoff.
    """

    def __init__(self, browser_client, store: BaseStore, user_id: str):
        self.client = browser_client
        self.store = store
        self.user_id = user_id
        self.namespace_graph = (user_id, "social_graph")
        self.namespace_competitors = (user_id, "competitor_profiles")

        # Rate limiting state
        self.consecutive_failures = 0
        self.base_delay = 3  # Base delay between requests in seconds
        self.max_delay = 60  # Maximum delay after backoff
        self.rate_limited = False

    async def _smart_delay(self, is_navigation: bool = False):
        """
        Apply intelligent delay with exponential backoff.
        Navigation operations get longer delays.
        """
        # Base delay with jitter
        base = self.base_delay if not is_navigation else self.base_delay * 2
        jitter = random.uniform(0.5, 1.5)

        # Exponential backoff based on consecutive failures
        if self.consecutive_failures > 0:
            backoff_multiplier = min(2 ** self.consecutive_failures, 10)
            delay = min(base * backoff_multiplier * jitter, self.max_delay)
            print(f"      ⏳ Rate limit backoff: {delay:.1f}s (failures: {self.consecutive_failures})")
        else:
            delay = base * jitter

        await asyncio.sleep(delay)

    async def _check_rate_limited(self) -> bool:
        """
        Check if X has rate limited us by looking at page content.
        X shows empty content or specific error messages when blocked.
        """
        try:
            dom_result = await self.client._request("GET", "/dom/elements")
            if not dom_result.get("success"):
                return True

            elements = dom_result.get("elements", [])

            # Check for rate limit indicators
            for el in elements:
                text = (el.get("text", "") or "").lower()
                # X shows these when rate limited
                if any(indicator in text for indicator in [
                    "something went wrong",
                    "try again",
                    "rate limit",
                    "too many requests",
                    "temporarily unavailable"
                ]):
                    return True

            # If page has very few elements, might be blocked
            if len(elements) < 5:
                return True

            return False
        except Exception:
            return True

    async def _navigate_with_retry(self, url: str, max_retries: int = 3) -> bool:
        """
        Navigate to URL with retry logic and rate limit detection.
        Returns True if successful, False if blocked.
        """
        for attempt in range(max_retries):
            result = await self.client._request("POST", "/navigate", {"url": url})

            if not result.get("success"):
                self.consecutive_failures += 1
                print(f"      ⚠️ Navigation failed (attempt {attempt + 1}/{max_retries})")
                await self._smart_delay(is_navigation=True)
                continue

            # Wait for page to load
            await asyncio.sleep(3 + random.uniform(0, 2))

            # Check if we got rate limited
            if await self._check_rate_limited():
                self.consecutive_failures += 1
                self.rate_limited = True
                print(f"      🚫 Rate limited detected (attempt {attempt + 1}/{max_retries})")
                await self._smart_delay(is_navigation=True)
                continue

            # Success - reset failure count
            self.consecutive_failures = max(0, self.consecutive_failures - 1)
            self.rate_limited = False
            return True

        return False

    async def get_followers_list(
        self,
        username: str,
        max_count: int = 50  # Reduced from 1000 to avoid rate limits
    ) -> List[str]:
        """
        Get the followers list for a user.
        Returns list of usernames only (no need for follower counts).
        Uses conservative scrolling to avoid rate limits.
        """
        print(f"   📊 Getting followers for @{username}...")

        # Use regular followers page (not verified_followers which has limited results)
        url = f"https://x.com/{username}/followers"

        if not await self._navigate_with_retry(url):
            print(f"      ❌ Failed to navigate to followers after retries")
            return []

        followers = []
        seen_usernames = set()
        scroll_count = 0
        max_scrolls = 10  # Reduced from 50 to avoid rate limits
        no_new_count = 0

        while len(followers) < max_count and scroll_count < max_scrolls:
            dom_result = await self.client._request("GET", "/dom/elements")
            if not dom_result.get("success"):
                break

            new_accounts = self._extract_usernames(dom_result)
            new_found = 0

            for uname in new_accounts:
                if uname not in seen_usernames and uname.lower() != username.lower():
                    seen_usernames.add(uname)
                    followers.append(uname)
                    new_found += 1

            if len(followers) >= max_count:
                break

            # Track if we're getting new results
            if new_found == 0:
                no_new_count += 1
                if no_new_count >= 3:
                    print(f"      ℹ️ No new followers found, stopping scroll")
                    break
            else:
                no_new_count = 0

            # Scroll to load more with human-like delay
            await self.client._request("POST", "/scroll", {
                "x": 500, "y": 800, "scroll_x": 0, "scroll_y": 3
            })
            scroll_count += 1
            await self._smart_delay()

        print(f"      ✅ Got {len(followers)} followers")
        return followers[:max_count]

    def _extract_usernames(self, dom_result: Dict) -> List[str]:
        """Extract usernames from DOM."""
        usernames = []
        elements = dom_result.get("elements", [])
        excluded = {"home", "explore", "notifications", "messages", "compose", "i", "settings", "search", "x", "twitter"}

        for el in elements:
            href = el.get("href", "")
            if href.startswith("/") and len(href) > 1:
                username = href[1:].split("/")[0]
                if username and username.lower() not in excluded and not username.startswith("_"):
                    usernames.append(username)

            text = el.get("text", "")
            if text.startswith("@"):
                username = text[1:].split()[0]
                if username and username.lower() not in excluded:
                    usernames.append(username)

        return list(set(usernames))

    async def get_common_followers_count(self, username: str) -> Optional[Dict]:
        """
        Use X's "Followers you know" tab to get mutual followers.

        X has a dedicated tab at: https://x.com/{username}/followers_you_follow
        This shows ALL followers that you both follow - perfect for competitor discovery!

        Returns:
            {
                "count": int,  # Number of mutual followers
                "sample_accounts": List[str]  # Sample of common followers
            }
        """
        print(f"      🔍 Checking @{username}'s mutual followers...")

        # Check if we're heavily rate limited - if so, skip this account
        if self.consecutive_failures >= 5:
            print(f"         ⚠️ Skipping due to rate limiting (will retry later)")
            return None

        # Navigate to "Followers you know" tab with retry
        url = f"https://x.com/{username}/followers_you_follow"

        if not await self._navigate_with_retry(url, max_retries=2):
            print(f"         ⚠️ Failed to navigate (rate limited)")
            return None

        # Scroll and collect followers from this tab (conservative)
        mutual_followers = []
        seen_usernames = set()
        scroll_count = 0
        max_scrolls = 5  # Reduced from 10

        while scroll_count < max_scrolls:
            dom_result = await self.client._request("GET", "/dom/elements")
            if not dom_result.get("success"):
                break

            # Extract usernames from this page
            new_accounts = self._extract_usernames(dom_result)

            for username_found in new_accounts:
                if username_found not in seen_usernames and username_found.lower() != username.lower():
                    seen_usernames.add(username_found)
                    mutual_followers.append(username_found)

            # Check if we got new accounts this scroll
            before_scroll = len(mutual_followers)

            # Scroll to load more
            await self.client._request("POST", "/scroll", {
                "x": 500, "y": 800, "scroll_x": 0, "scroll_y": 3
            })
            scroll_count += 1
            await self._smart_delay()

            # If no new accounts after scroll, we've reached the end
            if len(mutual_followers) == before_scroll:
                break

        mutual_count = len(mutual_followers)

        if mutual_count > 0:
            print(f"         ✅ {mutual_count} mutual followers")
            return {
                "count": mutual_count,
                "sample_accounts": mutual_followers[:20]  # First 20 as sample
            }
        else:
            print(f"         ℹ️  No mutual followers found")
            return {"count": 0, "sample_accounts": []}

    async def discover_competitors_fast(
        self,
        user_handle: str,
        max_followers_to_check: int = 20  # Reduced from 100 to avoid rate limits
    ) -> Dict:
        """
        ULTRA-FAST competitor discovery using X's native common follower display.

        This is 10x faster than the other methods because we don't scrape
        full following lists - we just read X's own "Followed by" display!

        RATE LIMIT PROTECTION:
        - Conservative defaults (20 accounts max)
        - Exponential backoff on failures
        - Random delays between requests
        - Early termination if heavily rate limited

        Args:
            user_handle: Your X handle
            max_followers_to_check: How many of your followers to analyze (default: 20)

        Returns:
            Graph data with competitor matches sorted by mutual connections
        """
        print(f"\n{'='*80}")
        print(f"⚡ X NATIVE COMMON FOLLOWERS DISCOVERY FOR @{user_handle}")
        print(f"   (Rate-limited mode: checking up to {max_followers_to_check} accounts)")
        print(f"{'='*80}\n")

        # Reset rate limit state
        self.consecutive_failures = 0
        self.rate_limited = False

        # STEP 1: Get YOUR followers
        print(f"STEP 1: Getting YOUR followers list...")
        your_followers = await self.get_followers_list(user_handle, max_followers_to_check * 2)

        if len(your_followers) == 0:
            print(f"❌ Could not get followers list (possibly rate limited)")
            return {
                "user_handle": user_handle,
                "analyzed_followers": 0,
                "successful_checks": 0,
                "all_competitors_raw": [],
                "top_competitors": [],
                "high_quality_competitors": 0,
                "created_at": datetime.utcnow().isoformat(),
                "last_updated": datetime.utcnow().isoformat(),
                "method": "x_native_common_followers",
                "error": "Rate limited - please try again later",
                "config": {"max_followers_checked": max_followers_to_check}
            }

        print(f"✅ You have {len(your_followers)} followers (sampled)\n")

        # STEP 2: For each follower, check their profile for "Followed by" count
        print(f"STEP 2: Checking profiles for mutual connections...\n")

        competitors = []
        cancel_namespace = (self.user_id, "discovery_control")
        progress_namespace = (self.user_id, "discovery_progress")

        # Analyze up to max_followers_to_check
        candidates = your_followers[:max_followers_to_check]
        skipped_due_to_rate_limit = 0

        for i, username in enumerate(candidates, 1):
            # Update progress (only if store is available)
            if self.store:
                self.store.put(progress_namespace, "current", {
                    "current": i,
                    "total": len(candidates),
                    "current_account": username,
                    "status": "analyzing",
                    "stage": "checking_profiles",
                    "rate_limited": self.rate_limited,
                    "consecutive_failures": self.consecutive_failures
                })

                # Check for cancellation
                cancel_items = list(self.store.search(cancel_namespace, limit=1))
                if cancel_items and cancel_items[0].value.get("cancelled"):
                    print(f"\n⚠️ DISCOVERY CANCELLED by user!")
                    print(f"   Processed {i-1}/{len(candidates)} accounts")
                    print(f"   Saving {len(competitors)} partial results...\n")
                    break

            # Check if we should abort due to heavy rate limiting
            if self.consecutive_failures >= 8:
                print(f"\n🚫 STOPPING: Heavy rate limiting detected ({self.consecutive_failures} consecutive failures)")
                print(f"   Processed {i-1}/{len(candidates)} accounts")
                print(f"   Saving {len(competitors)} results...\n")
                break

            print(f"[{i}/{len(candidates)}] Checking @{username}...")

            try:
                # Get X's native common follower count
                common_info = await self.get_common_followers_count(username)

                if common_info is None:
                    skipped_due_to_rate_limit += 1
                    continue

                if common_info['count'] > 0:
                    # Calculate percentage based on your follower count
                    overlap_percentage = round((common_info['count'] / max(len(your_followers), 1)) * 100, 1)

                    competitors.append({
                        "username": username,
                        "mutual_connections": common_info['count'],
                        "overlap_count": common_info['count'],  # For frontend compatibility
                        "overlap_percentage": overlap_percentage,  # For frontend compatibility
                        "sample_mutual": common_info['sample_accounts'],
                        "discovered_at": datetime.utcnow().isoformat(),
                        "method": "x_native_common_followers"
                    })

                # Rate limit with exponential backoff
                await self._smart_delay(is_navigation=True)

            except Exception as e:
                print(f"      ⚠️ Failed: {e}")
                self.consecutive_failures += 1
                continue

        # STEP 3: Sort by mutual connections
        print(f"\nSTEP 3: Ranking by mutual connections...\n")

        competitors_sorted = sorted(
            competitors,
            key=lambda x: x['mutual_connections'],
            reverse=True
        )

        if competitors_sorted:
            print(f"Top 10 matches:")
            for i, comp in enumerate(competitors_sorted[:10], 1):
                sample = ', '.join(comp['sample_mutual'][:3]) if comp['sample_mutual'] else 'N/A'
                print(f"   {i}. @{comp['username']}: {comp['mutual_connections']} mutual (e.g. {sample})")
        else:
            print(f"   No competitors found (possibly due to rate limiting)")

        # STEP 4: Store results
        print(f"\nSTEP 4: Storing results...\n")

        # Add empty posts array for compatibility
        for comp in competitors_sorted:
            comp['posts'] = []
            comp['post_count'] = 0

        graph_data = {
            "user_handle": user_handle,
            "analyzed_followers": len(candidates),
            "successful_checks": len(competitors),
            "skipped_due_to_rate_limit": skipped_due_to_rate_limit,
            "all_competitors_raw": competitors_sorted,
            "top_competitors": competitors_sorted[:20],
            "high_quality_competitors": len([c for c in competitors_sorted if c['mutual_connections'] >= 5]),
            "created_at": datetime.utcnow().isoformat(),
            "last_updated": datetime.utcnow().isoformat(),
            "method": "x_native_common_followers",
            "config": {
                "max_followers_checked": max_followers_to_check
            }
        }

        # Store results (only if store is available)
        if self.store:
            self.store.put(self.namespace_graph, "latest", graph_data)

            # Store individual competitors
            for comp in competitors_sorted:
                self.store.put(
                    self.namespace_competitors,
                    comp["username"],
                    {**comp, "status": "discovered"}
                )

        print(f"{'='*80}")
        print(f"✅ X NATIVE DISCOVERY COMPLETE!")
        print(f"   - Analyzed {len(competitors)} accounts with mutual connections")
        print(f"   - Skipped due to rate limits: {skipped_due_to_rate_limit}")
        print(f"   - High quality matches (5+ mutual): {graph_data['high_quality_competitors']}")
        if competitors_sorted:
            print(f"   - Top match: @{competitors_sorted[0]['username']} ({competitors_sorted[0]['mutual_connections']} mutual)")
            if len(competitors_sorted) > 1:
                print(f"   - 2nd match: @{competitors_sorted[1]['username']} ({competitors_sorted[1]['mutual_connections']} mutual)")
        print(f"{'='*80}\n")

        return graph_data
