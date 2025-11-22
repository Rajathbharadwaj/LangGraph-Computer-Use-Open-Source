# Complete GCP Deployment Plan - Parallel Universe

## Service Architecture Analysis

### Current Services Identified:

```
┌─────────────────────────────────────────────────────────────────┐
│                    PARALLEL UNIVERSE PLATFORM                    │
└─────────────────────────────────────────────────────────────────┘

1. BACKEND API (backend_websocket_server.py)
   - Port: 8002
   - Functions: REST API, WebSocket, LangGraph integration
   - Deploy to: Cloud Run (PRIMARY SERVICE)

2. DATABASE (PostgreSQL)
   - Local: localhost:5433
   - GCP: Cloud SQL PostgreSQL 15
   - Deploy to: Cloud SQL ✅ IN PROGRESS

3. SCHEDULED POST EXECUTOR (scheduled_post_executor.py)
   - Function: Execute posts at scheduled times
   - Current: APScheduler (requires always-on server)
   - Deploy to: Cloud Scheduler + Cloud Run endpoint ✅ PLANNED

4. FRONTEND (cua-frontend/)
   - Framework: Next.js
   - Deploy to: Cloud Run ✅ PLANNED

5. CHROME EXTENSION (x-automation-extension/)
   - Function: Browser automation, cookie management
   - Deploy to: Chrome Web Store OR Self-hosted ⚠️ NEEDS DECISION

6. LANGGRAPH AGENTS (embedded)
   - x_growth_deep_agent.py
   - langgraph_cua_agent.py
   - Deploy to: Same Cloud Run service as backend ✅
```

---

## ✅ WHAT WE'RE DEPLOYING CORRECTLY

### 1. Backend API (Cloud Run)
```yaml
Service: backend-api
Image: gcr.io/parallel-universe-prod/backend-api
Configuration:
  - Memory: 2GB
  - CPU: 2 vCPU
  - Min instances: 1 (WebSocket needs persistent connection)
  - Max instances: 10
  - Port: 8080 (Cloud Run standard)
  - Environment:
      - ANTHROPIC_API_KEY (from Secret Manager)
      - PERPLEXITY_API_KEY (from Secret Manager)
      - DATABASE_URL (from Secret Manager)
      - LANGSMITH_API_KEY (from Secret Manager)
  - Cloud SQL Connection: ✅ Configured
  - WebSocket Support: ✅ Native Cloud Run support
```

**Status**: ✅ Docker build in progress

### 2. PostgreSQL Database (Cloud SQL)
```yaml
Instance: parallel-universe-db
Tier: db-f1-micro (0.6GB RAM, shared vCPU)
Storage: 10GB SSD, auto-increase enabled
Backup: Daily at 3:00 AM UTC
Region: us-central1
```

**Status**: ✅ Creation in progress

### 3. Frontend (Cloud Run)
```yaml
Service: frontend
Framework: Next.js
Memory: 1GB
CPU: 1 vCPU
Min instances: 1
Max instances: 5
Environment:
  - NEXT_PUBLIC_BACKEND_URL: https://backend-api-xxx.run.app
```

**Status**: 📋 Next step after backend

### 4. Scheduled Post Execution (Cloud Scheduler)
```yaml
Job: execute-scheduled-posts
Schedule: "* * * * *" (every minute)
Target: POST /api/cron/execute-scheduled-posts
Authentication: OIDC token with service account
```

**Status**: 📋 Will configure after backend deployment

---

## ⚠️ WHAT WE NEED TO DECIDE

### Chrome Extension Distribution

You have **3 OPTIONS**:

#### **Option 1: Chrome Web Store (Recommended for Public Release)**

**Pros:**
- Official distribution
- Automatic updates
- Users trust it
- Easy installation (1-click)

**Cons:**
- $5 one-time developer fee
- Review process (1-3 days)
- Requires privacy policy
- Public listing (or unlisted)

