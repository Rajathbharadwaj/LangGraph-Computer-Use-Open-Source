"""
UGC Ad Factory - AI-powered video ad generation pipeline

Generates 20-30 short-form video ads from a single product/business input.
Uses ComfyUI + ZImage for images, KeyAI Sora 2 Pro for video, FFmpeg for assembly.
"""

from .state import (
    UGCPipelineState,
    AssetRequest,
    AssetStatus,
    GeneratedVideo,
    ProductProfile,
    CreativeAngle,
    ScriptPackage,
    Shot,
    ShotList,
    UploadPackage,
)
from .graph import create_ugc_pipeline

__version__ = "0.1.0"
__all__ = [
    "create_ugc_pipeline",
    "UGCPipelineState",
    "AssetRequest",
    "AssetStatus",
    "GeneratedVideo",
    "ProductProfile",
    "CreativeAngle",
    "ScriptPackage",
    "Shot",
    "ShotList",
    "UploadPackage",
]
