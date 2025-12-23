"""
Meta Messaging Client - Unified interface for WhatsApp, Instagram DM, and Messenger

All three channels use Meta Graph API with similar patterns.
WhatsApp Cloud API: Send via phone_number_id
Instagram: Send via instagram_scoped_id
Messenger: Send via page_scoped_id

Docs:
- WhatsApp: https://developers.facebook.com/docs/whatsapp/cloud-api
- Instagram: https://developers.facebook.com/docs/instagram-api/guides/messaging
- Messenger: https://developers.facebook.com/docs/messenger-platform
"""

import asyncio
import logging
import httpx
from typing import Optional, Dict, Any, List
from datetime import datetime
from functools import partial
from enum import Enum

from ..config import get_crm_settings

logger = logging.getLogger(__name__)


class MessageChannel(str, Enum):
    """Messaging channel types."""
    WHATSAPP = "whatsapp"
    INSTAGRAM = "instagram"
    MESSENGER = "messenger"


class MetaMessagingClient:
    """
    Unified client for Meta messaging platforms.

    Handles WhatsApp Cloud API, Instagram DM, and Messenger
    through the Meta Graph API.
    """

    def __init__(
        self,
        access_token: str,
        phone_number_id: Optional[str] = None,
        instagram_account_id: Optional[str] = None,
        page_id: Optional[str] = None,
    ):
        """
        Initialize the messaging client.

        Args:
            access_token: System User or User access token with messaging permissions
            phone_number_id: WhatsApp Cloud API phone number ID
            instagram_account_id: Instagram business account ID
            page_id: Facebook Page ID for Messenger
        """
        self.access_token = access_token
        self.phone_number_id = phone_number_id
        self.instagram_account_id = instagram_account_id
        self.page_id = page_id

        settings = get_crm_settings()
        self.api_version = settings.meta_api_version
        self.base_url = f"https://graph.facebook.com/{self.api_version}"

        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    # =========================================================================
    # WhatsApp Cloud API
    # =========================================================================

    async def send_whatsapp_text(
        self,
        to: str,
        text: str,
        preview_url: bool = False,
    ) -> Dict[str, Any]:
        """
        Send a text message via WhatsApp.

        Args:
            to: Recipient phone number in E.164 format (e.g., +14155551234)
            text: Message text
            preview_url: Whether to show URL previews

        Returns:
            API response with message ID
        """
        if not self.phone_number_id:
            raise ValueError("phone_number_id required for WhatsApp messaging")

        client = await self._get_client()

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to.lstrip("+"),  # WhatsApp expects without +
            "type": "text",
            "text": {
                "preview_url": preview_url,
                "body": text,
            },
        }

        response = await client.post(
            f"/{self.phone_number_id}/messages",
            json=payload,
        )

        result = response.json()
        if response.status_code != 200:
            logger.error(f"WhatsApp send failed: {result}")
            raise Exception(f"WhatsApp API error: {result.get('error', {}).get('message', 'Unknown')}")

        logger.info(f"WhatsApp message sent to {to}: {result.get('messages', [{}])[0].get('id')}")
        return result

    async def send_whatsapp_template(
        self,
        to: str,
        template_name: str,
        language_code: str = "en_US",
        components: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """
        Send a WhatsApp template message.

        Template messages can be sent outside the 24-hour window.

        Args:
            to: Recipient phone number
            template_name: Approved template name
            language_code: Template language
            components: Template components (header, body, buttons params)

        Returns:
            API response with message ID
        """
        if not self.phone_number_id:
            raise ValueError("phone_number_id required for WhatsApp messaging")

        client = await self._get_client()

        template_data = {
            "name": template_name,
            "language": {"code": language_code},
        }

        if components:
            template_data["components"] = components

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to.lstrip("+"),
            "type": "template",
            "template": template_data,
        }

        response = await client.post(
            f"/{self.phone_number_id}/messages",
            json=payload,
        )

        result = response.json()
        if response.status_code != 200:
            logger.error(f"WhatsApp template send failed: {result}")
            raise Exception(f"WhatsApp API error: {result.get('error', {}).get('message', 'Unknown')}")

        return result

    async def send_whatsapp_media(
        self,
        to: str,
        media_type: str,  # image, video, audio, document
        media_url: str,
        caption: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a media message via WhatsApp.

        Args:
            to: Recipient phone number
            media_type: Type of media (image, video, audio, document)
            media_url: URL of the media
            caption: Optional caption (for image/video)

        Returns:
            API response with message ID
        """
        if not self.phone_number_id:
            raise ValueError("phone_number_id required for WhatsApp messaging")

        client = await self._get_client()

        media_object = {"link": media_url}
        if caption and media_type in ["image", "video"]:
            media_object["caption"] = caption

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to.lstrip("+"),
            "type": media_type,
            media_type: media_object,
        }

        response = await client.post(
            f"/{self.phone_number_id}/messages",
            json=payload,
        )

        return response.json()

    async def mark_whatsapp_read(self, message_id: str) -> Dict[str, Any]:
        """Mark a WhatsApp message as read."""
        if not self.phone_number_id:
            raise ValueError("phone_number_id required for WhatsApp messaging")

        client = await self._get_client()

        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }

        response = await client.post(
            f"/{self.phone_number_id}/messages",
            json=payload,
        )

        return response.json()

    # =========================================================================
    # Instagram Direct Messages
    # =========================================================================

    async def send_instagram_text(
        self,
        recipient_id: str,
        text: str,
    ) -> Dict[str, Any]:
        """
        Send a text message via Instagram DM.

        Args:
            recipient_id: Instagram-scoped user ID
            text: Message text

        Returns:
            API response with message ID
        """
        if not self.instagram_account_id:
            raise ValueError("instagram_account_id required for Instagram messaging")

        client = await self._get_client()

        payload = {
            "recipient": {"id": recipient_id},
            "message": {"text": text},
        }

        response = await client.post(
            f"/{self.instagram_account_id}/messages",
            json=payload,
        )

        result = response.json()
        if response.status_code != 200:
            logger.error(f"Instagram send failed: {result}")
            raise Exception(f"Instagram API error: {result.get('error', {}).get('message', 'Unknown')}")

        return result

    async def send_instagram_media(
        self,
        recipient_id: str,
        media_url: str,
    ) -> Dict[str, Any]:
        """
        Send an image via Instagram DM.

        Args:
            recipient_id: Instagram-scoped user ID
            media_url: URL of the image

        Returns:
            API response with message ID
        """
        if not self.instagram_account_id:
            raise ValueError("instagram_account_id required for Instagram messaging")

        client = await self._get_client()

        payload = {
            "recipient": {"id": recipient_id},
            "message": {
                "attachment": {
                    "type": "image",
                    "payload": {"url": media_url},
                }
            },
        }

        response = await client.post(
            f"/{self.instagram_account_id}/messages",
            json=payload,
        )

        return response.json()

    async def get_instagram_conversations(
        self,
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        """Get Instagram DM conversations."""
        if not self.instagram_account_id:
            raise ValueError("instagram_account_id required for Instagram messaging")

        client = await self._get_client()

        response = await client.get(
            f"/{self.instagram_account_id}/conversations",
            params={"limit": limit},
        )

        result = response.json()
        return result.get("data", [])

    # =========================================================================
    # Facebook Messenger
    # =========================================================================

    async def send_messenger_text(
        self,
        recipient_id: str,
        text: str,
    ) -> Dict[str, Any]:
        """
        Send a text message via Messenger.

        Args:
            recipient_id: Page-scoped user ID
            text: Message text

        Returns:
            API response with message ID
        """
        if not self.page_id:
            raise ValueError("page_id required for Messenger")

        client = await self._get_client()

        payload = {
            "recipient": {"id": recipient_id},
            "message": {"text": text},
            "messaging_type": "RESPONSE",
        }

        response = await client.post(
            f"/{self.page_id}/messages",
            json=payload,
        )

        result = response.json()
        if response.status_code != 200:
            logger.error(f"Messenger send failed: {result}")
            raise Exception(f"Messenger API error: {result.get('error', {}).get('message', 'Unknown')}")

        return result

    async def send_messenger_media(
        self,
        recipient_id: str,
        media_type: str,  # image, audio, video, file
        media_url: str,
    ) -> Dict[str, Any]:
        """
        Send media via Messenger.

        Args:
            recipient_id: Page-scoped user ID
            media_type: Type of media
            media_url: URL of the media

        Returns:
            API response with message ID
        """
        if not self.page_id:
            raise ValueError("page_id required for Messenger")

        client = await self._get_client()

        payload = {
            "recipient": {"id": recipient_id},
            "message": {
                "attachment": {
                    "type": media_type,
                    "payload": {"url": media_url, "is_reusable": True},
                }
            },
            "messaging_type": "RESPONSE",
        }

        response = await client.post(
            f"/{self.page_id}/messages",
            json=payload,
        )

        return response.json()

    # =========================================================================
    # Unified Send Method
    # =========================================================================

    async def send_message(
        self,
        channel: MessageChannel,
        recipient_id: str,
        text: Optional[str] = None,
        media_url: Optional[str] = None,
        media_type: Optional[str] = None,
        template_name: Optional[str] = None,
        template_params: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Unified method to send a message across any channel.

        Args:
            channel: WhatsApp, Instagram, or Messenger
            recipient_id: Channel-specific recipient ID
            text: Text message content
            media_url: Optional media URL
            media_type: Type of media if sending media
            template_name: WhatsApp template name (for outside 24hr window)
            template_params: Template parameters

        Returns:
            API response with message ID
        """
        if channel == MessageChannel.WHATSAPP:
            if template_name:
                # Build template components from params
                components = None
                if template_params:
                    components = [{
                        "type": "body",
                        "parameters": [{"type": "text", "text": p} for p in template_params],
                    }]
                return await self.send_whatsapp_template(
                    to=recipient_id,
                    template_name=template_name,
                    components=components,
                )
            elif media_url and media_type:
                return await self.send_whatsapp_media(
                    to=recipient_id,
                    media_type=media_type,
                    media_url=media_url,
                    caption=text,
                )
            else:
                return await self.send_whatsapp_text(to=recipient_id, text=text)

        elif channel == MessageChannel.INSTAGRAM:
            if media_url:
                return await self.send_instagram_media(
                    recipient_id=recipient_id,
                    media_url=media_url,
                )
            else:
                return await self.send_instagram_text(
                    recipient_id=recipient_id,
                    text=text,
                )

        elif channel == MessageChannel.MESSENGER:
            if media_url and media_type:
                return await self.send_messenger_media(
                    recipient_id=recipient_id,
                    media_type=media_type,
                    media_url=media_url,
                )
            else:
                return await self.send_messenger_text(
                    recipient_id=recipient_id,
                    text=text,
                )

        else:
            raise ValueError(f"Unknown channel: {channel}")

    # =========================================================================
    # Profile Fetching
    # =========================================================================

    async def get_whatsapp_profile(self, phone_number: str) -> Dict[str, Any]:
        """Get WhatsApp user profile info (limited data available)."""
        # WhatsApp Cloud API doesn't expose profile data directly
        # Profile pic comes from webhook
        return {"phone_number": phone_number}

    async def get_instagram_profile(self, user_id: str) -> Dict[str, Any]:
        """Get Instagram user profile."""
        client = await self._get_client()

        response = await client.get(
            f"/{user_id}",
            params={"fields": "id,username,name,profile_pic"},
        )

        return response.json()

    async def get_messenger_profile(self, user_id: str) -> Dict[str, Any]:
        """Get Messenger user profile."""
        client = await self._get_client()

        response = await client.get(
            f"/{user_id}",
            params={"fields": "id,first_name,last_name,profile_pic"},
        )

        return response.json()

    # =========================================================================
    # Webhook Subscription
    # =========================================================================

    async def subscribe_to_webhooks(self, callback_url: str, verify_token: str) -> Dict[str, Any]:
        """
        Subscribe to webhook updates.

        Note: This is typically done once during setup, not per-user.
        """
        client = await self._get_client()

        # Subscribe the app to the Page/WABA webhooks
        if self.page_id:
            response = await client.post(
                f"/{self.page_id}/subscribed_apps",
                json={
                    "subscribed_fields": ["messages", "messaging_postbacks"],
                },
            )
            return response.json()

        return {"status": "no page_id configured"}


# =============================================================================
# Factory Function
# =============================================================================


def create_messaging_client(
    access_token: str,
    phone_number_id: Optional[str] = None,
    instagram_account_id: Optional[str] = None,
    page_id: Optional[str] = None,
) -> MetaMessagingClient:
    """Create a Meta Messaging client instance."""
    return MetaMessagingClient(
        access_token=access_token,
        phone_number_id=phone_number_id,
        instagram_account_id=instagram_account_id,
        page_id=page_id,
    )


async def create_client_for_user(user_id: str) -> MetaMessagingClient:
    """
    Create a messaging client with credentials from the database.

    Args:
        user_id: Clerk user ID

    Returns:
        Configured MetaMessagingClient
    """
    from database.database import SessionLocal
    from database.models import MessagingPlatform, MessagingCredential
    from ads_service.routes import TokenEncryptionService

    db = SessionLocal()
    try:
        # Get user's messaging platform
        platform = (
            db.query(MessagingPlatform)
            .filter(
                MessagingPlatform.user_id == user_id,
                MessagingPlatform.is_connected == True,
            )
            .first()
        )

        if not platform:
            raise ValueError(f"No connected messaging platform for user {user_id}")

        # Get credentials
        credential = (
            db.query(MessagingCredential)
            .filter(MessagingCredential.platform_id == platform.id)
            .first()
        )

        if not credential:
            raise ValueError(f"No credentials found for platform {platform.id}")

        # Decrypt access token
        encryption = TokenEncryptionService()
        access_token = encryption.decrypt_token(credential.encrypted_access_token)

        return MetaMessagingClient(
            access_token=access_token,
            phone_number_id=platform.phone_number_id,
            instagram_account_id=platform.instagram_account_id,
            page_id=platform.page_id,
        )

    finally:
        db.close()
