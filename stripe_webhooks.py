"""
Stripe Webhook Handler

Processes subscription lifecycle events from Stripe.
"""
import os
import logging
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException, Header
from sqlalchemy.orm import Session

from database.database import SessionLocal
from database.models import User
from services.stripe_service import StripeService, PLAN_CREDITS
from services.billing_service import BillingService

logger = logging.getLogger(__name__)

router = APIRouter()

STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")


@router.post("/api/webhooks/stripe")
async def stripe_webhook_handler(
    request: Request,
    stripe_signature: str = Header(None, alias="stripe-signature"),
):
    """
    Handle Stripe webhooks for subscription events.

    Events handled:
    - checkout.session.completed: New subscription created
    - customer.subscription.created: Subscription record created
    - customer.subscription.updated: Plan change, status change
    - customer.subscription.deleted: Subscription canceled
    - invoice.payment_succeeded: Payment successful, reset credits
    - invoice.payment_failed: Payment failed, mark past_due
    """
    if not STRIPE_WEBHOOK_SECRET:
        logger.warning("Stripe webhook secret not configured")
        raise HTTPException(status_code=500, detail="Webhook not configured")

    payload = await request.body()

    try:
        event = StripeService.verify_webhook_signature(
            payload, stripe_signature, STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        logger.error("Invalid Stripe webhook signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    event_type = event["type"]
    data = event["data"]["object"]

    print(f"")
    print(f"========================================")
    print(f"STRIPE WEBHOOK RECEIVED: {event_type}")
    print(f"========================================")

    db = SessionLocal()
    try:
        if event_type == "checkout.session.completed":
            await handle_checkout_completed(db, data)
        elif event_type == "customer.subscription.created":
            await handle_subscription_created(db, data)
        elif event_type == "customer.subscription.updated":
            await handle_subscription_updated(db, data)
        elif event_type == "customer.subscription.deleted":
            await handle_subscription_deleted(db, data)
        elif event_type == "invoice.payment_succeeded":
            await handle_invoice_paid(db, data)
        elif event_type == "invoice.payment_failed":
            await handle_invoice_failed(db, data)
        else:
            logger.debug(f"Unhandled Stripe event: {event_type}")

        return {"success": True, "event": event_type}

    except Exception as e:
        logger.error(f"Error handling Stripe webhook {event_type}: {e}")
        import traceback
        traceback.print_exc()
        # Don't raise - return 200 to acknowledge receipt
        return {"success": False, "error": str(e)}
    finally:
        db.close()


async def handle_checkout_completed(db: Session, session: dict):
    """
    Handle successful checkout - create subscription record.

    This is the primary handler for new subscriptions.
    """
    import stripe

    print("=== handle_checkout_completed started ===")

    customer_id = session.get("customer")
    subscription_id = session.get("subscription")

    print(f"customer_id: {customer_id}, subscription_id: {subscription_id}")

    if not subscription_id:
        logger.warning("Checkout completed without subscription")
        return

    # Get customer to find user_id
    print(f"Retrieving customer {customer_id} from Stripe...")
    customer = stripe.Customer.retrieve(customer_id)
    user_id = customer.metadata.get("clerk_user_id")

    print(f"Customer metadata: {customer.metadata}")
    print(f"clerk_user_id from metadata: {user_id}")

    if not user_id:
        logger.error(f"No clerk_user_id in customer metadata: {customer_id}")
        return

    # Get subscription details from Stripe
    print(f"Retrieving subscription {subscription_id} from Stripe...")
    subscription_data = stripe.Subscription.retrieve(subscription_id)
    plan = subscription_data.metadata.get("plan", "pro")
    print(f"Plan from metadata: {plan}")

    # Access subscription fields - handle both dict and object access
    try:
        period_start = subscription_data.current_period_start
        period_end = subscription_data.current_period_end
        price_id = subscription_data.items.data[0].price.id
    except (AttributeError, KeyError):
        # Fallback to dict access
        period_start = subscription_data.get("current_period_start")
        period_end = subscription_data.get("current_period_end")
        price_id = subscription_data["items"]["data"][0]["price"]["id"]

    # Create/update subscription record
    print(f"Creating subscription record...")
    print(f"  user_id: {user_id}")
    print(f"  subscription_id: {subscription_id}")
    print(f"  price_id: {price_id}")
    print(f"  plan: {plan}")
    print(f"  period_start: {period_start}")
    print(f"  period_end: {period_end}")

    try:
        billing = BillingService(db)
        result = billing.create_subscription_record(
            user_id=user_id,
            stripe_subscription_id=subscription_id,
            stripe_price_id=price_id,
            plan=plan,
            current_period_start=datetime.fromtimestamp(period_start) if period_start else datetime.utcnow(),
            current_period_end=datetime.fromtimestamp(period_end) if period_end else datetime.utcnow(),
        )
        print(f"✅ Subscription created successfully: {result.id if result else 'None'}")
    except Exception as e:
        print(f"❌ Error creating subscription: {e}")
        import traceback
        traceback.print_exc()
        raise

    # Update user's stripe_customer_id if not set
    user = db.query(User).filter(User.id == user_id).first()
    print(f"User found: {user is not None}")
    if user and not user.stripe_customer_id:
        user.stripe_customer_id = customer_id
        db.commit()
        print(f"Updated user stripe_customer_id")

    print(f"=== handle_checkout_completed DONE for user {user_id}: {plan} ===")


async def handle_subscription_created(db: Session, subscription_data: dict):
    """
    Handle subscription.created event.

    This is a backup - checkout.session.completed should handle most cases.
    """
    import stripe

    subscription_id = subscription_data["id"]
    customer_id = subscription_data["customer"]
    plan = subscription_data.get("metadata", {}).get("plan", "pro")

    # Check if we already have this subscription
    from database.models import Subscription
    existing = db.query(Subscription).filter(
        Subscription.stripe_subscription_id == subscription_id
    ).first()

    if existing:
        logger.debug(f"Subscription {subscription_id} already exists")
        return

    # Get user_id from customer metadata
    customer = stripe.Customer.retrieve(customer_id)
    user_id = customer.metadata.get("clerk_user_id")

    if not user_id:
        logger.warning(f"No user_id for subscription.created: {subscription_id}")
        return

    # Access subscription fields safely
    try:
        period_start = subscription_data.current_period_start
        period_end = subscription_data.current_period_end
        price_id = subscription_data.items.data[0].price.id
    except (AttributeError, KeyError):
        period_start = subscription_data.get("current_period_start")
        period_end = subscription_data.get("current_period_end")
        price_id = subscription_data["items"]["data"][0]["price"]["id"]

    # Create subscription record
    billing = BillingService(db)
    billing.create_subscription_record(
        user_id=user_id,
        stripe_subscription_id=subscription_id,
        stripe_price_id=price_id,
        plan=plan,
        current_period_start=datetime.fromtimestamp(period_start) if period_start else datetime.utcnow(),
        current_period_end=datetime.fromtimestamp(period_end) if period_end else datetime.utcnow(),
    )

    logger.info(f"Created subscription from webhook for user {user_id}")


async def handle_subscription_updated(db: Session, subscription_data: dict):
    """
    Handle subscription updates (plan change, status change, renewal).
    """
    # Access fields safely - handle both object and dict access
    try:
        subscription_id = subscription_data.id
        status = subscription_data.status
        plan = subscription_data.metadata.get("plan") if subscription_data.metadata else None
        period_start = subscription_data.current_period_start
        period_end = subscription_data.current_period_end
        cancel_at_period_end = subscription_data.cancel_at_period_end
    except AttributeError:
        subscription_id = subscription_data["id"]
        status = subscription_data["status"]
        plan = subscription_data.get("metadata", {}).get("plan")
        period_start = subscription_data.get("current_period_start")
        period_end = subscription_data.get("current_period_end")
        cancel_at_period_end = subscription_data.get("cancel_at_period_end", False)

    billing = BillingService(db)
    billing.update_subscription_status(
        stripe_subscription_id=subscription_id,
        status=status,
        plan=plan,
        current_period_start=datetime.fromtimestamp(period_start) if period_start else None,
        current_period_end=datetime.fromtimestamp(period_end) if period_end else None,
        cancel_at_period_end=cancel_at_period_end or False,
    )

    logger.info(f"Updated subscription {subscription_id}: status={status}, plan={plan}")


async def handle_subscription_deleted(db: Session, subscription_data: dict):
    """
    Handle subscription cancellation/deletion.
    """
    subscription_id = subscription_data["id"]

    billing = BillingService(db)
    billing.cancel_subscription(subscription_id)

    logger.info(f"Canceled subscription {subscription_id}")


async def handle_invoice_paid(db: Session, invoice: dict):
    """
    Handle successful payment - reset credits for new billing period.
    """
    subscription_id = invoice.get("subscription")
    if not subscription_id:
        return

    # Only reset on recurring invoices, not the first one
    billing_reason = invoice.get("billing_reason")
    if billing_reason not in ["subscription_cycle", "subscription_update"]:
        logger.debug(f"Skipping credit reset for billing_reason: {billing_reason}")
        return

    billing = BillingService(db)
    billing.reset_monthly_credits(subscription_id)

    logger.info(f"Reset credits for subscription {subscription_id}")


async def handle_invoice_failed(db: Session, invoice: dict):
    """
    Handle failed payment - mark subscription as past_due.
    """
    subscription_id = invoice.get("subscription")
    if not subscription_id:
        return

    billing = BillingService(db)
    billing.update_subscription_status(
        stripe_subscription_id=subscription_id,
        status="past_due",
    )

    logger.warning(f"Payment failed for subscription {subscription_id}")
    # TODO: Send email notification to user
