#!/bin/bash
# Parallel Universe Production Deployment Script
# Usage: ./deploy-prod.sh [backend|frontend|all|status]
#
# Required environment variables (set these before running):
#   CLERK_SECRET_KEY - Clerk production secret key (sk_live_...)
#   NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY - Clerk publishable key (pk_live_...)
#   DATABASE_URL - PostgreSQL connection string
#
# Or create a .env.prod file with these values

set -e

# Load from .env.prod if exists
if [ -f .env.prod ]; then
    source .env.prod
fi

PROJECT_ID="parallel-universe-prod"
REGION="us-central1"

# Check required env vars
if [ -z "$CLERK_SECRET_KEY" ]; then
    echo "Error: CLERK_SECRET_KEY not set. Export it or add to .env.prod"
    exit 1
fi
if [ -z "$DATABASE_URL" ]; then
    echo "Error: DATABASE_URL not set. Export it or add to .env.prod"
    exit 1
fi

# Defaults
REDIS_HOST="${REDIS_HOST:-10.110.183.147}"
REDIS_PORT="${REDIS_PORT:-6379}"

# Service URLs
EXTENSION_BACKEND_URL="https://extension-backend-service-644185288504.us-central1.run.app"
MAIN_BACKEND_URL="https://backend-api-644185288504.us-central1.run.app"
OMNIPARSER_URL="https://omniparser-service-644185288504.us-central1.run.app"
VNC_BROWSER_URL="wss://vnc-browser-service-644185288504.us-central1.run.app"

deploy_backend() {
    echo "🚀 Deploying Backend API..."

    cd /home/rajathdb/cua

    echo "📦 Building Docker image..."
    gcloud builds submit --tag gcr.io/$PROJECT_ID/backend-api:latest --project $PROJECT_ID --timeout=600s

    echo "🌐 Deploying to Cloud Run..."
    gcloud run deploy backend-api \
        --image gcr.io/$PROJECT_ID/backend-api:latest \
        --region $REGION \
        --platform managed \
        --allow-unauthenticated \
        --vpc-connector paralleluniverse-vpc \
        --vpc-egress private-ranges-only \
        --service-account parallel-universe-app@$PROJECT_ID.iam.gserviceaccount.com \
        --set-env-vars "DATABASE_URL=$DATABASE_URL,REDIS_HOST=$REDIS_HOST,REDIS_PORT=$REDIS_PORT,EXTENSION_BACKEND_URL=$EXTENSION_BACKEND_URL,GOOGLE_CLOUD_PROJECT=$PROJECT_ID,GCP_REGION=$REGION,CLERK_SECRET_KEY=$CLERK_SECRET_KEY" \
        --min-instances 1 \
        --cpu-boost \
        --timeout 60s \
        --project $PROJECT_ID

    echo "✅ Backend deployed!"
}

deploy_frontend() {
    echo "🚀 Deploying Frontend..."

    cd /home/rajathdb/cua-frontend

    echo "📦 Building and deploying frontend with production Clerk keys..."
    gcloud builds submit --config cloudbuild.yaml \
        --substitutions="_CLERK_SECRET_KEY=$CLERK_SECRET_KEY,_NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=$NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY" \
        --project $PROJECT_ID

    echo "✅ Frontend deployed!"
}

show_status() {
    echo "📊 Current deployment status:"
    echo ""
    echo "Backend revisions:"
    gcloud run revisions list --service backend-api --region $REGION --project $PROJECT_ID --format="table(name,active,status.conditions[0].status)" --limit=3
    echo ""
    echo "Frontend revisions:"
    gcloud run revisions list --service frontend --region $REGION --project $PROJECT_ID --format="table(name,active,status.conditions[0].status)" --limit=3
}

case "${1:-all}" in
    backend)
        deploy_backend
        ;;
    frontend)
        deploy_frontend
        ;;
    all)
        deploy_backend
        deploy_frontend
        ;;
    status)
        show_status
        exit 0
        ;;
    *)
        echo "Usage: $0 [backend|frontend|all|status]"
        echo ""
        echo "  backend  - Deploy only backend API"
        echo "  frontend - Deploy only frontend"
        echo "  all      - Deploy both (default)"
        echo "  status   - Show deployment status"
        exit 1
        ;;
esac

echo ""
echo "🎉 Deployment complete!"
show_status
