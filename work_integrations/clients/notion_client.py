"""
Notion API Client for Work Integrations.

Handles Notion API calls for:
- Databases and pages
- Page updates and changes
- Comments

Note: Notion doesn't support webhooks, so we use polling.
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import httpx

from ..config import get_work_integrations_settings

logger = logging.getLogger(__name__)

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


class NotionClient:
    """
    Notion API client for work integrations.

    Uses OAuth tokens to access workspace data.
    Polling-based since Notion doesn't support webhooks.
    """

    def __init__(self, access_token: str):
        """Initialize with access token."""
        self.access_token = access_token
        self.settings = get_work_integrations_settings()
        self._headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Notion-Version": NOTION_VERSION,
        }

    async def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs,
    ) -> Dict[str, Any]:
        """Make a request to Notion API."""
        url = f"{NOTION_API_BASE}/{endpoint}"
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
    # User & Workspace
    # =========================================================================

    async def get_me(self) -> Dict[str, Any]:
        """Get current user/bot info."""
        return await self._request("GET", "users/me")

    async def list_users(self) -> List[Dict[str, Any]]:
        """List all users in the workspace."""
        data = await self._request("GET", "users")
        return data.get("results", [])

    # =========================================================================
    # Search
    # =========================================================================

    async def search(
        self,
        query: str = "",
        filter_type: str = None,
        sort_direction: str = "descending",
        page_size: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Search pages and databases.

        Args:
            query: Search query
            filter_type: "page" or "database"
            sort_direction: "ascending" or "descending"
            page_size: Results per page

        Returns:
            List of matching objects
        """
        body = {
            "page_size": page_size,
            "sort": {
                "direction": sort_direction,
                "timestamp": "last_edited_time",
            },
        }

        if query:
            body["query"] = query
        if filter_type:
            body["filter"] = {"property": "object", "value": filter_type}

        data = await self._request("POST", "search", json=body)
        return data.get("results", [])

    # =========================================================================
    # Databases
    # =========================================================================

    async def list_databases(self) -> List[Dict[str, Any]]:
        """List all databases the integration has access to."""
        return await self.search(filter_type="database")

    async def get_database(self, database_id: str) -> Dict[str, Any]:
        """Get a database by ID."""
        return await self._request("GET", f"databases/{database_id}")

    async def query_database(
        self,
        database_id: str,
        filter_obj: Dict[str, Any] = None,
        sorts: List[Dict[str, Any]] = None,
        page_size: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Query a database for pages.

        Args:
            database_id: Database ID
            filter_obj: Filter object
            sorts: Sort objects
            page_size: Results per page

        Returns:
            List of database entries (pages)
        """
        body = {"page_size": page_size}
        if filter_obj:
            body["filter"] = filter_obj
        if sorts:
            body["sorts"] = sorts

        data = await self._request("POST", f"databases/{database_id}/query", json=body)
        return data.get("results", [])

    # =========================================================================
    # Pages
    # =========================================================================

    async def get_page(self, page_id: str) -> Dict[str, Any]:
        """Get a page by ID."""
        return await self._request("GET", f"pages/{page_id}")

    async def get_page_content(
        self,
        page_id: str,
        page_size: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get page content (blocks).

        Args:
            page_id: Page ID
            page_size: Blocks per page

        Returns:
            List of block objects
        """
        data = await self._request(
            "GET",
            f"blocks/{page_id}/children",
            params={"page_size": page_size},
        )
        return data.get("results", [])

    # =========================================================================
    # Comments
    # =========================================================================

    async def list_comments(
        self,
        block_id: str = None,
        page_size: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        List comments on a block or page.

        Args:
            block_id: Block or page ID
            page_size: Comments per page

        Returns:
            List of comment objects
        """
        params = {"page_size": page_size}
        if block_id:
            params["block_id"] = block_id

        data = await self._request("GET", "comments", params=params)
        return data.get("results", [])

    # =========================================================================
    # Polling for Changes
    # =========================================================================

    async def get_recently_edited_pages(
        self,
        since: datetime = None,
        database_ids: List[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Get pages that were recently edited.

        Uses search API sorted by last_edited_time.

        Args:
            since: Only pages edited after this time
            database_ids: Only check specific databases
            limit: Maximum pages to return

        Returns:
            List of recently edited pages
        """
        if since is None:
            since = datetime.utcnow() - timedelta(hours=24)

        results = []

        if database_ids:
            # Query specific databases
            for db_id in database_ids[:5]:  # Limit to avoid rate limits
                try:
                    pages = await self.query_database(
                        db_id,
                        sorts=[{
                            "timestamp": "last_edited_time",
                            "direction": "descending",
                        }],
                        page_size=20,
                    )

                    # Filter by time
                    for page in pages:
                        edited = page.get("last_edited_time", "")
                        if edited:
                            edited_dt = datetime.fromisoformat(edited.replace("Z", "+00:00"))
                            if edited_dt >= since.replace(tzinfo=edited_dt.tzinfo):
                                results.append(page)

                except Exception as e:
                    logger.warning(f"Failed to query database {db_id}: {e}")
                    continue
        else:
            # Use general search
            pages = await self.search(
                filter_type="page",
                sort_direction="descending",
                page_size=limit,
            )

            for page in pages:
                edited = page.get("last_edited_time", "")
                if edited:
                    edited_dt = datetime.fromisoformat(edited.replace("Z", "+00:00"))
                    if edited_dt >= since.replace(tzinfo=edited_dt.tzinfo):
                        results.append(page)

        return results[:limit]

    def extract_page_title(self, page: Dict[str, Any]) -> str:
        """Extract the title from a page object."""
        properties = page.get("properties", {})

        # Try common title property names
        for key in ["Name", "Title", "name", "title"]:
            if key in properties:
                prop = properties[key]
                if prop.get("type") == "title":
                    title_arr = prop.get("title", [])
                    if title_arr:
                        return title_arr[0].get("plain_text", "Untitled")

        # Fallback to first title type property
        for prop in properties.values():
            if prop.get("type") == "title":
                title_arr = prop.get("title", [])
                if title_arr:
                    return title_arr[0].get("plain_text", "Untitled")

        return "Untitled"


def get_notion_client(access_token: str) -> NotionClient:
    """Create a Notion client with the given access token."""
    return NotionClient(access_token)
