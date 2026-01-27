"""
LinkedIn Growth Principles

Professional engagement rules and targeting strategies for LinkedIn automation.
These principles guide the LinkedIn agent's behavior to maximize authentic engagement
while maintaining a professional brand image.

Key differences from X/Twitter:
- Professional tone expected
- Longer, value-adding comments preferred
- Connection-degree awareness (1st, 2nd, 3rd)
- Less emoji usage
- Peak engagement during business hours
"""

# =============================================================================
# Targeting Configuration
# =============================================================================

LINKEDIN_TARGETING = {
    # WHO to engage with
    "who_to_engage": {
        # Connection proximity (prioritize network)
        "connection_degrees": ["1st", "2nd"],  # 3rd degree requires InMail or connection first

        # Follower/connection thresholds (sweet spot for engagement)
        "min_connections": 500,
        "max_connections": 50000,  # Avoid mega-influencers (low engagement rate)

        # Activity indicators
        "active_recently": True,  # Posted in last 7 days
        "min_engagement_rate": 0.02,  # 2% engagement rate minimum

        # Industry/relevance
        "industry_relevance": True,  # Must be in similar industry
        "job_title_keywords": [],  # Set dynamically based on user's network

        # Avoid
        "avoid_recruiters": False,  # Optional: some users want to avoid recruiters
        "avoid_sales": False,  # Optional: avoid obvious sales accounts
    },

    # WHAT content to engage with
    "what_to_engage": {
        # Content types (ordered by preference)
        "preferred_types": ["text", "article", "document", "carousel"],
        "avoid_types": ["job_posting", "company_update", "ad"],

        # Engagement thresholds
        "min_reactions": 10,  # Some traction already
        "max_reactions": 10000,  # Avoid viral posts (comments get lost)
        "min_comments": 0,  # Fresh posts are good
        "max_comments": 200,  # Too many = comment gets buried

        # Timing
        "max_age_hours": 48,  # Posts older than 2 days have less visibility
        "prefer_recent": True,  # Weight toward newer posts

        # Topic preferences
        "prefer_topics": [
            "industry_insights",
            "career_advice",
            "professional_growth",
            "leadership",
            "technology_trends",
            "startup_journey",
            "lessons_learned",
        ],

        # Topics to avoid
        "avoid_topics": [
            "politics",
            "religion",
            "controversial_social_issues",
            "crypto_shilling",
            "mlm",
            "get_rich_quick",
        ],

        # Quality signals
        "prefer_posts_with_questions": True,  # Easy to add value
        "prefer_original_content": True,  # Not reshares
        "prefer_personal_stories": True,  # Authentic content
    },

    # HOW to engage
    "how_to_engage": {
        # Comment guidelines
        "comment_min_length": 50,  # LinkedIn rewards longer comments (dwell time)
        "comment_max_length": 500,  # Keep it focused
        "comment_ideal_length": (100, 300),  # Sweet spot

        # Tone
        "tone": "professional",
        "allowed_tones": ["professional", "thoughtful", "supportive", "curious"],
        "avoid_tones": ["casual", "sarcastic", "controversial", "salesy"],

        # Content requirements
        "must_include_one_of": [
            "insight",  # Share relevant experience or knowledge
            "question",  # Ask a thoughtful follow-up question
            "experience",  # Share a related personal experience
            "resource",  # Offer a helpful resource or recommendation
            "perspective",  # Add a different viewpoint
        ],

        # Banned phrases (AI-sounding or low-value)
        "banned_phrases": [
            "Great post!",
            "Love this!",
            "This!",
            "So true!",
            "Couldn't agree more!",
            "Absolutely!",
            "Well said!",
            "Thanks for sharing!",
            "Great insights!",
            "Totally agree!",
            "100%!",
            "Spot on!",
            "This is gold!",
            "Mind blown!",
            "Game changer!",
            "Food for thought!",
            "Preach!",
            "Facts!",
            "Mic drop!",
            "Nailed it!",
            # AI-sounding patterns
            "As an AI",
            "I'm just an AI",
            "In my opinion as",
            "From my perspective as",
            "I wholeheartedly",
            "I couldn't help but",
            "I just wanted to chime in",
        ],

        # Emoji usage
        "emoji_usage": "minimal",  # "none", "minimal", "moderate"
        "max_emojis_per_comment": 1,

        # Reaction preferences (ordered by appropriateness)
        "reaction_preference": ["Like", "Insightful", "Celebrate", "Support"],
        "avoid_reactions": ["Funny", "Love"],  # Use sparingly, context-dependent
    },

    # WHEN to engage
    "when_to_engage": {
        # Peak engagement hours (local time)
        "peak_hours": [
            (8, 10),   # Morning commute / start of day
            (12, 13),  # Lunch break
            (17, 18),  # End of work day
        ],

        # Best days (ranked)
        "best_days": ["Tuesday", "Wednesday", "Thursday", "Monday", "Friday"],
        "avoid_days": ["Saturday", "Sunday"],  # Low engagement on weekends

        # Timezone handling
        "timezone_aware": True,
        "default_timezone": "America/New_York",  # Default to East Coast business hours

        # Frequency limits
        "min_minutes_between_comments": 5,  # Don't spam
        "max_comments_per_hour": 10,
    },
}


# =============================================================================
# Daily Rate Limits
# =============================================================================

DAILY_LIMITS = {
    # Engagement actions
    "reactions": 100,  # LinkedIn is more lenient than X
    "comments": 30,  # Quality over quantity
    "connection_requests": 10,  # LinkedIn is strict about connections
    "messages": 5,  # InMail/messages are limited

    # Profile views (for research)
    "profile_views": 100,

    # Content creation
    "posts": 2,  # 1-2 posts per day is optimal
    "articles": 1,  # Articles take more effort

    # Search actions
    "searches": 50,
}


