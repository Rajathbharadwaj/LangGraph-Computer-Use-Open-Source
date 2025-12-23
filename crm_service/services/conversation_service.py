"""
Conversation Service - Unified inbox management

Handles:
- Conversation listing (unified inbox)
- Message thread retrieval
- Message sending via appropriate channel
- AI draft generation
- 24-hour window tracking
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy import or_, and_, func, desc
from sqlalchemy.orm import Session

from database.database import SessionLocal
from database.models import (
    Customer,
    Conversation,
    Message,
    MessagingPlatform,
    MessagingCredential,
)
from ..models import (
    Channel,
    ConversationStatus,
    MessageDirection,
    MessageType,
    MessageStatus,
    ConversationResponse,
    ConversationListResponse,
    ConversationUpdateRequest,
    MessageResponse,
    MessageThreadResponse,
    SendMessageRequest,
    DraftReplyRequest,
    DraftReplyResponse,
)
from ..clients.meta_messaging import MetaMessagingClient, MessageChannel

logger = logging.getLogger(__name__)


class ConversationService:
    """
    Service for unified inbox and conversation management.
    """

    def __init__(self, db: Optional[Session] = None):
        """
        Initialize conversation service.

        Args:
            db: Optional database session.
        """
        self._db = db

    def _get_db(self) -> Session:
        """Get or create database session."""
        if self._db:
            return self._db
        return SessionLocal()

    def _close_db(self, db: Session):
        """Close database session if we created it."""
        if not self._db:
            db.close()

    # =========================================================================
    # Inbox (Conversation List)
    # =========================================================================

    def get_inbox(
        self,
        user_id: str,
        status: Optional[ConversationStatus] = None,
        channel: Optional[Channel] = None,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> ConversationListResponse:
        """
        Get unified inbox for a user.

        Args:
            user_id: Owner's Clerk user ID
            status: Filter by status
            channel: Filter by channel
            unread_only: Only show unread conversations
            limit: Max results
            offset: Pagination offset

        Returns:
            List of conversations with metadata
        """
        db = self._get_db()
        try:
            query = db.query(Conversation).filter(Conversation.user_id == user_id)

            # Apply filters
            if status:
                query = query.filter(Conversation.status == status.value)

            if channel:
                query = query.filter(Conversation.channel == channel.value)

            if unread_only:
                query = query.filter(Conversation.is_unread == True)

            # Get total and unread counts
            total = query.count()
            unread_count = (
                db.query(Conversation)
                .filter(
                    Conversation.user_id == user_id,
                    Conversation.is_unread == True,
                )
                .count()
            )

            # Order by last message, get page
            conversations = (
                query.order_by(desc(Conversation.last_customer_message_at))
                .offset(offset)
                .limit(limit)
                .all()
            )

            return ConversationListResponse(
                conversations=[self._to_conversation_response(db, c) for c in conversations],
                total=total,
                unread_count=unread_count,
            )

        finally:
            self._close_db(db)

    def get_conversation(
        self, user_id: str, conversation_id: int
    ) -> Optional[ConversationResponse]:
        """Get a single conversation."""
        db = self._get_db()
        try:
            conversation = (
                db.query(Conversation)
                .filter(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user_id,
                )
                .first()
            )

            if not conversation:
                return None

            return self._to_conversation_response(db, conversation)

        finally:
            self._close_db(db)

    def update_conversation(
        self, user_id: str, conversation_id: int, data: ConversationUpdateRequest
    ) -> Optional[ConversationResponse]:
        """Update conversation status or read state."""
        db = self._get_db()
        try:
            conversation = (
                db.query(Conversation)
                .filter(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user_id,
                )
                .first()
            )

            if not conversation:
                return None

            if data.status is not None:
                conversation.status = data.status.value

            if data.is_unread is not None:
                conversation.is_unread = data.is_unread

            db.commit()

            return self._to_conversation_response(db, conversation)

        finally:
            self._close_db(db)

    # =========================================================================
    # Messages
    # =========================================================================

    def get_messages(
        self,
        user_id: str,
        conversation_id: int,
        limit: int = 100,
        before_id: Optional[int] = None,
    ) -> Optional[MessageThreadResponse]:
        """
        Get messages in a conversation thread.

        Args:
            user_id: Owner's Clerk user ID
            conversation_id: Conversation ID
            limit: Max messages to return
            before_id: Get messages before this ID (for pagination)

        Returns:
            Conversation with message list
        """
        db = self._get_db()
        try:
            # Verify ownership
            conversation = (
                db.query(Conversation)
                .filter(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user_id,
                )
                .first()
            )

            if not conversation:
                return None

            # Build message query
            query = db.query(Message).filter(Message.conversation_id == conversation_id)

            if before_id:
                query = query.filter(Message.id < before_id)

            # Get total count
            total = db.query(Message).filter(Message.conversation_id == conversation_id).count()

            # Get messages (newest first)
            messages = (
                query.order_by(desc(Message.created_at))
                .limit(limit)
                .all()
            )

            # Reverse to chronological order
            messages = list(reversed(messages))

            # Mark as read
            if conversation.is_unread:
                conversation.is_unread = False
                db.commit()

            return MessageThreadResponse(
                conversation=self._to_conversation_response(db, conversation),
                messages=[self._to_message_response(m) for m in messages],
                total_messages=total,
            )

        finally:
            self._close_db(db)

    async def send_message(
        self,
        user_id: str,
        conversation_id: int,
        data: SendMessageRequest,
    ) -> Optional[MessageResponse]:
        """
        Send a message in a conversation.

        Automatically uses the appropriate channel (WhatsApp, Instagram, Messenger).

        Args:
            user_id: Owner's Clerk user ID
            conversation_id: Conversation ID
            data: Message to send

        Returns:
            Sent message response
        """
        db = self._get_db()
        try:
            # Get conversation and customer
            conversation = (
                db.query(Conversation)
                .filter(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user_id,
                )
                .first()
            )

            if not conversation:
                return None

            customer = db.query(Customer).filter(Customer.id == conversation.customer_id).first()
            if not customer:
                return None

            # Check 24-hour window
            window_open = True
            if conversation.window_expires_at:
                window_open = datetime.utcnow() < conversation.window_expires_at

            # If window closed and no template, fail
            if not window_open and not data.template_name:
                raise ValueError(
                    "24-hour window expired. Use a template message or wait for customer to message."
                )

            # Get messaging platform and credentials
            platform = (
                db.query(MessagingPlatform)
                .filter(MessagingPlatform.user_id == user_id)
                .first()
            )

            if not platform:
                raise ValueError("No messaging platform connected")

            credential = (
                db.query(MessagingCredential)
                .filter(MessagingCredential.platform_id == platform.id)
                .first()
            )

            if not credential:
                raise ValueError("No credentials found")

            # Decrypt token
            from ads_service.routes import TokenEncryptionService
            encryption = TokenEncryptionService()
            access_token = encryption.decrypt_token(credential.encrypted_access_token)

            # Create messaging client
            client = MetaMessagingClient(
                access_token=access_token,
                phone_number_id=platform.phone_number_id,
                instagram_account_id=platform.instagram_account_id,
                page_id=platform.page_id,
            )

            # Determine recipient ID based on channel
            channel = MessageChannel(conversation.channel)
            if channel == MessageChannel.WHATSAPP:
                recipient_id = customer.phone_number
            elif channel == MessageChannel.INSTAGRAM:
                recipient_id = customer.instagram_id
            else:
                recipient_id = customer.messenger_id

            # Create message record first (pending)
            message = Message(
                conversation_id=conversation_id,
                direction="outbound",
                message_type=data.message_type.value if data.message_type else "text",
                content=data.content,
                media_url=data.media_url,
                status="pending",
            )
            db.add(message)
            db.flush()

            # Send via API
            try:
                result = await client.send_message(
                    channel=channel,
                    recipient_id=recipient_id,
                    text=data.content,
                    media_url=data.media_url,
                    media_type=data.message_type.value if data.message_type and data.message_type != MessageType.TEXT else None,
                    template_name=data.template_name,
                    template_params=data.template_params,
                )

                # Update message with external ID
                if "messages" in result:
                    message.external_message_id = result["messages"][0].get("id")
                elif "message_id" in result:
                    message.external_message_id = result["message_id"]

                message.status = "sent"
                message.sent_at = datetime.utcnow()

            except Exception as e:
                message.status = "failed"
                message.error_message = str(e)
                logger.error(f"Failed to send message: {e}")

            db.commit()
            await client.close()

            return self._to_message_response(message)

        finally:
            self._close_db(db)

    # =========================================================================
    # AI Draft Generation
    # =========================================================================

    async def generate_draft_reply(
        self,
        user_id: str,
        conversation_id: int,
        request: DraftReplyRequest,
    ) -> Optional[DraftReplyResponse]:
        """
        Generate an AI-drafted reply for a conversation.

        Uses the CRM Deep Agent to generate contextual responses.

        Args:
            user_id: Owner's Clerk user ID
            conversation_id: Conversation ID
            request: Optional context for the AI

        Returns:
            Draft reply for approval
        """
        db = self._get_db()
        try:
            # Get conversation and recent messages
            conversation = (
                db.query(Conversation)
                .filter(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user_id,
                )
                .first()
            )

            if not conversation:
                return None

            # Get customer info
            customer = db.query(Customer).filter(Customer.id == conversation.customer_id).first()

            # Get last few messages for context
            recent_messages = (
                db.query(Message)
                .filter(Message.conversation_id == conversation_id)
                .order_by(desc(Message.created_at))
                .limit(10)
                .all()
            )

            # Build context for AI
            message_history = []
            for msg in reversed(recent_messages):
                role = "customer" if msg.direction == "inbound" else "business"
                message_history.append(f"{role}: {msg.content}")

            context = f"""
