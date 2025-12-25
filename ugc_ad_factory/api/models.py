"""
Pydantic models for API request/response schemas.
"""

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


class CreateJobRequest(BaseModel):
    """Request to create a new UGC generation job (LEGACY - text-to-image mode)."""

    mode: str = Field(
        default="ecom_product",
        description="Generation mode: ecom_product, local_business, personal_brand",
    )
    product_name: str = Field(..., description="Name of the product or business")
    product_description: str = Field(..., description="Detailed description")
    product_images: list[str] = Field(
        default=[],
        description="URLs of product reference images",
    )
    target_audience: str | None = Field(
        default=None,
        description="Description of target audience",
    )
    key_benefits: list[str] | None = Field(
        default=None,
        description="Key product benefits",
    )
    brand_colors: list[str] | None = Field(
        default=None,
        description="Brand colors as hex codes",
    )
    variations_count: int = Field(
        default=20,
        ge=1,
        le=30,
        description="Number of video variations to generate (1-30)",
    )


# ============================================================================
# NEW: Perspective-Based Job Request
# ============================================================================


class CreatePerspectiveJobRequest(BaseModel):
    """
    Request to create a perspective-based UGC generation job.

    NEW APPROACH: Takes product images and generates different perspectives,
    then animates smooth transitions between them.
    """

    # Required: Product images (at least 1)
    product_images: list[str] = Field(
        ...,
        min_length=1,
        description="URLs of product images (official photos). First image is primary.",
    )

    # Product context
    product_name: str = Field(
        default="Product",
        description="Name of the product",
    )
    product_description: str = Field(
        default="",
        description="Brief description of the product",
    )
    product_style: str = Field(
        default="clean",
        description="Visual style: clean, vibrant, minimal, luxury, bold",
    )

    # Optional: Image descriptions for context
    image_descriptions: dict[str, str] = Field(
        default={},
        description="Optional descriptions for each image by index (e.g., {'0': 'front view'})",
    )

    # Generation settings
    num_perspectives: int = Field(
        default=5,
        ge=2,
        le=10,
        description="Number of perspectives to generate (2-10)",
    )
    mode: str = Field(
        default="perspective",
        description="Generation mode (perspective for new pipeline)",
    )


class JobResponse(BaseModel):
    """Response with job status and progress."""

    job_id: str
    user_id: str
    status: str = Field(description="pending, running, completed, failed")
    current_stage: str | None = None
    progress_percent: float = 0.0
    completed_variations: int = 0
    target_variations: int = 20
    error: str | None = None
    warnings: list[str] = []
    started_at: datetime | None = None
    estimated_completion: datetime | None = None
    completed_at: datetime | None = None


class VideoDetail(BaseModel):
    """Details of a generated video."""

    video_id: str
    angle_id: str
    angle_name: str | None = None
    storage_url: str
    thumbnail_url: str | None = None
    duration_seconds: float
    qc_score: float
    qc_passed: bool
    qc_issues: list[str] = []


class VideosResponse(BaseModel):
    """Response with all generated videos for a job."""

    job_id: str
    total_videos: int
    passed_videos: int
    failed_videos: int
    videos: list[VideoDetail]


class UploadPackageDetail(BaseModel):
    """Upload metadata for a specific platform."""

    video_id: str
    platform: str
    title: str
    description: str
    hashtags: list[str]
    thumbnail_url: str | None = None


class MetadataResponse(BaseModel):
    """Response with upload packages for videos."""

    job_id: str
    packages: list[UploadPackageDetail]


class HealthResponse(BaseModel):
    """Service health check response."""

    status: str
    version: str
    comfyui_available: bool
    keyai_available: bool
    gcs_available: bool
