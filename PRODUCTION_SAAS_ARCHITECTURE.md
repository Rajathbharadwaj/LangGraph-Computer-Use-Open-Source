# 🚀 Production SaaS Architecture Guide

## 📋 **Overview: How Your X Automation SaaS Works in Production**

This guide shows you exactly how to deploy your X automation SaaS to production and handle real customers.

---

## 🏗️ **Architecture Overview**

```
┌─────────────────────────────────────────────────────────────────┐
│                         CUSTOMER                                 │
│                    (your-saas.com)                              │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│                    FRONTEND (Next.js/React)                      │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  - Dashboard                                               │ │
│  │  - "Connect X Account" button                              │ │
│  │  - Automation controls (like, follow, comment)             │ │
│  │  - Analytics & reports                                     │ │
│  │  - VNC viewer (for initial login)                          │ │
│  └────────────────────────────────────────────────────────────┘ │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTPS
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│                   API GATEWAY / LOAD BALANCER                    │
│                        (nginx/traefik)                           │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│                    BACKEND API (FastAPI)                         │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  Authentication & Authorization                            │ │
│  │  User Management                                           │ │
│  │  Subscription/Billing (Stripe)                             │ │
│  │  Rate Limiting                                             │ │
│  │  Job Queue Management                                      │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────┬──────────────────────┬────────────────────┬───────────────┘
      │                      │                    │
      ↓                      ↓                    ↓
┌─────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  PostgreSQL │    │  Redis/RabbitMQ  │    │  Object Storage │
│  Database   │    │  Job Queue       │    │  (S3/MinIO)     │
│             │    │                  │    │  - Screenshots  │
│  - Users    │    │  - Automation    │    │  - Logs         │
│  - Sessions │    │    jobs          │    │                 │
│  - Cookies  │    │  - Scheduled     │    │                 │
│  - Jobs     │    │    tasks         │    │                 │
└─────────────┘    └──────────────────┘    └─────────────────┘
                             │
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│              WORKER POOL (Celery/Background Workers)             │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  Worker 1  │  Worker 2  │  Worker 3  │  ... Worker N      │ │
│  │  Processes automation jobs from queue                      │ │
│  └────────────────────────────────────────────────────────────┘ │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP API calls
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│           BROWSER POOL (Multiple Docker Containers)              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ cua-stealth-1│  │ cua-stealth-2│  │ cua-stealth-3│  ...     │
│  │ Port: 8005   │  │ Port: 8006   │  │ Port: 8007   │          │
│  │ VNC: 5900    │  │ VNC: 5901    │  │ VNC: 5902    │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                                                                  │
│  Each container runs:                                           │
│  - Stealth browser (Playwright + Chromium)                      │
│  - Session management API                                       │
│  - VNC server (for customer login)                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🔄 **Customer Journey: Step-by-Step**

### **Phase 1: Customer Signs Up**

```
1. Customer visits your-saas.com
2. Signs up (email + password)
3. Chooses subscription plan (Stripe checkout)
4. Redirected to dashboard
```

**Backend Code:**
```python
# backend/api/auth.py
from fastapi import FastAPI, HTTPException
from passlib.hash import bcrypt
import stripe

app = FastAPI()

@app.post("/signup")
async def signup(email: str, password: str, plan: str):
    # Create user
    hashed_password = bcrypt.hash(password)
    user = await db.create_user(
        email=email,
        password_hash=hashed_password,
        plan=plan
    )
    
    # Create Stripe customer
    stripe_customer = stripe.Customer.create(
        email=email,
        metadata={'user_id': user.id}
    )
    
    # Create subscription
    subscription = stripe.Subscription.create(
        customer=stripe_customer.id,
        items=[{'price': PLAN_PRICES[plan]}]
    )
    
    await db.update_user(user.id, stripe_customer_id=stripe_customer.id)
    
    return {
        "user_id": user.id,
        "token": create_jwt_token(user.id)
    }
