"""
Attribution Service - Links customer actions to ad campaigns

Handles:
- CAPI event syncing for conversion attribution
- Campaign attribution reporting
- Customer journey tracking
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from database.database import SessionLocal
from database.models import (
    Customer,
    ConversionEvent,
    AdsCampaign,
    AdsPlatform,
)
from ..models import (
    AttributionReportResponse,
    CampaignAttributionRow,
    CustomerJourneyResponse,
    CustomerJourneyEvent,
    LifecycleStage,
)
from ..clients.meta_capi import create_capi_client, MetaCAPIClient

logger = logging.getLogger(__name__)


class AttributionService:
    """
    Service for conversion attribution and reporting.

    Links customer actions (leads, visits, purchases) back to ad campaigns
    via Meta Conversions API.
    """

    def __init__(self, db: Optional[Session] = None):
        """
        Initialize attribution service.

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
    # CAPI Event Syncing
    # =========================================================================

    async def sync_event_to_capi(
        self, event_id: int, capi_client: Optional[MetaCAPIClient] = None
    ) -> bool:
        """
        Sync a conversion event to Meta CAPI.

        Args:
            event_id: ConversionEvent ID
            capi_client: Optional CAPI client (will create if not provided)

        Returns:
            True if sync successful
        """
        db = self._get_db()
        try:
            # Get the event
            event = db.query(ConversionEvent).filter(ConversionEvent.id == event_id).first()

            if not event:
                logger.warning(f"Event {event_id} not found")
                return False

            # Skip if already synced
            if event.capi_synced_at:
                logger.debug(f"Event {event_id} already synced")
                return True

            # Get customer for user data
            customer = db.query(Customer).filter(Customer.id == event.customer_id).first()

            if not customer:
                logger.warning(f"Customer not found for event {event_id}")
                return False

            # Create CAPI client if not provided
            if not capi_client:
                capi_client = create_capi_client()

            if not capi_client:
                logger.warning("CAPI not configured, skipping sync")
                return False

            # Send event to CAPI
            result = await capi_client.send_event(
                event_name=event.event_name,
                event_time=event.created_at,
                phone=customer.phone_number,
                email=customer.email,
                first_name=customer.first_name,
                last_name=customer.last_name,
                click_id=event.click_id or customer.ctwa_clid,
                value=event.value_cents / 100 if event.value_cents else None,
            )

            # Check result
            if result.get("events_received", 0) > 0:
                event.capi_synced_at = datetime.utcnow()
                db.commit()
                logger.info(f"Event {event_id} synced to CAPI")
                return True
            else:
                logger.error(f"CAPI sync failed for event {event_id}: {result}")
                return False

        except Exception as e:
            logger.error(f"Error syncing event {event_id}: {e}")
            return False

        finally:
            if capi_client:
                await capi_client.close()
            self._close_db(db)

    async def sync_pending_events(
        self, user_id: str, batch_size: int = 50
    ) -> Dict[str, int]:
        """
        Sync all pending conversion events for a user.

        Args:
            user_id: Owner's Clerk user ID
            batch_size: Max events to sync in one batch

        Returns:
            Dict with synced/failed counts
        """
        db = self._get_db()
        try:
            # Get pending events
            pending_events = (
                db.query(ConversionEvent)
                .join(Customer)
                .filter(
                    Customer.user_id == user_id,
                    ConversionEvent.capi_synced_at.is_(None),
                )
                .limit(batch_size)
                .all()
            )

            if not pending_events:
                return {"synced": 0, "failed": 0}

            capi_client = create_capi_client()
            if not capi_client:
                logger.warning("CAPI not configured")
                return {"synced": 0, "failed": len(pending_events)}

            synced = 0
            failed = 0

            for event in pending_events:
                success = await self.sync_event_to_capi(event.id, capi_client)
                if success:
                    synced += 1
                else:
                    failed += 1

            await capi_client.close()

            logger.info(f"Batch sync complete: {synced} synced, {failed} failed")
            return {"synced": synced, "failed": failed}

        finally:
            self._close_db(db)

    # =========================================================================
    # Attribution Reporting
    # =========================================================================

    def get_attribution_report(
        self,
        user_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> AttributionReportResponse:
        """
        Get attribution report linking campaigns to customer outcomes.

        Args:
            user_id: Owner's Clerk user ID
            start_date: Report start date (default: 30 days ago)
            end_date: Report end date (default: now)

        Returns:
            Attribution report with per-campaign breakdown
        """
        db = self._get_db()
        try:
            # Default date range
            if not end_date:
                end_date = datetime.utcnow()
            if not start_date:
                start_date = end_date - timedelta(days=30)

            # Get user's platforms
            platform_ids = (
                db.query(AdsPlatform.id)
                .filter(AdsPlatform.user_id == user_id)
                .subquery()
            )

            # Get campaigns with metrics
            campaigns = (
                db.query(AdsCampaign)
                .filter(AdsCampaign.platform_id.in_(platform_ids))
                .all()
            )

            campaign_rows = []
            total_ad_spend = 0
            total_leads = 0
            total_visits = 0
            total_revenue = 0

            for campaign in campaigns:
                # Count customers attributed to this campaign
                leads = (
                    db.query(func.count(Customer.id))
                    .filter(
                        Customer.user_id == user_id,
                        Customer.source_campaign_id == campaign.id,
                        Customer.created_at >= start_date,
                        Customer.created_at <= end_date,
                    )
                    .scalar()
                    or 0
                )

                # Count conversions
                from database.models import Conversation

                conversations = (
                    db.query(func.count(Conversation.id))
                    .join(Customer)
                    .filter(
                        Customer.user_id == user_id,
                        Customer.source_campaign_id == campaign.id,
                        Conversation.created_at >= start_date,
                        Conversation.created_at <= end_date,
                    )
                    .scalar()
                    or 0
                )

                # Count visits from events
                visits = (
                    db.query(func.count(ConversionEvent.id))
                    .filter(
                        ConversionEvent.campaign_id == campaign.id,
                        ConversionEvent.event_name == "Visit",
                        ConversionEvent.created_at >= start_date,
                        ConversionEvent.created_at <= end_date,
                    )
                    .scalar()
                    or 0
                )

                # Sum purchases
                purchases = (
                    db.query(func.count(ConversionEvent.id))
                    .filter(
                        ConversionEvent.campaign_id == campaign.id,
                        ConversionEvent.event_name == "Purchase",
                        ConversionEvent.created_at >= start_date,
                        ConversionEvent.created_at <= end_date,
                    )
                    .scalar()
                    or 0
                )

                revenue = (
                    db.query(func.sum(ConversionEvent.value_cents))
                    .filter(
                        ConversionEvent.campaign_id == campaign.id,
                        ConversionEvent.event_name == "Purchase",
                        ConversionEvent.created_at >= start_date,
                        ConversionEvent.created_at <= end_date,
                    )
                    .scalar()
                    or 0
                )

                # Get ad spend from campaign
                ad_spend = campaign.total_spend_cents or 0

                # Calculate metrics
                cost_per_lead = ad_spend // leads if leads > 0 else None
                cost_per_visit = ad_spend // visits if visits > 0 else None
                roas = revenue / ad_spend if ad_spend > 0 else None

                # Get platform info
                platform = db.query(AdsPlatform).filter(AdsPlatform.id == campaign.platform_id).first()

                campaign_rows.append(
                    CampaignAttributionRow(
                        campaign_id=campaign.id,
                        campaign_name=campaign.name,
                        platform=platform.platform if platform else "unknown",
                        ad_spend_cents=ad_spend,
                        impressions=0,  # Would need to fetch from ads API
                        clicks=0,  # Would need to fetch from ads API
                        leads=leads,
                        conversations=conversations,
                        visits=visits,
                        purchases=purchases,
                        revenue_cents=revenue,
                        cost_per_lead_cents=cost_per_lead,
                        cost_per_visit_cents=cost_per_visit,
                        roas=roas,
                    )
                )

                # Update totals
                total_ad_spend += ad_spend
                total_leads += leads
                total_visits += visits
                total_revenue += revenue

            return AttributionReportResponse(
                period_start=start_date,
                period_end=end_date,
                total_ad_spend_cents=total_ad_spend,
                total_leads=total_leads,
                total_visits=total_visits,
                total_revenue_cents=total_revenue,
                overall_roas=total_revenue / total_ad_spend if total_ad_spend > 0 else None,
                campaigns=campaign_rows,
            )

        finally:
            self._close_db(db)

    def get_customer_journey(
        self, user_id: str, customer_id: int
    ) -> Optional[CustomerJourneyResponse]:
        """
        Get the complete journey for a customer.

        Shows: ad click -> message -> visit -> purchase timeline.

        Args:
            user_id: Owner's Clerk user ID
            customer_id: Customer ID

        Returns:
            Customer journey with event timeline
        """
        db = self._get_db()
        try:
            # Get customer
            customer = (
                db.query(Customer)
                .filter(
                    Customer.id == customer_id,
                    Customer.user_id == user_id,
                )
                .first()
            )

            if not customer:
                return None

            events = []

            # Add ad click event if attributed to campaign
            if customer.source_campaign_id:
                campaign = (
                    db.query(AdsCampaign)
                    .filter(AdsCampaign.id == customer.source_campaign_id)
                    .first()
                )

                events.append(
                    CustomerJourneyEvent(
                        event_type="ad_click",
                        timestamp=customer.created_at,  # Approximate
                        channel=customer.source_channel,
                        campaign_name=campaign.name if campaign else None,
                    )
                )

            # Add first message event
            from database.models import Conversation, Message

            first_message = (
                db.query(Message)
                .join(Conversation)
                .filter(
                    Conversation.customer_id == customer_id,
                    Message.direction == "inbound",
                )
                .order_by(Message.created_at)
                .first()
            )

            if first_message:
                conversation = db.query(Conversation).filter(
                    Conversation.id == first_message.conversation_id
                ).first()

                events.append(
                    CustomerJourneyEvent(
                        event_type="first_message",
                        timestamp=first_message.created_at,
                        channel=conversation.channel if conversation else None,
                        content_preview=first_message.content[:50] if first_message.content else None,
                    )
                )

            # Add conversion events
            conversion_events = (
                db.query(ConversionEvent)
                .filter(ConversionEvent.customer_id == customer_id)
                .order_by(ConversionEvent.created_at)
                .all()
            )

            for conv_event in conversion_events:
                events.append(
                    CustomerJourneyEvent(
                        event_type=conv_event.event_name.lower(),
                        timestamp=conv_event.created_at,
                        value_cents=conv_event.value_cents,
                    )
                )

            # Sort events by timestamp
            events.sort(key=lambda e: e.timestamp)

            # Get source campaign name
            source_campaign = None
            if customer.source_campaign_id:
                campaign = db.query(AdsCampaign).filter(
                    AdsCampaign.id == customer.source_campaign_id
                ).first()
                source_campaign = campaign.name if campaign else None

            return CustomerJourneyResponse(
                customer_id=customer.id,
                customer_name=f"{customer.first_name or ''} {customer.last_name or ''}".strip() or None,
                phone_number=customer.phone_number,
                source_campaign=source_campaign,
                source_channel=customer.source_channel,
                lifecycle_stage=LifecycleStage(customer.lifecycle_stage) if customer.lifecycle_stage else LifecycleStage.LEAD,
                total_spent_cents=customer.total_spent_cents or 0,
                visit_count=customer.visit_count or 0,
                events=events,
            )

        finally:
            self._close_db(db)

    # =========================================================================
    # Attribution Helpers
    # =========================================================================

    def link_customer_to_campaign(
        self, customer_id: int, campaign_id: int, click_id: Optional[str] = None
    ) -> bool:
        """
        Link a customer to a campaign for attribution.

        Called when processing Click-to-WhatsApp referrals.

        Args:
            customer_id: Customer ID
            campaign_id: Campaign ID
            click_id: CTWA click ID

        Returns:
            True if linked successfully
        """
        db = self._get_db()
        try:
            customer = db.query(Customer).filter(Customer.id == customer_id).first()

            if not customer:
                return False

            customer.source_campaign_id = campaign_id
            if click_id:
                customer.ctwa_clid = click_id

            db.commit()
            logger.info(f"Linked customer {customer_id} to campaign {campaign_id}")
            return True

        except Exception as e:
            logger.error(f"Error linking customer to campaign: {e}")
            db.rollback()
            return False

        finally:
            self._close_db(db)


# Convenience function
def get_attribution_service(db: Optional[Session] = None) -> AttributionService:
    """Get an attribution service instance."""
    return AttributionService(db)
