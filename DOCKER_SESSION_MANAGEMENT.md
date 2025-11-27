# 🐳 Docker Session Management - Complete Guide

## 📋 **What Changed?**

I've added **cookie-based session management** to your existing Docker stealth browser!

### **✅ What's Now in Docker:**

1. **Stealth Browser** (already had)
   - Playwright with Chromium
   - Anti-bot detection
   - VNC access

2. **Session Management** (NEW!)
   - `/session/save` - Capture cookies after login
   - `/session/load` - Restore session from cookies
   - `/session/check` - Verify login status

3. **X Session Manager** (NEW!)
   - `x_session_manager.py` included in Docker
   - Encryption support (cryptography package)
   - Username extraction

---

## 🚀 **Quick Start**

### **Step 1: Rebuild Docker with New Features**

```bash
cd /home/rajathdb/cua
./rebuild_stealth_with_auth.sh
```

This will:
- Stop old container
- Rebuild with session management
- Start new container
- Test new endpoints

### **Step 2: Test the New Endpoints**

```bash
# Quick test
python3 test_session_management.py quick

# Full demo (interactive)
python3 test_session_management.py
```

---

## 📚 **How It Works**

### **Architecture:**

```
┌─────────────────────────────────────────────────────────┐
│                    Your SaaS Backend                     │
│  ┌────────────────────────────────────────────────────┐ │
│  │  FastAPI App                                       │ │
│  │  - User onboarding endpoints                       │ │
│  │  - Automation endpoints                            │ │
│  │  - Database (encrypted cookies)                    │ │
│  └────────────────────────────────────────────────────┘ │
└───────────────────────┬─────────────────────────────────┘
                        │ HTTP API calls
                        ↓
┌─────────────────────────────────────────────────────────┐
│              Docker Container (cua-stealth)              │
│  ┌────────────────────────────────────────────────────┐ │
│  │  Stealth CUA Server (port 8005)                    │ │
│  │  ┌──────────────────────────────────────────────┐  │ │
│  │  │  NEW: Session Management                     │  │ │
│  │  │  - POST /session/save   (capture cookies)    │  │ │
│  │  │  - POST /session/load   (restore session)    │  │ │
│  │  │  - POST /session/check  (verify login)       │  │ │
│  │  └──────────────────────────────────────────────┘  │ │
│  │  ┌──────────────────────────────────────────────┐  │ │
│  │  │  Existing: Browser Automation                │  │ │
│  │  │  - POST /navigate                            │  │ │
│  │  │  - POST /click                               │  │ │
│  │  │  - GET /screenshot                           │  │ │
│  │  │  - GET /dom/elements                         │  │ │
│  │  └──────────────────────────────────────────────┘  │ │
│  └────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────┐ │
│  │  Playwright Stealth Browser                        │ │
│  │  - Chromium with stealth patches                   │ │
│  │  - Session cookies stored in context               │ │
│  └────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────┐ │
│  │  VNC Server (port 5900)                            │ │
│  │  - View/control browser remotely                   │ │
│  └────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

---

## 🔐 **User Onboarding Flow**

### **Scenario: New customer connects their X account**

```python
# 1. Customer clicks "Connect X Account" in your SaaS UI
@app.post("/onboard/connect-x")
async def connect_x_account(user_id: str):
    # Open X login page in Docker browser
    async with aiohttp.ClientSession() as session:
        await session.post(
            'http://localhost:8005/navigate',
            json={'url': 'https://x.com/login'}
        )
    
    # Return VNC URL for customer to log in
    return {
        "vnc_url": "https://your-app.com/vnc-viewer",
        "message": "Please log in to your X account"
    }


# 2. Customer logs in via VNC viewer (you don't see password!)


# 3. After login, capture cookies
@app.post("/onboard/confirm-login")
async def confirm_login(user_id: str):
    # Capture cookies from Docker browser
    async with aiohttp.ClientSession() as session:
        async with session.post('http://localhost:8005/session/save') as resp:
            result = await resp.json()
    
    if not result['success']:
        return {"error": "Login not detected"}
    
    # Encrypt cookies
    from cryptography.fernet import Fernet
    ENCRYPTION_KEY = os.getenv('COOKIE_ENCRYPTION_KEY').encode()
    fernet = Fernet(ENCRYPTION_KEY)
    
    encrypted = fernet.encrypt(
        json.dumps(result['cookies']).encode()
    ).decode()
    
    # Save to database
    await db.save_user_session(
        user_id=user_id,
        encrypted_cookies=encrypted,
        username=result['username'],
        expires_at=datetime.now() + timedelta(days=30)
    )
    
    return {
        "success": True,
        "username": result['username'],
        "message": "X account connected!"
    }
