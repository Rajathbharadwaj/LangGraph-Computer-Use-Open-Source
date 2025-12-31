---
name: api-endpoint
description: Create FastAPI endpoints in the backend. Use when adding new API routes, modifying existing endpoints, or building new features. Triggers on "add endpoint", "create API", "new route", "backend route".
allowed-tools: Read, Edit, Grep, Glob
---

# API Endpoint Development

## Main Backend File

`backend_websocket_server.py` - 60+ routes, main FastAPI application

## Authentication Pattern

All authenticated endpoints use Clerk JWT verification:

```python
from clerk_auth import get_current_user

@app.post("/api/your-endpoint")
async def your_endpoint(
    request: YourRequest,
    user_id: str = Depends(get_current_user)
):
    async with async_session() as db:
        # Your logic here
        return {"success": True, "data": result}
```

## Request/Response Models

Define Pydantic models for type safety:

```python
from pydantic import BaseModel
from typing import Optional, List

class YourRequest(BaseModel):
    name: str
    optional_field: Optional[str] = None
    items: List[str] = []

class YourResponse(BaseModel):
    success: bool
    data: dict
    message: Optional[str] = None
```

## Database Access Pattern

```python
@app.get("/api/items")
async def get_items(user_id: str = Depends(get_current_user)):
    async with async_session() as db:
        # Query with user isolation
        result = await db.execute(
            select(Item).where(Item.user_id == user_id)
        )
        items = result.scalars().all()

        return {
            "items": [item.to_dict() for item in items]
        }
```

## CRUD Endpoint Template

```python
# CREATE
@app.post("/api/items")
async def create_item(
    request: CreateItemRequest,
    user_id: str = Depends(get_current_user)
):
    async with async_session() as db:
        item = Item(user_id=user_id, **request.dict())
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return {"success": True, "item": item.to_dict()}

# READ (list)
@app.get("/api/items")
async def list_items(user_id: str = Depends(get_current_user)):
    async with async_session() as db:
        result = await db.execute(
            select(Item).where(Item.user_id == user_id)
        )
        return {"items": [i.to_dict() for i in result.scalars().all()]}

# READ (single)
@app.get("/api/items/{item_id}")
async def get_item(
    item_id: int,
    user_id: str = Depends(get_current_user)
):
    async with async_session() as db:
        item = await db.get(Item, item_id)
        if not item or item.user_id != user_id:
            raise HTTPException(status_code=404, detail="Item not found")
        return {"item": item.to_dict()}

# UPDATE
@app.put("/api/items/{item_id}")
async def update_item(
    item_id: int,
    request: UpdateItemRequest,
    user_id: str = Depends(get_current_user)
):
    async with async_session() as db:
        item = await db.get(Item, item_id)
        if not item or item.user_id != user_id:
            raise HTTPException(status_code=404, detail="Item not found")

        for key, value in request.dict(exclude_unset=True).items():
            setattr(item, key, value)

        await db.commit()
        return {"success": True, "item": item.to_dict()}

# DELETE
@app.delete("/api/items/{item_id}")
async def delete_item(
    item_id: int,
    user_id: str = Depends(get_current_user)
):
    async with async_session() as db:
        item = await db.get(Item, item_id)
        if not item or item.user_id != user_id:
            raise HTTPException(status_code=404, detail="Item not found")

        await db.delete(item)
        await db.commit()
        return {"success": True}
```

## Frontend Proxy Integration

If the endpoint needs to be accessible from the frontend, add to `cua-frontend/middleware.ts`:

```typescript
// In the proxy configuration
if (pathname.startsWith('/api/your-endpoint')) {
  // Will be proxied to backend
}
```

And create the API function in `cua-frontend/lib/api/`:

```typescript
export async function yourEndpoint(token: string, data: YourData) {
  const response = await fetch(`${API_BASE_URL}/api/your-endpoint`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(data),
  });
  return response.json();
}
```

## Error Handling

```python
from fastapi import HTTPException

# Not found
raise HTTPException(status_code=404, detail="Resource not found")

# Bad request
raise HTTPException(status_code=400, detail="Invalid input")

# Unauthorized
raise HTTPException(status_code=401, detail="Not authenticated")

# Forbidden
raise HTTPException(status_code=403, detail="Not authorized")

# Server error
raise HTTPException(status_code=500, detail="Internal error")
```

## Best Practices

1. **Always authenticate** with `Depends(get_current_user)`
2. **Isolate by user_id** - never expose other users' data
3. **Use async/await** consistently
4. **Validate input** with Pydantic models
5. **Return consistent response format** `{"success": bool, "data": ...}`
6. **Log important actions** for debugging
7. **Handle errors gracefully** with proper HTTP status codes
