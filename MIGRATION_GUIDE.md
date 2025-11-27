# Migration Guide: Development → Production

## 🎯 Overview

This guide helps you migrate from the development setup to the production-ready scalable system.

## 📊 What Changed

### Before (Development)
```
• Random user IDs (user_abc123...)
• In-memory storage
• Single shared browser
• No authentication
• No rate limiting
• Manual service management
```

### After (Production)
```
• Clerk authentication
• PostgreSQL database
• Redis caching
• Per-user Docker containers
• Rate limiting
• Encrypted cookie storage
• Docker Compose deployment
```

## 🔄 Migration Steps

### Step 1: Backup Current Data

```bash
# Backup any important data
# (Development setup doesn't persist data, but just in case)

# Export cookies if stored anywhere
# Export any test data you want to keep
```

### Step 2: Install Production Dependencies

```bash
cd /home/rajathdb/cua

# Install production Python packages
pip install -r requirements-prod.txt

# Install Clerk in frontend
cd /home/rajathdb/cua-frontend
npm install @clerk/nextjs
```

### Step 3: Setup Clerk Authentication

Follow the complete guide in `CLERK_SETUP.md`:

1. Create Clerk account at https://clerk.com
2. Create new application
3. Get API keys
4. Configure environment variables

**Backend (.env):**
```bash
CLERK_SECRET_KEY=sk_test_...
```

**Frontend (.env.local):**
```bash
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...
```

### Step 4: Generate Encryption Key

```bash
cd /home/rajathdb/cua

# Generate encryption key
python -c "from cryptography.fernet import Fernet; print('COOKIE_ENCRYPTION_KEY=' + Fernet.generate_key().decode())"

# Copy the output to .env
```

### Step 5: Configure Environment Variables

**Backend (.env):**
```bash
# Copy example
cp .env.example .env

# Edit with your values
nano .env
```

Required values:
- `DATABASE_URL` - PostgreSQL connection string
- `REDIS_URL` - Redis connection string
- `COOKIE_ENCRYPTION_KEY` - Generated key
- `CLERK_SECRET_KEY` - From Clerk dashboard
- `ANTHROPIC_API_KEY` - Your API key
- `OPENAI_API_KEY` - Your API key (optional)

**Frontend (.env.local):**
```bash
# Copy example
cp .env.local.example .env.local

# Edit with your values
nano .env.local
```

### Step 6: Start Production Services

```bash
cd /home/rajathdb/cua

# Start PostgreSQL and Redis
make prod-up

# Wait for services to be ready (about 10 seconds)
sleep 10

# Initialize database
make prod-db-init
```

### Step 7: Update Extension Backend

The extension backend now needs to store cookies in the database instead of memory.

**Old code (in-memory):**
```python
# cookies stored in global dict
user_cookies = {}
```

**New code (database):**
```python
from database import get_db, UserCookies, XAccount
from services import cookie_encryption

# Store cookies
encrypted = cookie_encryption.encrypt_cookies(cookies)
db = next(get_db())
user_cookies = UserCookies(
    x_account_id=x_account_id,
    encrypted_cookies=encrypted
)
db.add(user_cookies)
db.commit()
```

### Step 8: Update Main Backend

Add rate limiting to API endpoints:

```python
from services import rate_limiter

@app.post("/api/scrape-posts")
async def scrape_posts(user_id: str):
    # Check rate limit
    is_allowed, retry_after = await rate_limiter.check_rate_limit(
        user_id=user_id,
        endpoint="/api/scrape-posts"
    )
    
    if not is_allowed:
        return JSONResponse(
            status_code=429,
            content={
                "error": "Rate limit exceeded",
                "retry_after": retry_after
            }
        )
    
    # Continue with scraping...
```

### Step 9: Update Frontend Components

The frontend now uses Clerk for authentication:

**Old code:**
```typescript
// No authentication
const userId = "user_" + Math.random();
```

**New code:**
```typescript
import { useUser } from "@clerk/nextjs";

const { user } = useUser();
const userId = user?.id; // Consistent Clerk user ID
```

### Step 10: Test Migration

```bash
# Check all services are running
make prod-status

# Should show:
# ✅ Frontend Dashboard (3000)
# ✅ Main Backend (8000)
# ✅ Extension Backend (8001)
# ✅ OmniParser Server (8003)
# ✅ LangGraph Server (8124)
# ✅ Docker Browser API (8005)
# ✅ PostgreSQL
# ✅ Redis

# View logs
make prod-logs
```

### Step 11: Test User Flow

1. **Sign Up:**
   - Go to http://localhost:3000
   - Click "Sign Up"
   - Create account
   - Verify email

2. **Connect X Account:**
   - Install Chrome extension
   - Log into X.com
   - Click "Connect X Account" in dashboard
   - Verify connection

3. **Import Posts:**
   - Click "Import Posts"
   - Verify posts are stored in database
   - Check PostgreSQL:
     ```bash
     docker exec -it xgrowth-postgres psql -U postgres xgrowth
     SELECT * FROM user_posts;
     ```

