"""
Test dataset for post tone/intent analysis.

Contains 6 posts covering:
1. Obvious humor (meme about debugging)
2. Educational thread (serious technical content)
3. Hard sarcasm (risky, should skip)
4. Promotional spam (should skip)
5. Safe sarcasm (relatable dev humor)
6. Genuine question (should engage thoughtfully)
"""

TEST_POSTS = [
    {
        "id": "humor_debugging",
        "post_text": "My debugging process:\n\n1. It doesn't work\n2. Why doesn't it work?\n3. Oh that's why\n4. Now it works\n5. Why does it work now?\n\n😭",
        "author_handle": "devmemes",
        "author_followers": 5000,
        "engagement_metrics": {"likes": 250, "retweets": 45, "replies": 12},
        "expected_analysis": {
            "tone": "humorous",
            "intent": "meme",
            "engagement_worthy": True,
            "recommended_response_type": "quick_reaction",
            "min_confidence": 0.8,
            "reasoning": "Clear debugging humor, relatable to developers"
        }
    },

    {
        "id": "educational_technical",
        "post_text": "Deep dive into Python's GIL and why it matters for concurrent programming:\n\nThread 🧵\n\n1/ The Global Interpreter Lock (GIL) is a mutex that protects access to Python objects, preventing multiple threads from executing Python bytecodes at once.\n\nThis means CPU-bound Python programs don't benefit from multi-threading...",
        "author_handle": "pythonexpert",
        "author_followers": 12000,
        "engagement_metrics": {"likes": 450, "retweets": 120, "replies": 35},
        "expected_analysis": {
            "tone": "serious",
            "intent": "educational",
            "engagement_worthy": True,
            "recommended_response_type": "thoughtful_comment",
            "min_confidence": 0.8,
            "reasoning": "High-quality educational content about GIL"
        }
    },

    {
        "id": "hard_sarcasm_risky",
        "post_text": "Oh yeah, writing tests is SUCH a waste of time. Who needs tests when you have production users to find bugs for you? 🙄\n\nJust ship it and pray, that's my motto. Works every time! 💯",
        "author_handle": "frustrateddev",
        "author_followers": 800,
        "engagement_metrics": {"likes": 15, "retweets": 2, "replies": 8},
        "expected_analysis": {
            "tone": "sarcastic",
            "intent": "hot_take",
            "engagement_worthy": False,  # Should skip unless confidence >= 0.9
            "recommended_response_type": "skip",
            "min_confidence": 0.7,
            "reasoning": "Sarcastic rant, risky to engage with"
        }
    },

    {
        "id": "promotional_spam",
        "post_text": "🚀 Make $10k/month with my NEW COURSE on web development! 💰\n\n✅ No experience needed\n✅ Learn in 7 days\n✅ Guaranteed results\n\nLink in bio! 👇 DM me for discount code! 🔥🔥🔥",
        "author_handle": "webdevguru2024",
        "author_followers": 450,
        "engagement_metrics": {"likes": 5, "retweets": 1, "replies": 0},
        "expected_analysis": {
            "tone": "neutral",  # Promotional tone
            "intent": "promotion",
            "engagement_worthy": False,
            "recommended_response_type": "skip",
            "min_confidence": 0.9,
            "reasoning": "Clear promotional spam with unrealistic claims"
        }
    },

    {
        "id": "safe_sarcasm_relatable",
        "post_text": "Me: *writes clean, well-documented code*\n\nMe 3 months later looking at the same code: \"What absolute genius wrote this masterpiece? Oh wait, it was me. Past me was a legend.\" 😎",
        "author_handle": "codinglife",
        "author_followers": 8500,
        "engagement_metrics": {"likes": 320, "retweets": 55, "replies": 18},
        "expected_analysis": {
            "tone": "humorous",  # Self-deprecating humor, not harsh sarcasm
            "intent": "personal_story",
            "engagement_worthy": True,
            "recommended_response_type": "quick_reaction",
            "min_confidence": 0.8,
            "reasoning": "Relatable developer humor about code documentation"
        }
    },

    {
        "id": "genuine_question",
        "post_text": "Quick question for React devs: What's your preferred state management solution in 2024?\n\nI'm torn between:\n- Redux Toolkit\n- Zustand\n- Jotai\n- Context + useReducer\n\nWorking on a medium-sized app (~20 components). What would you recommend and why?",
        "author_handle": "reactlearner",
        "author_followers": 1200,
        "engagement_metrics": {"likes": 45, "retweets": 5, "replies": 32},
        "expected_analysis": {
            "tone": "neutral",
            "intent": "question",
            "engagement_worthy": True,
            "recommended_response_type": "thoughtful_comment",
            "min_confidence": 0.9,
            "reasoning": "Genuine technical question seeking advice"
        }
    }
]


def get_test_post(post_id: str):
    """Get a specific test post by ID"""
    for post in TEST_POSTS:
        if post["id"] == post_id:
            return post
    return None


def get_all_test_posts():
    """Get all test posts"""
    return TEST_POSTS


def print_test_dataset():
    """Print formatted test dataset for review"""
    print("=" * 80)
    print("POST TONE ANALYSIS TEST DATASET")
    print("=" * 80)

    for i, post in enumerate(TEST_POSTS, 1):
        print(f"\n{i}. {post['id'].upper()}")
        print(f"   Author: @{post['author_handle']} ({post['author_followers']:,} followers)")
        print(f"   Post: {post['post_text'][:100]}...")
        print(f"   Expected: {post['expected_analysis']['tone']} / {post['expected_analysis']['intent']}")
        print(f"   Engage? {post['expected_analysis']['engagement_worthy']}")
        print(f"   Reasoning: {post['expected_analysis']['reasoning']}")


if __name__ == "__main__":
    print_test_dataset()
