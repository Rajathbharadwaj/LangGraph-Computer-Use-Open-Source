"""
Image Generation Service

High-level service for AI image generation using Nano Banana Pro.
Handles database tracking, asset management, and campaign linking.
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from sqlalchemy.orm import Session

from database.database import SessionLocal
from database.models import UserAsset, ImageGenerationJob, AdsCampaign
from ..clients.nano_banana import NanoBananaClient, get_nano_banana_client

logger = logging.getLogger(__name__)


class ImageGenerationService:
    """
    Service for generating and managing AI-generated ad images.

    Wraps the NanoBananaClient with database tracking and asset management.
    """

    def __init__(self, db: Optional[Session] = None, api_key: Optional[str] = None):
        """
        Initialize the image generation service.

        Args:
            db: Optional database session (creates one if not provided)
            api_key: Optional Kie.ai API key (uses env var if not provided)
        """
        self._db = db
        self._client: Optional[NanoBananaClient] = None
        self._api_key = api_key

    def _get_db(self) -> Session:
        """Get or create database session."""
        if self._db:
            return self._db
        return SessionLocal()

    def _close_db(self, db: Session):
        """Close database session if we created it."""
        if not self._db:
            db.close()

    def _get_client(self) -> NanoBananaClient:
        """Get or create the Nano Banana client."""
        if self._client is None:
            self._client = get_nano_banana_client(self._api_key)
        return self._client

    async def close(self):
        """Close the client connection."""
        if self._client:
            await self._client.close()
            self._client = None

    # =========================================================================
    # Asset Management
    # =========================================================================

    def create_asset(
        self,
        user_id: str,
        name: str,
        file_url: str,
        asset_type: str = "other",
        description: Optional[str] = None,
        thumbnail_url: Optional[str] = None,
        file_size_bytes: Optional[int] = None,
        mime_type: Optional[str] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
    ) -> UserAsset:
        """
        Create a new user asset record.

        Args:
            user_id: Clerk user ID
            name: Asset display name
            file_url: URL to the uploaded file
            asset_type: Type of asset (logo, product, background, other)
            description: Optional description
            thumbnail_url: Optional thumbnail URL
            file_size_bytes: File size in bytes
            mime_type: MIME type (image/png, image/jpeg)
            width: Image width in pixels
            height: Image height in pixels

        Returns:
            Created UserAsset record
        """
        db = self._get_db()
        try:
            asset = UserAsset(
                user_id=user_id,
                name=name,
                asset_type=asset_type,
                description=description,
                file_url=file_url,
                thumbnail_url=thumbnail_url,
                file_size_bytes=file_size_bytes,
                mime_type=mime_type,
                width=width,
                height=height,
            )
            db.add(asset)
            db.commit()
            db.refresh(asset)

            logger.info(f"Created asset {asset.id} ({asset.name}) for user {user_id}")
            return asset

        finally:
            self._close_db(db)

    def get_user_assets(
        self,
        user_id: str,
        asset_type: Optional[str] = None,
        active_only: bool = True,
    ) -> List[UserAsset]:
        """
        Get all assets for a user.

        Args:
            user_id: Clerk user ID
            asset_type: Optional filter by type
            active_only: Only return active assets

        Returns:
            List of UserAsset records
        """
        db = self._get_db()
        try:
            query = db.query(UserAsset).filter(UserAsset.user_id == user_id)

            if asset_type:
                query = query.filter(UserAsset.asset_type == asset_type)

            if active_only:
                query = query.filter(UserAsset.is_active == True)

            return query.order_by(UserAsset.created_at.desc()).all()

        finally:
            self._close_db(db)

    def get_asset_by_id(self, asset_id: int, user_id: str) -> Optional[UserAsset]:
        """Get a specific asset by ID (with user verification)."""
        db = self._get_db()
        try:
            return (
                db.query(UserAsset)
                .filter(UserAsset.id == asset_id, UserAsset.user_id == user_id)
                .first()
            )
        finally:
            self._close_db(db)

    def delete_asset(self, asset_id: int, user_id: str) -> bool:
        """
        Soft-delete an asset (mark as inactive).

        Args:
            asset_id: Asset ID to delete
            user_id: User ID for verification

        Returns:
            True if deleted, False if not found
        """
        db = self._get_db()
        try:
            asset = (
                db.query(UserAsset)
                .filter(UserAsset.id == asset_id, UserAsset.user_id == user_id)
                .first()
            )

            if not asset:
                return False

            asset.is_active = False
            db.commit()

            logger.info(f"Deleted asset {asset_id} for user {user_id}")
            return True

        finally:
            self._close_db(db)

    # =========================================================================
    # Image Generation
    # =========================================================================

    async def generate_image(
        self,
        user_id: str,
        prompt: str,
        asset_ids: Optional[List[int]] = None,
        aspect_ratio: str = "1:1",
        resolution: str = "1k",
        campaign_id: Optional[int] = None,
        wait_for_completion: bool = True,
    ) -> ImageGenerationJob:
        """
        Generate an image using Nano Banana Pro.

        Args:
            user_id: Clerk user ID
            prompt: Text prompt for generation
            asset_ids: Optional list of UserAsset IDs to use as inputs
            aspect_ratio: Output aspect ratio
            resolution: Output resolution (1k or 2k)
            campaign_id: Optional campaign to link to
            wait_for_completion: Whether to wait for the result

        Returns:
            ImageGenerationJob record
        """
        db = self._get_db()
        try:
            # Get image URLs from asset IDs
            image_inputs = []
            if asset_ids:
                assets = (
                    db.query(UserAsset)
                    .filter(
                        UserAsset.id.in_(asset_ids),
                        UserAsset.user_id == user_id,
                        UserAsset.is_active == True,
                    )
                    .all()
                )
                image_inputs = [a.file_url for a in assets]

            # Create the job record
            job = ImageGenerationJob(
                user_id=user_id,
                campaign_id=campaign_id,
                prompt=prompt,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                input_asset_ids=asset_ids or [],
                status="pending",
            )
            db.add(job)
            db.commit()
            db.refresh(job)

            logger.info(f"Created image generation job {job.id} for user {user_id}")

            # Call the API
            client = self._get_client()

            try:
                if wait_for_completion:
                    # Wait for full result
                    result = await client.generate_and_wait(
                        prompt=prompt,
                        image_inputs=image_inputs if image_inputs else None,
                        aspect_ratio=aspect_ratio,
                        resolution=resolution,
                    )

                    # Update job with result
                    job.external_task_id = result.get("taskId")
                    job.status = "completed"
                    job.result_url = result.get("result") or result.get("imageUrl")
                    job.completed_at = datetime.utcnow()

                    # Update campaign if linked
                    if campaign_id and job.result_url:
                        campaign = db.query(AdsCampaign).filter(
                            AdsCampaign.id == campaign_id
                        ).first()
                        if campaign:
                            campaign.media_url = job.result_url
                            logger.info(f"Updated campaign {campaign_id} with generated image")

                else:
                    # Just create the task, don't wait
                    create_result = await client.create_task(
                        prompt=prompt,
                        image_inputs=image_inputs if image_inputs else None,
                        aspect_ratio=aspect_ratio,
                        resolution=resolution,
                    )

                    job.external_task_id = create_result.get("taskId")
                    job.status = "processing"

                db.commit()
                db.refresh(job)

                logger.info(
                    f"Image generation job {job.id} completed: {job.status}"
                )
                return job

            except Exception as e:
                job.status = "failed"
                job.error_message = str(e)
                db.commit()
                logger.error(f"Image generation failed for job {job.id}: {e}")
                raise

        finally:
            self._close_db(db)

    async def check_job_status(self, job_id: int, user_id: str) -> Optional[ImageGenerationJob]:
        """
        Check and update the status of a generation job.

        Args:
            job_id: Job ID to check
            user_id: User ID for verification

        Returns:
            Updated ImageGenerationJob or None if not found
        """
        db = self._get_db()
        try:
            job = (
                db.query(ImageGenerationJob)
                .filter(
                    ImageGenerationJob.id == job_id,
                    ImageGenerationJob.user_id == user_id,
                )
                .first()
            )

            if not job:
                return None

            # If already completed/failed, just return
            if job.status in ["completed", "failed"]:
                return job

            # Check with the API
            if job.external_task_id:
                client = self._get_client()
                result = await client.get_task_result(job.external_task_id)

                status = result.get("status", "").lower()

                if status == "completed":
                    job.status = "completed"
                    job.result_url = result.get("result") or result.get("imageUrl")
                    job.completed_at = datetime.utcnow()

                    # Update campaign if linked
                    if job.campaign_id and job.result_url:
                        campaign = db.query(AdsCampaign).filter(
                            AdsCampaign.id == job.campaign_id
                        ).first()
                        if campaign:
                            campaign.media_url = job.result_url

                elif status == "failed":
                    job.status = "failed"
                    job.error_message = result.get("error", "Unknown error")

                else:
                    job.status = "processing"

                db.commit()
                db.refresh(job)

            return job

        finally:
            self._close_db(db)

    def get_user_jobs(
        self,
        user_id: str,
        limit: int = 20,
        status: Optional[str] = None,
    ) -> List[ImageGenerationJob]:
        """
        Get image generation jobs for a user.

        Args:
            user_id: Clerk user ID
            limit: Max results to return
            status: Optional filter by status

        Returns:
            List of ImageGenerationJob records
        """
        db = self._get_db()
        try:
            query = db.query(ImageGenerationJob).filter(
                ImageGenerationJob.user_id == user_id
            )

            if status:
                query = query.filter(ImageGenerationJob.status == status)

            return (
                query.order_by(ImageGenerationJob.created_at.desc())
                .limit(limit)
                .all()
            )

        finally:
            self._close_db(db)

    async def generate_ad_creative(
        self,
        user_id: str,
        headline: str,
        description: str,
        business_name: str,
        product_asset_ids: Optional[List[int]] = None,
        logo_asset_id: Optional[int] = None,
        style: str = "modern, professional",
        aspect_ratio: str = "1:1",
        campaign_id: Optional[int] = None,
    ) -> ImageGenerationJob:
        """
        Generate an ad creative with business context.

        This is a high-level method that crafts a good prompt for ad generation.

        Args:
            user_id: Clerk user ID
            headline: Ad headline
            description: Ad description/offer
            business_name: Name of the business
            product_asset_ids: Product image asset IDs
            logo_asset_id: Logo asset ID
            style: Visual style descriptor
            aspect_ratio: Output aspect ratio
            campaign_id: Optional campaign to link

        Returns:
            ImageGenerationJob record
        """
        # Craft the prompt
        prompt = f"""Create a professional advertisement image for {business_name}.

Headline: {headline}
Offer/Description: {description}

Style: {style}
The image should be eye-catching, professional, and suitable for social media advertising.
Include clear visual hierarchy with the main offer being prominent.
Use vibrant, engaging colors that attract attention."""

        # Collect asset IDs
        asset_ids = []
        if logo_asset_id:
            asset_ids.append(logo_asset_id)
        if product_asset_ids:
            asset_ids.extend(product_asset_ids[:7])  # Max 8 total

        return await self.generate_image(
            user_id=user_id,
            prompt=prompt,
            asset_ids=asset_ids if asset_ids else None,
            aspect_ratio=aspect_ratio,
            resolution="1k",
            campaign_id=campaign_id,
            wait_for_completion=True,
        )


# =============================================================================
# Convenience Functions
# =============================================================================


def get_image_generation_service(
    db: Optional[Session] = None,
    api_key: Optional[str] = None,
) -> ImageGenerationService:
    """Get an ImageGenerationService instance."""
    return ImageGenerationService(db, api_key)
