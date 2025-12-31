---
description: Check status and health of all deployed services
argument-hint: [service] | all | backend | frontend | langgraph
allowed-tools: Bash(gcloud:*), Bash(curl:*)
---

# Service Status Check

Check the deployment status and health of production services.

## Check Requested

**Service:** `$ARGUMENTS` (default: all)

## Service URLs

| Service | URL | Health Endpoint |
|---------|-----|-----------------|
| Backend | https://backend-websocket-server-644185288504.us-central1.run.app | /health |
| Frontend | https://app.paralleluniverse.ai | / |
| LangGraph | https://langgraph-service-644185288504.us-central1.run.app | / |

## Status Commands

### List all Cloud Run services
```bash
gcloud run services list --region us-central1 --project parallel-universe-prod --format="table(SERVICE,REGION,URL,LAST_DEPLOYED_BY,LAST_DEPLOYED_AT)"
```

### Backend health check
```bash
curl -s https://backend-websocket-server-644185288504.us-central1.run.app/health
```

### LangGraph health check
```bash
curl -s https://langgraph-service-644185288504.us-central1.run.app/
```

### Frontend health check
```bash
curl -s -o /dev/null -w "%{http_code}" https://app.paralleluniverse.ai
```

## Additional Checks

1. Show recent Cloud Build history:
```bash
gcloud builds list --limit=5 --project parallel-universe-prod
```

2. Show service revisions:
```bash
gcloud run revisions list --service backend-websocket-server --region us-central1 --project parallel-universe-prod --limit 5
```

## Usage Examples

```
/status           # Check all services
/status backend   # Check only backend
/status langgraph # Check only langgraph
```
