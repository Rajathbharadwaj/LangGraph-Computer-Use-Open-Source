"""
Tier 2: Structured Feedback Collection

Collect and store structured feedback (decision + reasons) from the UI.
This is the core training data for the generative recommender.

Data flow:
1. UI sends: recommendation_id, decision (yes/no), selected_reason_ids
2. This module: maps reasons → features, stores in DB, returns for immediate use
3. Later: A-SFT trainer uses this data with advantage weighting
"""

import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import and_

from database.models import PostRecommendation, PreferenceSignal
from ml.reason_generator import ReasonGenerator

logger = logging.getLogger(__name__)


@dataclass
class StructuredFeedback:
    """
    Rich feedback signal for training the generative recommender.

    Contains:
    - User's explicit decision (yes/no)
    - Which reasons they selected (from predefined options)
    - Aggregated feature signals from those reasons
    - Behavioral metadata (how long they took to decide)
    """
    recommendation_id: int
    user_id: str
    post_url: str

    # User's decision
    decision: str  # "yes" or "no"

    # Selected reasons (from UI checkboxes)
    selected_reasons: List[str]  # List of reason IDs

    # Aggregated feature signals (computed from selected reasons)
    feature_signals: Dict[str, float]  # e.g., {"topic_relevance": 1.0, "author_preference": -0.5}

    # Optional free-text reason
    other_reason: Optional[str] = None

    # Behavioral metadata
    time_to_decide_ms: int = 0  # Engagement signal: quick = confident, slow = uncertain
    timestamp: Optional[datetime] = None

    # Outcome (filled later after engagement)
    engagement_outcome: Optional[Dict] = None  # likes, replies on our comment

    def to_dict(self) -> Dict[str, Any]:
        return {
            **asdict(self),
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


class StructuredFeedbackCollector:
    """
    Collects structured feedback and converts to training signals.

    Responsibilities:
    1. Record user feedback (decision + reasons)
    2. Map reasons to feature signals
    3. Update PreferenceSignal counts for online learning
    4. Convert feedback to training samples for A-SFT
    """

    def __init__(self, db: Session):
        """
        Initialize the collector.

        Args:
            db: SQLAlchemy session
        """
        self.db = db
        self.reason_gen = ReasonGenerator()

    async def record_feedback(
        self,
        user_id: str,
        recommendation_id: int,
        decision: str,
        selected_reason_ids: List[str],
        other_reason: Optional[str] = None,
        time_to_decide_ms: int = 0
    ) -> Optional[StructuredFeedback]:
        """
        Record user's structured feedback.

        Steps:
        1. Validate recommendation exists
        2. Map selected reasons to feature signals
        3. Update PostRecommendation record
        4. Update PreferenceSignal counts (online learning)
        5. Return feedback object for immediate model update

        Args:
            user_id: The user's ID
            recommendation_id: PostRecommendation.id
            decision: "yes" or "no"
            selected_reason_ids: List of reason IDs user selected
            other_reason: Optional free-text reason
            time_to_decide_ms: How long user took to decide

        Returns:
            StructuredFeedback if successful, None otherwise
        """
        # 1. Get the recommendation
        rec = self.db.query(PostRecommendation).filter(
            PostRecommendation.id == recommendation_id,
            PostRecommendation.user_id == user_id
        ).first()

        if not rec:
            logger.warning(f"Recommendation {recommendation_id} not found for user {user_id}")
            return None

        # 2. Map reasons to feature signals
        feature_signals = self.reason_gen.get_features_for_reasons(
            selected_reason_ids,
            decision
        )

        # 3. Create feedback object
        feedback = StructuredFeedback(
            recommendation_id=recommendation_id,
            user_id=user_id,
            post_url=rec.post_url,
            decision=decision,
            selected_reasons=selected_reason_ids,
            feature_signals=feature_signals,
            other_reason=other_reason,
            time_to_decide_ms=time_to_decide_ms,
            timestamp=datetime.utcnow()
        )

        # 4. Update PostRecommendation record
        rec.action = "selected" if decision == "yes" else "skipped"
        rec.action_at = feedback.timestamp
        rec.feedback_decision = decision
        rec.feedback_reasons = selected_reason_ids
        rec.feedback_features = feature_signals
        rec.other_reason = other_reason
        rec.time_to_decide_ms = time_to_decide_ms

        # 5. Update PreferenceSignals (online learning)
        await self._update_preference_signals(
            user_id=user_id,
            post=rec,
            decision=decision,
            selected_reasons=selected_reason_ids
        )

        self.db.commit()

        logger.info(
            f"Recorded feedback for rec {recommendation_id}: "
            f"decision={decision}, reasons={selected_reason_ids}"
        )

        return feedback

    async def _update_preference_signals(
        self,
        user_id: str,
        post: PostRecommendation,
        decision: str,
        selected_reasons: List[str]
    ):
        """
        Update PreferenceSignal counts for online learning.

        Updates signals for:
        - Topic preferences (from post content analysis)
        - Author preferences (from post author)
        - Reason preferences (which reasons user tends to select)
        """
        is_positive = decision == "yes"
        now = datetime.utcnow()

        # Update author preference signal
        if post.post_author:
            await self._increment_signal(
                user_id=user_id,
                signal_type="author_preference",
                signal_value=post.post_author,
                is_positive=is_positive,
                timestamp=now
            )

        # Update reason preference signals
        for reason_id in selected_reasons:
            await self._increment_signal(
                user_id=user_id,
                signal_type="reason_preference",
                signal_value=reason_id,
                is_positive=is_positive,  # Track which reasons correlate with engagement
                timestamp=now
            )

    async def _increment_signal(
        self,
        user_id: str,
        signal_type: str,
        signal_value: str,
        is_positive: bool,
        timestamp: datetime
    ):
        """
        Increment a preference signal (Bayesian counting for Thompson Sampling).
        """
        # Find or create signal
        signal = self.db.query(PreferenceSignal).filter(
            and_(
                PreferenceSignal.user_id == user_id,
                PreferenceSignal.signal_type == signal_type,
                PreferenceSignal.signal_value == signal_value
            )
        ).first()

        if not signal:
            signal = PreferenceSignal(
                user_id=user_id,
                signal_type=signal_type,
                signal_value=signal_value,
                positive_count=0,
                negative_count=0,
                total_shown=0
            )
            self.db.add(signal)

        # Update counts
        signal.total_shown += 1
        if is_positive:
            signal.positive_count += 1
            signal.last_positive_at = timestamp
        else:
            signal.negative_count += 1
            signal.last_negative_at = timestamp

        # Recompute derived scores
        total = signal.positive_count + signal.negative_count
        if total > 0:
            # Beta distribution mean: (alpha) / (alpha + beta)
            # Using +1 for Laplace smoothing
            signal.preference_score = (signal.positive_count + 1) / (total + 2)
            # Confidence increases with more samples
            signal.confidence = min(1.0, total / 20.0)  # Max confidence at 20 samples

        signal.updated_at = timestamp

    async def record_engagement_outcome(
        self,
        recommendation_id: int,
        engagement_type: str,
        comment_url: Optional[str] = None,
        engagement_content: Optional[str] = None,
        outcome_likes: int = 0,
        outcome_replies: int = 0,
        outcome_retweets: int = 0
    ) -> bool:
        """
        Record the outcome after user actually engages.

        Called by:
        1. Immediately after agent posts comment (engagement_type, comment_url)
        2. Later by scraper job (outcome_likes, outcome_replies)

        Args:
            recommendation_id: PostRecommendation.id
            engagement_type: "liked", "commented", "quoted", "retweeted"
            comment_url: URL to our comment if applicable
            engagement_content: Our comment text if applicable
            outcome_likes: Likes on our engagement
            outcome_replies: Replies to our engagement
            outcome_retweets: Retweets of our engagement

        Returns:
            True if successful
        """
        rec = self.db.query(PostRecommendation).get(recommendation_id)
        if not rec:
            logger.warning(f"Recommendation {recommendation_id} not found")
            return False

        # Update engagement fields
        if engagement_type:
            rec.engagement_type = engagement_type
        if comment_url:
            rec.comment_url = comment_url
        if engagement_content:
            rec.engagement_content = engagement_content

        # Update outcome metrics
        rec.outcome_likes = outcome_likes
        rec.outcome_replies = outcome_replies
        rec.outcome_retweets = outcome_retweets
        rec.outcome_scraped_at = datetime.utcnow()

        # Compute engagement success
        rec.engagement_success = (outcome_likes + outcome_replies + outcome_retweets) > 0

        # Compute advantage for A-SFT training
        actual_outcome = self._compute_outcome_score(rec)
        predicted = rec.recommendation_score or 0.5
        rec.advantage = actual_outcome - predicted

        # Compute training weight (bounded sigmoid)
        import math
        rec.training_weight = 1.0 + math.tanh(rec.advantage * 2)

        # Update preference signal success rates
        await self._update_signal_success_rates(rec)

        self.db.commit()

        logger.info(
            f"Recorded outcome for rec {recommendation_id}: "
            f"type={engagement_type}, likes={outcome_likes}, advantage={rec.advantage:.3f}"
        )

        return True

    def _compute_outcome_score(self, rec: PostRecommendation) -> float:
        """
        Compute actual outcome score (0-1) from engagement results.

        Used for advantage calculation in A-SFT.
        """
        if rec.action != "selected":
            return 0.0

        base = 0.5  # User chose to engage

        # Bonus for successful engagement
        if rec.outcome_likes and rec.outcome_likes > 0:
            base += min(rec.outcome_likes * 0.05, 0.3)
        if rec.outcome_replies and rec.outcome_replies > 0:
            base += min(rec.outcome_replies * 0.1, 0.2)

        return min(base, 1.0)

    async def _update_signal_success_rates(self, rec: PostRecommendation):
        """Update engagement success rates on preference signals."""
        if not rec.feedback_reasons:
            return

        # Update success rate for each reason selected
        for reason_id in rec.feedback_reasons:
            signal = self.db.query(PreferenceSignal).filter(
                and_(
                    PreferenceSignal.user_id == rec.user_id,
                    PreferenceSignal.signal_type == "reason_preference",
                    PreferenceSignal.signal_value == reason_id
                )
            ).first()

            if signal:
                # Running average of success rate
                old_rate = signal.engagement_success_rate or 0.5
                new_success = 1.0 if rec.engagement_success else 0.0
                # Exponential moving average
                signal.engagement_success_rate = old_rate * 0.9 + new_success * 0.1

    def feedback_to_training_sample(
        self,
        feedback: StructuredFeedback,
        post_features: Dict
    ) -> Dict:
        """
        Convert structured feedback to training sample for A-SFT.

        Output format matches what ASFTTrainer expects.

        Args:
            feedback: StructuredFeedback object
            post_features: Additional post features (embedding, metrics, etc.)

        Returns:
            Training sample dict
        """
        # Calculate reward from decision + reasons
        base_reward = 1.0 if feedback.decision == "yes" else 0.0

        # Bonus for high-value engagement patterns
        reason_bonus = 0.0
        if "author_relationship" in feedback.selected_reasons:
            reason_bonus += 0.2  # Strategic relationship building
        if "question_expertise" in feedback.selected_reasons:
            reason_bonus += 0.15  # Expertise showcase
        if "early_viral" in feedback.selected_reasons:
            reason_bonus += 0.1  # Good timing

        reward = base_reward + reason_bonus

        return {
            "recommendation_id": feedback.recommendation_id,
            "post_features": post_features,
            "decision": feedback.decision,
            "selected_reasons": feedback.selected_reasons,
            "feature_signals": feedback.feature_signals,
            "other_reason": feedback.other_reason,
            "time_to_decide_ms": feedback.time_to_decide_ms,
            "reward": reward,
            "timestamp": feedback.timestamp.isoformat() if feedback.timestamp else None
        }

    def get_user_feedback_stats(self, user_id: str) -> Dict:
        """
        Get statistics on a user's feedback history.

        Useful for debugging and monitoring.
        """
        from sqlalchemy import func

        # Count by decision
        counts = self.db.query(
            PostRecommendation.feedback_decision,
            func.count(PostRecommendation.id)
        ).filter(
            PostRecommendation.user_id == user_id,
            PostRecommendation.feedback_decision.isnot(None)
        ).group_by(PostRecommendation.feedback_decision).all()

        decision_counts = {d: c for d, c in counts}

        # Top reasons
        from collections import Counter
        feedbacks = self.db.query(PostRecommendation.feedback_reasons).filter(
            PostRecommendation.user_id == user_id,
            PostRecommendation.feedback_reasons.isnot(None)
        ).all()

        reason_counter = Counter()
        for (reasons,) in feedbacks:
            if reasons:
                reason_counter.update(reasons)

        return {
            "total_feedbacks": sum(decision_counts.values()),
            "yes_count": decision_counts.get("yes", 0),
            "no_count": decision_counts.get("no", 0),
            "engagement_rate": decision_counts.get("yes", 0) / max(1, sum(decision_counts.values())),
            "top_reasons": reason_counter.most_common(10),
        }
