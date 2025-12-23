"""
Render Coordinator - Orchestrates image and video generation with concurrency control.

Manages the rendering pipeline:
1. Generate images via ComfyUI (with semaphore limit)
2. Upload images to GCS for public URLs
3. Generate videos via KeyAI Sora 2 (with semaphore limit)
4. Handle failures with retries and fallbacks
"""

import asyncio
from asyncio import Semaphore
from datetime import datetime
from pathlib import Path
from typing import Callable, Any

from ..state import UGCPipelineState, AssetRequest, AssetStatus, GeneratedAsset
from ..config import settings
from .comfyui_client import ComfyUIClient
from .keyai_client import KeyAISora2Client
from ..storage.gcs_store import GCSAssetStore


class RenderCoordinator:
    """
    Orchestrates rendering with concurrency limits and retries.

    Ensures we don't overload ComfyUI or KeyAI by limiting concurrent requests.
    Implements retry logic with exponential backoff for transient failures.
    """

    def __init__(
        self,
        comfyui_client: ComfyUIClient | None = None,
        keyai_client: KeyAISora2Client | None = None,
        gcs_store: GCSAssetStore | None = None,
    ):
        self.comfyui = comfyui_client or ComfyUIClient()
        self.keyai = keyai_client or KeyAISora2Client()
        self.gcs = gcs_store or GCSAssetStore()

        # Concurrency controls
        self.comfyui_semaphore = Semaphore(settings.comfyui_concurrency)
        self.keyai_semaphore = Semaphore(settings.keyai_concurrency)

        # Configuration
        self.max_retries = settings.max_retries
        self.keyai_timeout = settings.keyai_timeout

    async def close(self):
        """Close all client sessions."""
        await self.comfyui.close()
        await self.keyai.close()

    async def render_all_assets(
        self,
        state: UGCPipelineState,
        progress_callback: Callable[[str, int, int], None] | None = None,
    ) -> UGCPipelineState:
        """
        Process all asset requests in the state.

        Workflow:
        1. Generate all images via ComfyUI (parallel, limited concurrency)
        2. Upload images to GCS for public URLs
        3. Generate videos via KeyAI (parallel, limited concurrency)
        4. Update state with results

        Args:
            state: Pipeline state with asset_requests
            progress_callback: Optional callback(stage, completed, total)

        Returns:
            Updated state with generated_assets populated
        """
        state.current_stage = "render"

        # Separate requests by type
        image_requests = [r for r in state.asset_requests if r.asset_type == "image"]
        video_requests = [r for r in state.asset_requests if r.asset_type == "video"]

        total_images = len(image_requests)
        total_videos = len(video_requests)

        # Step 1: Generate all images
        if progress_callback:
            progress_callback("images", 0, total_images)

        completed_images = 0
        image_tasks = []
        for request in image_requests:
            task = asyncio.create_task(
                self._render_image_with_retry(request, state.job_id)
            )
            image_tasks.append((request, task))

        for request, task in image_tasks:
            await task
            completed_images += 1
            if progress_callback:
                progress_callback("images", completed_images, total_images)

        # Step 2: Upload successful images to GCS
        await self._upload_images_to_gcs(image_requests, state.job_id, state.user_id)

        # Step 3: Link video requests to their image URLs
        image_url_map = {}
        for req in image_requests:
            if req.status == AssetStatus.SUCCESS and req.result_url:
                image_url_map[req.shot_id] = req.result_url

        # Step 4: Generate videos
        if progress_callback:
            progress_callback("videos", 0, total_videos)

        completed_videos = 0
        video_tasks = []
        for request in video_requests:
            # Get the image URL for this shot
            image_url = image_url_map.get(request.shot_id)
            if not image_url:
                request.status = AssetStatus.FAILED
                request.error_message = f"No image available for shot {request.shot_id}"
                completed_videos += 1
                continue

            request.reference_image_url = image_url
            task = asyncio.create_task(
                self._render_video_with_retry(request, state.job_id)
            )
            video_tasks.append((request, task))

        for request, task in video_tasks:
            await task
            completed_videos += 1
            if progress_callback:
                progress_callback("videos", completed_videos, total_videos)

        # Step 5: Build generated_assets summary
        state.generated_assets = {
            "images": [
                self._request_to_asset(r)
                for r in image_requests
                if r.status == AssetStatus.SUCCESS
            ],
            "clips": [
                self._request_to_asset(r)
                for r in video_requests
                if r.status == AssetStatus.SUCCESS
            ],
        }

        # Summary
        image_success = sum(1 for r in image_requests if r.status == AssetStatus.SUCCESS)
        video_success = sum(1 for r in video_requests if r.status == AssetStatus.SUCCESS)
        state.warnings.append(
            f"Render complete: {image_success}/{total_images} images, "
            f"{video_success}/{total_videos} videos"
        )

        return state

    async def _render_image_with_retry(
        self,
        request: AssetRequest,
        job_id: str,
    ) -> None:
        """Render an image with concurrency control and retries."""
        async with self.comfyui_semaphore:
            for attempt in range(self.max_retries + 1):
                try:
                    request.status = AssetStatus.RENDERING
                    request.started_at = datetime.utcnow()

                    result = await self.comfyui.generate_image(
                        prompt=request.prompt,
                        negative_prompt=request.negative_prompt,
                        width=request.width,
                        height=request.height,
                        style_preset=request.style_preset,
                    )

                    if result.get("success"):
                        request.status = AssetStatus.SUCCESS
                        request.local_path = result["image_path"]
                        request.completed_at = datetime.utcnow()
                        return
                    else:
                        request.error_message = result.get("error", "Unknown error")

                except asyncio.TimeoutError:
                    request.error_message = "Timeout during image generation"
                except Exception as e:
                    request.error_message = str(e)

                request.retry_count += 1
                if attempt < self.max_retries:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff

            # All retries failed
            request.status = AssetStatus.FAILED
            request.completed_at = datetime.utcnow()

    async def _render_video_with_retry(
        self,
        request: AssetRequest,
        job_id: str,
    ) -> None:
        """Render a video with concurrency control and retries."""
        async with self.keyai_semaphore:
            for attempt in range(self.max_retries + 1):
                try:
                    request.status = AssetStatus.RENDERING
                    request.started_at = datetime.utcnow()

                    # Determine duration (10 or 15 seconds)
                    duration = "10" if (request.duration_seconds or 10) <= 10 else "15"

                    result = await self.keyai.generate_video(
                        image_url=request.reference_image_url,
                        prompt=request.prompt,
                        duration=duration,
                        aspect_ratio="portrait",  # 9:16 for vertical video
                        size="high",
                        timeout=self.keyai_timeout,
                    )

                    if result.get("success"):
                        request.status = AssetStatus.SUCCESS
                        request.result_url = result["video_url"]
                        request.completed_at = datetime.utcnow()
                        return
                    else:
                        request.error_message = result.get("error", "Unknown error")

                except asyncio.TimeoutError:
                    request.error_message = f"Timeout after {self.keyai_timeout}s"
                except Exception as e:
                    request.error_message = str(e)

                request.retry_count += 1
                if attempt < self.max_retries:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff

            # All retries failed - mark for fallback
            request.status = AssetStatus.FAILED
            request.completed_at = datetime.utcnow()

    async def _upload_images_to_gcs(
        self,
        requests: list[AssetRequest],
        job_id: str,
        user_id: str,
    ) -> None:
        """Upload successful images to GCS and update result_url."""
        for request in requests:
            if request.status == AssetStatus.SUCCESS and request.local_path:
                try:
                    public_url = await self.gcs.upload_image(
                        local_path=request.local_path,
                        job_id=job_id,
                        user_id=user_id,
                        asset_id=request.request_id,
                    )
                    request.result_url = public_url
                except Exception as e:
                    request.error_message = f"GCS upload failed: {e}"
                    # Keep the local path, video gen will fail gracefully

    def _request_to_asset(self, request: AssetRequest) -> dict[str, Any]:
        """Convert AssetRequest to GeneratedAsset dict."""
        return {
            "asset_id": request.request_id,
            "request_id": request.request_id,
            "shot_id": request.shot_id,
            "asset_type": request.asset_type,
            "storage_url": request.result_url or "",
            "local_path": request.local_path,
            "duration_seconds": request.duration_seconds,
        }


async def render_assets(state: UGCPipelineState) -> UGCPipelineState:
    """
    Stage 6: Render all assets (images and videos).

    This is the LangGraph node function that wraps the RenderCoordinator.
    """
    if state.error:
        return state

    if not state.asset_requests:
        state.error = "No asset requests available (prompt building stage failed?)"
        return state

    coordinator = RenderCoordinator()
    try:
        state = await coordinator.render_all_assets(state)
    finally:
        await coordinator.close()

    return state
