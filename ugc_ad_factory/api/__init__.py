"""REST API endpoints for UGC ad factory"""

from .routes import router
from .models import (
    CreateJobRequest,
    JobResponse,
    VideosResponse,
    VideoDetail,
)

__all__ = [
    "router",
    "CreateJobRequest",
    "JobResponse",
    "VideosResponse",
    "VideoDetail",
]
