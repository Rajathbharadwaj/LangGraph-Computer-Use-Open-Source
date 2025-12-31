"""
OAuth Manager for Work Integrations.

Handles OAuth2 flows for GitHub, Slack, Notion, Linear, and Figma.
Uses Redis for secure state management (following ads_service pattern).
"""

import secrets
import logging
import json
import hmac
import hashlib
from typing import Optional, Dict, Any, Tuple
from datetime import datetime
from urllib.parse import urlencode
import httpx

from ..config import get_work_integrations_settings, PLATFORM_SCOPES
from ..models import WorkPlatform

logger = logging.getLogger(__name__)

# OAuth state expiration (15 minutes)
STATE_EXPIRATION_SECONDS = 900


class WorkOAuthManager:
    """
    Manages OAuth2 flows for work platforms.

    Uses Redis for state storage to prevent CSRF attacks.
    Follows the same pattern as ads_service/services/oauth_manager.py.
    """

    def __init__(self, redis_client=None):
        """
        Initialize OAuth manager.

        Args:
            redis_client: Optional Redis client. If not provided, will create one.
        """
        self.redis = redis_client
        self.settings = get_work_integrations_settings()

    async def _get_redis(self):
        """Get or create Redis client."""
        if self.redis is None:
            import redis.asyncio as aioredis
            self.redis = aioredis.from_url(self.settings.redis_url)
        return self.redis

    async def _store_state(self, state: str, data: Dict[str, Any]) -> None:
        """Store OAuth state in Redis."""
        try:
            redis = await self._get_redis()
            key = f"work_oauth:state:{state}"
            await redis.setex(key, STATE_EXPIRATION_SECONDS, json.dumps(data))
        except Exception as e:
            logger.error(f"Failed to store OAuth state in Redis: {e}")
            raise ConnectionError(f"Redis connection failed: {e}")

    async def _get_and_delete_state(self, state: str) -> Optional[Dict[str, Any]]:
        """Get OAuth state from Redis and delete it (one-time use)."""
        redis = await self._get_redis()
        key = f"work_oauth:state:{state}"
        data = await redis.get(key)
        if data:
            await redis.delete(key)
            return json.loads(data)
        return None

    # =========================================================================
    # GitHub OAuth
    # https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps
    # =========================================================================

    async def get_github_oauth_url(self, user_id: str) -> Tuple[str, str]:
        """
        Generate GitHub OAuth authorization URL.

        Args:
            user_id: Clerk user ID

        Returns:
            Tuple of (authorization_url, state)
        """
        state = secrets.token_urlsafe(32)

        await self._store_state(
            state,
            {
                "user_id": user_id,
                "platform": "github",
                "created_at": datetime.utcnow().isoformat(),
            },
        )

        params = {
            "client_id": self.settings.github_client_id,
            "redirect_uri": self.settings.github_redirect_uri,
            "scope": " ".join(PLATFORM_SCOPES["github"]),
            "state": state,
        }

        url = f"https://github.com/login/oauth/authorize?{urlencode(params)}"
        logger.info(f"Generated GitHub OAuth URL for user {user_id}")
        return url, state

    async def handle_github_callback(
        self, code: str, state: str
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Handle GitHub OAuth callback.

        Args:
            code: Authorization code from GitHub
            state: State parameter for verification

        Returns:
            Tuple of (user_id, token_data)
        """
        state_data = await self._get_and_delete_state(state)
        if not state_data:
            raise ValueError("Invalid or expired OAuth state")

        if state_data.get("platform") != "github":
            raise ValueError("State platform mismatch")

        user_id = state_data["user_id"]

        async with httpx.AsyncClient() as client:
            # Exchange code for access token
            token_url = "https://github.com/login/oauth/access_token"
            data = {
                "client_id": self.settings.github_client_id,
                "client_secret": self.settings.github_client_secret,
                "code": code,
                "redirect_uri": self.settings.github_redirect_uri,
            }

            response = await client.post(
                token_url,
                data=data,
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            token_data = response.json()

            if "error" in token_data:
                raise ValueError(f"GitHub OAuth error: {token_data.get('error_description', token_data['error'])}")

            # Get user info
            user_url = "https://api.github.com/user"
            user_response = await client.get(
                user_url,
                headers={
                    "Authorization": f"Bearer {token_data['access_token']}",
                    "Accept": "application/vnd.github+json",
                },
            )

            if user_response.status_code == 200:
                user_info = user_response.json()
                token_data["user"] = {
                    "id": user_info.get("id"),
                    "login": user_info.get("login"),
                    "name": user_info.get("name"),
                    "avatar_url": user_info.get("avatar_url"),
                }

        logger.info(f"GitHub OAuth completed for user {user_id}")
        return user_id, token_data

    # =========================================================================
    # Slack OAuth
    # https://api.slack.com/authentication/oauth-v2
    # =========================================================================

    async def get_slack_oauth_url(self, user_id: str) -> Tuple[str, str]:
        """Generate Slack OAuth authorization URL."""
        state = secrets.token_urlsafe(32)

        await self._store_state(
            state,
            {
                "user_id": user_id,
                "platform": "slack",
                "created_at": datetime.utcnow().isoformat(),
            },
        )

        params = {
            "client_id": self.settings.slack_client_id,
            "redirect_uri": self.settings.slack_redirect_uri,
            "scope": ",".join(PLATFORM_SCOPES["slack"]),
            "state": state,
        }

        url = f"https://slack.com/oauth/v2/authorize?{urlencode(params)}"
        logger.info(f"Generated Slack OAuth URL for user {user_id}")
        return url, state

    async def handle_slack_callback(
        self, code: str, state: str
    ) -> Tuple[str, Dict[str, Any]]:
        """Handle Slack OAuth callback."""
        state_data = await self._get_and_delete_state(state)
        if not state_data:
            raise ValueError("Invalid or expired OAuth state")

        if state_data.get("platform") != "slack":
            raise ValueError("State platform mismatch")

        user_id = state_data["user_id"]

        async with httpx.AsyncClient() as client:
            token_url = "https://slack.com/api/oauth.v2.access"
            data = {
                "client_id": self.settings.slack_client_id,
                "client_secret": self.settings.slack_client_secret,
                "code": code,
                "redirect_uri": self.settings.slack_redirect_uri,
            }

            response = await client.post(token_url, data=data)
            response.raise_for_status()
            token_data = response.json()

            if not token_data.get("ok"):
                raise ValueError(f"Slack OAuth error: {token_data.get('error')}")

            # Extract relevant info
            token_data["workspace"] = {
                "id": token_data.get("team", {}).get("id"),
                "name": token_data.get("team", {}).get("name"),
            }

        logger.info(f"Slack OAuth completed for user {user_id}")
        return user_id, token_data

    # =========================================================================
    # Notion OAuth
    # https://developers.notion.com/docs/authorization
    # =========================================================================

    async def get_notion_oauth_url(self, user_id: str) -> Tuple[str, str]:
        """Generate Notion OAuth authorization URL."""
        state = secrets.token_urlsafe(32)

        await self._store_state(
            state,
            {
                "user_id": user_id,
                "platform": "notion",
                "created_at": datetime.utcnow().isoformat(),
            },
        )

        params = {
            "client_id": self.settings.notion_client_id,
            "redirect_uri": self.settings.notion_redirect_uri,
            "response_type": "code",
            "state": state,
            "owner": "user",  # Request access as user, not workspace
        }

        url = f"https://api.notion.com/v1/oauth/authorize?{urlencode(params)}"
        logger.info(f"Generated Notion OAuth URL for user {user_id}")
        return url, state

    async def handle_notion_callback(
        self, code: str, state: str
    ) -> Tuple[str, Dict[str, Any]]:
        """Handle Notion OAuth callback."""
        state_data = await self._get_and_delete_state(state)
        if not state_data:
            raise ValueError("Invalid or expired OAuth state")

        if state_data.get("platform") != "notion":
            raise ValueError("State platform mismatch")

        user_id = state_data["user_id"]

        async with httpx.AsyncClient() as client:
            import base64
            credentials = base64.b64encode(
                f"{self.settings.notion_client_id}:{self.settings.notion_client_secret}".encode()
            ).decode()

            token_url = "https://api.notion.com/v1/oauth/token"
            response = await client.post(
                token_url,
                json={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self.settings.notion_redirect_uri,
                },
                headers={
                    "Authorization": f"Basic {credentials}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            token_data = response.json()

            # Notion returns workspace info
            token_data["workspace"] = {
                "id": token_data.get("workspace_id"),
                "name": token_data.get("workspace_name"),
                "icon": token_data.get("workspace_icon"),
            }

        logger.info(f"Notion OAuth completed for user {user_id}")
        return user_id, token_data

    # =========================================================================
    # Linear OAuth
    # https://developers.linear.app/docs/oauth/authentication
    # =========================================================================

    async def get_linear_oauth_url(self, user_id: str) -> Tuple[str, str]:
        """Generate Linear OAuth authorization URL."""
        state = secrets.token_urlsafe(32)

        await self._store_state(
            state,
            {
                "user_id": user_id,
                "platform": "linear",
                "created_at": datetime.utcnow().isoformat(),
            },
        )

        params = {
            "client_id": self.settings.linear_client_id,
            "redirect_uri": self.settings.linear_redirect_uri,
            "response_type": "code",
            "scope": ",".join(PLATFORM_SCOPES["linear"]),
            "state": state,
        }

        url = f"https://linear.app/oauth/authorize?{urlencode(params)}"
        logger.info(f"Generated Linear OAuth URL for user {user_id}")
        return url, state

    async def handle_linear_callback(
        self, code: str, state: str
    ) -> Tuple[str, Dict[str, Any]]:
        """Handle Linear OAuth callback."""
        state_data = await self._get_and_delete_state(state)
        if not state_data:
            raise ValueError("Invalid or expired OAuth state")

        if state_data.get("platform") != "linear":
            raise ValueError("State platform mismatch")

        user_id = state_data["user_id"]

        async with httpx.AsyncClient() as client:
            token_url = "https://api.linear.app/oauth/token"
            response = await client.post(
                token_url,
                data={
                    "client_id": self.settings.linear_client_id,
                    "client_secret": self.settings.linear_client_secret,
                    "code": code,
                    "redirect_uri": self.settings.linear_redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            response.raise_for_status()
            token_data = response.json()

            # Get user/organization info
            viewer_query = """
            query {
                viewer {
                    id
                    name
                    email
                }
                organization {
                    id
                    name
                }
            }
            """
            viewer_response = await client.post(
                "https://api.linear.app/graphql",
                json={"query": viewer_query},
                headers={"Authorization": f"Bearer {token_data['access_token']}"},
            )

            if viewer_response.status_code == 200:
                viewer_data = viewer_response.json().get("data", {})
                token_data["user"] = viewer_data.get("viewer", {})
                token_data["organization"] = viewer_data.get("organization", {})

        logger.info(f"Linear OAuth completed for user {user_id}")
        return user_id, token_data

    # =========================================================================
    # Figma OAuth
    # https://www.figma.com/developers/api#oauth2
    # =========================================================================

    async def get_figma_oauth_url(self, user_id: str) -> Tuple[str, str]:
        """Generate Figma OAuth authorization URL."""
        state = secrets.token_urlsafe(32)

        await self._store_state(
            state,
            {
                "user_id": user_id,
                "platform": "figma",
                "created_at": datetime.utcnow().isoformat(),
            },
        )

        params = {
            "client_id": self.settings.figma_client_id,
            "redirect_uri": self.settings.figma_redirect_uri,
            "scope": ",".join(PLATFORM_SCOPES["figma"]),
            "response_type": "code",
            "state": state,
        }

        url = f"https://www.figma.com/oauth?{urlencode(params)}"
        logger.info(f"Generated Figma OAuth URL for user {user_id}")
        return url, state

    async def handle_figma_callback(
        self, code: str, state: str
    ) -> Tuple[str, Dict[str, Any]]:
        """Handle Figma OAuth callback."""
        state_data = await self._get_and_delete_state(state)
        if not state_data:
            raise ValueError("Invalid or expired OAuth state")

        if state_data.get("platform") != "figma":
            raise ValueError("State platform mismatch")

        user_id = state_data["user_id"]

        async with httpx.AsyncClient() as client:
            token_url = "https://www.figma.com/api/oauth/token"
            response = await client.post(
                token_url,
                data={
                    "client_id": self.settings.figma_client_id,
                    "client_secret": self.settings.figma_client_secret,
                    "code": code,
                    "redirect_uri": self.settings.figma_redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            response.raise_for_status()
            token_data = response.json()

            # Get user info
            user_url = "https://api.figma.com/v1/me"
            user_response = await client.get(
                user_url,
                headers={"Authorization": f"Bearer {token_data['access_token']}"},
            )

            if user_response.status_code == 200:
                user_info = user_response.json()
                token_data["user"] = {
                    "id": user_info.get("id"),
                    "handle": user_info.get("handle"),
                    "email": user_info.get("email"),
                    "img_url": user_info.get("img_url"),
                }

        logger.info(f"Figma OAuth completed for user {user_id}")
        return user_id, token_data

    # =========================================================================
    # Token Refresh (for platforms that support it)
    # =========================================================================

    async def refresh_slack_token(self, refresh_token: str) -> Dict[str, Any]:
        """Refresh a Slack access token."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://slack.com/api/oauth.v2.access",
                data={
                    "client_id": self.settings.slack_client_id,
                    "client_secret": self.settings.slack_client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
            )
            response.raise_for_status()
            return response.json()

    async def refresh_figma_token(self, refresh_token: str) -> Dict[str, Any]:
        """Refresh a Figma access token."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://www.figma.com/api/oauth/refresh",
                data={
                    "client_id": self.settings.figma_client_id,
                    "client_secret": self.settings.figma_client_secret,
                    "refresh_token": refresh_token,
                },
            )
            response.raise_for_status()
            return response.json()

    # =========================================================================
    # Token Validation
    # =========================================================================

    async def validate_github_token(self, access_token: str) -> bool:
        """Check if a GitHub access token is still valid."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.github.com/user",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            return response.status_code == 200

    async def validate_slack_token(self, access_token: str) -> bool:
        """Check if a Slack access token is still valid."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://slack.com/api/auth.test",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("ok", False)
            return False

    async def validate_notion_token(self, access_token: str) -> bool:
        """Check if a Notion access token is still valid."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.notion.com/v1/users/me",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Notion-Version": "2022-06-28",
                },
            )
            return response.status_code == 200

    async def validate_linear_token(self, access_token: str) -> bool:
        """Check if a Linear access token is still valid."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.linear.app/graphql",
                json={"query": "query { viewer { id } }"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if response.status_code == 200:
                data = response.json()
                return "errors" not in data
            return False

    async def validate_figma_token(self, access_token: str) -> bool:
        """Check if a Figma access token is still valid."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.figma.com/v1/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            return response.status_code == 200

    # =========================================================================
    # Webhook Verification
    # =========================================================================

    def verify_github_webhook(self, payload: bytes, signature: str) -> bool:
        """Verify GitHub webhook signature."""
        if not self.settings.github_webhook_secret:
            return True  # No secret configured, skip verification

        expected = "sha256=" + hmac.new(
            self.settings.github_webhook_secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, signature)

    def verify_slack_request(self, timestamp: str, body: str, signature: str) -> bool:
        """Verify Slack request signature."""
        if not self.settings.slack_signing_secret:
            return True  # No secret configured, skip verification

        base_string = f"v0:{timestamp}:{body}"
        expected = "v0=" + hmac.new(
            self.settings.slack_signing_secret.encode(),
            base_string.encode(),
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, signature)


# Singleton instance
_work_oauth_manager: Optional[WorkOAuthManager] = None


def get_work_oauth_manager(redis_client=None) -> WorkOAuthManager:
    """Get or create the work OAuth manager singleton."""
    global _work_oauth_manager
    if _work_oauth_manager is None:
        _work_oauth_manager = WorkOAuthManager(redis_client)
    return _work_oauth_manager
