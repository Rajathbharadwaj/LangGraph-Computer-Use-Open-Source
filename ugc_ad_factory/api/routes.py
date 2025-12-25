"""
FastAPI routes for UGC Ad Factory API.
"""

import asyncio
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from .models import (
    CreateJobRequest,
    CreatePerspectiveJobRequest,
    JobResponse,
    VideosResponse,
    VideoDetail,
    MetadataResponse,
    UploadPackageDetail,
    HealthResponse,
)
from ..state import UGCPipelineState
from ..graph import create_ugc_pipeline
from ..graph_perspective import create_perspective_pipeline
from ..render.comfyui_client import ComfyUIClient
from ..render.keyai_client import KeyAISora2Client
from .. import __version__


router = APIRouter(prefix="/api/ugc", tags=["UGC Ad Factory"])

# In-memory job storage (replace with database in production)
_jobs: dict[str, UGCPipelineState] = {}
_job_tasks: dict[str, asyncio.Task] = {}


@router.post("/jobs", response_model=JobResponse)
async def create_job(request: CreateJobRequest, user_id: str = "demo_user"):
    """
    Create a new UGC ad generation job (LEGACY text-to-image mode).

    Starts the generation pipeline asynchronously and returns job ID for tracking.
    """
    job_id = str(uuid.uuid4())

    # Initialize state
    state = UGCPipelineState(
        user_id=user_id,
        job_id=job_id,
        mode=request.mode,
        raw_input={
            "product_name": request.product_name,
            "product_description": request.product_description,
            "product_images": request.product_images,
            "target_audience": request.target_audience,
            "key_benefits": request.key_benefits,
            "brand_colors": request.brand_colors,
        },
        target_count=request.variations_count,
        current_stage="pending",
    )

    _jobs[job_id] = state

    # Start async execution
    task = asyncio.create_task(_execute_job(job_id))
    _job_tasks[job_id] = task

    return _state_to_response(state)


@router.post("/jobs/perspective", response_model=JobResponse)
async def create_perspective_job(
    request: CreatePerspectiveJobRequest,
    user_id: str = "demo_user",
):
    """
    Create a new perspective-based UGC ad generation job.

    NEW APPROACH: Takes product images and generates different perspectives,
    then animates smooth transitions between them.

    This is the recommended mode for high-quality product ads.
    """
    job_id = str(uuid.uuid4())

    # Initialize state for perspective pipeline
    state = UGCPipelineState(
        user_id=user_id,
        job_id=job_id,
        mode="perspective",
        raw_input={
            "product_name": request.product_name,
            "product_description": request.product_description,
            "product_images": request.product_images,
            "product_style": request.product_style,
            "image_descriptions": request.image_descriptions,
            "num_perspectives": request.num_perspectives,
        },
        target_count=1,  # One final video for perspective mode
        current_stage="pending",
    )

    _jobs[job_id] = state

    # Start async execution with perspective pipeline
    task = asyncio.create_task(_execute_perspective_job(job_id))
    _job_tasks[job_id] = task

    return _state_to_response(state)


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job_status(job_id: str):
    """Get the current status of a job."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    state = _jobs[job_id]
    return _state_to_response(state)


@router.get("/jobs/{job_id}/videos", response_model=VideosResponse)
async def get_job_videos(job_id: str):
    """Get all generated videos for a completed job."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    state = _jobs[job_id]

    videos = []
    for video in state.videos:
        # Find angle name
        angle = next(
            (a for a in state.angles if a.angle_id == video.angle_id),
            None
        )

        videos.append(VideoDetail(
            video_id=video.video_id,
            angle_id=video.angle_id,
            angle_name=angle.name if angle else None,
            storage_url=video.storage_url,
            thumbnail_url=video.thumbnail_url,
            duration_seconds=video.duration_seconds,
            qc_score=video.qc_score,
            qc_passed=video.qc_passed,
            qc_issues=video.qc_issues,
        ))

    passed = sum(1 for v in videos if v.qc_passed)

    return VideosResponse(
        job_id=job_id,
        total_videos=len(videos),
        passed_videos=passed,
        failed_videos=len(videos) - passed,
        videos=videos,
    )


@router.get("/jobs/{job_id}/metadata", response_model=MetadataResponse)
async def get_job_metadata(job_id: str):
    """Get upload metadata packages for a completed job."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    state = _jobs[job_id]

    packages = [
        UploadPackageDetail(
            video_id=pkg.video_id,
            platform=pkg.platform,
            title=pkg.title,
            description=pkg.description,
            hashtags=pkg.hashtags,
            thumbnail_url=pkg.thumbnail_url,
        )
        for pkg in state.upload_packages
    ]

    return MetadataResponse(job_id=job_id, packages=packages)


@router.delete("/jobs/{job_id}")
async def cancel_job(job_id: str):
    """Cancel a running job."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    if job_id in _job_tasks:
        task = _job_tasks[job_id]
        if not task.done():
            task.cancel()
            _jobs[job_id].error = "Job cancelled by user"

    return {"status": "cancelled", "job_id": job_id}


