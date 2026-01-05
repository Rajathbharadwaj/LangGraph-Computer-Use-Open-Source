"""
Tier 3: Generative Recommender (LLM-based Ranking)

Instead of traditional scoring (embeddings + similarity), this uses an LLM to:
1. Understand user preferences from their structured feedback history
2. Rank candidates by asking "which posts would this user engage with?"
3. Generate explanations for why each post is recommended

This is the core of the "Generative Recommenders" approach inspired by Netflix's A-SFT paper.
The LLM acts as both the feature extractor and the ranking model.
"""

import os
import json
import logging
from typing import List, Dict, Tuple, Optional
from datetime import datetime, timedelta

from anthropic import Anthropic
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

from database.models import PostRecommendation, PreferenceSignal, RecommendationModel

logger = logging.getLogger(__name__)


class GenerativeRecommender:
    """
    LLM-based recommender that learns from structured feedback.

    Key differences from traditional recommenders:
    - No embedding similarity scoring
    - LLM directly ranks based on learned preferences
    - Can explain WHY each recommendation was made

    The "generative" aspect: the LLM generates both the ranking AND the reasoning,
    allowing for interpretable recommendations that can be validated by users.
    """

    def __init__(self, user_id: str, db: Session):
        """
        Initialize the recommender.

        Args:
            user_id: User to generate recommendations for
            db: SQLAlchemy session
        """
        self.user_id = user_id
        self.db = db
        self.client = Anthropic()

    async def get_recommendations(
        self,
        candidate_posts: List[Dict],
        limit: int = 10
    ) -> List[Tuple[Dict, float, str]]:
        """
        Rank candidate posts using LLM with user's feedback history.

        Args:
            candidate_posts: List of posts to rank. Each should have:
                - url: Post URL
                - author: Author username
                - content: Post text
                - likes, retweets, replies: Engagement counts
                - hours_ago: Age in hours
            limit: Maximum recommendations to return

        Returns:
            List of (post, score, reason) tuples sorted by score
        """
        if not candidate_posts:
            return []

        # 1. Load user's preference profile (from feedback history)
        feedback_summary = await self._get_feedback_summary()

        # 2. Load any stored model profile for additional context
        model_profile = self._get_model_profile()

        # 3. Format candidates for LLM
        candidates_text = self._format_candidates(candidate_posts)

        # 4. Ask LLM to rank
        prompt = self._build_ranking_prompt(
            feedback_summary=feedback_summary,
            model_profile=model_profile,
            candidates_text=candidates_text,
            limit=limit
        )

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}]
            )

            # 5. Parse response
            content = response.content[0].text.strip()

            # Handle potential markdown code blocks
            if "```" in content:
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()

            rankings = json.loads(content)

            # 6. Build results
            results = []
            for r in rankings[:limit]:
                idx = r.get("index", 0)
                if 0 <= idx < len(candidate_posts):
                    post = candidate_posts[idx]
                    score = float(r.get("score", 0.5))
                    reason = r.get("reason", "Recommended based on your preferences")
                    results.append((post, score, reason))

            logger.info(f"Generated {len(results)} recommendations for user {self.user_id}")
            return results

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM response: {e}")
            return self._fallback_ranking(candidate_posts, limit)
        except Exception as e:
            logger.error(f"Recommendation generation failed: {e}")
            return self._fallback_ranking(candidate_posts, limit)

    async def _get_feedback_summary(self) -> str:
        """
        Summarize user's feedback history into a preference profile.

        This is the "learned" part of the generative recommender.
        We aggregate patterns from their structured feedback to create
        a natural language description of their preferences.
        """
        # Get recent feedback with reasons
        feedbacks = self.db.query(PostRecommendation).filter(
            PostRecommendation.user_id == self.user_id,
            PostRecommendation.action.in_(["selected", "skipped"]),
            PostRecommendation.feedback_reasons.isnot(None)
        ).order_by(desc(PostRecommendation.action_at)).limit(50).all()

        if not feedbacks:
            return "New user - no preference history yet. Use general best practices for X engagement."

        # Aggregate patterns
        positive_reasons = {}
        negative_reasons = {}
        engaged_authors = set()
        avoided_authors = set()
        successful_engagements = []

        for fb in feedbacks:
            reasons = fb.feedback_reasons or []
            if fb.action == "selected":
                for r in reasons:
                    positive_reasons[r] = positive_reasons.get(r, 0) + 1
                if fb.post_author:
                    engaged_authors.add(fb.post_author)
                # Track successful engagements
                if fb.engagement_success:
                    successful_engagements.append({
                        "author": fb.post_author,
                        "reason": reasons[0] if reasons else "unknown",
                        "likes": fb.outcome_likes or 0
                    })
            else:  # skipped
                for r in reasons:
                    negative_reasons[r] = negative_reasons.get(r, 0) + 1
                if fb.post_author:
                    avoided_authors.add(fb.post_author)

        # Calculate engagement rate
        total = len(feedbacks)
        engaged = sum(1 for f in feedbacks if f.action == "selected")
        rate = engaged / total if total > 0 else 0

        # Build summary
        summary = f"""
ENGAGEMENT PATTERNS (from {total} recent decisions, {rate:.0%} engagement rate):

Why they engage (positive signals):
{self._format_reasons(positive_reasons)}

Why they skip (negative signals):
{self._format_reasons(negative_reasons)}

Authors they like: {', '.join(list(engaged_authors)[:10]) or 'None tracked yet'}
Authors they skip: {', '.join(list(avoided_authors)[:10]) or 'None tracked yet'}

Top successful engagements (got likes/replies):
{self._format_successes(successful_engagements[:5])}
"""
        return summary.strip()

    def _get_model_profile(self) -> Optional[str]:
        """Get any stored LLM profile for this user."""
        model = self.db.query(RecommendationModel).filter(
            RecommendationModel.user_id == self.user_id,
            RecommendationModel.model_type == "llm_profile",
            RecommendationModel.is_active == True
        ).first()

        if model and model.llm_profile:
            return model.llm_profile
        return None

    def _format_reasons(self, reasons: Dict[str, int]) -> str:
        """Format reason counts as bullet points."""
        if not reasons:
            return "- No patterns detected yet"

        sorted_reasons = sorted(reasons.items(), key=lambda x: x[1], reverse=True)
        lines = []
        for reason_id, count in sorted_reasons[:7]:
            # Convert reason_id to readable label
            label = reason_id.replace("_", " ").title()
            lines.append(f"- {label}: {count}x")
        return "\n".join(lines)

    def _format_successes(self, engagements: List[Dict]) -> str:
        """Format successful engagements."""
        if not engagements:
            return "- No tracked successes yet"

        lines = []
        for e in engagements:
            lines.append(f"- @{e['author']}: {e['likes']} likes (reason: {e['reason']})")
        return "\n".join(lines)

    def _format_candidates(self, posts: List[Dict]) -> str:
        """Format candidate posts for LLM prompt."""
        lines = []
        for i, p in enumerate(posts):
            # Truncate content but keep enough for context
            content = p.get("content", "")[:250]
            if len(p.get("content", "")) > 250:
                content += "..."

            lines.append(f"""
[{i}] @{p.get('author', 'unknown')} ({p.get('author_followers', '?')} followers)
Content: {content}
Engagement: {p.get('likes', 0)} likes, {p.get('retweets', 0)} RTs, {p.get('replies', 0)} replies
Age: {p.get('hours_ago', '?')} hours old
""")
        return "\n".join(lines)

    def _build_ranking_prompt(
        self,
        feedback_summary: str,
        model_profile: Optional[str],
        candidates_text: str,
        limit: int
    ) -> str:
        """Build the prompt for LLM ranking."""
        profile_section = ""
        if model_profile:
            profile_section = f"""
ADDITIONAL USER PROFILE:
{model_profile}
"""

        return f"""You are a recommendation system for X/Twitter engagement. Your task is to rank posts by likelihood the user would engage with them.

USER PREFERENCE PROFILE (learned from their feedback):
{feedback_summary}
{profile_section}
CANDIDATE POSTS TO RANK:
{candidates_text}

Based on the user's preferences above, rank these posts by likelihood they would engage.

For each recommended post, provide:
1. index: The post index (0-based from the list above)
2. score: Engagement probability from 0.0 to 1.0
3. reason: Brief explanation (10-15 words) of why THIS user would engage, based on their specific patterns

Rules:
- Only include posts with score > 0.3
- Maximum {limit} posts
- Be specific about WHY - reference the user's patterns
- Consider: topic match, author relationship, timing, engagement opportunity

Return ONLY a JSON array sorted by score descending:
[{{"index": 0, "score": 0.95, "reason": "Matches their AI interest + author they've engaged with before"}}]"""

    def _fallback_ranking(
        self,
        candidates: List[Dict],
        limit: int
    ) -> List[Tuple[Dict, float, str]]:
        """
        Fallback ranking when LLM fails.
        Uses simple heuristics based on engagement and recency.
        """
        logger.info("Using fallback ranking heuristics")

        scored = []
        for post in candidates:
            # Simple engagement-based score
            likes = post.get("likes", 0)
            replies = post.get("replies", 0)
            hours_ago = post.get("hours_ago", 24)

            # Higher engagement = better, but penalize old posts
            engagement_score = min(1.0, (likes + replies * 2) / 100)
            recency_score = max(0, 1 - (hours_ago / 48))  # Decay over 48 hours

            score = engagement_score * 0.6 + recency_score * 0.4

            scored.append((post, score, "Recommended based on engagement and recency"))

        # Sort by score and return top N
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:limit]

    async def update_model_profile(self):
        """
        Update the stored LLM profile based on accumulated feedback.

        Called periodically (e.g., daily) to consolidate learnings.
        """
        summary = await self._get_feedback_summary()

        # Ask LLM to create a compact profile
        prompt = f"""Based on this user's feedback history, create a concise preference profile
that can guide future recommendations.

USER FEEDBACK HISTORY:
{summary}

Create a 3-5 sentence profile summarizing:
1. What topics/content types they engage with
2. What they avoid
3. Their engagement style (e.g., thought leadership, relationship building, visibility hunting)

Be specific and actionable. This profile will be used to rank future posts."""

        try:
            response = self.client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}]
            )

            profile = response.content[0].text.strip()

            # Store/update profile
            model = self.db.query(RecommendationModel).filter(
                RecommendationModel.user_id == self.user_id,
                RecommendationModel.model_type == "llm_profile"
            ).first()

            if model:
                model.llm_profile = profile
                model.model_version += 1
                model.last_trained_at = datetime.utcnow()
            else:
                model = RecommendationModel(
                    user_id=self.user_id,
                    model_type="llm_profile",
                    llm_profile=profile,
                    model_version=1,
                    is_active=True,
                    last_trained_at=datetime.utcnow()
                )
                self.db.add(model)

            self.db.commit()
            logger.info(f"Updated LLM profile for user {self.user_id}")

            return profile

        except Exception as e:
            logger.error(f"Failed to update model profile: {e}")
            return None

    def get_preference_signals(self) -> Dict[str, List[Dict]]:
        """
        Get user's preference signals grouped by type.
        Useful for debugging and UI display.
        """
        signals = self.db.query(PreferenceSignal).filter(
            PreferenceSignal.user_id == self.user_id
        ).all()

        grouped = {}
        for s in signals:
            if s.signal_type not in grouped:
                grouped[s.signal_type] = []
            grouped[s.signal_type].append({
                "value": s.signal_value,
                "score": s.preference_score,
                "confidence": s.confidence,
                "positive": s.positive_count,
                "negative": s.negative_count,
                "success_rate": s.engagement_success_rate
            })

        # Sort each group by preference score
        for key in grouped:
            grouped[key].sort(key=lambda x: x["score"], reverse=True)

        return grouped
