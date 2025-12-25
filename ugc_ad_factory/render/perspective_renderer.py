"""
Perspective Renderer - Renders perspectives and transitions.

Coordinates the two-step process:
1. Generate perspective images from source images (ComfyUI img2img)
2. Animate transitions between perspectives (KeyAI I2V)
"""

import asyncio
from asyncio import Semaphore
from pathlib import Path
import tempfile

from ..state import (
    UGCPipelineState,
    SourceImage,
    Perspective,
    GeneratedPerspective,
    Transition,
    GeneratedTransition,
    AssetStatus,
)
from ..config import settings
from .comfyui_client import ComfyUIClient
from .keyai_client import KeyAISora2Client
from ..storage.gcs_store import GCSAssetStore


class PerspectiveRenderer:
    """
    Renders perspectives and animates transitions.

    Two-phase rendering:
    Phase 1: Generate perspective images via ComfyUI img2img
    Phase 2: Animate transitions via KeyAI I2V (start+end frame)
    """

    # Concurrency limits
    COMFYUI_CONCURRENCY = 2    # Max parallel ComfyUI jobs (img2img is heavier)
    KEYAI_CONCURRENCY = 5      # Max parallel KeyAI jobs
    MAX_RETRIES = 2
    TIMEOUT = 300  # 5 min per render

    def __init__(self):
        self.comfyui = ComfyUIClient()
        self.keyai = KeyAISora2Client()
        self.gcs = GCSAssetStore()
        self.comfyui_semaphore = Semaphore(self.COMFYUI_CONCURRENCY)
        self.keyai_semaphore = Semaphore(self.KEYAI_CONCURRENCY)
        self.output_dir = Path(tempfile.gettempdir()) / "ugc_perspectives"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def close(self):
        """Close all clients."""
        await self.comfyui.close()
        await self.keyai.close()

    async def render_perspectives(
        self,
        state: UGCPipelineState,
    ) -> UGCPipelineState:
        """
        Phase 1: Generate all perspective images from source images.

        Uses ComfyUI img2img to transform source images into new perspectives.
        """
        state.current_stage = "render_perspectives"

        if state.error:
            return state

        if not state.perspectives:
            state.error = "No perspectives to render"
            return state

        # First, ensure source images are downloaded locally
        await self._download_source_images(state)

        # Render all perspectives in parallel (with semaphore limits)
        tasks = [
            self._render_perspective_with_retry(state, perspective)
            for perspective in state.perspectives
        ]
        await asyncio.gather(*tasks)

        # Count successes
        success_count = sum(
            1 for gp in state.generated_perspectives
            if gp.status == AssetStatus.SUCCESS
        )
        state.warnings.append(
            f"Rendered {success_count}/{len(state.perspectives)} perspectives"
        )

        return state

    async def render_transitions(
        self,
        state: UGCPipelineState,
    ) -> UGCPipelineState:
        """
        Phase 2: Animate transitions between perspectives using KeyAI I2V.

        Uses start+end frame I2V to create smooth motion between perspectives.
        """
        state.current_stage = "render_transitions"

        if state.error:
            return state

        if not state.transitions:
            state.warnings.append("No transitions to render")
            return state

        # First, link perspective images to transitions
        await self._link_perspective_urls(state)

        # Render all transitions in parallel
        tasks = [
            self._render_transition_with_retry(state, transition)
            for transition in state.transitions
        ]
        await asyncio.gather(*tasks)

        # Count successes
        success_count = sum(
            1 for gt in state.generated_transitions
            if gt.status == AssetStatus.SUCCESS
        )
        state.warnings.append(
            f"Rendered {success_count}/{len(state.transitions)} transitions"
        )

        return state

    async def _download_source_images(self, state: UGCPipelineState):
        """Download source images to local paths."""
        import aiohttp

        async with aiohttp.ClientSession() as session:
            for source in state.source_images:
                if source.local_path and Path(source.local_path).exists():
                    continue

                local_path = self.output_dir / f"source_{source.image_id}.png"

                try:
                    async with session.get(source.url) as resp:
                        if resp.status == 200:
                            with open(local_path, "wb") as f:
                                f.write(await resp.read())
                            source.local_path = str(local_path)
                except Exception as e:
                    state.warnings.append(f"Failed to download {source.image_id}: {e}")

    async def _render_perspective_with_retry(
        self,
        state: UGCPipelineState,
        perspective: Perspective,
    ):
        """Render a single perspective with retry logic."""
        async with self.comfyui_semaphore:
            # Find the generated perspective entry
            gen_persp = next(
                (gp for gp in state.generated_perspectives
                 if gp.perspective_id == perspective.perspective_id),
                None
            )
            if not gen_persp:
                return

            # Find source image
            source = next(
                (s for s in state.source_images
                 if s.image_id == perspective.source_image_id),
                None
            )
            if not source or not source.local_path:
                gen_persp.status = AssetStatus.FAILED
                gen_persp.error_message = "Source image not found"
                return

            # Build perspective prompt
            prompt = self._build_perspective_prompt(perspective, state)

            for attempt in range(self.MAX_RETRIES + 1):
                try:
                    gen_persp.status = AssetStatus.RENDERING

                    result = await asyncio.wait_for(
                        self.comfyui.generate_perspective(
                            source_image_path=source.local_path,
                            perspective_prompt=prompt,
                            denoise_strength=0.4,  # Keep product identity
                        ),
                        timeout=self.TIMEOUT,
                    )

                    if result.get("success"):
                        # Upload to GCS
                        gcs_url = await self.gcs.upload_image(
                            result["image_path"],
                            state.job_id,
                            f"perspective_{perspective.perspective_id}",
                        )
                        gen_persp.generated_url = gcs_url
                        gen_persp.local_path = result["image_path"]
                        gen_persp.status = AssetStatus.SUCCESS
                        return
                    else:
                        gen_persp.error_message = result.get("error", "Unknown error")

                except asyncio.TimeoutError:
                    gen_persp.error_message = f"Timeout after {self.TIMEOUT}s"
                except Exception as e:
                    gen_persp.error_message = str(e)

                if attempt < self.MAX_RETRIES:
                    await asyncio.sleep(2 ** attempt)

            gen_persp.status = AssetStatus.FAILED

    async def _render_transition_with_retry(
        self,
        state: UGCPipelineState,
        transition: Transition,
    ):
        """Render a single transition with retry logic."""
        async with self.keyai_semaphore:
            # Find the generated transition entry
            gen_trans = next(
                (gt for gt in state.generated_transitions
                 if gt.transition_id == transition.transition_id),
                None
            )
            if not gen_trans:
                return

            # Check we have both images
            if not gen_trans.start_image_url or not gen_trans.end_image_url:
                gen_trans.status = AssetStatus.FAILED
                gen_trans.error_message = "Missing start or end image"
                return

            for attempt in range(self.MAX_RETRIES + 1):
                try:
                    gen_trans.status = AssetStatus.RENDERING

                    # Use KeyAI I2V with start+end frames
                    result = await asyncio.wait_for(
                        self.keyai.create_video_from_frames(
                            start_image_url=gen_trans.start_image_url,
                            end_image_url=gen_trans.end_image_url,
                            motion_prompt=transition.motion_description,
                            duration=str(int(transition.duration_seconds)),
                        ),
                        timeout=self.TIMEOUT,
                    )

                    if result.get("success"):
                        gen_trans.video_url = result["video_url"]
                        gen_trans.status = AssetStatus.SUCCESS
                        return
                    else:
                        gen_trans.error_message = result.get("error", "Unknown error")

                except asyncio.TimeoutError:
                    gen_trans.error_message = f"Timeout after {self.TIMEOUT}s"
                except Exception as e:
                    gen_trans.error_message = str(e)

                if attempt < self.MAX_RETRIES:
                    await asyncio.sleep(2 ** attempt)

            gen_trans.status = AssetStatus.FAILED

    async def _link_perspective_urls(self, state: UGCPipelineState):
        """Link generated perspective URLs to transitions."""
        # Build lookup
        perspective_urls = {
            gp.perspective_id: gp.generated_url
            for gp in state.generated_perspectives
            if gp.status == AssetStatus.SUCCESS and gp.generated_url
        }

        for gen_trans in state.generated_transitions:
            trans = next(
                (t for t in state.transitions
                 if t.transition_id == gen_trans.transition_id),
                None
            )
            if not trans:
                continue

            gen_trans.start_image_url = perspective_urls.get(trans.start_perspective_id, "")
            gen_trans.end_image_url = perspective_urls.get(trans.end_perspective_id, "")

    def _build_perspective_prompt(
        self,
        perspective: Perspective,
        state: UGCPipelineState,
    ) -> str:
        """Build the prompt for perspective generation."""
        parts = []

        # Product context
        if state.product_name:
            parts.append(f"Product: {state.product_name}")

        # Perspective description
        parts.append(perspective.description)

        # Camera/composition hints
        parts.append(f"{perspective.camera_angle} view")
        parts.append(f"{perspective.zoom_level} shot")
        parts.append(f"{perspective.lighting_style} lighting")

        if perspective.background_hint:
            parts.append(f"Background: {perspective.background_hint}")

        # Style hints
        parts.append(f"{state.product_style} style")
        parts.append("professional product photography")
        parts.append("high quality")
        parts.append("sharp details")

        return ", ".join(parts)


# LangGraph node functions

async def render_perspectives_node(state: UGCPipelineState) -> UGCPipelineState:
    """LangGraph node for rendering perspectives."""
    renderer = PerspectiveRenderer()
    try:
        return await renderer.render_perspectives(state)
    finally:
        await renderer.close()


async def render_transitions_node(state: UGCPipelineState) -> UGCPipelineState:
    """LangGraph node for rendering transitions."""
    renderer = PerspectiveRenderer()
    try:
        return await renderer.render_transitions(state)
    finally:
        await renderer.close()
