"""
Stripe Payment Service

Handles all Stripe API interactions for subscriptions, checkout, and billing.
"""
import os
import stripe
import logging
from datetime import datetime
from typing import Optional, Dict, Any, Tuple

logger = logging.getLogger(__name__)

# Initialize Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

# Price IDs for each plan (set in Stripe Dashboard)
PRICE_IDS = {
    "starter": os.getenv("STRIPE_PRICE_STARTER"),
    "pro": os.getenv("STRIPE_PRICE_PRO"),
    "pro_plus": os.getenv("STRIPE_PRICE_PRO_PLUS"),
    "ultimate": os.getenv("STRIPE_PRICE_ULTIMATE"),
}

# Credit allocations per plan (updated for usage-based billing)
# Based on real LangSmith data: $3-$17 per session, avg ~$10
# Formula: credits = cost × 100 × 1.5 (50% markup)
# At $10 avg session cost = 1,500 credits per session
PLAN_CREDITS = {
    "starter": 500,     # ~$3 worth, 2-3 sessions
    "pro": 2000,        # ~$13 worth, ~10 sessions
    "pro_plus": 5000,   # ~$33 worth, ~25 sessions
    "ultimate": 10000,  # ~$67 worth, ~50 sessions
}

# Feature limits per plan (-1 = unlimited)
PLAN_LIMITS = {
    "starter": {
        "x_growth_sessions": 5,
        "content_generations": 20,
        "scheduled_posts": 10,
        "ads_campaigns": 0,
        "crm_access": False,
        "image_generations": 0,
        "analytics_days": 3,
        "work_integrations": 1,  # 1 platform
        "work_drafts_per_month": 10,
    },
    "pro": {
        "x_growth_sessions": 15,
        "content_generations": 100,
        "scheduled_posts": 50,
        "ads_campaigns": 0,
        "crm_access": False,
        "image_generations": 10,
        "analytics_days": 7,
        "work_integrations": 3,  # 3 platforms
        "work_drafts_per_month": 30,
    },
    "pro_plus": {
        "x_growth_sessions": 50,
        "content_generations": 300,
        "scheduled_posts": -1,  # Unlimited
        "ads_campaigns": 10,
        "crm_access": False,
        "image_generations": 50,
        "analytics_days": 30,
        "work_integrations": 5,  # 5 platforms (all)
        "work_drafts_per_month": 60,
    },
    "ultimate": {
        "x_growth_sessions": 100,  # ~50-100 sessions based on 10,000 credits
        "content_generations": 500,
        "scheduled_posts": -1,  # Unlimited
        "ads_campaigns": 50,
        "crm_access": True,
        "image_generations": 200,
        "analytics_days": 90,
        "work_integrations": -1,  # Unlimited
        "work_drafts_per_month": -1,  # Unlimited
    },
}

# Plan display info
PLAN_INFO = {
    "starter": {
        "name": "Starter",
        "price": 99,
        "description": "Entry-level AI automation for new creators",
    },
    "pro": {
        "name": "Pro",
        "price": 299,
        "description": "For individual creators ready to scale",
    },
    "pro_plus": {
        "name": "Pro Plus",
        "price": 499,
        "description": "Advanced automation for growing businesses",
    },
    "ultimate": {
        "name": "Ultimate",
        "price": 799,
        "description": "Full platform access for agencies",
    },
}

# DEPRECATED: Fixed credit costs - Now using LangSmith usage-based billing
# These are kept for backwards compatibility and fallback only
CREDIT_COSTS = {
    "sonnet_message": 1,       # ~$0.01 actual cost
    "opus_message": 3,         # ~$0.05 actual cost
    "computer_use_minute": 1,  # ~$0.005 actual cost (Cloud Run)
    "image_generation": 10,    # Legacy - use ai_image_generation instead
    "ai_image_generation": 27, # KIE Nano Banana Pro: 18 credits × 1.5 markup = 27 credits
    "web_search": 1,           # ~$0.02 actual cost
}

# DEPRECATED: Fixed session costs - Now using LangSmith usage-based billing
AGENT_SESSION_COSTS = {
    "x_growth": 5,        # X Growth agent session
    "ads": 10,            # Ads campaign agent session
    "crm": 5,             # CRM conversation agent session
    "content_engine": 3,  # Content generation session
}