**Steps:**
1. Create Chrome Web Store developer account ($5)
2. Package extension as .zip
3. Submit for review
4. Get approved
5. Users install from: `chrome://extensions` or Web Store link

**Timeline**: 2-3 days for approval

---

#### **Option 2: Self-Hosted (Unlisted/Private Distribution)**

**Pros:**
- No review process
- Full control
- Can update instantly
- Free

**Cons:**
- Users need to enable "Developer mode"
- Manual updates
- No automatic distribution
- Chrome shows warning "This extension is not listed in the Chrome Web Store"

**Steps:**
1. Zip the extension folder
2. Host on your website/GCS bucket
3. Users download and install manually:
   - Go to `chrome://extensions`
   - Enable "Developer mode"
   - Click "Load unpacked"
   - Select extension folder

**Timeline**: Immediate, but requires user education

---

#### **Option 3: Enterprise Distribution (For Company Use)**

**Pros:**
- Private to your organization
- Centrally managed
- Force-install to users

**Cons:**
- Requires Google Workspace
- More complex setup

---

### **RECOMMENDATION:**

**Start with Option 2 (Self-Hosted)** for:
- Beta testing
- Early users
- Quick iteration

**Move to Option 1 (Chrome Web Store)** when:
- Product is stable
- Ready for public release
- Want easier user onboarding

---

## Extension Configuration for Production

The extension needs to be updated to connect to your production backend:

### Current Configuration:
```javascript
// x-automation-extension/background.js
const wsUrl = `ws://localhost:8002/ws/extension/${userId}`;  // ❌ Development
```

### Production Configuration:
```javascript
// Option A: Using Cloud Run URL
const wsUrl = `wss://backend-api-xxx-uc.a.run.app/ws/extension/${userId}`;

// Option B: Using custom domain (recommended)
const wsUrl = `wss://api.paralleluniverse.com/ws/extension/${userId}`;
```

### Extension Update Process:

1. **Update manifest.json**:
```json
{
  "host_permissions": [
    "https://x.com/*",
    "https://twitter.com/*",
    "https://*.run.app/*",
    "https://api.paralleluniverse.com/*"
  ]
}
```

2. **Create production build**:
```bash
# Update URLs in background.js and extension_agent_bridge.js
cd x-automation-extension
zip -r parallel-universe-extension-v1.0.zip . -x "*.git*" "node_modules/*"
```

3. **Distribution**:
   - **Self-hosted**: Upload to Cloud Storage bucket
   - **Chrome Store**: Submit through developer dashboard

---

## DEPLOYMENT CHECKLIST

### ✅ Phase 1: Infrastructure (CURRENT)
- [x] GCP project created
- [x] APIs enabled
- [x] Service account created
- [x] Secrets stored
- [ ] Database created (IN PROGRESS)
- [ ] Backend Docker built (IN PROGRESS)

### 📋 Phase 2: Backend Deployment (NEXT 10 MIN)
- [ ] Deploy backend to Cloud Run
- [ ] Connect Cloud SQL to backend
- [ ] Get backend URL
- [ ] Test health endpoint
- [ ] Test WebSocket connection

### 📋 Phase 3: Database Setup (NEXT 15 MIN)
- [ ] Create database schema
- [ ] Run migrations
- [ ] Seed initial data (if needed)
- [ ] Test database connection

### 📋 Phase 4: Frontend Deployment (NEXT 20 MIN)
- [ ] Build frontend Docker image
- [ ] Deploy to Cloud Run
- [ ] Configure NEXT_PUBLIC_BACKEND_URL
- [ ] Test frontend loads

### 📋 Phase 5: Scheduling (NEXT 30 MIN)
- [ ] Create Cloud Scheduler job
- [ ] Add `/api/cron/execute-scheduled-posts` endpoint
- [ ] Test scheduled execution
- [ ] Monitor logs

### 📋 Phase 6: Extension (DEPENDS ON CHOICE)
- [ ] **Decision: Chrome Store vs Self-Hosted?**
- [ ] Update extension URLs to production
- [ ] Test extension connection
- [ ] Package extension
- [ ] Distribute to users

### 📋 Phase 7: Monitoring (NEXT 45 MIN)
- [ ] Set up logging
- [ ] Create dashboards
- [ ] Configure alerts
- [ ] Set up budget alerts

---

## MISSING SERVICES ANALYSIS

Based on file analysis, you also have these files that we should address:

### Additional Backend Services (Optional):
```
backend_extension_server.py      - Old extension backend (REPLACE with backend_websocket_server.py)
backend_post_importer.py          - Post import utility (KEEP as utility, not service)
multi_tenant_backend.py           - Alternative backend (NOT NEEDED if using backend_websocket_server.py)
cua_server.py                     - Legacy server (NOT NEEDED)
stealth_cua_server.py             - Stealth variant (NOT NEEDED)
```

**Recommendation**: Only deploy `backend_websocket_server.py` as it's the main unified backend.

### Agent Files (Embedded in Backend):
```
x_growth_deep_agent.py           - ✅ Already imported by backend
langgraph_cua_agent.py           - ✅ Already imported by backend
x_strategic_subagents.py         - ✅ Already imported by backend
```

These are **already bundled** in the Docker image, no separate deployment needed.

---

## COST ESTIMATE

### Development/Testing (Current Setup):
```
Cloud Run (backend): $5-20/month
Cloud Run (frontend): $3-10/month
Cloud SQL (db-f1-micro): $7-15/month
Cloud Scheduler: $0.10/month
Secrets: $0.06/month
Storage: $0.20/month
Total: ~$20-50/month
```

### Production (1000 users):
```
Cloud Run (backend): $50-150/month
Cloud Run (frontend): $20-50/month
Cloud SQL (db-n1-standard-1): $50-100/month
Cloud Scheduler: $0.10/month
Secrets: $0.06/month
Storage: $5/month
Load Balancer (optional): $20/month
Total: ~$150-350/month
```

---

## NEXT STEPS DECISION TREE

```
1. ✅ Wait for database + Docker build to complete (5 min)
   ↓
