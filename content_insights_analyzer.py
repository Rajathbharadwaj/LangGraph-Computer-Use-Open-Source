"""
Content Insights Analyzer

Analyzes competitor posts to extract actionable insights and generate
personalized content suggestions using AI.
"""

import asyncio
from typing import List, Dict, Optional
from datetime import datetime
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
import json


class ContentInsightsAnalyzer:
    """
    Analyzes competitor content to extract patterns and generate insights.
    """

    def __init__(self, llm: Optional[ChatAnthropic] = None):
        self.llm = llm or ChatAnthropic(
            model="claude-sonnet-4-5-20250929",
            temperature=0.3
        )

    async def analyze_competitor_content(
        self,
        competitors_data: List[Dict],
        user_handle: str
    ) -> Dict:
        """
        Analyze all competitor posts to extract insights.

        Args:
            competitors_data: List of competitors with their posts
            user_handle: The user's X handle

        Returns:
            Comprehensive insights including:
            - Top topics
            - Winning patterns
            - Content suggestions
            - Engagement benchmarks
        """

        # Filter competitors with posts
        with_posts = [c for c in competitors_data if c.get('posts') and len(c['posts']) > 0]

        if not with_posts:
            return {
                "success": False,
                "error": "No competitor posts found to analyze"
            }

        # Step 1: Extract high-performing posts
        high_performers = self._extract_high_performers(with_posts)

        # Step 2: Analyze patterns using AI
        patterns = await self._analyze_patterns_with_ai(high_performers)

        # Step 3: Generate content suggestions
        suggestions = await self._generate_content_suggestions(
            patterns,
            high_performers,
            user_handle
        )

        # Step 4: Calculate benchmarks
        benchmarks = self._calculate_benchmarks(with_posts)

        # Step 5: Cluster competitors
        clusters = self._cluster_competitors(competitors_data)

        return {
            "success": True,
            "insights": {
                "top_performers": high_performers[:10],
                "patterns": patterns,
                "suggestions": suggestions,
                "benchmarks": benchmarks,
                "clusters": clusters,
                "analyzed_at": datetime.utcnow().isoformat()
            }
        }

    def _extract_high_performers(self, competitors: List[Dict]) -> List[Dict]:
        """Extract posts with highest engagement."""
        all_posts = []

        for comp in competitors:
            username = comp['username']
            mutual = comp.get('mutual_connections', 0)

            for post in comp.get('posts', []):
                engagement = (
                    post.get('likes', 0) +
                    post.get('retweets', 0) * 2 +  # Retweets worth 2x
                    post.get('replies', 0)
                )

                all_posts.append({
                    'username': username,
                    'text': post.get('text', ''),
                    'likes': post.get('likes', 0),
                    'retweets': post.get('retweets', 0),
                    'replies': post.get('replies', 0),
                    'views': post.get('views', 0),
                    'engagement_score': engagement,
                    'engagement_rate': (engagement / max(post.get('views', 1), 1)) * 100,
                    'competitor_reach': mutual
                })

        # Sort by engagement score
        all_posts.sort(key=lambda x: x['engagement_score'], reverse=True)

        return all_posts[:50]  # Top 50 posts

    async def _analyze_patterns_with_ai(self, posts: List[Dict]) -> Dict:
        """Use AI to analyze patterns in high-performing posts."""

        # Prepare posts for analysis
        posts_text = "\n\n".join([
            f"Post by @{p['username']} ({p['likes']} likes, {p['retweets']} RTs, {p['views']:,} views):\n{p['text'][:500]}"
            for p in posts[:20]  # Top 20 for analysis
        ])

        analysis_prompt = f"""Analyze these top-performing X (Twitter) posts and extract actionable patterns:

{posts_text}

Please provide:
1. **Common Topics**: What topics/themes appear most in high-engagement posts?
2. **Content Patterns**: What makes these posts engaging? (length, style, formatting)
3. **Hooks & Techniques**: What opening lines/hooks work best?
4. **Call-to-Actions**: How do they encourage engagement?
5. **Key Insights**: 3-5 specific observations about what works

Format as JSON with these keys: topics, patterns, hooks, cta_strategies, key_insights
"""

        try:
            response = await self.llm.ainvoke([
                SystemMessage(content="You are an expert social media content strategist analyzing X (Twitter) posts."),
                HumanMessage(content=analysis_prompt)
            ])

            # Try to parse as JSON, fallback to text
            try:
                # Extract JSON from response
                content = response.content
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0].strip()

                patterns = json.loads(content)
            except:
                # Fallback: structure the response
                patterns = {
                    "raw_analysis": response.content,
                    "topics": ["Analysis available in raw_analysis"],
                    "patterns": [],
                    "hooks": [],
                    "cta_strategies": [],
                    "key_insights": []
                }

            return patterns

        except Exception as e:
            print(f"Error in AI analysis: {e}")
            return {
                "error": str(e),
                "topics": [],
                "patterns": [],
                "hooks": [],
                "cta_strategies": [],
                "key_insights": []
            }

    async def _generate_content_suggestions(
        self,
        patterns: Dict,
        top_posts: List[Dict],
        user_handle: str
    ) -> List[Dict]:
        """Generate personalized content suggestions."""

        suggestion_prompt = f"""Based on the analysis of top-performing posts, generate 5 specific post ideas for @{user_handle}.

Patterns found:
{json.dumps(patterns, indent=2)}

For each suggestion, provide:
1. Post text (ready to use, 280 chars max)
2. Why it will work (based on patterns)
3. Expected engagement type (discussion/viral/educational)

Format as JSON array with keys: post_text, reasoning, engagement_type
"""

        try:
            response = await self.llm.ainvoke([
                SystemMessage(content=f"You are a content strategist creating posts for @{user_handle}. Be specific and actionable."),
                HumanMessage(content=suggestion_prompt)
            ])

            # Parse suggestions
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            suggestions = json.loads(content)

            if isinstance(suggestions, dict) and 'suggestions' in suggestions:
                suggestions = suggestions['suggestions']

            return suggestions[:5]  # Max 5 suggestions

        except Exception as e:
            print(f"Error generating suggestions: {e}")
            return [{
                "post_text": "Analysis complete - check insights for patterns",
                "reasoning": "Error generating suggestions",
                "engagement_type": "N/A"
            }]

    def _calculate_benchmarks(self, competitors: List[Dict]) -> Dict:
        """Calculate engagement benchmarks."""

        all_posts = []
        for comp in competitors:
            all_posts.extend(comp.get('posts', []))

        if not all_posts:
            return {}

        likes = [p.get('likes', 0) for p in all_posts if p.get('likes', 0) > 0]
        retweets = [p.get('retweets', 0) for p in all_posts if p.get('retweets', 0) > 0]
        replies = [p.get('replies', 0) for p in all_posts if p.get('replies', 0) > 0]
        views = [p.get('views', 0) for p in all_posts if p.get('views', 0) > 0]

        def percentile(data, p):
            if not data:
                return 0
            sorted_data = sorted(data)
            k = (len(sorted_data) - 1) * p
            f = int(k)
            c = k - f
            if f + 1 < len(sorted_data):
                return sorted_data[f] + c * (sorted_data[f + 1] - sorted_data[f])
            return sorted_data[f]

        return {
            "total_posts_analyzed": len(all_posts),
            "average_likes": sum(likes) / len(likes) if likes else 0,
            "average_retweets": sum(retweets) / len(retweets) if retweets else 0,
            "average_replies": sum(replies) / len(replies) if replies else 0,
            "average_views": sum(views) / len(views) if views else 0,
            "median_likes": percentile(likes, 0.5) if likes else 0,
            "top_10_percent_likes": percentile(likes, 0.9) if likes else 0,
            "top_25_percent_likes": percentile(likes, 0.75) if likes else 0,
            "engagement_goal": {
                "beginner": percentile(likes, 0.25) if likes else 0,
                "intermediate": percentile(likes, 0.5) if likes else 0,
                "advanced": percentile(likes, 0.75) if likes else 0,
                "expert": percentile(likes, 0.9) if likes else 0
            }
        }

    def _cluster_competitors(self, competitors: List[Dict]) -> Dict:
        """
        Cluster competitors based on follower count and analyze account types.

        Tiers:
        - Nano: 1K-10K followers
        - Micro: 10K-50K followers
        - Mid: 50K-500K followers
        - Macro: 500K-1M followers
        - Mega: 1M+ followers
        """

        def get_tier_from_followers(followers: int) -> str:
            """Tier based on follower count."""
            if followers < 1000:
                return "Nano (<1K)"
            elif followers < 10000:
                return "Nano (1K-10K)"
            elif followers < 50000:
                return "Micro (10K-50K)"
            elif followers < 500000:
                return "Mid (50K-500K)"
            elif followers < 1000000:
                return "Macro (500K-1M)"
            else:
                return "Mega (1M+)"

        def get_tier_from_engagement(avg_engagement: float) -> str:
            """Tier based on average engagement (fallback when follower count unavailable)."""
            # Engagement-based tiers (based on typical engagement rates)
            if avg_engagement < 50:
                return "Micro Influencer"
            elif avg_engagement < 200:
                return "Growing Creator"
            elif avg_engagement < 1000:
                return "Mid-Tier Creator"
            elif avg_engagement < 5000:
                return "Popular Creator"
            else:
                return "Viral Creator"

        def infer_account_type(comp: Dict) -> str:
            """Infer account type from username and metrics."""
            username = comp.get('username', '').lower()
            follower_count = comp.get('follower_count', 0)

            # Check for common patterns
            if any(keyword in username for keyword in ['official', 'hq', 'news', 'media', 'press']):
                return "Media/Official"
            elif any(keyword in username for keyword in ['ceo', 'founder', 'co']):
                return "Founder/Executive"
            elif follower_count > 100000 and comp.get('verified', False):
                return "Influencer"
            elif any(keyword in username for keyword in ['dev', 'engineer', 'tech', 'code']):
                return "Tech Professional"
            else:
                return "Personal Brand"

        # Group by tier
        clusters = {}
        has_follower_data = any(comp.get('follower_count', 0) > 0 for comp in competitors)

        for comp in competitors:
            # Calculate average engagement from posts first (needed for engagement-based tiers)
            posts = comp.get('posts', [])
            avg_engagement = 0
            if posts:
                total_engagement = sum(
                    p.get('likes', 0) + p.get('retweets', 0) + p.get('replies', 0)
                    for p in posts
                )
                avg_engagement = total_engagement / len(posts)

            # Determine tier (use followers if available, otherwise use engagement)
            follower_count = comp.get('follower_count', 0)
            if has_follower_data and follower_count > 0:
                tier = get_tier_from_followers(follower_count)
                tier_metric = follower_count
            else:
                tier = get_tier_from_engagement(avg_engagement)
                tier_metric = avg_engagement

            account_type = infer_account_type(comp)

            if tier not in clusters:
                clusters[tier] = {
                    "count": 0,
                    "accounts": [],
                    "avg_followers": 0,
                    "avg_engagement": 0,
                    "account_types": {},
                    "tier_type": "followers" if has_follower_data else "engagement"
                }

            clusters[tier]["count"] += 1
            clusters[tier]["accounts"].append({
                "username": comp.get('username'),
                "followers": follower_count if has_follower_data else None,
                "tier_metric": tier_metric,
                "account_type": account_type,
                "avg_engagement": round(avg_engagement),
                "post_count": len(posts)
            })

            # Track account types
            if account_type not in clusters[tier]["account_types"]:
                clusters[tier]["account_types"][account_type] = 0
            clusters[tier]["account_types"][account_type] += 1

        # Calculate cluster averages and sort accounts
        for tier in clusters:
            accounts = clusters[tier]["accounts"]
            if accounts:
                # Calculate averages (handle None for followers in engagement mode)
                if has_follower_data:
                    clusters[tier]["avg_followers"] = sum(a.get("followers", 0) for a in accounts if a.get("followers")) / len(accounts)
                else:
                    clusters[tier]["avg_followers"] = 0

                clusters[tier]["avg_engagement"] = sum(a["avg_engagement"] for a in accounts) / len(accounts)

                # Sort accounts by tier_metric descending
                clusters[tier]["accounts"] = sorted(
                    accounts,
                    key=lambda x: x["tier_metric"],
                    reverse=True
                )[:10]  # Top 10 per tier

        # Sort tiers (by follower-based or engagement-based order)
        if has_follower_data:
            tier_order = ["Mega (1M+)", "Macro (500K-1M)", "Mid (50K-500K)", "Micro (10K-50K)", "Nano (1K-10K)", "Nano (<1K)"]
        else:
            tier_order = ["Viral Creator", "Popular Creator", "Mid-Tier Creator", "Growing Creator", "Micro Influencer"]

        sorted_clusters = {tier: clusters[tier] for tier in tier_order if tier in clusters}

        return {
            "total_competitors": len(competitors),
            "tiers": sorted_clusters,
            "summary": {
                tier: {
                    "count": data["count"],
                    "avg_followers": round(data["avg_followers"]),
                    "avg_engagement": round(data["avg_engagement"]),
                    "top_account_types": sorted(
                        data["account_types"].items(),
                        key=lambda x: x[1],
                        reverse=True
                    )[:3]
                }
                for tier, data in sorted_clusters.items()
            }
        }


