---
description: View Cloud Run service logs (backend, frontend, or langgraph)
argument-hint: <service> [lines] | backend | frontend | langgraph
allowed-tools: Bash(gcloud:*)
---

# View Service Logs

Fetch and display logs from the specified Cloud Run service.

## Service Requested

**Service:** `$1`
**Lines:** `$2` (default: 50)

## Service Mappings

| Argument | Service Name |
|----------|--------------|
| `backend` | backend-websocket-server |
| `frontend` | cua-frontend |
| `langgraph` | langgraph-service |

## Commands

### Backend logs
```bash
gcloud run services logs read backend-websocket-server --region us-central1 --project parallel-universe-prod --limit 50
```

### Frontend logs
```bash
gcloud run services logs read cua-frontend --region us-central1 --project parallel-universe-prod --limit 50
```

### LangGraph logs
```bash
gcloud run services logs read langgraph-service --region us-central1 --project parallel-universe-prod --limit 50
```

## Usage Examples

```
/logs backend        # View last 50 backend logs
/logs langgraph 100  # View last 100 langgraph logs
/logs frontend       # View last 50 frontend logs
```
