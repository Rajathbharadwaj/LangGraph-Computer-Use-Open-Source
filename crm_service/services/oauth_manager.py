"""
OAuth Manager for CRM Messaging Platforms

Extends Meta OAuth to include messaging scopes for WhatsApp, Instagram, and Messenger.
"""

import secrets
import logging
import json
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime
from urllib.parse import urlencode
import httpx

from ..config import get_crm_settings, MESSAGING_SCOPES

logger = logging.getLogger(__name__)

# OAuth state expiration (15 minutes)
STATE_EXPIRATION_SECONDS = 900


class CRMOAuthManager:
    """
    Manages OAuth2 flows for Meta messaging platforms.

    Handles WhatsApp Cloud API, Instagram Messaging, and Messenger setup.
    """

    def __init__(self, redis_client=None):
        """
        Initialize CRM OAuth manager.

        Args:
            redis_client: Optional Redis client. If not provided, will create one.
        """
        self.redis = redis_client
        self.settings = get_crm_settings()

    async def _get_redis(self):
        """Get or create Redis client."""
        if self.redis is None:
            import redis.asyncio as aioredis
            self.redis = aioredis.from_url(self.settings.redis_url)
        return self.redis

    async def _store_state(self, state: str, data: Dict[str, Any]) -> None:
        """Store OAuth state in Redis."""
        redis = await self._get_redis()
        key = f"oauth:crm:state:{state}"
        await redis.setex(key, STATE_EXPIRATION_SECONDS, json.dumps(data))

    async def _get_and_delete_state(self, state: str) -> Optional[Dict[str, Any]]:
        """Get OAuth state from Redis and delete it (one-time use)."""
        redis = await self._get_redis()
        key = f"oauth:crm:state:{state}"
        data = await redis.get(key)
        if data:
            await redis.delete(key)
            return json.loads(data)
        return None

    # =========================================================================
    # Meta Messaging OAuth
    # =========================================================================

    async def get_meta_messaging_oauth_url(self, user_id: str) -> Tuple[str, str]:
        """
        Generate Meta OAuth authorization URL with messaging scopes.

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
                "platform": "meta_messaging",
                "created_at": datetime.utcnow().isoformat(),
            },
        )

        # Build authorization URL with messaging scopes
        scopes = ",".join(MESSAGING_SCOPES)

        params = {
            "client_id": self.settings.meta_app_id,
            "redirect_uri": f"{self.settings.app_base_url}/api/crm/oauth/meta/callback",
            "scope": scopes,
            "response_type": "code",
            "state": state,
        }

        base_url = f"https://www.facebook.com/{self.settings.meta_api_version}/dialog/oauth"
        url = f"{base_url}?{urlencode(params)}"

        logger.info(f"Generated Meta messaging OAuth URL for user {user_id}")
        return url, state

    async def handle_meta_messaging_callback(
        self, code: str, state: str
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Handle Meta messaging OAuth callback.

        Fetches WhatsApp Business Accounts, Instagram accounts, and Pages.

        Args:
            code: Authorization code from Meta
            state: State parameter for verification

        Returns:
            Tuple of (user_id, platform_data)

        Raises:
            ValueError: If state is invalid or expired
        """
        # Verify state
        state_data = await self._get_and_delete_state(state)
        if not state_data:
            raise ValueError("Invalid or expired OAuth state")

        if state_data.get("platform") != "meta_messaging":
            raise ValueError("State platform mismatch")

        user_id = state_data["user_id"]

        async with httpx.AsyncClient() as client:
            # Exchange code for access token
            token_url = f"https://graph.facebook.com/{self.settings.meta_api_version}/oauth/access_token"
            params = {
                "client_id": self.settings.meta_app_id,
                "client_secret": self.settings.meta_app_secret,
                "redirect_uri": f"{self.settings.app_base_url}/api/crm/oauth/meta/callback",
                "code": code,
            }

            response = await client.get(token_url, params=params)
            response.raise_for_status()
            token_data = response.json()

            access_token = token_data["access_token"]

            # Get long-lived token
            ll_url = f"https://graph.facebook.com/{self.settings.meta_api_version}/oauth/access_token"
            ll_params = {
                "grant_type": "fb_exchange_token",
                "client_id": self.settings.meta_app_id,
                "client_secret": self.settings.meta_app_secret,
                "fb_exchange_token": access_token,
            }

            ll_response = await client.get(ll_url, params=ll_params)
            if ll_response.status_code == 200:
                ll_data = ll_response.json()
                access_token = ll_data.get("access_token", access_token)
                token_data["access_token"] = access_token
                token_data["expires_in"] = ll_data.get("expires_in", 5184000)

            # Build platform data
            platform_data = {
                "access_token": access_token,
                "expires_in": token_data.get("expires_in"),
            }

            # Fetch WhatsApp Business Accounts (WABA)
            waba_data = await self._fetch_whatsapp_accounts(client, access_token)
            platform_data["whatsapp"] = waba_data

            # Fetch Instagram accounts
            instagram_data = await self._fetch_instagram_accounts(client, access_token)
            platform_data["instagram"] = instagram_data

            # Fetch Facebook Pages for Messenger
            pages_data = await self._fetch_pages(client, access_token)
            platform_data["pages"] = pages_data

        logger.info(f"Meta messaging OAuth completed for user {user_id}")
        return user_id, platform_data

    async def _fetch_whatsapp_accounts(
        self, client: httpx.AsyncClient, access_token: str
    ) -> Dict[str, Any]:
        """Fetch WhatsApp Business Accounts accessible by the user."""
        try:
            # First get the user's businesses
            business_url = f"https://graph.facebook.com/{self.settings.meta_api_version}/me/businesses"
            response = await client.get(
                business_url,
                params={
                    "access_token": access_token,
                    "fields": "id,name",
                },
            )

            businesses = []
            if response.status_code == 200:
                businesses = response.json().get("data", [])

            # For each business, get WhatsApp Business Accounts
            wabas = []
            for business in businesses:
                waba_url = f"https://graph.facebook.com/{self.settings.meta_api_version}/{business['id']}/owned_whatsapp_business_accounts"
                waba_response = await client.get(
                    waba_url,
                    params={
                        "access_token": access_token,
                        "fields": "id,name,timezone_id,message_template_namespace",
                    },
                )

                if waba_response.status_code == 200:
                    for waba in waba_response.json().get("data", []):
                        # Get phone numbers for this WABA
                        phones_url = f"https://graph.facebook.com/{self.settings.meta_api_version}/{waba['id']}/phone_numbers"
                        phones_response = await client.get(
                            phones_url,
                            params={
                                "access_token": access_token,
                                "fields": "id,display_phone_number,verified_name,quality_rating",
                            },
                        )

                        phone_numbers = []
                        if phones_response.status_code == 200:
                            phone_numbers = phones_response.json().get("data", [])

                        wabas.append({
                            "waba_id": waba["id"],
                            "name": waba.get("name"),
                            "business_id": business["id"],
                            "business_name": business.get("name"),
                            "phone_numbers": phone_numbers,
                        })

            return {"accounts": wabas}

        except Exception as e:
            logger.error(f"Error fetching WhatsApp accounts: {e}")
            return {"accounts": [], "error": str(e)}

    async def _fetch_instagram_accounts(
        self, client: httpx.AsyncClient, access_token: str
    ) -> Dict[str, Any]:
        """Fetch Instagram business accounts connected via Pages."""
        try:
            # Get user's pages first
            pages_url = f"https://graph.facebook.com/{self.settings.meta_api_version}/me/accounts"
            response = await client.get(
                pages_url,
                params={
                    "access_token": access_token,
                    "fields": "id,name,instagram_business_account",
                },
            )

            instagram_accounts = []
            if response.status_code == 200:
                pages = response.json().get("data", [])

                for page in pages:
                    if "instagram_business_account" in page:
                        ig_id = page["instagram_business_account"]["id"]

                        # Get Instagram account details
                        ig_url = f"https://graph.facebook.com/{self.settings.meta_api_version}/{ig_id}"
                        ig_response = await client.get(
                            ig_url,
                            params={
                                "access_token": access_token,
                                "fields": "id,username,name,profile_picture_url,followers_count",
                            },
                        )

                        if ig_response.status_code == 200:
                            ig_data = ig_response.json()
                            instagram_accounts.append({
                                "instagram_id": ig_id,
                                "username": ig_data.get("username"),
                                "name": ig_data.get("name"),
                                "profile_picture_url": ig_data.get("profile_picture_url"),
                                "followers_count": ig_data.get("followers_count"),
                                "page_id": page["id"],
                                "page_name": page.get("name"),
                            })

            return {"accounts": instagram_accounts}

        except Exception as e:
            logger.error(f"Error fetching Instagram accounts: {e}")
            return {"accounts": [], "error": str(e)}

    async def _fetch_pages(
        self, client: httpx.AsyncClient, access_token: str
    ) -> Dict[str, Any]:
        """Fetch Facebook Pages for Messenger."""
        try:
            pages_url = f"https://graph.facebook.com/{self.settings.meta_api_version}/me/accounts"
            response = await client.get(
                pages_url,
                params={
                    "access_token": access_token,
                    "fields": "id,name,access_token,category",
                },
            )

            pages = []
            if response.status_code == 200:
                for page in response.json().get("data", []):
                    pages.append({
                        "page_id": page["id"],
                        "name": page.get("name"),
                        "category": page.get("category"),
                        "access_token": page.get("access_token"),  # Page-specific token
                    })

            return {"pages": pages}

        except Exception as e:
            logger.error(f"Error fetching Pages: {e}")
            return {"pages": [], "error": str(e)}

    # =========================================================================
    # Webhook Setup
    # =========================================================================

    async def setup_webhook_subscriptions(
        self,
        page_id: str,
        page_access_token: str,
        verify_token: str,
        callback_url: str,
    ) -> Dict[str, Any]:
        """
        Subscribe a Page to webhook events for Messenger and Instagram.

        Args:
            page_id: Facebook Page ID
            page_access_token: Page-specific access token
            verify_token: Webhook verification token
            callback_url: Webhook callback URL

        Returns:
            Subscription result
        """
        async with httpx.AsyncClient() as client:
            # Subscribe the app to the Page
            subscribe_url = f"https://graph.facebook.com/{self.settings.meta_api_version}/{page_id}/subscribed_apps"

            response = await client.post(
                subscribe_url,
                params={"access_token": page_access_token},
                json={
                    "subscribed_fields": [
                        "messages",
                        "messaging_postbacks",
                        "messaging_optins",
                        "messaging_referrals",
                        "message_reads",
                        "message_deliveries",
                    ],
                },
            )

            if response.status_code == 200:
                logger.info(f"Subscribed Page {page_id} to webhook events")
                return {"success": True, "page_id": page_id}
            else:
                error = response.json()
                logger.error(f"Failed to subscribe Page: {error}")
                return {"success": False, "error": error}

    # =========================================================================
    # Token Management
    # =========================================================================

    async def validate_token(self, access_token: str) -> Dict[str, Any]:
        """
        Validate an access token and check its permissions.

        Returns:
            Token info including scopes and expiration
        """
        async with httpx.AsyncClient() as client:
            debug_url = f"https://graph.facebook.com/{self.settings.meta_api_version}/debug_token"

            response = await client.get(
                debug_url,
                params={
                    "input_token": access_token,
                    "access_token": f"{self.settings.meta_app_id}|{self.settings.meta_app_secret}",
                },
            )

            if response.status_code == 200:
                data = response.json().get("data", {})
                return {
                    "is_valid": data.get("is_valid", False),
                    "scopes": data.get("scopes", []),
                    "expires_at": data.get("expires_at"),
                    "user_id": data.get("user_id"),
                }

            return {"is_valid": False, "error": response.text}

    async def get_system_user_token(self, waba_id: str) -> Optional[str]:
        """
        Get a System User token for a WABA (required for production WhatsApp).

        Note: This requires Business Manager admin access and is typically
        done during initial setup, not OAuth.
        """
        # System User tokens are created in Business Manager
        # This is a placeholder for documentation
        # In production, you would create a System User and assign it to the WABA
        logger.warning(
            "System User tokens should be created in Meta Business Manager. "
            "See: https://developers.facebook.com/docs/whatsapp/cloud-api/get-started"
        )
        return None


# Singleton instance
_crm_oauth_manager: Optional[CRMOAuthManager] = None


def get_crm_oauth_manager(redis_client=None) -> CRMOAuthManager:
    """Get or create the CRM OAuth manager singleton."""
    global _crm_oauth_manager
    if _crm_oauth_manager is None:
        _crm_oauth_manager = CRMOAuthManager(redis_client)
    return _crm_oauth_manager