```

---

### **Phase 2: Customer Connects X Account**

```
1. Customer clicks "Connect X Account" in dashboard
2. Backend allocates a browser container
3. Frontend shows VNC viewer (embedded or popup)
4. Customer logs in to X (you never see password!)
5. Backend captures cookies
6. Cookies encrypted and stored in database
7. Browser container released back to pool
```

**Backend Code:**
```python
# backend/api/onboarding.py
from fastapi import FastAPI, WebSocket
import aiohttp
from cryptography.fernet import Fernet
import asyncio

app = FastAPI()

# Browser pool manager
class BrowserPool:
    def __init__(self):
        self.available_browsers = []
        self.in_use_browsers = {}
        
    async def get_browser(self):
        """Get available browser from pool"""
        if self.available_browsers:
            return self.available_browsers.pop()
        else:
            # Scale up - start new container
            return await self.start_new_browser()
    
    async def release_browser(self, browser_id):
        """Return browser to pool"""
        # Clear cookies/cache
        await self.reset_browser(browser_id)
        self.available_browsers.append(browser_id)
    
    async def start_new_browser(self):
        """Start new Docker container"""
        import docker
        client = docker.from_env()
        
        # Find next available port
        port = 8005 + len(self.in_use_browsers)
        vnc_port = 5900 + len(self.in_use_browsers)
        
        container = client.containers.run(
            'cua-stealth',
            detach=True,
            ports={
                '8005/tcp': port,
                '5900/tcp': vnc_port
            },
            shm_size='2g'
        )
        
        browser = {
            'id': container.id,
            'api_url': f'http://localhost:{port}',
            'vnc_port': vnc_port,
            'container': container
        }
        
        # Wait for browser to be ready
        await asyncio.sleep(10)
        
        return browser

browser_pool = BrowserPool()

@app.post("/onboard/connect-x")
async def connect_x_account(user_id: str):
    """Step 1: Allocate browser and navigate to X login"""
    
    # Get browser from pool
    browser = await browser_pool.get_browser()
    
    # Store browser assignment
    await redis.set(f"browser:{user_id}", json.dumps(browser), ex=600)  # 10 min timeout
    
    # Navigate to X login
    async with aiohttp.ClientSession() as session:
        await session.post(
            f"{browser['api_url']}/navigate",
            json={'url': 'https://x.com/login'}
        )
    
    # Return VNC connection info
    return {
        "vnc_url": f"wss://your-saas.com/vnc/{user_id}",  # WebSocket proxy to VNC
        "session_id": user_id,
        "message": "Please log in to your X account"
    }


@app.websocket("/vnc/{user_id}")
async def vnc_proxy(websocket: WebSocket, user_id: str):
    """WebSocket proxy to VNC server"""
    await websocket.accept()
    
    # Get browser info
    browser_info = json.loads(await redis.get(f"browser:{user_id}"))
    vnc_port = browser_info['vnc_port']
    
    # Proxy VNC connection
    # Use noVNC or similar WebSocket-to-VNC proxy
    # ... implementation details ...


@app.post("/onboard/confirm-login")
async def confirm_login(user_id: str):
    """Step 2: Capture cookies after customer logs in"""
    
    # Get browser info
    browser_info = json.loads(await redis.get(f"browser:{user_id}"))
    
    # Capture cookies
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{browser_info['api_url']}/session/save"
        ) as resp:
            result = await resp.json()
    
    if not result['success']:
        return {"error": "Login not detected. Please try again."}
    
    # Encrypt cookies
    ENCRYPTION_KEY = os.getenv('COOKIE_ENCRYPTION_KEY').encode()
    fernet = Fernet(ENCRYPTION_KEY)
    encrypted_cookies = fernet.encrypt(
        json.dumps(result['cookies']).encode()
    ).decode()
    
    # Save to database
    await db.save_user_session(
        user_id=user_id,
        encrypted_cookies=encrypted_cookies,
        username=result['username'],
        created_at=datetime.now(),
        expires_at=datetime.now() + timedelta(days=30)
    )
    
    # Release browser back to pool
    await browser_pool.release_browser(browser_info['id'])
    await redis.delete(f"browser:{user_id}")
    
    return {
        "success": True,
        "username": result['username'],
        "message": "X account connected successfully!"
    }
