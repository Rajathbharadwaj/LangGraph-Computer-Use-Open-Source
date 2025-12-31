"""
KIE AI Image Generation Service

Uses the Nano Banana Pro model to generate images from prompts.
API Documentation: https://kie.ai/api-docs
Prompt Guide: https://www.imagine.art/blogs/nano-banana-pro-prompt-guide
"""

import os
import asyncio
import aiohttp
import anthropic
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

# Anthropic client for prompt generation
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# KIE API configuration
KIE_API_BASE_URL = "https://api.kie.ai/api/v1"
KIE_API_KEY = os.getenv("KIE_API_KEY", "")

# Default settings
DEFAULT_MODEL = "nano-banana-pro"
DEFAULT_ASPECT_RATIO = "1:1"  # Good for X/Twitter
DEFAULT_RESOLUTION = "1K"
DEFAULT_OUTPUT_FORMAT = "png"


class KIEImageService:
    """Service for generating images using KIE AI's Nano Banana Pro model"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or KIE_API_KEY
        if not self.api_key:
            logger.warning("KIE_API_KEY not set - AI image generation will not work")

    async def generate_image(
        self,
        prompt: str,
        aspect_ratio: str = DEFAULT_ASPECT_RATIO,
        resolution: str = DEFAULT_RESOLUTION,
        output_format: str = DEFAULT_OUTPUT_FORMAT,
        reference_images: list = None,
        timeout_seconds: int = 120
    ) -> Dict[str, Any]:
        """
        Generate an image using KIE AI.

        Args:
            prompt: Text description of the image to generate
            aspect_ratio: Aspect ratio (1:1, 16:9, 9:16, etc.)
            resolution: Resolution (1K, 2K, 4K)
            output_format: Output format (png, jpg)
            reference_images: Optional list of reference image URLs
            timeout_seconds: Max time to wait for generation

        Returns:
            Dict with keys:
            - success: bool
            - image_url: str (if successful)
            - error: str (if failed)
            - task_id: str
        """
        if not self.api_key:
            return {
                "success": False,
                "error": "KIE_API_KEY not configured",
                "image_url": None,
                "task_id": None
            }

        try:
            # Step 1: Create the generation task
            task_result = await self._create_task(
                prompt=prompt,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                output_format=output_format,
                image_input=reference_images or []
            )

            if not task_result.get("success"):
                return task_result

            task_id = task_result["task_id"]
            logger.info(f"Created KIE task: {task_id}")

            # Step 2: Poll for results
            result = await self._poll_for_result(task_id, timeout_seconds)
            return result

        except Exception as e:
            logger.error(f"KIE image generation failed: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e),
                "image_url": None,
                "task_id": None
            }

    async def _create_task(
        self,
        prompt: str,
        aspect_ratio: str,
        resolution: str,
        output_format: str,
        image_input: list
    ) -> Dict[str, Any]:
        """Create a generation task on KIE API"""
        url = f"{KIE_API_BASE_URL}/jobs/createTask"

        payload = {
            "model": DEFAULT_MODEL,
            "input": {
                "prompt": prompt,
                "image_input": image_input,
                "aspect_ratio": aspect_ratio,
                "resolution": resolution,
                "output_format": output_format
            }
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                data = await response.json()

                if response.status != 200 or data.get("code") != 200:
                    error_msg = data.get("msg", f"HTTP {response.status}")
                    logger.error(f"KIE create task failed: {error_msg}")
                    return {
                        "success": False,
                        "error": error_msg,
                        "task_id": None
                    }

                task_id = data.get("data", {}).get("taskId")
                if not task_id:
                    return {
                        "success": False,
                        "error": "No taskId in response",
                        "task_id": None
                    }

                return {
                    "success": True,
                    "task_id": task_id
                }

    async def _poll_for_result(
        self,
        task_id: str,
        timeout_seconds: int
    ) -> Dict[str, Any]:
        """Poll KIE API until task completes or times out"""
        url = f"{KIE_API_BASE_URL}/jobs/recordInfo"
        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }

        start_time = asyncio.get_event_loop().time()
        poll_interval = 2  # Start with 2 seconds

        async with aiohttp.ClientSession() as session:
            while True:
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > timeout_seconds:
                    return {
                        "success": False,
                        "error": f"Timeout after {timeout_seconds}s",
                        "image_url": None,
                        "task_id": task_id
                    }

                try:
                    async with session.get(
                        url,
                        params={"taskId": task_id},
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as response:
                        data = await response.json()

                        if response.status != 200 or data.get("code") != 200:
                            error_msg = data.get("msg", f"HTTP {response.status}")
                            logger.warning(f"KIE poll error: {error_msg}")
                            await asyncio.sleep(poll_interval)
                            continue

                        task_data = data.get("data", {})
                        state = task_data.get("state")

                        logger.info(f"KIE task {task_id} state: {state}")

                        if state == "success":
                            # Parse resultJson
                            import json
                            result_json = task_data.get("resultJson", "{}")
                            try:
                                result = json.loads(result_json)
                                result_urls = result.get("resultUrls", [])
                                if result_urls:
                                    return {
                                        "success": True,
                                        "image_url": result_urls[0],
                                        "all_urls": result_urls,
                                        "task_id": task_id,
                                        "cost_time_ms": task_data.get("costTime")
                                    }
                                else:
                                    return {
                                        "success": False,
                                        "error": "No result URLs in response",
                                        "image_url": None,
                                        "task_id": task_id
                                    }
                            except json.JSONDecodeError as e:
                                return {
                                    "success": False,
                                    "error": f"Failed to parse resultJson: {e}",
                                    "image_url": None,
                                    "task_id": task_id
                                }

                        elif state == "fail":
                            fail_msg = task_data.get("failMsg", "Unknown error")
                            fail_code = task_data.get("failCode", "")
                            return {
                                "success": False,
                                "error": f"{fail_code}: {fail_msg}",
                                "image_url": None,
                                "task_id": task_id
                            }

                        # Still waiting, continue polling
                        await asyncio.sleep(poll_interval)
                        # Increase poll interval up to 5 seconds
                        poll_interval = min(poll_interval + 1, 5)

                except asyncio.TimeoutError:
                    logger.warning(f"Timeout polling task {task_id}, retrying...")
                    await asyncio.sleep(poll_interval)
                except Exception as e:
                    logger.error(f"Error polling task {task_id}: {e}")
                    await asyncio.sleep(poll_interval)


async def generate_image_prompt_from_post(post_content: str) -> str:
    """
    Generate an optimized Nano Banana Pro prompt using Claude.

    Uses LLM to analyze post content and create a structured prompt
    following Nano Banana Pro best practices:
    - Subject: Who/what in the image
    - Composition: Camera angles and framing
    - Action: What's occurring
    - Setting/Location: Scene context
    - Style: Art direction
    - Lighting: Specific lighting details

    Args:
        post_content: The text content of the post

    Returns:
        An optimized prompt string for Nano Banana Pro
    """
    clean_content = post_content.strip()[:500]

    # Use Claude to generate an optimized image prompt
    if ANTHROPIC_API_KEY:
        try:
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

            system_prompt = """You are an expert at creating image generation prompts for Nano Banana Pro.

