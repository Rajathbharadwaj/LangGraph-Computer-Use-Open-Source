"""
Learning Engine - Post Recommendation & Preference Learning

Provides:
- API routes for recommendations
- Integration with ML components (reason_generator, structured_feedback, etc.)
"""

from .routes import router as learning_engine_router

__all__ = ["learning_engine_router"]
