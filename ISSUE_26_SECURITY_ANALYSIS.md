# Issue #26: AI Content Generation Multi-Tenancy Security Vulnerabilities

## Executive Summary

**CRITICAL SECURITY ISSUE FOUND**: The UPDATE and DELETE endpoints for scheduled posts do not verify user ownership, allowing any authenticated user to modify or delete another user's posts by guessing post IDs.

## Affected Endpoints

### VULNERABLE:
1. **PUT `/api/scheduled-posts/{post_id}`** (backend_websocket_server.py:3635-3728)
   - Does NOT verify post belongs to requesting user
   - Only checks if post_id exists

2. **DELETE `/api/scheduled-posts/{post_id}`** (backend_websocket_server.py:3730-3758)
   - Does NOT verify post belongs to requesting user
   - Only checks if post_id exists

### SECURE (Already Implemented Correctly):
1. ✅ **GET `/api/scheduled-posts`** (line 3528)
   - Filters by `user_id` parameter
   - Returns only user's own posts

2. ✅ **POST `/api/scheduled-posts`** (line 3586)
   - Uses `user_id` from request body
   - Creates post under user's X account

3. ✅ **POST `/api/scheduled-posts/generate-ai`** (line 3800)
   - Requires `user_id` parameter
   - Generates content for specific user

4. ✅ **GET `/api/scheduled-posts/ai-drafts`** (line 4143)
   - Filters by `user_id` parameter
   - Returns only user's AI drafts

## Vulnerability Details

### Current Vulnerable Code (UPDATE):

```python
# backend_websocket_server.py:3643-3646
post = db.query(ScheduledPost).filter(ScheduledPost.id == post_id).first()

if not post:
    raise HTTPException(status_code=404, detail="Post not found")

# ❌ NO USER OWNERSHIP CHECK!
# Proceeds to update the post regardless of who owns it
```

### Current Vulnerable Code (DELETE):

```python
# backend_websocket_server.py:3737-3740
post = db.query(ScheduledPost).filter(ScheduledPost.id == post_id).first()

if not post:
    raise HTTPException(status_code=404, detail="Post not found")

# ❌ NO USER OWNERSHIP CHECK!
# Proceeds to delete the post regardless of who owns it
```

## Attack Scenario

**Attacker**: User A (Clerk ID: `user_attacker123`)
**Victim**: User B (Clerk ID: `user_victim456`)

1. User B creates scheduled post with ID `123`
2. User A discovers post ID `123` (by guessing or observing network traffic)
3. User A sends: `PUT /api/scheduled-posts/123` with malicious content
4. **RESULT**: User A successfully modifies User B's post
5. OR User A sends: `DELETE /api/scheduled-posts/123`
6. **RESULT**: User A successfully deletes User B's post

## Root Cause Analysis

### Backend Issue:
- UPDATE and DELETE endpoints accept only `post_id` as parameter
- No `user_id` parameter required
- No verification that the post's `x_account.user_id` matches the requesting user

### Frontend Issue:
- `updateScheduledPost()` in `/home/rajathdb/cua-frontend/lib/api/scheduled-posts.ts:91`
  - Does NOT pass `user_id`
  - Only sends: `{ content, media_urls, scheduled_at, status }`

- `deleteScheduledPost()` in `/home/rajathdb/cua-frontend/lib/api/scheduled-posts.ts:114`
  - Does NOT pass `user_id`
  - No body parameters at all

## Required Fix

### Backend Changes:

**1. Update Endpoint** (backend_websocket_server.py:3635)

```python
@app.put("/api/scheduled-posts/{post_id}")
async def update_scheduled_post(
    post_id: int,
    request: UpdateScheduledPostRequest,
    user_id: str,  # ADD THIS PARAMETER
    db: Session = Depends(get_db)
):
    """Update an existing scheduled post"""
    try:
        # SECURITY: Verify post belongs to user
        post = (
            db.query(ScheduledPost)
            .join(XAccount, ScheduledPost.x_account_id == XAccount.id)
            .filter(
                ScheduledPost.id == post_id,
                XAccount.user_id == user_id  # SECURITY CHECK
            )
            .first()
        )

        if not post:
            raise HTTPException(
                status_code=404,
                detail="Post not found or access denied"
            )

        # ... rest of update logic
```

**2. Delete Endpoint** (backend_websocket_server.py:3730)

```python
@app.delete("/api/scheduled-posts/{post_id}")
async def delete_scheduled_post(
    post_id: int,
    user_id: str,  # ADD THIS PARAMETER
    db: Session = Depends(get_db)
):
    """Delete a scheduled post"""
    try:
        # SECURITY: Verify post belongs to user
        post = (
            db.query(ScheduledPost)
            .join(XAccount, ScheduledPost.x_account_id == XAccount.id)
            .filter(
                ScheduledPost.id == post_id,
                XAccount.user_id == user_id  # SECURITY CHECK
            )
            .first()
        )

        if not post:
            raise HTTPException(
                status_code=404,
                detail="Post not found or access denied"
            )

        # ... rest of delete logic
```

