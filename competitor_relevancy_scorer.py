"""
Competitor Relevancy Scorer

Analyzes semantic similarity between user and competitors to determine niche alignment.
Combines with overlap percentage for a comprehensive "quality score".
"""

import anthropic
import os
from typing import Dict, List, Any, Optional
from async_playwright_tools import AsyncPlaywrightClient
from pydantic import BaseModel, Field
from langchain_anthropic import ChatAnthropic


class RelevancyScore(BaseModel):
    """Pydantic model for structured relevancy score output"""
    relevancy_score: float = Field(description="Relevancy score from 0-100")
    user_niche: str = Field(description="Primary niche/topic of the user")
    competitor_niche: str = Field(description="Primary niche/topic of the competitor")
    reasoning: str = Field(description="2-3 sentence explanation of the score")


class CompetitorRelevancyScorer:
    """Scores competitors based on content/niche similarity to the user"""

    def __init__(self, playwright_client: AsyncPlaywrightClient, store=None):
        self.client = playwright_client
        self.anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.store = store  # PostgresStore for state tracking

    def get_analysis_state(self, user_id: str) -> Dict[str, Any]:
        """Load analysis state from database to track which competitors have been analyzed"""
        if not self.store:
            return {"analyzed_usernames": [], "total_analyzed": 0, "last_batch_size": 0}

        try:
            state_namespace = (user_id, "relevancy_analysis_state")
            state = self.store.get(state_namespace, "state")
            if state and state.value:
                return state.value
        except:
            pass

        return {"analyzed_usernames": [], "total_analyzed": 0, "last_batch_size": 0}

    def save_analysis_state(self, user_id: str, analyzed_usernames: List[str], batch_size: int):
        """Save analysis state to database"""
        if not self.store:
            return

        import datetime
        state_namespace = (user_id, "relevancy_analysis_state")
        state = {
            "analyzed_usernames": analyzed_usernames,
            "total_analyzed": len(analyzed_usernames),
            "last_batch_size": batch_size,
            "last_analyzed_at": datetime.datetime.now().isoformat()
        }
        self.store.put(state_namespace, "state", state)
        print(f"💾 Saved analysis state: {len(analyzed_usernames)} competitors analyzed")

    async def get_user_profile(self, username: str, user_id: str = None) -> Dict[str, Any]:
        """Get user's bio and recent posts to determine their niche"""
        print(f"📊 Analyzing @{username}'s profile and content...")

        posts = []
        bio = ""

        # Try to get imported posts from LangGraph store first
        if user_id and self.store:
            try:
                posts_namespace = (user_id, "writing_samples")
                stored_posts = self.store.search(posts_namespace)
                if stored_posts:
                    # Extract post texts from stored data
                    post_texts = [p.value.get("content", "") for p in stored_posts if p.value.get("content")]
                    if post_texts:
                        posts = post_texts[:10]  # Use first 10 posts
                        print(f"✅ Using {len(posts)} imported posts from LangGraph store for @{username}")
            except Exception as e:
                print(f"⚠️ Could not load imported posts from LangGraph store: {e}")

        # Fallback: Try to get posts from PostgreSQL database (UserPost table)
        if not posts:
            try:
                from database.database import SessionLocal
                from database.models import UserPost, XAccount

                db = SessionLocal()
                try:
                    # Find the X account by username
                    x_account = db.query(XAccount).filter(XAccount.username == username).first()
                    if x_account:
                        # Get posts from database
                        db_posts = db.query(UserPost).filter(
                            UserPost.x_account_id == x_account.id
                        ).order_by(UserPost.scraped_at.desc()).limit(10).all()

                        if db_posts:
                            posts = [p.content for p in db_posts if p.content]
                            print(f"✅ Using {len(posts)} imported posts from PostgreSQL database for @{username}")
                finally:
                    db.close()
            except Exception as e:
                print(f"⚠️ Could not load imported posts from PostgreSQL: {e}")

        # If we don't have posts from either source, we can't analyze this user
        if not posts:
            print(f"⚠️ No imported posts found for @{username}. Import posts first to enable relevancy analysis.")

        return {
            "username": username,
            "bio": bio,
            "posts": posts
        }

    async def get_competitor_profiles(self, competitors: List[Dict[str, Any]], skip_usernames: List[str] = None) -> Dict[str, Dict[str, Any]]:
        """Get bios and posts for competitors (use existing post data if available)"""
        profiles = {}
        skip_usernames = skip_usernames or []

        for comp in competitors:
            username = comp.get("username")
            if not username:
                continue

            # Skip already-analyzed competitors
            if username in skip_usernames:
                print(f"⏭️  Skipping @{username} (already analyzed)")
                continue

            print(f"📄 Getting profile for @{username}...")

            # Use existing posts if available
            existing_posts = comp.get("posts", [])
            post_texts = [p.get("text", "") for p in existing_posts if p.get("text")]

            profiles[username] = {
                "username": username,
                "bio": "",  # Bio not needed, posts are sufficient for analysis
                "posts": post_texts[:10]  # Use first 10 posts
            }

        return profiles

    def calculate_relevancy_scores(
        self,
        user_profile: Dict[str, Any],
        competitor_profiles: Dict[str, Dict[str, Any]]
    ) -> Dict[str, float]:
        """
        Use Claude to calculate semantic similarity between user and each competitor.
        Returns relevancy scores (0-100) for each competitor.
        """
        print(f"\n🧠 Calculating relevancy scores using AI...")

        # Prepare user content summary
        user_bio = user_profile.get("bio", "")
        user_posts = user_profile.get("posts", [])
        user_content = f"Bio: {user_bio}\n\nRecent posts:\n" + "\n".join([f"- {p}" for p in user_posts[:5]])

        scores = {}

        for username, comp_profile in competitor_profiles.items():
            comp_bio = comp_profile.get("bio", "")
            comp_posts = comp_profile.get("posts", [])
            comp_content = f"Bio: {comp_bio}\n\nRecent posts:\n" + "\n".join([f"- {p}" for p in comp_posts[:5]])

            # Skip if both have no content
            if not user_content.strip() or not comp_content.strip():
                scores[username] = 50.0  # Neutral score
                continue

            try:
                # Use Claude with structured output to analyze semantic similarity
                prompt = f"""Analyze the semantic similarity between these two X/Twitter accounts to determine if they're in the same niche.

USER ACCOUNT (@{user_profile['username']}):
{user_content}

COMPETITOR ACCOUNT (@{username}):
{comp_content}

Analyze:
1. Main topics/themes for each account
2. Content style and target audience
3. Niche alignment (are they in the same industry/field?)
4. How relevant is the competitor to the user's audience?

Provide a RELEVANCY SCORE (0-100):
- 90-100: Perfect niche match, nearly identical focus
- 70-89: Strong alignment, same niche with different angles
- 50-69: Moderate relevance, overlapping topics but different primary focus
- 30-49: Weak relevance, some tangential connections
- 0-29: Not relevant, completely different niches"""

                # Use LangChain with structured output (guaranteed valid response)
                llm = ChatAnthropic(
                    model="claude-sonnet-4-5-20250929",
                    max_tokens=800,
                    api_key=os.getenv("ANTHROPIC_API_KEY")
                )
                structured_llm = llm.with_structured_output(RelevancyScore)
                result = structured_llm.invoke(prompt)

                # Extract score from structured response
                relevancy_score = float(result.relevancy_score)
                print(f"  @{username}: {relevancy_score:.1f}/100 - {result.reasoning[:80]}...")
                scores[username] = relevancy_score

            except Exception as e:
                print(f"⚠️ Error scoring @{username}: {e}")
                scores[username] = 50.0  # Neutral fallback

        return scores

    def combine_scores(
        self,
        competitors: List[Dict[str, Any]],
        relevancy_scores: Dict[str, float],
        overlap_weight: float = 0.4,
        relevancy_weight: float = 0.6
    ) -> List[Dict[str, Any]]:
        """
        Combine overlap percentage with relevancy score to create a quality score.

        Args:
            competitors: List of competitor dicts with overlap_percentage
            relevancy_scores: Dict mapping username -> relevancy score (0-100)
            overlap_weight: Weight for overlap percentage (default 0.4)
            relevancy_weight: Weight for relevancy score (default 0.6)

        Returns:
            Updated competitors list with relevancy_score and quality_score
        """
        print(f"\n🎯 Combining overlap and relevancy scores...")

        for comp in competitors:
            username = comp.get("username")
            overlap_pct = comp.get("overlap_percentage", 0)
            relevancy = relevancy_scores.get(username, 50.0)

            # Calculate weighted quality score
            quality_score = (overlap_pct * overlap_weight) + (relevancy * relevancy_weight)

            # Add to competitor data
            comp["relevancy_score"] = round(relevancy, 1)
            comp["quality_score"] = round(quality_score, 1)

            print(f"  @{username}: Quality={quality_score:.1f} (Overlap={overlap_pct}%, Relevancy={relevancy:.1f})")

        # Sort by quality score (descending)
        competitors.sort(key=lambda x: x.get("quality_score", 0), reverse=True)

        return competitors

    async def score_competitors(
        self,
        user_handle: str,
        competitors: List[Dict[str, Any]],
        user_id: str = None,
        batch_size: int = 20,
        overlap_weight: float = 0.4,
        relevancy_weight: float = 0.6
    ) -> Dict[str, Any]:
        """
        Main method to score competitors with smart batching.

        Args:
            user_handle: User's X handle
            competitors: List of competitors from discovery
            user_id: User ID for state tracking (optional)
            batch_size: Number of competitors to analyze in this batch (default 20)
            overlap_weight: Weight for overlap score (default 0.4)
            relevancy_weight: Weight for relevancy score (default 0.6)

        Returns:
            Dict with:
                - competitors: All competitors with scores
                - analyzed_count: Total number analyzed
                - total_count: Total competitors available
                - has_more: Whether more competitors can be analyzed
        """
        print(f"\n{'='*80}")
        print(f"🎯 COMPETITOR RELEVANCY ANALYSIS (Batch Size: {batch_size})")
        print(f"{'='*80}\n")

        # Load existing state
        analyzed_usernames = []
        if user_id and self.store:
            state = self.get_analysis_state(user_id)
            analyzed_usernames = state.get("analyzed_usernames", [])
            print(f"📊 Previously analyzed: {len(analyzed_usernames)} competitors")

        # Filter out already-analyzed competitors and get next batch
        unanalyzed = [c for c in competitors if c.get("username") not in analyzed_usernames]
        batch_to_analyze = unanalyzed[:batch_size]

        print(f"📋 Total competitors: {len(competitors)}")
        print(f"✅ Already analyzed: {len(analyzed_usernames)}")
        print(f"⏳ Remaining: {len(unanalyzed)}")
        print(f"🔄 Analyzing this batch: {len(batch_to_analyze)}\n")

        # Get user profile (only once, reuse if needed)
        # Pass user_id so we can reuse imported posts from database
        user_profile = await self.get_user_profile(user_handle, user_id=user_id)

        # Get competitor profiles (skip already-analyzed)
        competitor_profiles = await self.get_competitor_profiles(batch_to_analyze, analyzed_usernames)

        # Calculate relevancy scores using AI
        new_relevancy_scores = {}
        if competitor_profiles:
            new_relevancy_scores = self.calculate_relevancy_scores(user_profile, competitor_profiles)

        # Apply scores to newly analyzed competitors
        newly_analyzed = []
        for comp in batch_to_analyze:
            username = comp.get("username")
            if username in new_relevancy_scores:
                overlap_pct = comp.get("overlap_percentage", 0)
                relevancy = new_relevancy_scores[username]
                quality_score = (overlap_pct * overlap_weight) + (relevancy * relevancy_weight)

                comp["relevancy_score"] = round(relevancy, 1)
                comp["quality_score"] = round(quality_score, 1)
                newly_analyzed.append(username)

        # Update state with newly analyzed competitors
        all_analyzed = analyzed_usernames + newly_analyzed
        if user_id and self.store and newly_analyzed:
            self.save_analysis_state(user_id, all_analyzed, len(newly_analyzed))

        # Sort all competitors by quality score
        competitors.sort(key=lambda x: x.get("quality_score", 0), reverse=True)

        print(f"\n✅ Batch analysis complete!")
        print(f"📊 Progress: {len(all_analyzed)}/{len(competitors)} competitors analyzed")
        print(f"\nTop 5 by quality score:")
        for i, comp in enumerate(competitors[:5], 1):
            quality = comp.get("quality_score", 0)
            relevancy = comp.get("relevancy_score", 0)
            overlap = comp.get("overlap_percentage", 0)
            username = comp.get("username", "unknown")
            if quality > 0:
                print(f"  {i}. @{username}: Quality={quality:.1f} (Overlap={overlap}%, Relevancy={relevancy:.1f})")
            else:
                print(f"  {i}. @{username}: Overlap={overlap}% (not yet analyzed)")

        return {
            "competitors": competitors,
            "analyzed_count": len(all_analyzed),
            "total_count": len(competitors),
            "has_more": len(all_analyzed) < len(competitors),
            "batch_analyzed": len(newly_analyzed)
        }