```

---

## 🤖 **Automation Flow**

### **Scenario: Customer wants to like a post**

```python
@app.post("/automate/like-post")
async def like_post(user_id: str, post_url: str):
    # 1. Get encrypted cookies from database
    session_data = await db.get_user_session(user_id)
    
    # 2. Decrypt cookies
    from cryptography.fernet import Fernet
    ENCRYPTION_KEY = os.getenv('COOKIE_ENCRYPTION_KEY').encode()
    fernet = Fernet(ENCRYPTION_KEY)
    
    cookies = json.loads(
        fernet.decrypt(session_data.encrypted_cookies.encode())
    )
    
    # 3. Load cookies into Docker browser
    async with aiohttp.ClientSession() as session:
        async with session.post(
            'http://localhost:8005/session/load',
            json={'cookies': cookies}
        ) as resp:
            load_result = await resp.json()
    
    if not load_result['logged_in']:
        # Session expired - notify user to reconnect
        await notify_user_reauth_needed(user_id)
        return {"error": "Session expired - please reconnect"}
    
    # 4. Navigate to post
    async with aiohttp.ClientSession() as session:
        await session.post(
            'http://localhost:8005/navigate',
            json={'url': post_url}
        )
    
    # 5. Click like button (using your existing tools)
    # Use async_playwright_tools.py like_post() function
    from async_playwright_tools import like_post as like_tool
    result = await like_tool.arun({"search_text": "post content"})
    
    return {"success": True, "message": "Post liked!"}
```

---

## 🧪 **Testing the New Features**

### **Test 1: Check Docker Status**

```bash
curl http://localhost:8005/status | python3 -m json.tool
```

Expected output:
```json
{
  "success": true,
  "mode": "stealth",
  "stealth_browser_ready": true,
  "current_url": "https://x.com/home",
  "message": "Stealth CUA Server running"
}
```

### **Test 2: Check Root Endpoint (New Features)**

```bash
curl http://localhost:8005/ | python3 -m json.tool
```

Expected output:
```json
{
  "message": "🥷 Stealth CUA Server",
  "mode": "stealth",
  "stealth_ready": true,
  "features": [
    "Browser automation",
    "Session management (cookies)",
    "X authentication support"
  ]
}
```

### **Test 3: Manual Login + Capture**

```bash
# 1. Open VNC viewer
open vnc://localhost:5900

# 2. Navigate to X login
curl -X POST http://localhost:8005/navigate \
  -H "Content-Type: application/json" \
  -d '{"url": "https://x.com/login"}'

# 3. Log in manually in VNC viewer

# 4. Capture cookies
curl -X POST http://localhost:8005/session/save | python3 -m json.tool
```

Expected output:
```json
{
  "success": true,
  "cookies": [...],
  "cookies_count": 15,
  "username": "your_username",
  "message": "Captured 15 cookies"
}
```

### **Test 4: Load Session**

```bash
# Save cookies to file first
curl -X POST http://localhost:8005/session/save > cookies.json

# Load them back
curl -X POST http://localhost:8005/session/load \
  -H "Content-Type: application/json" \
  -d @cookies.json | python3 -m json.tool
```

Expected output:
```json
{
  "success": true,
  "logged_in": true,
  "username": "your_username",
  "message": "Session loaded"
}
```

---

## 📊 **API Reference**

### **Session Management Endpoints**

#### **POST /session/save**
Capture cookies from current browser session.

**Request:** None (uses current browser state)

**Response:**
```json
{
  "success": true,
  "cookies": [...],
  "cookies_count": 15,
  "username": "rajath_db",
  "message": "Captured 15 cookies"
}
```

#### **POST /session/load**
Load cookies into browser to restore session.

**Request:**
```json
{
  "cookies": [...]
}
```

**Response:**
```json
{
  "success": true,
  "logged_in": true,
  "username": "rajath_db",
  "message": "Session loaded"
}
```

#### **POST /session/check**
Check if currently logged in to X.

**Request:** None

**Response:**
```json
{
  "success": true,
  "logged_in": true,
  "username": "rajath_db"
}
```

---

## 🔐 **Security Best Practices**

### **1. Always Encrypt Cookies**

```python
from cryptography.fernet import Fernet
import os

# Generate key once, store in environment
ENCRYPTION_KEY = os.getenv('COOKIE_ENCRYPTION_KEY')
if not ENCRYPTION_KEY:
    # First time setup
    key = Fernet.generate_key()
    print(f"Save this key: {key.decode()}")
    # Store in .env file or secrets manager
    ENCRYPTION_KEY = key.decode()

