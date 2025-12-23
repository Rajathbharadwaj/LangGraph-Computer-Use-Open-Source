"""
KeyAI Sora 2 Pro Client - Image-to-Video generation API.

Uses the KeyAI (kie.ai) API to convert still images into 10-15 second video clips.
"""

import asyncio
from datetime import datetime
from typing import Any, Literal

import aiohttp

from ..config import settings


class KeyAISora2Client:
    """
    Client for KeyAI Sora 2 Pro Image-to-Video API.

    API Documentation: https://api.kie.ai/api/v1

    Workflow:
    1. Create a generation task with POST /jobs/createTask
    2. Poll task status with GET /jobs/recordInfo?taskId=xxx
    3. Get video URL from resultJson.resultUrls when complete
    """

    API_URL = "https://api.kie.ai/api/v1"
    MODEL_NAME = "sora-2-pro-image-to-video"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.keyai_api_key
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session with auth headers."""
        if self._session is None or self._session.closed:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    async def close(self):
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def create_video_task(
        self,
        image_url: str,
        prompt: str,
        duration: Literal["10", "15"] = "10",
        aspect_ratio: Literal["portrait", "landscape"] = "portrait",
        size: Literal["standard", "high"] = "high",
        remove_watermark: bool = True,
        callback_url: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a video generation task.

        Args:
            image_url: Public URL of the source image (must be accessible)
            prompt: Motion/animation prompt describing desired video motion
            duration: Video length - "10" for 10s or "15" for 15s
            aspect_ratio: "portrait" (9:16) or "landscape" (16:9)
            size: "standard" or "high" quality
            remove_watermark: Remove Sora watermark from output
            callback_url: Optional webhook URL for completion notification

        Returns:
            dict with:
                - success: bool
                - task_id: KeyAI task ID for polling
                - error: error message if failed
        """
        try:
            session = await self._get_session()

            payload = {
                "model": self.MODEL_NAME,
                "input": {
                    "prompt": prompt,
                    "image_urls": [image_url],
                    "aspect_ratio": aspect_ratio,
                    "n_frames": duration,
                    "size": size,
                    "remove_watermark": remove_watermark,
                },
            }

            if callback_url:
                payload["callBackUrl"] = callback_url

            async with session.post(
                f"{self.API_URL}/jobs/createTask",
                json=payload,
            ) as resp:
                data = await resp.json()

                if resp.status != 200 or data.get("code") != 200:
                    return {
                        "success": False,
                        "error": data.get("msg", f"API error: {resp.status}"),
                    }

                return {
                    "success": True,
                    "task_id": data["data"]["taskId"],
                }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    async def get_task_status(self, task_id: str) -> dict[str, Any]:
        """
        Get the status of a video generation task.

        Args:
            task_id: The task ID from create_video_task

        Returns:
            dict with:
                - state: "waiting" | "success" | "fail"
                - video_url: URL of generated video (if success)
                - error: error message (if fail)
                - cost_time: generation time in ms (if success)
        """
        try:
            session = await self._get_session()

            async with session.get(
                f"{self.API_URL}/jobs/recordInfo",
                params={"taskId": task_id},
            ) as resp:
                data = await resp.json()

                if resp.status != 200 or data.get("code") != 200:
                    return {
                        "state": "fail",
                        "error": data.get("msg", f"API error: {resp.status}"),
                    }

                task_data = data["data"]
                state = task_data.get("state", "waiting")

                result: dict[str, Any] = {
                    "state": state,
                    "task_id": task_id,
                    "model": task_data.get("model"),
                    "created_at": task_data.get("createTime"),
                }

                if state == "success":
                    # Parse resultJson to get video URL
                    result_json = task_data.get("resultJson", "{}")
                    if isinstance(result_json, str):
                        import json
                        result_json = json.loads(result_json)

                    result_urls = result_json.get("resultUrls", [])
                    if result_urls:
                        result["video_url"] = result_urls[0]

                    result["cost_time"] = task_data.get("costTime")
                    result["completed_at"] = task_data.get("completeTime")

                elif state == "fail":
                    result["error"] = task_data.get("failMsg", "Unknown error")
                    result["error_code"] = task_data.get("failCode")

                return result

        except Exception as e:
            return {
                "state": "fail",
                "error": str(e),
            }

    async def poll_until_complete(
        self,
        task_id: str,
        timeout: int | None = None,
        poll_interval: float = 5.0,
    ) -> dict[str, Any]:
        """
        Poll task status until completion or timeout.

        Args:
            task_id: The task ID to poll
            timeout: Maximum seconds to wait (default from settings)
            poll_interval: Seconds between polls

        Returns:
            Final task status dict with video_url if successful
        """
        timeout = timeout or settings.keyai_timeout
        start_time = datetime.utcnow()

        while True:
            elapsed = (datetime.utcnow() - start_time).total_seconds()
            if elapsed > timeout:
                return {
                    "state": "fail",
                    "error": f"Timeout after {timeout}s",
                    "task_id": task_id,
                }

            status = await self.get_task_status(task_id)

            if status["state"] in ("success", "fail"):
                return status

            # Still waiting, sleep and retry
            await asyncio.sleep(poll_interval)

    async def generate_video(
        self,
        image_url: str,
        prompt: str,
        duration: Literal["10", "15"] = "10",
        aspect_ratio: Literal["portrait", "landscape"] = "portrait",
        size: Literal["standard", "high"] = "high",
        remove_watermark: bool = True,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """
        High-level method: Create task and wait for completion.

        Combines create_video_task and poll_until_complete.

        Args:
            image_url: Public URL of the source image
            prompt: Motion/animation prompt
            duration: "10" or "15" seconds
            aspect_ratio: "portrait" or "landscape"
            size: "standard" or "high"
            remove_watermark: Remove watermark
            timeout: Max seconds to wait

        Returns:
            dict with:
                - success: bool
                - video_url: URL of generated video (if success)
                - task_id: KeyAI task ID
                - cost_time: generation time in ms
                - error: error message (if failed)
        """
        # Create task
        create_result = await self.create_video_task(
            image_url=image_url,
            prompt=prompt,
            duration=duration,
            aspect_ratio=aspect_ratio,
            size=size,
            remove_watermark=remove_watermark,
        )

        if not create_result.get("success"):
            return create_result

        task_id = create_result["task_id"]

        # Poll until complete
        status = await self.poll_until_complete(
            task_id=task_id,
            timeout=timeout,
        )

        if status["state"] == "success":
            return {
                "success": True,
                "video_url": status.get("video_url"),
                "task_id": task_id,
                "cost_time": status.get("cost_time"),
            }
        else:
            return {
                "success": False,
                "task_id": task_id,
                "error": status.get("error", "Generation failed"),
            }

    async def create_video_from_frames(
        self,
        start_image_url: str,
        end_image_url: str,
        motion_prompt: str = "",
        duration: Literal["5", "10"] = "5",
        aspect_ratio: Literal["portrait", "landscape"] = "portrait",
        size: Literal["standard", "high"] = "high",
        remove_watermark: bool = True,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """
        Generate video from start and end frames (key frame interpolation).

        This is the core method for the perspective-based pipeline transitions.
        Uses two images as keyframes and generates smooth motion between them.

        Args:
            start_image_url: Public URL of the start frame
            end_image_url: Public URL of the end frame
            motion_prompt: Description of the motion (optional)
            duration: Video length - "5" for ~5s or "10" for ~10s
            aspect_ratio: "portrait" (9:16) or "landscape" (16:9)
            size: "standard" or "high" quality
            remove_watermark: Remove watermark from output
            timeout: Max seconds to wait for completion

        Returns:
            dict with:
                - success: bool
                - video_url: URL of generated video (if success)
                - task_id: KeyAI task ID
                - error: error message (if failed)
        """
        try:
            session = await self._get_session()

            # Build prompt for frame interpolation
            full_prompt = motion_prompt or "smooth camera motion, seamless transition"

            # KeyAI supports multiple images for keyframe-based generation
            payload = {
                "model": self.MODEL_NAME,
                "input": {
                    "prompt": full_prompt,
                    "image_urls": [start_image_url, end_image_url],
                    "aspect_ratio": aspect_ratio,
                    "n_frames": duration,
                    "size": size,
                    "remove_watermark": remove_watermark,
                },
            }

            async with session.post(
                f"{self.API_URL}/jobs/createTask",
                json=payload,
            ) as resp:
                data = await resp.json()

                if resp.status != 200 or data.get("code") != 200:
                    return {
                        "success": False,
                        "error": data.get("msg", f"API error: {resp.status}"),
                    }

                task_id = data["data"]["taskId"]

            # Poll until complete
            status = await self.poll_until_complete(
                task_id=task_id,
                timeout=timeout,
            )

            if status["state"] == "success":
                return {
                    "success": True,
                    "video_url": status.get("video_url"),
                    "task_id": task_id,
                    "cost_time": status.get("cost_time"),
                }
            else:
                return {
                    "success": False,
                    "task_id": task_id,
                    "error": status.get("error", "Generation failed"),
                }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    async def check_health(self) -> bool:
        """Check if API key is valid by making a simple request."""
        try:
            session = await self._get_session()
            # Try to get status of a non-existent task - will return 200 with error data
            async with session.get(
                f"{self.API_URL}/jobs/recordInfo",
                params={"taskId": "health_check_test"},
                timeout=10,
            ) as resp:
                # Any 200 response means the API is reachable and key is valid
                return resp.status == 200
        except Exception:
            return False
