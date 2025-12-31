---
description: Deploy application components to production (backend, frontend, langgraph, or all)
argument-hint: <component> | backend | frontend | langgraph | all
allowed-tools: Bash(./deploy_cloudrun.sh:*), Bash(./deploy_langgraph_service.sh:*), Bash(gcloud:*), Bash(npm:*), Bash(git:*), Bash(cd:*), Bash(docker:*), Bash(langgraph:*), Read
---

# Deploy Command

Deploy specified component(s) to production on Google Cloud Run.

## Available Components

| Component | Description | Script |
|-----------|-------------|--------|
| `backend` | Main FastAPI backend (backend_websocket_server.py) | `./deploy_cloudrun.sh` |
| `frontend` | Next.js frontend app | `cd cua-frontend && ./deploy.sh` |
| `langgraph` | LangGraph agent server (uses `langgraph build`) | `./deploy_langgraph_service.sh` |
| `all` | Deploy backend, frontend, and langgraph in sequence | All scripts |

## Deployment Requested

**Component to deploy:** `$ARGUMENTS`

## Pre-Deployment Checks

Before deploying:
1. Check git status to see uncommitted changes
2. Verify we're in the correct project directory
3. Confirm the deployment target

## Deployment Scripts

### Backend (`backend`)
```bash
./deploy_cloudrun.sh
```
Deploys FastAPI backend to Cloud Run with:
- 2GB memory, 2 CPU
- 300 second timeout
- Auto-scaling 1-10 instances
- Service URL: https://backend-websocket-server-644185288504.us-central1.run.app

### Frontend (`frontend`)
```bash
cd /home/rajathdb/cua-frontend && ./deploy.sh
```
Builds Next.js app and deploys to Cloud Run.
- Service URL: https://app.paralleluniverse.ai

### LangGraph (`langgraph`)
```bash
./deploy_langgraph_service.sh
```
This script:
1. Uses `langgraph build` to create a proper LangGraph Cloud server image
2. Pushes to Google Container Registry
3. Deploys to Cloud Run with 4GB memory, 1-hour timeout
4. Connects to PostgresStore and Redis

Note: LangGraph is different from backend - it runs the agent infrastructure!

### All (`all`)
Deploy backend, frontend, and langgraph in sequence.

## Post-Deployment

After successful deployment:
1. Report deployment status
2. Show service URL
3. Run health check: `curl https://SERVICE_URL/health`

## Service URLs

| Service | URL |
|---------|-----|
| Frontend | https://app.paralleluniverse.ai |
| Backend API | https://backend-websocket-server-644185288504.us-central1.run.app |
| LangGraph | https://langgraph-service-644185288504.us-central1.run.app |

## Usage Examples

```
/deploy backend      # Deploy the FastAPI backend
/deploy frontend     # Deploy the Next.js frontend
/deploy langgraph    # Deploy the LangGraph agent server
/deploy all          # Deploy everything
```
