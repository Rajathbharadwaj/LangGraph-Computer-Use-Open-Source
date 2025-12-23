"""
LangGraph Pipeline for Perspective-Based UGC Ad Generation.

NEW PIPELINE FLOW:
1. intake - Load and validate source images
2. perspectives - Plan perspectives to generate
3. transitions - Plan transitions between perspectives
4. render_perspectives - Generate perspective images (ComfyUI img2img)
5. render_transitions - Animate transitions (KeyAI I2V)
6. assemble - Concatenate transition clips into final video
7. qc - Quality check the final video
8. metadata - Generate platform metadata

This replaces the old text-to-image pipeline with a perspective-based approach
where we take real product images and generate new views/angles, then animate
smooth transitions between them.
"""

from langgraph.graph import StateGraph, END

from .state import UGCPipelineState
from .agents.perspectives import analyze_source_images, plan_perspectives
from .agents.transitions import plan_transitions
from .render.perspective_renderer import (
    render_perspectives_node,
    render_transitions_node,
)
from .agents.qc import quality_check
from .agents.metadata import generate_metadata


def should_continue(state: UGCPipelineState) -> str:
    """
    Conditional edge function to check for errors.

    If there's an error at any stage, skip to END.
    """
    if state.error:
        return "end"
    return "continue"


async def assemble_perspective_video(state: UGCPipelineState) -> UGCPipelineState:
    """
    Assemble the final video from transition clips.

    Concatenates all generated transition clips in sequence
    to create the final product video.
    """
    from .render.assembler import FFmpegAssembler
    from .state import GeneratedVideo, AssetStatus
    from pathlib import Path
    import tempfile

    state.current_stage = "assemble"

    if state.error:
        return state

    if not state.generated_transitions:
        state.error = "No transitions to assemble"
        return state

    # Collect successful transition clips
    clips = []
    for gen_trans in state.generated_transitions:
        if gen_trans.status == AssetStatus.SUCCESS and gen_trans.video_url:
            # Find the transition definition for duration
            trans = next(
                (t for t in state.transitions
                 if t.transition_id == gen_trans.transition_id),
                None
            )
            duration = trans.duration_seconds if trans else 2.5

            clips.append({
                "path": gen_trans.video_url,  # Will be downloaded
                "duration": duration,
                "is_fallback": False,
            })

    if not clips:
        state.error = "No successful transition clips to assemble"
        return state

    # Use FFmpegAssembler to concatenate
    assembler = FFmpegAssembler()

    # Download clips first
    import aiohttp
    output_dir = Path(tempfile.gettempdir()) / "ugc_assembly"
    output_dir.mkdir(parents=True, exist_ok=True)

    async with aiohttp.ClientSession() as session:
        for i, clip in enumerate(clips):
            if clip["path"].startswith("http"):
                local_path = output_dir / f"trans_clip_{i}.mp4"
                try:
                    async with session.get(clip["path"]) as resp:
                        if resp.status == 200:
                            with open(local_path, "wb") as f:
                                f.write(await resp.read())
                            clip["path"] = str(local_path)
                except Exception as e:
                    state.warnings.append(f"Failed to download clip {i}: {e}")
                    continue

    # Concatenate clips
    try:
        output_path = output_dir / f"{state.job_id}_final.mp4"
        concat_result = await assembler._concatenate_clips(clips, "cut")

        if concat_result and Path(concat_result).exists():
            duration = await assembler._get_video_duration(concat_result)

            video = GeneratedVideo(
                video_id="video_final",
                angle_id="perspective_flow",
                script_id="",
                shotlist_id="",
                storage_url="",  # Will be set after GCS upload
                local_path=concat_result,
                duration_seconds=duration,
            )
            state.videos.append(video)
            state.warnings.append(f"Assembled final video: {duration:.1f}s")
        else:
            state.error = "Failed to concatenate clips"

    except Exception as e:
        state.error = f"Assembly failed: {e}"

    return state


def create_perspective_pipeline():
    """
    Create the LangGraph state graph for perspective-based UGC ad generation.

    Pipeline stages:
    1. intake - Load and validate source images
    2. perspectives - Plan what perspectives to generate
    3. transitions - Plan transitions between perspectives
    4. render_perspectives - Generate perspective images via img2img
    5. render_transitions - Animate transitions via I2V
    6. assemble - Concatenate into final video
    7. qc - Quality control
    8. metadata - Platform metadata

    Returns:
        Compiled LangGraph graph ready for execution
    """
    workflow = StateGraph(UGCPipelineState)

    # Add all nodes
    workflow.add_node("intake", analyze_source_images)
    workflow.add_node("perspectives", plan_perspectives)
    workflow.add_node("transitions", plan_transitions)
    workflow.add_node("render_perspectives", render_perspectives_node)
    workflow.add_node("render_transitions", render_transitions_node)
    workflow.add_node("assemble", assemble_perspective_video)
    workflow.add_node("qc", quality_check)
    workflow.add_node("metadata", generate_metadata)

    # Set entry point
    workflow.set_entry_point("intake")

    # Add edges with error checking
    workflow.add_conditional_edges(
        "intake",
        should_continue,
        {"continue": "perspectives", "end": END},
    )

    workflow.add_conditional_edges(
        "perspectives",
        should_continue,
        {"continue": "transitions", "end": END},
    )

    workflow.add_conditional_edges(
        "transitions",
        should_continue,
        {"continue": "render_perspectives", "end": END},
    )

    workflow.add_conditional_edges(
        "render_perspectives",
        should_continue,
        {"continue": "render_transitions", "end": END},
    )

    workflow.add_conditional_edges(
        "render_transitions",
        should_continue,
        {"continue": "assemble", "end": END},
    )

    workflow.add_conditional_edges(
        "assemble",
        should_continue,
        {"continue": "qc", "end": END},
    )

    workflow.add_conditional_edges(
        "qc",
        should_continue,
        {"continue": "metadata", "end": END},
    )

    # Final edge to END
    workflow.add_edge("metadata", END)

    return workflow.compile()


# Factory function for external use
def create_perspective_ad_agent(config: dict | None = None):
    """
    Factory function for creating the perspective-based UGC ad pipeline.

    This can be registered in langgraph.json for LangGraph Platform deployment.

    Args:
        config: Optional configuration dict

    Returns:
        Compiled LangGraph graph
    """
    return create_perspective_pipeline()


# Convenience: pre-compiled graph instance
perspective_graph = create_perspective_pipeline()
