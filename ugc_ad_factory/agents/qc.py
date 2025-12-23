"""
Quality Control Agent - Evaluates generated videos and assigns scores.

Stage 8 of the UGC pipeline.
"""

from ..state import (
    UGCPipelineState,
    GeneratedVideo,
    AssetRequest,
    AssetStatus,
    ShotList,
)
from ..config import settings


async def quality_check(state: UGCPipelineState) -> UGCPipelineState:
    """
    Stage 8: Quality control on assembled videos.

    Evaluates each video and assigns a QC score based on:
    - Missing shots (major penalty)
    - Fallback shots used (minor penalty)
    - Duration within valid range
    - Basic file validation

    Videos with score >= 0.7 pass QC.
    """
    state.current_stage = "qc"

    if state.error:
        return state

    if not state.videos:
        state.error = "No videos to QC (assembly stage failed?)"
        return state

    passed_count = 0
    failed_count = 0

    for video in state.videos:
        # Find the corresponding shot list
        shotlist = next(
            (sl for sl in state.shot_lists if sl.shotlist_id == video.shotlist_id),
            None,
        )

        if not shotlist:
            video.qc_issues.append("No matching shot list found")
            video.qc_score = 0.0
            video.qc_passed = False
            failed_count += 1
            continue

        # Evaluate video
        video = await _evaluate_video(
            video=video,
            shot_list=shotlist,
            asset_requests=state.asset_requests,
        )

        if video.qc_passed:
            passed_count += 1
        else:
            failed_count += 1

    state.completed_count = passed_count
    state.warnings.append(
        f"QC complete: {passed_count} passed, {failed_count} failed"
    )

    return state


async def _evaluate_video(
    video: GeneratedVideo,
    shot_list: ShotList,
    asset_requests: list[AssetRequest],
) -> GeneratedVideo:
    """
    Evaluate a single video and compute QC score.

    Scoring rules:
    - Start at 1.0
    - Missing shot: -0.15 each
    - Fallback (Ken Burns): -0.05 each
    - Duration too short (<9s): -0.2
    - Duration too long (>17s): -0.1
    - PASS threshold: 0.7
    """
    score = 1.0
    issues = []
    missing_shots = 0
    fallback_shots = 0

    # Check all planned shots have assets
    for shot in shot_list.shots:
        # Find corresponding asset request
        request = next(
            (r for r in asset_requests if r.shot_id == shot.shot_id and r.asset_type == "video"),
            None,
        )

        if not request:
            # Try to find image request (might have fallen back to image)
            image_request = next(
                (r for r in asset_requests if r.shot_id == shot.shot_id and r.asset_type == "image"),
                None,
            )
            if not image_request or image_request.status != AssetStatus.SUCCESS:
                missing_shots += 1
                score -= 0.15
                issues.append(f"Missing shot: {shot.shot_id}")
        elif request.status == AssetStatus.FAILED:
            # Check if we have a fallback image
            image_request = next(
                (r for r in asset_requests if r.shot_id == shot.shot_id and r.asset_type == "image"),
                None,
            )
            if image_request and image_request.status == AssetStatus.SUCCESS:
                # Used Ken Burns fallback
                fallback_shots += 1
                score -= 0.05
                issues.append(f"Fallback used for: {shot.shot_id}")
            else:
                missing_shots += 1
                score -= 0.15
                issues.append(f"Missing shot: {shot.shot_id}")
        elif request.status == AssetStatus.FALLBACK:
            fallback_shots += 1
            score -= 0.05
            issues.append(f"Fallback used for: {shot.shot_id}")
        elif request.status != AssetStatus.SUCCESS:
            missing_shots += 1
            score -= 0.15
            issues.append(f"Shot not ready: {shot.shot_id} ({request.status})")

    # Check duration
    min_duration = settings.qc_min_duration
    max_duration = settings.qc_max_duration

    if video.duration_seconds < min_duration:
        score -= 0.2
        issues.append(
            f"Too short: {video.duration_seconds:.1f}s < {min_duration}s"
        )
    elif video.duration_seconds > max_duration:
        score -= 0.1
        issues.append(
            f"Too long: {video.duration_seconds:.1f}s > {max_duration}s"
        )

    # Update video with QC results
    video.qc_score = max(0.0, score)
    video.missing_shots = missing_shots
    video.fallback_shots = fallback_shots
    video.qc_passed = video.qc_score >= settings.qc_pass_threshold
    video.qc_issues = issues

    return video


def create_fallback_clip(image_path: str, duration: float, output_path: str) -> str:
    """
    Create Ken Burns pan/zoom effect from static image.

    This is used as a fallback when video generation fails but we have the image.

    Args:
        image_path: Path to the source image
        duration: Duration in seconds
        output_path: Path for the output video

    Returns:
        Path to the generated fallback clip
    """
    import subprocess

    # FFmpeg Ken Burns effect using zoompan filter
    # Slowly zooms in from 1.0 to 1.2 scale while panning slightly
    filter_complex = (
        f"zoompan=z='min(zoom+0.001,1.2)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d={int(duration * 25)}:s=1080x1920:fps=25"
    )

    cmd = [
        "ffmpeg",
        "-y",
        "-loop", "1",
        "-i", image_path,
        "-vf", filter_complex,
        "-t", str(duration),
        "-pix_fmt", "yuv420p",
        "-c:v", "libx264",
        "-preset", "fast",
        output_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg failed: {result.stderr}")

    return output_path
