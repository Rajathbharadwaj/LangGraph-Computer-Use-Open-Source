"""
Tier 1: LLM-Generated Reason Options for Structured Feedback

Generate contextual "why would you engage / why not" options for the UI.
These options are used to collect rich training data for the A-SFT model.

Two modes:
1. Static options (fast, predefined) - default for most users
2. Dynamic options (LLM-generated) - for high-value users or A/B testing
"""

import os
import json
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from anthropic import Anthropic

logger = logging.getLogger(__name__)


@dataclass
class ReasonOption:
    """A selectable reason option for the feedback UI."""
    id: str  # Unique identifier, e.g., "topic_match", "author_relationship"
    label: str  # User-facing display text
    category: str  # "positive" (for YES) or "negative" (for NO)
    features: Dict[str, float]  # Feature signals this reason maps to

    def to_dict(self) -> Dict:
        return asdict(self)


class ReasonGenerator:
    """
    Generate contextual "why" options for user feedback collection.

    The UI flow:
    1. User sees post
    2. User answers "Would you engage?" → YES or NO
    3. Based on answer, show relevant "Why?" options from this generator
    4. User selects 1+ reasons
    5. Selection maps to feature signals for training
    """

    # =========================================================================
    # Static Positive Reasons (why user would engage)
    # =========================================================================
    POSITIVE_REASONS = [
        ReasonOption(
            id="topic_match",
            label="Topic matches my niche",
            category="positive",
            features={"topic_relevance": 1.0}
        ),
        ReasonOption(
            id="author_relationship",
            label="Author I want to build relationship with",
            category="positive",
            features={"author_preference": 1.0, "relationship_building": 0.5}
        ),
        ReasonOption(
            id="controversial_nuance",
            label="Controversial take I can add nuance to",
            category="positive",
            features={"controversy_opportunity": 1.0, "thought_leadership": 0.5}
        ),
        ReasonOption(
            id="high_visibility",
            label="High engagement = good visibility opportunity",
            category="positive",
            features={"engagement_level": 1.0, "visibility_potential": 0.5}
        ),
        ReasonOption(
            id="question_expertise",
            label="Question I can answer with expertise",
            category="positive",
            features={"is_question": 1.0, "topic_relevance": 0.5, "expertise_showcase": 0.5}
        ),
        ReasonOption(
            id="early_viral",
            label="Early viral post (good timing)",
            category="positive",
            features={"virality_potential": 1.0, "recency": 0.5}
        ),
        ReasonOption(
            id="thread_opportunity",
            label="Thread I can contribute to meaningfully",
            category="positive",
            features={"is_thread": 1.0, "contribution_opportunity": 0.5}
        ),
    ]

    # =========================================================================
    # Static Negative Reasons (why user would NOT engage)
    # =========================================================================
    NEGATIVE_REASONS = [
        ReasonOption(
            id="off_topic",
            label="Topic outside my expertise/niche",
            category="negative",
            features={"topic_relevance": -1.0}
        ),
        ReasonOption(
            id="too_controversial",
            label="Too controversial / risky",
            category="negative",
            features={"controversy_risk": -1.0, "brand_safety": -0.5}
        ),
        ReasonOption(
            id="too_crowded",
            label="Already too many replies (won't be seen)",
            category="negative",
            features={"reply_count": -1.0, "visibility_potential": -0.5}
        ),
        ReasonOption(
            id="dislike_author",
            label="Don't like this author's content",
            category="negative",
            features={"author_preference": -1.0}
        ),
        ReasonOption(
            id="low_quality",
            label="Low quality / spam vibes",
            category="negative",
            features={"quality_score": -1.0}
        ),
        ReasonOption(
            id="bad_timing",
            label="Wrong timing (too old/too new)",
            category="negative",
            features={"recency": -1.0}
        ),
        ReasonOption(
            id="no_value_add",
            label="Nothing meaningful I could add",
            category="negative",
            features={"contribution_opportunity": -1.0}
        ),
    ]

    def __init__(self, use_dynamic: bool = False):
        """
        Initialize the reason generator.

        Args:
            use_dynamic: If True, use LLM to generate contextual options.
                        Default is False (static options) for speed/cost.
        """
        self.use_dynamic = use_dynamic
        self.client = None
        if use_dynamic:
            self.client = Anthropic()

    def get_static_options(self, decision: str) -> List[ReasonOption]:
        """
        Return predefined options based on yes/no decision.

        Args:
            decision: "yes" or "no"

        Returns:
            List of ReasonOption for the UI
        """
        if decision.lower() == "yes":
            return self.POSITIVE_REASONS.copy()
        return self.NEGATIVE_REASONS.copy()

    def get_options_for_api(self, decision: str) -> List[Dict]:
        """
        Get options formatted for API response.

        Returns list of dicts with id, label, category.
        """
        options = self.get_static_options(decision)
        return [
            {"id": o.id, "label": o.label, "category": o.category}
            for o in options
        ]

    def get_features_for_reasons(
        self,
        reason_ids: List[str],
        decision: str
    ) -> Dict[str, float]:
        """
        Map selected reason IDs to aggregated feature signals.

        Args:
            reason_ids: List of selected reason IDs from UI
            decision: "yes" or "no" to get the right reason set

        Returns:
            Aggregated feature dict, e.g., {"topic_relevance": 1.5, "author_preference": 1.0}
        """
        options = self.get_static_options(decision)
        reason_map = {r.id: r for r in options}

        features = {}
        for reason_id in reason_ids:
            if reason_id in reason_map:
                for feature, weight in reason_map[reason_id].features.items():
                    features[feature] = features.get(feature, 0.0) + weight

        return features

    async def generate_contextual_options(
        self,
        post: Dict,
        user_context: Dict,
        decision: str
    ) -> List[ReasonOption]:
        """
        Generate LLM-personalized reason options for this specific post.

        This is more expensive but produces better training data.
        Use for high-value users or A/B testing.

        Args:
            post: Post dict with author, content, likes, etc.
            user_context: User context with niche, style, preferred_topics, etc.
            decision: "yes" or "no"

        Returns:
            List of contextual ReasonOption
        """
        if not self.client:
            logger.warning("Dynamic options requested but no client initialized")
            return self.get_static_options(decision)

        # Build prompt for contextual reasons
        polarity = "engage with" if decision == "yes" else "NOT engage with"
        reason_type = "positive" if decision == "yes" else "negative"

        prompt = f"""Given this X/Twitter post and user context, generate 5-7 specific reasons
why the user would {polarity} this post.

POST:
Author: @{post.get('author', 'unknown')} ({post.get('author_followers', 'unknown')} followers)
Content: {post.get('content', '')[:500]}
Engagement: {post.get('likes', 0)} likes, {post.get('retweets', 0)} RTs, {post.get('replies', 0)} replies
Posted: {post.get('hours_ago', '?')} hours ago

USER CONTEXT:
Niche: {user_context.get('niche', 'unknown')}
Engagement style: {user_context.get('style', 'unknown')}
Topics they like: {user_context.get('preferred_topics', [])}
Authors they engage with: {user_context.get('preferred_authors', [])}

Generate {reason_type} reasons as JSON array:
[{{"id": "unique_snake_case_id", "label": "User-facing reason text (max 50 chars)", "features": {{"feature_name": weight_float}}}}]

Focus on SPECIFIC reasons related to THIS post, not generic ones.
Keep labels concise and actionable.
Return ONLY the JSON array, no other text."""

        try:
            response = self.client.messages.create(
                model="claude-3-5-haiku-20241022",  # Fast + cheap
                max_tokens=600,
                messages=[{"role": "user", "content": prompt}]
            )

            # Parse response
            content = response.content[0].text.strip()
            # Handle potential markdown code blocks
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]

            reasons_data = json.loads(content)

            return [
                ReasonOption(
                    id=r["id"],
                    label=r["label"][:60],  # Truncate for safety
                    category=reason_type,
                    features=r.get("features", {})
                )
                for r in reasons_data
            ]

        except Exception as e:
            logger.warning(f"Failed to generate contextual options: {e}, falling back to static")
            return self.get_static_options(decision)

    def get_all_feature_names(self) -> List[str]:
        """Return all unique feature names used across all reasons."""
        features = set()
        for reason in self.POSITIVE_REASONS + self.NEGATIVE_REASONS:
            features.update(reason.features.keys())
        return sorted(features)