@router.websocket("/ws/jobs/{job_id}")
async def job_progress_websocket(websocket: WebSocket, job_id: str):
    """
    WebSocket for real-time job progress updates.

    Sends progress updates every 2 seconds until job completes.
    """
    await websocket.accept()

    if job_id not in _jobs:
        await websocket.send_json({"error": "Job not found"})
        await websocket.close()
        return

    try:
        while True:
            state = _jobs[job_id]

            progress = {
                "job_id": job_id,
                "status": _get_job_status(state),
                "current_stage": state.current_stage,
                "progress_percent": _calculate_progress(state),
                "completed_variations": state.completed_count,
                "target_variations": state.target_count,
                "warnings": state.warnings[-5:],  # Last 5 warnings
            }

            if state.error:
                progress["error"] = state.error

            await websocket.send_json(progress)

            # Check if complete
            if state.completed_at or state.error:
                break

            await asyncio.sleep(2)

    except WebSocketDisconnect:
        pass


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Check service health and backend availability."""
    comfyui = ComfyUIClient()
    keyai = KeyAISora2Client()

    comfyui_ok = await comfyui.check_health()
    keyai_ok = await keyai.check_health()

    await comfyui.close()
    await keyai.close()

    # GCS check would require credentials
    gcs_ok = True  # Assume OK if credentials are configured

    return HealthResponse(
        status="healthy" if (comfyui_ok and keyai_ok) else "degraded",
        version=__version__,
        comfyui_available=comfyui_ok,
        keyai_available=keyai_ok,
        gcs_available=gcs_ok,
    )


# ============================================================================
# Helper Functions
# ============================================================================


async def _execute_job(job_id: str):
    """Execute the UGC pipeline for a job (LEGACY text-to-image mode)."""
    import traceback

    state = _jobs[job_id]
    state.current_stage = "running"
    state.started_at = datetime.utcnow()

    print(f"[JOB {job_id}] Starting pipeline execution...")

    try:
        # Create and run the pipeline
        pipeline = create_ugc_pipeline()

        # Convert Pydantic model to dict for LangGraph
        initial_state = state.model_dump()

        print(f"[JOB {job_id}] Running pipeline with mode: {state.mode}")

        # Run the pipeline
        final_state = await pipeline.ainvoke(initial_state)

        print(f"[JOB {job_id}] Pipeline completed!")
        print(f"[JOB {job_id}] Final stage: {final_state.get('current_stage')}")
        print(f"[JOB {job_id}] Warnings: {final_state.get('warnings')}")

        # Update stored state from result
        _jobs[job_id] = UGCPipelineState(**final_state)

    except asyncio.CancelledError:
        print(f"[JOB {job_id}] Cancelled")
        _jobs[job_id].error = "Job cancelled"
    except Exception as e:
        print(f"[JOB {job_id}] ERROR: {e}")
        traceback.print_exc()
        _jobs[job_id].error = str(e)


async def _execute_perspective_job(job_id: str):
    """Execute the perspective-based pipeline for a job."""
    import traceback

    state = _jobs[job_id]
    state.current_stage = "running"
    state.started_at = datetime.utcnow()

    print(f"[PERSPECTIVE JOB {job_id}] Starting perspective pipeline execution...")

    try:
        # Create and run the perspective pipeline
        pipeline = create_perspective_pipeline()

        # Convert Pydantic model to dict for LangGraph
        initial_state = state.model_dump()

        print(f"[PERSPECTIVE JOB {job_id}] Input images: {len(state.raw_input.get('product_images', []))}")

        # Run the pipeline
        final_state = await pipeline.ainvoke(initial_state)

        print(f"[PERSPECTIVE JOB {job_id}] Pipeline completed!")
        print(f"[PERSPECTIVE JOB {job_id}] Final stage: {final_state.get('current_stage')}")
        print(f"[PERSPECTIVE JOB {job_id}] Perspectives: {len(final_state.get('perspectives', []))}")
        print(f"[PERSPECTIVE JOB {job_id}] Transitions: {len(final_state.get('transitions', []))}")
        print(f"[PERSPECTIVE JOB {job_id}] Videos: {len(final_state.get('videos', []))}")
        print(f"[PERSPECTIVE JOB {job_id}] Warnings: {final_state.get('warnings')}")

        # Update stored state from result
        _jobs[job_id] = UGCPipelineState(**final_state)
        _jobs[job_id].completed_at = datetime.utcnow()

    except asyncio.CancelledError:
        print(f"[PERSPECTIVE JOB {job_id}] Cancelled")
        _jobs[job_id].error = "Job cancelled"
    except Exception as e:
        print(f"[PERSPECTIVE JOB {job_id}] ERROR: {e}")
        traceback.print_exc()
        _jobs[job_id].error = str(e)


def _state_to_response(state: UGCPipelineState) -> JobResponse:
    """Convert pipeline state to API response."""
    return JobResponse(
        job_id=state.job_id,
        user_id=state.user_id,
        status=_get_job_status(state),
        current_stage=state.current_stage,
        progress_percent=_calculate_progress(state),
        completed_variations=state.completed_count,
        target_variations=state.target_count,
        error=state.error,
        warnings=state.warnings,
        started_at=state.started_at,
        estimated_completion=state.estimated_completion,
        completed_at=state.completed_at,
    )


def _get_job_status(state: UGCPipelineState) -> str:
    """Determine job status from state."""
    if state.error:
        return "failed"
    if state.completed_at:
        return "completed"
    if state.started_at:
        return "running"
    return "pending"


def _calculate_progress(state: UGCPipelineState) -> float:
    """Calculate progress percentage based on stage."""
    stages = [
        "pending",
        "intake",
        "angles",
        "scripts",
        "shots",
        "prompts",
        "render",
        "assemble",
        "qc",
        "metadata",
    ]

    if state.completed_at:
        return 100.0

    if state.current_stage in stages:
        stage_idx = stages.index(state.current_stage)
        return (stage_idx / len(stages)) * 100

    return 0.0
