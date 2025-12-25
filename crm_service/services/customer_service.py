"""
Customer Service - CRUD operations and smart tagging for CRM

Handles:
- Customer creation and updates
- Smart tagging (auto-tags based on behavior)
- Visit tracking and lifecycle management
- Customer search and filtering
"""

import logging
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta
from sqlalchemy import or_, and_, func
from sqlalchemy.orm import Session

from database.database import SessionLocal
from database.models import (
    Customer,
    CustomerTag,
    Conversation,
    Message,
    ConversionEvent,
    AdsCampaign,
)
from ..models import (
    CustomerCreate,
    CustomerUpdate,
    CustomerResponse,
    CustomerTagRequest,
    CustomerTagResponse,
    CustomerSearchParams,
    CustomerListResponse,
    LifecycleStage,
    VisitResponse,
)

logger = logging.getLogger(__name__)


class CustomerService:
    """
    Service for customer management and smart tagging.
    """

    # Smart tag rules
    SMART_TAG_RULES = {
        "new_customer": {
            "condition": lambda c: c.visit_count == 0,
            "category": "lifecycle",
        },
        "returning": {
            "condition": lambda c: c.visit_count >= 2,
            "category": "lifecycle",
        },
        "high_value": {
            "condition": lambda c: c.total_spent_cents >= 10000,  # $100+
            "category": "value",
        },
        "dormant": {
            "condition": lambda c: (
                c.last_visit_at
                and (datetime.utcnow() - c.last_visit_at).days >= 30
            ),
            "category": "engagement",
        },
        "from_ad": {
            "condition": lambda c: c.source_campaign_id is not None,
            "category": "source",
        },
    }

    def __init__(self, db: Optional[Session] = None):
        """
        Initialize customer service.

        Args:
            db: Optional database session. If not provided, will create new sessions.
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
    # Customer CRUD
    # =========================================================================

    def create_customer(
        self, user_id: str, data: CustomerCreate
    ) -> CustomerResponse:
        """
        Create a new customer.

        Args:
            user_id: Owner's Clerk user ID
            data: Customer creation data

        Returns:
            Created customer response
        """
        db = self._get_db()
        try:
            customer = Customer(
                user_id=user_id,
                phone_number=data.phone_number,
                email=data.email,
                first_name=data.first_name,
                last_name=data.last_name,
                instagram_id=data.instagram_id,
                messenger_id=data.messenger_id,
                whatsapp_id=data.whatsapp_id,
                source_channel=data.source_channel.value if data.source_channel else None,
                ctwa_clid=data.ctwa_clid,
                source_campaign_id=data.source_campaign_id,
                lifecycle_stage="lead",
            )
            db.add(customer)
            db.commit()
            db.refresh(customer)

            # Apply smart tags
            self._apply_smart_tags(db, customer)
            db.commit()

            logger.info(f"Created customer {customer.id} for user {user_id}")
            return self._to_response(db, customer)

        finally:
            self._close_db(db)

    def get_customer(self, user_id: str, customer_id: int) -> Optional[CustomerResponse]:
        """Get a customer by ID."""
        db = self._get_db()
        try:
            customer = (
                db.query(Customer)
                .filter(Customer.id == customer_id, Customer.user_id == user_id)
                .first()
            )

            if not customer:
                return None

            return self._to_response(db, customer)

        finally:
            self._close_db(db)

    def update_customer(
        self, user_id: str, customer_id: int, data: CustomerUpdate
    ) -> Optional[CustomerResponse]:
        """Update a customer."""
        db = self._get_db()
        try:
            customer = (
                db.query(Customer)
                .filter(Customer.id == customer_id, Customer.user_id == user_id)
                .first()
            )

            if not customer:
                return None

            # Update fields
            if data.first_name is not None:
                customer.first_name = data.first_name
            if data.last_name is not None:
                customer.last_name = data.last_name
            if data.email is not None:
                customer.email = data.email
            if data.lifecycle_stage is not None:
                customer.lifecycle_stage = data.lifecycle_stage.value

            customer.updated_at = datetime.utcnow()
            db.commit()

            # Re-apply smart tags
            self._apply_smart_tags(db, customer)
            db.commit()

            return self._to_response(db, customer)

        finally:
            self._close_db(db)

    def search_customers(
        self, user_id: str, params: CustomerSearchParams
    ) -> CustomerListResponse:
        """
        Search customers with filters.

        Args:
            user_id: Owner's Clerk user ID
            params: Search parameters

        Returns:
            Paginated customer list
        """
        db = self._get_db()
        try:
            query = db.query(Customer).filter(Customer.user_id == user_id)

            # Text search
            if params.query:
                search = f"%{params.query}%"
                query = query.filter(
                    or_(
                        Customer.first_name.ilike(search),
                        Customer.last_name.ilike(search),
                        Customer.phone_number.ilike(search),
                        Customer.email.ilike(search),
                    )
                )

            # Lifecycle stage filter
            if params.lifecycle_stage:
                query = query.filter(
                    Customer.lifecycle_stage == params.lifecycle_stage.value
                )

            # Tag filter
            if params.tag:
                query = query.join(CustomerTag).filter(
                    CustomerTag.name == params.tag
                )

            # Source channel filter
            if params.source_channel:
                query = query.filter(
                    Customer.source_channel == params.source_channel.value
                )

            # Visit filter
            if params.has_visited is not None:
                if params.has_visited:
                    query = query.filter(Customer.visit_count > 0)
                else:
                    query = query.filter(Customer.visit_count == 0)

            # Get total count
            total = query.count()

            # Paginate
            offset = (params.page - 1) * params.page_size
            customers = (
                query.order_by(Customer.created_at.desc())
                .offset(offset)
                .limit(params.page_size)
                .all()
            )

            return CustomerListResponse(
                customers=[self._to_response(db, c) for c in customers],
                total=total,
                page=params.page,
                page_size=params.page_size,
            )

        finally:
            self._close_db(db)

    # =========================================================================
    # Visit Tracking
    # =========================================================================

    def record_visit(
        self, user_id: str, customer_id: int, spent_cents: int = 0
    ) -> Optional[VisitResponse]:
        """
        Record a customer visit (from check-in or manual entry).

        Args:
            user_id: Owner's Clerk user ID
            customer_id: Customer ID
            spent_cents: Amount spent during visit

        Returns:
            Visit response with updated stats
        """
        db = self._get_db()
        try:
            customer = (
                db.query(Customer)
                .filter(Customer.id == customer_id, Customer.user_id == user_id)
                .first()
            )

            if not customer:
                return None

            # Update visit stats
            customer.visit_count = (customer.visit_count or 0) + 1
            customer.last_visit_at = datetime.utcnow()
            customer.total_spent_cents = (customer.total_spent_cents or 0) + spent_cents

            # Update lifecycle stage
            if customer.visit_count >= 2:
                customer.lifecycle_stage = "repeat"
            elif customer.lifecycle_stage == "lead":
                customer.lifecycle_stage = "customer"

            # Create conversion event
            event = ConversionEvent(
                customer_id=customer.id,
                event_name="Visit",
                event_source="manual",
                value_cents=spent_cents,
                campaign_id=customer.source_campaign_id,
                click_id=customer.ctwa_clid,
            )
            db.add(event)

            # Re-apply smart tags
            self._apply_smart_tags(db, customer)

            db.commit()

            # Schedule review request (if this is a qualified visit)
            review_scheduled = False
            review_scheduled_at = None

            if customer.visit_count >= 1 and spent_cents > 0:
                from .followup_scheduler import FollowupScheduler
                scheduler = FollowupScheduler(db)
                review_scheduled_at = scheduler.schedule_review_request(customer.id)
                review_scheduled = review_scheduled_at is not None

            logger.info(
                f"Recorded visit for customer {customer_id}: "
                f"visit #{customer.visit_count}, spent ${spent_cents/100:.2f}"
            )

            return VisitResponse(
                customer_id=customer.id,
                visit_count=customer.visit_count,
                total_spent_cents=customer.total_spent_cents,
                review_request_scheduled=review_scheduled,
                review_scheduled_at=review_scheduled_at,
            )

        except Exception as e:
            logger.error(f"Error recording visit: {e}")
            db.rollback()
            raise

        finally:
            self._close_db(db)

    # =========================================================================
    # Tagging
    # =========================================================================

    def add_tag(
        self, user_id: str, customer_id: int, tag: CustomerTagRequest
    ) -> Optional[CustomerTagResponse]:
        """Add a manual tag to a customer."""
        db = self._get_db()
        try:
            customer = (
                db.query(Customer)
                .filter(Customer.id == customer_id, Customer.user_id == user_id)
                .first()
            )

            if not customer:
                return None

            # Check if tag already exists
            existing = (
                db.query(CustomerTag)
                .filter(
                    CustomerTag.customer_id == customer_id,
                    CustomerTag.name == tag.name,
                )
                .first()
            )

            if existing:
                return CustomerTagResponse(
                    id=existing.id,
                    name=existing.name,
                    category=existing.category,
                    is_smart_tag=existing.is_smart_tag,
                    created_at=existing.created_at,
                )

            # Create new tag
            new_tag = CustomerTag(
                customer_id=customer_id,
                name=tag.name,
                category=tag.category,
                is_smart_tag=False,
            )
            db.add(new_tag)
            db.commit()
            db.refresh(new_tag)

            return CustomerTagResponse(
                id=new_tag.id,
                name=new_tag.name,
                category=new_tag.category,
                is_smart_tag=new_tag.is_smart_tag,
                created_at=new_tag.created_at,
            )

        finally:
            self._close_db(db)

    def remove_tag(self, user_id: str, customer_id: int, tag_name: str) -> bool:
        """Remove a tag from a customer."""
        db = self._get_db()
        try:
            customer = (
                db.query(Customer)
                .filter(Customer.id == customer_id, Customer.user_id == user_id)
                .first()
            )

            if not customer:
                return False

            tag = (
                db.query(CustomerTag)
                .filter(
                    CustomerTag.customer_id == customer_id,
                    CustomerTag.name == tag_name,
                    CustomerTag.is_smart_tag == False,  # Only remove manual tags
                )
                .first()
            )

            if tag:
                db.delete(tag)
                db.commit()
                return True

            return False

        finally:
            self._close_db(db)

    def _apply_smart_tags(self, db: Session, customer: Customer):
        """Apply smart tags based on customer attributes."""
        for tag_name, rule in self.SMART_TAG_RULES.items():
            # Check if rule condition is met
            should_have_tag = rule["condition"](customer)

            # Check if tag exists
            existing = (
                db.query(CustomerTag)
                .filter(
                    CustomerTag.customer_id == customer.id,
                    CustomerTag.name == tag_name,
                    CustomerTag.is_smart_tag == True,
                )
                .first()
            )

            if should_have_tag and not existing:
                # Add the smart tag
                new_tag = CustomerTag(
                    customer_id=customer.id,
                    name=tag_name,
                    category=rule["category"],
                    is_smart_tag=True,
                )
                db.add(new_tag)

            elif not should_have_tag and existing:
                # Remove the smart tag
                db.delete(existing)

    # =========================================================================
    # Helpers
    # =========================================================================

    def _to_response(self, db: Session, customer: Customer) -> CustomerResponse:
        """Convert database customer to response model."""
        # Get tags
        tags = (
            db.query(CustomerTag)
            .filter(CustomerTag.customer_id == customer.id)
            .all()
        )

        tag_responses = [
            CustomerTagResponse(
                id=t.id,
                name=t.name,
                category=t.category,
                is_smart_tag=t.is_smart_tag,
                created_at=t.created_at,
            )
            for t in tags
        ]

        # Get source campaign name if available
        campaign_name = None
        if customer.source_campaign_id:
            campaign = db.query(AdsCampaign).filter(
                AdsCampaign.id == customer.source_campaign_id
            ).first()
            if campaign:
                campaign_name = campaign.name

        return CustomerResponse(
            id=customer.id,
            phone_number=customer.phone_number,
            email=customer.email,
            first_name=customer.first_name,
            last_name=customer.last_name,
            profile_picture_url=customer.profile_picture_url,
            source_channel=customer.source_channel,
            source_campaign_id=customer.source_campaign_id,
            source_campaign_name=campaign_name,
            lifecycle_stage=LifecycleStage(customer.lifecycle_stage) if customer.lifecycle_stage else LifecycleStage.LEAD,
            visit_count=customer.visit_count or 0,
            last_visit_at=customer.last_visit_at,
            total_spent_cents=customer.total_spent_cents or 0,
            tags=tag_responses,
            created_at=customer.created_at,
            updated_at=customer.updated_at,
        )

    def find_by_phone(self, user_id: str, phone_number: str) -> Optional[CustomerResponse]:
        """Find customer by phone number."""
        db = self._get_db()
        try:
            customer = (
                db.query(Customer)
                .filter(
                    Customer.user_id == user_id,
                    Customer.phone_number == phone_number,
                )
                .first()
            )

            if not customer:
                return None

            return self._to_response(db, customer)

        finally:
            self._close_db(db)

    def find_by_identifier(
        self, user_id: str, identifier: str, channel: str
    ) -> Optional[CustomerResponse]:
        """Find customer by channel-specific identifier."""
        db = self._get_db()
        try:
            if channel == "whatsapp":
                customer = (
                    db.query(Customer)
                    .filter(
                        Customer.user_id == user_id,
                        Customer.whatsapp_id == identifier,
                    )
                    .first()
                )
            elif channel == "instagram":
                customer = (
                    db.query(Customer)
                    .filter(
                        Customer.user_id == user_id,
                        Customer.instagram_id == identifier,
                    )
                    .first()
                )
            elif channel == "messenger":
                customer = (
                    db.query(Customer)
                    .filter(
                        Customer.user_id == user_id,
                        Customer.messenger_id == identifier,
                    )
                    .first()
                )
            else:
                return None

            if not customer:
                return None

            return self._to_response(db, customer)

        finally:
            self._close_db(db)


# Convenience function
def get_customer_service(db: Optional[Session] = None) -> CustomerService:
    """Get a customer service instance."""
    return CustomerService(db)