```

---

### **Phase 3: Customer Requests Automation**

```
1. Customer clicks "Like this post" or "Follow these users"
2. Request goes to API
3. API validates subscription & rate limits
4. Job added to queue
5. Worker picks up job
6. Worker gets browser from pool
7. Worker loads customer's cookies
8. Worker performs automation
9. Worker releases browser
10. Customer sees result in dashboard
```

**Backend Code:**
```python
# backend/api/automation.py
from celery import Celery
import aiohttp

celery_app = Celery('automation', broker='redis://localhost:6379')

@app.post("/automate/like-post")
async def like_post(user_id: str, post_url: str, token: str):
    """Customer requests to like a post"""
    
    # Verify JWT token
    user = await verify_token(token)
    if user.id != user_id:
        raise HTTPException(403, "Unauthorized")
    
    # Check subscription
    subscription = await db.get_subscription(user_id)
    if subscription.status != 'active':
        raise HTTPException(402, "Subscription required")
    
    # Check rate limits
    await check_rate_limit(user_id, 'like')
    
    # Add job to queue
    job = await celery_app.send_task(
        'automation.like_post',
        args=[user_id, post_url]
    )
    
    # Save job to database
    await db.create_job(
        user_id=user_id,
        job_id=job.id,
        type='like_post',
        status='queued',
        params={'post_url': post_url}
    )
    
    return {
        "job_id": job.id,
        "status": "queued",
        "message": "Your like request has been queued"
    }


# Worker (runs in separate process)
@celery_app.task(name='automation.like_post')
async def like_post_worker(user_id: str, post_url: str):
    """Background worker that performs the automation"""
    
    try:
        # Update job status
        await db.update_job_status(job_id, 'processing')
        
        # Get user session
        session = await db.get_user_session(user_id)
        
        # Decrypt cookies
        ENCRYPTION_KEY = os.getenv('COOKIE_ENCRYPTION_KEY').encode()
        fernet = Fernet(ENCRYPTION_KEY)
        cookies = json.loads(
            fernet.decrypt(session.encrypted_cookies.encode())
        )
        
        # Get browser from pool
        browser = await browser_pool.get_browser()
        
        try:
            # Load cookies
            async with aiohttp.ClientSession() as http_session:
                async with http_session.post(
                    f"{browser['api_url']}/session/load",
                    json={'cookies': cookies}
                ) as resp:
                    load_result = await resp.json()
            
            if not load_result['logged_in']:
                # Session expired
                await db.mark_session_expired(user_id)
                await notify_user_reauth_needed(user_id)
                raise Exception("Session expired")
            
            # Navigate to post
            async with aiohttp.ClientSession() as http_session:
                await http_session.post(
                    f"{browser['api_url']}/navigate",
                    json={'url': post_url}
                )
            
            # Wait for page load
            await asyncio.sleep(2)
            
            # Get DOM elements
            async with aiohttp.ClientSession() as http_session:
                async with http_session.get(
                    f"{browser['api_url']}/dom/elements"
                ) as resp:
                    dom_data = await resp.json()
            
            # Find like button
            like_button = None
            for el in dom_data['elements']:
                if el.get('testId') == 'like':
                    like_button = el
                    break
            
            if not like_button:
                raise Exception("Like button not found")
            
            # Click like button
            async with aiohttp.ClientSession() as http_session:
                await http_session.post(
                    f"{browser['api_url']}/click",
                    json={'x': like_button['x'], 'y': like_button['y']}
                )
            
            # Wait for action
            await asyncio.sleep(1)
            
            # Take screenshot for proof
            async with aiohttp.ClientSession() as http_session:
                async with http_session.get(
                    f"{browser['api_url']}/screenshot"
                ) as resp:
                    screenshot_data = await resp.json()
            
            # Upload screenshot to S3
            screenshot_url = await upload_to_s3(
                screenshot_data['screenshot'],
                f"jobs/{job_id}/screenshot.png"
            )
            
            # Update job as completed
            await db.update_job_status(
                job_id,
                'completed',
                result={'screenshot_url': screenshot_url}
            )
            
            # Increment rate limit counter
            await redis.incr(f"rate_limit:{user_id}:like:{datetime.now().hour}")
            
        finally:
            # Always release browser
            await browser_pool.release_browser(browser['id'])
        
    except Exception as e:
        # Update job as failed
        await db.update_job_status(job_id, 'failed', error=str(e))
        
        # Log error
        logger.error(f"Job {job_id} failed: {e}")
