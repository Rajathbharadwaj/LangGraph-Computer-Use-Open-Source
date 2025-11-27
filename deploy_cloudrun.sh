#!/bin/bash

# =============================================================================
# Cloud Run Deployment Script for Parallel Universe Backend
# =============================================================================
#
# WHEN TO USE THIS SCRIPT:
#   - After making code changes to backend_websocket_server.py or any backend files
#   - After fixing bugs that need to be deployed to production
#   - When environment variables need to be updated
#   - To redeploy after a failed deployment
#
# USAGE:
#   ./deploy_cloudrun.sh              # Deploy backend-api (default)
#   ./deploy_cloudrun.sh backend-api  # Explicitly deploy backend-api
#
# WHAT THIS SCRIPT DOES:
#   1. Fetches API keys from Google Secret Manager (Anthropic, OpenAI, Clerk, etc.)
#   2. Builds the Docker image from source
#   3. Deploys to Cloud Run with all required environment variables
#   4. Runs a health check to verify deployment
#
# PREREQUISITES:
#   - gcloud CLI authenticated with parallel-universe-prod project
#   - Secrets configured in Google Secret Manager
#
# =============================================================================

set -e

SERVICE_NAME="${1:-backend-api}"
PROJECT_ID="parallel-universe-prod"
REGION="us-central1"

echo "🚀 Deploying $SERVICE_NAME to Cloud Run..."
echo "============================================"

# Fetch secrets from Google Secret Manager
echo "🔐 Fetching secrets from Secret Manager..."
ANTHROPIC_KEY=$(gcloud secrets versions access latest --secret=anthropic-api-key --project=$PROJECT_ID)
OPENAI_KEY=$(gcloud secrets versions access latest --secret=openai-api-key --project=$PROJECT_ID 2>/dev/null || echo "")
LANGSMITH_KEY=$(gcloud secrets versions access latest --secret=langsmith-api-key --project=$PROJECT_ID 2>/dev/null || echo "")
CLERK_SECRET=$(gcloud secrets versions access latest --secret=clerk-secret-key --project=$PROJECT_ID 2>/dev/null || echo "")
CLERK_PUBLISHABLE=$(gcloud secrets versions access latest --secret=clerk-publishable-key --project=$PROJECT_ID 2>/dev/null || echo "")

# Environment variables for Cloud Run
ENV_VARS="DATABASE_URL=postgresql://postgres:ParallelUniverse2024!@10.97.0.3:5432/parallel_universe_db"
ENV_VARS="$ENV_VARS,REDIS_HOST=10.110.183.147"
ENV_VARS="$ENV_VARS,GCP_PROJECT_ID=$PROJECT_ID"
ENV_VARS="$ENV_VARS,LANGGRAPH_URL=https://langgraph-service-644185288504.us-central1.run.app"
ENV_VARS="$ENV_VARS,ANTHROPIC_API_KEY=$ANTHROPIC_KEY"
[ -n "$OPENAI_KEY" ] && ENV_VARS="$ENV_VARS,OPENAI_API_KEY=$OPENAI_KEY"
[ -n "$LANGSMITH_KEY" ] && ENV_VARS="$ENV_VARS,LANGSMITH_API_KEY=$LANGSMITH_KEY"
[ -n "$CLERK_SECRET" ] && ENV_VARS="$ENV_VARS,CLERK_SECRET_KEY=$CLERK_SECRET"
[ -n "$CLERK_PUBLISHABLE" ] && ENV_VARS="$ENV_VARS,NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=$CLERK_PUBLISHABLE"
ENV_VARS="$ENV_VARS,EXTENSION_BACKEND_URL=https://extension-backend-service-644185288504.us-central1.run.app"

echo "📦 Building and deploying from source..."

gcloud run deploy "$SERVICE_NAME" \
  --source . \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --allow-unauthenticated \
  --vpc-connector=paralleluniverse-vpc \
  --set-env-vars="$ENV_VARS" \
  --memory=2Gi \
  --cpu=2 \
  --timeout=3600 \
  --min-instances=1 \
  --max-instances=10

echo ""
echo "✅ Deployment complete!"
echo ""

# Verify deployment
echo "🔍 Verifying deployment..."
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --format="value(status.url)")

echo "📡 Service URL: $SERVICE_URL"

# Health check
echo "🏥 Running health check..."
HEALTH_RESPONSE=$(curl -s "$SERVICE_URL/" 2>&1 || echo "FAILED")
if echo "$HEALTH_RESPONSE" | grep -q "Parallel Universe"; then
  echo "✅ Health check passed!"
else
  echo "⚠️  Health check response: $HEALTH_RESPONSE"
fi

echo ""
echo "🎉 Done! Service deployed to: $SERVICE_URL"
