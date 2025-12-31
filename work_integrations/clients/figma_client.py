"""
Figma REST API Client for Work Integrations.

Handles Figma API calls for:
- Files and projects
- Version history
- Comments

Note: Figma webhooks are limited, so we primarily use polling.
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import httpx

from ..config import get_work_integrations_settings

logger = logging.getLogger(__name__)

FIGMA_API_BASE = "https://api.figma.com/v1"


class FigmaClient:
    """
    Figma REST API client for work integrations.

    Uses OAuth tokens to access design files.
    Polling-based since Figma webhooks are limited.
    """

    def __init__(self, access_token: str):
        """Initialize with access token."""
        self.access_token = access_token
        self.settings = get_work_integrations_settings()
        self._headers = {
            "Authorization": f"Bearer {access_token}",
        }

    async def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs,
    ) -> Dict[str, Any]:
        """Make a request to Figma API."""
        url = f"{FIGMA_API_BASE}/{endpoint}"
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method,
                url,
                headers=self._headers,
                **kwargs,
            )
            response.raise_for_status()
            return response.json()

    # =========================================================================
    # User
    # =========================================================================

    async def get_me(self) -> Dict[str, Any]:
        """Get current user info."""
        return await self._request("GET", "me")

    # =========================================================================
    # Teams & Projects
    # =========================================================================

    async def list_team_projects(self, team_id: str) -> List[Dict[str, Any]]:
        """
        List all projects in a team.

        Args:
            team_id: Team ID

        Returns:
            List of project objects
        """
        data = await self._request("GET", f"teams/{team_id}/projects")
        return data.get("projects", [])

    async def list_project_files(self, project_id: str) -> List[Dict[str, Any]]:
        """
        List all files in a project.

        Args:
            project_id: Project ID

        Returns:
            List of file objects
        """
        data = await self._request("GET", f"projects/{project_id}/files")
        return data.get("files", [])

    # =========================================================================
    # Files
    # =========================================================================

    async def get_file(
        self,
        file_key: str,
        depth: int = 1,
    ) -> Dict[str, Any]:
        """
        Get a file by key.

        Args:
            file_key: File key (from URL)
            depth: Traversal depth for node tree

        Returns:
            File object with document tree
        """
        return await self._request(
            "GET",
            f"files/{file_key}",
            params={"depth": depth},
        )

    async def get_file_metadata(self, file_key: str) -> Dict[str, Any]:
        """
        Get file metadata only (faster than full file).

        Args:
            file_key: File key

        Returns:
            File metadata
        """
        # Getting with depth=0 returns just metadata
        data = await self._request(
            "GET",
            f"files/{file_key}",
            params={"depth": 0},
        )
        return {
            "name": data.get("name"),
            "lastModified": data.get("lastModified"),
            "thumbnailUrl": data.get("thumbnailUrl"),
            "version": data.get("version"),
        }

    # =========================================================================
    # Version History
    # =========================================================================

    async def get_file_versions(
        self,
        file_key: str,
        limit: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        Get version history for a file.

        Args:
            file_key: File key
            limit: Maximum versions to return

        Returns:
            List of version objects
        """
        data = await self._request("GET", f"files/{file_key}/versions")
        versions = data.get("versions", [])
        return versions[:limit]

    # =========================================================================
    # Comments
    # =========================================================================

    async def get_file_comments(
        self,
        file_key: str,
        as_md: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Get all comments on a file.

        Args:
            file_key: File key
            as_md: Return message as markdown

        Returns:
            List of comment objects
        """
        params = {}
        if as_md:
            params["as_md"] = "true"

        data = await self._request(
            "GET",
            f"files/{file_key}/comments",
            params=params,
        )
        return data.get("comments", [])

    async def post_comment(
        self,
        file_key: str,
        message: str,
        client_meta: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        Post a comment on a file.

        Args:
            file_key: File key
            message: Comment text
            client_meta: Optional position metadata

        Returns:
            Created comment object
        """
        body = {"message": message}
        if client_meta:
            body["client_meta"] = client_meta

        return await self._request(
            "POST",
            f"files/{file_key}/comments",
            json=body,
        )

    # =========================================================================
    # Polling for Changes
    # =========================================================================

    async def get_recently_modified_files(
        self,
        project_ids: List[str],
        since: datetime = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Get files that were recently modified.

        Checks project files and filters by last modified time.

        Args:
            project_ids: Project IDs to check
            since: Only files modified after this time
            limit: Maximum files to return

        Returns:
            List of recently modified files with metadata
        """
        if since is None:
            since = datetime.utcnow() - timedelta(hours=24)

        results = []

        for project_id in project_ids[:5]:  # Limit to avoid rate limits
            try:
                files = await self.list_project_files(project_id)

                for file_info in files:
                    file_key = file_info.get("key")
                    if not file_key:
                        continue

                    # Get metadata with last modified time
                    try:
                        metadata = await self.get_file_metadata(file_key)
                        last_modified = metadata.get("lastModified", "")

                        if last_modified:
                            # Figma uses ISO format
                            modified_dt = datetime.fromisoformat(
                                last_modified.replace("Z", "+00:00")
                            )
                            if modified_dt >= since.replace(tzinfo=modified_dt.tzinfo):
                                results.append({
                                    **file_info,
                                    **metadata,
                                    "project_id": project_id,
                                })
                    except Exception as e:
                        logger.warning(f"Failed to get metadata for file {file_key}: {e}")
                        continue

            except Exception as e:
                logger.warning(f"Failed to list files for project {project_id}: {e}")
                continue

        # Sort by last modified
        results.sort(
            key=lambda x: x.get("lastModified", ""),
            reverse=True,
        )

        return results[:limit]

    async def get_recent_comments(
        self,
        file_keys: List[str],
        since: datetime = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Get recent comments across multiple files.

        Args:
            file_keys: File keys to check
            since: Only comments after this time
            limit: Maximum comments to return

        Returns:
            List of comments with file context
        """
        if since is None:
            since = datetime.utcnow() - timedelta(hours=24)

        results = []

        for file_key in file_keys[:10]:  # Limit to avoid rate limits
            try:
                comments = await self.get_file_comments(file_key)

                for comment in comments:
                    created = comment.get("created_at", "")
                    if created:
                        created_dt = datetime.fromisoformat(
                            created.replace("Z", "+00:00")
                        )
                        if created_dt >= since.replace(tzinfo=created_dt.tzinfo):
                            results.append({
                                **comment,
                                "file_key": file_key,
                            })

            except Exception as e:
                logger.warning(f"Failed to get comments for file {file_key}: {e}")
                continue

        # Sort by created time
        results.sort(
            key=lambda x: x.get("created_at", ""),
            reverse=True,
        )

        return results[:limit]

    async def get_recent_versions(
        self,
        file_keys: List[str],
        since: datetime = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Get recent version saves across multiple files.

        Args:
            file_keys: File keys to check
            since: Only versions after this time
            limit: Maximum versions to return

        Returns:
            List of versions with file context
        """
        if since is None:
            since = datetime.utcnow() - timedelta(hours=24)

        results = []

        for file_key in file_keys[:10]:  # Limit to avoid rate limits
            try:
                versions = await self.get_file_versions(file_key, limit=10)

                for version in versions:
                    created = version.get("created_at", "")
                    if created:
                        created_dt = datetime.fromisoformat(
                            created.replace("Z", "+00:00")
                        )
                        if created_dt >= since.replace(tzinfo=created_dt.tzinfo):
                            results.append({
                                **version,
                                "file_key": file_key,
                            })

            except Exception as e:
                logger.warning(f"Failed to get versions for file {file_key}: {e}")
                continue

        # Sort by created time
        results.sort(
            key=lambda x: x.get("created_at", ""),
            reverse=True,
        )

        return results[:limit]


def get_figma_client(access_token: str) -> FigmaClient:
    """Create a Figma client with the given access token."""
    return FigmaClient(access_token)
