# Scalable Per-User VNC Architecture

## Overview
Production-ready architecture for isolated per-user VNC browser sessions using Cloud Run Jobs.

## Architecture

```
User Request → Frontend → Backend API → Cloud Run Job (VNC Container)
                                       ↓
                                   Redis (Session Tracking)
                                       ↓
                          wss://vnc-{user_id}-{session_id}.run.app
```

## Components

### 1. Backend API Endpoints

**POST /api/vnc/create**
- Creates new VNC session for authenticated user
- Spawns Cloud Run Job with unique name
- Stores session metadata in Redis
- Returns VNC WebSocket URL

**DELETE /api/vnc/{session_id}**
- Terminates VNC container
- Cleans up Redis session data

**GET /api/vnc/session**
- Returns current user's active VNC session
- Creates new session if none exists

### 2. Cloud Run Job Configuration

Each VNC job runs as an isolated container:
- **Image**: `gcr.io/parallel-universe-prod/vnc-browser:latest`
- **Resources**: 4Gi RAM, 2 CPU
- **Timeout**: 3600s (1 hour)
- **Networking**: Public HTTPS with WebSocket
- **Auto-cleanup**: Job deletes after completion

### 3. Session Management (Redis)

```python
# Session data structure
{
  f"vnc:session:{user_id}": {
    "session_id": "uuid",
    "job_name": "vnc-{user_id}-{timestamp}",
    "url": "wss://...",
    "created_at": timestamp,
    "status": "starting|running|stopped"
  }
}
```

- TTL: 4 hours (auto-cleanup)
- Indexed by user_id for fast lookup

### 4. VNC Container

Dockerfile modifications needed:
- Expose port 5900 for VNC
- Add healthcheck endpoint
- Start X11vnc server on container start
- Enable WebSocket proxy

## Scalability

- **Concurrent Users**: Unlimited (GCP quota limits only)
- **Cost**: Pay per active session (Cloud Run Jobs billing)
- **Isolation**: Full isolation between users
- **Auto-scaling**: Cloud Run handles scaling automatically

## Implementation Steps

1. ✅ Cancel single shared VNC build
2. ⏳ Add VNC session management to backend API
3. ⏳ Deploy VNC as Cloud Run Job (not Service)
4. ⏳ Update frontend to request/connect to user-specific VNC
5. ⏳ Implement auto-cleanup of stale sessions

## Cost Estimate

- VNC Job: $0.00002400/vCPU-second + $0.00000250/GiB-second
- Per session (1 hour): ~$0.35
- 1000 concurrent users: ~$350/hour (only when active)
