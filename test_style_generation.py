#!/usr/bin/env python3
"""
Test the integrated generate_content() method in XWritingStyleManager
"""
import asyncio
from langgraph.store.postgres import PostgresStore
from psycopg_pool import ConnectionPool
from x_writing_style_learner import XWritingStyleManager
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database connection
DB_URI = os.environ.get("DATABASE_URL", "postgresql://postgres:password@localhost:5432/xgrowth")


async def main():
    """Test generating styled content"""
    
    # Initialize store
    conn_pool = ConnectionPool(
        conninfo=DB_URI,
        min_size=1,
        max_size=10
    )
    store = PostgresStore(conn=conn_pool)
    
    # Initialize style manager
    user_id = "user_6l78nk"  # Rajath's extension user ID
    style_manager = XWritingStyleManager(store, user_id)
    
    print("=" * 70)
    print("TEST 1: Generate a comment (NO hashtags)")
    print("=" * 70)
    
    tech_post = """
    Just released our new AI model with 10x faster inference!
    Built with PyTorch and optimized for edge devices.
    Check it out: https://github.com/example/model
    """
    
    print(f"📄 Original Post: {tech_post.strip()}\n")
    print("🤖 Generating comment...\n")
    
    comment = await style_manager.generate_content(
        context=tech_post,
        content_type="comment"
    )
    
    print(f"💬 Generated Comment:")
    print(f"   {comment.content}")
    if comment.mentions:
        print(f"   Mentions: {', '.join('@' + m for m in comment.mentions)}")
    print()
    
    print("=" * 70)
    print("TEST 2: Generate a post about building (NO hashtags)")
    print("=" * 70)
    
    post_context = """
    Share your thoughts on the best way to build and ship a side project quickly.
    Give practical advice on tech stack, deployment, and getting first users.
    """
    
    print(f"📝 Context: {post_context.strip()}\n")
    print("🤖 Generating post...\n")
    
    post = await style_manager.generate_content(
        context=post_context,
        content_type="post"
    )
    
    print(f"📝 Generated Post:")
    print(f"   {post.content}")
    print()
    
    print("=" * 70)
    print("✅ Test complete!")
    print("=" * 70)
    
    # Close pool
    conn_pool.close()


if __name__ == "__main__":
    asyncio.run(main())


