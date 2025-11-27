# Clerk + Database Production Setup Guide

Complete guide to integrate Clerk authentication with your PostgreSQL database for production.

## Overview

This setup enables:
1. **Clerk handles authentication** - User sign up, sign in, session management
2. **Webhooks auto-sync users** - When users sign up in Clerk, they're automatically created in your database
3. **JWT verification** - Backend verifies Clerk tokens on every API request
4. **Secure APIs** - User ID extracted from verified token, not from frontend

## Architecture Flow

```
User signs up → Clerk webhook fires → User created in PostgreSQL
                                                  ↓
User signs in → Clerk session created → Frontend gets token
                                                  ↓
Frontend API call → Token sent in header → Backend verifies token → User ID extracted
                                                                            ↓
                                                    Database operations with verified user_id
```

## Step 1: Get Your Clerk Credentials

### 1.1 Go to Clerk Dashboard
- Visit: https://dashboard.clerk.com
- Select your application

### 1.2 Get API Keys
Navigate to **API Keys** section:

```bash
# Already in your .env:
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...
```

## Step 2: Setup Clerk Webhooks

### 2.1 Create Webhook Endpoint in Clerk

1. Go to **Webhooks** in Clerk Dashboard
2. Click **Add Endpoint**
3. Enter your webhook URL:
   ```
   https://your-domain.com/api/webhooks/clerk
   ```

   **For local testing with ngrok:**
   ```bash
   # Install ngrok
   brew install ngrok  # or: npm install -g ngrok

   # Start ngrok tunnel
   ngrok http 8002

   # Use the ngrok URL in Clerk:
   https://abc123.ngrok.io/api/webhooks/clerk
   ```

4. Select these events:
   - ✅ `user.created`
   - ✅ `user.updated`
   - ✅ `user.deleted`

5. Click **Create**

### 2.2 Get Webhook Signing Secret

After creating the webhook:
1. Click on your webhook endpoint
2. Copy the **Signing Secret** (starts with `whsec_...`)
3. Add to `.env`:
   ```bash
   CLERK_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxx
   ```

## Step 3: Test Webhook Integration

### 3.1 Start Your Backend
```bash
# Make sure backend is running
python backend_websocket_server.py
```

### 3.2 Test with Clerk Dashboard

1. Go to **Webhooks** in Clerk Dashboard
2. Select your webhook
3. Click **Testing** tab
4. Send a test `user.created` event
5. Check your backend logs for:
   ```
   📨 Received Clerk webhook: user.created
   ✅ Created user: user_xxxxx (email@example.com)
   ```

### 3.3 Verify Database
```bash
# Connect to PostgreSQL
PGPASSWORD=password psql -U postgres -h localhost -d xgrowth

# Check if user was created
SELECT id, email, created_at FROM users;
```

## Step 4: Update Frontend to Send Auth Tokens

### 4.1 Update API Client

Edit `/home/rajathdb/cua-frontend/lib/api/scheduled-posts.ts`:

```typescript
import { useAuth } from "@clerk/nextjs";

export async function fetchScheduledPosts(
  userId: string,
  startDate?: Date,
  endDate?: Date
): Promise<ScheduledPost[]> {
  // Get Clerk token
  const { getToken } = useAuth();
  const token = await getToken();

  const params = new URLSearchParams({ user_id: userId });
  if (startDate) params.append("start_date", startDate.toISOString());
  if (endDate) params.append("end_date", endDate.toISOString());

  const response = await fetch(`${API_BASE_URL}/api/scheduled-posts?${params}`, {
    headers: {
      'Authorization': `Bearer ${token}`,  // ← Add this!
    },
  });

  if (!response.ok) throw new Error(`Failed to fetch scheduled posts`);

  const data = await response.json();
  return data.posts || [];
}
```

## Step 5: Enable Authentication on Backend (Production)

Currently, the backend accepts `user_id` from frontend without verification. For production:

### 5.1 Update Scheduled Posts Endpoints

Edit `/home/rajathdb/cua/backend_websocket_server.py`:

```python
# Before (development):
@app.get("/api/scheduled-posts")
async def get_scheduled_posts(
    user_id: str,  # ← Trusts frontend
    db: Session = Depends(get_db)
):

# After (production):
@app.get("/api/scheduled-posts")
async def get_scheduled_posts(
    user_id: str = Depends(get_current_user),  # ← Verifies token
    db: Session = Depends(get_db)
):
```

Update ALL these endpoints:
- `GET /api/scheduled-posts`
- `POST /api/scheduled-posts`
- `PUT /api/scheduled-posts/{post_id}`
- `DELETE /api/scheduled-posts/{post_id}`
- `POST /api/scheduled-posts/generate-ai`

### 5.2 Example Full Update

```python
@app.get("/api/scheduled-posts")
async def get_scheduled_posts(
    current_user_id: str = Depends(get_current_user),  # ← Verifies JWT
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Fetch scheduled posts for authenticated user"""
    try:
        # Get user's X accounts
        x_accounts = db.query(XAccount).filter(
            XAccount.user_id == current_user_id  # ← Use verified ID
        ).all()

        # ... rest of logic
```

## Step 6: Production Deployment Checklist

### 6.1 Environment Variables

Ensure these are set in production:

```bash
# Clerk
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_live_...  # ← Note: pk_live not pk_test
CLERK_SECRET_KEY=sk_live_...                    # ← Note: sk_live not sk_test
CLERK_WEBHOOK_SECRET=whsec_...

# Database
DATABASE_URL=postgresql://user:pass@host:5432/dbname
POSTGRES_PASSWORD=secure_password_here

# API URL (for frontend)
NEXT_PUBLIC_API_URL=https://api.your-domain.com
```

