# 🍪 Cookie Transfer System - Complete Guide

## 🎯 What This Does

Transfers your X (Twitter) session from Chrome Extension → Docker Browser → LangGraph Agent

**Result:** Your LangGraph AI agent can automate your X account 24/7 without you being online!

---

## 🏗️ Architecture

```
User logs into X in Chrome
    ↓
Chrome Extension captures cookies
    ↓
WebSocket sends cookies to Backend (port 8001)
    ↓
Backend stores cookies (encrypted in production)
    ↓
Dashboard triggers cookie injection
    ↓
Backend calls Docker API (port 8005)
    ↓
Docker Playwright browser loads cookies
    ↓
LangGraph Agent now has your X session! 🎉
```

---

## 📋 Testing Instructions

### Step 1: Start All Services

```bash
# Terminal 1: Start Docker stealth browser (if not running)
cd /home/rajathdb/cua
docker run -p 5900:5900 -p 8005:8005 your-stealth-docker-image

# Terminal 2: Start Backend WebSocket Server
cd /home/rajathdb/cua
python3 backend_websocket_server.py

# Terminal 3: Start Next.js Dashboard
cd /home/rajathdb/cua-frontend
npm run dev
```

### Step 2: Install & Reload Extension

1. Go to `chrome://extensions/`
2. Enable "Developer mode"
3. Click "Load unpacked"
4. Select `/home/rajathdb/x-automation-extension/`
5. **IMPORTANT:** Click the reload button (🔄) on the extension

### Step 3: Login to X

1. Open new tab: `https://x.com`
2. Log in with your X account
3. Make sure you're on the home feed

### Step 4: Trigger Cookie Capture

1. Click the extension icon (𝕏) in Chrome toolbar
2. You should see:
   ```
   ✅ Connected to Dashboard
   User ID: user_xxxxx
   X Account: @YourUsername
   ```

3. Open browser console (F12) and check extension logs:
   ```
   ✅ User logged into X as @YourUsername
   🍪 Captured 15 X cookies for @YourUsername
   📤 Sent cookies to backend
   ```

### Step 5: Verify Backend Received Cookies

Check backend terminal, you should see:
```
🍪 Received 15 cookies from @YourUsername
✅ Cookies stored for user_xxxxx (@YourUsername)
```

### Step 6: Test Cookie Injection

```bash
# Check extension status
curl http://localhost:8001/api/extension/status | python3 -m json.tool

# Should show:
# {
#   "connected": true,
#   "users": [{
#     "userId": "user_xxxxx",
#     "username": "YourUsername",
#     "hasCookies": true
#   }]
# }

# Inject cookies into Docker
curl -X POST http://localhost:8001/api/inject-cookies-to-docker \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user_xxxxx"}'

# Should return:
# {
#   "success": true,
#   "message": "Session loaded for @YourUsername",
#   "logged_in": true,
#   "username": "YourUsername"
# }
```

### Step 7: Verify Docker Has Session

```bash
# Check Docker session
curl http://localhost:8005/session/check | python3 -m json.tool

# Should show:
# {
#   "success": true,
#   "logged_in": true,
#   "username": "YourUsername"
# }
```

### Step 8: Test with LangGraph Agent

```python
# test_agent_with_session.py
import asyncio
from langgraph_playwright_agent import run_playwright_agent_task

async def test():
    # The Docker browser now has your X session!
    result = await run_playwright_agent_task(
        "Go to x.com and tell me what you see. Am I logged in?"
    )
    print(result)

asyncio.run(test())
```

---

## 🎉 Success Indicators

✅ Extension shows "Connected to Dashboard"  
✅ Extension shows your X username  
✅ Backend logs show "Cookies stored"  
✅ Docker API returns "logged_in": true  
✅ LangGraph agent can see your X home feed  
✅ Agent can like posts, follow users, etc.

---

## 🐛 Troubleshooting

### Extension not capturing cookies?

1. Make sure you're logged into X
2. Reload the extension at `chrome://extensions/`
3. Check extension service worker console for errors

### Backend not receiving cookies?

1. Check WebSocket connection: Extension popup should show "Connected"
2. Check backend terminal for connection logs
3. Verify port 8001 is not blocked

### Docker not loading cookies?

1. Check Docker is running: `curl http://localhost:8005/status`
2. Check cookie format (Chrome → Playwright conversion)
3. Check Docker terminal logs for errors

### Agent not logged in after injection?

1. Cookies might be expired - re-login to X
2. X might have invalidated session - try again
3. Check Docker browser in VNC viewer (port 5900)

---

## 🔒 Production Considerations

### Security

- **Encrypt cookies** before storing in database
- Use environment variables for encryption keys
- Implement cookie expiration checks
- Add rate limiting to prevent abuse

### Scalability

- Store cookies in Redis/PostgreSQL
- One Docker container per user
- Use Kubernetes for orchestration
- Implement session refresh logic

### Monitoring

- Log cookie capture events
- Alert on failed injections
- Track session validity
- Monitor Docker container health

---

## 🚀 Next Steps

1. **Add encryption** to cookie storage
2. **Implement session refresh** when cookies expire
3. **Add user management** (multiple users, multiple accounts)
4. **Deploy to production** with proper infrastructure
5. **Add monitoring** and alerting

---

## 📚 Related Files

- `x-automation-extension/background.js` - Cookie capture logic
- `backend_websocket_server.py` - Cookie storage & injection
- `stealth_cua_server.py` - Docker browser session management
- `langgraph_playwright_agent.py` - AI agent that uses the session
- `async_playwright_tools.py` - Tools that interact with Docker

---

## 💡 How It Works (Technical)

### Cookie Capture (Extension)

```javascript
// Get all X cookies
const xCookies = await chrome.cookies.getAll({ domain: '.x.com' });

// Send to backend via WebSocket
ws.send(JSON.stringify({
  type: 'COOKIES_CAPTURED',
  userId: userId,
  username: username,
  cookies: xCookies
}));
```

### Cookie Storage (Backend)

```python
# Store cookies in memory (use DB in production)
user_cookies[user_id] = {
    "username": username,
    "cookies": cookies,
    "timestamp": timestamp
}
```

### Cookie Injection (Backend → Docker)

```python
# Convert Chrome cookies to Playwright format
playwright_cookies = convert_cookies(chrome_cookies)

# Inject into Docker browser
async with aiohttp.ClientSession() as session:
    await session.post(
        "http://localhost:8005/session/load",
        json={"cookies": playwright_cookies}
    )
```

### Session Activation (Docker)

```python
# Add cookies to Playwright context
await context.add_cookies(cookies)

# Navigate to X to activate session
await page.goto("https://x.com/home")

# Verify login
is_logged_in = await page.wait_for_selector('[data-testid="SideNav_AccountSwitcher_Button"]')
```

---

## 🎊 Congratulations!

You now have a complete cookie transfer system that allows your LangGraph AI agent to automate X accounts securely and scalably!

**The user logs in once, and the agent can work 24/7!** 🚀

