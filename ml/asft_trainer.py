"""
Tier 4: Advantage-Weighted Supervised Fine-Tuning (A-SFT)

Implements advantage-weighted training inspired by Netflix's post-training approach
for generative recommenders. Paper: "Post-Training Generative Recommenders with
Advantage-Weighted Supervised Finetuning" (Oct 2025)

Key insight from Netflix:
Even with noisy reward signals, the DIRECTION (better vs worse than expected)
provides useful learning signal. We weight training samples by their "advantage":
- High positive advantage → model underpredicted, upweight this pattern
- High negative advantage → model overpredicted, learn from mistake
- Zero advantage → matched expectation, normal weight

In our context:
- We don't fine-tune the LLM itself
- Instead, we use advantage-weighted samples to update the LLM profile
- High-advantage samples contribute more to the profile summary
"""

import math
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from collections import Counter

import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

from database.models import PostRecommendation, PreferenceSignal, RecommendationModel
from anthropic import Anthropic

logger = logging.getLogger(__name__)


class ASFTTrainer:
    """
    Implements advantage-weighted training for the preference model.

    Instead of traditional fine-tuning, we:
    1. Compute advantage for each feedback sample
    2. Weight samples by advantage magnitude
    3. Generate an updated LLM profile from weighted samples
    4. Use the profile in future recommendations

    This is "training" in the sense that we're updating the model's
    understanding, but via prompt engineering rather than gradient descent.
    """

    def __init__(self, db: Session):
        """
        Initialize the trainer.

        Args:
            db: SQLAlchemy session
        """
        self.db = db
        self.client = Anthropic()

    async def compute_advantages(
        self,
        user_id: str,
        lookback_days: int = 7
    ) -> List[Dict]:
        """
        Compute advantage for each feedback sample.

        Advantage = actual_outcome - model_prediction

        Where:
        - actual_outcome = normalized engagement success (0-1)
        - model_prediction = recommendation_score from when post was shown

        Args:
            user_id: User to compute for
            lookback_days: How far back to look

        Returns:
            List of training samples with computed advantages
        """
        cutoff = datetime.utcnow() - timedelta(days=lookback_days)

        # Get feedback with outcomes
        feedbacks = self.db.query(PostRecommendation).filter(
            and_(
                PostRecommendation.user_id == user_id,
                PostRecommendation.action_at > cutoff,
                PostRecommendation.action.in_(["selected", "skipped"])
            )
        ).order_by(desc(PostRecommendation.action_at)).all()

        training_samples = []

        for fb in feedbacks:
            # Compute actual outcome (0-1)
            actual = self._compute_actual_outcome(fb)

            # Model's prediction at recommendation time
            predicted = fb.recommendation_score or 0.5

            # Advantage = how much better/worse than expected
            advantage = actual - predicted

            # Convert advantage to training weight (bounded)
            weight = self._advantage_to_weight(advantage)

            sample = {
                "feedback_id": fb.id,
                "post_url": fb.post_url,
                "post_author": fb.post_author,
                "post_content": fb.post_content_preview,
                "decision": fb.action,
                "reasons": fb.feedback_reasons or [],
                "features": fb.feedback_features or {},
                "actual_outcome": actual,
                "predicted_outcome": predicted,
                "advantage": advantage,
                "weight": weight,
                "outcome_likes": fb.outcome_likes or 0,
                "outcome_replies": fb.outcome_replies or 0,
                "action_at": fb.action_at.isoformat() if fb.action_at else None
            }

            training_samples.append(sample)

        logger.info(
            f"Computed advantages for {len(training_samples)} samples, "
            f"user={user_id}, avg_advantage={np.mean([s['advantage'] for s in training_samples]):.3f}"
        )

        return training_samples

    def _compute_actual_outcome(self, fb: PostRecommendation) -> float:
        """
        Compute actual outcome from engagement results.

        Outcome signals:
        - Did user actually engage? (selected vs skipped)
        - If engaged, did it get likes/replies?

        Returns:
            Float 0-1 representing actual outcome quality
        """
        if fb.action == "skipped":
            return 0.0

        if fb.action == "selected":
            base = 0.5  # They chose to engage

            # Bonus for successful engagement (if outcome tracked)
            if fb.outcome_likes is not None and fb.outcome_likes > 0:
                base += min(fb.outcome_likes * 0.05, 0.3)
            if fb.outcome_replies is not None and fb.outcome_replies > 0:
                base += min(fb.outcome_replies * 0.1, 0.2)

            return min(base, 1.0)

        return 0.5  # Unknown / pending

    def _advantage_to_weight(self, advantage: float) -> float:
        """
        Convert advantage to training weight.

        Netflix finding: Don't just use raw advantage.
        Use a bounded transformation to prevent extreme weights.

        Transformation: 1 + tanh(advantage * 2)
        - High positive advantage → weight ~2.0 (learn more from surprises)
        - Zero advantage → weight ~1.0 (normal)
        - High negative advantage → weight ~0.5 (still learn from mistakes!)

        Args:
            advantage: Raw advantage value (-1 to 1 typically)

        Returns:
            Training weight (0.5 to 2.0)
        """
        return 1.0 + math.tanh(advantage * 2)

    async def generate_training_batch(
        self,
        user_id: str,
        batch_size: int = 32
    ) -> Optional[Dict]:
        """
        Generate advantage-weighted training batch.

        Samples are selected with probability proportional to their weight,
        so high-advantage samples appear more frequently.

        Args:
            user_id: User to generate for
            batch_size: Number of samples in batch

        Returns:
            Training batch dict or None if insufficient data
        """
        samples = await self.compute_advantages(user_id)

        if len(samples) < 5:
            logger.info(f"Insufficient samples for user {user_id}: {len(samples)}")
            return None

        # Sample with probability proportional to weight
        weights = np.array([s["weight"] for s in samples])
        weights = weights / weights.sum()  # Normalize to probabilities

        # Sample indices (with replacement if needed)
        n_samples = min(batch_size, len(samples))
        indices = np.random.choice(
            len(samples),
            size=n_samples,
            p=weights,
            replace=(len(samples) < batch_size)
        )

        batch = [samples[i] for i in indices]

        return {
            "user_id": user_id,
            "samples": batch,
            "total_samples": len(samples),
            "avg_advantage": float(np.mean([s["advantage"] for s in samples])),
            "avg_weight": float(np.mean([s["weight"] for s in samples])),
            "generated_at": datetime.utcnow().isoformat()
        }

    async def train_user_model(
        self,
        user_id: str,
        min_samples: int = 10
    ) -> Optional[str]:
        """
        Train (update) the user's recommendation model.

        Steps:
        1. Get advantage-weighted training batch
        2. Generate updated LLM profile from weighted patterns
        3. Store new profile version

        This is "training" via prompt engineering - we summarize
        the weighted feedback patterns into a profile that guides
        future recommendations.

        Args:
            user_id: User to train for
            min_samples: Minimum samples required

        Returns:
            New profile text if successful, None otherwise
        """
        batch = await self.generate_training_batch(user_id, batch_size=50)

        if not batch or len(batch["samples"]) < min_samples:
            logger.info(f"Not enough samples to train for user {user_id}")
            return None

        # Aggregate weighted patterns
        patterns = self._aggregate_weighted_patterns(batch["samples"])

        # Generate profile using LLM
        profile = await self._generate_profile_from_patterns(user_id, patterns)

        if not profile:
            return None

        # Store updated model
        await self._store_model(
            user_id=user_id,
            profile=profile,
            training_samples=len(batch["samples"]),
            avg_advantage=batch["avg_advantage"]
        )

        return profile

    def _aggregate_weighted_patterns(self, samples: List[Dict]) -> Dict:
        """
        Aggregate patterns from weighted samples.

        Patterns weighted by sample weight, so high-advantage
        patterns contribute more.
        """
        # Weighted reason counts
        positive_reasons = Counter()
        negative_reasons = Counter()
        author_engagement = {}  # author -> (weighted_positive, weighted_negative)
        successful_patterns = []

        for s in samples:
            weight = s["weight"]
            is_positive = s["decision"] == "selected"

            # Count reasons (weighted)
            for reason in s["reasons"]:
                if is_positive:
                    positive_reasons[reason] += weight
                else:
                    negative_reasons[reason] += weight

            # Track author patterns
            author = s.get("post_author")
            if author:
                if author not in author_engagement:
                    author_engagement[author] = {"positive": 0, "negative": 0}
                if is_positive:
                    author_engagement[author]["positive"] += weight
                else:
                    author_engagement[author]["negative"] += weight

            # Track successful high-advantage patterns
            if s["advantage"] > 0.2 and s["outcome_likes"] > 0:
                successful_patterns.append({
                    "author": author,
                    "reasons": s["reasons"],
                    "advantage": s["advantage"],
                    "likes": s["outcome_likes"]
                })

        # Sort authors by net preference
        sorted_authors = sorted(
            author_engagement.items(),
            key=lambda x: x[1]["positive"] - x[1]["negative"],
            reverse=True
        )

        return {
            "positive_reasons": positive_reasons.most_common(10),
            "negative_reasons": negative_reasons.most_common(10),
            "preferred_authors": [a for a, _ in sorted_authors[:10] if sorted_authors],
            "avoided_authors": [a for a, _ in sorted_authors[-5:] if sorted_authors],
            "successful_patterns": successful_patterns[:5]
        }

    async def _generate_profile_from_patterns(
        self,
        user_id: str,
        patterns: Dict
    ) -> Optional[str]:
        """
        Generate LLM profile from aggregated patterns.
        """
        # Format patterns for prompt
        positive_str = "\n".join([
            f"- {r.replace('_', ' ').title()}: {w:.1f} weighted occurrences"
            for r, w in patterns["positive_reasons"]
        ]) or "No clear positive patterns yet"

        negative_str = "\n".join([
            f"- {r.replace('_', ' ').title()}: {w:.1f} weighted occurrences"
            for r, w in patterns["negative_reasons"]
        ]) or "No clear negative patterns yet"

        success_str = "\n".join([
            f"- @{p['author']}: {p['likes']} likes (reasons: {', '.join(p['reasons'][:2])})"
            for p in patterns["successful_patterns"]
        ]) or "No tracked successes yet"

        prompt = f"""Based on this weighted analysis of user feedback (higher weights = more surprising/informative outcomes), create a concise preference profile.

POSITIVE PATTERNS (why they engage - weighted by how much better than expected):
{positive_str}

NEGATIVE PATTERNS (why they skip - weighted by predictability):
{negative_str}

PREFERRED AUTHORS: {', '.join(patterns['preferred_authors'][:5]) or 'None identified'}

HIGH-ADVANTAGE SUCCESSES (engagements that exceeded expectations):
{success_str}

Create a 4-6 sentence profile that captures:
1. Primary engagement motivations (topic, relationship, visibility)
2. What they consistently avoid
3. Their engagement style
4. Any clear author preferences

Be specific and actionable. This profile guides future recommendations.
Focus especially on the high-advantage patterns - these are the insights the model was missing."""

        try:
            response = self.client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}]
            )

            return response.content[0].text.strip()

        except Exception as e:
            logger.error(f"Failed to generate profile: {e}")
            return None

    async def _store_model(
        self,
        user_id: str,
        profile: str,
        training_samples: int,
        avg_advantage: float
    ):
        """Store the updated model."""
        # Find existing model
        model = self.db.query(RecommendationModel).filter(
            RecommendationModel.user_id == user_id,
            RecommendationModel.model_type == "llm_profile"
        ).first()

        if model:
            model.llm_profile = profile
            model.model_version += 1
            model.training_samples = training_samples
            model.avg_advantage = avg_advantage
            model.last_trained_at = datetime.utcnow()
            model.is_active = True
        else:
            model = RecommendationModel(
                user_id=user_id,
                model_type="llm_profile",
                llm_profile=profile,
                model_version=1,
                training_samples=training_samples,
                avg_advantage=avg_advantage,
                is_active=True,
                last_trained_at=datetime.utcnow()
            )
            self.db.add(model)

        self.db.commit()

        logger.info(
            f"Stored model v{model.model_version} for user {user_id}: "
            f"{training_samples} samples, avg_advantage={avg_advantage:.3f}"
        )

    async def get_training_stats(self, user_id: str) -> Dict:
        """
        Get training statistics for a user.

        Useful for monitoring and debugging.
        """
        samples = await self.compute_advantages(user_id, lookback_days=30)

        if not samples:
            return {"status": "no_data"}

        advantages = [s["advantage"] for s in samples]
        weights = [s["weight"] for s in samples]

        # Count by decision
        selected = sum(1 for s in samples if s["decision"] == "selected")
        skipped = len(samples) - selected

        # Outcome success rate
        with_outcomes = [s for s in samples if s["outcome_likes"] is not None]
        successful = sum(1 for s in with_outcomes if s["outcome_likes"] > 0)

        # Get current model
        model = self.db.query(RecommendationModel).filter(
            RecommendationModel.user_id == user_id,
            RecommendationModel.model_type == "llm_profile",
            RecommendationModel.is_active == True
        ).first()

        return {
            "total_samples": len(samples),
            "selected_count": selected,
            "skipped_count": skipped,
            "engagement_rate": selected / len(samples) if samples else 0,
            "with_outcomes": len(with_outcomes),
            "successful_engagements": successful,
            "success_rate": successful / len(with_outcomes) if with_outcomes else None,
            "advantage_stats": {
                "mean": float(np.mean(advantages)),
                "std": float(np.std(advantages)),
                "min": float(np.min(advantages)),
                "max": float(np.max(advantages)),
            },
            "weight_stats": {
                "mean": float(np.mean(weights)),
                "std": float(np.std(weights)),
            },
            "model": {
                "version": model.model_version if model else None,
                "training_samples": model.training_samples if model else None,
                "last_trained": model.last_trained_at.isoformat() if model and model.last_trained_at else None,
            }
        }


async def daily_training_job(db: Session):
    """
    Daily job to retrain all active users' models.

    Should be run as a Cloud Run Job or cron task.
    """
    from database.models import User

    trainer = ASFTTrainer(db)

    # Get all users with recent activity
    cutoff = datetime.utcnow() - timedelta(days=7)
    active_users = db.query(User).filter(
        User.is_active == True
    ).all()

    trained = 0
    skipped = 0

    for user in active_users:
        try:
            # Check if user has enough recent feedback
            recent = db.query(PostRecommendation).filter(
                and_(
                    PostRecommendation.user_id == user.id,
                    PostRecommendation.action_at > cutoff
                )
            ).count()

            if recent < 10:
                skipped += 1
                continue

            # Train model
            profile = await trainer.train_user_model(user.id)
            if profile:
                trained += 1
                logger.info(f"Trained model for user {user.id}")
            else:
                skipped += 1

        except Exception as e:
            logger.error(f"Training failed for user {user.id}: {e}")
            continue

    logger.info(f"Daily training complete: {trained} trained, {skipped} skipped")

    return {"trained": trained, "skipped": skipped}
