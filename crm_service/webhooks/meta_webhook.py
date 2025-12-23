"""
Meta Webhook Handler - Unified webhook for WhatsApp, Instagram DM, and Messenger

Handles all incoming webhook events from Meta platforms:
- Message received (text, media, interactive)
- Message status updates (sent, delivered, read)
- Click-to-WhatsApp referrals (for attribution)
- QR Code check-ins (for visit tracking)

Webhook URL: POST /api/webhooks/meta
Verification: GET /api/webhooks/meta?hub.mode=subscribe&hub.verify_token=...
"""

import logging
import hmac
import hashlib
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta
from enum import Enum

from ..config import get_crm_settings
from ..models import (
    Channel,
    MessageType,
    MessageDirection,
    MessageStatus,
    WebhookEventResponse,
)

logger = logging.getLogger(__name__)


class WebhookEventType(str, Enum):
    """Types of webhook events we handle."""
    MESSAGE_RECEIVED = "message_received"
    MESSAGE_STATUS = "message_status"
    CHECKIN = "checkin"
    REFERRAL = "referral"  # Click-to-WhatsApp/Instagram


class MetaWebhookHandler:
    """
    Handles incoming webhook events from Meta platforms.

    Processes events and creates/updates:
    - Customer records
    - Conversation threads
    - Messages
    - Conversion events (for check-ins)
    """

    def __init__(self):
        self.settings = get_crm_settings()
        self.checkin_prefix = self.settings.checkin_message_prefix
        self.checkin_auto_reply = self.settings.checkin_auto_reply

    def verify_signature(self, payload: bytes, signature: str) -> bool:
        """
        Verify webhook signature from Meta.

        Args:
            payload: Raw request body
            signature: X-Hub-Signature-256 header value

        Returns:
            True if signature is valid
        """
        if not signature:
            return False

        expected_signature = hmac.new(
            self.settings.meta_app_secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()

        # Signature format: sha256=...
        provided = signature.replace("sha256=", "")

        return hmac.compare_digest(expected_signature, provided)

    async def handle_webhook(
        self, payload: Dict[str, Any], user_id: str
    ) -> List[WebhookEventResponse]:
        """
        Process a webhook payload from Meta.

        Args:
            payload: Parsed webhook JSON payload
            user_id: Owner's Clerk user ID (from platform lookup)

        Returns:
            List of processed event responses
        """
        results = []

        # Meta sends webhooks in batches
        for entry in payload.get("entry", []):
            # WhatsApp uses "changes", Messenger/Instagram use "messaging"
            if "changes" in entry:
                # WhatsApp Cloud API format
                for change in entry["changes"]:
                    if change.get("field") == "messages":
                        result = await self._handle_whatsapp_change(
                            change.get("value", {}), user_id
                        )
                        if result:
                            results.append(result)

            elif "messaging" in entry:
                # Messenger/Instagram format
                for event in entry["messaging"]:
                    result = await self._handle_messaging_event(event, user_id)
                    if result:
                        results.append(result)

        return results

    async def _handle_whatsapp_change(
        self, value: Dict[str, Any], user_id: str
    ) -> Optional[WebhookEventResponse]:
        """Handle a WhatsApp webhook change event."""
        from database.database import SessionLocal
        from database.models import (
            Customer,
            Conversation,
            Message,
            ConversionEvent,
            MessagingPlatform,
        )

        # Extract metadata
        metadata = value.get("metadata", {})
        phone_number_id = metadata.get("phone_number_id")

        # Process messages
        messages = value.get("messages", [])
        if not messages:
            # Might be a status update
            return await self._handle_whatsapp_status(value)

        db = SessionLocal()
        try:
            # Get the messaging platform for this phone_number_id
            platform = (
                db.query(MessagingPlatform)
                .filter(MessagingPlatform.phone_number_id == phone_number_id)
                .first()
            )

            if not platform:
                logger.warning(f"No platform found for phone_number_id: {phone_number_id}")
                return None

            for msg in messages:
                # Extract sender info
                from_number = msg.get("from")  # Sender's phone number
                message_id = msg.get("id")
                timestamp = datetime.fromtimestamp(int(msg.get("timestamp", 0)))

                # Get message content
                msg_type = msg.get("type", "text")
                text_content = None
                media_url = None

                if msg_type == "text":
                    text_content = msg.get("text", {}).get("body")
                elif msg_type == "image":
                    media_url = msg.get("image", {}).get("id")  # Media ID, not URL
                    text_content = msg.get("image", {}).get("caption")
                elif msg_type == "interactive":
                    # Button click or list selection
                    interactive = msg.get("interactive", {})
                    if "button_reply" in interactive:
                        text_content = interactive["button_reply"].get("title")
                    elif "list_reply" in interactive:
                        text_content = interactive["list_reply"].get("title")

                # Check for referral (Click-to-WhatsApp attribution)
                referral = msg.get("referral")
                ctwa_clid = None
                source_campaign_id = None

                if referral:
                    ctwa_clid = referral.get("ctwa_clid")
                    # TODO: Look up campaign from ctwa_clid

                # Check if this is a check-in message
                is_checkin = False
                if text_content and text_content.upper().startswith(self.checkin_prefix):
                    is_checkin = True

                # Find or create customer
                customer = (
                    db.query(Customer)
                    .filter(
                        Customer.user_id == platform.user_id,
                        Customer.phone_number == f"+{from_number}",
                    )
                    .first()
                )

                is_new_customer = False
                if not customer:
                    is_new_customer = True
                    customer = Customer(
                        user_id=platform.user_id,
                        phone_number=f"+{from_number}",
                        whatsapp_id=from_number,
                        source_channel="whatsapp",
                        ctwa_clid=ctwa_clid,
                        source_campaign_id=source_campaign_id,
                        lifecycle_stage="lead",
                    )
                    db.add(customer)
                    db.flush()  # Get the customer ID

                    logger.info(f"Created new customer from WhatsApp: {customer.id}")

                # Find or create conversation
                conversation = (
                    db.query(Conversation)
                    .filter(
                        Conversation.customer_id == customer.id,
                        Conversation.channel == "whatsapp",
                        Conversation.status != "closed",
                    )
                    .first()
                )

                if not conversation:
                    conversation = Conversation(
                        customer_id=customer.id,
                        user_id=platform.user_id,
                        channel="whatsapp",
                        status="open",
                        is_unread=True,
                        ctwa_clid=ctwa_clid,
                        source_campaign_id=source_campaign_id,
                    )
                    db.add(conversation)
                    db.flush()

                # Update conversation with new message
                conversation.last_customer_message_at = timestamp
                conversation.is_unread = True
                # 24-hour window for free replies
                conversation.window_expires_at = timestamp + timedelta(hours=24)

                # Create message record
                message = Message(
                    conversation_id=conversation.id,
                    external_message_id=message_id,
                    direction="inbound",
                    message_type="checkin" if is_checkin else msg_type,
                    content=text_content,
                    media_url=media_url,
                    status="delivered",
                )
                db.add(message)
                db.flush()

                # Handle check-in
                if is_checkin:
                    # Extract check-in code
                    checkin_code = text_content.upper().replace(self.checkin_prefix, "").strip()

                    # Verify this is the right business
                    if platform.checkin_code and checkin_code == platform.checkin_code.upper():
                        # Record the visit
                        customer.visit_count = (customer.visit_count or 0) + 1
                        customer.last_visit_at = timestamp

                        # Update lifecycle stage
                        if customer.visit_count >= 2:
                            customer.lifecycle_stage = "repeat"
                        elif customer.lifecycle_stage == "lead":
                            customer.lifecycle_stage = "customer"

                        # Create conversion event
                        visit_event = ConversionEvent(
                            customer_id=customer.id,
                            event_name="Visit",
                            event_source="checkin",
                            campaign_id=customer.source_campaign_id,
                            click_id=customer.ctwa_clid,
                        )
                        db.add(visit_event)

                        logger.info(
                            f"Check-in recorded for customer {customer.id}, "
                            f"visit #{customer.visit_count}"
                        )

                        # TODO: Send auto-reply
                        # TODO: Schedule review request

                db.commit()

                return WebhookEventResponse(
                    success=True,
                    customer_id=customer.id,
                    conversation_id=conversation.id,
                    message_id=message.id,
                    is_checkin=is_checkin,
                    is_new_customer=is_new_customer,
                )

        except Exception as e:
            logger.error(f"Error handling WhatsApp webhook: {e}")
            db.rollback()
            return WebhookEventResponse(success=False)

        finally:
            db.close()

        return None

    async def _handle_whatsapp_status(
        self, value: Dict[str, Any]
    ) -> Optional[WebhookEventResponse]:
        """Handle WhatsApp message status updates."""
        from database.database import SessionLocal
        from database.models import Message

        statuses = value.get("statuses", [])
        if not statuses:
            return None

        db = SessionLocal()
        try:
            for status in statuses:
                message_id = status.get("id")
                status_value = status.get("status")  # sent, delivered, read, failed
                timestamp = datetime.fromtimestamp(int(status.get("timestamp", 0)))

                # Find the message
                message = (
                    db.query(Message)
                    .filter(Message.external_message_id == message_id)
                    .first()
                )

                if message:
                    message.status = status_value
                    if status_value == "sent":
                        message.sent_at = timestamp
                    elif status_value == "delivered":
                        message.delivered_at = timestamp
                    elif status_value == "read":
                        message.read_at = timestamp
                    elif status_value == "failed":
                        error = status.get("errors", [{}])[0]
                        message.error_message = error.get("message")

            db.commit()
            return WebhookEventResponse(success=True)

        except Exception as e:
            logger.error(f"Error handling status update: {e}")
            db.rollback()
            return WebhookEventResponse(success=False)

        finally:
            db.close()

    async def _handle_messaging_event(
        self, event: Dict[str, Any], user_id: str
    ) -> Optional[WebhookEventResponse]:
        """
        Handle Messenger/Instagram messaging events.

        Similar structure to WhatsApp but different payload format.
        """
        from database.database import SessionLocal
        from database.models import (
            Customer,
            Conversation,
            Message,
            MessagingPlatform,
        )

        # Determine channel from event structure
        # Instagram has 'instagram' in the page_id field pattern
        sender_id = event.get("sender", {}).get("id")
        recipient_id = event.get("recipient", {}).get("id")
        timestamp = datetime.fromtimestamp(event.get("timestamp", 0) / 1000)

        if not sender_id or not recipient_id:
            return None

        db = SessionLocal()
        try:
            # Determine if this is Instagram or Messenger
            # Instagram page IDs are typically longer numbers
            platform = (
                db.query(MessagingPlatform)
                .filter(
                    (MessagingPlatform.page_id == recipient_id) |
                    (MessagingPlatform.instagram_account_id == recipient_id)
                )
                .first()
            )

            if not platform:
                logger.warning(f"No platform found for recipient: {recipient_id}")
                return None

            # Determine channel
            channel = "messenger"
            if platform.instagram_account_id == recipient_id:
                channel = "instagram"

            # Get message content
            message_data = event.get("message", {})
            text_content = message_data.get("text")
            attachments = message_data.get("attachments", [])

            media_url = None
            msg_type = "text"
            if attachments:
                attachment = attachments[0]
                msg_type = attachment.get("type", "text")
                media_url = attachment.get("payload", {}).get("url")

            # Find or create customer
            if channel == "instagram":
                customer = (
                    db.query(Customer)
                    .filter(
                        Customer.user_id == platform.user_id,
                        Customer.instagram_id == sender_id,
                    )
                    .first()
                )
            else:
                customer = (
                    db.query(Customer)
                    .filter(
                        Customer.user_id == platform.user_id,
                        Customer.messenger_id == sender_id,
                    )
                    .first()
                )

            is_new_customer = False
            if not customer:
                is_new_customer = True
                customer = Customer(
                    user_id=platform.user_id,
                    instagram_id=sender_id if channel == "instagram" else None,
                    messenger_id=sender_id if channel == "messenger" else None,
                    source_channel=channel,
                    lifecycle_stage="lead",
                )
                db.add(customer)
                db.flush()

            # Find or create conversation
            conversation = (
                db.query(Conversation)
                .filter(
                    Conversation.customer_id == customer.id,
                    Conversation.channel == channel,
                    Conversation.status != "closed",
                )
                .first()
            )

            if not conversation:
                conversation = Conversation(
                    customer_id=customer.id,
                    user_id=platform.user_id,
                    channel=channel,
                    status="open",
                    is_unread=True,
                )
                db.add(conversation)
                db.flush()

            # Update conversation
            conversation.last_customer_message_at = timestamp
            conversation.is_unread = True
            conversation.window_expires_at = timestamp + timedelta(hours=24)

            # Create message
            message = Message(
                conversation_id=conversation.id,
                external_message_id=message_data.get("mid"),
                direction="inbound",
                message_type=msg_type,
                content=text_content,
                media_url=media_url,
                status="delivered",
            )
            db.add(message)

            db.commit()

            return WebhookEventResponse(
                success=True,
                customer_id=customer.id,
                conversation_id=conversation.id,
                message_id=message.id,
                is_new_customer=is_new_customer,
            )

        except Exception as e:
            logger.error(f"Error handling messaging event: {e}")
            db.rollback()
            return WebhookEventResponse(success=False)

        finally:
            db.close()


# Singleton instance
_webhook_handler: Optional[MetaWebhookHandler] = None


def get_webhook_handler() -> MetaWebhookHandler:
    """Get or create the webhook handler singleton."""
    global _webhook_handler
    if _webhook_handler is None:
        _webhook_handler = MetaWebhookHandler()
    return _webhook_handler
