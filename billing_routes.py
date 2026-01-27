"""
Billing API Routes

Handles subscription management and billing operations.
"""
import os
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import User, Subscription
from clerk_auth import get_current_user, verify_clerk_token
import requests
from services.stripe_service import StripeService, get_all_plans, get_plan_info, PLAN_LIMITS
from services.billing_service import BillingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/billing", tags=["billing"])


def get_clerk_user_email(clerk_user_id: str) -> Optional[str]:
    """Fetch user email from Clerk API"""
    clerk_secret = os.environ.get("CLERK_SECRET_KEY")
    if not clerk_secret:
        return None

    try:
        response = requests.get(
            f"https://api.clerk.com/v1/users/{clerk_user_id}",
            headers={"Authorization": f"Bearer {clerk_secret}"}
        )
        if response.status_code == 200:
            user_data = response.json()
            email_addresses = user_data.get("email_addresses", [])
            for email in email_addresses:
                if email.get("id") == user_data.get("primary_email_address_id"):
                    return email.get("email_address")
            if email_addresses:
                return email_addresses[0].get("email_address")
    except Exception as e:
        logger.error(f"Failed to fetch email from Clerk: {e}")

    return None


# =============================================================================
# Request/Response Models
# =============================================================================


class CreateCheckoutRequest(BaseModel):
    plan: str  # pro, pro_plus, ultimate
    success_url: str
    cancel_url: str


class CreatePortalRequest(BaseModel):
    return_url: str


# =============================================================================
# Public Endpoints
# =============================================================================


@router.get("/plans")
async def get_plans():
    """
    Get available subscription plans.
    Public endpoint - no auth required.
    """
    return {
        "plans": get_all_plans(),
        "guarantee": "30-day money-back guarantee",
    }


@router.get("/configured")
async def check_stripe_configured():
    """
    Check if Stripe is configured.
    Used by frontend to show/hide billing features.
    """
    return {
        "configured": StripeService.is_configured(),
    }


# =============================================================================
# Authenticated Endpoints
# =============================================================================


