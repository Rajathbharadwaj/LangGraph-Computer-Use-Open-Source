# Billing & Pricing Documentation

## Overview

Parallel Universe uses a subscription-based pricing model with credit allocations and feature limits. Billing is handled through Stripe with usage-based tracking via LangSmith.

---

## Pricing Plans

| Plan | Price/Month | Credits | Target User |
|------|-------------|---------|-------------|
| **Starter** | $99 | 500 | New creators getting started |
| **Pro** | $299 | 2,000 | Individual creators ready to scale |
| **Pro Plus** | $499 | 5,000 | Growing businesses |
| **Ultimate** | $799 | 10,000 | Agencies and power users |

---

## Feature Limits by Plan

| Feature | Starter | Pro | Pro Plus | Ultimate |
|---------|---------|-----|----------|----------|
| X Growth Sessions | 5/mo | 15/mo | 50/mo | 100/mo |
| Content Generations | 20/mo | 100/mo | 300/mo | 500/mo |
| Scheduled Posts | 10/mo | 50/mo | Unlimited | Unlimited |
| Ads Campaigns | - | - | 10/mo | 50/mo |
| CRM Access | - | - | - | Full |
| AI Image Generations | - | 10/mo | 50/mo | 200/mo |
| Analytics History | 3 days | 7 days | 30 days | 90 days |

---

## Credit System

### How Credits Work

Credits are consumed when users perform AI-powered actions. The credit system provides flexible billing while ensuring profitability.

**Credit Value by Plan:**

| Plan | Credits | Credit Value | Effective Cost/Credit |
|------|---------|--------------|----------------------|
| Starter | 500 | $99 / 500 | $0.198 |
| Pro | 2,000 | $299 / 2,000 | $0.150 |
| Pro Plus | 5,000 | $499 / 5,000 | $0.100 |
| Ultimate | 10,000 | $799 / 10,000 | $0.080 |

### Credit Costs (Fixed)

These are fixed costs for specific operations:

```python
CREDIT_COSTS = {
    "sonnet_message": 1,        # ~$0.01 actual cost
    "opus_message": 3,          # ~$0.05 actual cost
    "computer_use_minute": 1,   # ~$0.005 actual cost
    "ai_image_generation": 27,  # KIE Nano Banana Pro: 18 credits × 1.5 markup
    "web_search": 1,            # ~$0.02 actual cost
}

AGENT_SESSION_COSTS = {
    "x_growth": 5,
    "ads": 10,
    "crm": 5,
    "content_engine": 3,
}
```

### AI Image Generation Pricing

AI images are generated using KIE AI's Nano Banana Pro model:

| Resolution | KIE Cost | With 1.5x Markup | Credits |
|------------|----------|------------------|---------|
| 1K | 18 credits | 18 × 1.5 | **27 credits** |

**Feature Limits by Plan:**

| Plan | AI Images/Month |
|------|-----------------|
| Starter | 0 (not available) |
| Pro | 10 |
| Pro Plus | 50 |
| Ultimate | 200 |

**Note:** Credits are only charged on successful image generation.

### Usage-Based Billing (Primary)

Credits are calculated from actual LangSmith costs:

```
credits = actual_cost × 100 × markup_multiplier (1.5)
```

**Example:** $10 session cost = 10 × 100 × 1.5 = **1,500 credits**

**Configuration:**
```python
USAGE_BILLING = {
    "markup_multiplier": 1.5,  # 50% profit margin
    "cents_per_credit": 1,     # $0.01 = 1 credit base
    "minimum_credits": 50,     # Min charge per session
    "minimum_cost": 0.50,      # $0.50 fallback
}
```

---

## Cost Analysis

### Real-World Session Costs (from LangSmith)

| Session Type | Duration | LLM Calls | Actual Cost |
|--------------|----------|-----------|-------------|
| Short | 5 min | ~50 | $3 |
| Medium | 20 min | ~200 | $8 |
| Long | 60 min | ~500 | $17 |
| **Average** | **25 min** | **~250** | **$10** |

### Estimated Sessions per Plan

