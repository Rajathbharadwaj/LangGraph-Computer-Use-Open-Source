"""
User Writing Style Analyzer
Analyzes user's posts to extract writing style and generate style-matched comments.
"""

import json
from typing import Dict, List, Optional
from pathlib import Path


class UserWritingStyleAnalyzer:
    """Analyzes user's posts to extract writing style patterns"""
    
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.posts_file = Path(f"user_posts_{user_id}.json")
        self.style_profile_file = Path(f"user_style_profile_{user_id}.json")
    
    def load_user_posts(self) -> List[Dict]:
        """Load user's scraped posts"""
        if not self.posts_file.exists():
            return []
        
        with open(self.posts_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('posts', [])
    
    def analyze_writing_style(self) -> Dict:
        """Analyze user's writing style from their posts"""
        posts = self.load_user_posts()
        
        if not posts:
            return self._default_style_profile()
        
        # Extract text from posts
        post_texts = [post.get('text', '') for post in posts if post.get('text')]
        
        if not post_texts:
            return self._default_style_profile()
        
        # Analyze style patterns
        style_profile = {
            "user_id": self.user_id,
            "total_posts_analyzed": len(post_texts),
            
            # Length patterns
            "avg_post_length": sum(len(text) for text in post_texts) / len(post_texts),
            "avg_word_count": sum(len(text.split()) for text in post_texts) / len(post_texts),
            
            # Tone patterns
            "uses_emojis": any('😀' <= char <= '🙏' or '🚀' <= char <= '🛿' 
                              for text in post_texts for char in text),
            "emoji_frequency": sum(1 for text in post_texts 
                                  for char in text 
                                  if '😀' <= char <= '🙏' or '🚀' <= char <= '🛿') / len(post_texts),
            
            # Punctuation patterns
            "uses_exclamation": sum(text.count('!') for text in post_texts) / len(post_texts),
            "uses_question": sum(text.count('?') for text in post_texts) / len(post_texts),
            "uses_ellipsis": sum(text.count('...') for text in post_texts) / len(post_texts),
            
            # Capitalization patterns
            "uses_all_caps": any(word.isupper() and len(word) > 2 
                                for text in post_texts 
                                for word in text.split()),
            
            # Common phrases (first 3 words of each post)
            "common_starters": self._extract_common_starters(post_texts),
            
            # Hashtag usage
            "uses_hashtags": any('#' in text for text in post_texts),
            "avg_hashtags": sum(text.count('#') for text in post_texts) / len(post_texts),
            
            # Mention usage
            "uses_mentions": any('@' in text for text in post_texts),
            "avg_mentions": sum(text.count('@') for text in post_texts) / len(post_texts),
            
            # Sample posts for reference
            "sample_posts": post_texts[:5]
        }
        
        # Save style profile
        self._save_style_profile(style_profile)
        
        return style_profile
    
    def _extract_common_starters(self, texts: List[str]) -> List[str]:
        """Extract common ways the user starts their posts"""
        starters = []
        for text in texts:
            words = text.split()
            if len(words) >= 3:
                starter = ' '.join(words[:3])
                starters.append(starter)
        
        # Return top 5 most common starters
        from collections import Counter
        common = Counter(starters).most_common(5)
        return [starter for starter, _ in common]
    
    def _default_style_profile(self) -> Dict:
        """Default style profile if no posts available"""
        return {
            "user_id": self.user_id,
            "total_posts_analyzed": 0,
            "avg_post_length": 100,
            "avg_word_count": 20,
            "uses_emojis": False,
            "emoji_frequency": 0,
            "uses_exclamation": 0.5,
            "uses_question": 0.2,
            "uses_ellipsis": 0.1,
            "uses_all_caps": False,
            "common_starters": [],
            "uses_hashtags": False,
            "avg_hashtags": 0,
            "uses_mentions": True,
            "avg_mentions": 0.5,
            "sample_posts": []
        }
    
    def _save_style_profile(self, profile: Dict):
        """Save style profile to file"""
        with open(self.style_profile_file, 'w', encoding='utf-8') as f:
            json.dump(profile, indent=2, fp=f)
    
    def load_style_profile(self) -> Dict:
        """Load existing style profile or create new one"""
        if self.style_profile_file.exists():
            with open(self.style_profile_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        # Analyze and create new profile
        return self.analyze_writing_style()
    
    def generate_style_prompt(self) -> str:
        """Generate a prompt describing the user's writing style"""
        profile = self.load_style_profile()
        
        if profile['total_posts_analyzed'] == 0:
            return """Write in a professional but friendly tone. Keep comments concise and thoughtful."""
        
        prompt = f"""🎨 USER'S WRITING STYLE (based on {profile['total_posts_analyzed']} posts):

📏 LENGTH:
- Average post: {profile['avg_post_length']:.0f} characters
- Average words: {profile['avg_word_count']:.0f} words
- Keep comments similar length (slightly shorter is fine)

✍️ TONE & STYLE:
"""
        
        # Emoji usage
        if profile['uses_emojis']:
            prompt += f"- ✅ Uses emojis (avg {profile['emoji_frequency']:.1f} per post) - include relevant emojis\n"
        else:
            prompt += "- ❌ Rarely uses emojis - keep it text-focused\n"
        
        # Punctuation
        if profile['uses_exclamation'] > 1:
            prompt += f"- ✅ Enthusiastic (uses ! often) - show excitement\n"
        elif profile['uses_exclamation'] < 0.3:
            prompt += "- 📊 Measured tone (rarely uses !) - stay calm and professional\n"
        
        if profile['uses_question'] > 0.5:
            prompt += "- ❓ Asks questions - engage with questions\n"
        
        if profile['uses_ellipsis'] > 0.3:
            prompt += "- ... Uses ellipsis for pauses - can use sparingly\n"
        
        # Capitalization
        if profile['uses_all_caps']:
            prompt += "- 🔊 Sometimes uses ALL CAPS for emphasis\n"
        
        # Hashtags
        if profile['uses_hashtags']:
            prompt += f"- #️⃣ Uses hashtags (avg {profile['avg_hashtags']:.1f} per post)\n"
        
        # Mentions
        if profile['uses_mentions']:
            prompt += f"- @ Mentions others (avg {profile['avg_mentions']:.1f} per post)\n"
        
        # Common starters
        if profile['common_starters']:
            prompt += f"\n🎯 COMMON PHRASES:\n"
            for starter in profile['common_starters'][:3]:
                prompt += f"- \"{starter}...\"\n"
        
        # Sample posts
        if profile['sample_posts']:
            prompt += f"\n📝 SAMPLE POSTS (for reference):\n"
            for i, post in enumerate(profile['sample_posts'][:3], 1):
                # Truncate long posts
                sample = post[:150] + "..." if len(post) > 150 else post
                prompt += f"{i}. \"{sample}\"\n"
        
        prompt += """
🎯 COMMENTING GUIDELINES:
1. Match the user's tone and style
2. Keep length similar to their typical posts (or shorter for comments)
3. Use similar punctuation and emoji patterns
4. Be authentic - this should sound like the user wrote it
5. Add value to the conversation - don't just say "great post!"

Remember: You're commenting AS this user, so it should sound like them!
"""
        
        return prompt


def get_user_style_prompt(user_id: str) -> str:
    """Convenience function to get style prompt for a user"""
    analyzer = UserWritingStyleAnalyzer(user_id)
    return analyzer.generate_style_prompt()


def analyze_user_style(user_id: str) -> Dict:
    """Convenience function to analyze and return style profile"""
    analyzer = UserWritingStyleAnalyzer(user_id)
    return analyzer.analyze_writing_style()


if __name__ == "__main__":
    # Test with a user ID
    import sys
    
    if len(sys.argv) > 1:
        user_id = sys.argv[1]
        print(f"Analyzing writing style for user: {user_id}")
        print("=" * 60)
        
        analyzer = UserWritingStyleAnalyzer(user_id)
        profile = analyzer.analyze_writing_style()
        
        print(f"\n✅ Analyzed {profile['total_posts_analyzed']} posts")
        print(f"📏 Avg length: {profile['avg_post_length']:.0f} chars, {profile['avg_word_count']:.0f} words")
        print(f"😀 Emojis: {'Yes' if profile['uses_emojis'] else 'No'}")
        print(f"❗ Exclamations: {profile['uses_exclamation']:.1f} per post")
        print(f"#️⃣ Hashtags: {profile['avg_hashtags']:.1f} per post")
        
        print("\n" + "=" * 60)
        print("\n📝 STYLE PROMPT:\n")
        print(analyzer.generate_style_prompt())
    else:
        print("Usage: python user_writing_style.py <user_id>")