### 6.2 Update CORS

In `backend_websocket_server.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",           # Development
        "https://your-domain.com",         # Production
        "https://www.your-domain.com",     # Production
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 6.3 Enable JWT Verification

Update `clerk_auth.py` line 67:

```python
# DEVELOPMENT (current):
payload = jwt.decode(
    token,
    options={"verify_signature": False}  # ← INSECURE
)

# PRODUCTION (change to):
# Use PyJWT with Clerk's JWKS endpoint
import requests
from jwt import PyJWKClient

# Get Clerk's JWKS URL from your instance
# Format: https://{clerk-domain}/.well-known/jwks.json
jwks_url = f"https://present-wasp-53.clerk.accounts.dev/.well-known/jwks.json"
jwks_client = PyJWKClient(jwks_url)

signing_key = jwks_client.get_signing_key_from_jwt(token)

payload = jwt.decode(
    token,
    signing_key.key,
    algorithms=["RS256"],
    options={"verify_signature": True}  # ← SECURE
)
```

## Step 7: Test Production Setup

### 7.1 Test User Sign Up
1. Sign up a new user in your app
2. Check Clerk webhook logs
3. Verify user appears in database:
   ```sql
   SELECT * FROM users ORDER BY created_at DESC LIMIT 1;
   ```

### 7.2 Test Authenticated API Call
```bash
# Get token from browser (inspect network tab)
TOKEN="eyJhbGc..."

# Test API with token
curl -H "Authorization: Bearer $TOKEN" \
  https://your-api.com/api/scheduled-posts?user_id=user_xxx
```

Should return posts for authenticated user only.

### 7.3 Test Token Verification
```bash
# Try with invalid token (should fail)
curl -H "Authorization: Bearer invalid_token" \
  https://your-api.com/api/scheduled-posts?user_id=user_xxx

# Expected response:
{"detail": "Invalid token"}
```

## Security Best Practices

### 1. Never Trust Frontend Data
❌ **Bad:**
```python
user_id: str  # Frontend can send any user_id
```

✅ **Good:**
```python
user_id: str = Depends(get_current_user)  # Verified from JWT
```

### 2. Always Verify Webhook Signatures
The webhook handler already does this:
```python
wh = Webhook(CLERK_WEBHOOK_SECRET)
payload = wh.verify(body_str, headers)  # ← Verifies Clerk sent it
```

### 3. Use Environment Variables
Never hardcode secrets:
```python
CLERK_SECRET_KEY = os.getenv("CLERK_SECRET_KEY")  # ✅ Good
CLERK_SECRET_KEY = "sk_test_abc123"                 # ❌ Bad
```

### 4. Enable HTTPS in Production
- Use SSL/TLS certificates
- Redirect HTTP to HTTPS
- Set secure cookie flags

### 5. Rate Limiting
Add rate limiting to prevent abuse:
```python
from slowapi import Limiter, _rate_limit_exceeded_handler

limiter = Limiter(key_func=lambda: request.client.host)
app.state.limiter = limiter

@app.get("/api/scheduled-posts")
@limiter.limit("100/hour")  # ← 100 requests per hour
async def get_scheduled_posts(...):
    ...
```

## Troubleshooting

### Webhook not receiving events
1. Check ngrok is running (for local testing)
2. Verify webhook URL is correct in Clerk
3. Check backend logs for incoming requests
4. Test with Clerk's testing tab

### JWT verification failing
1. Verify `CLERK_SECRET_KEY` is correct
2. Check token is being sent in `Authorization` header
3. Ensure token hasn't expired (15 minute default)
4. Check JWKS URL matches your Clerk instance

### Database user not created
1. Check webhook secret is correct
2. Verify database connection works
3. Check for errors in webhook handler logs
4. Ensure `users` table exists

### CORS errors
1. Add your domain to `allow_origins`
2. Enable `allow_credentials=True`
3. Check protocol (http vs https) matches

## Migration from Development to Production

### Phase 1: Current (Development)
- ✅ Clerk authenticates users
- ✅ Frontend passes user_id
- ⚠️ Backend trusts user_id without verification

### Phase 2: Add Webhooks (Safe)
- ✅ Setup Clerk webhooks
- ✅ Auto-create users in database
- ⚠️ Still accepting user_id from frontend

### Phase 3: Enable JWT Verification (Production Ready)
- ✅ Frontend sends tokens
- ✅ Backend verifies tokens
- ✅ User ID extracted from verified token
- ✅ Production ready! 🎉

You can deploy **Phase 2** immediately without breaking anything. Phase 3 requires frontend updates.

## Quick Start Commands

```bash
# 1. Install dependencies
pip install pyjwt[crypto] svix

# 2. Add webhook secret to .env
echo "CLERK_WEBHOOK_SECRET=whsec_your_secret" >> .env

# 3. Start backend
python backend_websocket_server.py

# 4. Test webhook (in another terminal)
# Use Clerk Dashboard → Webhooks → Testing

# 5. Verify user created
PGPASSWORD=password psql -U postgres -h localhost -d xgrowth -c "SELECT * FROM users;"
```

## Support

- **Clerk Docs**: https://clerk.com/docs
- **Webhook Docs**: https://clerk.com/docs/webhooks/overview
- **JWT Docs**: https://clerk.com/docs/request-authentication/validate-session-tokens

---

**Ready for Production!** 🚀

You now have:
- ✅ Secure authentication with Clerk
- ✅ Auto-synced users via webhooks
- ✅ JWT token verification (when enabled)
- ✅ Database integration
- ✅ Production-ready architecture
