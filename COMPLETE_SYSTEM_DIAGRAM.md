# Complete System Architecture Diagram

## 🎯 How Everything Connects

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│                        USER'S BROWSER (Chrome)                          │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                                                                  │  │
│  │                    Chrome Extension                              │  │
│  │                  (X Automation Helper)                           │  │
│  │                                                                  │  │
│  │  ┌────────────────┐  ┌──────────────────────────────────────┐  │  │
│  │  │  background.js │  │  extension_agent_bridge.js           │  │  │
│  │  │  - Cookies     │  │  - Executes agent commands           │  │  │
│  │  │  - Login       │  │  - Human-like clicks                 │  │  │
│  │  └────────┬───────┘  │  - Data extraction                   │  │  │
│  │           │          │  - Rate limit detection              │  │  │
│  │           │          └──────────────┬───────────────────────┘  │  │
│  └───────────┼─────────────────────────┼──────────────────────────┘  │
│              │                         │                              │
└──────────────┼─────────────────────────┼──────────────────────────────┘
               │                         │
               │ WebSocket               │ WebSocket
               │ (Cookies)               │ (Commands)
               ▼                         ▼
┌──────────────────────────┐   ┌──────────────────────────────────────┐
│                          │   │                                      │
│   Main Backend Server    │   │   Extension Backend Server           │
│   (port 8000)            │   │   (port 8001)                        │
│                          │   │                                      │
│  - Cookie injection      │   │  - WebSocket server                  │
│  - Session management    │   │  - 9 extension tool endpoints        │
│  - Dashboard WebSocket   │   │  - Request/response routing          │
│                          │   │  - Bidirectional communication       │
└──────────┬───────────────┘   └──────────┬───────────────────────────┘
           │                              │
           │ HTTP/Cookies                 │ HTTP/Tool Calls
           ▼                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│                    Docker Container                                 │