async def main():
    """Test the analyzer."""
    from langgraph.store.postgres import PostgresStore

    async with PostgresStore.from_conn_string('postgresql://postgres:password@localhost:5433/xgrowth') as store:
        user_id = "user_34wsv56iMdmN9jPXo6Pg6HeroFK"
        namespace = (user_id, "social_graph")

        # Get graph data
        items = list(store.search(namespace, limit=1))
        if not items:
            print("No graph data found")
            return

        graph_data = items[0].value
        competitors = graph_data.get('all_competitors_raw', [])

        print(f"\n🔍 Analyzing content from {len(competitors)} competitors...\n")

        analyzer = ContentInsightsAnalyzer()
        insights = await analyzer.analyze_competitor_content(
            competitors,
            user_handle="Rajath_DB"
        )

        if insights['success']:
            data = insights['insights']

            print("="*80)
            print("📊 CONTENT INSIGHTS")
            print("="*80)

            # Benchmarks
            bench = data['benchmarks']
            print(f"\n📈 ENGAGEMENT BENCHMARKS:")
            print(f"  Posts analyzed: {bench['total_posts_analyzed']}")
            print(f"  Average likes: {bench['average_likes']:.0f}")
            print(f"  Average views: {bench['average_views']:,.0f}")
            print(f"  Top 10% threshold: {bench['top_10_percent_likes']:.0f} likes")

            # Goals
            print(f"\n🎯 ENGAGEMENT GOALS:")
            for level, likes in bench['engagement_goal'].items():
                print(f"  {level.capitalize()}: {likes:.0f} likes per post")

            # Patterns
            print(f"\n🔍 PATTERNS DISCOVERED:")
            patterns = data['patterns']
            if 'topics' in patterns:
                print(f"\n  Topics: {', '.join(patterns['topics'][:5])}")
            if 'key_insights' in patterns:
                print(f"\n  Key Insights:")
                for insight in patterns['key_insights'][:3]:
                    print(f"    • {insight}")

            # Suggestions
            print(f"\n💡 CONTENT SUGGESTIONS:")
            for i, sug in enumerate(data['suggestions'], 1):
                print(f"\n  {i}. {sug.get('post_text', '')}")
                print(f"     Why: {sug.get('reasoning', '')}")
                print(f"     Type: {sug.get('engagement_type', '')}")

            print("\n" + "="*80)


if __name__ == "__main__":
    asyncio.run(main())