### Frontend Changes:

**1. Update API Client** (/home/rajathdb/cua-frontend/lib/api/scheduled-posts.ts)

```typescript
// Line 91: Update function signature
export async function updateScheduledPost(
  postId: number,
  userId: string,  // ADD THIS PARAMETER
  updateData: UpdatePostData
): Promise<ScheduledPost> {
  const params = new URLSearchParams({ user_id: userId });  // ADD THIS

  const response = await fetch(
    `${API_BASE_URL}/api/scheduled-posts/${postId}?${params}`,  // ADD QUERY PARAMS
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updateData),
    }
  );
  // ... rest
}

// Line 114: Update delete function
export async function deleteScheduledPost(
  postId: number,
  userId: string  // ADD THIS PARAMETER
): Promise<void> {
  const params = new URLSearchParams({ user_id: userId });  // ADD THIS

  const response = await fetch(
    `${API_BASE_URL}/api/scheduled-posts/${postId}?${params}`,  // ADD QUERY PARAMS
    {
      method: "DELETE",
    }
  );
  // ... rest
}
```

**2. Update Frontend Components** (need to search for all usages)

All components calling `updateScheduledPost()` or `deleteScheduledPost()` must pass `userId`:

```typescript
// Example usage in ai-content-tab.tsx
const handleApprove = async (postId: number) => {
  if (!userId) return;

  await updateScheduledPost(
    postId,
    userId,  // ADD THIS
    { status: "scheduled" }
  );
};

const handleDelete = async (postId: number) => {
  if (!userId) return;

  await deleteScheduledPost(postId, userId);  // ADD userId
};
```

## Testing Plan

### Test 1: Verify UPDATE Security
1. User A creates post with ID `123`
2. User B attempts: `PUT /api/scheduled-posts/123?user_id=user_B_id`
3. **Expected**: 404 "Post not found or access denied"
4. **NOT**: Successful update

### Test 2: Verify DELETE Security
1. User A creates post with ID `456`
2. User B attempts: `DELETE /api/scheduled-posts/456?user_id=user_B_id`
3. **Expected**: 404 "Post not found or access denied"
4. **NOT**: Successful deletion

### Test 3: Verify Legitimate Operations Still Work
1. User A creates post with ID `789`
2. User A updates: `PUT /api/scheduled-posts/789?user_id=user_A_id`
3. **Expected**: ✅ Successful update
4. User A deletes: `DELETE /api/scheduled-posts/789?user_id=user_A_id`
5. **Expected**: ✅ Successful deletion

## Files to Modify

| File | Lines | Change | Priority |
|------|-------|--------|----------|
| `/home/rajathdb/cua/backend_websocket_server.py` | 3635-3728 | Add user_id parameter and ownership check to UPDATE | P0 |
| `/home/rajathdb/cua/backend_websocket_server.py` | 3730-3758 | Add user_id parameter and ownership check to DELETE | P0 |
| `/home/rajathdb/cua-frontend/lib/api/scheduled-posts.ts` | 91-108 | Add userId parameter to updateScheduledPost() | P0 |
| `/home/rajathdb/cua-frontend/lib/api/scheduled-posts.ts` | 114-122 | Add userId parameter to deleteScheduledPost() | P0 |
| All frontend components using these functions | Various | Pass userId to update/delete calls | P0 |

## Impact Assessment

**Before Fix**:
- ❌ Any user can modify any post by guessing post IDs
- ❌ Any user can delete any post by guessing post IDs
- ❌ No audit trail of unauthorized access attempts
- ❌ Complete multi-tenancy failure for scheduled posts

**After Fix**:
- ✅ Users can only modify their own posts
- ✅ Users can only delete their own posts
- ✅ 404 error logged for unauthorized access attempts
- ✅ Full multi-tenancy isolation for all scheduled post operations

## Severity: CRITICAL

**CVSS Score**: 8.1 (High)
- **Impact**: High (data integrity, unauthorized modification/deletion)
- **Exploitability**: Medium (requires guessing post IDs, but sequential IDs are common)
- **Scope**: Changed (affects multiple users)

## Recommendation

**IMMEDIATE ACTION REQUIRED**:
1. Implement backend user_id verification for UPDATE and DELETE endpoints
2. Update frontend to pass userId to these endpoints
3. Deploy fixes to production immediately
4. Audit logs for any suspicious post modifications/deletions
5. Consider implementing database audit triggers for scheduled_posts table

---

**Created**: 2025-12-06
**Issue**: #26
**Status**: ❌ VULNERABLE - Fix Required
**Priority**: P0 - Critical Security Issue
