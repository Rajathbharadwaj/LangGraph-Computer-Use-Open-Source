"""
Learning Engine API Routes

Endpoints for post recommendations and preference learning:
- GET /api/recommendations/batch - Get recommended posts with reasons
- GET /api/recommendations/reasons - Get "why" options for feedback UI
- POST /api/recommendations/feedback - Record structured feedback (decision + reasons)
- POST /api/recommendations/engage - Record engagement (after user actually engages)
- POST /api/recommendations/outcome - Record engagement outcome (likes/replies on our comment)
- GET /api/recommendations/preferences - Get learned preference summary
- GET /api/recommendations/stats - Get training statistics
"""

import uuid
import logging
from typing import List, Optional, Dict
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database.database import SessionLocal
from database.models import PostRecommendation, PreferenceSignal, RecommendationModel, XAccount
from clerk_auth import get_current_user

from ml.reason_generator import ReasonGenerator
from ml.structured_feedback import StructuredFeedbackCollector
from ml.generative_recommender import GenerativeRecommender
from ml.asft_trainer import ASFTTrainer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/recommendations", tags=["Learning Engine"])


# =============================================================================
# Pydantic Models for Request/Response
# =============================================================================


class CandidatePost(BaseModel):
    """A post to potentially recommend."""
    url: str
    author: str
    content: str
    likes: int = 0
    retweets: int = 0
    replies: int = 0
    hours_ago: float = 0
    author_followers: Optional[int] = None


class RecommendationRequest(BaseModel):
    """Request for recommendations."""
    candidates: List[CandidatePost] = Field(..., min_items=1, max_items=100)
    limit: int = Field(default=10, ge=1, le=20)
    x_account_id: Optional[int] = None


class RecommendationResponse(BaseModel):
    """A single recommendation."""
    id: int  # PostRecommendation.id for tracking
    post: CandidatePost
    score: float
    reason: str
    position: int


class FeedbackRequest(BaseModel):
    """User's structured feedback on a recommendation."""
    recommendation_id: int
    decision: str = Field(..., pattern="^(yes|no)$")
    selected_reasons: List[str] = []
    other_reason: Optional[str] = None
    time_to_decide_ms: int = 0


class EngagementRequest(BaseModel):
    """Record that user engaged with a post."""
    recommendation_id: int
    engagement_type: str = Field(..., pattern="^(liked|commented|quoted|retweeted)$")
    comment_url: Optional[str] = None
    engagement_content: Optional[str] = None


class OutcomeRequest(BaseModel):
    """Record engagement outcome (how well did our engagement do)."""
    recommendation_id: int
    outcome_likes: int = 0
    outcome_replies: int = 0
    outcome_retweets: int = 0


# =============================================================================
# Dependency for DB Session
# =============================================================================


def get_db():
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =============================================================================
# API Endpoints
# =============================================================================


