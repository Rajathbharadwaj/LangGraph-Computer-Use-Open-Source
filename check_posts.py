#!/usr/bin/env python3
"""
Check what posts are stored in LangGraph store for different user IDs
"""
import os
from langgraph.store.postgres import PostgresStore

# User IDs from the extension status
RAJATH_CLERK_ID = "user_35sAy5DRwouHPOUOk3okhywCGXN"  # Your Clerk ID
CHICAGO_CLERK_ID = "user_35uW9PgcmBgN1szXvwzxN4MxcIm"  # chicagotechclab's Clerk ID

def check_posts_for_user(store, user_id, username):
    """Check what posts are stored for a user"""
    print(f"\n{'='*80}")
    print(f"Checking posts for {username} (user_id: {user_id})")
    print(f"{'='*80}")

    namespace = (user_id, "writing_samples")
    posts = list(store.search(namespace, limit=100))

    print(f"📦 Found {len(posts)} posts")

    if posts:
        # Show first 5 posts
        print(f"\n📝 Sample posts (first 5):")
        for i, post in enumerate(posts[:5], 1):
            content = post.value.get("content", "")[:150]
            user_id_in_post = post.value.get("user_id")
            timestamp = post.value.get("timestamp")
            print(f"\n{i}. [{timestamp}]")
            print(f"   user_id in post: {user_id_in_post}")
            print(f"   Content: {content}...")

    return len(posts)

def main():
    # Get database connection string
    conn_string = (
        os.environ.get("POSTGRES_URI") or
        os.environ.get("DATABASE_URL") or
        "postgresql://postgres:password@localhost:5433/xgrowth"
    )

    print(f"🔗 Connecting to database...")
    print(f"   Connection: {conn_string.split('@')[1] if '@' in conn_string else 'local'}")

    with PostgresStore.from_conn_string(conn_string) as store:
        # Check both user IDs
        rajath_count = check_posts_for_user(store, RAJATH_CLERK_ID, "Rajath_DB")
        chicago_count = check_posts_for_user(store, CHICAGO_CLERK_ID, "chicagotechclab")

        # Summary
        print(f"\n{'='*80}")
        print(f"SUMMARY")
        print(f"{'='*80}")
        print(f"Rajath_DB ({RAJATH_CLERK_ID}): {rajath_count} posts")
        print(f"chicagotechclab ({CHICAGO_CLERK_ID}): {chicago_count} posts")
        print(f"{'='*80}\n")

if __name__ == "__main__":
    main()