```

---

## 🗄️ **Database Schema**

```sql
-- Users table
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    stripe_customer_id VARCHAR(255),
    plan VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- X Sessions table (encrypted cookies)
CREATE TABLE x_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    encrypted_cookies TEXT NOT NULL,
    username VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP,
    last_used TIMESTAMP,
    is_valid BOOLEAN DEFAULT TRUE,
    UNIQUE(user_id)
);

-- Jobs table
CREATE TABLE jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    celery_job_id VARCHAR(255),
    type VARCHAR(50) NOT NULL,  -- 'like_post', 'follow_user', etc.
    status VARCHAR(50) NOT NULL,  -- 'queued', 'processing', 'completed', 'failed'
    params JSONB,
    result JSONB,
    error TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

-- Subscriptions table
CREATE TABLE subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    stripe_subscription_id VARCHAR(255),
    plan VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL,  -- 'active', 'canceled', 'past_due'
    current_period_start TIMESTAMP,
    current_period_end TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id)
);

-- Rate limits table (optional, can use Redis instead)
CREATE TABLE rate_limits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    action VARCHAR(50) NOT NULL,
    count INTEGER DEFAULT 0,
    window_start TIMESTAMP NOT NULL,
    window_end TIMESTAMP NOT NULL,
    UNIQUE(user_id, action, window_start)
);

-- Indexes
CREATE INDEX idx_jobs_user_id ON jobs(user_id);
CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_created_at ON jobs(created_at DESC);
CREATE INDEX idx_x_sessions_user_id ON x_sessions(user_id);
CREATE INDEX idx_x_sessions_expires_at ON x_sessions(expires_at);
```

---

## 🐳 **Docker Compose for Production**

```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  # Nginx reverse proxy
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/nginx/ssl
    depends_on:
      - backend
    restart: unless-stopped

  # Backend API
  backend:
    build: ./backend
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - REDIS_URL=${REDIS_URL}
      - COOKIE_ENCRYPTION_KEY=${COOKIE_ENCRYPTION_KEY}
      - STRIPE_SECRET_KEY=${STRIPE_SECRET_KEY}
      - JWT_SECRET=${JWT_SECRET}
    depends_on:
      - postgres
      - redis
    restart: unless-stopped
    deploy:
      replicas: 3  # Scale horizontally

  # Celery workers
  worker:
    build: ./backend
    command: celery -A automation worker --loglevel=info --concurrency=4
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - REDIS_URL=${REDIS_URL}
      - COOKIE_ENCRYPTION_KEY=${COOKIE_ENCRYPTION_KEY}
    depends_on:
      - postgres
      - redis
    restart: unless-stopped
    deploy:
      replicas: 5  # 5 workers

  # Browser pool (multiple containers)
  browser-1:
    image: cua-stealth
    ports:
      - "8005:8005"
      - "5900:5900"
    shm_size: '2gb'
    restart: unless-stopped

  browser-2:
    image: cua-stealth
    ports:
      - "8006:8005"
      - "5901:5900"
    shm_size: '2gb'
    restart: unless-stopped

  browser-3:
    image: cua-stealth
    ports:
      - "8007:8005"
      - "5902:5900"
    shm_size: '2gb'
    restart: unless-stopped

  # Add more browsers as needed...

  # PostgreSQL
  postgres:
    image: postgres:15
    environment:
      - POSTGRES_DB=saas_db
      - POSTGRES_USER=saas_user
      - POSTGRES_PASSWORD=${DB_PASSWORD}
    volumes:
      - postgres-data:/var/lib/postgresql/data
    restart: unless-stopped

  # Redis (for queue and cache)
  redis:
    image: redis:7-alpine
    volumes:
      - redis-data:/data
    restart: unless-stopped

  # MinIO (S3-compatible storage for screenshots)
  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    environment:
      - MINIO_ROOT_USER=${MINIO_ACCESS_KEY}
      - MINIO_ROOT_PASSWORD=${MINIO_SECRET_KEY}
    volumes:
      - minio-data:/data
    ports:
      - "9000:9000"
      - "9001:9001"
    restart: unless-stopped