│                (stealth-cua-with-extension)                         │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                                                              │  │
│  │              Chromium with Extension                         │  │
│  │              (Playwright controlled)                         │  │
│  │                                                              │  │
│  │  ┌────────────────────┐  ┌──────────────────────────────┐  │  │
│  │  │  Playwright        │  │  Chrome Extension            │  │  │
│  │  │  Stealth Browser   │  │  (Same as user's browser)    │  │  │
│  │  │  - Screenshots     │  │  - Executes commands         │  │  │
│  │  │  - Navigation      │  │  - Extracts data             │  │  │
│  │  │  - DOM access      │  │  - Human-like behavior       │  │  │
│  │  └────────────────────┘  └──────────────────────────────┘  │  │
│  │                                                              │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                                                              │  │
│  │              Stealth CUA Server (port 8005)                  │  │
│  │              - Playwright API endpoints                      │  │
│  │              - Screenshot, click, type, navigate             │  │
│  │              - DOM extraction                                │  │
│  │                                                              │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                                                              │  │
│  │              VNC Server (port 5900)                          │  │
│  │              - X11 display :98                               │  │
│  │              - XFCE desktop                                  │  │
│  │              - x11vnc streaming                              │  │
│  │                                                              │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
           ▲                              ▲
           │ HTTP                         │ VNC
           │                              │
┌──────────┴───────────────┐   ┌──────────┴──────────────────────────┐
│                          │   │                                     │
│   LangGraph Agent        │   │   Frontend Dashboard                │
│   (x_growth_deep_agent)  │   │   (Next.js - port 3000)             │
│                          │   │                                     │
│  ┌────────────────────┐  │   │  ┌──────────────────────────────┐  │
│  │ Playwright Tools   │  │   │  │  VNC Viewer Component        │  │
│  │ (27 tools)         │  │   │  │  - Embedded noVNC            │  │
│  │ - Screenshots      │  │   │  │  - Real-time view            │  │
│  │ - Navigation       │  │   │  │  - Mouse/keyboard control    │  │
│  │ - DOM extraction   │  │   │  └──────────────────────────────┘  │
│  └────────────────────┘  │   │                                     │
│                          │   │  ┌──────────────────────────────┐  │
│  ┌────────────────────┐  │   │  │  Import Posts Component      │  │
│  │ Extension Tools    │  │   │  │  - Scrape user posts         │  │
│  │ (9 tools)          │  │   │  │  - Analyze writing style     │  │
│  │ - Rate limits      │  │   │  │  - Progress tracking         │  │
│  │ - Hidden data      │  │   │  └──────────────────────────────┘  │
│  │ - Human clicks     │  │   │                                     │
│  │ - Session health   │  │   │  ┌──────────────────────────────┐  │
│  └────────────────────┘  │   │  │  Agent Status Component      │  │
│                          │   │  │  - Current workflow          │  │
│  ┌────────────────────┐  │   │  │  - Action history            │  │
│  │ Workflows          │  │   │  │  - Performance metrics       │  │
│  │ - Engagement       │  │   │  └──────────────────────────────┘  │
│  │ - Posting          │  │   │                                     │
│  │ - DM outreach      │  │   └─────────────────────────────────────┘
│  └────────────────────┘  │
│                          │
│  ┌────────────────────┐  │
│  │ Memory System      │  │
│  │ - Action history   │  │
│  │ - User preferences │  │
│  │ - Writing style    │  │
│  └────────────────────┘  │
│                          │
└──────────────────────────┘
```

---

## 🔄 Data Flow Example: "Like a Post"

### Step-by-Step Flow:

```
1. USER → Dashboard
   "I want to like trending AI posts"
   
2. Dashboard → Agent
   HTTP POST /agent/run
   {"goal": "like trending AI posts"}
   
3. Agent → Extension Tool
   "Check rate limits"
   ↓
   HTTP POST localhost:8001/extension/rate_limit_status
   
4. Extension Backend → Chrome Extension (WebSocket)
   {"type": "CHECK_RATE_LIMIT", "request_id": "abc-123"}
   
5. Chrome Extension → X.com DOM
   Checks page for rate limit messages
   Returns: {"success": true, "is_rate_limited": false}
   
6. Extension Backend → Agent
   Returns rate limit status
   
7. Agent → Extension Tool
   "Find trending topics"
   ↓
   HTTP POST localhost:8001/extension/trending_topics
   
8. Extension Backend → Chrome Extension
   {"type": "GET_TRENDING_TOPICS", "request_id": "def-456"}
   
9. Chrome Extension → X.com DOM
   Extracts trending sidebar
   Returns: {"topics": ["AI agents", "LangGraph", ...]}
   
10. Agent → Extension Tool
    "Find high-engagement posts on 'AI agents'"
    ↓
    HTTP POST localhost:8001/extension/find_posts
    
11. Extension Backend → Chrome Extension
    {"type": "FIND_HIGH_ENGAGEMENT_POSTS", "topic": "AI agents"}
    
12. Chrome Extension → X.com DOM
    Searches posts, ranks by engagement
    Returns: [{author: "akshay", likes: 150, ...}, ...]
    
13. Agent → Extension Tool
    "Like post by akshay with human-like behavior"
    ↓
    HTTP POST localhost:8001/extension/human_click
    
14. Extension Backend → Chrome Extension
    {"type": "HUMAN_CLICK", "element_description": "like button..."}
    
15. Chrome Extension → X.com DOM
    - Adds random delay (50-150ms)
    - Moves mouse with micro-movements
    - Dispatches realistic events
    - Clicks like button
    Returns: {"success": true, "stealth_score": 95}
    
16. Agent → Playwright Tool
    "Take screenshot to verify"
    ↓
    HTTP GET localhost:8005/screenshot
    
17. Docker Chromium → Playwright
    Takes screenshot
    Returns: base64 image data
    
18. Agent → Memory System
    Saves action to history
    {"action": "like", "post": "akshay AI agents", "success": true}
    
19. Agent → Dashboard
    Returns: "✅ Successfully liked post by akshay!"
    
20. Dashboard → User
    Shows success message + screenshot
```

---

## 🎯 Component Responsibilities

### Chrome Extension (User's Browser):
- ✅ Captures cookies for authentication
- ✅ Scrapes user's posts for writing style
- ✅ Sends data to backend

### Extension Backend Server:
- ✅ Bridges agent ↔ extension communication
- ✅ WebSocket server for real-time commands
- ✅ 9 HTTP endpoints for extension tools
- ✅ Request/response routing

### Main Backend Server:
- ✅ Cookie injection into Docker
- ✅ Session management
- ✅ Dashboard WebSocket
- ✅ Post import handling

### Docker Container:
- ✅ Chromium with extension (for agent)
- ✅ Playwright stealth browser
- ✅ VNC server for visual monitoring
- ✅ Isolated environment

### LangGraph Agent:
- ✅ Strategic decision making
- ✅ 36 tools (27 Playwright + 9 Extension)
- ✅ Workflow execution
- ✅ Memory management
- ✅ Writing style learning

### Frontend Dashboard:
- ✅ VNC viewer (see agent in action)
- ✅ Import posts feature
- ✅ Agent status monitoring
- ✅ Real-time updates

---

## 🚀 Startup Sequence

```
1. START_COMPLETE_SYSTEM.sh
   ↓
2. Extension Backend Server (port 8001)
   ↓
3. Main Backend Server (port 8000)
   ↓
4. Docker Container with Extension
   ├─ Chromium with extension
   ├─ Playwright API (port 8005)
   └─ VNC Server (port 5900)
   ↓
5. Frontend Dashboard (port 3000)
   ↓
6. User reloads Chrome Extension
   ↓
7. Extension connects to backend
   ↓
8. System ready! 🎉
```

---

## 📊 Port Map

| Port | Service | Purpose |
|------|---------|---------|
| 3000 | Frontend Dashboard | User interface |
| 5900 | VNC Server | Visual monitoring |
| 8000 | Main Backend | Cookie injection, WebSocket |
| 8001 | Extension Backend | Extension tool endpoints |
| 8005 | Playwright API | Browser automation |

---

## 🔐 Security & Isolation

```
┌─────────────────────────────────────────┐
│  User's Browser (Real X Account)       │
│  - Cookies captured securely            │
│  - Extension runs in isolated context   │
└──────────────┬──────────────────────────┘
               │ Encrypted WebSocket
               ▼
┌─────────────────────────────────────────┐
│  Backend Servers (Localhost)            │
│  - No external access                   │
│  - Cookies encrypted in transit         │
└──────────────┬──────────────────────────┘
               │ Internal network
               ▼
┌─────────────────────────────────────────┐
│  Docker Container (Isolated)            │
│  - Separate browser instance            │
│  - No access to host system             │
│  - Cookies injected securely            │
└─────────────────────────────────────────┘
```

---

## 🎉 Complete Integration

**Everything is connected:**
- ✅ Extension in user's browser → Captures cookies & scrapes posts
- ✅ Extension backend → Bridges agent ↔ extension
- ✅ Main backend → Injects cookies into Docker
- ✅ Docker with extension → Agent's browser environment
- ✅ Playwright tools → Screenshots & visual context
- ✅ Extension tools → Actions & hidden data
- ✅ Agent → Strategic intelligence
- ✅ Dashboard → Visual monitoring & control

**One command starts everything:** `./START_COMPLETE_SYSTEM.sh` 🚀

