# GitHub CI/CD Setup Guide

This guide will help you set up automated deployments for both the backend (`cua`) and frontend (`cua-frontend`) repositories.

## Prerequisites

1. Both repositories pushed to GitHub
2. GCP Service Account with deployment permissions
3. Access to GitHub repository settings

## Step 1: Create GCP Service Account

If you don't already have a service account for CI/CD:

```bash
# Create service account
gcloud iam service-accounts create github-actions \
  --display-name="GitHub Actions Deployer" \
  --project=parallel-universe-prod

# Grant necessary roles
gcloud projects add-iam-policy-binding parallel-universe-prod \
  --member="serviceAccount:github-actions@parallel-universe-prod.iam.gserviceaccount.com" \
  --role="roles/run.admin"

gcloud projects add-iam-policy-binding parallel-universe-prod \
  --member="serviceAccount:github-actions@parallel-universe-prod.iam.gserviceaccount.com" \
  --role="roles/cloudbuild.builds.builder"

gcloud projects add-iam-policy-binding parallel-universe-prod \
  --member="serviceAccount:github-actions@parallel-universe-prod.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"

gcloud projects add-iam-policy-binding parallel-universe-prod \
  --member="serviceAccount:github-actions@parallel-universe-prod.iam.gserviceaccount.com" \
  --role="roles/storage.admin"

gcloud projects add-iam-policy-binding parallel-universe-prod \
  --member="serviceAccount:github-actions@parallel-universe-prod.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.writer"

# Create and download key
gcloud iam service-accounts keys create github-actions-key.json \
  --iam-account=github-actions@parallel-universe-prod.iam.gserviceaccount.com
```

## Step 2: Configure GitHub Secrets

### For Backend Repository (`cua`)

Go to: `https://github.com/YOUR_ORG/cua/settings/secrets/actions`

Add the following secrets:

1. **GCP_SA_KEY**
   - Value: Contents of `github-actions-key.json`
   - How to get: `cat github-actions-key.json` (copy entire JSON)

2. **REDIS_HOST**
   - Value: `10.110.183.147` (or your Redis internal IP)

### For Frontend Repository (`cua-frontend`)

Go to: `https://github.com/YOUR_ORG/cua-frontend/settings/secrets/actions`

Add the following secrets:

1. **GCP_SA_KEY**
   - Value: Contents of `github-actions-key.json`
   - How to get: `cat github-actions-key.json` (copy entire JSON)

2. **CLERK_PUBLISHABLE_KEY**
   - Value: `pk_test_cHJlc2VudC13YXNwLTUzLmNsZXJrLmFjY291bnRzLmRldiQ`

3. **CLERK_SECRET_KEY**
   - Value: `sk_test_NWWN1EbDckqh8N5t8ElobwoC5apBqnq7jdEsfcG68w`

## Step 3: Verify Workflow Files

### Backend Workflow
File: `.github/workflows/deploy-backend.yml`

Deploys 3 services on push to `main`:
- Main Backend API
- Extension Backend
- OmniParser

### Frontend Workflow
File: `.github/workflows/deploy-frontend.yml`

Deploys frontend on push to `main`:
- Builds Docker image with Clerk publishable key
- Deploys to Cloud Run
- Updates runtime env vars with Clerk secret key

## Step 4: Test Deployment

1. Commit and push the workflow files:

```bash
# Backend
cd /home/rajathdb/cua
git add .github/workflows/deploy-backend.yml GITHUB_CICD_SETUP.md
git commit -m "Add GitHub Actions CI/CD workflow"
git push origin main

# Frontend
cd /home/rajathdb/cua-frontend
git add .github/workflows/deploy-frontend.yml
git commit -m "Add GitHub Actions CI/CD workflow"
git push origin main
```

2. Check GitHub Actions tab:
   - Backend: `https://github.com/YOUR_ORG/cua/actions`
   - Frontend: `https://github.com/YOUR_ORG/cua-frontend/actions`

3. Monitor the deployment logs for any errors

## Workflow Behavior

### Backend (`cua`)
- **Trigger**: Push to `main` branch
- **Runs**: 3 parallel jobs
  - Deploy Main Backend API (with Redis VPC connector)
  - Deploy Extension Backend (via Cloud Build)
  - Deploy OmniParser (via Cloud Build)
- **Duration**: ~5-8 minutes

### Frontend (`cua-frontend`)
- **Trigger**: Push to `main` branch
- **Runs**: Single job with 2 steps
  - Build and deploy via Cloud Build
  - Update runtime environment variables
- **Duration**: ~4-6 minutes

## Troubleshooting

### Permission Denied Errors
- Verify service account has all required roles
- Check that `GCP_SA_KEY` secret is valid JSON

### Build Failures
- Check Cloud Build logs in GCP Console
- Verify Dockerfile and cloudbuild.yaml are correct

### Environment Variable Issues
- Ensure all secrets are set in GitHub
- Check spelling of secret names in workflow file

## Security Notes

1. **Never commit** `github-actions-key.json` to git
2. Add to `.gitignore`:
   ```
   github-actions-key.json
   *.json
   ```
3. Rotate service account keys periodically
4. Use different service accounts for dev/staging/prod

## Additional Configuration

### Deploy to Specific Branches

To deploy from branches other than `main`, edit the workflow:

```yaml
on:
  push:
    branches:
      - main
      - staging
      - production
```

### Manual Deployment

You can also trigger deployments manually:

```yaml
on:
  push:
    branches:
      - main
  workflow_dispatch:  # Enables manual trigger
```

Then use: Actions → Select workflow → Run workflow

## Next Steps

- [ ] Set up staging environment
- [ ] Add automated tests before deployment
- [ ] Configure deployment notifications (Slack/Discord)
- [ ] Set up rollback procedures
- [ ] Monitor deployment metrics
