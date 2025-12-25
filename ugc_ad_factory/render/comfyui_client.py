"""
ComfyUI Client - Interface to ComfyUI API for image generation.

Supports:
- Text-to-image: ZImage Turbo for fast generation
- Image-to-image (img2img): For perspective generation from source images

For the perspective-based pipeline, img2img uses IP-Adapter or similar
conditioning to transform source product images into new perspectives.
"""

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any

import aiohttp

from ..config import settings


class ComfyUIClient:
    """
    Client for ComfyUI API - handles image generation with ZImage Turbo.

    ComfyUI uses a workflow-based system where you submit a JSON workflow
    and it returns the generated images.
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
    ):
        self.host = host or settings.comfyui_host
        self.port = port or settings.comfyui_port
        self.base_url = f"http://{self.host}:{self.port}"
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def generate_image(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1080,
        height: int = 1920,
        style_preset: str = "default",
        seed: int | None = None,
    ) -> dict[str, Any]:
        """
        Generate an image using ComfyUI.

        Args:
            prompt: The positive prompt describing the image
            negative_prompt: Things to avoid in the image
            width: Output width in pixels (default 1080 for 9:16)
            height: Output height in pixels (default 1920 for 9:16)
            style_preset: Style preset name (loads different workflow)
            seed: Random seed for reproducibility (None = random)

        Returns:
            dict with:
                - success: bool
                - image_path: local path to generated image
                - prompt_id: ComfyUI prompt ID for tracking
                - error: error message if failed
        """
        try:
            # Build workflow
            workflow = self._build_workflow(
                prompt=prompt,
                negative_prompt=negative_prompt,
                width=width,
                height=height,
                seed=seed or self._random_seed(),
            )

            # Queue the prompt
            prompt_id = await self._queue_prompt(workflow)

            # Wait for completion
            result = await self._wait_for_completion(prompt_id)

            if result.get("success"):
                # Download the image
                image_path = await self._download_image(
                    result["filename"],
                    result.get("subfolder", ""),
                )
                return {
                    "success": True,
                    "image_path": str(image_path),
                    "prompt_id": prompt_id,
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "Unknown error"),
                    "prompt_id": prompt_id,
                }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    async def _queue_prompt(self, workflow: dict) -> str:
        """Queue a prompt and return the prompt ID."""
        session = await self._get_session()

        async with session.post(
            f"{self.base_url}/prompt",
            json={"prompt": workflow},
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"ComfyUI queue failed: {resp.status} - {text}")

            data = await resp.json()
            return data["prompt_id"]

    async def _wait_for_completion(
        self,
        prompt_id: str,
        timeout: int = 120,
        poll_interval: float = 1.0,
    ) -> dict:
        """
        Poll ComfyUI until the prompt is complete.

        Returns dict with success/failure and image info.
        """
        session = await self._get_session()
        start_time = asyncio.get_event_loop().time()

        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                return {"success": False, "error": f"Timeout after {timeout}s"}

            # Check history for completion
            async with session.get(f"{self.base_url}/history/{prompt_id}") as resp:
                if resp.status == 200:
                    history = await resp.json()

                    if prompt_id in history:
                        prompt_data = history[prompt_id]

                        # Check for errors
                        if prompt_data.get("status", {}).get("status_str") == "error":
                            return {
                                "success": False,
                                "error": prompt_data.get("status", {}).get("messages", "Unknown error"),
                            }

                        # Check for outputs
                        outputs = prompt_data.get("outputs", {})
                        for node_id, node_output in outputs.items():
                            if "images" in node_output:
                                image = node_output["images"][0]
                                return {
                                    "success": True,
                                    "filename": image["filename"],
                                    "subfolder": image.get("subfolder", ""),
                                    "type": image.get("type", "output"),
                                }

            await asyncio.sleep(poll_interval)

    async def _download_image(
        self,
        filename: str,
        subfolder: str = "",
    ) -> Path:
        """Download generated image from ComfyUI output folder."""
        session = await self._get_session()

        params = {"filename": filename, "subfolder": subfolder, "type": "output"}
        async with session.get(f"{self.base_url}/view", params=params) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Failed to download image: {resp.status}")

            # Save to temp directory
            output_dir = Path("/tmp/ugc_comfyui_output")
            output_dir.mkdir(parents=True, exist_ok=True)

            output_path = output_dir / filename
            with open(output_path, "wb") as f:
                f.write(await resp.read())

            return output_path

    def _build_workflow(
        self,
        prompt: str,
        negative_prompt: str,
        width: int,
        height: int,
        seed: int,
    ) -> dict:
        """
        Build ComfyUI workflow JSON for ZImage Turbo.

        ZImage Turbo uses a different architecture than SDXL:
        - Separate UNETLoader, CLIPLoader, VAELoader
        - EmptySD3LatentImage (not EmptyLatentImage)
        - ModelSamplingAuraFlow for proper sampling
        - 9 steps, cfg=1, res_multistep sampler
        """
        workflow = {
            # CLIP Loader - Qwen text encoder
            "39": {
                "class_type": "CLIPLoader",
                "inputs": {
                    "clip_name": "qwen_3_4b.safetensors",
                    "type": "lumina2",
                    "device": "default",
                },
            },
            # VAE Loader
            "40": {
                "class_type": "VAELoader",
                "inputs": {
                    "vae_name": "ae.safetensors",
                },
            },
            # Empty SD3 Latent Image
            "41": {
                "class_type": "EmptySD3LatentImage",
                "inputs": {
                    "width": width,
                    "height": height,
                    "batch_size": 1,
                },
            },
            # Conditioning Zero Out (for negative)
            "42": {
                "class_type": "ConditioningZeroOut",
                "inputs": {
                    "conditioning": ["45", 0],
                },
            },
            # UNET Loader - ZImage Turbo model
            "46": {
                "class_type": "UNETLoader",
                "inputs": {
                    "unet_name": "z_image_turbo_bf16.safetensors",
                    "weight_dtype": "default",
                },
            },
            # CLIP Text Encode (prompt)
            "45": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": prompt,
                    "clip": ["39", 0],
                },
            },
            # Model Sampling AuraFlow
            "47": {
                "class_type": "ModelSamplingAuraFlow",
                "inputs": {
                    "model": ["46", 0],
                    "shift": 3.0,
                },
            },
            # KSampler
            "44": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": seed,
                    "steps": 9,
                    "cfg": 1.0,
                    "sampler_name": "res_multistep",
                    "scheduler": "simple",
                    "denoise": 1.0,
                    "model": ["47", 0],
                    "positive": ["45", 0],
                    "negative": ["42", 0],
                    "latent_image": ["41", 0],
                },
            },
            # VAE Decode
            "43": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["44", 0],
                    "vae": ["40", 0],
                },
            },
            # Save Image
            "9": {
                "class_type": "SaveImage",
                "inputs": {
                    "filename_prefix": "ugc_output",
                    "images": ["43", 0],
                },
            },
        }

        return workflow

    def _random_seed(self) -> int:
        """Generate a random seed."""
        import random
        return random.randint(0, 2**32 - 1)

    async def check_health(self) -> bool:
        """Check if ComfyUI is running and accessible."""
        try:
            session = await self._get_session()
            async with session.get(f"{self.base_url}/system_stats", timeout=5) as resp:
                return resp.status == 200
        except Exception:
            return False

    async def generate_perspective(
        self,
        source_image_path: str,
        perspective_prompt: str,
        negative_prompt: str = "",
        width: int = 1080,
        height: int = 1920,
        denoise_strength: float = 0.5,
        seed: int | None = None,
    ) -> dict[str, Any]:
        """
        Generate a new perspective from a source image using img2img.

        This is the core method for the perspective-based pipeline.
        It takes a source product image and transforms it according to
        the perspective prompt while maintaining product identity.

        Args:
            source_image_path: Local path to source image
            perspective_prompt: Description of the new perspective
            negative_prompt: Things to avoid
            width: Output width
            height: Output height
            denoise_strength: How much to change (0.3-0.7 recommended)
            seed: Random seed

        Returns:
            dict with success, image_path, error
        """
        try:
            # First, upload the source image to ComfyUI
            image_name = await self._upload_image(source_image_path)

            # Build img2img workflow
            workflow = self._build_img2img_workflow(
                image_name=image_name,
                prompt=perspective_prompt,
                negative_prompt=negative_prompt,
                width=width,
                height=height,
                denoise=denoise_strength,
                seed=seed or self._random_seed(),
            )

            # Queue the prompt
            prompt_id = await self._queue_prompt(workflow)

            # Wait for completion
            result = await self._wait_for_completion(prompt_id)

            if result.get("success"):
                image_path = await self._download_image(
                    result["filename"],
                    result.get("subfolder", ""),
                )
                return {
                    "success": True,
                    "image_path": str(image_path),
                    "prompt_id": prompt_id,
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "Unknown error"),
                    "prompt_id": prompt_id,
                }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    async def _upload_image(self, image_path: str) -> str:
        """Upload an image to ComfyUI and return the filename."""
        session = await self._get_session()

        with open(image_path, "rb") as f:
            image_data = f.read()

        # Determine filename
        filename = Path(image_path).name

        # Create form data
        form = aiohttp.FormData()
        form.add_field(
            "image",
            image_data,
            filename=filename,
            content_type="image/png",
        )

        async with session.post(
            f"{self.base_url}/upload/image",
            data=form,
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"Image upload failed: {resp.status} - {text}")

            data = await resp.json()
            return data.get("name", filename)

    def _build_img2img_workflow(
        self,
        image_name: str,
        prompt: str,
        negative_prompt: str,
        width: int,
        height: int,
        denoise: float,
        seed: int,
    ) -> dict:
        """
        Build ComfyUI workflow for img2img using ZImage Turbo.

        Uses the source image as latent conditioning with adjustable denoise.
        Lower denoise = closer to original, higher = more creative freedom.
        """
        workflow = {
            # Load the source image
            "10": {
                "class_type": "LoadImage",
                "inputs": {
                    "image": image_name,
                },
            },
            # Resize to target dimensions
            "11": {
                "class_type": "ImageScale",
                "inputs": {
                    "image": ["10", 0],
                    "width": width,
                    "height": height,
                    "upscale_method": "lanczos",
                    "crop": "center",
                },
            },
            # CLIP Loader - Qwen text encoder
            "39": {
                "class_type": "CLIPLoader",
                "inputs": {
                    "clip_name": "qwen_3_4b.safetensors",
                    "type": "lumina2",
                    "device": "default",
                },
            },
            # VAE Loader
            "40": {
                "class_type": "VAELoader",
                "inputs": {
                    "vae_name": "ae.safetensors",
                },
            },
            # Encode source image to latent
            "12": {
                "class_type": "VAEEncode",
                "inputs": {
                    "pixels": ["11", 0],
                    "vae": ["40", 0],
                },
            },
            # Conditioning Zero Out (for negative)
            "42": {
                "class_type": "ConditioningZeroOut",
                "inputs": {
                    "conditioning": ["45", 0],
                },
            },
            # UNET Loader - ZImage Turbo model
            "46": {
                "class_type": "UNETLoader",
                "inputs": {
                    "unet_name": "z_image_turbo_bf16.safetensors",
                    "weight_dtype": "default",
                },
            },
            # CLIP Text Encode (prompt)
            "45": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": prompt,
                    "clip": ["39", 0],
                },
            },
            # Model Sampling AuraFlow
            "47": {
                "class_type": "ModelSamplingAuraFlow",
                "inputs": {
                    "model": ["46", 0],
                    "shift": 3.0,
                },
            },
            # KSampler with source latent and denoise
            "44": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": seed,
                    "steps": 9,
                    "cfg": 1.0,
                    "sampler_name": "res_multistep",
                    "scheduler": "simple",
                    "denoise": denoise,  # Key difference from txt2img
                    "model": ["47", 0],
                    "positive": ["45", 0],
                    "negative": ["42", 0],
                    "latent_image": ["12", 0],  # Use encoded source image
                },
            },
            # VAE Decode
            "43": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["44", 0],
                    "vae": ["40", 0],
                },
            },
            # Save Image
            "9": {
                "class_type": "SaveImage",
                "inputs": {
                    "filename_prefix": "ugc_perspective",
                    "images": ["43", 0],
                },
            },
        }

        return workflow