Customer: {customer.first_name or 'Unknown'} {customer.last_name or ''}
Phone: {customer.phone_number or 'N/A'}
Lifecycle: {customer.lifecycle_stage}
Visit Count: {customer.visit_count}
Total Spent: ${(customer.total_spent_cents or 0) / 100:.2f}

Recent conversation:
{chr(10).join(message_history)}
"""

            if request.context:
                context += f"\nAdditional context: {request.context}"

            # TODO: Call the CRM Deep Agent or a simpler LLM for draft generation
            # For now, return a placeholder
            draft_content = f"Hi {customer.first_name or 'there'}! Thanks for reaching out. How can I help you today?"

            # Create draft message (not sent)
            draft = Message(
                conversation_id=conversation_id,
                direction="outbound",
                message_type="text",
                content=draft_content,
                is_ai_drafted=True,
                ai_draft_approved=False,
                status="pending",
            )
            db.add(draft)
            db.commit()
            db.refresh(draft)

            return DraftReplyResponse(
                draft_id=draft.id,
                content=draft_content,
                suggested_followup=None,
            )

        finally:
            self._close_db(db)

    async def approve_and_send_draft(
        self, user_id: str, draft_id: int
    ) -> Optional[MessageResponse]:
        """Approve an AI draft and send it."""
        db = self._get_db()
        try:
            # Get the draft
            draft = db.query(Message).filter(Message.id == draft_id).first()

            if not draft or not draft.is_ai_drafted:
                return None

            # Verify ownership
            conversation = (
                db.query(Conversation)
                .filter(
                    Conversation.id == draft.conversation_id,
                    Conversation.user_id == user_id,
                )
                .first()
            )

            if not conversation:
                return None

            # Mark as approved
            draft.ai_draft_approved = True

            # Send the message
            request = SendMessageRequest(
                content=draft.content,
                message_type=MessageType.TEXT,
            )

            db.commit()

            # Use send_message to actually send
            return await self.send_message(
                user_id=user_id,
                conversation_id=conversation.id,
                data=request,
            )

        finally:
            self._close_db(db)

    # =========================================================================
    # Helpers
    # =========================================================================

    def _to_conversation_response(
        self, db: Session, conversation: Conversation
    ) -> ConversationResponse:
        """Convert database conversation to response model."""
        # Get customer info
        customer = db.query(Customer).filter(Customer.id == conversation.customer_id).first()

        # Get last message preview
        last_message = (
            db.query(Message)
            .filter(Message.conversation_id == conversation.id)
            .order_by(desc(Message.created_at))
            .first()
        )

        # Check if 24hr window is still open
        window_open = True
        if conversation.window_expires_at:
            window_open = datetime.utcnow() < conversation.window_expires_at

        customer_name = None
        if customer:
            parts = [customer.first_name, customer.last_name]
            customer_name = " ".join(p for p in parts if p) or None

        return ConversationResponse(
            id=conversation.id,
            customer_id=conversation.customer_id,
            customer_name=customer_name,
            customer_phone=customer.phone_number if customer else None,
            customer_profile_pic=customer.profile_picture_url if customer else None,
            channel=Channel(conversation.channel),
            status=ConversationStatus(conversation.status),
            is_unread=conversation.is_unread,
            last_message_preview=last_message.content[:100] if last_message and last_message.content else None,
            last_message_at=last_message.created_at if last_message else None,
            last_customer_message_at=conversation.last_customer_message_at,
            window_expires_at=conversation.window_expires_at,
            window_open=window_open,
            source_campaign_id=conversation.source_campaign_id,
            ctwa_clid=conversation.ctwa_clid,
            created_at=conversation.created_at,
        )

    def _to_message_response(self, message: Message) -> MessageResponse:
        """Convert database message to response model."""
        return MessageResponse(
            id=message.id,
            conversation_id=message.conversation_id,
            external_message_id=message.external_message_id,
            direction=MessageDirection(message.direction),
            message_type=MessageType(message.message_type) if message.message_type else MessageType.TEXT,
            content=message.content,
            media_url=message.media_url,
            is_ai_drafted=message.is_ai_drafted or False,
            ai_draft_approved=message.ai_draft_approved or False,
            status=MessageStatus(message.status) if message.status else MessageStatus.PENDING,
            error_message=message.error_message,
            created_at=message.created_at,
            sent_at=message.sent_at,
            delivered_at=message.delivered_at,
            read_at=message.read_at,
        )


# Convenience function
def get_conversation_service(db: Optional[Session] = None) -> ConversationService:
    """Get a conversation service instance."""
    return ConversationService(db)