Your task is to analyze social media post content and create an optimized image prompt that will generate an engaging, scroll-stopping visual for Twitter/X.

Follow this structure for the prompt:
1. SUBJECT: The main focus of the image (person, object, concept visualization)
2. COMPOSITION: Camera angle and framing (close-up, wide shot, low angle, bird's eye view)
3. ACTION/SCENE: What's happening or the mood being conveyed
4. SETTING: Environment or background context
5. STYLE: Art direction (photorealistic, cinematic, editorial, abstract, 3D render)
6. LIGHTING: Specific lighting (soft studio lighting, golden hour, dramatic spotlight, neon glow)
7. MOOD/COLORS: Color palette and emotional tone

Important rules:
- NO text or words in the image (the post text will be separate)
- Create visually striking, high-contrast compositions
- Use specific, descriptive language
- Aim for professional, modern aesthetics suitable for Twitter/X
- Keep the prompt under 200 words
- Output ONLY the image prompt, no explanations"""

            user_message = f"""Create a Nano Banana Pro image prompt for this social media post:

"{clean_content}"

Generate a single, cohesive prompt that will create an engaging visual to accompany this post."""

            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=300,
                messages=[
                    {"role": "user", "content": user_message}
                ],
                system=system_prompt
            )

            generated_prompt = response.content[0].text.strip()
            logger.info(f"LLM generated prompt: {generated_prompt[:100]}...")
            return generated_prompt

        except Exception as e:
            logger.error(f"Failed to generate prompt with LLM: {e}")
            # Fall back to basic prompt

    # Fallback: Basic prompt structure if LLM fails
    logger.warning("Using fallback prompt generation (no LLM)")
    return f"""Photorealistic, modern social media visual. Subject: Abstract conceptual representation of the topic "{clean_content[:100]}". Composition: Dynamic angle, rule of thirds. Style: Clean, minimalist with bold colors. Lighting: Soft studio lighting with subtle shadows. Mood: Professional yet engaging, high contrast. No text overlays."""


# Singleton instance for easy access
_service_instance: Optional[KIEImageService] = None


def get_kie_service() -> KIEImageService:
    """Get or create the KIE service singleton"""
    global _service_instance
    if _service_instance is None:
        _service_instance = KIEImageService()
    return _service_instance


async def generate_ai_image_for_post(
    post_content: str,
    aspect_ratio: str = "1:1"
) -> Dict[str, Any]:
    """
    Convenience function to generate an AI image for a post.

    Uses Claude to create an optimized Nano Banana Pro prompt,
    then generates the image via KIE API.

    Args:
        post_content: The post text to generate an image for
        aspect_ratio: Desired aspect ratio (default 1:1 for Twitter)

    Returns:
        Dict with success, image_url, error, task_id, prompt
    """
    service = get_kie_service()

    logger.info(f"Generating AI image for post: {post_content[:50]}...")

    # Generate optimized prompt using LLM
    prompt = await generate_image_prompt_from_post(post_content)
    logger.info(f"Generated Nano Banana Pro prompt: {prompt[:150]}...")

    result = await service.generate_image(
        prompt=prompt,
        aspect_ratio=aspect_ratio
    )

    # Include the generated prompt in the result for transparency
    result["prompt"] = prompt
    return result
