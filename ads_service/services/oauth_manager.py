"""
OAuth Manager for Ads Platforms

Handles OAuth2 flows for Meta and Google Ads platforms.
Uses Redis for secure state management.
"""

import secrets
import logging
import json
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
from urllib.parse import urlencode, quote_plus
import httpx

from ..config import get_ads_settings
from ..models import AdsPlatformType

logger = logging.getLogger(__name__)

# OAuth state expiration (15 minutes)
STATE_EXPIRATION_SECONDS = 900


class OAuthManager:
    """
    Manages OAuth2 flows for Meta and Google Ads.

    Uses Redis for state storage to prevent CSRF attacks.
    """

    def __init__(self, redis_client=None):
        """
        Initialize OAuth manager.

        Args:
            redis_client: Optional Redis client. If not provided, will create one.
        """
        self.redis = redis_client
        self.settings = get_ads_settings()

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
            key = f"oauth:state:{state}"
            await redis.setex(key, STATE_EXPIRATION_SECONDS, json.dumps(data))
        except Exception as e:
            logger.error(f"Failed to store OAuth state in Redis: {e}")
            logger.error(f"Redis URL: {self.settings.redis_url}")
            raise ConnectionError(f"Redis connection failed: {e}")

    async def _get_and_delete_state(self, state: str) -> Optional[Dict[str, Any]]:
        """Get OAuth state from Redis and delete it (one-time use)."""
        redis = await self._get_redis()
        key = f"oauth:state:{state}"
        data = await redis.get(key)
        if data:
            await redis.delete(key)
            return json.loads(data)
        return None

    # =========================================================================
    # Meta OAuth
    # =========================================================================

    async def get_meta_oauth_url(self, user_id: str) -> Tuple[str, str]:
        """
        Generate Meta OAuth authorization URL.

        Args:
            user_id: Clerk user ID

        Returns:
            Tuple of (authorization_url, state)
        """
        state = secrets.token_urlsafe(32)

        # Store state with user info
        await self._store_state(
            state,
            {
                "user_id": user_id,
                "platform": "meta",
                "created_at": datetime.utcnow().isoformat(),
            },
        )

        # Build authorization URL
        params = {
            "client_id": self.settings.meta_app_id,
            "redirect_uri": self.settings.meta_redirect_uri,
            "scope": "ads_management,ads_read,business_management,pages_show_list",
            "response_type": "code",
            "state": state,
        }

        base_url = f"https://www.facebook.com/{self.settings.meta_api_version}/dialog/oauth"
        url = f"{base_url}?{urlencode(params)}"

        logger.info(f"Generated Meta OAuth URL for user {user_id}")
        return url, state

    async def handle_meta_callback(
        self, code: str, state: str
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Handle Meta OAuth callback.

        Args:
            code: Authorization code from Meta
            state: State parameter for verification

        Returns:
            Tuple of (user_id, token_data)

        Raises:
            ValueError: If state is invalid or expired
        """
        # Verify state
        state_data = await self._get_and_delete_state(state)
        if not state_data:
            raise ValueError("Invalid or expired OAuth state")

        if state_data.get("platform") != "meta":
            raise ValueError("State platform mismatch")

        user_id = state_data["user_id"]

        # Exchange code for access token
        async with httpx.AsyncClient() as client:
            token_url = f"https://graph.facebook.com/{self.settings.meta_api_version}/oauth/access_token"
            params = {
                "client_id": self.settings.meta_app_id,
                "client_secret": self.settings.meta_app_secret,
                "redirect_uri": self.settings.meta_redirect_uri,
                "code": code,
            }

            response = await client.get(token_url, params=params)
            response.raise_for_status()
            token_data = response.json()

            # Get long-lived token
            if "access_token" in token_data:
                long_lived_url = f"https://graph.facebook.com/{self.settings.meta_api_version}/oauth/access_token"
                ll_params = {
                    "grant_type": "fb_exchange_token",
                    "client_id": self.settings.meta_app_id,
                    "client_secret": self.settings.meta_app_secret,
                    "fb_exchange_token": token_data["access_token"],
                }

                ll_response = await client.get(long_lived_url, params=ll_params)
                if ll_response.status_code == 200:
                    ll_data = ll_response.json()
                    token_data["access_token"] = ll_data.get(
                        "access_token", token_data["access_token"]
                    )
                    token_data["expires_in"] = ll_data.get("expires_in", 5184000)

            # Get ad accounts
            me_url = f"https://graph.facebook.com/{self.settings.meta_api_version}/me/adaccounts"
            me_params = {
                "access_token": token_data["access_token"],
                "fields": "id,name,account_status",
            }

            me_response = await client.get(me_url, params=me_params)
            if me_response.status_code == 200:
                ad_accounts = me_response.json().get("data", [])
                token_data["ad_accounts"] = ad_accounts

            # Get pages
            pages_url = f"https://graph.facebook.com/{self.settings.meta_api_version}/me/accounts"
            pages_params = {
                "access_token": token_data["access_token"],
                "fields": "id,name,access_token",
            }

            pages_response = await client.get(pages_url, params=pages_params)
            if pages_response.status_code == 200:
                pages = pages_response.json().get("data", [])
                token_data["pages"] = pages

        logger.info(f"Meta OAuth completed for user {user_id}")
        return user_id, token_data

    # =========================================================================
    # Google OAuth
    # =========================================================================

    async def get_google_oauth_url(self, user_id: str) -> Tuple[str, str]:
        """
        Generate Google OAuth authorization URL.

        Args:
            user_id: Clerk user ID

        Returns:
            Tuple of (authorization_url, state)
        """
        state = secrets.token_urlsafe(32)

        # Store state with user info
        await self._store_state(
            state,
            {
                "user_id": user_id,
                "platform": "google",
                "created_at": datetime.utcnow().isoformat(),
            },
        )

        # Build authorization URL
        params = {
            "client_id": self.settings.google_client_id,
            "redirect_uri": self.settings.google_redirect_uri,
            "scope": "https://www.googleapis.com/auth/adwords",
            "response_type": "code",
            "state": state,
            "access_type": "offline",  # Get refresh token
            "prompt": "consent",  # Always show consent screen to get refresh token
        }

        base_url = "https://accounts.google.com/o/oauth2/v2/auth"
        url = f"{base_url}?{urlencode(params)}"

        logger.info(f"Generated Google OAuth URL for user {user_id}")
        return url, state

    async def handle_google_callback(
        self, code: str, state: str
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Handle Google OAuth callback.

        Args:
            code: Authorization code from Google
            state: State parameter for verification

        Returns:
            Tuple of (user_id, token_data)

        Raises:
            ValueError: If state is invalid or expired
        """
        # Verify state
        state_data = await self._get_and_delete_state(state)
        if not state_data:
            raise ValueError("Invalid or expired OAuth state")

        if state_data.get("platform") != "google":
            raise ValueError("State platform mismatch")

        user_id = state_data["user_id"]

        # Exchange code for tokens
        async with httpx.AsyncClient() as client:
            token_url = "https://oauth2.googleapis.com/token"
            data = {
                "client_id": self.settings.google_client_id,
                "client_secret": self.settings.google_client_secret,
                "redirect_uri": self.settings.google_redirect_uri,
                "code": code,
                "grant_type": "authorization_code",
            }

            response = await client.post(token_url, data=data)
            response.raise_for_status()
            token_data = response.json()

            # Get accessible customer IDs using the Google Ads API
            # Note: This requires the google-ads SDK which we'll do in the client
            token_data["customer_ids"] = []

        logger.info(f"Google OAuth completed for user {user_id}")
        return user_id, token_data

    async def refresh_google_token(self, refresh_token: str) -> Dict[str, Any]:
        """
        Refresh a Google access token.

        Args:
            refresh_token: The refresh token

        Returns:
            New token data
        """
        async with httpx.AsyncClient() as client:
            token_url = "https://oauth2.googleapis.com/token"
            data = {
                "client_id": self.settings.google_client_id,
                "client_secret": self.settings.google_client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            }

            response = await client.post(token_url, data=data)
            response.raise_for_status()
            return response.json()

    # =========================================================================
    # Token Validation
    # =========================================================================

    async def validate_meta_token(self, access_token: str) -> bool:
        """Check if a Meta access token is still valid."""
        async with httpx.AsyncClient() as client:
            url = f"https://graph.facebook.com/{self.settings.meta_api_version}/me"
            params = {"access_token": access_token}

            response = await client.get(url, params=params)
            return response.status_code == 200

    async def validate_google_token(self, access_token: str) -> bool:
        """Check if a Google access token is still valid."""
        async with httpx.AsyncClient() as client:
            url = "https://www.googleapis.com/oauth2/v1/tokeninfo"
            params = {"access_token": access_token}

            response = await client.get(url, params=params)
            return response.status_code == 200


# Singleton instance
_oauth_manager: Optional[OAuthManager] = None


def get_oauth_manager(redis_client=None) -> OAuthManager:
    """Get or create the OAuth manager singleton."""
    global _oauth_manager
    if _oauth_manager is None:
        _oauth_manager = OAuthManager(redis_client)
    return _oauth_manager
