"""
Billing Service

Handles subscription management, credit tracking, and feature gating.
"""
import logging
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from typing import Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session

from database.models import User, Subscription, CreditBalance, CreditTransaction, FeatureUsage
from services.stripe_service import PLAN_CREDITS, PLAN_LIMITS, CREDIT_COSTS

logger = logging.getLogger(__name__)


class BillingService:
    """
    Service class for billing operations.
    Requires a database session for all operations.
    """

    def __init__(self, db: Session):
        self.db = db

    def get_subscription(self, user_id: str) -> Optional[Subscription]:
        """
        Get user's active subscription.

        Args:
            user_id: Clerk user ID

        Returns:
            Subscription object or None
        """
        return self.db.query(Subscription).filter(
            Subscription.user_id == user_id,
            Subscription.status.in_(["active", "past_due", "trialing"])
        ).first()

    def has_active_subscription(self, user_id: str) -> bool:
        """
        Check if user has an active subscription.

        Args:
            user_id: Clerk user ID

        Returns:
            True if user has active subscription
        """
        subscription = self.get_subscription(user_id)
        return subscription is not None and subscription.status in ["active", "trialing"]

    def get_subscription_details(self, user_id: str) -> Dict[str, Any]:
        """
        Get full subscription details for API response.

        Args:
            user_id: Clerk user ID

        Returns:
            Dict with subscription info
        """
        subscription = self.get_subscription(user_id)

        if not subscription:
            return {
                "has_subscription": False,
                "plan": "free",
                "status": "none",
            }

        return {
            "has_subscription": True,
            "plan": subscription.plan,
            "status": subscription.status,
            "current_period_start": subscription.current_period_start.isoformat() if subscription.current_period_start else None,
            "current_period_end": subscription.current_period_end.isoformat() if subscription.current_period_end else None,
            "cancel_at_period_end": subscription.cancel_at_period_end,
            "limits": PLAN_LIMITS.get(subscription.plan, {}),
        }

    def check_feature_access(self, user_id: str, feature: str) -> Tuple[bool, str]:
        """
        Check if user has access to a feature.

        Args:
            user_id: Clerk user ID
            feature: Feature identifier (e.g., "x_growth_sessions", "crm_access")

        Returns:
            Tuple of (has_access: bool, reason: str)
        """
        subscription = self.get_subscription(user_id)

        if not subscription:
            return False, "No active subscription. Please subscribe to access this feature."

        if subscription.status == "past_due":
            return False, "Your payment is past due. Please update your payment method."

        limits = PLAN_LIMITS.get(subscription.plan, {})

        # Boolean features (like CRM access)
        if feature in limits and isinstance(limits[feature], bool):
            if not limits[feature]:
                return False, f"This feature requires the Ultimate plan. Please upgrade to access."
            return True, ""

        # Count-based features
        limit = limits.get(feature, 0)

        if limit == 0:
            plan_name = subscription.plan.replace("_", " ").title()
            return False, f"This feature is not included in your {plan_name} plan. Please upgrade."

        if limit == -1:  # Unlimited
            return True, ""

        # Check current usage
        current_usage = self._get_feature_usage(user_id, feature)
        if current_usage >= limit:
            return False, f"You've reached your monthly limit of {limit} for this feature. Please upgrade for more."

        return True, ""

    def _get_feature_usage(self, user_id: str, feature: str) -> int:
        """
        Get current month's usage for a feature.

        Args:
            user_id: Clerk user ID
            feature: Feature identifier

        Returns:
            Usage count
        """
        today = date.today()
        period_start = today.replace(day=1)

        usage = self.db.query(FeatureUsage).filter(
            FeatureUsage.user_id == user_id,
            FeatureUsage.feature == feature,
            FeatureUsage.period_start == period_start,
        ).first()

        return usage.count if usage else 0

    def increment_feature_usage(self, user_id: str, feature: str, count: int = 1) -> int:
        """
        Increment usage counter for a feature.

        Args:
            user_id: Clerk user ID
            feature: Feature identifier
            count: Amount to increment

        Returns:
            New usage count
        """
        today = date.today()
        period_start = today.replace(day=1)
        period_end = (period_start + relativedelta(months=1)) - relativedelta(days=1)

        usage = self.db.query(FeatureUsage).filter(
            FeatureUsage.user_id == user_id,
            FeatureUsage.feature == feature,
            FeatureUsage.period_start == period_start,
        ).first()

        if usage:
            usage.count += count
            usage.updated_at = datetime.utcnow()
        else:
            usage = FeatureUsage(
                user_id=user_id,
                feature=feature,
                count=count,
                period_start=period_start,
                period_end=period_end,
            )
            self.db.add(usage)

        self.db.commit()
        return usage.count

    def get_credit_balance(self, user_id: str) -> Dict[str, Any]:
        """
        Get user's current credit balance.

        Args:
            user_id: Clerk user ID

        Returns:
            Dict with credit info
        """
        subscription = self.get_subscription(user_id)

        if not subscription or not subscription.credit_balance:
            return {
                "has_credits": False,
                "monthly_allocation": 0,
                "credits_used": 0,
                "credits_remaining": 0,
                "credits_purchased": 0,
                "overage_credits": 0,
                "next_reset": None,
            }

        balance = subscription.credit_balance
        return {
            "has_credits": True,
            "monthly_allocation": balance.monthly_allocation,
            "credits_used": balance.credits_used,
            "credits_remaining": max(0, balance.monthly_allocation - balance.credits_used + balance.credits_purchased),
            "credits_purchased": balance.credits_purchased,
            "overage_credits": balance.overage_credits,
            "next_reset": balance.next_reset_at.isoformat() if balance.next_reset_at else None,
        }

    def check_credits(self, user_id: str, credits_needed: int) -> Tuple[bool, str]:
        """
        Check if user has enough credits.

        Args:
            user_id: Clerk user ID
            credits_needed: Number of credits required

        Returns:
            Tuple of (has_credits: bool, reason: str)
        """
        subscription = self.get_subscription(user_id)

        if not subscription or not subscription.credit_balance:
            return False, "No active subscription"

        balance = subscription.credit_balance
        available = (
            balance.monthly_allocation - balance.credits_used +
            balance.credits_purchased
        )

        # Allow overage - it will be billed
        return True, ""

    def consume_credits(
        self,
        user_id: str,
        credits: int,
        description: str,
        endpoint: str = None,
        agent_type: str = None
    ) -> Tuple[bool, str]:
        """
        Consume credits for an action.

        Args:
            user_id: Clerk user ID
            credits: Number of credits to consume
            description: Description of the action
            endpoint: Optional API endpoint
            agent_type: Optional agent type (x_growth, ads, crm, content_engine)

        Returns:
            Tuple of (success: bool, reason: str)
        """
        subscription = self.get_subscription(user_id)

        if not subscription or not subscription.credit_balance:
            return False, "No active subscription"

        balance = subscription.credit_balance
        available = (
            balance.monthly_allocation - balance.credits_used +
            balance.credits_purchased
        )

        if available < credits:
            # Record as overage (will be billed via Stripe metered billing)
            overage = credits - available
            balance.overage_credits += overage
            balance.credits_used = balance.monthly_allocation
            balance.credits_purchased = 0  # Use up purchased credits first
        else:
            # First use purchased credits, then monthly allocation
            if balance.credits_purchased >= credits:
                balance.credits_purchased -= credits
            else:
                remaining = credits - balance.credits_purchased
                balance.credits_purchased = 0
                balance.credits_used += remaining

        balance.updated_at = datetime.utcnow()

        # Record transaction
        transaction = CreditTransaction(
            user_id=user_id,
            transaction_type="usage",
            credits=-credits,
            description=description,
            endpoint=endpoint,
            agent_type=agent_type,
        )
        self.db.add(transaction)
        self.db.commit()

        logger.info(f"Consumed {credits} credits for user {user_id}: {description}")
        return True, ""

    def consume_credits_from_langsmith(
        self,
        user_id: str,
        run_id: str,
        agent_type: str,
        description: str = None
    ) -> Dict[str, Any]:
        """
        Consume credits based on actual LangSmith run cost.

        This is the preferred method for usage-based billing.
        It queries LangSmith for the actual cost and converts to credits with markup.

        Args:
            user_id: The user to charge
            run_id: LangSmith run ID to get cost from
            agent_type: Type of agent (x_growth, ads, crm, content_engine)
            description: Optional description for the transaction

        Returns:
            Dict with billing result:
            {
                "actual_cost": 4.55,
                "credits_charged": 682,
                "tokens": 200000,
                "run_id": "...",
                "success": True
            }
        """
        from services.langsmith_service import LangSmithService, USAGE_BILLING_CONFIG

        langsmith = LangSmithService()

        # Get actual cost from LangSmith (with child runs for full session cost)
        cost_data = langsmith.get_run_cost_with_children(run_id)
        actual_cost = cost_data.get("total_cost", 0)

        # Handle $0 cost (API error or cost not tracked)
        if actual_cost == 0:
            logger.warning(f"LangSmith returned $0 cost for run {run_id}, using minimum")
            actual_cost = USAGE_BILLING_CONFIG["minimum_cost"]

        # Convert to credits with markup
        credits_to_charge = langsmith.cost_to_credits(
            actual_cost,
            markup=USAGE_BILLING_CONFIG["markup_multiplier"]
        )

        # Ensure minimum charge
        credits_to_charge = max(credits_to_charge, USAGE_BILLING_CONFIG["minimum_credits"])

        # Consume the credits using existing method
        success, reason = self.consume_credits(
            user_id=user_id,
            credits=credits_to_charge,
            description=description or f"{agent_type} session",
            agent_type=agent_type
        )

        result = {
            "actual_cost": actual_cost,
            "credits_charged": credits_to_charge,
            "tokens": cost_data.get("total_tokens", 0),
            "prompt_tokens": cost_data.get("prompt_tokens", 0),
            "completion_tokens": cost_data.get("completion_tokens", 0),
            "run_id": run_id,
            "success": success,
            "reason": reason if not success else None
        }

        if success:
            logger.info(
                f"💳 Usage-based billing: charged {credits_to_charge} credits "
                f"(${actual_cost:.2f} actual) for user {user_id}, run {run_id}"
            )
        else:
            logger.error(f"Failed to charge credits for run {run_id}: {reason}")

        return result

    def get_usage_summary(self, user_id: str) -> Dict[str, Any]:
        """
        Get usage summary for current billing period.

        Args:
            user_id: Clerk user ID

        Returns:
            Dict with usage info per feature
        """
        subscription = self.get_subscription(user_id)

        if not subscription:
            return {"error": "No active subscription"}

        # Get all feature usage for this user in current period
        today = date.today()
        period_start = today.replace(day=1)

        usages = self.db.query(FeatureUsage).filter(
            FeatureUsage.user_id == user_id,
            FeatureUsage.period_start == period_start,
        ).all()

        limits = PLAN_LIMITS.get(subscription.plan, {})

        usage_dict = {}
        for u in usages:
            limit = limits.get(u.feature, 0)
            usage_dict[u.feature] = {
                "used": u.count,
                "limit": limit if limit != -1 else None,
                "unlimited": limit == -1,
                "percentage": (u.count / limit * 100) if limit > 0 else 0,
            }

        # Get credit usage breakdown by agent type
        credit_breakdown = self._get_credit_breakdown(user_id, subscription.current_period_start)

        return {
            "plan": subscription.plan,
            "period_start": period_start.isoformat(),
            "usage": usage_dict,
            "credits": self.get_credit_balance(user_id),
            "credit_breakdown": credit_breakdown,
        }

    def _get_credit_breakdown(self, user_id: str, period_start: datetime) -> Dict[str, int]:
        """
        Get credit usage breakdown by agent type for current billing period.

        Args:
            user_id: Clerk user ID
            period_start: Start of billing period

        Returns:
            Dict with credits used per agent type
        """
        from sqlalchemy import func

        # Query credit transactions grouped by agent_type
        results = self.db.query(
            CreditTransaction.agent_type,
            func.sum(func.abs(CreditTransaction.credits)).label('total')
        ).filter(
            CreditTransaction.user_id == user_id,
            CreditTransaction.transaction_type == "usage",
            CreditTransaction.created_at >= period_start if period_start else True,
        ).group_by(CreditTransaction.agent_type).all()

        breakdown = {}
        for agent_type, total in results:
            if agent_type:
                breakdown[agent_type] = int(total or 0)

        return breakdown

    def create_subscription_record(
        self,
        user_id: str,
        stripe_subscription_id: str,
        stripe_price_id: str,
        plan: str,
        current_period_start: datetime,
        current_period_end: datetime,
    ) -> Subscription:
        """
        Create a new subscription record after successful Stripe checkout.

        Args:
            user_id: Clerk user ID
            stripe_subscription_id: Stripe subscription ID
            stripe_price_id: Stripe price ID
            plan: Plan identifier
            current_period_start: Billing period start
            current_period_end: Billing period end

        Returns:
            Created Subscription object
        """
        # Check if subscription already exists
        existing = self.db.query(Subscription).filter(
            Subscription.user_id == user_id
        ).first()

        if existing:
            # Update existing subscription
            existing.stripe_subscription_id = stripe_subscription_id
            existing.stripe_price_id = stripe_price_id
            existing.plan = plan
            existing.status = "active"
            existing.current_period_start = current_period_start
            existing.current_period_end = current_period_end
            existing.cancel_at_period_end = False
            existing.updated_at = datetime.utcnow()

            # Update credit balance
            if existing.credit_balance:
                existing.credit_balance.monthly_allocation = PLAN_CREDITS.get(plan, 5000)
                existing.credit_balance.next_reset_at = current_period_end
            else:
                credit_balance = CreditBalance(
                    subscription_id=existing.id,
                    monthly_allocation=PLAN_CREDITS.get(plan, 5000),
                    next_reset_at=current_period_end,
                )
                self.db.add(credit_balance)

            subscription = existing
        else:
            # Create new subscription
            subscription = Subscription(
                user_id=user_id,
                stripe_subscription_id=stripe_subscription_id,
                stripe_price_id=stripe_price_id,
                plan=plan,
                status="active",
                current_period_start=current_period_start,
                current_period_end=current_period_end,
            )
            self.db.add(subscription)
            self.db.flush()  # Get the ID

            # Create credit balance
            credit_balance = CreditBalance(
                subscription_id=subscription.id,
                monthly_allocation=PLAN_CREDITS.get(plan, 5000),
                next_reset_at=current_period_end,
            )
            self.db.add(credit_balance)

        # Update user's plan field for backwards compatibility
        user = self.db.query(User).filter(User.id == user_id).first()
        if user:
            user.plan = plan

        # Record allocation transaction
        transaction = CreditTransaction(
            user_id=user_id,
            transaction_type="allocation",
            credits=PLAN_CREDITS.get(plan, 5000),
            description=f"Monthly credit allocation for {plan} plan",
        )
        self.db.add(transaction)

        self.db.commit()
        logger.info(f"Created subscription for user {user_id}: {plan}")
        return subscription

    def update_subscription_status(
        self,
        stripe_subscription_id: str,
        status: str,
        plan: str = None,
        current_period_start: datetime = None,
        current_period_end: datetime = None,
        cancel_at_period_end: bool = None,
    ) -> Optional[Subscription]:
        """
        Update subscription status from Stripe webhook.

        Args:
            stripe_subscription_id: Stripe subscription ID
            status: New status
            plan: Optional new plan
            current_period_start: Optional new period start
            current_period_end: Optional new period end
            cancel_at_period_end: Optional cancellation flag

        Returns:
            Updated Subscription or None
        """
        subscription = self.db.query(Subscription).filter(
            Subscription.stripe_subscription_id == stripe_subscription_id
        ).first()

        if not subscription:
            logger.warning(f"Subscription not found: {stripe_subscription_id}")
            return None

        subscription.status = status
        subscription.updated_at = datetime.utcnow()

        if plan:
            subscription.plan = plan
            # Update credit allocation if plan changed
            if subscription.credit_balance:
                subscription.credit_balance.monthly_allocation = PLAN_CREDITS.get(plan, 5000)

            # Update user's plan field
            user = self.db.query(User).filter(User.id == subscription.user_id).first()
            if user:
                user.plan = plan

        if current_period_start:
            subscription.current_period_start = current_period_start
        if current_period_end:
            subscription.current_period_end = current_period_end
            if subscription.credit_balance:
                subscription.credit_balance.next_reset_at = current_period_end
        if cancel_at_period_end is not None:
            subscription.cancel_at_period_end = cancel_at_period_end

        self.db.commit()
        logger.info(f"Updated subscription {stripe_subscription_id}: status={status}")
        return subscription

    def cancel_subscription(self, stripe_subscription_id: str) -> Optional[Subscription]:
        """
        Mark subscription as canceled.

        Args:
            stripe_subscription_id: Stripe subscription ID

        Returns:
            Updated Subscription or None
        """
        subscription = self.db.query(Subscription).filter(
            Subscription.stripe_subscription_id == stripe_subscription_id
        ).first()

        if not subscription:
            return None

        subscription.status = "canceled"
        subscription.canceled_at = datetime.utcnow()
        subscription.updated_at = datetime.utcnow()

        # Update user's plan to free
        user = self.db.query(User).filter(User.id == subscription.user_id).first()
        if user:
            user.plan = "free"

        self.db.commit()
        logger.info(f"Canceled subscription {stripe_subscription_id}")
        return subscription

    def reset_monthly_credits(self, stripe_subscription_id: str) -> bool:
        """
        Reset credits at the start of a new billing period.
        Called when invoice.payment_succeeded webhook is received.

        Args:
            stripe_subscription_id: Stripe subscription ID

        Returns:
            True if reset was successful
        """
        subscription = self.db.query(Subscription).filter(
            Subscription.stripe_subscription_id == stripe_subscription_id
        ).first()

        if not subscription or not subscription.credit_balance:
            return False

        balance = subscription.credit_balance

        # Report overage to Stripe for billing (if implemented)
        if balance.overage_credits > 0:
            logger.info(f"User {subscription.user_id} had {balance.overage_credits} overage credits")
            # TODO: Report to Stripe metered billing if configured

        # Record reset transaction
        transaction = CreditTransaction(
            user_id=subscription.user_id,
            transaction_type="reset",
            credits=balance.monthly_allocation,
            description="Monthly credit reset",
        )
        self.db.add(transaction)

        # Reset counters
        balance.credits_used = 0
        balance.overage_credits = 0
        balance.last_reset_at = datetime.utcnow()
        balance.next_reset_at = subscription.current_period_end
        balance.updated_at = datetime.utcnow()

        self.db.commit()
        logger.info(f"Reset credits for subscription {stripe_subscription_id}")
        return True
