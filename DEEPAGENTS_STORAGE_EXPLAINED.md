# DeepAgents Storage Architecture - Per-User File Persistence

## Summary

Action JSON files are now **properly isolated per user** and persist across all threads/conversations in PostgreSQL.

## How It Works

### 1. Storage Backends

DeepAgents supports multiple storage backends via `CompositeBackend`:

- **StateBackend** (Ephemeral): Files stored in LangGraph state, lost when thread ends
  - Used for: Temporary working files like `/workspace/draft.md`
  - Location: Thread-specific state (checkpointed)

- **StoreBackend** (Persistent): Files stored in LangGraph Store (PostgreSQL in production)
  - Used for: Long-term memory like `/memories/action_history.json`
  - Location: PostgreSQL database via `store.put(namespace, key, value)`

### 2. File Path Routing

The `CompositeBackend` routes file operations based on path prefix:

```python
def make_backend(runtime):
    return CompositeBackend(
        default=StateBackend(runtime),  # Ephemeral storage for regular files
        routes={
            "/memories/": StoreBackend(runtime)  # Persistent storage for /memories/*
        }
    )
```

**Examples:**
- `/workspace/plan.md` → StateBackend (ephemeral, lost when thread ends)
- `/memories/action_history.json` → StoreBackend (persistent, survives across threads)

### 3. Per-User Isolation via `assistant_id`

**CRITICAL:** StoreBackend uses `assistant_id` from config metadata to namespace files:

```python
# StoreBackend._get_namespace() implementation:
assistant_id = config.get("metadata", {}).get("assistant_id")
if assistant_id:
    return (assistant_id, "filesystem")  # e.g., ("user_abc123", "filesystem")
return ("filesystem",)  # SHARED ACROSS ALL USERS - BAD!
```

**Our Fix:** Pass user_id as assistant_id in config metadata:

```python
# backend_websocket_server.py:3749
config = {
    "configurable": {
        "user_id": user_id,
        "cua_url": vnc_url,
    },
    "metadata": {
        "assistant_id": user_id  # This isolates /memories/ files per user!
    }
}
```

### 4. Storage Namespacing in PostgreSQL

Files are stored in PostgreSQL with this structure:

```
Namespace: (user_id, "filesystem")
Key: "/memories/action_history.json"
Value: {"content": [...], "created_at": "...", "modified_at": "..."}
```

**Example queries:**
- User `user_123` writes to `/memories/action_history.json`:
  - Stored as: `namespace=("user_123", "filesystem")`, `key="/memories/action_history.json"`
- User `user_456` writes to `/memories/action_history.json`:
  - Stored as: `namespace=("user_456", "filesystem")`, `key="/memories/action_history.json"`

**Result:** Each user has completely isolated `/memories/` files!

## Agent Instructions

The system prompt now instructs the agent:

```
📊 MEMORY FORMAT (/memories/action_history.json):
CRITICAL: ALL action history MUST be saved to /memories/action_history.json (persistent storage)
DO NOT save to action_history.json (ephemeral - will be lost!)
```

## Scalability

✅ **Fully scalable per user:**
- Each user gets isolated `/memories/` namespace
- Files persist across all threads for that user
- Uses PostgreSQL for production-grade storage
- No file conflicts between users

## Testing

To verify isolation works:

1. User A writes to `/memories/action_history.json`
2. User B writes to `/memories/action_history.json`
3. User A reads `/memories/action_history.json` → Gets their own data (not User B's)

## Storage Location Summary

| File Path | Backend | Persistence | Isolation |
|-----------|---------|-------------|-----------|
| `/workspace/plan.md` | StateBackend | Thread-scoped (ephemeral) | Per thread |
| `/memories/action_history.json` | StoreBackend | Cross-thread (persistent) | Per user (via assistant_id) |
| `action_history.json` | StateBackend | Thread-scoped (ephemeral) | Per thread |

## Key Files Modified

1. **x_growth_deep_agent.py**:
   - Added `CompositeBackend` configuration
   - Routed `/memories/` to `StoreBackend`
   - Updated system prompt to use `/memories/action_history.json`

2. **backend_websocket_server.py**:
   - Added `metadata.assistant_id = user_id` to config
   - Ensures per-user isolation in StoreBackend

## Important Notes

⚠️ **Without `assistant_id` in metadata**: All users would share the same `/memories/` files (security issue!)

✅ **With `assistant_id` in metadata**: Each user gets isolated storage (correct!)

This architecture follows DeepAgents best practices for multi-tenant deployments.
