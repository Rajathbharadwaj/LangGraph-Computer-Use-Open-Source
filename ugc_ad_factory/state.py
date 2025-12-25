"""
Pydantic state models for UGC Ad Factory pipeline.

Uses Pydantic BaseModel for validation + easier API serialization.

NEW ARCHITECTURE (perspective-based):
- Input: Product images (official photos)
- Plan: Different perspectives/views to generate
- Generate: New perspectives via img2img
- Transition: Start→End frame pairs for smooth motion
- Animate: I2V between frames
- Assemble: Final video
"""

from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field
from datetime import datetime


class AssetStatus(str, Enum):
    """Status tracking for render requests"""

    PENDING = "pending"
    RENDERING = "rendering"
    SUCCESS = "success"
    FAILED = "failed"
    FALLBACK = "fallback"  # Used Ken Burns instead of video


class UGCMode(str, Enum):
    """Supported generation modes"""

    ECOM_PRODUCT = "ecom_product"
    LOCAL_BUSINESS = "local_business"
    PERSONAL_BRAND = "personal_brand"


# ============================================================================
# NEW: Perspective-Based Models
# ============================================================================


class SourceImage(BaseModel):
    """An input product image provided by user"""

    image_id: str
    url: str  # Original URL or GCS URL after upload
    local_path: str | None = None
    description: str = ""  # What's in this image (e.g., "front view", "product box")
    is_primary: bool = False  # Main hero image


class Perspective(BaseModel):
    """A planned perspective/view to generate from source image"""

    perspective_id: str
    source_image_id: str  # Which input image to derive from
    view_type: str  # e.g., "close_up", "angle_45", "top_down", "lifestyle", "detail"
    description: str  # Description for img2img prompt
    camera_angle: str = "front"  # front, side, top, 3/4, etc.
    zoom_level: str = "medium"  # close, medium, wide
    lighting_style: str = "studio"  # studio, natural, dramatic, soft
    background_hint: str = ""  # Optional background guidance
    sequence_order: int = 0  # Order in the final video sequence


class GeneratedPerspective(BaseModel):
    """A perspective image that was generated via img2img"""

    perspective_id: str
    source_image_id: str
    generated_url: str | None = None
    local_path: str | None = None
    status: AssetStatus = AssetStatus.PENDING
    error_message: str | None = None


class Transition(BaseModel):
    """A transition between two perspectives (start → end frame)"""

    transition_id: str
    start_perspective_id: str
    end_perspective_id: str
    motion_type: str = "smooth"  # smooth, zoom_in, zoom_out, pan, orbit
    motion_description: str = ""  # Description for I2V prompt
    duration_seconds: float = 2.0
    easing: str = "ease_in_out"  # linear, ease_in, ease_out, ease_in_out


class GeneratedTransition(BaseModel):
    """An animated transition clip between perspectives"""

    transition_id: str
    start_image_url: str
    end_image_url: str
    video_url: str | None = None
    local_path: str | None = None
    duration_seconds: float = 2.0
    status: AssetStatus = AssetStatus.PENDING
    error_message: str | None = None


# ============================================================================
# Sub-models for structured data
# ============================================================================


class ProductProfile(BaseModel):
    """Normalized product/business profile from intake"""

    name: str
    category: str
    description: str
    target_audience: str
    key_benefits: list[str] = []
    pain_points: list[str] = []
    unique_selling_points: list[str] = []
    tone: str = "professional"  # professional, playful, urgent, etc.
    price_point: str | None = None
    reference_images: list[str] = []  # URLs
    brand_colors: list[str] = []
    brand_guidelines: dict | None = None


class CreativeAngle(BaseModel):
    """A creative angle/hook strategy"""

    angle_id: str
    name: str
    hook_type: str  # problem_solution, testimonial, before_after, urgency, social_proof
    hook_text: str  # Opening line
    emotional_trigger: str
    target_segment: str
    estimated_effectiveness: float = 0.8  # 0-1


class ScriptPackage(BaseModel):
    """Complete script for one ad variation"""

    script_id: str
    angle_id: str
    voiceover_text: str | None = None
    text_overlays: list[dict] = []  # [{time: "0:00", text: "...", style: "..."}]
    cta_text: str
    duration_seconds: float = 15.0
    music_mood: str = "upbeat"  # upbeat, calm, dramatic, etc.


class Shot(BaseModel):
    """A single shot in the video"""

    shot_id: str
    shot_type: str  # hero_product, lifestyle, close_up, text_card, b_roll
    duration_seconds: float = 3.0
    description: str
    camera_movement: str = "static"  # static, pan_left, pan_right, zoom_in, ken_burns
    subject: str
    background: str = ""
    lighting: str = "studio"


class ShotList(BaseModel):
    """Complete shot list for one video"""

    shotlist_id: str
    script_id: str
    angle_id: str
    shots: list[Shot] = []
    total_duration: float = 0.0
    transition_style: str = "cut"  # cut, crossfade, wipe


