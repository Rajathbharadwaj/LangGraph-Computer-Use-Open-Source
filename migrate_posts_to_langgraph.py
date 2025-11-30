"""
Migrate user posts from PostgreSQL to LangGraph Store.

This fixes the issue where posts exist in PostgreSQL but not in LangGraph Store,
preventing the agent from learning the user's writing style.
"""

import asyncio
from langgraph_sdk import get_client
import os

async def migrate_posts_for_user(user_id: str, username: str):
    """
    Migrate posts from PostgreSQL to LangGraph Store for a specific user.

    Args:
        user_id: Clerk user ID
        username: X/Twitter username
    """
    print(f"\n{'='*80}")
    print(f"🔄 MIGRATING POSTS FOR @{username}")
    print(f"{'='*80}\n")

    # Get backend URL
    backend_url = "https://backend-api-bw5qfm5d5a-uc.a.run.app"

    # Step 1: Get posts from PostgreSQL via API
    import aiohttp
    async with aiohttp.ClientSession() as session:
        print(f"📡 Fetching posts from PostgreSQL...")
        async with session.get(f"{backend_url}/api/posts/count/{username}") as resp:
            count_data = await resp.json()
            post_count = count_data.get("count", 0)
            print(f"   Found {post_count} posts in PostgreSQL\n")

        if post_count == 0:
            print("❌ No posts to migrate!")
            return

        # Get actual posts (we'll need to add an endpoint for this)
        # For now, let's call the scrape endpoint with a flag to force re-import
        print(f"📥 Triggering re-import to LangGraph Store...")

        async with session.post(
            f"{backend_url}/api/migrate-posts-to-langgraph",
            json={
                "user_id": user_id,
                "username": username
            }
        ) as resp:
            result = await resp.json()

            if result.get("success"):
                print(f"\n✅ Migration complete!")
                print(f"   Migrated: {result.get('migrated_count', 0)} posts")
                print(f"   Skipped: {result.get('skipped_count', 0)} duplicates")
            else:
                print(f"\n❌ Migration failed: {result.get('error')}")

    # Step 2: Verify in LangGraph Store
    print(f"\n📊 Verifying in LangGraph Store...")
    client = get_client(url="https://langgraph-service-644185288504.us-central1.run.app")

    namespace = [user_id, "writing_samples"]
    items = await client.store.search_items(namespace, query="", limit=5)
    items_list = [item async for item in items]

    if items_list:
        print(f"✅ Verified: {len(items_list)}+ writing samples in LangGraph Store")
        print(f"\nFirst 3 samples:")
        for i, item in enumerate(items_list[:3], 1):
            content = item.value.get('content', '')[:80]
            print(f"{i}. {content}...")
    else:
        print(f"❌ Still no samples in LangGraph Store - migration may have failed")


if __name__ == "__main__":
    # Migrate for Rajath_DB
    asyncio.run(migrate_posts_for_user(
        user_id="user_35sAy5DRwouHPOUOk3okhywCGXN",
        username="Rajath_DB"
    ))
