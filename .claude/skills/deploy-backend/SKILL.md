---
name: deploy-backend
description: Deploy backend services to Cloud Run. Use when deploying updates, checking deployment status, or releasing new versions. Triggers on "deploy", "push to prod", "release", "cloud run".
allowed-tools: Read, Bash(./deploy*.sh:*), Bash(gcloud:*), Bash(cd:*), Bash(git:*)
---

# Deployment Guide

## Quick Deploy Commands

### Backend (Main API)
```bash
./deploy_cloudrun.sh
```

### Frontend (Next.js)
```bash
cd cua-frontend && ./deploy.sh
```

### Documentation
```bash
cd parallel-universe-docs && npm run build && gcloud builds submit --config cloudbuild.yaml --project parallel-universe-prod
```

### LangGraph Agent Server
```bash
# Uses Dockerfile.langgraph
gcloud builds submit --config cloudbuild.langgraph.yaml --project parallel-universe-prod
```

## Service URLs

| Service | URL |
|---------|-----|
| Frontend | https://app.paralleluniverse.ai |
| Backend API | https://backend-websocket-server-644185288504.us-central1.run.app |
| Docs | https://docs-service-644185288504.us-central1.run.app |
| LangGraph | Internal service |

## Pre-Deployment Checklist

1. **Test locally** - Run the service and verify changes
2. **Check git status** - Ensure all changes are committed
3. **Review environment variables** - Check secrets are set
4. **Run linting** - No syntax errors
5. **Check database migrations** - Schema changes in lifespan()

## Backend Deployment Details

The `deploy_cloudrun.sh` script:

1. Builds Docker image
2. Pushes to Google Container Registry
3. Deploys to Cloud Run with:
   - 2GB memory
   - 2 CPU
   - 300 request timeout
   - Auto-scaling (1-10 instances)

### Environment Variables

Set via Secret Manager or Cloud Run config:
- `DATABASE_URL` - PostgreSQL connection
- `REDIS_URL` - Redis connection
- `CLERK_SECRET_KEY` - Clerk auth
- `STRIPE_SECRET_KEY` - Stripe billing
- `ANTHROPIC_API_KEY` - Claude API

## Frontend Deployment Details

The `cua-frontend/deploy.sh` script:

1. Fetches secrets from Secret Manager
2. Builds Next.js with production config
3. Deploys to Cloud Run

### Build Arguments

```bash
--build-arg NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=...
--build-arg NEXT_PUBLIC_MAIN_BACKEND_URL=...
```

## Troubleshooting

### Deployment Failed
```bash
# Check build logs
gcloud builds list --limit=5

# View specific build
gcloud builds log BUILD_ID
```

### Service Not Starting
```bash
# Check Cloud Run logs
gcloud run services logs read SERVICE_NAME --region us-central1 --limit 50
```

### Database Connection Issues
```bash
# Verify Cloud SQL connectivity
gcloud sql instances describe INSTANCE_NAME
```

### Health Check
```bash
# Verify service is running
curl https://SERVICE_URL/health
```

## Rollback

```bash
# List revisions
gcloud run revisions list --service SERVICE_NAME --region us-central1

# Rollback to previous revision
gcloud run services update-traffic SERVICE_NAME \
  --to-revisions=REVISION_NAME=100 \
  --region us-central1
```

## GCS Public Assets

For public files (like extension downloads):

```bash
# Upload to public bucket
gsutil cp file.zip gs://parallel-universe-prod-public/

# Verify public access
gsutil iam ch allUsers:objectViewer gs://parallel-universe-prod-public
```

## Best Practices

1. **Deploy during low traffic** - Minimize user impact
2. **Monitor after deploy** - Check logs for errors
3. **Test health endpoint** - Verify service responds
4. **Keep rollback ready** - Know how to revert
5. **Document changes** - Update changelog
6. **Notify team** - Communicate deployments
