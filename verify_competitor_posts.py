"""
Verification script to check competitor posts with engagement metrics in LangGraph Store.
Run this on the production environment to verify the competitor learning implementation.
"""
import asyncio
from langgraph.store.postgres import PostgresStore
import os

async def verify_competitor_posts():
    """Check if competitor posts with engagement metrics exist in the store."""

    # Get connection string from environment
    conn_string = os.environ.get(
        "POSTGRES_URI",
        "postgresql://deepagent:BfG44RmMgxCCVm0Pbn5g@10.97.0.3:5432/deepagent_db"
    )

    user_id = "user_01JD06JPW07W5AVKAJWZS0RQJZ"

    with PostgresStore.from_conn_string(conn_string) as store:
        namespace = (user_id, "competitor_profiles")

        print("🔍 Checking competitor posts with engagement metrics...\n")

        # Get all competitors
        competitors = list(store.search(namespace, limit=100))

        print(f"Total competitors found: {len(competitors)}\n")

        total_posts = 0
        high_performing_posts = 0

        for i, comp_item in enumerate(competitors, 1):
            comp_data = comp_item.value
            username = comp_data.get("username", "unknown")
            posts = comp_data.get("posts", [])

            print(f"{i}. @{username}")
            print(f"   Total posts: {len(posts)}")

            if posts:
                # Count posts with engagement metrics
                posts_with_likes = [p for p in posts if p.get("likes", 0) > 0]
                high_perf = [p for p in posts if p.get("likes", 0) >= 100]

                print(f"   Posts with likes: {len(posts_with_likes)}")
                print(f"   High-performing posts (≥100 likes): {len(high_perf)}")

                if high_perf:
                    # Show sample
                    sample = high_perf[0]
                    print(f"   Sample high-performing post:")
                    print(f"     Likes: {sample.get('likes', 0)}, Retweets: {sample.get('retweets', 0)}, Replies: {sample.get('replies', 0)}")
                    text = sample.get("text", "")
                    print(f"     Text: {text[:100]}..." if len(text) > 100 else f"     Text: {text}")

                total_posts += len(posts)
                high_performing_posts += len(high_perf)

            print()

        print(f"📊 Summary:")
        print(f"Total posts across all competitors: {total_posts}")
        print(f"High-performing posts (≥100 likes): {high_performing_posts}")

        if high_performing_posts > 0:
            print(f"\n✅ SUCCESS: Competitor posts with engagement metrics are available!")
            print(f"   The agent can now learn from {high_performing_posts} high-performing posts.")
        else:
            print(f"\n⚠️  WARNING: No high-performing posts found.")
            print(f"   Total posts found: {total_posts}")
            if total_posts > 0:
                print(f"   Posts exist but may not have engagement metrics.")

if __name__ == "__main__":
    asyncio.run(verify_competitor_posts())