fernet = Fernet(ENCRYPTION_KEY.encode())

# Encrypt before storing
encrypted = fernet.encrypt(json.dumps(cookies).encode())
await db.save(encrypted.decode())

# Decrypt when using
decrypted = fernet.decrypt(encrypted.encode())
cookies = json.loads(decrypted.decode())
```

### **2. Validate Sessions Before Use**

```python
async def validate_and_load_session(user_id: str):
    """Always check session validity before automation"""
    
    # Get from database
    session = await db.get_user_session(user_id)
    
    # Check expiry
    if session.expires_at < datetime.now():
        await notify_user_reauth_needed(user_id)
        return None
    
    # Decrypt cookies
    cookies = decrypt_cookies(session.encrypted_cookies)
    
    # Load into browser
    result = await load_session_to_docker(cookies)
    
    if not result['logged_in']:
        # Session invalid - update database
        await db.mark_session_expired(user_id)
        await notify_user_reauth_needed(user_id)
        return None
    
    return result
```

### **3. Rate Limiting**

```python
from datetime import datetime, timedelta
import redis

redis_client = redis.Redis()

async def check_rate_limit(user_id: str, action: str):
    """Prevent abuse and bot detection"""
    
    key = f"rate_limit:{user_id}:{action}:{datetime.now().hour}"
    count = redis_client.incr(key)
    redis_client.expire(key, 3600)  # 1 hour
    
    limits = {
        'like': 50,      # 50 likes per hour
        'follow': 20,    # 20 follows per hour
        'tweet': 10,     # 10 tweets per hour
        'comment': 15    # 15 comments per hour
    }
    
    if count > limits.get(action, 10):
        raise RateLimitError(f"Rate limit exceeded for {action}")
```

---

## 🚀 **Production Deployment**

### **Docker Compose Setup**

```yaml
# docker-compose.yml
version: '3.8'

services:
  stealth-browser:
    image: cua-stealth
    build:
      context: .
      dockerfile: Dockerfile.stealth
    ports:
      - "5900:5900"  # VNC
      - "8005:8005"  # API
    shm_size: '2gb'
    restart: unless-stopped
    environment:
      - DISPLAY=:98
    volumes:
      - browser-data:/app/data

  your-saas-backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - COOKIE_ENCRYPTION_KEY=${COOKIE_ENCRYPTION_KEY}
      - DOCKER_BROWSER_URL=http://stealth-browser:8005
    depends_on:
      - stealth-browser
      - postgres

  postgres:
    image: postgres:15
    environment:
      - POSTGRES_DB=saas_db
      - POSTGRES_PASSWORD=${DB_PASSWORD}
    volumes:
      - postgres-data:/var/lib/postgresql/data

volumes:
  browser-data:
  postgres-data:
```

### **Environment Variables**

```bash
# .env
COOKIE_ENCRYPTION_KEY=your-fernet-key-here
DOCKER_BROWSER_URL=http://localhost:8005
DATABASE_URL=postgresql://user:pass@localhost/saas_db
```

---

## 📖 **Related Documentation**

- **`SAAS_AUTH_GUIDE.md`** - Complete authentication strategy guide
- **`x_auth_strategies.md`** - Detailed technical strategies
- **`x_session_manager.py`** - Standalone session manager (can run outside Docker)
- **`test_session_management.py`** - Test scripts and examples

---

## ❓ **FAQ**

### **Q: Do I need to rebuild Docker?**
A: Yes, run `./rebuild_stealth_with_auth.sh` to get the new features.

### **Q: Will this break my existing setup?**
A: No, all existing endpoints still work. New endpoints are additions.

### **Q: Can I use this without Docker?**
A: Yes, use `x_session_manager.py` standalone for local development.

### **Q: How long do sessions last?**
A: Typically 30 days, but check validity before each use.

### **Q: What if a session expires?**
A: Notify the user to reconnect. Make it easy with one-click flow.

### **Q: Is this secure?**
A: Yes, if you:
- Encrypt all cookies
- Use HTTPS
- Validate sessions
- Follow security best practices

---

## 🎯 **Next Steps**

1. **Rebuild Docker:**
   ```bash
   ./rebuild_stealth_with_auth.sh
   ```

2. **Test endpoints:**
   ```bash
   python3 test_session_management.py quick
   ```

3. **Integrate with your SaaS:**
   - Add database schema
   - Create onboarding endpoints
   - Build automation endpoints

4. **Deploy to production:**
   - Use Docker Compose
   - Add monitoring
   - Set up logging

---

**🎉 You now have a complete cookie-based authentication system in Docker!**

