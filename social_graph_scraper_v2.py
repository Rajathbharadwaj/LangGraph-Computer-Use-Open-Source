"""
Social Graph Scraper V2 - Direct Following Comparison

OPTIMIZED APPROACH:
Instead of sampling followers (indirect), we directly compare following lists.

Algorithm:
1. Get YOUR following list (200 accounts)
2. From follower samples, get list of potential competitors (3000+ accounts)
3. For top candidates, scrape THEIR following list (200 accounts)
4. Calculate direct overlap: How many of YOUR follows do THEY also follow?
5. Result: Accounts with 60-90% overlap = true competitors!

This is the STANDARD industry approach (LinkedIn, Twitter recommendations, etc.)
"""

import asyncio
from datetime import datetime
from typing import List, Dict, Set, Optional
from langgraph.store.base import BaseStore


class DirectComparisonScraper:
    """
    Optimized scraper using direct following list comparison.
    """

    def __init__(self, browser_client):
        self.client = browser_client

    async def get_following_list(
        self,
        username: str,
        max_count: int = 200
    ) -> Set[str]:
        """
        Get the following list for a user.
        Returns as a Set for fast comparison.
        """
        print(f"   📊 Getting following list for @{username}...")

        url = f"https://x.com/{username}/following"
        result = await self.client._request("POST", "/navigate", {"url": url})

        if not result.get("success"):
            print(f"      ⚠️ Failed: {result.get('error')}")
            return set()

        await asyncio.sleep(2)  # Reduced from 3 for speed

        following = []
        scroll_count = 0
        max_scrolls = 10  # Reduced for speed

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
            await asyncio.sleep(1)  # Reduced from 2 for speed

        result_set = set(following[:max_count])
        print(f"      ✅ Got {len(result_set)} accounts")
        return result_set

    def _extract_usernames(self, dom_result: Dict) -> List[str]:
        """Extract usernames from DOM."""
        usernames = []
        elements = dom_result.get("elements", [])
        excluded = {"home", "explore", "notifications", "messages", "compose", "i", "settings", "search"}

        for el in elements:
            href = el.get("href", "")
            if href.startswith("/") and len(href) > 1:
                username = href[1:]
                if "/" not in username and username not in excluded:
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
        Calculate direct overlap between two following lists.

        Returns:
            overlap_count: Number of shared accounts
            overlap_percentage: Percentage match
            common_accounts: List of shared accounts
        """
        intersection = user_following.intersection(competitor_following)

        # Use YOUR following count as denominator (what % of your interests do they share?)
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
            "common_accounts": sorted(list(intersection))[:50]  # Limit for storage
        }


class OptimizedSocialGraphBuilder:
    """
    Builds social graph using direct following comparison.
    """

    def __init__(self, store: BaseStore, user_id: str):
        self.store = store
        self.user_id = user_id
        self.namespace_graph = (user_id, "social_graph_v2")
        self.namespace_competitors = (user_id, "competitor_profiles_v2")

    async def build_optimized_graph(
        self,
        user_handle: str,
        max_user_following: int = 100,  # Reduced from 200 for speed
        candidates_to_check: int = 10   # Reduced from 30 for speed
    ) -> Dict:
        """
        Build social graph using direct following comparison.

        Args:
            user_handle: User's X handle
            max_user_following: Max accounts to get from user's following
            candidates_to_check: How many candidates to deeply analyze

        Returns:
            Graph data with high-accuracy competitors
        """
        print(f"\n{'='*80}")
        print(f"🎯 OPTIMIZED COMPETITOR DISCOVERY FOR @{user_handle}")
        print(f"{'='*80}\n")

        from social_graph_scraper import SocialGraphScraper, SocialGraphBuilder
        from async_playwright_tools import _global_client

        scraper = DirectComparisonScraper(_global_client)
        old_scraper = SocialGraphScraper(_global_client)

        # STEP 1: Get user's following list
        print(f"STEP 1: Getting YOUR following list...")
        user_following_set = await scraper.get_following_list(user_handle, max_user_following)

        if not user_following_set:
            raise Exception("Failed to get user's following list")

        print(f"✅ You follow {len(user_following_set)} accounts\n")

        # STEP 2: Use YOUR following as candidates (people you follow are potential competitors)
        print(f"STEP 2: Using your following list as candidates...")
        candidate_usernames = list(user_following_set)[:min(candidates_to_check, len(user_following_set))]
        print(f"✅ Will analyze {len(candidate_usernames)} accounts you follow\n")

        # STEP 3: Prepare candidates for analysis
        print(f"STEP 3: Preparing to compare following lists...\n")
        top_candidates = [{"username": username} for username in candidate_usernames]

        # STEP 4: For each candidate, get THEIR following and compare
        print(f"STEP 4: Comparing following lists directly...\n")

        competitors = []
        cancel_namespace = (self.user_id, "discovery_control")

        for i, candidate in enumerate(top_candidates, 1):
            # Update progress
            progress_namespace = (self.user_id, "discovery_progress")
            self.store.put(progress_namespace, "current", {
                "current": i,
                "total": len(top_candidates),
                "current_account": candidate['username'],
                "status": "analyzing",
                "stage": "analyzing_accounts"
            })

            # Check for cancellation
            cancel_items = list(self.store.search(cancel_namespace, limit=1))
            if cancel_items and cancel_items[0].value.get("cancelled"):
                print(f"\n⚠️ DISCOVERY CANCELLED by user!")
                print(f"   Processed {i-1}/{len(top_candidates)} candidates")
                print(f"   Saving {len(competitors)} partial results...\n")
                break

            username = candidate['username']
            print(f"[{i}/{len(top_candidates)}] Analyzing @{username}...")

            try:
                # Get their following list
                competitor_following = await scraper.get_following_list(username, max_user_following)

                if not competitor_following:
                    print(f"      ⚠️ Failed to get following list, skipping")
                    continue

                # Filter out accounts with too few following (noisy data)
                if len(competitor_following) < 20:
                    print(f"      ⚠️ Only follows {len(competitor_following)} accounts, skipping (too small sample)")
                    continue

                # Calculate DIRECT overlap
                overlap_result = scraper.calculate_overlap(user_following_set, competitor_following)

                print(f"      ✅ Direct overlap: {overlap_result['overlap_percentage']}% ({overlap_result['overlap_count']} accounts)")

                # Store result
                competitors.append({
                    "username": username,
                    "overlap_percentage": overlap_result['overlap_percentage'],
                    "overlap_count": overlap_result['overlap_count'],
                    "common_follows": overlap_result['common_accounts'],
                    "following_count": len(competitor_following),
                    "discovered_at": datetime.utcnow().isoformat(),
                    "method": "direct_comparison"
                })

                # Rate limit (reduced for speed)
                await asyncio.sleep(2)

            except Exception as e:
                print(f"      ⚠️ Failed: {e}")
                continue

        # STEP 5: Sort by overlap and store
        print(f"\nSTEP 5: Ranking by direct overlap...\n")

        competitors_sorted = sorted(
            competitors,
            key=lambda x: x['overlap_percentage'],
            reverse=True
        )

        for i, comp in enumerate(competitors_sorted[:10], 1):
            print(f"   {i}. @{comp['username']}: {comp['overlap_percentage']}% ({comp['overlap_count']} shared follows)")

        # STEP 6: Skip post scraping for speed - can scrape later
        print(f"\nSTEP 6: Skipping post scraping for speed (use 'Scrape Posts' button later)...\n")

        for comp in competitors_sorted:
            comp['posts'] = []
            comp['post_count'] = 0

        # STEP 7: Store results
        print(f"\nSTEP 7: Storing results...")

        graph_data = {
            "user_handle": user_handle,
            "user_following_count": len(user_following_set),
            "user_following": sorted(list(user_following_set)),
            "analyzed_candidates": len(top_candidates),
            "successful_comparisons": len(competitors),
            "top_competitors": competitors_sorted,
            "created_at": datetime.utcnow().isoformat(),
            "last_updated": datetime.utcnow().isoformat(),
            "method": "optimized_direct_comparison",
            "config": {
                "max_user_following": max_user_following,
                "candidates_checked": candidates_to_check
            }
        }

        self.store.put(self.namespace_graph, "latest", graph_data)

        for comp in competitors_sorted:
            self.store.put(
                self.namespace_competitors,
                comp["username"],
                {**comp, "status": "discovered"}
            )

        print(f"\n{'='*80}")
        print(f"✅ OPTIMIZED DISCOVERY COMPLETE!")
        print(f"   - Analyzed {len(competitors)} competitors")
        if competitors_sorted:
            print(f"   - Top match: @{competitors_sorted[0]['username']} ({competitors_sorted[0]['overlap_percentage']}% overlap)")
            if len(competitors_sorted) > 1:
                print(f"   - 2nd match: @{competitors_sorted[1]['username']} ({competitors_sorted[1]['overlap_percentage']}%)")
        print(f"{'='*80}\n")

        return graph_data

    def get_graph(self) -> Optional[Dict]:
        """Get the optimized graph from database."""
        items = list(self.store.search(self.namespace_graph, limit=1))
        if items:
            return items[0].value
        return None
