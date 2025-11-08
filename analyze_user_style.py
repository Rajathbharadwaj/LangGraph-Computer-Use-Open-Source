#!/usr/bin/env python3
"""
Analyze User Writing Style
Run this after scraping user posts to generate their writing style profile.
"""

import sys
from user_writing_style import UserWritingStyleAnalyzer


def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze_user_style.py <user_id>")
        print("\nExample: python analyze_user_style.py user_s2izyx2x2")
        sys.exit(1)
    
    user_id = sys.argv[1]
    
    print(f"🔍 Analyzing writing style for user: {user_id}")
    print("=" * 70)
    
    analyzer = UserWritingStyleAnalyzer(user_id)
    
    # Check if posts file exists
    if not analyzer.posts_file.exists():
        print(f"\n❌ No posts file found: {analyzer.posts_file}")
        print("\n💡 To scrape user posts, use the dashboard:")
        print("   1. Go to http://localhost:3000")
        print("   2. Click 'Import Posts' in the 'Your Posts' card")
        print("   3. Wait for scraping to complete")
        print("   4. Run this script again")
        sys.exit(1)
    
    # Analyze style
    profile = analyzer.analyze_writing_style()
    
    print(f"\n✅ Successfully analyzed {profile['total_posts_analyzed']} posts!")
    print(f"📁 Style profile saved to: {analyzer.style_profile_file}")
    
    print("\n" + "=" * 70)
    print("📊 WRITING STYLE SUMMARY:")
    print("=" * 70)
    
    print(f"\n📏 LENGTH:")
    print(f"   - Average post: {profile['avg_post_length']:.0f} characters")
    print(f"   - Average words: {profile['avg_word_count']:.0f} words")
    
    print(f"\n✍️ STYLE:")
    print(f"   - Emojis: {'✅ Yes' if profile['uses_emojis'] else '❌ No'} ({profile['emoji_frequency']:.1f} per post)")
    print(f"   - Exclamations: {profile['uses_exclamation']:.1f} per post")
    print(f"   - Questions: {profile['uses_question']:.1f} per post")
    print(f"   - Ellipsis: {profile['uses_ellipsis']:.1f} per post")
    print(f"   - ALL CAPS: {'✅ Sometimes' if profile['uses_all_caps'] else '❌ Rarely'}")
    
    print(f"\n#️⃣ HASHTAGS & MENTIONS:")
    print(f"   - Hashtags: {'✅ Yes' if profile['uses_hashtags'] else '❌ No'} ({profile['avg_hashtags']:.1f} per post)")
    print(f"   - Mentions: {'✅ Yes' if profile['uses_mentions'] else '❌ No'} ({profile['avg_mentions']:.1f} per post)")
    
    if profile['common_starters']:
        print(f"\n🎯 COMMON PHRASES:")
        for starter in profile['common_starters']:
            print(f"   - \"{starter}...\"")
    
    if profile['sample_posts']:
        print(f"\n📝 SAMPLE POSTS:")
        for i, post in enumerate(profile['sample_posts'][:3], 1):
            sample = post[:100] + "..." if len(post) > 100 else post
            print(f"   {i}. \"{sample}\"")
    
    print("\n" + "=" * 70)
    print("🎨 GENERATED STYLE PROMPT:")
    print("=" * 70)
    print(analyzer.generate_style_prompt())
    
    print("\n" + "=" * 70)
    print("✅ NEXT STEPS:")
    print("=" * 70)
    print("1. The agent will now use this style when commenting")
    print("2. Restart LangGraph to load the style profile:")
    print("   cd /home/rajathdb/cua && make langgraph")
    print("3. Test by running the engagement workflow")
    print("\n💡 The agent will comment in YOUR writing style!")


if __name__ == "__main__":
    main()




