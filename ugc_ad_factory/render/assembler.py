"""
Video Assembler - FFmpeg-based video assembly with text overlays.

Stitches together video clips, adds text overlays, transitions, and music.
"""

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any
import tempfile
import uuid

from ..state import (
    UGCPipelineState,
    GeneratedVideo,
    ShotList,
    ScriptPackage,
    AssetRequest,
    AssetStatus,
)
from ..config import settings


class FFmpegAssembler:
    """
    Assembles final videos from rendered clips using FFmpeg.

    Features:
    - Concatenate clips in sequence
    - Add text overlays with timing
    - Simple transitions (cuts or crossfades)
    - Background music mixing
    - Ken Burns fallback for missing video clips
    """

    def __init__(self, output_dir: Path | None = None):
        self.output_dir = output_dir or Path(tempfile.gettempdir()) / "ugc_assembly"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def assemble_video(
        self,
        shotlist: ShotList,
        script: ScriptPackage,
        asset_requests: list[AssetRequest],
        job_id: str,
        music_path: str | None = None,
    ) -> dict[str, Any]:
        """
        Assemble a single video from its components.

        Args:
            shotlist: The shot list with shot ordering
            script: The script with text overlays
            asset_requests: All asset requests (to find rendered clips)
            job_id: Job ID for output naming
            music_path: Optional path to background music

        Returns:
            dict with:
                - success: bool
                - output_path: path to assembled video
                - duration_seconds: actual duration
                - error: error message if failed
        """
        try:
            # Collect clips for each shot
            clips = []
            total_duration = 0.0

            for shot in shotlist.shots:
                # Find the video clip for this shot
                video_req = next(
                    (r for r in asset_requests
                     if r.shot_id == shot.shot_id and r.asset_type == "video"
                     and r.status == AssetStatus.SUCCESS and r.result_url),
                    None
                )

                if video_req and video_req.result_url:
                    # Download video clip if needed
                    clip_path = await self._ensure_local_clip(
                        video_req.result_url, video_req.request_id
                    )
                    clips.append({
                        "path": clip_path,
                        "duration": shot.duration_seconds,
                        "is_fallback": False,
                    })
                else:
                    # Try to use image fallback (Ken Burns)
                    image_req = next(
                        (r for r in asset_requests
                         if r.shot_id == shot.shot_id and r.asset_type == "image"
                         and r.status == AssetStatus.SUCCESS and r.local_path),
                        None
                    )

                    if image_req and image_req.local_path:
                        fallback_path = await self._create_ken_burns_clip(
                            image_req.local_path,
                            shot.duration_seconds,
                            shot.shot_id,
                        )
                        clips.append({
                            "path": fallback_path,
                            "duration": shot.duration_seconds,
                            "is_fallback": True,
                        })

                total_duration += shot.duration_seconds

            if not clips:
                return {
                    "success": False,
                    "error": "No clips available for assembly",
                }

            # Build output path
            output_path = self.output_dir / f"{job_id}_{shotlist.shotlist_id}.mp4"

            # Concatenate clips
            concat_path = await self._concatenate_clips(clips, shotlist.transition_style)

            # Add text overlays
            if script.text_overlays:
                with_overlays = await self._add_text_overlays(
                    concat_path, script.text_overlays
                )
            else:
                with_overlays = concat_path

            # Add music if provided
            if music_path:
                final_path = await self._add_music(with_overlays, music_path, output_path)
            else:
                # Just copy/move to final location
                final_path = output_path
                if with_overlays != output_path:
                    subprocess.run(["cp", str(with_overlays), str(final_path)], check=True)

            # Get actual duration
            duration = await self._get_video_duration(final_path)

            return {
                "success": True,
                "output_path": str(final_path),
                "duration_seconds": duration,
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    async def _ensure_local_clip(self, url: str, clip_id: str) -> str:
        """Download a clip from URL if needed, return local path."""
        local_path = self.output_dir / f"clip_{clip_id}.mp4"

        if local_path.exists():
            return str(local_path)

        # Download using curl or aiohttp
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    with open(local_path, "wb") as f:
                        f.write(await resp.read())
                    return str(local_path)

        raise RuntimeError(f"Failed to download clip from {url}")

    async def _create_ken_burns_clip(
        self,
        image_path: str,
        duration: float,
        shot_id: str,
    ) -> str:
        """Create Ken Burns pan/zoom effect from static image."""
        output_path = self.output_dir / f"fallback_{shot_id}.mp4"

        # FFmpeg Ken Burns effect using zoompan filter
        filter_complex = (
            f"zoompan=z='min(zoom+0.0015,1.3)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={int(duration * 25)}:s=1080x1920:fps=25"
        )

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", image_path,
            "-vf", filter_complex,
            "-t", str(duration),
            "-pix_fmt", "yuv420p",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            str(output_path),
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()

        if process.returncode != 0:
            raise RuntimeError(f"Ken Burns creation failed: {stderr.decode()}")

        return str(output_path)

    async def _concatenate_clips(
        self,
        clips: list[dict],
        transition_style: str = "cut",
    ) -> str:
        """Concatenate clips with optional transitions."""
        output_path = self.output_dir / f"concat_{uuid.uuid4().hex[:8]}.mp4"

        # Create concat file
        concat_file = self.output_dir / f"concat_{uuid.uuid4().hex[:8]}.txt"
        with open(concat_file, "w") as f:
            for clip in clips:
                f.write(f"file '{clip['path']}'\n")

        if transition_style == "crossfade" and len(clips) > 1:
            # Use xfade filter for crossfades
            # This is more complex, simplified to cuts for now
            pass

        # Simple concatenation with cuts
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-c", "copy",
            str(output_path),
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()

        if process.returncode != 0:
            # Try re-encoding if copy fails
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_file),
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "23",
                "-c:a", "aac",
                str(output_path),
            ]
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await process.communicate()

            if process.returncode != 0:
                raise RuntimeError(f"Concatenation failed: {stderr.decode()}")

        return str(output_path)

    def _escape_drawtext(self, text: str) -> str:
        """
        Escape special characters for FFmpeg drawtext filter.

        FFmpeg drawtext requires escaping:
        - \ (backslash) -> \\
        - ' (single quote) -> \'
        - : (colon) -> \:
        - = (equals) -> \=
        """
        # Order matters: escape backslashes first
        text = text.replace("\\", "\\\\")
        text = text.replace("'", "\\'")
        text = text.replace(":", "\\:")
        text = text.replace("=", "\\=")
        return text

    async def _add_text_overlays(
        self,
        input_path: str,
        overlays: list[dict],
    ) -> str:
        """Add text overlays to video using drawtext filter."""
        output_path = self.output_dir / f"overlays_{uuid.uuid4().hex[:8]}.mp4"

        # Build drawtext filter chain
        filters = []
        for overlay in overlays:
            time = float(overlay.get("time", 0))
            text = self._escape_drawtext(overlay.get("text", ""))
            style = overlay.get("style", "benefit")

            # Different styles for different overlay types
            if style == "hook":
                fontsize = 72
                fontcolor = "white"
            elif style == "cta":
                fontsize = 56
                fontcolor = "yellow"
            else:
                fontsize = 48
                fontcolor = "white"

            # Enable for ~3 seconds after time
            enable = f"between(t,{time},{time + 3})"

            filter_str = (
                f"drawtext=text='{text}':fontsize={fontsize}:fontcolor={fontcolor}"
                f":x=(w-text_w)/2:y=h-text_h-100:enable='{enable}'"
                f":shadowcolor=black:shadowx=2:shadowy=2"
            )
            filters.append(filter_str)

        if not filters:
            return input_path

        filter_complex = ",".join(filters)

        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-vf", filter_complex,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "copy",
            str(output_path),
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()

        if process.returncode != 0:
            raise RuntimeError(f"Text overlay failed: {stderr.decode()}")

        return str(output_path)

    async def _add_music(
        self,
        video_path: str,
        music_path: str,
        output_path: Path,
    ) -> str:
        """Add background music to video."""
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", music_path,
            "-filter_complex",
            "[1:a]volume=0.3[music];[0:a][music]amix=inputs=2:duration=first",
            "-c:v", "copy",
            str(output_path),
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()

        if process.returncode != 0:
            # Fall back to video without music
            subprocess.run(["cp", video_path, str(output_path)], check=True)

        return str(output_path)

    async def _get_video_duration(self, path: Path | str) -> float:
        """Get video duration using ffprobe."""
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate()

        try:
            return float(stdout.decode().strip())
        except ValueError:
            return 0.0


