---
name: database-schema
description: Modify database models and handle migrations. Use when adding tables, columns, relationships, or changing the SQLAlchemy schema. Triggers on "add column", "new table", "database migration", "model change", "schema".
allowed-tools: Read, Edit, Grep, Glob
---

# Database Schema Guide

## Models Location

`database/models.py` (1026 lines)

## Key Model Categories

### User Management
- `User` - Clerk user mapping
- `XAccount` - X/Twitter account details
- `XCookies` - Encrypted session cookies

### Content & Analytics
- `UserPost` - Posts created (with `source`: 'agent' or 'imported')
- `UserComment` - Comments made on others' posts
- `ReceivedComment` - Comments received on own posts
- `ScheduledPost` - Future scheduled content

### Automation
- `CronJob` - Recurring automation jobs
- `CronJobRun` - Execution history
- `WorkflowExecution` - Workflow run tracking

### Billing
- `Subscription` - User subscription status
- `CreditBalance` - Monthly credit allocation
- `CreditTransaction` - Credit usage audit log
- `FeatureUsage` - API consumption tracking

### Ads Platform
- `AdsPlatform` - Platform credentials (Meta, Google)
- `AdsCampaign` - Campaign configurations
- `AdsMetrics` - Performance data

### CRM
- `Customer` - Customer lifecycle tracking
- `Conversation` - Multi-channel messaging
- `AutomatedFollowup` - Scheduled follow-ups

## Migration Pattern

This project uses **inline migrations** in the backend startup. Add migrations to the `lifespan()` function in `backend_websocket_server.py`:

```python
async with engine.begin() as conn:
    # Add new column
    await conn.execute(text("""
        ALTER TABLE table_name
        ADD COLUMN IF NOT EXISTS column_name VARCHAR(255) DEFAULT 'value'
    """))

    # Create new table
    await conn.execute(text("""
        CREATE TABLE IF NOT EXISTS new_table (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))

    # Add index
    await conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_table_column
        ON table_name(column_name)
    """))
```

## Adding a New Model

### Step 1: Define in `database/models.py`

```python
class NewModel(Base):
    __tablename__ = "new_models"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="new_models")
```

### Step 2: Add Relationship to Parent

```python
class User(Base):
    # ... existing fields
    new_models = relationship("NewModel", back_populates="user", cascade="all, delete-orphan")
```

### Step 3: Add Migration in `lifespan()`

```python
await conn.execute(text("""
    CREATE TABLE IF NOT EXISTS new_models (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        name VARCHAR(255) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
"""))
```

## Common Column Types

| Python Type | PostgreSQL | Example |
|-------------|------------|---------|
| `String(255)` | VARCHAR(255) | Names, short text |
| `Text` | TEXT | Long content |
| `Integer` | INTEGER | Counts, IDs |
| `Boolean` | BOOLEAN | Flags |
| `DateTime` | TIMESTAMP | Timestamps |
| `JSON` | JSONB | Flexible data |
| `Float` | REAL | Metrics |

## Best Practices

1. **Always use `IF NOT EXISTS`** for migrations
2. **Add `ondelete="CASCADE"`** for foreign keys
3. **Index frequently queried columns**
4. **Use `nullable=False`** unless truly optional
5. **Add `created_at` and `updated_at`** to all models
6. **Encrypt sensitive data** using `services/cookie_encryption.py`
