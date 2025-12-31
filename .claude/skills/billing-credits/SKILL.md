---
name: billing-credits
description: Work with the Stripe billing and credit system. Use when modifying subscriptions, credit allocation, usage tracking, or payment flows. Triggers on "billing", "credits", "subscription", "stripe", "payment", "pricing".
allowed-tools: Read, Edit, Grep
---

# Billing System Guide

## Key Files

| File | Purpose |
|------|---------|
| `billing_routes.py` | Billing API endpoints |
| `services/stripe_service.py` | Stripe SDK integration |
| `stripe_webhooks.py` | Webhook event handlers |
| `database/models.py` | Subscription, CreditBalance, etc. |

## Subscription Plans

| Plan | Monthly Credits | Features |
|------|-----------------|----------|
| `free` | 100 | Basic features |
| `pro` | 1000 | + Advanced workflows |
| `pro_plus` | 5000 | + Priority support |
| `ultimate` | Unlimited | Full access |

## Database Models

### Subscription
```python
class Subscription(Base):
    user_id: str
    stripe_customer_id: str
    stripe_subscription_id: str
    plan: str  # free, pro, pro_plus, ultimate
    status: str  # active, canceled, past_due
    current_period_end: datetime
```

### CreditBalance
```python
class CreditBalance(Base):
    user_id: str
    monthly_credits: int  # Allocated per plan
    used_credits: int  # Used this period
    bonus_credits: int  # One-time additions
    reset_date: datetime  # Monthly reset
```

### CreditTransaction
```python
class CreditTransaction(Base):
    user_id: str
    amount: int  # Positive = add, Negative = deduct
    transaction_type: str  # usage, refund, bonus, reset
    description: str
    created_at: datetime
```

## Credit Operations

### Deduct Credits
```python
async def deduct_credits(db: AsyncSession, user_id: str, amount: int, description: str):
    balance = await db.execute(
        select(CreditBalance).where(CreditBalance.user_id == user_id)
    )
    balance = balance.scalar_one()

    # Check available credits
    available = balance.monthly_credits - balance.used_credits + balance.bonus_credits
    if available < amount:
        raise HTTPException(status_code=402, detail="Insufficient credits")

    # Deduct
    balance.used_credits += amount

    # Log transaction
    transaction = CreditTransaction(
        user_id=user_id,
        amount=-amount,
        transaction_type="usage",
        description=description
    )
    db.add(transaction)
    await db.commit()
```

### Check Credits
```python
async def check_credits(db: AsyncSession, user_id: str, required: int) -> bool:
    balance = await get_credit_balance(db, user_id)
    available = balance.monthly_credits - balance.used_credits + balance.bonus_credits
    return available >= required
```

## Stripe Integration

### Create Checkout Session
```python
from services.stripe_service import create_checkout_session

@app.post("/api/billing/checkout")
async def create_checkout(
    plan: str,
    user_id: str = Depends(get_current_user)
):
    session = await create_checkout_session(
        user_id=user_id,
        plan=plan,
        success_url="https://app.paralleluniverse.ai/settings/billing?success=true",
        cancel_url="https://app.paralleluniverse.ai/settings/billing?canceled=true"
    )
    return {"checkout_url": session.url}
```

### Webhook Handler
```python
@app.post("/api/webhooks/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    event = stripe.Webhook.construct_event(
        payload, sig_header, STRIPE_WEBHOOK_SECRET
    )

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        await handle_checkout_completed(session)

    elif event["type"] == "customer.subscription.updated":
        subscription = event["data"]["object"]
        await handle_subscription_updated(subscription)

    return {"received": True}
```

## Feature Gating

```python
async def require_feature(db: AsyncSession, user_id: str, feature: str):
    """Check if user has access to a feature."""
    subscription = await get_subscription(db, user_id)

    feature_access = {
        "free": ["basic_posts", "analytics"],
        "pro": ["basic_posts", "analytics", "advanced_workflows", "scheduling"],
        "pro_plus": ["basic_posts", "analytics", "advanced_workflows", "scheduling", "ads"],
        "ultimate": ["*"]  # All features
    }

    allowed = feature_access.get(subscription.plan, [])
    if "*" not in allowed and feature not in allowed:
        raise HTTPException(
            status_code=403,
            detail=f"Upgrade to access {feature}"
        )
```

## Usage Tracking

```python
async def track_usage(db: AsyncSession, user_id: str, feature: str, count: int = 1):
    """Track feature usage for analytics."""
    usage = FeatureUsage(
        user_id=user_id,
        feature=feature,
        count=count,
        created_at=datetime.utcnow()
    )
    db.add(usage)
    await db.commit()
```

## Best Practices

1. **Always check credits** before expensive operations
2. **Log all transactions** for audit trail
3. **Handle webhook idempotency** - events may be sent multiple times
4. **Validate Stripe signatures** on all webhooks
5. **Use test mode** during development (sk_test_ keys)
6. **Reset credits monthly** via cron job