| Plan | Credits | Avg Session Cost | Est. Sessions |
|------|---------|------------------|---------------|
| Starter | 500 | 150 credits | ~3 |
| Pro | 2,000 | 150 credits | ~13 |
| Pro Plus | 5,000 | 150 credits | ~33 |
| Ultimate | 10,000 | 150 credits | ~66 |

---

## Profit Margins

### Per-Session Profitability

Using $10 average session cost and 50% markup:

| Plan | Revenue/Session | Cost | Margin |
|------|-----------------|------|--------|
| Starter | $29.70 | $10 | 66% |
| Pro | $22.50 | $10 | 56% |
| Pro Plus | $15.00 | $10 | 33% |
| Ultimate | $12.00 | $10 | 17% |

### Monthly User Profitability

**Light User (uses 30% of credits):**

| Plan | Revenue | Est. Cost | Margin |
|------|---------|-----------|--------|
| Starter | $99 | ~$10 | 90% |
| Pro | $299 | ~$40 | 87% |
| Pro Plus | $499 | ~$100 | 80% |
| Ultimate | $799 | ~$200 | 75% |

**Heavy User (uses 100% of credits):**

| Plan | Revenue | Est. Cost | Margin |
|------|---------|-----------|--------|
| Starter | $99 | ~$33 | 67% |
| Pro | $299 | ~$133 | 56% |
| Pro Plus | $499 | ~$333 | 33% |
| Ultimate | $799 | ~$667 | 17% |

---

## Stripe Configuration

### Environment Variables

```bash
STRIPE_SECRET_KEY=sk_live_xxx
STRIPE_WEBHOOK_SECRET=whsec_xxx
STRIPE_PRICE_STARTER=price_xxx
STRIPE_PRICE_PRO=price_xxx
STRIPE_PRICE_PRO_PLUS=price_xxx
STRIPE_PRICE_ULTIMATE=price_xxx
```

### Webhook Events Handled

| Event | Action |
|-------|--------|
| `checkout.session.completed` | Create subscription, allocate credits |
| `customer.subscription.updated` | Update plan, adjust credits |
| `customer.subscription.deleted` | Cancel subscription |
| `invoice.payment_succeeded` | Reset monthly credits |
| `invoice.payment_failed` | Mark subscription past_due |

---

## Path to Profitability

### Revenue Targets

| Milestone | Customers | MRR | Monthly Profit |
|-----------|-----------|-----|----------------|
| Break-even | 5-10 | ~$2k | ~$1k |
| Sustainable | 25 | ~$7k | ~$4k |
| **$10k Profit** | **45-50** | **~$15k** | **~$10k** |
| Scale | 100 | ~$30k | ~$20k |

### Customer Mix Assumption

- 30% Starter ($99)
- 40% Pro ($299)
- 20% Pro Plus ($499)
- 10% Ultimate ($799)

**Average Revenue per Customer:** ~$300/month

---

## Files Reference

| File | Purpose |
|------|---------|
| `services/stripe_service.py` | Stripe API integration, plan definitions |
| `services/billing_service.py` | Credit tracking, feature gating |
| `billing_routes.py` | API endpoints for billing |
| `stripe_webhooks.py` | Webhook handlers |
| `database/models.py` | Subscription, CreditBalance models |

---

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/billing/plans` | GET | List all plans |
| `/api/billing/subscription` | GET | Get user's subscription |
| `/api/billing/checkout` | POST | Create checkout session |
| `/api/billing/portal` | POST | Create customer portal |
| `/api/billing/usage` | GET | Get credit usage |

---

## Database Schema

### Subscription Table
```sql
- id (UUID)
- user_id (Clerk user ID)
- stripe_subscription_id
- stripe_price_id
- plan (starter/pro/pro_plus/ultimate)
- status (active/past_due/canceled)
- current_period_start
- current_period_end
- cancel_at_period_end
```

### CreditBalance Table
```sql
- id (UUID)
- subscription_id (FK)
- monthly_allocation
- credits_used
- credits_purchased
- overage_credits
- last_reset_at
- next_reset_at
```

### FeatureUsage Table
```sql
- id (UUID)
- user_id
- feature (x_growth_sessions, content_generations, etc.)
- count
- period_start
- period_end
```

---

*Last updated: December 23, 2025*