volumes:
  postgres-data:
  redis-data:
  minio-data:
```

---

## 💰 **Pricing & Subscription Plans**

```python
# backend/config/plans.py

PLANS = {
    'starter': {
        'price_monthly': 29,  # $29/month
        'stripe_price_id': 'price_starter_monthly',
        'limits': {
            'likes_per_day': 50,
            'follows_per_day': 20,
            'comments_per_day': 10,
            'x_accounts': 1
        }
    },
    'pro': {
        'price_monthly': 99,  # $99/month
        'stripe_price_id': 'price_pro_monthly',
        'limits': {
            'likes_per_day': 200,
            'follows_per_day': 100,
            'comments_per_day': 50,
            'x_accounts': 3
        }
    },
    'enterprise': {
        'price_monthly': 299,  # $299/month
        'stripe_price_id': 'price_enterprise_monthly',
        'limits': {
            'likes_per_day': 1000,
            'follows_per_day': 500,
            'comments_per_day': 200,
            'x_accounts': 10
        }
    }
}
```

---

## 📊 **Scaling Strategy**

### **Phase 1: MVP (0-100 customers)**
```
- 1 backend server
- 1 worker server
- 3 browser containers
- 1 database
- 1 Redis instance

Cost: ~$200-300/month (DigitalOcean/Hetzner)
```

### **Phase 2: Growth (100-1000 customers)**
```
- 3 backend servers (load balanced)
- 5 worker servers
- 20 browser containers (auto-scaling)
- 1 database (with read replicas)
- 1 Redis cluster

Cost: ~$1000-2000/month
```

### **Phase 3: Scale (1000+ customers)**
```
- Auto-scaling backend (Kubernetes)
- Auto-scaling workers
- Browser pool with auto-scaling (50-200 containers)
- Database cluster (PostgreSQL with Patroni)
- Redis cluster
- CDN for static assets
- Monitoring & logging (Datadog/New Relic)