@router.get("/batch")
async def get_recommendations_batch(
    limit: int = 10,
    x_account_id: Optional[int] = None,
    clerk_user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get a batch of recommended posts (placeholder - actual candidates come from scraper).

    In production:
    1. Frontend calls scraper to get timeline/competitor posts
    2. Frontend sends candidates to POST /batch endpoint
    3. This endpoint returns scored/ranked recommendations

    For now, returns empty with instructions.
    """
    if not clerk_user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    return {
        "success": True,
        "message": "Use POST /api/recommendations/batch with candidates to get recommendations",
        "batch_id": None,
        "recommendations": []
    }


@router.post("/batch")
async def create_recommendations_batch(
    request: RecommendationRequest,
    clerk_user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Score and rank candidate posts for the user.

    Flow:
    1. Receive candidate posts from frontend (from timeline scraper)
    2. Use GenerativeRecommender to rank by predicted engagement
    3. Store recommendations for tracking
    4. Return top N with scores and reasons

    Request body:
    {
        "candidates": [{"url": "...", "author": "...", "content": "...", ...}],
        "limit": 10,
        "x_account_id": 123  // optional, for multi-account
    }
    """
    if not clerk_user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        # Convert Pydantic models to dicts
        candidates = [c.model_dump() for c in request.candidates]

        # Get recommendations using generative recommender
        recommender = GenerativeRecommender(clerk_user_id, db)
        recommendations = await recommender.get_recommendations(
            candidate_posts=candidates,
            limit=request.limit
        )

        # Create batch and store recommendations for tracking
        batch_id = str(uuid.uuid4())
        results = []

        for i, (post, score, reason) in enumerate(recommendations):
            # Create recommendation record
            rec = PostRecommendation(
                user_id=clerk_user_id,
                x_account_id=request.x_account_id,
                batch_id=batch_id,
                position_in_batch=i,
                post_url=post.get("url", ""),
                post_author=post.get("author"),
                post_content_preview=post.get("content", "")[:500],
                post_likes=post.get("likes", 0),
                post_retweets=post.get("retweets", 0),
                post_replies=post.get("replies", 0),
                post_hours_ago=post.get("hours_ago"),
                recommendation_score=score,
                recommendation_reason=reason,
                feature_vector=post.get("features", {}),
                action="pending"
            )
            db.add(rec)
            db.flush()  # Get the ID

            results.append(RecommendationResponse(
                id=rec.id,
                post=CandidatePost(**post),
                score=score,
                reason=reason,
                position=i
            ))

        db.commit()

        logger.info(f"Created batch {batch_id} with {len(results)} recommendations for user {clerk_user_id}")

        return {
            "success": True,
            "batch_id": batch_id,
            "recommendations": [r.model_dump() for r in results]
        }

    except Exception as e:
        logger.error(f"Failed to create recommendations: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reasons")
async def get_reason_options(
    decision: str,
    clerk_user_id: str = Depends(get_current_user)
):
    """
    Get the "why" options for the feedback UI.

    Args:
        decision: "yes" or "no" - determines which reasons to show

    Returns:
        List of reason options with id, label, category
    """
    if not clerk_user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    if decision not in ("yes", "no"):
        raise HTTPException(status_code=400, detail="decision must be 'yes' or 'no'")

    generator = ReasonGenerator()
    options = generator.get_options_for_api(decision)

    return {
        "success": True,
        "decision": decision,
        "options": options
    }


@router.post("/feedback")
async def record_feedback(
    request: FeedbackRequest,
    clerk_user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Record user's structured feedback (decision + reasons).

    This is the core training data collection endpoint.

    Request body:
    {
        "recommendation_id": 123,
        "decision": "yes" | "no",
        "selected_reasons": ["topic_match", "author_relationship"],
        "other_reason": "optional free text",
        "time_to_decide_ms": 3500
    }
    """
    if not clerk_user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        collector = StructuredFeedbackCollector(db)
        feedback = await collector.record_feedback(
            user_id=clerk_user_id,
            recommendation_id=request.recommendation_id,
            decision=request.decision,
            selected_reason_ids=request.selected_reasons,
            other_reason=request.other_reason,
            time_to_decide_ms=request.time_to_decide_ms
        )

        if not feedback:
            raise HTTPException(status_code=404, detail="Recommendation not found")

        return {
            "success": True,
            "feedback": {
                "recommendation_id": feedback.recommendation_id,
                "decision": feedback.decision,
                "feature_signals": feedback.feature_signals
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to record feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/engage")
async def record_engagement(
    request: EngagementRequest,
    clerk_user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Record that user actually engaged with a post.

    Called after the agent or user performs the engagement action.

    Request body:
    {
        "recommendation_id": 123,
        "engagement_type": "commented",
        "comment_url": "https://x.com/...",
        "engagement_content": "Great point about..."
    }
    """
    if not clerk_user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        collector = StructuredFeedbackCollector(db)
        success = await collector.record_engagement_outcome(
            recommendation_id=request.recommendation_id,
            engagement_type=request.engagement_type,
            comment_url=request.comment_url,
            engagement_content=request.engagement_content
        )

        if not success:
            raise HTTPException(status_code=404, detail="Recommendation not found")

        return {"success": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to record engagement: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/outcome")
async def record_outcome(
    request: OutcomeRequest,
    clerk_user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Record engagement outcome (how well our engagement performed).

    Called by outcome scraper job that checks likes/replies on our comments.

    Request body:
    {
        "recommendation_id": 123,
        "outcome_likes": 5,
        "outcome_replies": 2,
        "outcome_retweets": 1
    }
    """
    if not clerk_user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        collector = StructuredFeedbackCollector(db)
        success = await collector.record_engagement_outcome(
            recommendation_id=request.recommendation_id,
            engagement_type=None,  # Don't overwrite existing
            outcome_likes=request.outcome_likes,
            outcome_replies=request.outcome_replies,
            outcome_retweets=request.outcome_retweets
        )

        if not success:
            raise HTTPException(status_code=404, detail="Recommendation not found")

        return {"success": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to record outcome: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/preferences")
async def get_preferences(
    clerk_user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get user's learned preference summary.

    Returns aggregated signals and model profile.
    """
    if not clerk_user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        recommender = GenerativeRecommender(clerk_user_id, db)

        # Get preference signals grouped by type
        signals = recommender.get_preference_signals()

        # Get LLM profile if exists
        model = db.query(RecommendationModel).filter(
            RecommendationModel.user_id == clerk_user_id,
            RecommendationModel.model_type == "llm_profile",
            RecommendationModel.is_active == True
        ).first()

        return {
            "success": True,
            "signals": signals,
            "profile": {
                "text": model.llm_profile if model else None,
                "version": model.model_version if model else None,
                "training_samples": model.training_samples if model else 0,
                "last_trained": model.last_trained_at.isoformat() if model and model.last_trained_at else None
            }
        }

    except Exception as e:
        logger.error(f"Failed to get preferences: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_stats(
    clerk_user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get training statistics for debugging/monitoring.

    Returns feedback counts, engagement rates, advantage stats.
    """
    if not clerk_user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        trainer = ASFTTrainer(db)
        stats = await trainer.get_training_stats(clerk_user_id)

        # Add feedback stats
        collector = StructuredFeedbackCollector(db)
        feedback_stats = collector.get_user_feedback_stats(clerk_user_id)

        return {
            "success": True,
            "training": stats,
            "feedback": feedback_stats
        }

    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/train")
async def trigger_training(
    clerk_user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Manually trigger model training for the user.

    Normally runs daily, but can be triggered manually.
    """
    if not clerk_user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        trainer = ASFTTrainer(db)
        profile = await trainer.train_user_model(clerk_user_id)

        if not profile:
            return {
                "success": False,
                "message": "Insufficient training data (need at least 10 feedback samples)"
            }

        return {
            "success": True,
            "profile": profile
        }

    except Exception as e:
        logger.error(f"Failed to train model: {e}")
        raise HTTPException(status_code=500, detail=str(e))
