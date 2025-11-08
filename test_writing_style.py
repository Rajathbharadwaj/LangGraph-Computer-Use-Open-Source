"""
Test Writing Style Learning System

This script demonstrates how the writing style learning system works.
"""

import os
from x_writing_style_learner import XWritingStyleManager, WritingSample
from langgraph.store.memory import InMemoryStore
from langchain.embeddings import init_embeddings


def test_writing_style_system():
    """Test the complete writing style learning flow"""
    
    print("=" * 80)
    print("🎨 TESTING WRITING STYLE LEARNING SYSTEM")
    print("=" * 80)
    
    # Check API key
    if not os.environ.get("OPENAI_API_KEY"):
        print("❌ OPENAI_API_KEY not set (needed for embeddings)")
        print("   Set it with: export OPENAI_API_KEY='your-key'")
        return
    
    try:
        # 1. Create store with semantic search
        print("\n1️⃣ Creating store with semantic search...")
        embeddings = init_embeddings("openai:text-embedding-3-small")
        store = InMemoryStore(
            index={
                "embed": embeddings,
                "dims": 1536,
            }
        )
        print("   ✅ Store created with embeddings")
        
        # 2. Initialize style manager
        print("\n2️⃣ Initializing style manager...")
        user_id = "test_user_123"
        style_manager = XWritingStyleManager(store, user_id)
        print(f"   ✅ Style manager ready for user: {user_id}")
        
        # 3. Import sample posts
        print("\n3️⃣ Importing user's past posts...")
        past_posts = [
            {
                "content": "Interesting pattern I've noticed with LangGraph subagents: context isolation really helps with token efficiency. Anyone else seeing this?",
                "timestamp": "2025-10-15T10:30:00",
                "engagement": {"likes": 15, "replies": 5, "reposts": 2},
                "topic": "LangGraph"
            },
            {
                "content": "Just shipped a new feature using DeepAgents. The built-in planning tool is a game-changer for complex workflows.",
                "timestamp": "2025-10-20T14:00:00",
                "engagement": {"likes": 23, "replies": 8, "reposts": 4},
                "topic": "DeepAgents"
            },
            {
                "content": "Quick tip: If your agent is making too many tool calls, try delegating to subagents. Keeps the main agent focused.",
                "timestamp": "2025-10-25T09:15:00",
                "engagement": {"likes": 31, "replies": 12, "reposts": 6},
                "topic": "AI agents"
            },
            {
                "content": "Have you experimented with different context isolation strategies? I've found that namespace-based organization works really well.",
                "timestamp": "2025-10-28T11:00:00",
                "engagement": {"likes": 18, "replies": 7, "reposts": 3},
                "topic": "LangGraph"
            },
            {
                "content": "In my experience, the key is keeping the main agent focused on high-level coordination. What's your current architecture look like?",
                "timestamp": "2025-10-30T15:45:00",
                "engagement": {"likes": 27, "replies": 11, "reposts": 5},
                "topic": "Architecture"
            },
        ]
        
        style_manager.bulk_import_posts(past_posts)
        print(f"   ✅ Imported {len(past_posts)} posts")
        
        # 4. Analyze writing style
        print("\n4️⃣ Analyzing writing style...")
        profile = style_manager.analyze_writing_style()
        print(f"   📊 Writing Style Profile:")
        print(f"      - Tone: {profile.tone}")
        print(f"      - Avg post length: {profile.avg_post_length} chars")
        print(f"      - Avg comment length: {profile.avg_comment_length} chars")
        print(f"      - Uses emojis: {profile.uses_emojis}")
        print(f"      - Uses questions: {profile.uses_questions}")
        print(f"      - Sentence structure: {profile.sentence_structure}")
        print(f"      - Technical terms: {', '.join(profile.technical_terms[:5])}")
        
        # 5. Test semantic search
        print("\n5️⃣ Testing semantic search for similar examples...")
        context = "Someone posted: 'How do you handle agent context management?'"
        similar = style_manager.get_similar_examples(context, limit=3)
        
        print(f"   🔍 Query: {context}")
        print(f"   📝 Found {len(similar)} similar examples:")
        for i, example in enumerate(similar, 1):
            print(f"\n      Example {i}:")
            print(f"      {example.content[:100]}...")
            print(f"      Engagement: {sum(example.engagement.values())} total")
        
        # 6. Get high-engagement examples
        print("\n6️⃣ Finding high-engagement examples...")
        high_engagement = style_manager.get_high_engagement_examples(
            content_type="post",
            min_engagement=20,
            limit=3
        )
        
        print(f"   🔥 Found {len(high_engagement)} high-engagement posts:")
        for i, example in enumerate(high_engagement, 1):
            total = sum(example.engagement.values())
            print(f"\n      {i}. ({total} engagement)")
            print(f"      {example.content[:100]}...")
        
        # 7. Generate few-shot prompt
        print("\n7️⃣ Generating few-shot prompt...")
        prompt = style_manager.generate_few_shot_prompt(
            context="Someone posted: 'Struggling with LangGraph memory management. Any tips?'",
            content_type="comment",
            num_examples=3
        )
        
        print("   📝 Generated Few-Shot Prompt:")
        print("   " + "-" * 76)
        # Print first 800 chars
        prompt_preview = prompt[:800] + "\n   [...]\n   " + prompt[-200:]
        for line in prompt_preview.split("\n"):
            print(f"   {line}")
        print("   " + "-" * 76)
        
        # 8. Summary
        print("\n" + "=" * 80)
        print("✅ WRITING STYLE LEARNING SYSTEM WORKING!")
        print("=" * 80)
        print("\n🎯 What we demonstrated:")
        print("   ✅ Store user's past posts with embeddings")
        print("   ✅ Analyze writing style (tone, length, vocabulary)")
        print("   ✅ Semantic search for similar examples")
        print("   ✅ Find high-engagement content")
        print("   ✅ Generate few-shot prompts for style matching")
        print("\n🚀 Next steps:")
        print("   1. Integrate with comment_generator subagent")
        print("   2. Fetch real user posts via X API")
        print("   3. Generate comments in user's style")
        print("   4. Track engagement and improve over time")
        print("\n📖 See WRITING_STYLE_GUIDE.md for full documentation")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_writing_style_system()

