# Deployment Recovery Procedures

## Overview

This document covers common deployment issues and their fixes for the Parallel Universe backend services.

---

## Issue 1: VNC Session Returns 500 Error

### Symptoms
- Frontend shows: `Error fetching VNC session: Error: Failed to get VNC session: 500`
- Backend logs show 500 for `/api/vnc/session` but NO error message inside the endpoint

### Root Cause
**Missing `CLERK_SECRET_KEY` environment variable** in backend-api Cloud Run service.

The `/api/vnc/session` endpoint uses `Depends(get_current_user)` which calls `verify_clerk_token()` in `clerk_auth.py`. This function requires `CLERK_SECRET_KEY` to verify JWT tokens:

```python
# clerk_auth.py line 73-77
if not CLERK_SECRET_KEY:
    raise HTTPException(
        status_code=500,
        detail="Clerk secret key not configured"
    )
```

### Why This Happens
When deploying with `gcloud run deploy`, if you use `--set-env-vars`, it **REPLACES ALL** environment variables, not appends to them. So if you deploy with only `DATABASE_URL` and `REDIS_HOST`, you lose `CLERK_SECRET_KEY`.

### Fix
Always include ALL required environment variables when deploying:

```bash
gcloud run deploy backend-api \
  --image gcr.io/parallel-universe-prod/backend-api:latest \
  --project parallel-universe-prod \
  --region us-central1 \
  --vpc-connector paralleluniverse-vpc \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --timeout 600 \
  --set-env-vars "DATABASE_URL=$DATABASE_URL,REDIS_HOST=10.110.183.147,REDIS_PORT=6379,CLERK_SECRET_KEY=$CLERK_SECRET_KEY,NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=$NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY"
```

### Check Current Env Vars
```bash
gcloud run services describe backend-api \
  --project parallel-universe-prod \
  --region us-central1 \
  --format="yaml(spec.template.spec.containers[0].env)"
```

---

## Issue 2: 'NoneType' object has no attribute 'search' / 'put'

### Symptoms
- Discovery endpoints fail with `'NoneType' object has no attribute 'search'`
- Activity logs endpoint returns error but 200 status

### Root Cause
**PostgresStore (`store`) fails to initialize** and is `None`. Code tries to call `store.search()` or `store.put()` on `None`.

The store initialization in `backend_websocket_server.py` tries to connect to localhost:5433 instead of the proper DATABASE_URL because LangGraph's PostgresStore uses a different connection string format.

### Fix Applied
Added null checks throughout the code:

**In `backend_websocket_server.py` (discovery endpoints):**
```python
# Check if store is available before using
if store:
    lock_items = list(store.search(lock_namespace, limit=1))
    # ... rest of lock logic
```

**In `x_native_common_followers.py`:**
```python
# Update progress (only if store is available)
if self.store:
    self.store.put(progress_namespace, "current", {...})

# Store results (only if store is available)
if self.store:
    self.store.put(self.namespace_graph, "latest", graph_data)
```

### Impact When Store is None
Discovery still works, but:
- No progress tracking
- No cancellation support
- Results not cached to store (but still returned to frontend)

---

## Issue 3: X Native Discovery Only Finds 1 Follower

### Symptoms
- Discovery completes but only analyzes 1 account
- Logs show: `Got 1 followers`

### Root Cause
Code was navigating to `/verified_followers` instead of `/followers`. The verified_followers tab only shows accounts with blue checkmarks.

### Fix Applied
Changed `x_native_common_followers.py` line 52-53:

```python
# OLD (wrong)
url = f"https://x.com/{username}/verified_followers"

# NEW (correct)
url = f"https://x.com/{username}/followers"
```

---

## Issue 4: "No cookies found for this user" Error

### Symptoms
- Clicking "Connect to VNC" shows: `No cookies found for this user`
- Backend logs show: `ConnectionRefusedError: [Errno 111] Connect call failed ('127.0.0.1', 8001)`

