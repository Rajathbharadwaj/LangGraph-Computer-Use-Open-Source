"""
Learning Engine API Routes

Endpoints for post recommendations and preference learning:
- GET /api/recommendations/timeline - Get real posts from Following feed for training
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


@router.get("/timeline")
async def get_timeline_posts(
    max_posts: int = 30,
    min_engagement: int = 10,
    max_hours_ago: int = 48,
    clerk_user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get real posts from the user's Following timeline for preference training.

    This endpoint scrapes the authenticated user's "Following" tab (not "For You")
    to get high signal-to-noise posts from accounts they explicitly follow.

    Args:
        max_posts: Maximum posts to return (default 30)
        min_engagement: Minimum likes+retweets+replies to include (default 10)
        max_hours_ago: Maximum age of posts in hours (default 48)

    Returns:
        List of posts with full metadata ready for Learning Engine
    """
    import os
    import redis

    if not clerk_user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        # Get user's VNC client
        from async_playwright_tools import get_client_for_url
        import json

        redis_host = os.environ.get('REDIS_HOST', '10.110.183.147')
        redis_port = int(os.environ.get('REDIS_PORT', '6379'))

        vnc_url = None
        try:
            r = redis.Redis(host=redis_host, port=redis_port, db=0, decode_responses=True)
            # VNC sessions are stored as JSON in vnc:session:{user_id} (singular, not "sessions")
            session_json = r.get(f"vnc:session:{clerk_user_id}")
            if session_json:
                session_data = json.loads(session_json)
                vnc_url = session_data.get("https_url") or session_data.get("service_url")
                logger.info(f"Found VNC session for user {clerk_user_id}: {vnc_url}")
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}")
            vnc_url = None

        if not vnc_url:
            raise HTTPException(
                status_code=400,
                detail="No active browser session. Please start a VNC session from the Dashboard first."
            )

        # Create client and scrape timeline
        from timeline_feed_scraper import TimelineFeedScraper, get_following_timeline_posts

        client = get_client_for_url(vnc_url)
        posts = await get_following_timeline_posts(
            browser_client=client,
            max_posts=max_posts,
            min_engagement=min_engagement,
            max_hours_ago=max_hours_ago
        )

        logger.info(f"Scraped {len(posts)} posts from Following timeline for user {clerk_user_id}")

        return {
            "success": True,
            "posts": posts,
            "count": len(posts),
            "source": "following_timeline"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to scrape timeline: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to scrape timeline: {str(e)}")


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
    Get static "why" options for the feedback UI.

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


class ContextualReasonsRequest(BaseModel):
    """Request for contextual LLM-generated reasons."""
    post: CandidatePost
    decision: str = Field(..., pattern="^(yes|no)$")


@router.post("/reasons/contextual")
async def get_contextual_reasons(
    request: ContextualReasonsRequest,
    clerk_user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get LLM-generated contextual reasons for a specific post + decision.

    Returns both:
    - Contextual reasons (LLM-generated based on the post)
    - General reasons (static fallback options)

    Each reason has isContextual=true/false to differentiate in UI.
    """
    if not clerk_user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        # Get user context for personalized reason generation
        user_context = {}
        try:
            # Try to get user's preferences from existing signals
            signals = db.query(PreferenceSignal).filter(
                PreferenceSignal.user_id == clerk_user_id
            ).order_by(PreferenceSignal.preference_score.desc()).limit(10).all()

            if signals:
                # Build context from signals
                preferred_topics = [s.signal_value for s in signals if s.signal_type == "topic_preference" and s.preference_score > 0.5]
                preferred_authors = [s.signal_value for s in signals if s.signal_type == "author_preference" and s.preference_score > 0.5]
                user_context = {
                    "preferred_topics": preferred_topics[:5],
                    "preferred_authors": preferred_authors[:5],
                    "niche": "technology & AI" if not preferred_topics else preferred_topics[0],
                    "style": "thoughtful engagement"
                }
        except Exception as e:
            logger.warning(f"Could not fetch user context: {e}")

        # Generate contextual reasons via LLM
        generator = ReasonGenerator(use_dynamic=True)

        post_dict = {
            "author": request.post.author,
            "content": request.post.content,
            "likes": request.post.likes,
            "retweets": request.post.retweets,
            "replies": request.post.replies,
            "hours_ago": request.post.hours_ago,
            "author_followers": request.post.author_followers or 0
        }

        contextual_options = await generator.generate_contextual_options(
            post=post_dict,
            user_context=user_context,
            decision=request.decision
        )

        # Also get static options as fallback
        static_options = generator.get_static_options(request.decision)

        # Format response with isContextual flag
        reasons = []

        # Add contextual options first (LLM-generated)
        for opt in contextual_options[:5]:  # Limit to 5 contextual
            reasons.append({
                "id": f"ctx_{opt.id}",
                "label": opt.label,
                "isContextual": True
            })

        # Add static options as general fallback
        for opt in static_options[:4]:  # Limit to 4 general
            reasons.append({
                "id": opt.id,
                "label": opt.label,
                "isContextual": False
            })

        return {
            "success": True,
            "decision": request.decision,
            "reasons": reasons
        }

    except Exception as e:
        logger.error(f"Failed to generate contextual reasons: {e}")
        # Fall back to static reasons on error
        generator = ReasonGenerator()
        static_options = generator.get_options_for_api(request.decision)
        return {
            "success": True,
            "decision": request.decision,
            "reasons": [
                {"id": opt["id"], "label": opt["label"], "isContextual": False}
                for opt in static_options
            ]
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
