"""
Competitor Content Analyzer

Scrapes recent posts from competitors and uses LLM to:
1. Extract main topics/themes
2. Classify content type (technical, marketing, personal, etc.)
3. Cluster competitors by content similarity

This enhances the social graph with actual content insights.
"""

import asyncio
from typing import List, Dict, Optional
from datetime import datetime
from langgraph.store.base import BaseStore
from langchain_anthropic import ChatAnthropic


# ============================================================================
# CONTENT SCRAPER
# ============================================================================

class CompetitorContentScraper:
    """
    Scrapes recent posts from competitor accounts.
    """

    def __init__(self, browser_client):
        self.client = browser_client

    async def scrape_recent_posts(
        self,
        username: str,
        max_posts: int = 10
    ) -> List[Dict]:
        """
        Scrape recent posts from a user's profile.

        Args:
            username: Twitter/X handle (without @)
            max_posts: Number of recent posts to scrape

        Returns:
            List of posts with text content
        """
        print(f"   📝 Scraping {max_posts} recent posts from @{username}...")

        # Navigate to user's profile
        url = f"https://x.com/{username}"
        result = await self.client._request("POST", "/navigate", {"url": url})

        if not result.get("success"):
            print(f"      ⚠️ Failed to navigate: {result.get('error')}")
            return []

        await asyncio.sleep(3)  # Wait for timeline to load

        posts = []
        scroll_count = 0
        max_scrolls = 5

        while len(posts) < max_posts and scroll_count < max_scrolls:
            # Get DOM
            dom_result = await self.client._request("GET", "/dom/elements")

            if not dom_result.get("success"):
                break

            # Extract post text from DOM
            new_posts = self._extract_posts_from_dom(dom_result)

            for post in new_posts:
                if post not in posts and len(posts) < max_posts:
                    posts.append(post)

            # Scroll to load more
            await self.client._request("POST", "/scroll", {
                "x": 500, "y": 800, "scroll_x": 0, "scroll_y": 3
            })

            scroll_count += 1
            await asyncio.sleep(2)

        print(f"      ✅ Scraped {len(posts)} posts")
        return posts[:max_posts]

    def _extract_posts_from_dom(self, dom_result: Dict) -> List[Dict]:
        """
        Extract post text from X DOM structure.

        X posts are in <article> tags with data-testid="tweet"
        """
        posts = []
        elements = dom_result.get("elements", [])

        for el in elements:
            # Look for tweet text
            text = el.get("text", "").strip()

            # Filter out navigation, headers, etc.
            if text and len(text) > 20 and not text.startswith("@"):
                # Basic heuristic: posts are longer than 20 chars
                # and don't start with @ (which are usually metadata)
                posts.append({
                    "text": text,
                    "scraped_at": datetime.utcnow().isoformat()
                })

        return posts


# ============================================================================
# CONTENT ANALYZER
# ============================================================================

class CompetitorContentAnalyzer:
    """
    Analyzes competitor post content using LLM to extract topics and themes.
    """

    def __init__(self, llm: Optional[ChatAnthropic] = None):
        self.llm = llm or ChatAnthropic(
            model="claude-3-5-haiku-20241022",
            temperature=0
        )

    async def analyze_competitor_content(
        self,
        username: str,
        posts: List[Dict]
    ) -> Dict:
        """
        Analyze a competitor's posts to extract topics and themes.

        Args:
            username: Competitor's handle
            posts: List of recent posts

        Returns:
            Analysis with topics, themes, content type
        """
        if not posts:
            return {
                "username": username,
                "topics": [],
                "primary_theme": "Unknown",
                "content_type": "Unknown",
                "analysis_failed": True
            }

        # Combine post text
        post_texts = "\n\n".join([p["text"] for p in posts[:10]])

        # Analyze with LLM
        prompt = f"""Analyze these recent posts from @{username} and extract:

1. Main topics (3-5 specific topics like "AI", "Web3", "SaaS", "Design", "Marketing", etc.)
2. Primary theme (one word: Technical, Business, Creative, Educational, Personal, etc.)
3. Content type (one word: Educational, Promotional, Commentary, Personal, Mixed)

Posts:
{post_texts}

Respond in JSON format:
{{
    "topics": ["topic1", "topic2", "topic3"],
    "primary_theme": "theme",
    "content_type": "type"
}}"""

        try:
            response = await self.llm.ainvoke(prompt)
            content = response.content

            # Parse JSON from response
            import json
            # Extract JSON from markdown code blocks if present
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            analysis = json.loads(content)

            return {
                "username": username,
                "topics": analysis.get("topics", []),
                "primary_theme": analysis.get("primary_theme", "Unknown"),
                "content_type": analysis.get("content_type", "Unknown"),
                "analyzed_at": datetime.utcnow().isoformat(),
                "post_count": len(posts)
            }

        except Exception as e:
            print(f"      ⚠️ Failed to analyze content: {e}")
            return {
                "username": username,
                "topics": [],
                "primary_theme": "Unknown",
                "content_type": "Unknown",
                "analysis_failed": True,
                "error": str(e)
            }