4. **Run Agent:**
   - Start an automation task
   - Verify it runs in isolated container
   - Check logs

## 🔧 Troubleshooting Migration

### Issue: "Clerk keys not found"

**Solution:**
```bash
# Check .env.local exists
ls -la /home/rajathdb/cua-frontend/.env.local

# Verify keys are set
cat /home/rajathdb/cua-frontend/.env.local | grep CLERK

# Restart frontend
cd /home/rajathdb/cua-frontend
npm run dev
```

### Issue: "Database connection failed"

**Solution:**
```bash
# Check PostgreSQL is running
docker ps | grep postgres

# Check connection string
cat /home/rajathdb/cua/.env | grep DATABASE_URL

# Test connection
docker exec xgrowth-postgres pg_isready
```

### Issue: "Redis connection failed"

**Solution:**
```bash
# Check Redis is running
docker ps | grep redis

# Test connection
docker exec xgrowth-redis redis-cli ping
# Should return: PONG
```

### Issue: "Cookies not persisting"

**Solution:**
```bash
# Check encryption key is set
cat /home/rajathdb/cua/.env | grep COOKIE_ENCRYPTION_KEY

# Check database has cookies table
docker exec -it xgrowth-postgres psql -U postgres xgrowth -c "\d user_cookies"

# Check if cookies are being stored
docker exec -it xgrowth-postgres psql -U postgres xgrowth -c "SELECT COUNT(*) FROM user_cookies;"
```

### Issue: "Rate limiting not working"

**Solution:**
```bash
# Check Redis is running
docker exec xgrowth-redis redis-cli ping

# Check rate limit keys
docker exec xgrowth-redis redis-cli KEYS "ratelimit:*"

# Test rate limit
curl -X POST http://localhost:8000/api/test-endpoint \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test_user"}'
```

## 📊 Data Migration

If you have existing data to migrate:

### Export from Development

```bash
# Export cookies (if stored)
# Export user data
# Export posts
```

### Import to Production

```python
from database import get_db, User, XAccount, UserCookies, UserPost
from services import cookie_encryption

db = next(get_db())

# Create user
user = User(
    id="user_clerk_id",
    email="user@example.com",
    plan="free"
)
db.add(user)

# Create X account
x_account = XAccount(
    user_id=user.id,
    username="@username",
    display_name="Display Name"
)
db.add(x_account)

# Store encrypted cookies
encrypted = cookie_encryption.encrypt_cookies(cookies)
user_cookies = UserCookies(
    x_account_id=x_account.id,
    encrypted_cookies=encrypted
)
db.add(user_cookies)

# Import posts
for post in posts:
    user_post = UserPost(
        x_account_id=x_account.id,
        content=post['content'],
        likes=post['likes'],
        retweets=post['retweets']
    )
    db.add(user_post)

db.commit()
```

## ✅ Migration Checklist

- [ ] Backed up important data
- [ ] Installed production dependencies
- [ ] Created Clerk account
- [ ] Got Clerk API keys
- [ ] Generated encryption key
- [ ] Configured .env files
- [ ] Started production services
- [ ] Initialized database
- [ ] Updated extension backend
- [ ] Updated main backend
- [ ] Updated frontend components
- [ ] Tested sign up flow
- [ ] Tested X account connection
- [ ] Tested post import
- [ ] Tested agent execution
- [ ] Verified database persistence
- [ ] Verified rate limiting
- [ ] Checked all logs
- [ ] Documented any issues

## 🎯 Post-Migration

After successful migration:

1. **Monitor Services:**
   ```bash
   make prod-status  # Check status
   make prod-logs    # View logs
   ```

2. **Setup Monitoring:**
   - Sign up for Sentry
   - Add DSN to .env
   - Test error tracking

3. **Configure Backups:**
   ```bash
   # Daily database backup
   0 2 * * * docker exec xgrowth-postgres pg_dump -U postgres xgrowth > /backups/xgrowth_$(date +\%Y\%m\%d).sql
   ```

4. **Plan Scaling:**
   - Review ARCHITECTURE.md
   - Plan for growth
   - Consider managed services

## 📚 Additional Resources

- [PRODUCTION_DEPLOYMENT.md](./PRODUCTION_DEPLOYMENT.md) - Full deployment guide
- [CLERK_SETUP.md](./CLERK_SETUP.md) - Authentication setup
- [ARCHITECTURE.md](./ARCHITECTURE.md) - System architecture
- [SCALABILITY_SUMMARY.md](./SCALABILITY_SUMMARY.md) - Scalability overview

## 🎉 Success!

You've successfully migrated to the production-ready system!

Your application now has:
- ✅ Secure authentication
- ✅ Persistent storage
- ✅ Rate limiting
- ✅ Per-user isolation
- ✅ Scalable architecture
- ✅ Production deployment

Ready to scale to thousands of users! 🚀