2. Deploy backend to Cloud Run (2 min)
   ↓
3. Initialize database schema (3 min)
   ↓
4. Test backend endpoints (2 min)
   ↓
5. **DECISION POINT: Extension Distribution**

   A. Chrome Web Store Route:
      - Create developer account ($5)
      - Update extension URLs
      - Package and submit
      - Wait 1-3 days for approval

   B. Self-Hosted Route:
      - Update extension URLs
      - Package as .zip
      - Upload to Cloud Storage
      - Share download link
      - Users install manually

   ↓
6. Deploy frontend (10 min)
   ↓
7. Set up Cloud Scheduler (5 min)
   ↓
8. Configure monitoring (5 min)
   ↓
9. ✅ PRODUCTION READY
```

---

## QUESTIONS FOR YOU:

1. **Extension Distribution**: Do you want to:
   - A) Submit to Chrome Web Store (public/unlisted, 1-3 days, $5 fee)
   - B) Self-host for now (immediate, free, manual install)

2. **Custom Domain**: Do you want to:
   - A) Use Cloud Run URLs (`backend-api-xxx.run.app`)
   - B) Set up custom domain (`api.paralleluniverse.com`) - requires domain ownership

3. **Testing Strategy**: Before going live:
   - A) Deploy everything and test in production
   - B) Create staging environment first

4. **User Onboarding**: How will users get the extension?
   - A) Public release (anyone can use)
   - B) Private beta (invite-only)
   - C) Enterprise (specific companies)

---

## IMMEDIATE ACTION ITEMS

While database and Docker build complete:

1. ✅ Decide on extension distribution method
2. ✅ Decide on domain strategy
3. ⏳ Wait for builds to complete
4. 🚀 Continue deployment

**Estimated Total Deployment Time**: 30-45 minutes (excluding Chrome Store review)

