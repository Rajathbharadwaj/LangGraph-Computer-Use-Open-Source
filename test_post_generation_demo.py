#!/usr/bin/env python3
"""
Test Post Generation in User's Style - Demo Version

This script demonstrates style-aware post generation.
Replace SAMPLE_POSTS with your actual scraped posts.
"""

import asyncio
import os
from anthropic import Anthropic

# SAMPLE POSTS - Replace these with your actual posts after importing
# These are just examples to show how it works
SAMPLE_POSTS = [
    {
        "content": "Just shipped a new feature that lets AI agents remember context across sessions. Game changer for building autonomous systems. 🚀",
        "engagement": {"likes": 45, "replies": 8, "reposts": 3}
    },
    {
        "content": "Hot take: Most AI agent frameworks are overengineered. You don't need 10 layers of abstraction. Keep it simple, make it work.",
        "engagement": {"likes": 89, "replies": 15, "reposts": 7}
    },
    {
        "content": "Building in public is wild. Shipped 3 major features this week based on user feedback. The community knows what they want.",
        "engagement": {"likes": 67, "replies": 12, "reposts": 4}
    },
    {
        "content": "Pro tip: When debugging async code, add timestamps to your logs. Saved me 2 hours today tracking down a race condition.",
        "engagement": {"likes": 123, "replies": 18, "reposts": 9}
    },
    {
        "content": "The best code is code you don't write. Spent all day deleting features nobody uses. Codebase is 30% smaller and 2x faster.",
        "engagement": {"likes": 156, "replies": 24, "reposts": 12}
    }
]


def analyze_writing_style(posts):
    """Analyze writing style from posts"""
    if not posts:
        return None
    
    # Calculate metrics
    total_length = sum(len(p.get('content', '')) for p in posts)
    avg_length = total_length / len(posts) if posts else 0
    
    # Check for patterns
    all_text = ' '.join(p.get('content', '') for p in posts)
    uses_emojis = any(emoji in all_text for emoji in ['😀', '🚀', '💡', '✨', '🔥', '👀', '💪', '🎯', '⚡'])
    uses_hashtags = '#' in all_text
    uses_questions = '?' in all_text
    
    # Count sentence starters
    sentences = all_text.split('.')
    short_sentences = sum(1 for s in sentences if len(s.strip()) < 50)
    
    return {
        'total_posts': len(posts),
        'avg_length': int(avg_length),
        'uses_emojis': uses_emojis,
        'uses_hashtags': uses_hashtags,
        'uses_questions': uses_questions,
        'short_sentences': short_sentences,
        'total_sentences': len(sentences)
    }


async def generate_post_in_style(posts, topic="AI agents"):
    """Generate a new post in the user's style"""
    
    # Analyze style
    style = analyze_writing_style(posts)
    
    print("\n📊 Writing Style Analysis:")
    print(f"   Total posts analyzed: {style['total_posts']}")
    print(f"   Average post length: {style['avg_length']} characters")
    print(f"   Uses emojis: {'✅' if style['uses_emojis'] else '❌'}")
    print(f"   Uses hashtags: {'✅' if style['uses_hashtags'] else '❌'}")
    print(f"   Uses questions: {'✅' if style['uses_questions'] else '❌'}")
    print(f"   Writing style: {'Punchy/concise' if style['short_sentences'] > style['total_sentences'] * 0.6 else 'Flowing/detailed'}")
    
    print("\n📝 Your actual posts:")
    for i, post in enumerate(posts[:5], 1):
        content = post.get('content', '')
        likes = post.get('engagement', {}).get('likes', 0)
        print(f"   {i}. {content}")
        print(f"      (❤️ {likes} likes)\n")
    
    # Create style-aware prompt
    examples = "\n\n".join([
        f"Example {i+1}: {post.get('content', '')}"
        for i, post in enumerate(posts)
    ])
    
    prompt = f"""You are writing a new X (Twitter) post in the EXACT style of the user below.

IMPORTANT: Match their:
- Tone and voice (analyze carefully)
- Sentence structure and length
- Use of emojis: {"Include emojis like 🚀 💡 ✨" if style['uses_emojis'] else "No emojis"}
- Use of hashtags: {"Include relevant hashtags" if style['uses_hashtags'] else "No hashtags"}
- Post length: around {style['avg_length']} characters
- Vocabulary and phrases they actually use
- Their personality and perspective

Here are the user's actual posts - study them carefully:

{examples}

Now write a NEW post about "{topic}" in this EXACT same style. 
Make it sound EXACTLY like it was written by the same person.
Match their energy, tone, and way of expressing ideas.

Only output the post text, nothing else. No quotes, no explanations."""

    # Generate using Claude
    try:
        client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        
        print(f"\n🤖 Generating post about '{topic}' in your style...")
        print("=" * 70)
        
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=300,
            temperature=0.8,  # Higher temp for more personality
            messages=[{
                "role": "user",
                "content": prompt
            }]
        )
        
        generated_post = response.content[0].text.strip()
        
        print("\n✨ GENERATED POST:")
        print("=" * 70)
        print(generated_post)
        print("=" * 70)
        
        print(f"\n📏 Length: {len(generated_post)} characters")
        print(f"   (Your average: {style['avg_length']} characters)")
        
        # Show comparison
        print("\n🔍 Style Match Check:")
        gen_has_emoji = any(emoji in generated_post for emoji in ['😀', '🚀', '💡', '✨', '🔥', '👀', '💪', '🎯', '⚡'])
        gen_has_hashtag = '#' in generated_post
        gen_has_question = '?' in generated_post
        
        print(f"   Emojis: {'✅ Match' if gen_has_emoji == style['uses_emojis'] else '⚠️ Mismatch'}")
        print(f"   Hashtags: {'✅ Match' if gen_has_hashtag == style['uses_hashtags'] else '⚠️ Mismatch'}")
        print(f"   Questions: {'✅ Match' if gen_has_question == style['uses_questions'] else '⚠️ Mismatch'}")
        print(f"   Length: {'✅ Similar' if abs(len(generated_post) - style['avg_length']) < 50 else '⚠️ Different'}")
        
        return generated_post
        
    except Exception as e:
        print(f"❌ Error generating post: {e}")
        import traceback
        traceback.print_exc()
        return None


async def main():
    """Main test function"""
    print("🚀 Testing Post Generation in Your Style (DEMO)")
    print("=" * 70)
    print("\n⚠️  Using SAMPLE posts for demo. Replace with your actual posts!")
    print("   After importing your posts, they'll be used automatically.\n")
    
    # Use sample posts for demo
    posts = SAMPLE_POSTS
    
    # Test with different topics
    topics = [
        "AI agents and automation",
        "building developer tools",
        "productivity and focus"
    ]
    
    for i, topic in enumerate(topics, 1):
        print(f"\n{'='*70}")
        print(f"TEST {i}/{len(topics)}")
        await generate_post_in_style(posts, topic)
        
        # Ask if user wants to continue
        if i < len(topics):
            print("\n" + "="*70)
            response = input("\n👉 Generate another post? (y/n): ")
            if response.lower() != 'y':
                break


if __name__ == "__main__":
    asyncio.run(main())

