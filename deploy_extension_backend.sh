#!/bin/bash

# =============================================================================
# Extension Backend Service Deployment Script for Cloud Run
# =============================================================================
#
# WHEN TO USE THIS SCRIPT:
#   - After making changes to backend_extension_server.py
#   - After updating extension-related endpoints or functionality
#   - When you need to redeploy the extension backend
#
# IMPORTANT: This script deploys ONLY extension-backend-service!
#   - backend-api: Use deploy_cloudrun.sh
#   - langgraph-service: Use deploy_langgraph_service.sh
#   - extension-backend-service: Use THIS script
#
# USAGE:
#   ./deploy_extension_backend.sh
#
# WHAT THIS SCRIPT DOES:
#   1. Builds Docker image using Dockerfile.extension
#   2. Pushes the image to Google Container Registry
#   3. Deploys to Cloud Run as extension-backend-service
#   4. Sets up Cloud SQL connection and environment variables
#
# PREREQUISITES:
#   - gcloud CLI authenticated with parallel-universe-prod project
#   - Docker running locally
#   - Dockerfile.extension exists in the project root
#
# =============================================================================

set -e

PROJECT_ID="parallel-universe-prod"
REGION="us-central1"
SERVICE_NAME="extension-backend-service"

echo "🚀 Deploying Extension Backend Service to Cloud Run..."
echo "======================================================="
echo ""

# Use Cloud Build to build and deploy
echo "📦 Building and deploying using Cloud Build..."
echo "   This uses Dockerfile.extension and cloudbuild.extension.yaml"
echo ""

gcloud builds submit \
  --config cloudbuild.extension.yaml \
  --project="$PROJECT_ID"

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
echo ""

# Health check
echo "🏥 Running health check..."
HEALTH_RESPONSE=$(curl -s "$SERVICE_URL/" 2>&1 || echo "FAILED")
if echo "$HEALTH_RESPONSE" | grep -q -E "Extension Backend|WebSocket|ready"; then
  echo "✅ Health check passed!"
else
  echo "⚠️  Health check response: $HEALTH_RESPONSE"
fi

echo ""
echo "🎉 Done! Extension Backend Service deployed to: $SERVICE_URL"
echo ""
echo "📝 This service provides:"
echo "   - WebSocket endpoint for Chrome extension communication"
echo "   - /extension/* REST API endpoints"
echo "   - Premium status detection (/extension/premium_status)"
echo ""