Cost: ~$5000-10000/month
```

---

## 🔐 **Security Checklist**

```
✅ HTTPS everywhere (Let's Encrypt)
✅ JWT authentication with refresh tokens
✅ Rate limiting (per user, per IP)
✅ Cookie encryption (Fernet)
✅ Database encryption at rest
✅ Environment variables for secrets
✅ CORS configuration
✅ SQL injection prevention (parameterized queries)
✅ XSS prevention (sanitize inputs)
✅ CSRF protection
✅ Regular security audits
✅ Dependency updates
✅ Backup strategy (daily database backups)
✅ Monitoring & alerting
✅ DDoS protection (Cloudflare)
```

---

## 📈 **Monitoring & Analytics**

```python
# backend/monitoring.py
from prometheus_client import Counter, Histogram, Gauge
import sentry_sdk

# Initialize Sentry for error tracking
sentry_sdk.init(dsn=os.getenv('SENTRY_DSN'))

# Prometheus metrics
job_counter = Counter('automation_jobs_total', 'Total automation jobs', ['type', 'status'])
job_duration = Histogram('automation_job_duration_seconds', 'Job duration')
active_sessions = Gauge('active_x_sessions', 'Active X sessions')
browser_pool_size = Gauge('browser_pool_size', 'Available browsers')

# Track metrics
@app.middleware("http")
async def track_metrics(request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    
    # Log slow requests
    if duration > 5:
        logger.warning(f"Slow request: {request.url} took {duration}s")
    
    return response
```

---

## 🚀 **Deployment Checklist**

### **Pre-Launch:**
```
✅ Set up domain (your-saas.com)
✅ Configure DNS
✅ Set up SSL certificates
✅ Create Stripe account & products
✅ Set up error tracking (Sentry)
✅ Set up monitoring (Datadog/Prometheus)
✅ Set up email service (SendGrid/Postmark)
✅ Write privacy policy
✅ Write terms of service
✅ Test payment flow
✅ Test automation flow end-to-end
✅ Load testing
✅ Security audit
```

### **Launch Day:**
```
✅ Deploy to production
✅ Test all endpoints
✅ Monitor error rates
✅ Monitor performance
✅ Have rollback plan ready
```

### **Post-Launch:**
```
✅ Monitor user signups
✅ Track conversion rates
✅ Monitor job success rates
✅ Track session expiry rates
✅ Collect user feedback
✅ Iterate based on data
```

---

## 💡 **Cost Breakdown (Monthly)**

### **Starter Phase (0-100 customers)**
```
Infrastructure:
- VPS (8GB RAM, 4 CPU)         $40
- Database (managed)            $50
- Redis (managed)               $20
- Object storage (100GB)        $5
- Domain & SSL                  $10
- Monitoring                    $20
Total Infrastructure:           $145/month

Revenue (50 customers @ $29):   $1,450/month
Profit:                         $1,305/month
```

### **Growth Phase (100-1000 customers)**
```
Infrastructure:
- Backend servers (3x)          $120
- Worker servers (5x)           $200
- Browser containers (20x)      $400
- Database cluster              $200
- Redis cluster                 $100
- Object storage (1TB)          $50
- CDN                           $50
- Monitoring & logging          $100
Total Infrastructure:           $1,220/month

Revenue (500 customers @ $29):  $14,500/month
Profit:                         $13,280/month
```

---

## 📞 **Customer Support Flow**

```python
# backend/api/support.py

@app.post("/support/session-expired")
async def handle_session_expired(user_id: str):
    """Customer reports session expired"""
    
    # Send email with reconnect link
    await send_email(
        to=user.email,
        subject="Reconnect your X account",
        template="session_expired",
        data={
            'reconnect_url': f"https://your-saas.com/connect-x"
        }
    )
    
    # Log support ticket
    await db.create_support_ticket(
        user_id=user_id,
        type='session_expired',
        status='auto_resolved'
    )


@app.get("/support/job-status/{job_id}")
async def get_job_status(job_id: str, user_id: str):
    """Customer checks job status"""
    
    job = await db.get_job(job_id)
    
    if job.user_id != user_id:
        raise HTTPException(403, "Unauthorized")
    
    return {
        "job_id": job.id,
        "type": job.type,
        "status": job.status,
        "created_at": job.created_at,
        "completed_at": job.completed_at,
        "result": job.result,
        "error": job.error
    }
```

---

## 🎯 **Next Steps to Go Live**

1. **Week 1-2: Infrastructure Setup**
   - Set up servers (DigitalOcean/AWS/Hetzner)
   - Configure Docker Compose
   - Set up database
   - Configure SSL
   - Set up monitoring

2. **Week 3-4: Backend Development**
   - Implement authentication
   - Implement subscription/billing
   - Implement job queue
   - Implement automation endpoints
   - Write tests

3. **Week 5-6: Frontend Development**
   - Build dashboard
   - Build onboarding flow
   - Build VNC viewer integration
   - Build job status tracking
   - Build analytics

4. **Week 7: Testing**
   - End-to-end testing
   - Load testing
   - Security testing
   - Beta user testing

5. **Week 8: Launch**
   - Deploy to production
   - Monitor closely
   - Collect feedback
   - Iterate

---

## 📚 **Additional Resources**

- **Stripe Integration:** https://stripe.com/docs/billing/subscriptions
- **Celery Documentation:** https://docs.celeryq.dev/
- **Docker Compose:** https://docs.docker.com/compose/
- **FastAPI Best Practices:** https://fastapi.tiangolo.com/
- **PostgreSQL Scaling:** https://www.postgresql.org/docs/

---

**🎉 You now have a complete blueprint to launch your X automation SaaS!**

