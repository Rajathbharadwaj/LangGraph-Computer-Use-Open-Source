"""
Metadata Tagger Agent - Generates platform-specific upload metadata.

Stage 9 (final) of the UGC pipeline.
"""

import json
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from ..state import UGCPipelineState, UploadPackage
from ..config import settings


METADATA_SYSTEM_PROMPT = """You are a social media expert creating upload metadata for short-form video ads.

For each video, generate platform-specific metadata:
1. YouTube Shorts: Title (max 100 chars), description (with product mention), tags
2. TikTok: Caption (with relevant hashtags integrated)
3. Instagram Reels: Caption (with hashtags at the end)

Guidelines:
- Titles should be catchy and create curiosity
- Use trending/relevant hashtags for each platform
- Include a subtle CTA in descriptions
- Keep TikTok/Reels captions conversational
- Use emojis strategically but don't overdo it

Respond with a JSON array:
[
    {
        "video_id": "video_001",
        "platforms": [
            {
                "platform": "youtube_shorts",
                "title": "This changed my morning routine forever",
                "description": "I couldn't believe how easy it was...",
                "hashtags": ["#shorts", "#lifehack", "#productivity"]
            },
            {
                "platform": "tiktok",
                "title": "POV: you finally found THE product",
                "description": "okay but why did no one tell me about this sooner #fyp #tiktokmademebuyit",
                "hashtags": ["#fyp", "#tiktokmademebuyit", "#viral"]
            },
            {
                "platform": "reels",
                "title": "The only product you need this year",
                "description": "Trust me on this one... #reels #viral #musthave",
                "hashtags": ["#reels", "#viral", "#musthave"]
            }
        ]
    },
    ...
]
"""


async def generate_metadata(state: UGCPipelineState) -> UGCPipelineState:
    """
    Stage 9: Generate platform-specific upload metadata for videos that passed QC.

    Creates UploadPackage objects for YouTube Shorts, TikTok, and Instagram Reels.
    """
    state.current_stage = "metadata"

    if state.error:
        return state

    # Only generate metadata for videos that passed QC
    passed_videos = [v for v in state.videos if v.qc_passed]

    if not passed_videos:
        state.warnings.append("No videos passed QC, skipping metadata generation")
        return state

    profile = state.product_profile

    # Build prompt with video info
    videos_info = []
    for video in passed_videos:
        # Find the corresponding angle
        angle = next(
            (a for a in state.angles if a.angle_id == video.angle_id),
            None,
        )
        # Find the corresponding script
        script = next(
            (s for s in state.script_packages if s.script_id == video.script_id),
            None,
        )

        videos_info.append({
            "video_id": video.video_id,
            "angle_name": angle.name if angle else "Unknown",
            "hook_type": angle.hook_type if angle else "general",
            "hook_text": angle.hook_text if angle else "",
            "cta_text": script.cta_text if script else "Link in bio",
            "duration_seconds": video.duration_seconds,
        })

    user_prompt = f"""Generate upload metadata for these {len(passed_videos)} videos:

Product: {profile.name}
Category: {profile.category}
Target Audience: {profile.target_audience}
Tone: {profile.tone}

Videos:
{json.dumps(videos_info, indent=2)}

Create platform-specific metadata for each video, optimized for:
- YouTube Shorts (discovery via search + shorts feed)
- TikTok (virality via FYP algorithm)
- Instagram Reels (explore page + hashtag discovery)"""

    try:
        llm = ChatAnthropic(
            model=settings.llm_model,
            api_key=settings.anthropic_api_key,
            max_tokens=16000,
        )

        messages = [
            SystemMessage(content=METADATA_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        response = await llm.ainvoke(messages)

        # Parse JSON response
        content = response.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        metadata_list = json.loads(content.strip())

        # Create UploadPackage objects
        state.upload_packages = []
        for meta in metadata_list:
            video_id = meta.get("video_id")
            video = next((v for v in passed_videos if v.video_id == video_id), None)

            for platform_data in meta.get("platforms", []):
                package = UploadPackage(
                    video_id=video_id,
                    platform=platform_data.get("platform", "unknown"),
                    title=platform_data.get("title", ""),
                    description=platform_data.get("description", ""),
                    hashtags=platform_data.get("hashtags", []),
                    thumbnail_url=video.thumbnail_url if video else None,
                )
                state.upload_packages.append(package)

        # Mark completion
        from datetime import datetime
        state.completed_at = datetime.utcnow()

        state.warnings.append(
            f"Generated {len(state.upload_packages)} upload packages for {len(passed_videos)} videos"
        )

    except json.JSONDecodeError as e:
        state.error = f"Failed to parse metadata response: {str(e)}"
    except Exception as e:
        state.error = f"Metadata generation failed: {str(e)}"

    return state
