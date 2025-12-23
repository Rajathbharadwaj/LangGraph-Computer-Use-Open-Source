"""
Followup Scheduler - Automated follow-up message scheduling

Handles:
- Review request scheduling after visits
- Dormant customer reactivation
- Custom follow-up scheduling
- Follow-up execution (triggered by cron job)
"""

import logging
from typing import Optional, List
from datetime import datetime, timedelta
from sqlalchemy import and_
from sqlalchemy.orm import Session

from database.database import SessionLocal
from database.models import (
    Customer,
    AutomatedFollowup,
    MessagingPlatform,
    MessagingCredential,
)
from ..config import get_crm_settings
from ..models import (
    FollowupType,
    FollowupStatus,
    FollowupResponse,
    FollowupListResponse,
)

logger = logging.getLogger(__name__)


class FollowupScheduler:
    """
    Service for scheduling and executing automated follow-ups.
    """

    def __init__(self, db: Optional[Session] = None):
        """
        Initialize followup scheduler.

        Args:
            db: Optional database session.
        """
        self._db = db
        self.settings = get_crm_settings()

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
    # Scheduling Methods
    # =========================================================================

    def schedule_review_request(
        self, customer_id: int, hours_delay: Optional[int] = None
    ) -> Optional[datetime]:
        """
        Schedule a review request after a customer visit.

        Args:
            customer_id: Customer ID
            hours_delay: Hours to wait before sending (default from settings)

        Returns:
            Scheduled datetime or None if already scheduled
        """
        db = self._get_db()
        try:
            # Check if review request already pending for this customer
            existing = (
                db.query(AutomatedFollowup)
                .filter(
                    AutomatedFollowup.customer_id == customer_id,
                    AutomatedFollowup.followup_type == "review_request",
                    AutomatedFollowup.status == "scheduled",
                )
                .first()
            )

            if existing:
                logger.debug(f"Review request already scheduled for customer {customer_id}")
                return existing.scheduled_at

            # Check customer has a phone number
            customer = db.query(Customer).filter(Customer.id == customer_id).first()
            if not customer or not customer.phone_number:
                logger.warning(f"Cannot schedule review - no phone for customer {customer_id}")
                return None

            # Calculate scheduled time
            delay_hours = hours_delay or self.settings.review_request_delay_hours
            scheduled_at = datetime.utcnow() + timedelta(hours=delay_hours)

            # Create the followup
            followup = AutomatedFollowup(
                customer_id=customer_id,
                followup_type="review_request",
                scheduled_at=scheduled_at,
                status="scheduled",
                template_name="review_request",  # WhatsApp template name
            )
            db.add(followup)
            db.commit()

            logger.info(
                f"Scheduled review request for customer {customer_id} "
                f"at {scheduled_at}"
            )
            return scheduled_at

        except Exception as e:
            logger.error(f"Error scheduling review request: {e}")
            db.rollback()
            return None

        finally:
            self._close_db(db)

    def schedule_dormant_reactivation(
        self, customer_id: int, template_name: Optional[str] = None
    ) -> Optional[datetime]:
        """
        Schedule a reactivation message for a dormant customer.

        Args:
            customer_id: Customer ID
            template_name: WhatsApp template to use

        Returns:
            Scheduled datetime or None if failed
        """
        db = self._get_db()
        try:
            # Check customer qualifies as dormant
            customer = db.query(Customer).filter(Customer.id == customer_id).first()

            if not customer:
                return None

            if not customer.phone_number:
                logger.warning(f"Cannot schedule reactivation - no phone for customer {customer_id}")
                return None

            # Check if already has a recent reactivation
            existing = (
                db.query(AutomatedFollowup)
                .filter(
                    AutomatedFollowup.customer_id == customer_id,
                    AutomatedFollowup.followup_type == "dormant_reactivation",
                    AutomatedFollowup.status.in_(["scheduled", "sent"]),
                    AutomatedFollowup.created_at >= datetime.utcnow() - timedelta(days=30),
                )
                .first()
            )

            if existing:
                logger.debug(f"Recent reactivation exists for customer {customer_id}")
                return existing.scheduled_at

            # Schedule for immediate sending
            scheduled_at = datetime.utcnow()

            followup = AutomatedFollowup(
                customer_id=customer_id,
                followup_type="dormant_reactivation",
                scheduled_at=scheduled_at,
                status="scheduled",
                template_name=template_name or "reactivation",
            )
            db.add(followup)
            db.commit()

            logger.info(f"Scheduled dormant reactivation for customer {customer_id}")
            return scheduled_at

        except Exception as e:
            logger.error(f"Error scheduling reactivation: {e}")
            db.rollback()
            return None

        finally:
            self._close_db(db)

    def schedule_followup(
        self,
        customer_id: int,
        followup_type: FollowupType,
        scheduled_at: datetime,
        template_name: Optional[str] = None,
        custom_message: Optional[str] = None,
    ) -> Optional[datetime]:
        """
        Schedule a custom follow-up.

        Args:
            customer_id: Customer ID
            followup_type: Type of follow-up
            scheduled_at: When to send
            template_name: WhatsApp template (required if outside 24hr window)
            custom_message: Custom message content (if within 24hr window)

        Returns:
            Scheduled datetime or None if failed
        """
        db = self._get_db()
        try:
            customer = db.query(Customer).filter(Customer.id == customer_id).first()

            if not customer or not customer.phone_number:
                logger.warning(f"Cannot schedule followup - no phone for customer {customer_id}")
                return None

            followup = AutomatedFollowup(
                customer_id=customer_id,
                followup_type=followup_type.value,
                scheduled_at=scheduled_at,
                status="scheduled",
                template_name=template_name,
            )
            db.add(followup)
            db.commit()

            logger.info(
                f"Scheduled {followup_type.value} for customer {customer_id} "
                f"at {scheduled_at}"
            )
            return scheduled_at

        except Exception as e:
            logger.error(f"Error scheduling followup: {e}")
            db.rollback()
            return None

        finally:
            self._close_db(db)

    # =========================================================================
    # Listing Methods
    # =========================================================================

    def get_pending_followups(
        self, user_id: str, limit: int = 50
    ) -> FollowupListResponse:
        """
        Get all pending follow-ups for a user.

        Args:
            user_id: Owner's Clerk user ID
            limit: Max results

        Returns:
            List of pending follow-ups
        """
        db = self._get_db()
        try:
            # Get user's customers
            customer_ids = (
                db.query(Customer.id)
                .filter(Customer.user_id == user_id)
                .subquery()
            )

            followups = (
                db.query(AutomatedFollowup)
                .filter(
                    AutomatedFollowup.customer_id.in_(customer_ids),
                    AutomatedFollowup.status == "scheduled",
                )
                .order_by(AutomatedFollowup.scheduled_at)
                .limit(limit)
                .all()
            )

            result = []
            for f in followups:
                customer = db.query(Customer).filter(Customer.id == f.customer_id).first()
                customer_name = None
                if customer:
                    parts = [customer.first_name, customer.last_name]
                    customer_name = " ".join(p for p in parts if p) or None

                result.append(
                    FollowupResponse(
                        id=f.id,
                        customer_id=f.customer_id,
                        customer_name=customer_name,
                        followup_type=FollowupType(f.followup_type),
                        scheduled_at=f.scheduled_at,
                        status=FollowupStatus(f.status),
                        template_name=f.template_name,
                        sent_at=f.sent_at,
                        created_at=f.created_at,
                    )
                )

            return FollowupListResponse(followups=result, total=len(result))

        finally:
            self._close_db(db)

    def cancel_followup(self, followup_id: int) -> bool:
        """Cancel a scheduled follow-up."""
        db = self._get_db()
        try:
            followup = (
                db.query(AutomatedFollowup)
                .filter(
                    AutomatedFollowup.id == followup_id,
                    AutomatedFollowup.status == "scheduled",
                )
                .first()
            )

            if not followup:
                return False

            followup.status = "cancelled"
            db.commit()

            logger.info(f"Cancelled followup {followup_id}")
            return True

        except Exception as e:
            logger.error(f"Error cancelling followup: {e}")
            db.rollback()
            return False

        finally:
            self._close_db(db)

    # =========================================================================
    # Execution Methods (called by cron job)
    # =========================================================================

    async def execute_pending_followups(self, batch_size: int = 50) -> dict:
        """
        Execute all pending follow-ups that are due.

        This should be called by a cron job every few minutes.

        Args:
            batch_size: Max followups to process in one batch

        Returns:
            Dict with sent/failed counts
        """
        db = self._get_db()
        try:
            # Get followups that are due
            due_followups = (
                db.query(AutomatedFollowup)
                .filter(
                    AutomatedFollowup.status == "scheduled",
                    AutomatedFollowup.scheduled_at <= datetime.utcnow(),
                )
                .limit(batch_size)
                .all()
            )

            if not due_followups:
                return {"sent": 0, "failed": 0, "message": "No pending followups"}

            sent = 0
            failed = 0

            for followup in due_followups:
                success = await self._execute_single_followup(db, followup)
                if success:
                    sent += 1
                else:
                    failed += 1

            db.commit()

            logger.info(f"Executed followups: {sent} sent, {failed} failed")
            return {"sent": sent, "failed": failed}

        except Exception as e:
            logger.error(f"Error executing followups: {e}")
            db.rollback()
            return {"sent": 0, "failed": 0, "error": str(e)}

        finally:
            self._close_db(db)

    async def _execute_single_followup(
        self, db: Session, followup: AutomatedFollowup
    ) -> bool:
        """
        Execute a single follow-up.

        Args:
            db: Database session
            followup: The followup to execute

        Returns:
            True if sent successfully
        """
        try:
            # Get customer
            customer = db.query(Customer).filter(Customer.id == followup.customer_id).first()

            if not customer or not customer.phone_number:
                followup.status = "failed"
                return False

            # Get messaging platform for this customer's owner
            platform = (
                db.query(MessagingPlatform)
                .filter(
                    MessagingPlatform.user_id == customer.user_id,
                    MessagingPlatform.is_connected == True,
                )
                .first()
            )

            if not platform or not platform.phone_number_id:
                logger.warning(f"No WhatsApp platform for user {customer.user_id}")
                followup.status = "failed"
                return False

            # Get credentials
            credential = (
                db.query(MessagingCredential)
                .filter(MessagingCredential.platform_id == platform.id)
                .first()
            )

            if not credential:
                followup.status = "failed"
                return False

            # Decrypt token
            from ads_service.routes import TokenEncryptionService
            encryption = TokenEncryptionService()
            access_token = encryption.decrypt_token(credential.encrypted_access_token)

            # Send template message via WhatsApp
            from ..clients.meta_messaging import MetaMessagingClient

            client = MetaMessagingClient(
                access_token=access_token,
                phone_number_id=platform.phone_number_id,
            )

            result = await client.send_whatsapp_template(
                to=customer.phone_number,
                template_name=followup.template_name or "default",
                components=None,  # Could add customer name here
            )

            await client.close()

            # Check result
            if result.get("messages"):
                followup.status = "sent"
                followup.sent_at = datetime.utcnow()
                logger.info(f"Sent followup {followup.id} to {customer.phone_number}")
                return True
            else:
                followup.status = "failed"
                logger.error(f"Failed to send followup {followup.id}: {result}")
                return False

        except Exception as e:
            logger.error(f"Error executing followup {followup.id}: {e}")
            followup.status = "failed"
            return False

    # =========================================================================
    # Dormant Customer Detection (called by cron job)
    # =========================================================================

    def find_dormant_customers(self, user_id: str) -> List[int]:
        """
        Find customers who haven't visited in the dormant threshold period.

        Args:
            user_id: Owner's Clerk user ID

        Returns:
            List of dormant customer IDs
        """
        db = self._get_db()
        try:
            threshold = datetime.utcnow() - timedelta(days=self.settings.dormant_threshold_days)

            dormant = (
                db.query(Customer.id)
                .filter(
                    Customer.user_id == user_id,
                    Customer.visit_count > 0,  # Has visited before
                    Customer.last_visit_at < threshold,  # But not recently
                    Customer.lifecycle_stage != "churned",  # Not already churned
                )
                .all()
            )

            return [c.id for c in dormant]

        finally:
            self._close_db(db)

    async def schedule_dormant_reactivations(self, user_id: str) -> int:
        """
        Schedule reactivation messages for all dormant customers.

        Args:
            user_id: Owner's Clerk user ID

        Returns:
            Number of reactivations scheduled
        """
        dormant_ids = self.find_dormant_customers(user_id)

        count = 0
        for customer_id in dormant_ids:
            result = self.schedule_dormant_reactivation(customer_id)
            if result:
                count += 1

        logger.info(f"Scheduled {count} dormant reactivations for user {user_id}")
        return count


# Convenience function
def get_followup_scheduler(db: Optional[Session] = None) -> FollowupScheduler:
    """Get a followup scheduler instance."""
    return FollowupScheduler(db)