class AssetRequest(BaseModel):
    """Individual render request with status tracking"""

    request_id: str
    shot_id: str
    shotlist_id: str
    asset_type: Literal["image", "video"]
    backend: Literal["comfyui", "keyai"]
    prompt: str
    negative_prompt: str = ""
    width: int = 1080
    height: int = 1920
    duration_seconds: float | None = None  # For video clips
    style_preset: str = "default"
    reference_image_url: str | None = None  # For image-to-video

    # Status tracking
    status: AssetStatus = AssetStatus.PENDING
    retry_count: int = 0
    error_message: str | None = None
    result_url: str | None = None
    local_path: str | None = None

    # Timestamps
    started_at: datetime | None = None
    completed_at: datetime | None = None


class GeneratedAsset(BaseModel):
    """A generated asset (image or video clip)"""

    asset_id: str
    request_id: str
    shot_id: str
    asset_type: Literal["image", "video"]
    storage_url: str
    local_path: str | None = None
    duration_seconds: float | None = None
    file_size_bytes: int | None = None


class GeneratedVideo(BaseModel):
    """Final assembled video with QC scoring"""

    video_id: str
    angle_id: str
    script_id: str
    shotlist_id: str
    storage_url: str
    thumbnail_url: str | None = None
    local_path: str | None = None
    duration_seconds: float = 0.0
    file_size_bytes: int | None = None
    resolution: str = "1080x1920"

    # QC scoring
    qc_score: float = 0.0  # 0-1
    missing_shots: int = 0
    fallback_shots: int = 0  # Ken Burns fallbacks
    qc_passed: bool = False
    qc_issues: list[str] = []

    # Render metadata
    render_time_seconds: float | None = None
    assets_used: list[str] = []


class UploadPackage(BaseModel):
    """Platform-specific upload metadata"""

    video_id: str
    platform: str  # youtube_shorts, tiktok, reels
    title: str
    description: str
    hashtags: list[str] = []
    thumbnail_url: str | None = None
    scheduled_time: datetime | None = None
    is_uploaded: bool = False
    upload_url: str | None = None  # Platform URL after upload


# ============================================================================
# Main Pipeline State
# ============================================================================


class UGCPipelineState(BaseModel):
    """
    Main pipeline state - Pydantic for validation + API serialization.

    This state flows through all pipeline stages, accumulating data.

    NEW PERSPECTIVE-BASED FLOW:
    1. source_images - Input product images from user
    2. perspectives - Planned perspectives to generate
    3. generated_perspectives - Perspectives generated via img2img
    4. transitions - Planned transitions between perspectives
    5. generated_transitions - Animated clips between frames
    6. videos - Final assembled video(s)
    """

    # Identity
    user_id: str
    job_id: str
    mode: str  # Required - drives template loading (ecom_product, local_business, etc.)

    # Raw input (preserved for reference)
    raw_input: dict = Field(default_factory=dict)

    # =========================================================================
    # NEW: Perspective-based pipeline fields
    # =========================================================================
    source_images: list[SourceImage] = []  # Input product images from user
    perspectives: list[Perspective] = []  # Planned perspectives to generate
    generated_perspectives: list[GeneratedPerspective] = []  # Generated perspective images
    transitions: list[Transition] = []  # Planned transitions (start→end pairs)
    generated_transitions: list[GeneratedTransition] = []  # Animated transition clips

    # Product context (simplified from old ProductProfile)
    product_name: str = ""
    product_description: str = ""
    product_style: str = "clean"  # clean, vibrant, minimal, luxury, etc.

    # =========================================================================
    # LEGACY: Original pipeline fields (kept for backward compatibility)
    # =========================================================================
    product_profile: ProductProfile | None = None
    angles: list[CreativeAngle] = []
    script_packages: list[ScriptPackage] = []
    shot_lists: list[ShotList] = []
    asset_requests: list[AssetRequest] = []
    generated_assets: dict = Field(
        default_factory=lambda: {"images": [], "clips": []}
    )  # {"images": [GeneratedAsset], "clips": [GeneratedAsset]}
    videos: list[GeneratedVideo] = []
    upload_packages: list[UploadPackage] = []

    # Progress tracking
    current_stage: str | None = None
    target_count: int = 20  # Target number of videos
    completed_count: int = 0

    # Error handling
    error: str | None = None
    warnings: list[str] = []

    # Timestamps
    started_at: datetime | None = None
    estimated_completion: datetime | None = None
    completed_at: datetime | None = None

    class Config:
        # Allow mutation during pipeline execution
        validate_assignment = True
        # Allow arbitrary types for flexibility
        arbitrary_types_allowed = True

    def model_dump_json_safe(self) -> dict:
        """Serialize to JSON-safe dict (for API responses)"""
        return self.model_dump(mode="json")
