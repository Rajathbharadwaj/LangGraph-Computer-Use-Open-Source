"""
GitHub API Client for Work Integrations.

Handles GitHub API calls for:
- Listing repositories
- Setting up webhooks
- Fetching recent activity (commits, PRs, releases)
"""

import logging
import secrets
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import httpx

from ..config import get_work_integrations_settings

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"


class GitHubClient:
    """
    GitHub API client for work integrations.

    Uses personal access tokens from OAuth to access user's GitHub data.
    """

    def __init__(self, access_token: str):
        """Initialize with access token."""
        self.access_token = access_token
        self.settings = get_work_integrations_settings()
        self._headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs,
    ) -> Dict[str, Any]:
        """Make a request to GitHub API."""
        url = f"{GITHUB_API_BASE}{endpoint}"
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method,
                url,
                headers=self._headers,
                **kwargs,
            )
            response.raise_for_status()
            return response.json() if response.text else {}

    # =========================================================================
    # User & Repositories
    # =========================================================================

    async def get_user(self) -> Dict[str, Any]:
        """Get authenticated user info."""
        return await self._request("GET", "/user")

    async def list_repos(
        self,
        per_page: int = 100,
        sort: str = "updated",
        visibility: str = "all",
    ) -> List[Dict[str, Any]]:
        """
        List repositories accessible to the authenticated user.

        Args:
            per_page: Number of repos per page (max 100)
            sort: Sort by: created, updated, pushed, full_name
            visibility: all, public, private

        Returns:
            List of repository objects
        """
        repos = []
        page = 1

        while True:
            data = await self._request(
                "GET",
                "/user/repos",
                params={
                    "per_page": per_page,
                    "page": page,
                    "sort": sort,
                    "visibility": visibility,
                },
            )

            if not data:
                break

            repos.extend(data)

            if len(data) < per_page:
                break

            page += 1

            # Safety limit
            if page > 10:
                break

        return repos

    async def get_repo(self, owner: str, repo: str) -> Dict[str, Any]:
        """Get a specific repository."""
        return await self._request("GET", f"/repos/{owner}/{repo}")

    # =========================================================================
    # Webhooks
    # =========================================================================

    async def create_webhook(
        self,
        owner: str,
        repo: str,
        webhook_url: str,
        secret: str,
        events: List[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a webhook for a repository.

        Args:
            owner: Repository owner (username or org)
            repo: Repository name
            webhook_url: URL to receive webhook events
            secret: Webhook secret for verification
            events: List of events to subscribe to

        Returns:
            Webhook object
        """
        if events is None:
            events = ["push", "pull_request", "release", "issues", "issue_comment"]

        return await self._request(
            "POST",
            f"/repos/{owner}/{repo}/hooks",
            json={
                "name": "web",
                "active": True,
                "events": events,
                "config": {
                    "url": webhook_url,
                    "content_type": "json",
                    "secret": secret,
                    "insecure_ssl": "0",
                },
            },
        )

    async def list_webhooks(self, owner: str, repo: str) -> List[Dict[str, Any]]:
        """List webhooks for a repository."""
        return await self._request("GET", f"/repos/{owner}/{repo}/hooks")

    async def delete_webhook(self, owner: str, repo: str, hook_id: int) -> None:
        """Delete a webhook."""
        await self._request("DELETE", f"/repos/{owner}/{repo}/hooks/{hook_id}")

    # =========================================================================
    # Activity Fetching
    # =========================================================================

    async def get_recent_commits(
        self,
        owner: str,
        repo: str,
        since: datetime = None,
        per_page: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        Get recent commits for a repository.

        Args:
            owner: Repository owner
            repo: Repository name
            since: Only commits after this date
            per_page: Number of commits to fetch

        Returns:
            List of commit objects
        """
        params = {"per_page": per_page}
        if since:
            params["since"] = since.isoformat()

        return await self._request(
            "GET",
            f"/repos/{owner}/{repo}/commits",
            params=params,
        )

    async def get_recent_prs(
        self,
        owner: str,
        repo: str,
        state: str = "all",
        per_page: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        Get recent pull requests for a repository.

        Args:
            owner: Repository owner
            repo: Repository name
            state: open, closed, or all
            per_page: Number of PRs to fetch

        Returns:
            List of PR objects
        """
        return await self._request(
            "GET",
            f"/repos/{owner}/{repo}/pulls",
            params={
                "state": state,
                "sort": "updated",
                "direction": "desc",
                "per_page": per_page,
            },
        )

    async def get_pr(self, owner: str, repo: str, pr_number: int) -> Dict[str, Any]:
        """Get a specific pull request."""
        return await self._request("GET", f"/repos/{owner}/{repo}/pulls/{pr_number}")

    async def get_recent_releases(
        self,
        owner: str,
        repo: str,
        per_page: int = 10,
    ) -> List[Dict[str, Any]]:
        """Get recent releases for a repository."""
        return await self._request(
            "GET",
            f"/repos/{owner}/{repo}/releases",
            params={"per_page": per_page},
        )

    async def get_recent_issues(
        self,
        owner: str,
        repo: str,
        state: str = "all",
        per_page: int = 30,
    ) -> List[Dict[str, Any]]:
        """Get recent issues for a repository (excluding PRs)."""
        issues = await self._request(
            "GET",
            f"/repos/{owner}/{repo}/issues",
            params={
                "state": state,
                "sort": "updated",
                "direction": "desc",
                "per_page": per_page,
            },
        )
        # Filter out pull requests (they appear in issues API too)
        return [i for i in issues if "pull_request" not in i]

    # =========================================================================
    # User Events (alternative to webhooks)
    # =========================================================================

    async def get_user_events(
        self,
        username: str,
        per_page: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        Get recent events for a user.

        Useful for polling when webhooks aren't set up.
        Events include: PushEvent, PullRequestEvent, ReleaseEvent, etc.
        """
        return await self._request(
            "GET",
            f"/users/{username}/events",
            params={"per_page": per_page},
        )

    async def get_repo_events(
        self,
        owner: str,
        repo: str,
        per_page: int = 30,
    ) -> List[Dict[str, Any]]:
        """Get recent events for a repository."""
        return await self._request(
            "GET",
            f"/repos/{owner}/{repo}/events",
            params={"per_page": per_page},
        )


def get_github_client(access_token: str) -> GitHubClient:
    """Create a GitHub client with the given access token."""
    return GitHubClient(access_token)