async def assemble_videos(state: UGCPipelineState) -> UGCPipelineState:
    """
    Stage 7: Assemble final videos from rendered assets.

    This is the LangGraph node function that wraps the FFmpegAssembler.
    """
    state.current_stage = "assemble"

    if state.error:
        return state

    if not state.shot_lists:
        state.error = "No shot lists available (shot planning stage failed?)"
        return state

    assembler = FFmpegAssembler()

    for i, shotlist in enumerate(state.shot_lists):
        # Find matching script
        script = next(
            (s for s in state.script_packages if s.script_id == shotlist.script_id),
            None
        )

        if not script:
            state.warnings.append(f"No script found for shotlist {shotlist.shotlist_id}")
            continue

        # Assemble this video
        result = await assembler.assemble_video(
            shotlist=shotlist,
            script=script,
            asset_requests=state.asset_requests,
            job_id=state.job_id,
        )

        if result.get("success"):
            video = GeneratedVideo(
                video_id=f"video_{i:03d}",
                angle_id=shotlist.angle_id,
                script_id=shotlist.script_id,
                shotlist_id=shotlist.shotlist_id,
                storage_url="",  # Will be set after GCS upload
                local_path=result["output_path"],
                duration_seconds=result["duration_seconds"],
            )
            state.videos.append(video)
        else:
            state.warnings.append(
                f"Assembly failed for {shotlist.shotlist_id}: {result.get('error')}"
            )

    state.warnings.append(f"Assembled {len(state.videos)} videos")

    return state
