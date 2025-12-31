---
name: run-migration
description: Run database migrations against Cloud SQL. Use when adding new tables, columns, or schema changes. Triggers on "migration", "database schema", "add table", "add column", "run migration".
allowed-tools: Read, Write, Bash(gcloud:*), Bash(python:*), Bash(./deploy*.sh:*)
---

# Database Migration Guide

## Overview

This project uses Cloud SQL (PostgreSQL 15) with a private IP (`10.97.0.3`). Migrations are run via **Cloud Run Jobs** because:
- Cloud SQL only has private IP (no public access)
- Cloud Run Jobs can access the VPC via connector
- Jobs are one-off executions, perfect for migrations

## Quick Start

### 1. Create Migration File

Create a Python migration in `migrations/`:

```python
# migrations/run_my_migration.py
import os
import sys
from urllib.parse import quote
from sqlalchemy import create_engine, text

def run_migration():
    database_url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URI")

    # Support building URL from components (for Cloud Run Jobs)
    if not database_url:
        db_password = os.environ.get("DB_PASSWORD")
        db_host = os.environ.get("POSTGRES_HOST", "10.97.0.3")
        db_user = os.environ.get("POSTGRES_USER", "postgres")
        db_name = os.environ.get("POSTGRES_DB", "parallel_universe_db")

        if db_password:
            encoded_password = quote(db_password, safe='')
            database_url = f"postgresql://{db_user}:{encoded_password}@{db_host}:5432/{db_name}"
        else:
            print("ERROR: No database credentials available")
            sys.exit(1)

    # Ensure sync driver
    if "+asyncpg" in database_url:
        database_url = database_url.replace("+asyncpg", "")

    engine = create_engine(database_url)

    migrations = [
        """
        CREATE TABLE IF NOT EXISTS my_table (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255)
        );
        """,
    ]

    with engine.connect() as conn:
        for i, migration in enumerate(migrations, 1):
            try:
                print(f"Running migration {i}/{len(migrations)}...")
                conn.execute(text(migration))
                conn.commit()
                print(f"  ✓ Migration {i} complete")
            except Exception as e:
                if "already exists" in str(e):
                    print(f"  ✓ Migration {i} skipped (already exists)")
                else:
                    print(f"  ✗ Migration {i} error: {e}")
                conn.rollback()

if __name__ == "__main__":
    run_migration()
```

### 2. Deploy Backend (Include Migration File)

The migration file must be in the Docker image:

```bash
./deploy_cloudrun.sh
```

Wait for deployment to complete successfully.

### 3. Create/Update Cloud Run Job

```bash
# Get the latest backend image
BACKEND_IMAGE=$(gcloud run services describe backend-api \
  --region=us-central1 \
  --project=parallel-universe-prod \
  --format="value(spec.template.spec.containers[0].image)")

# Create job (first time only)
gcloud run jobs create my-migration \
  --image="$BACKEND_IMAGE" \
  --region=us-central1 \
  --project=parallel-universe-prod \
  --vpc-connector=paralleluniverse-vpc \
  --vpc-egress=all-traffic \
  --set-env-vars="DATABASE_URL=postgresql://postgres:ParallelUniverse2024!@10.97.0.3:5432/parallel_universe_db" \
  --command="python" \
  --args="migrations/run_my_migration.py" \
  --max-retries=0 \
  --task-timeout=300s \
  --memory=512Mi

# Or update existing job with new image
gcloud run jobs update my-migration \
  --image="$BACKEND_IMAGE" \
  --region=us-central1 \
  --project=parallel-universe-prod
```

### 4. Execute Migration

```bash
gcloud run jobs execute my-migration \
  --region=us-central1 \
  --project=parallel-universe-prod \
  --wait
```

### 5. Verify

```bash
# Check logs
gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=my-migration" \
  --project=parallel-universe-prod \
  --limit=30 \
  --format='value(textPayload)'
```

## Database Connection Details

| Setting | Value |
|---------|-------|
| Host | `10.97.0.3` (private IP) |
| Port | `5432` |
| Database | `parallel_universe_db` |
| User | `postgres` |
| Password | `ParallelUniverse2024!` |
| VPC Connector | `paralleluniverse-vpc` |

## Common Issues

### "Password authentication failed"

The password might have special characters. URL-encode it:

```python
from urllib.parse import quote
encoded = quote("password!", safe='')
```

### "Connection refused" / "Socket error"

1. Check VPC connector is set: `--vpc-connector=paralleluniverse-vpc`
2. Check egress: `--vpc-egress=all-traffic`
3. Verify private IP is correct: `10.97.0.3`

### "No such file"

The migration file isn't in the Docker image. Redeploy backend first:

```bash
./deploy_cloudrun.sh
```

Then update the job with the new image.

### Job Fails Silently

Check logs:

```bash
gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=JOB_NAME" \
  --project=parallel-universe-prod \
  --limit=50
```

## Existing Migrations

| Migration | Purpose |
|-----------|---------|
| `run_migration.py` | Stripe billing tables |
| `add_style_learning_tables.sql` | Style learning feature |
| `add_work_integrations_tables.sql` | Work integrations (GitHub, Slack, etc.) |

## Best Practices

1. **Use `IF NOT EXISTS`** - Makes migrations idempotent
2. **Test locally first** - Use local postgres on port 5433
3. **Backup before major changes** - `gcloud sql backups create`
4. **One migration per feature** - Keep migrations focused
5. **Include rollback SQL** - Document how to undo changes

## Cloud SQL Instance

```bash
# View instance
gcloud sql instances describe parallel-universe-db --project=parallel-universe-prod

# Connect via Cloud SQL Proxy (for local debugging)
cloud-sql-proxy parallel-universe-prod:us-central1:parallel-universe-db --port=5434

# List databases
gcloud sql databases list --instance=parallel-universe-db --project=parallel-universe-prod
```
