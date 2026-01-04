"""
Booking Service for Voice Agent POC

Provides a booking form for prospects to confirm meeting details
during/after sales calls. The voice agent sends the form link via SMS.
"""

from .routes import router as booking_router

__all__ = ["booking_router"]
