"""
Nano Banana Pro API Client (Kie.ai)

Async client for AI image generation using Nano Banana Pro.
Handles task creation, polling for results, and error handling.

API Docs: https://kie.ai/docs
"""

import asyncio
import logging
import os
from typing import Optional, List, Dict, Any
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)


class NanoBananaClient:
    """
    Client for Nano Banana Pro image generation API.

    Nano Banana Pro is an AI image generation model available via Kie.ai.
    It supports:
    - Text-to-image generation
    - Image inputs (up to 8) for style/subject reference
    - Various aspect ratios and resolutions
    """

    BASE_URL = "https://api.kie.ai/api/v1/jobs"
    MODEL_NAME = "nano-banana-pro"

    # Aspect ratio options
    ASPECT_RATIOS = ["1:1", "16:9", "9:16", "4:3", "3:4", "4:5", "5:4", "21:9", "9:21"]
    RESOLUTIONS = ["1k", "2k"]

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the Nano Banana Pro client.

        Args:
            api_key: Kie.ai API key. Falls back to KIE_API_KEY env var.
        """
        self.api_key = api_key or os.getenv("KIE_API_KEY")
        if not self.api_key:
            raise ValueError(
                "KIE_API_KEY not provided. Set KIE_API_KEY environment variable "
                "or pass api_key parameter."
            )

        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(60.0, connect=10.0),
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    # =========================================================================
    # Task Creation
    # =========================================================================

    async def create_task(
        self,
        prompt: str,
        image_inputs: Optional[List[str]] = None,
        aspect_ratio: str = "1:1",
        resolution: str = "1k",
    ) -> Dict[str, Any]:
        """
        Create an image generation task.

        Args:
            prompt: Text description of the image to generate
            image_inputs: List of image URLs to use as references (max 8)
            aspect_ratio: Output aspect ratio (1:1, 16:9, 9:16, 4:3, 3:4, 4:5, 5:4, 21:9, 9:21)
            resolution: Output resolution (1k or 2k)

        Returns:
            Dict with taskId and status

        Raises:
            ValueError: If parameters are invalid
            httpx.HTTPError: If API request fails
        """
        # Validate parameters
        if aspect_ratio not in self.ASPECT_RATIOS:
            raise ValueError(
                f"Invalid aspect_ratio '{aspect_ratio}'. "
                f"Must be one of: {self.ASPECT_RATIOS}"
            )

        if resolution not in self.RESOLUTIONS:
            raise ValueError(
                f"Invalid resolution '{resolution}'. Must be one of: {self.RESOLUTIONS}"
            )

        if image_inputs and len(image_inputs) > 8:
            raise ValueError("Maximum 8 image inputs allowed")

        # Build request payload
        payload = {
            "model": self.MODEL_NAME,
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
        }

        if image_inputs:
            payload["image_input"] = image_inputs

        logger.info(f"Creating Nano Banana task: {prompt[:50]}...")

        # Make request
        client = await self._get_client()
        response = await client.post("/createTask", json=payload)
        response.raise_for_status()

        result = response.json()
        logger.info(f"Task created: {result.get('taskId')}")

        return result

    # =========================================================================
    # Result Fetching
    # =========================================================================

    async def get_task_result(self, task_id: str) -> Dict[str, Any]:
        """
        Get the result of a generation task.

        Args:
            task_id: The task ID from create_task

        Returns:
            Dict with task status and result (if complete)
            - status: "pending", "processing", "completed", "failed"
            - result: URL to generated image (when completed)
        """
        client = await self._get_client()
        response = await client.get(f"/getTaskResult/{task_id}")
        response.raise_for_status()

        return response.json()

    async def get_task_results_batch(
        self, task_ids: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get results for multiple tasks at once.

        Args:
            task_ids: List of task IDs to check

        Returns:
            Dict mapping task_id to result
        """
        if not task_ids:
            return {}

        client = await self._get_client()
        response = await client.post(
            "/getTaskResultBatch",
            json={"taskIds": task_ids},
        )
        response.raise_for_status()

        results = response.json()

        # Convert list to dict by taskId
        return {r["taskId"]: r for r in results.get("results", [])}

    # =========================================================================
    # High-Level Methods
    # =========================================================================

    async def generate_and_wait(
        self,
        prompt: str,
        image_inputs: Optional[List[str]] = None,
        aspect_ratio: str = "1:1",
        resolution: str = "1k",
        max_wait_seconds: int = 120,
        poll_interval: float = 3.0,
    ) -> Dict[str, Any]:
        """
        Create a task and wait for completion.

        This is a convenience method that handles the full workflow:
        1. Create the task
        2. Poll for results
        3. Return the completed result or raise on failure

        Args:
            prompt: Text description of the image
            image_inputs: Optional reference images
            aspect_ratio: Output aspect ratio
            resolution: Output resolution
            max_wait_seconds: Maximum time to wait for completion
            poll_interval: Seconds between status checks

        Returns:
            Dict with completed task result including image URL

        Raises:
            TimeoutError: If task doesn't complete in time
            RuntimeError: If task fails
        """
        # Create the task
        create_result = await self.create_task(
            prompt=prompt,
            image_inputs=image_inputs,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
        )

        task_id = create_result.get("taskId")
        if not task_id:
            raise RuntimeError(f"No taskId in response: {create_result}")

        # Poll for completion
        start_time = datetime.utcnow()
        while True:
            elapsed = (datetime.utcnow() - start_time).total_seconds()
            if elapsed > max_wait_seconds:
                raise TimeoutError(
                    f"Task {task_id} did not complete within {max_wait_seconds}s"
                )

            result = await self.get_task_result(task_id)
            status = result.get("status", "").lower()

            if status == "completed":
                logger.info(f"Task {task_id} completed in {elapsed:.1f}s")
                return result

            if status == "failed":
                error_msg = result.get("error", "Unknown error")
                raise RuntimeError(f"Task {task_id} failed: {error_msg}")

            logger.debug(f"Task {task_id} status: {status}, waiting...")
            await asyncio.sleep(poll_interval)

    async def generate_ad_image(
        self,
        headline: str,
        description: str,
        business_name: str,
        product_images: Optional[List[str]] = None,
        logo_url: Optional[str] = None,
        style: str = "modern, professional",
        aspect_ratio: str = "1:1",
    ) -> Dict[str, Any]:
        """
        Generate an ad image with business context.

        This is a high-level method that crafts a good prompt for ad generation.

        Args:
            headline: Ad headline text
            description: Ad description or offer
            business_name: Name of the business
            product_images: Optional product image URLs to include
            logo_url: Optional logo URL to include
            style: Visual style descriptor
            aspect_ratio: Output aspect ratio

        Returns:
            Generated image result with URL
        """
        # Craft a prompt optimized for ad generation
        prompt = f"""Create a professional advertisement image for {business_name}.

Headline: {headline}
Offer/Description: {description}

Style: {style}
The image should be eye-catching, professional, and suitable for social media advertising.
Include clear visual hierarchy with the main offer being prominent.
Use vibrant, engaging colors that attract attention."""

        # Collect image inputs
        image_inputs = []
        if logo_url:
            image_inputs.append(logo_url)
        if product_images:
            image_inputs.extend(product_images[:7])  # Leave room for logo

        return await self.generate_and_wait(
            prompt=prompt,
            image_inputs=image_inputs if image_inputs else None,
            aspect_ratio=aspect_ratio,
            resolution="1k",
        )


# =============================================================================
# Convenience Functions
# =============================================================================


def get_nano_banana_client(api_key: Optional[str] = None) -> NanoBananaClient:
    """Get a Nano Banana Pro client instance."""
    return NanoBananaClient(api_key)


def is_nano_banana_configured() -> bool:
    """Check if Nano Banana Pro API is configured."""
    return bool(os.getenv("KIE_API_KEY"))