# ============================================================================
# CLUSTER BUILDER
# ============================================================================

class ContentClusterBuilder:
    """
    Clusters competitors by content similarity.
    """

    def build_clusters(self, competitors_with_topics: List[Dict]) -> Dict:
        """
        Cluster competitors by their topics.

        Args:
            competitors_with_topics: List of competitors with topic analysis

        Returns:
            Clusters grouped by topic
        """
        clusters = {}

        for comp in competitors_with_topics:
            topics = comp.get("topics", [])

            for topic in topics:
                topic_lower = topic.lower()

                if topic_lower not in clusters:
                    clusters[topic_lower] = []

                clusters[topic_lower].append({
                    "username": comp["username"],
                    "overlap_percentage": comp.get("overlap_percentage", 0),
                    "primary_theme": comp.get("primary_theme", "Unknown")
                })

        # Sort clusters by size
        sorted_clusters = dict(
            sorted(clusters.items(), key=lambda x: len(x[1]), reverse=True)
        )

        return sorted_clusters


# ============================================================================
# MAIN ORCHESTRATOR
# ============================================================================

async def analyze_all_competitors(
    user_id: str,
    store: BaseStore,
    browser_client
) -> Dict:
    """
    Scrape and analyze content for all discovered competitors.

    Args:
        user_id: User identifier
        store: LangGraph Store
        browser_client: Playwright browser client

    Returns:
        Updated graph data with content analysis
    """
    print(f"\n{'='*80}")
    print(f"📊 ANALYZING COMPETITOR CONTENT")
    print(f"{'='*80}\n")

    # Get existing graph data
    namespace = (user_id, "social_graph")
    items = list(store.search(namespace, limit=1))

    if not items:
        return {"error": "No graph data found"}

    graph_data = items[0].value
    competitors = graph_data.get("top_competitors", [])[:15]  # Analyze top 15

    # Initialize
    scraper = CompetitorContentScraper(browser_client)
    analyzer = CompetitorContentAnalyzer()

    analyzed_competitors = []

    for i, comp in enumerate(competitors, 1):
        print(f"[{i}/{len(competitors)}] Analyzing @{comp['username']}...")

        try:
            # Scrape posts
            posts = await scraper.scrape_recent_posts(comp["username"], max_posts=8)

            # Analyze content
            analysis = await analyzer.analyze_competitor_content(
                comp["username"],
                posts
            )

            # Merge with existing competitor data
            analyzed_competitor = {
                **comp,
                **analysis
            }

            analyzed_competitors.append(analyzed_competitor)

            # Update in store
            competitor_namespace = (user_id, "competitor_profiles")
            store.put(
                competitor_namespace,
                comp["username"],
                analyzed_competitor
            )

            # Rate limit friendly
            await asyncio.sleep(5)

        except Exception as e:
            print(f"      ⚠️ Failed: {e}")
            analyzed_competitors.append(comp)
            continue

    # Build clusters
    cluster_builder = ContentClusterBuilder()
    clusters = cluster_builder.build_clusters(analyzed_competitors)

    # Update graph data
    graph_data["top_competitors"] = analyzed_competitors
    graph_data["content_clusters"] = clusters
    graph_data["content_analyzed_at"] = datetime.utcnow().isoformat()

    store.put(namespace, "latest", graph_data)

    print(f"\n{'='*80}")
    print(f"✅ CONTENT ANALYSIS COMPLETE!")
    print(f"   - Analyzed {len(analyzed_competitors)} competitors")
    print(f"   - Found {len(clusters)} topic clusters")
    print(f"   - Top clusters: {', '.join(list(clusters.keys())[:5])}")
    print(f"{'='*80}\n")

    return {
        "success": True,
        "analyzed_count": len(analyzed_competitors),
        "clusters": clusters
    }