### Root Cause
**Missing `EXTENSION_BACKEND_URL` environment variable** in backend-api Cloud Run service.

The code defaults to `http://localhost:8001` when the env var is not set:
```python
# backend_websocket_server.py line 21
EXTENSION_BACKEND_URL = os.getenv("EXTENSION_BACKEND_URL", "http://localhost:8001")
```

This causes the backend to try connecting to localhost inside the Cloud Run container, which fails.

### Fix
Add the `EXTENSION_BACKEND_URL` environment variable:
```bash
gcloud run services update backend-api \
  --project parallel-universe-prod \
  --region us-central1 \
  --update-env-vars "EXTENSION_BACKEND_URL=https://extension-backend-service-644185288504.us-central1.run.app"
```

### Verify Cookies Exist
First, verify that cookies are actually stored for the user:
```bash
curl "https://extension-backend-service-644185288504.us-central1.run.app/cookies/{user_id}"
```

If this returns `success: true` with cookies, the issue is the env var. If it returns no cookies, the user needs to sync cookies via the Chrome extension.

---

## Required Environment Variables for backend-api

| Variable | Value | Purpose |
|----------|-------|---------|
| `DATABASE_URL` | `postgresql://...` (from .env.prod) | PostgreSQL connection |
| `REDIS_HOST` | `10.110.183.147` | Redis for VNC session lookup |
| `REDIS_PORT` | `6379` | Redis port |
| `CLERK_SECRET_KEY` | `sk_live_...` (from .env.prod) | JWT verification |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | `pk_live_...` (from .env.prod) | Clerk public key |
| `EXTENSION_BACKEND_URL` | `https://extension-backend-service-644185288504.us-central1.run.app` | Extension backend for cookie fetching |

---

## Full Recovery Deploy Command

If backend-api is broken, run this complete deploy command:

```bash
# First, build the latest image
gcloud builds submit \
  --tag gcr.io/parallel-universe-prod/backend-api:latest \
  --project parallel-universe-prod \
  --timeout=600s

# Then deploy with ALL environment variables
gcloud run deploy backend-api \
  --image gcr.io/parallel-universe-prod/backend-api:latest \
  --project parallel-universe-prod \
  --region us-central1 \
  --vpc-connector paralleluniverse-vpc \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --timeout 600 \
  --set-env-vars "DATABASE_URL=$DATABASE_URL,REDIS_HOST=10.110.183.147,REDIS_PORT=6379,CLERK_SECRET_KEY=$CLERK_SECRET_KEY,NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=$NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY,EXTENSION_BACKEND_URL=https://extension-backend-service-644185288504.us-central1.run.app"
```

---

## Debugging Checklist

1. **Check logs for errors:**
   ```bash
   gcloud run services logs read backend-api \
     --project parallel-universe-prod \
     --region us-central1 \
     --limit 100
   ```

2. **Check current environment variables:**
   ```bash
   gcloud run services describe backend-api \
     --project parallel-universe-prod \
     --region us-central1 \
     --format="yaml(spec.template.spec.containers[0].env)"
   ```

3. **Check current revision:**
   ```bash
   gcloud run services describe backend-api \
     --project parallel-universe-prod \
     --region us-central1 \
     --format="value(status.latestReadyRevisionName)"
   ```

4. **List recent builds:**
   ```bash
   gcloud builds list \
     --project parallel-universe-prod \
     --limit 5
   ```

---

## Prevention

To prevent losing environment variables during deploys:

1. **Use `--update-env-vars` instead of `--set-env-vars`** when adding new variables:
   ```bash
   gcloud run deploy backend-api \
     --update-env-vars "NEW_VAR=value"
   ```

2. **Create a deploy script** (see `deploy-prod.sh`) that always includes all required variables.

3. **Always verify env vars after deploy:**
   ```bash
   gcloud run services describe backend-api \
     --project parallel-universe-prod \
     --region us-central1 \
     --format="yaml(spec.template.spec.containers[0].env)"
   ```
