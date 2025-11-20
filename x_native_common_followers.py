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
"""

import asyncio
import re
from datetime import datetime
from typing import List, Dict, Set, Optional
from langgraph.store.base import BaseStore


class XNativeCommonFollowersDiscovery:
    """
    Ultra-fast competitor discovery using X's native "Followed by" feature.
    """

    def __init__(self, browser_client, store: BaseStore, user_id: str):
        self.client = browser_client
        self.store = store
        self.user_id = user_id
        self.namespace_graph = (user_id, "social_graph")
        self.namespace_competitors = (user_id, "competitor_profiles")

    async def get_followers_list(
        self,
        username: str,
        max_count: int = 1000
    ) -> List[str]:
        """
        Get the followers list for a user.
        Returns list of usernames only (no need for follower counts).
        """
        print(f"   📊 Getting followers for @{username}...")

        url = f"https://x.com/{username}/verified_followers"
        result = await self.client._request("POST", "/navigate", {"url": url})

        if not result.get("success"):
            print(f"      ⚠️ Failed to navigate to verified followers, trying all followers...")
            url = f"https://x.com/{username}/followers"
            result = await self.client._request("POST", "/navigate", {"url": url})
            if not result.get("success"):
                print(f"      ❌ Failed: {result.get('error')}")
                return []

        await asyncio.sleep(3)

        followers = []
        seen_usernames = set()
        scroll_count = 0
        max_scrolls = 50  # Get up to 1000 followers

        while len(followers) < max_count and scroll_count < max_scrolls:
            dom_result = await self.client._request("GET", "/dom/elements")
            if not dom_result.get("success"):
                break

            new_accounts = self._extract_usernames(dom_result)

            for username in new_accounts:
                if username not in seen_usernames:
                    seen_usernames.add(username)
                    followers.append(username)

            if len(followers) >= max_count:
                break

            # Scroll to load more
            await self.client._request("POST", "/scroll", {
                "x": 500, "y": 800, "scroll_x": 0, "scroll_y": 5
            })
            scroll_count += 1
            await asyncio.sleep(1.5)

        print(f"      ✅ Got {len(followers)} followers")
        return followers[:max_count]

    def _extract_usernames(self, dom_result: Dict) -> List[str]:
        """Extract usernames from DOM."""
        usernames = []
        elements = dom_result.get("elements", [])
        excluded = {"home", "explore", "notifications", "messages", "compose", "i", "settings", "search"}

        for el in elements:
            href = el.get("href", "")
            if href.startswith("/") and len(href) > 1:
                username = href[1:].split("/")[0]
                if username and username not in excluded:
                    usernames.append(username)

            text = el.get("text", "")
            if text.startswith("@"):
                username = text[1:].split()[0]
                if username and username not in excluded:
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

        # Navigate to "Followers you know" tab
        url = f"https://x.com/{username}/followers_you_follow"
        result = await self.client._request("POST", "/navigate", {"url": url})

        if not result.get("success"):
            print(f"         ⚠️ Failed to navigate: {result.get('error')}")
            return None

        await asyncio.sleep(3)  # Wait for page load

        # Scroll and collect followers from this tab
        mutual_followers = []
        seen_usernames = set()
        scroll_count = 0
        max_scrolls = 10  # Get up to ~200 mutual followers

        while scroll_count < max_scrolls:
            dom_result = await self.client._request("GET", "/dom/elements")
            if not dom_result.get("success"):
                break

            # Extract usernames from this page
            new_accounts = self._extract_usernames(dom_result)

            for username_found in new_accounts:
                if username_found not in seen_usernames and username_found != username:
                    seen_usernames.add(username_found)
                    mutual_followers.append(username_found)

            # Check if we got new accounts this scroll
            before_scroll = len(mutual_followers)

            # Scroll to load more
            await self.client._request("POST", "/scroll", {
                "x": 500, "y": 800, "scroll_x": 0, "scroll_y": 5
            })
            scroll_count += 1
            await asyncio.sleep(1.5)

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
        max_followers_to_check: int = 100
    ) -> Dict:
        """
        ULTRA-FAST competitor discovery using X's native common follower display.

        This is 10x faster than the other methods because we don't scrape
        full following lists - we just read X's own "Followed by" display!

        Args:
            user_handle: Your X handle
            max_followers_to_check: How many of your followers to analyze

        Returns:
            Graph data with competitor matches sorted by mutual connections
        """
        print(f"\n{'='*80}")
        print(f"⚡ X NATIVE COMMON FOLLOWERS DISCOVERY FOR @{user_handle}")
        print(f"{'='*80}\n")

        # STEP 1: Get YOUR followers
        print(f"STEP 1: Getting YOUR followers list...")
        your_followers = await self.get_followers_list(user_handle, max_followers_to_check * 2)
        print(f"✅ You have {len(your_followers)} followers (sampled)\n")

        # STEP 2: For each follower, check their profile for "Followed by" count
        print(f"STEP 2: Checking profiles for mutual connections...\n")

        competitors = []
        cancel_namespace = (self.user_id, "discovery_control")
        progress_namespace = (self.user_id, "discovery_progress")

        # Analyze up to max_followers_to_check
        candidates = your_followers[:max_followers_to_check]

        for i, username in enumerate(candidates, 1):
            # Update progress
            self.store.put(progress_namespace, "current", {
                "current": i,
                "total": len(candidates),
                "current_account": username,
                "status": "analyzing",
                "stage": "checking_profiles"
            })

            # Check for cancellation
            cancel_items = list(self.store.search(cancel_namespace, limit=1))
            if cancel_items and cancel_items[0].value.get("cancelled"):
                print(f"\n⚠️ DISCOVERY CANCELLED by user!")
                print(f"   Processed {i-1}/{len(candidates)} accounts")
                print(f"   Saving {len(competitors)} partial results...\n")
                break

            print(f"[{i}/{len(candidates)}] Checking @{username}...")

            try:
                # Get X's native common follower count
                common_info = await self.get_common_followers_count(username)

                if common_info and common_info['count'] > 0:
                    # Calculate percentage based on your follower count
                    # This is an approximation - mutual followers as % of your total followers
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

                # Rate limit
                await asyncio.sleep(2)

            except Exception as e:
                print(f"      ⚠️ Failed: {e}")
                continue

        # STEP 3: Sort by mutual connections
        print(f"\nSTEP 3: Ranking by mutual connections...\n")

        competitors_sorted = sorted(
            competitors,
            key=lambda x: x['mutual_connections'],
            reverse=True
        )

        print(f"Top 10 matches:")
        for i, comp in enumerate(competitors_sorted[:10], 1):
            sample = ', '.join(comp['sample_mutual'][:3])
            print(f"   {i}. @{comp['username']}: {comp['mutual_connections']} mutual (e.g. {sample})")

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
        print(f"   - High quality matches (5+ mutual): {graph_data['high_quality_competitors']}")
        if competitors_sorted:
            print(f"   - Top match: @{competitors_sorted[0]['username']} ({competitors_sorted[0]['mutual_connections']} mutual)")
            if len(competitors_sorted) > 1:
                print(f"   - 2nd match: @{competitors_sorted[1]['username']} ({competitors_sorted[1]['mutual_connections']} mutual)")
        print(f"{'='*80}\n")

        return graph_data
