"""
LangGraph Pipeline Definition for UGC Ad Factory.

Defines the complete pipeline from product intake to final metadata generation.
"""

from langgraph.graph import StateGraph, END

from .state import UGCPipelineState
from .agents.intake import intake_product
from .agents.angles import generate_angles
from .agents.scripts import write_scripts
from .agents.shots import plan_shots
from .agents.prompts import build_prompts
from .render.coordinator import render_assets
from .render.assembler import assemble_videos
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


def create_ugc_pipeline():
    """
    Create the LangGraph state graph for UGC ad generation.

    Pipeline stages:
    1. intake - Normalize product input to profile
    2. angles - Generate creative angles/hooks
    3. scripts - Write voiceover scripts + text overlays
    4. shots - Plan shot sequences
    5. prompts - Build generation prompts
    6. render - Generate images and videos
    7. assemble - FFmpeg video assembly
    8. qc - Quality control scoring
    9. metadata - Platform-specific metadata

    Returns:
        Compiled LangGraph graph ready for execution
    """
    workflow = StateGraph(UGCPipelineState)

    # Add all nodes
    workflow.add_node("intake", intake_product)
    workflow.add_node("angles", generate_angles)
    workflow.add_node("scripts", write_scripts)
    workflow.add_node("shots", plan_shots)
    workflow.add_node("prompts", build_prompts)
    workflow.add_node("render", render_assets)
    workflow.add_node("assemble", assemble_videos)
    workflow.add_node("qc", quality_check)
    workflow.add_node("metadata", generate_metadata)

    # Set entry point
    workflow.set_entry_point("intake")

    # Add edges with error checking
    # Each stage checks for errors and can exit early

    workflow.add_conditional_edges(
        "intake",
        should_continue,
        {"continue": "angles", "end": END},
    )

    workflow.add_conditional_edges(
        "angles",
        should_continue,
        {"continue": "scripts", "end": END},
    )

    workflow.add_conditional_edges(
        "scripts",
        should_continue,
        {"continue": "shots", "end": END},
    )

    workflow.add_conditional_edges(
        "shots",
        should_continue,
        {"continue": "prompts", "end": END},
    )

    workflow.add_conditional_edges(
        "prompts",
        should_continue,
        {"continue": "render", "end": END},
    )

    workflow.add_conditional_edges(
        "render",
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
def create_ugc_ad_agent(config: dict | None = None):
    """
    Factory function for creating the UGC ad pipeline.

    This can be registered in langgraph.json for LangGraph Platform deployment.

    Args:
        config: Optional configuration dict

    Returns:
        Compiled LangGraph graph
    """
    return create_ugc_pipeline()


# Convenience: pre-compiled graph instance
graph = create_ugc_pipeline()