# NEW: Usage-based billing configuration
# Credits are calculated from actual LangSmith costs:
#   credits = actual_cost × 100 × markup_multiplier
# Example: $10 session cost = 10 × 100 × 1.5 = 1,500 credits
USAGE_BILLING = {
    "markup_multiplier": 1.5,      # 50% profit margin
    "cents_per_credit": 1,         # $0.01 = 1 credit base (before markup)
    "minimum_credits": 50,         # Minimum charge per session
    "minimum_cost": 0.50,          # $0.50 fallback if LangSmith returns 0
}


class StripeService:
    """
    Service class for Stripe operations.
    All methods are static for easy use without instantiation.
    """

    @staticmethod
    def is_configured() -> bool:
        """Check if Stripe is properly configured."""
        return bool(stripe.api_key and PRICE_IDS.get("pro"))

    @staticmethod
    async def create_customer(user_id: str, email: str, name: str = None) -> str:
        """
        Create a Stripe customer for a new user.

        Args:
            user_id: Clerk user ID
            email: User's email address
            name: Optional display name

        Returns:
            Stripe customer ID
        """
        try:
            customer = stripe.Customer.create(
                email=email,
                name=name,
                metadata={"clerk_user_id": user_id}
            )
            logger.info(f"Created Stripe customer {customer.id} for user {user_id}")
            return customer.id
        except stripe.error.StripeError as e:
            logger.error(f"Failed to create Stripe customer: {e}")
            raise

    @staticmethod
    async def get_or_create_customer(user_id: str, email: str, existing_customer_id: str = None) -> str:
        """
        Get existing Stripe customer or create new one.

        Args:
            user_id: Clerk user ID
            email: User's email
            existing_customer_id: Optional existing Stripe customer ID

        Returns:
            Stripe customer ID
        """
        if existing_customer_id:
            try:
                # Verify customer exists
                customer = stripe.Customer.retrieve(existing_customer_id)
                if not customer.get("deleted"):
                    # Update email if it's different and valid
                    if email and customer.get("email") != email:
                        stripe.Customer.modify(
                            existing_customer_id,
                            email=email
                        )
                        logger.info(f"Updated Stripe customer {existing_customer_id} email to {email}")
                    return existing_customer_id
            except stripe.error.InvalidRequestError:
                pass  # Customer doesn't exist, create new one

        return await StripeService.create_customer(user_id, email)

    @staticmethod
    async def create_checkout_session(
        customer_id: str,
        plan: str,
        success_url: str,
        cancel_url: str,
        user_id: str = None
    ) -> str:
        """
        Create a Stripe Checkout session for subscription signup.

        Args:
            customer_id: Stripe customer ID
            plan: Plan identifier (pro, pro_plus, ultimate)
            success_url: URL to redirect on success
            cancel_url: URL to redirect on cancel
            user_id: Optional Clerk user ID for metadata

        Returns:
            Checkout session URL
        """
        price_id = PRICE_IDS.get(plan)
        if not price_id:
            raise ValueError(f"Invalid plan: {plan}")

        try:
            session = stripe.checkout.Session.create(
                customer=customer_id,
                mode="subscription",
                line_items=[{
                    "price": price_id,
                    "quantity": 1,
                }],
                success_url=success_url,
                cancel_url=cancel_url,
                subscription_data={
                    "metadata": {
                        "plan": plan,
                        "clerk_user_id": user_id or "",
                    }
                },
                payment_method_types=["card"],
                allow_promotion_codes=True,
                billing_address_collection="auto",
            )
            logger.info(f"Created checkout session {session.id} for customer {customer_id}")
            return session.url
        except stripe.error.StripeError as e:
            logger.error(f"Failed to create checkout session: {e}")
            raise

    @staticmethod
    async def create_portal_session(customer_id: str, return_url: str) -> str:
        """
        Create a Stripe Customer Portal session for self-service management.

        Args:
            customer_id: Stripe customer ID
            return_url: URL to redirect when leaving portal

        Returns:
            Portal session URL
        """
        try:
            session = stripe.billing_portal.Session.create(
                customer=customer_id,
                return_url=return_url,
            )
            logger.info(f"Created portal session for customer {customer_id}")
            return session.url
        except stripe.error.StripeError as e:
            logger.error(f"Failed to create portal session: {e}")
            raise

    @staticmethod
    async def get_subscription(subscription_id: str) -> Dict[str, Any]:
        """
        Retrieve subscription details from Stripe.

        Args:
            subscription_id: Stripe subscription ID

        Returns:
            Subscription data dict
        """
        try:
            return stripe.Subscription.retrieve(subscription_id)
        except stripe.error.StripeError as e:
            logger.error(f"Failed to retrieve subscription: {e}")
            raise

    @staticmethod
    async def cancel_subscription(subscription_id: str, at_period_end: bool = True) -> Dict[str, Any]:
        """
        Cancel a subscription.

        Args:
            subscription_id: Stripe subscription ID
            at_period_end: If True, cancel at end of billing period

        Returns:
            Updated subscription data
        """
        try:
            if at_period_end:
                subscription = stripe.Subscription.modify(
                    subscription_id,
                    cancel_at_period_end=True
                )
            else:
                subscription = stripe.Subscription.delete(subscription_id)
            logger.info(f"Canceled subscription {subscription_id}")
            return subscription
        except stripe.error.StripeError as e:
            logger.error(f"Failed to cancel subscription: {e}")
            raise

    @staticmethod
    async def update_subscription(subscription_id: str, new_plan: str) -> Dict[str, Any]:
        """
        Upgrade or downgrade a subscription.

        Args:
            subscription_id: Stripe subscription ID
            new_plan: New plan identifier

        Returns:
            Updated subscription data
        """
        new_price_id = PRICE_IDS.get(new_plan)
        if not new_price_id:
            raise ValueError(f"Invalid plan: {new_plan}")

        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
            updated = stripe.Subscription.modify(
                subscription_id,
                items=[{
                    "id": subscription["items"]["data"][0].id,
                    "price": new_price_id,
                }],
                proration_behavior="create_prorations",
                metadata={"plan": new_plan}
            )
            logger.info(f"Updated subscription {subscription_id} to plan {new_plan}")
            return updated
        except stripe.error.StripeError as e:
            logger.error(f"Failed to update subscription: {e}")
            raise

    @staticmethod
    async def report_metered_usage(subscription_item_id: str, quantity: int) -> None:
        """
        Report metered usage for overage billing.

        Args:
            subscription_item_id: Stripe subscription item ID
            quantity: Usage quantity to report
        """
        try:
            stripe.SubscriptionItem.create_usage_record(
                subscription_item_id,
                quantity=quantity,
                timestamp=int(datetime.utcnow().timestamp()),
                action="increment",
            )
            logger.info(f"Reported {quantity} usage for item {subscription_item_id}")
        except stripe.error.StripeError as e:
            logger.error(f"Failed to report metered usage: {e}")
            raise

    @staticmethod
    def verify_webhook_signature(payload: bytes, signature: str, webhook_secret: str) -> Dict[str, Any]:
        """
        Verify Stripe webhook signature and construct event.

        Args:
            payload: Raw request body
            signature: Stripe-Signature header
            webhook_secret: Webhook endpoint secret

        Returns:
            Verified event dict

        Raises:
            ValueError: If signature is invalid
        """
        try:
            event = stripe.Webhook.construct_event(
                payload, signature, webhook_secret
            )
            return event
        except stripe.error.SignatureVerificationError as e:
            logger.error(f"Webhook signature verification failed: {e}")
            raise ValueError("Invalid webhook signature")


def get_plan_info(plan: str) -> Dict[str, Any]:
    """
    Get display info for a plan.

    Args:
        plan: Plan identifier

    Returns:
        Dict with plan name, price, description, credits, and limits
    """
    info = PLAN_INFO.get(plan, {})
    return {
        "id": plan,
        "name": info.get("name", plan.title()),
        "price": info.get("price", 0),
        "description": info.get("description", ""),
        "credits": PLAN_CREDITS.get(plan, 0),
        "limits": PLAN_LIMITS.get(plan, {}),
    }


def get_all_plans() -> list:
    """
    Get info for all available plans.

    Returns:
        List of plan info dicts
    """
    return [
        get_plan_info("starter"),
        get_plan_info("pro"),
        get_plan_info("pro_plus"),
        get_plan_info("ultimate"),
    ]
