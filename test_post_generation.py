#!/usr/bin/env python3
"""
Test script to generate a new X post using the user's writing style
"""
import asyncio
from langgraph.store.postgres import PostgresStore
from psycopg_pool import ConnectionPool
from x_writing_style_learner import XWritingStyleManager
import os
from anthropic import AsyncAnthropic
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Anthropic client (using Claude)
anthropic_client = AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

# Database connection
DB_URI = os.environ.get("DATABASE_URL", "postgresql://postgres:password@localhost:5432/xgrowth")

async def test_post_generation():
    """Test generating a post in the user's style"""
    
    # Initialize store
    conn_pool = ConnectionPool(
        conninfo=DB_URI,
        min_size=1,
        max_size=10
    )
    store = PostgresStore(conn=conn_pool)
    
    # Use the actual user_id from scraping
    user_id = "user_6l78nk"  # Rajath's extension user ID
    
    print(f"🔍 Testing post generation for user: {user_id}\n")
    
    # Initialize style manager
    style_manager = XWritingStyleManager(store, user_id)
    
    # Check how many posts we have
    namespace = (user_id, "writing_samples")
    items = store.search(namespace)
    posts = [item.value for item in items]
    
    print(f"📚 Found {len(posts)} posts in the store")
    print(f"📊 Sample posts:")
    for i, post in enumerate(posts[:3]):
        content = post.get('content', '')[:80]
        engagement = post.get('engagement', {})
        print(f"   {i+1}. {content}... (👍 {engagement.get('likes', 0)})")
    print()
    
    # Analyze writing style
    print("🔍 Analyzing writing style...")
    style_profile = style_manager.analyze_writing_style()
    
    if style_profile:
        print(f"✅ Writing Style Profile:")
        print(f"   📝 Tone: {style_profile.tone}")
        print(f"   📏 Avg Post Length: {style_profile.avg_post_length} chars")
        print(f"   📏 Avg Comment Length: {style_profile.avg_comment_length} chars")
        print(f"   🔤 Vocabulary: {style_profile.vocabulary_level}")
        print(f"   #️⃣  Uses Hashtags: {style_profile.uses_hashtags}")
        print(f"   😊 Uses Emojis: {style_profile.uses_emojis}")
        print(f"   ❓ Uses Questions: {style_profile.uses_questions}")
        print(f"   📐 Sentence Structure: {style_profile.sentence_structure}")
        print()
    
    # Test 1: Generate a comment on a tech post
    print("=" * 70)
    print("TEST 1: Generate a comment on a tech post")
    print("=" * 70)
    
    tech_post = """
    Just released our new AI model with 10x faster inference!
    Built with PyTorch and optimized for edge devices.
    Check it out: https://github.com/example/model
    """
    
    print(f"📄 Original Post:\n{tech_post}\n")
    print("🤖 Generating comment in your style...\n")
    
    # Generate few-shot prompt
    prompt = style_manager.generate_few_shot_prompt(
        context=tech_post,
        content_type="comment",
        num_examples=3
    )
    
    # Call Claude to generate the comment
    response = await anthropic_client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": prompt
        }]
    )
    
    comment = response.content[0].text
    print(f"💬 Generated Comment:\n{comment}\n")
    
    # Test 2: Generate a standalone post about a topic
    print("=" * 70)
    print("TEST 2: Generate a post about a topic you care about")
    print("=" * 70)
    
    # Find topics from existing posts
    topics = set()
    for post in posts[:10]:
        content = post.get('content', '').lower()
        if 'ai' in content or 'llm' in content or 'gpt' in content:
            topics.add('AI/LLMs')
        if 'build' in content or 'ship' in content or 'launch' in content:
            topics.add('Building/Shipping')
        if 'learn' in content or 'tutorial' in content or 'guide' in content:
            topics.add('Learning/Education')
    
    print(f"📊 Detected topics from your posts: {', '.join(topics) if topics else 'General tech'}\n")
    
    # Generate a post about building something
    print("🤖 Generating a post about 'building a side project'...\n")
    
    # Generate few-shot prompt for a post
    post_context = """
    Share your thoughts on the best way to build and ship a side project quickly.
    Give practical advice on tech stack, deployment, and getting first users.
    """
    
    prompt = style_manager.generate_few_shot_prompt(
        context=post_context,
        content_type="post",
        num_examples=3
    )
    
    # Call Claude to generate the post
    response = await anthropic_client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": prompt
        }]
    )
    
    generated_post = response.content[0].text
    print(f"📝 Generated Post:\n{generated_post}\n")
    
    # Test 3: Show similar posts used for generation
    print("=" * 70)
    print("TEST 3: Similar posts used for style learning")
    print("=" * 70)
    
    # Search for posts similar to "building projects"
    similar_items = store.search(
        namespace,
        query="building side projects and shipping fast"
    )
    
    print(f"🔍 Found {len(list(similar_items))} similar posts for context\n")
    
    # Re-search to display (generator exhausted)
    similar_items = store.search(
        namespace,
        query="building side projects and shipping fast"
    )
    
    for i, item in enumerate(list(similar_items)[:3]):
        post_data = item.value
        content = post_data.get('content', '')
        engagement = post_data.get('engagement', {})
        print(f"   {i+1}. {content[:100]}...")
        print(f"      👍 {engagement.get('likes', 0)} | 💬 {engagement.get('replies', 0)} | 🔁 {engagement.get('reposts', 0)}\n")
    
    print("=" * 70)
    print("✅ Post generation test complete!")
    print("=" * 70)
    
    # Close pool
    conn_pool.close()

if __name__ == "__main__":
    asyncio.run(test_post_generation())
