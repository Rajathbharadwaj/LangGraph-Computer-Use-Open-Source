"""
Google Cloud Storage client for asset management.

Handles uploading generated images and videos to GCS with public URLs.
"""

import asyncio
from pathlib import Path
from typing import Any
import uuid

from google.cloud import storage
from google.cloud.exceptions import GoogleCloudError

from ..config import settings


class GCSAssetStore:
    """
    Google Cloud Storage client for UGC assets.

    Uploads images and videos to GCS and returns public URLs.
    Uses a structured path: {user_id}/{job_id}/{asset_type}/{asset_id}
    """

    def __init__(
        self,
        bucket_name: str | None = None,
        project: str | None = None,
    ):
        self.bucket_name = bucket_name or settings.gcs_bucket
        self.project = project or settings.gcp_project
        self._client: storage.Client | None = None
        self._bucket: storage.Bucket | None = None

    def _get_client(self) -> storage.Client:
        """Lazily initialize GCS client."""
        if self._client is None:
            self._client = storage.Client(project=self.project)
        return self._client

    def _get_bucket(self) -> storage.Bucket:
        """Lazily initialize bucket reference."""
        if self._bucket is None:
            self._bucket = self._get_client().bucket(self.bucket_name)
        return self._bucket

    async def upload_image(
        self,
        local_path: str,
        job_id: str,
        user_id: str,
        asset_id: str,
    ) -> str:
        """
        Upload an image to GCS and return public URL.

        Args:
            local_path: Path to local image file
            job_id: Job ID for organization
            user_id: User ID for organization
            asset_id: Asset ID for naming

        Returns:
            Public URL of the uploaded image
        """
        # Determine file extension
        path = Path(local_path)
        ext = path.suffix or ".png"

        # Build blob path
        blob_path = f"ugc/{user_id}/{job_id}/images/{asset_id}{ext}"

        return await self._upload_file(local_path, blob_path, "image/png")

    async def upload_video(
        self,
        local_path: str,
        job_id: str,
        user_id: str,
        video_id: str,
    ) -> str:
        """
        Upload a video to GCS and return public URL.

        Args:
            local_path: Path to local video file
            job_id: Job ID for organization
            user_id: User ID for organization
            video_id: Video ID for naming

        Returns:
            Public URL of the uploaded video
        """
        path = Path(local_path)
        ext = path.suffix or ".mp4"

        blob_path = f"ugc/{user_id}/{job_id}/videos/{video_id}{ext}"

        return await self._upload_file(local_path, blob_path, "video/mp4")

    async def upload_thumbnail(
        self,
        local_path: str,
        job_id: str,
        user_id: str,
        video_id: str,
    ) -> str:
        """Upload a thumbnail image for a video."""
        path = Path(local_path)
        ext = path.suffix or ".jpg"

        blob_path = f"ugc/{user_id}/{job_id}/thumbnails/{video_id}{ext}"

        return await self._upload_file(local_path, blob_path, "image/jpeg")

    async def _upload_file(
        self,
        local_path: str,
        blob_path: str,
        content_type: str,
    ) -> str:
        """
        Upload a file to GCS.

        Uses run_in_executor since google-cloud-storage is synchronous.
        """
        loop = asyncio.get_event_loop()

        def _sync_upload():
            bucket = self._get_bucket()
            blob = bucket.blob(blob_path)

            blob.upload_from_filename(
                local_path,
                content_type=content_type,
            )

            # Make publicly accessible
            blob.make_public()

            return blob.public_url

        try:
            url = await loop.run_in_executor(None, _sync_upload)
            return url
        except GoogleCloudError as e:
            raise RuntimeError(f"GCS upload failed: {e}")

    async def download_file(
        self,
        blob_path: str,
        local_path: str,
    ) -> str:
        """Download a file from GCS."""
        loop = asyncio.get_event_loop()

        def _sync_download():
            bucket = self._get_bucket()
            blob = bucket.blob(blob_path)
            blob.download_to_filename(local_path)
            return local_path

        return await loop.run_in_executor(None, _sync_download)

    async def list_job_assets(
        self,
        user_id: str,
        job_id: str,
    ) -> dict[str, list[str]]:
        """List all assets for a job."""
        loop = asyncio.get_event_loop()

        def _sync_list():
            prefix = f"ugc/{user_id}/{job_id}/"
            bucket = self._get_bucket()
            blobs = bucket.list_blobs(prefix=prefix)

            assets = {"images": [], "videos": [], "thumbnails": []}
            for blob in blobs:
                if "/images/" in blob.name:
                    assets["images"].append(blob.public_url)
                elif "/videos/" in blob.name:
                    assets["videos"].append(blob.public_url)
                elif "/thumbnails/" in blob.name:
                    assets["thumbnails"].append(blob.public_url)

            return assets

        return await loop.run_in_executor(None, _sync_list)

    async def delete_job_assets(
        self,
        user_id: str,
        job_id: str,
    ) -> int:
        """Delete all assets for a job. Returns count of deleted objects."""
        loop = asyncio.get_event_loop()

        def _sync_delete():
            prefix = f"ugc/{user_id}/{job_id}/"
            bucket = self._get_bucket()
            blobs = list(bucket.list_blobs(prefix=prefix))

            for blob in blobs:
                blob.delete()

            return len(blobs)

        return await loop.run_in_executor(None, _sync_delete)

    async def get_signed_url(
        self,
        blob_path: str,
        expiration_minutes: int = 60,
    ) -> str:
        """Get a signed URL for temporary access to a private blob."""
        from datetime import timedelta

        loop = asyncio.get_event_loop()

        def _sync_sign():
            bucket = self._get_bucket()
            blob = bucket.blob(blob_path)
            return blob.generate_signed_url(
                expiration=timedelta(minutes=expiration_minutes),
                method="GET",
            )

        return await loop.run_in_executor(None, _sync_sign)
