"""
Follower-Based Competitor Discovery

STRATEGY:
Instead of analyzing who YOU follow (often one-way follows of big accounts),
analyze YOUR FOLLOWERS - people already interested in your content are more
likely to be competitors or peers in your niche.

Algorithm:
1. Get YOUR followers list (1000+ accounts)
2. Filter for peer accounts (500-10K followers range)
3. For each peer, get THEIR following list
4. Calculate overlap with YOUR following
5. High overlap = true competitor (similar interests)

Benefits:
- Much faster (2-3 minutes vs 10)
- Better quality matches (these are your actual peers)
- More relevant competitors (already in your niche)
"""

import asyncio
from datetime import datetime
from typing import List, Dict, Set, Optional
from langgraph.store.base import BaseStore


class FollowerBasedDiscovery:
    """
    Discovers competitors by analyzing YOUR followers.
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
    ) -> List[Dict]:
        """
        Get the followers list for a user with basic stats.
        Returns list of dicts with username and follower_count.
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
        max_scrolls = 50  # More scrolls to get more followers

        while len(followers) < max_count and scroll_count < max_scrolls:
            dom_result = await self.client._request("GET", "/dom/elements")
            if not dom_result.get("success"):
                break

            new_accounts = self._extract_follower_info(dom_result)

            for account in new_accounts:
                username_key = account['username']
                if username_key not in seen_usernames:
                    seen_usernames.add(username_key)
                    followers.append(account)

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

    def _extract_follower_info(self, dom_result: Dict) -> List[Dict]:
        """
        Extract follower usernames and basic info from DOM.
        Returns list of dicts with username and estimated follower_count.
        """
        followers = []
        elements = dom_result.get("elements", [])
        excluded = {"home", "explore", "notifications", "messages", "compose", "i", "settings", "search"}

        # Look for follower count patterns in text
        for el in elements:
            # Extract username from href
            href = el.get("href", "")
            if href.startswith("/") and len(href) > 1:
                username = href[1:].split("/")[0]  # Get username before any /status or /photo
                if username and "/" not in username and username not in excluded:
                    # Try to find follower count nearby in text
                    text = el.get("text", "")
                    follower_count = self._extract_follower_count(text)

                    followers.append({
                        "username": username,
                        "follower_count": follower_count
                    })

            # Also check @mentions
            text = el.get("text", "")
            if text.startswith("@"):
                username = text[1:].split()[0]
                if username and username not in excluded:
                    followers.append({
                        "username": username,
                        "follower_count": 0  # Unknown
                    })

        return followers

    def _extract_follower_count(self, text: str) -> int:
        """
        Try to extract follower count from text.
        Looks for patterns like "1.2K followers" or "500 Followers".
        """
        import re

        # Pattern: number followed by K/M and "follower"
        pattern = r'([\d.]+)\s*([KkMm])?\s*[Ff]ollowers?'
        match = re.search(pattern, text)

        if match:
            num = float(match.group(1))
            multiplier = match.group(2)

            if multiplier and multiplier.upper() == 'K':
                return int(num * 1000)
            elif multiplier and multiplier.upper() == 'M':
                return int(num * 1000000)
            else:
                return int(num)

        return 0  # Unknown

    async def get_following_list(
        self,
        username: str,
        max_count: int = 1000  # Increased from 200 to 1000
    ) -> Set[str]:
        """
        Get the following list for a user.
        Returns as a Set for fast comparison.
        """
        print(f"      📊 Getting following list for @{username}...")

        url = f"https://x.com/{username}/following"
        result = await self.client._request("POST", "/navigate", {"url": url})

        if not result.get("success"):
            print(f"         ⚠️ Failed: {result.get('error')}")
            return set()

        await asyncio.sleep(2)

        following = []
        scroll_count = 0
        max_scrolls = 50  # Increased from 10 to 50 to get ~1000 accounts

        while len(following) < max_count and scroll_count < max_scrolls:
            dom_result = await self.client._request("GET", "/dom/elements")
            if not dom_result.get("success"):
                break

            new_accounts = self._extract_usernames(dom_result)
            for account in new_accounts:
                if account not in following:
                    following.append(account)

            if len(following) >= max_count:
                break

            await self.client._request("POST", "/scroll", {
                "x": 500, "y": 800, "scroll_x": 0, "scroll_y": 5
            })
            scroll_count += 1
            await asyncio.sleep(1)

        result_set = set(following[:max_count])
        print(f"         ✅ Got {len(result_set)} accounts")
        return result_set

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

    def calculate_overlap(
        self,
        user_following: Set[str],
        competitor_following: Set[str]
    ) -> Dict:
        """
        Calculate overlap between two following lists.
        Uses YOUR following as denominator.
        """
        intersection = user_following.intersection(competitor_following)
        denominator = len(user_following)

        if denominator == 0:
            return {
                "overlap_count": 0,
                "overlap_percentage": 0.0,
                "common_accounts": []
            }

        overlap_percentage = round((len(intersection) / denominator) * 100, 1)

        return {
            "overlap_count": len(intersection),
            "overlap_percentage": overlap_percentage,
            "common_accounts": sorted(list(intersection))[:50]
        }

    async def discover_competitors(
        self,
        user_handle: str,
        max_followers_to_check: int = 100,
        min_follower_count: int = 500,
        max_follower_count: int = 10000,
        max_user_following: int = 200
    ) -> Dict:
        """
        Discover competitors by analyzing YOUR followers.

        Args:
            user_handle: Your X handle
            max_followers_to_check: How many of your followers to analyze
            min_follower_count: Min followers for peer accounts
            max_follower_count: Max followers for peer accounts
            max_user_following: Max following to get from each account

        Returns:
            Graph data with competitor matches
        """
        print(f"\n{'='*80}")
        print(f"🎯 FOLLOWER-BASED COMPETITOR DISCOVERY FOR @{user_handle}")
        print(f"{'='*80}\n")

        # STEP 1: Get YOUR following list (for comparison)
        print(f"STEP 1: Getting YOUR following list for comparison...")
        user_following_set = await self.get_following_list(user_handle, max_user_following)

        if not user_following_set:
            raise Exception("Failed to get user's following list")

        print(f"✅ You follow {len(user_following_set)} accounts\n")

        # STEP 2: Get YOUR followers
        print(f"STEP 2: Getting YOUR followers list...")
        your_followers = await self.get_followers_list(user_handle, max_followers_to_check * 3)
        print(f"✅ You have {len(your_followers)} followers (sampled)\n")

        # STEP 3: Filter for peer accounts (similar follower count range)
        print(f"STEP 3: Filtering for peer accounts ({min_follower_count}-{max_follower_count} followers)...")

        peers = []
        for follower in your_followers:
            count = follower['follower_count']
            # If count is unknown (0), include them anyway
            if count == 0 or (min_follower_count <= count <= max_follower_count):
                peers.append(follower)

        print(f"✅ Found {len(peers)} potential peer accounts\n")

        # Take top candidates
        candidates_to_analyze = peers[:max_followers_to_check]
        print(f"STEP 4: Will analyze {len(candidates_to_analyze)} of your followers...\n")

        # STEP 5: For each peer, analyze their following overlap
        print(f"STEP 5: Analyzing following overlap with each peer...\n")

        competitors = []
        cancel_namespace = (self.user_id, "discovery_control")
        progress_namespace = (self.user_id, "discovery_progress")

        for i, peer in enumerate(candidates_to_analyze, 1):
            # Update progress
            self.store.put(progress_namespace, "current", {
                "current": i,
                "total": len(candidates_to_analyze),
                "current_account": peer['username'],
                "status": "analyzing",
                "stage": "analyzing_followers"
            })

            # Check for cancellation
            cancel_items = list(self.store.search(cancel_namespace, limit=1))
            if cancel_items and cancel_items[0].value.get("cancelled"):
                print(f"\n⚠️ DISCOVERY CANCELLED by user!")
                print(f"   Processed {i-1}/{len(candidates_to_analyze)} peers")
                print(f"   Saving {len(competitors)} partial results...\n")
                break

            username = peer['username']
            print(f"[{i}/{len(candidates_to_analyze)}] Analyzing @{username}...")

            try:
                # Get their following list
                peer_following = await self.get_following_list(username, max_user_following)

                if not peer_following:
                    print(f"      ⚠️ Failed to get following list, skipping")
                    continue

                # Filter out accounts with too few following
                if len(peer_following) < 20:
                    print(f"      ⚠️ Only follows {len(peer_following)} accounts, skipping")
                    continue

                # Calculate overlap
                overlap_result = self.calculate_overlap(user_following_set, peer_following)

                print(f"      ✅ Overlap: {overlap_result['overlap_percentage']}% ({overlap_result['overlap_count']} common)")

                # Store result
                competitors.append({
                    "username": username,
                    "overlap_percentage": overlap_result['overlap_percentage'],
                    "overlap_count": overlap_result['overlap_count'],
                    "common_follows": overlap_result['common_accounts'],
                    "following_count": len(peer_following),
                    "follower_count": peer.get('follower_count', 0),
                    "discovered_at": datetime.utcnow().isoformat(),
                    "method": "follower_based"
                })

                # Rate limit
                await asyncio.sleep(2)

            except Exception as e:
                print(f"      ⚠️ Failed: {e}")
                continue

        # STEP 6: Sort by overlap
        print(f"\nSTEP 6: Ranking by overlap percentage...\n")

        competitors_sorted = sorted(
            competitors,
            key=lambda x: x['overlap_percentage'],
            reverse=True
        )

        print(f"Top 10 matches:")
        for i, comp in enumerate(competitors_sorted[:10], 1):
            print(f"   {i}. @{comp['username']}: {comp['overlap_percentage']}% ({comp['overlap_count']} common) - {comp['follower_count']} followers")

        # STEP 7: Store results
        print(f"\nSTEP 7: Storing results...\n")

        # Skip post scraping for now
        for comp in competitors_sorted:
            comp['posts'] = []
            comp['post_count'] = 0

        graph_data = {
            "user_handle": user_handle,
            "user_following_count": len(user_following_set),
            "user_following": sorted(list(user_following_set)),
            "analyzed_followers": len(candidates_to_analyze),
            "successful_comparisons": len(competitors),
            "all_competitors_raw": competitors_sorted,
            "top_competitors": competitors_sorted[:20],
            "high_quality_competitors": len([c for c in competitors_sorted if c['overlap_percentage'] >= 30]),
            "created_at": datetime.utcnow().isoformat(),
            "last_updated": datetime.utcnow().isoformat(),
            "method": "follower_based_discovery",
            "config": {
                "max_followers_checked": max_followers_to_check,
                "min_follower_count": min_follower_count,
                "max_follower_count": max_follower_count,
                "max_user_following": max_user_following
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
        print(f"✅ FOLLOWER-BASED DISCOVERY COMPLETE!")
        print(f"   - Analyzed {len(competitors)} of your followers")
        print(f"   - High quality matches (30%+ overlap): {graph_data['high_quality_competitors']}")
        if competitors_sorted:
            print(f"   - Top match: @{competitors_sorted[0]['username']} ({competitors_sorted[0]['overlap_percentage']}% overlap)")
            if len(competitors_sorted) > 1:
                print(f"   - 2nd match: @{competitors_sorted[1]['username']} ({competitors_sorted[1]['overlap_percentage']}%)")
        print(f"{'='*80}\n")

        return graph_data