@router.get("/subscription")
async def get_subscription(
    clerk_user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get current user's subscription details.
    """
    billing = BillingService(db)
    return billing.get_subscription_details(clerk_user_id)


@router.get("/credits")
async def get_credits(
    clerk_user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get current user's credit balance.
    """
    billing = BillingService(db)
    return billing.get_credit_balance(clerk_user_id)


@router.get("/usage")
async def get_usage(
    clerk_user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get feature usage for current billing period.
    """
    billing = BillingService(db)
    return billing.get_usage_summary(clerk_user_id)


@router.post("/checkout")
async def create_checkout(
    request: CreateCheckoutRequest,
    user_data: dict = Depends(verify_clerk_token),
    db: Session = Depends(get_db)
):
    """
    Create a Stripe Checkout session for new subscription.
    """
    clerk_user_id = user_data["user_id"]
    # Get email from JWT token (more reliable than database)
    jwt_email = user_data.get("email")

    # Debug logging
    logger.info(f"Checkout request - user_id: {clerk_user_id}")
    logger.info(f"JWT email: {jwt_email}")
    logger.info(f"JWT payload keys: {list(user_data.get('full_payload', {}).keys())}")

    if not StripeService.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Payment system is not configured"
        )

    # Validate plan
    if request.plan not in ["starter", "pro", "pro_plus", "ultimate"]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid plan: {request.plan}"
        )

    user = db.query(User).filter(User.id == clerk_user_id).first()
    if not user:
        # User not in database yet (race condition with Clerk webhook)
        # Create user on-the-fly using JWT email or fetch from Clerk API
        user_email = jwt_email
        if not user_email:
            user_email = get_clerk_user_email(clerk_user_id)
        if not user_email:
            user_email = f"{clerk_user_id}@unknown.com"

        user = User(
            id=clerk_user_id,
            email=user_email,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            plan="free",
            is_active=True
        )
        db.add(user)
        db.commit()
        logger.info(f"Created user {clerk_user_id} on-the-fly during checkout (webhook race condition)")

    # Use JWT email if database email looks invalid (contains user_ or @unknown)
    user_email = user.email
    logger.info(f"Database email: {user_email}")

    # Check if we need to get a better email
    needs_email_update = not user_email or "user_" in user_email or "@unknown" in user_email

    if needs_email_update:
        # Try JWT email first
        if jwt_email:
            user_email = jwt_email
            logger.info(f"Using JWT email: {jwt_email}")
        else:
            # Fallback: fetch from Clerk API
            clerk_email = get_clerk_user_email(clerk_user_id)
            if clerk_email:
                user_email = clerk_email
                logger.info(f"Using Clerk API email: {clerk_email}")

        # Update database with correct email
        if user_email and user_email != user.email:
            user.email = user_email
            db.commit()
            logger.info(f"Updated user {clerk_user_id} email in database to {user_email}")

    logger.info(f"Final email being used: {user_email}")

    # Check if user already has active subscription
    billing = BillingService(db)
    existing = billing.get_subscription(clerk_user_id)

    if existing and existing.status == "active":
        raise HTTPException(
            status_code=400,
            detail="You already have an active subscription. Use the billing portal to manage it."
        )

    # Get or create Stripe customer
    customer_id = await StripeService.get_or_create_customer(
        user_id=clerk_user_id,
        email=user_email,
        existing_customer_id=user.stripe_customer_id
    )

    # Save customer ID if new
    if not user.stripe_customer_id:
        user.stripe_customer_id = customer_id
        db.commit()

    # Create checkout session
    try:
        checkout_url = await StripeService.create_checkout_session(
            customer_id=customer_id,
            plan=request.plan,
            success_url=request.success_url,
            cancel_url=request.cancel_url,
            user_id=clerk_user_id,
        )
        return {"checkout_url": checkout_url}
    except Exception as e:
        logger.error(f"Failed to create checkout: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to create checkout session"
        )


@router.post("/portal")
async def create_portal(
    request: CreatePortalRequest,
    clerk_user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a Stripe Customer Portal session for self-service management.
    """
    if not StripeService.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Payment system is not configured"
        )

    user = db.query(User).filter(User.id == clerk_user_id).first()
    if not user or not user.stripe_customer_id:
        raise HTTPException(
            status_code=404,
            detail="No billing account found. Please subscribe first."
        )

    try:
        portal_url = await StripeService.create_portal_session(
            customer_id=user.stripe_customer_id,
            return_url=request.return_url,
        )
        return {"portal_url": portal_url}
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Failed to create portal: {error_msg}")

        # Handle test→live mode transition: clear invalid customer ID
        if "No such customer" in error_msg:
            logger.warning(f"Clearing invalid Stripe customer ID for user {clerk_user_id}")
            user.stripe_customer_id = None
            db.commit()
            raise HTTPException(
                status_code=404,
                detail="Your billing account needs to be recreated. Please subscribe to a plan."
            )

        raise HTTPException(
            status_code=500,
            detail="Failed to create billing portal session"
        )


@router.post("/reset")
async def reset_billing_account(
    clerk_user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Reset billing account - clears test mode data for live mode transition.
    Use this when switching from Stripe test to live mode.
    """
    user = db.query(User).filter(User.id == clerk_user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Clear Stripe customer ID
    old_customer_id = user.stripe_customer_id
    user.stripe_customer_id = None

    # Clear subscription
    subscription = db.query(Subscription).filter(Subscription.user_id == clerk_user_id).first()
    if subscription:
        db.delete(subscription)

    db.commit()

    logger.info(f"Reset billing account for user {clerk_user_id}, cleared customer {old_customer_id}")

    return {
        "message": "Billing account reset successfully. You can now subscribe to a plan.",
        "cleared_customer_id": old_customer_id,
    }


@router.get("/check-access/{feature}")
async def check_feature_access(
    feature: str,
    clerk_user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Check if user has access to a specific feature.
    """
    billing = BillingService(db)
    has_access, reason = billing.check_feature_access(clerk_user_id, feature)

    return {
        "feature": feature,
        "has_access": has_access,
        "reason": reason if not has_access else None,
    }
