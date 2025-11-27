#!/bin/bash

# =============================================================================
# LangGraph Service Deployment Script for Cloud Run
# =============================================================================
#
# WHEN TO USE THIS SCRIPT:
#   - After making changes to LangGraph agents (x_growth_deep_agent.py, etc.)
#   - After updating langgraph.json configuration
#   - When you need to redeploy the LangGraph Cloud server
#
# IMPORTANT: This script deploys the LANGGRAPH SERVER, not backend-api!
#   - backend-api: Use deploy_cloudrun.sh (runs backend_websocket_server.py)
#   - langgraph-service: Use THIS script (runs LangGraph Cloud with `langgraph up`)
#
# USAGE:
#   ./deploy_langgraph_service.sh
#
# WHAT THIS SCRIPT DOES:
#   1. Builds LangGraph Docker image using `langgraph build`
#   2. Pushes the image to Google Container Registry
#   3. Deploys to Cloud Run as langgraph-service
#   4. Sets up environment variables (POSTGRES_URI, API keys, etc.)
#
# PREREQUISITES:
#   - langgraph CLI installed (`pip install langgraph-cli`)
#   - gcloud CLI authenticated with parallel-universe-prod project
#   - Docker running locally
#
# =============================================================================

set -e

PROJECT_ID="parallel-universe-prod"
REGION="us-central1"
SERVICE_NAME="langgraph-service"
IMAGE_TAG="gcr.io/$PROJECT_ID/$SERVICE_NAME:latest"

echo "🚀 Deploying LangGraph Service to Cloud Run..."
echo "============================================"
echo ""

# Step 1: Build LangGraph Docker image
echo "📦 Building LangGraph Docker image..."
echo "   This will create a proper LangGraph Cloud server image"
echo "   (NOT backend_websocket_server.py - that's for backend-api)"
echo ""

langgraph build -t "$IMAGE_TAG" -c langgraph.json

echo ""
echo "✅ LangGraph image built successfully"
echo ""

# Step 2: Push to Google Container Registry
echo "🔼 Pushing image to Google Container Registry..."
docker push "$IMAGE_TAG"

echo ""
echo "✅ Image pushed to GCR"
echo ""

# Step 3: Fetch secrets from Google Secret Manager
echo "🔐 Fetching secrets from Secret Manager..."
ANTHROPIC_KEY=$(gcloud secrets versions access latest --secret=anthropic-api-key --project=$PROJECT_ID)
OPENAI_KEY=$(gcloud secrets versions access latest --secret=openai-api-key --project=$PROJECT_ID 2>/dev/null || echo "")
LANGSMITH_KEY=$(gcloud secrets versions access latest --secret=langsmith-api-key --project=$PROJECT_ID 2>/dev/null || echo "")

# Get POSTGRES_URI (LangGraph uses POSTGRES_URI, not DATABASE_URL!)
POSTGRES_URI=$(gcloud secrets versions access latest --secret=postgres-uri --project=$PROJECT_ID 2>/dev/null || gcloud secrets versions access latest --secret=database-url --project=$PROJECT_ID 2>/dev/null || echo "postgresql://postgres:ParallelUniverse2024!@10.97.0.3:5432/parallel_universe_db")

echo "✅ Secrets retrieved"
echo ""

# Step 4: Deploy to Cloud Run
echo "🚀 Deploying to Cloud Run..."

# Environment variables for LangGraph service
ENV_VARS="POSTGRES_URI=$POSTGRES_URI"
ENV_VARS="$ENV_VARS,REDIS_HOST=10.110.183.147"
ENV_VARS="$ENV_VARS,GCP_PROJECT_ID=$PROJECT_ID"
ENV_VARS="$ENV_VARS,ANTHROPIC_API_KEY=$ANTHROPIC_KEY"
[ -n "$OPENAI_KEY" ] && ENV_VARS="$ENV_VARS,OPENAI_API_KEY=$OPENAI_KEY"
[ -n "$LANGSMITH_KEY" ] && ENV_VARS="$ENV_VARS,LANGSMITH_API_KEY=$LANGSMITH_KEY"

gcloud run deploy "$SERVICE_NAME" \
  --image="$IMAGE_TAG" \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --allow-unauthenticated \
  --vpc-connector=paralleluniverse-vpc \
  --set-env-vars="$ENV_VARS" \
  --memory=4Gi \
  --cpu=2 \
  --timeout=3600 \
  --min-instances=1 \
  --max-instances=10

echo ""
echo "✅ Deployment complete!"
echo ""

# Step 5: Verify deployment
echo "🔍 Verifying deployment..."
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --format="value(status.url)")

echo "📡 Service URL: $SERVICE_URL"
echo ""

# Health check
echo "🏥 Running health check..."
HEALTH_RESPONSE=$(curl -s "$SERVICE_URL/" 2>&1 || echo "FAILED")
if echo "$HEALTH_RESPONSE" | grep -q -E "ok|LangGraph|langgraph"; then
  echo "✅ Health check passed!"
else
  echo "⚠️  Health check response: $HEALTH_RESPONSE"
fi

echo ""
echo "🎉 Done! LangGraph service deployed to: $SERVICE_URL"
echo ""
echo "📝 This service provides LangGraph Cloud API endpoints:"
echo "   - /threads/search  (list threads)"
echo "   - /threads/{id}    (get thread)"
echo "   - /runs/stream     (execute agents)"
echo ""