# Convenience function for use in backend
async def add_relevancy_scores(
    playwright_client: AsyncPlaywrightClient,
    user_handle: str,
    graph_data: Dict[str, Any],
    user_id: str = None,
    store = None,
    batch_size: int = 20,
    overlap_weight: float = 0.4,
    relevancy_weight: float = 0.6
) -> Dict[str, Any]:
    """
    Add relevancy scores to existing graph data with smart batching.

    Args:
        playwright_client: Playwright client for browser automation
        user_handle: User's X handle
        graph_data: Existing graph data from discovery
        user_id: User ID for state tracking
        store: PostgresStore for state persistence
        batch_size: Number of competitors to analyze in this batch
        overlap_weight: Weight for overlap percentage
        relevancy_weight: Weight for relevancy score

    Returns:
        Updated graph_data with relevancy scores and progress info
    """
    scorer = CompetitorRelevancyScorer(playwright_client, store=store)

    # Get competitors from graph data
    competitors = graph_data.get("all_competitors_raw", []) or graph_data.get("top_competitors", [])

    if not competitors:
        print("⚠️ No competitors found in graph data")
        return graph_data

    # Score competitors with batching
    result = await scorer.score_competitors(
        user_handle,
        competitors,
        user_id=user_id,
        batch_size=batch_size,
        overlap_weight=overlap_weight,
        relevancy_weight=relevancy_weight
    )

    # Update graph data
    graph_data["all_competitors_raw"] = result["competitors"]
    graph_data["top_competitors"] = result["competitors"][:20]  # Top 20 by quality

    # Update high quality count (quality score >= 60)
    high_quality = [c for c in result["competitors"] if c.get("quality_score", 0) >= 60]
    graph_data["high_quality_competitors"] = len(high_quality)

    # Add progress tracking info
    graph_data["relevancy_analysis"] = {
        "analyzed_count": result["analyzed_count"],
        "total_count": result["total_count"],
        "has_more": result["has_more"],
        "batch_analyzed": result["batch_analyzed"]
    }

    return graph_data