# =============================================================================
# Comment Templates & Patterns
# =============================================================================

COMMENT_PATTERNS = {
    # Insight pattern
    "insight": [
        "This resonates because {insight}. In my experience, {experience}.",
        "Great point about {topic}. I've found that {insight}.",
        "This aligns with what I've seen in {industry}. {observation}.",
    ],

    # Question pattern
    "question": [
        "Interesting perspective! How do you approach {specific_aspect}?",
        "This got me thinking - what's been your experience with {related_topic}?",
        "Love this. Curious to know: {thoughtful_question}?",
    ],

    # Experience pattern
    "experience": [
        "This hits home. When I was {role/situation}, I learned that {lesson}.",
        "I had a similar experience when {context}. The key takeaway was {insight}.",
        "Been there! What worked for me was {approach}. {result}.",
    ],

    # Resource pattern
    "resource": [
        "Great topic! For anyone interested, {resource} covers this in depth.",
        "This reminds me of {book/article/person}'s work on {topic}. Worth checking out.",
        "Adding to this: {resource} has some excellent frameworks for {topic}.",
    ],

    # Perspective pattern
    "perspective": [
        "Another angle to consider: {alternative_view}. Both approaches have merit.",
        "Building on this - what about {related_consideration}?",
        "Yes, and I'd add that {complementary_point}.",
    ],
}


# =============================================================================
# Connection Request Templates
# =============================================================================

CONNECTION_NOTE_PATTERNS = {
    # Mutual connection
    "mutual": "Hi {name}! I noticed we're both connected to {mutual}. I've been following your work on {topic} and would love to connect.",

    # Industry peer
    "industry": "Hi {name}, I work in {industry} and have been impressed by your insights on {topic}. Would be great to connect and exchange ideas.",

    # Content appreciation
    "content": "Hi {name}, your recent post about {topic} really resonated with me. I'd love to connect and learn more from your perspective.",

    # Event/group
    "event": "Hi {name}, I saw you're also in {group/event}. Great to see someone else passionate about {topic}. Let's connect!",

    # Referral
    "referral": "Hi {name}, {referrer} suggested I reach out. They mentioned your expertise in {topic}. Would love to connect.",
}


# =============================================================================
# Quality Scoring
# =============================================================================

def calculate_post_quality_score(post: dict) -> float:
    """
    Calculate a quality score for a post to determine engagement worthiness.

    Args:
        post: Dict with post data (reactions, comments, author, content, etc.)

    Returns:
        Float score from 0.0 to 1.0
    """
    score = 0.5  # Base score

    reactions = post.get('reactions', 0)
    comments = post.get('comments', 0)
    content = post.get('content', '')
    author = post.get('author', '')

    # Engagement signals
    if 10 <= reactions <= 500:
        score += 0.1
    if 1 <= comments <= 50:
        score += 0.1

    # Content signals
    if '?' in content:  # Has a question
        score += 0.1
    if len(content) > 200:  # Substantive post
        score += 0.1
    if any(keyword in content.lower() for keyword in ['learned', 'realized', 'tip', 'advice']):
        score += 0.1

    # Avoid signals
    if reactions > 5000:  # Too viral
        score -= 0.2
    if comments > 200:  # Comment will get lost
        score -= 0.1
    if any(bad in content.lower() for bad in ['dm me', 'link in bio', 'hiring', 'job alert']):
        score -= 0.2

    return max(0.0, min(1.0, score))


def validate_comment(comment: str) -> tuple[bool, list[str]]:
    """
    Validate a comment against quality rules.

    Args:
        comment: The comment text to validate

    Returns:
        Tuple of (is_valid, list of issues)
    """
    issues = []

    # Length checks
    if len(comment) < LINKEDIN_TARGETING["how_to_engage"]["comment_min_length"]:
        issues.append(f"Comment too short ({len(comment)} chars, min {LINKEDIN_TARGETING['how_to_engage']['comment_min_length']})")

    if len(comment) > LINKEDIN_TARGETING["how_to_engage"]["comment_max_length"]:
        issues.append(f"Comment too long ({len(comment)} chars, max {LINKEDIN_TARGETING['how_to_engage']['comment_max_length']})")

    # Banned phrase check
    lower_comment = comment.lower()
    for phrase in LINKEDIN_TARGETING["how_to_engage"]["banned_phrases"]:
        if phrase.lower() in lower_comment:
            issues.append(f"Contains banned phrase: '{phrase}'")

    # Must include one of
    has_value = False
    if '?' in comment:  # Has question
        has_value = True
    if len(comment) > 100:  # Substantive
        has_value = True
    if any(word in lower_comment for word in ['experience', 'learned', 'found', 'noticed', 'realized']):
        has_value = True

    if not has_value:
        issues.append("Comment should include an insight, question, or experience")

    # Emoji check
    emoji_count = sum(1 for c in comment if ord(c) > 127000)  # Rough emoji detection
    max_emojis = LINKEDIN_TARGETING["how_to_engage"]["max_emojis_per_comment"]
    if emoji_count > max_emojis:
        issues.append(f"Too many emojis ({emoji_count}, max {max_emojis})")

    return len(issues) == 0, issues


# =============================================================================
# Export
# =============================================================================

__all__ = [
    'LINKEDIN_TARGETING',
    'DAILY_LIMITS',
    'COMMENT_PATTERNS',
    'CONNECTION_NOTE_PATTERNS',
    'calculate_post_quality_score',
    'validate_comment',
]
