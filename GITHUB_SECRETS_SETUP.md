# GitHub Secrets Setup Guide

## Workload Identity Federation Complete!

Your Workload Identity Provider is now configured:
- Provider ID: `projects/644185288504/locations/global/workloadIdentityPools/github-pool/providers/github-provider`
- Service Account: `github-actions@parallel-universe-prod.iam.gserviceaccount.com`

## Step 1: Add Secrets to Backend Repo (`LangGraph-Computer-Use-Open-Source`)

Go to: https://github.com/Rajathbharadwaj/LangGraph-Computer-Use-Open-Source/settings/secrets/actions

Click **"New repository secret"** and add each of these:

### Secret 1: WIF_PROVIDER
```
projects/644185288504/locations/global/workloadIdentityPools/github-pool/providers/github-provider
```

### Secret 2: WIF_SERVICE_ACCOUNT
```
github-actions@parallel-universe-prod.iam.gserviceaccount.com
```

### Secret 3: REDIS_HOST
```
10.110.183.147
```

## Step 2: Add Secrets to Frontend Repo (`paralleluniverse-frontend`)

Go to: https://github.com/Rajathbharadwaj/paralleluniverse-frontend/settings/secrets/actions

Click **"New repository secret"** and add each of these:

### Secret 1: WIF_PROVIDER
```
projects/644185288504/locations/global/workloadIdentityPools/github-pool/providers/github-provider
```

### Secret 2: WIF_SERVICE_ACCOUNT
```
github-actions@parallel-universe-prod.iam.gserviceaccount.com
```

### Secret 3: CLERK_PUBLISHABLE_KEY
```
pk_test_cHJlc2VudC13YXNwLTUzLmNsZXJrLmFjY291bnRzLmRldiQ
```

### Secret 4: CLERK_SECRET_KEY
```
sk_test_NWWN1EbDckqh8N5t8ElobwoC5apBqnq7jdEsfcG68w
```

## Step 3: Update Workflow Files

You have two options:

### Option A: Update the existing WIF workflow (Recommended)

The workflow file `.github/workflows/deploy-backend-wif.yml` already uses the correct format. Just update the `env` section to reference secrets:

```yaml
env:
  PROJECT_ID: parallel-universe-prod
  REGION: us-central1
  WORKLOAD_IDENTITY_PROVIDER: ${{ secrets.WIF_PROVIDER }}
  SERVICE_ACCOUNT: ${{ secrets.WIF_SERVICE_ACCOUNT }}
```

### Option B: Replace the old workflow

Simply rename/delete the old service account key workflow and use the WIF one:

```bash
# In backend repo
cd /home/rajathdb/cua
rm .github/workflows/deploy-backend.yml
mv .github/workflows/deploy-backend-wif.yml .github/workflows/deploy-backend.yml
```

## Step 4: Test the CI/CD

After adding all secrets:

```bash
# Backend repo
cd /home/rajathdb/cua
git add .
git commit -m "Configure CI/CD with Workload Identity Federation"
git push origin main

# Frontend repo
cd /home/rajathdb/cua-frontend
git add .
git commit -m "Configure CI/CD with Workload Identity Federation"
git push origin main
```

Then check the Actions tab:
- Backend: https://github.com/Rajathbharadwaj/LangGraph-Computer-Use-Open-Source/actions
- Frontend: https://github.com/Rajathbharadwaj/paralleluniverse-frontend/actions

## What Happens on Push

### Backend (`cua` repo)
When you push to `main`:
1. GitHub Actions authenticates using Workload Identity (no keys!)
2. Deploys 3 services in parallel:
   - Main Backend API (with Redis connection)
   - Extension Backend
   - OmniParser

### Frontend (`cua-frontend` repo)
When you push to `main`:
1. GitHub Actions authenticates using Workload Identity
2. Builds Docker image with Clerk publishable key
3. Deploys to Cloud Run
4. Updates runtime environment variables with Clerk secret key

## Security Benefits

- No service account keys to manage or rotate
- Keys can't be leaked or stolen
- Authentication tokens expire automatically
- Access restricted to your GitHub repositories only
- Follows GCP best practices and org policies

## Troubleshooting

### Error: "failed to generate Google Cloud access token"
- Double-check `WIF_PROVIDER` secret matches exactly (no extra spaces)
- Verify `WIF_SERVICE_ACCOUNT` email is correct

### Error: "Permission denied"
- Service account already has all necessary IAM roles
- Check that you completed the "Grant access" step in GCP Console

### Error: "Audience validation failed"
- This shouldn't happen with the current setup
- If it does, verify the attribute condition in the provider settings

## Next Steps

Once CI/CD is working:
- Set up staging environment (optional)
- Add automated tests before deployment
- Configure deployment notifications
- Set up monitoring and alerting
