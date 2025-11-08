"""
X Growth Principles - Strategic Logic for Engagement

These are the RULES that guide WHO, WHAT, WHEN, and HOW to engage.
Subagents use these principles to make intelligent decisions.
"""

from dataclasses import dataclass
from typing import List, Dict, Optional


# ============================================================================
# ENGAGEMENT PRINCIPLES
# ============================================================================

@dataclass
class EngagementPrinciples:
    """Core principles for X growth strategy"""
    
    # WHO to engage with
    target_follower_range: tuple = (500, 50000)  # Sweet spot for engagement
    target_engagement_rate: float = 0.02  # Min 2% engagement rate
    target_niches: List[str] = None  # e.g., ["AI", "LangChain", "agents"]
    avoid_verified_mega_accounts: bool = True  # <100k followers
    
    # WHAT to engage with
    max_post_age_hours: int = 24  # Recent posts get more visibility
    min_post_quality_score: float = 0.7  # Quality threshold (0-1)
    prefer_posts_with_questions: bool = True  # Questions invite engagement
    avoid_controversial_topics: List[str] = None  # e.g., ["politics", "religion"]
    
    # WHEN to engage
    optimal_engagement_times: List[str] = None  # e.g., ["9-11am", "1-3pm", "7-9pm"]
    min_time_between_actions_seconds: int = 30  # Rate limiting
    
    # HOW to engage
    comment_min_length: int = 50  # Thoughtful comments
    comment_max_length: int = 280  # Twitter limit
    avoid_generic_comments: List[str] = None  # e.g., ["Great post!", "Nice!"]
    require_value_add: bool = True  # Comments must add insight
    
    def __post_init__(self):
        if self.target_niches is None:
            self.target_niches = ["AI", "machine learning", "LangChain", "agents"]
        if self.avoid_controversial_topics is None:
            self.avoid_controversial_topics = ["politics", "religion", "crypto scams"]
        if self.optimal_engagement_times is None:
            self.optimal_engagement_times = ["9-11am EST", "1-3pm EST", "7-9pm EST"]
        if self.avoid_generic_comments is None:
            self.avoid_generic_comments = [
                "great post", "nice", "awesome", "cool", "interesting",
                "👍", "🔥", "💯", "this", "agreed"
            ]


# ============================================================================
# ACCOUNT QUALITY ASSESSMENT
# ============================================================================

@dataclass
class AccountQualityMetrics:
    """Metrics for assessing account quality"""
    username: str
    follower_count: int
    following_count: int
    post_count: int
    engagement_rate: float  # (likes + comments) / followers
    niche_relevance: float  # 0-1 score
    account_age_days: int
    is_verified: bool
    has_profile_pic: bool
    has_bio: bool
    bio_keywords: List[str]
    
    @property
    def quality_score(self) -> float:
        """Calculate overall quality score (0-1)"""
        score = 0.0
        
        # Follower count (sweet spot: 500-50k)
        if 500 <= self.follower_count <= 50000:
            score += 0.3
        elif self.follower_count < 500:
            score += 0.1
        else:
            score += 0.15  # Too many followers = less likely to engage back
        
        # Engagement rate (higher is better)
        if self.engagement_rate > 0.05:  # 5%+
            score += 0.3
        elif self.engagement_rate > 0.02:  # 2-5%
            score += 0.2
        else:
            score += 0.1
        
        # Niche relevance
        score += self.niche_relevance * 0.2
        
        # Profile completeness
        if self.has_profile_pic:
            score += 0.05
        if self.has_bio:
            score += 0.05
        
        # Following/follower ratio (not a spam account)
        ratio = self.following_count / max(self.follower_count, 1)
        if 0.5 <= ratio <= 2.0:  # Healthy ratio
            score += 0.1
        
        return min(score, 1.0)


# ============================================================================
# POST QUALITY ASSESSMENT
# ============================================================================

@dataclass
class PostQualityMetrics:
    """Metrics for assessing post quality"""
    post_id: str
    author: str
    content: str
    like_count: int
    comment_count: int
    repost_count: int
    view_count: int
    age_hours: float
    has_media: bool
    has_link: bool
    has_question: bool
    content_length: int
    
    @property
    def engagement_score(self) -> float:
        """Calculate engagement score (0-1)"""
        # Normalize engagement metrics
        total_engagement = self.like_count + (self.comment_count * 3) + (self.repost_count * 2)
        
        # Adjust for post age (newer = better)
        age_factor = max(0, 1 - (self.age_hours / 24))
        
        # Engagement per hour
        engagement_per_hour = total_engagement / max(self.age_hours, 1)
        
        # Score based on engagement velocity
        if engagement_per_hour > 100:
            return 0.9 * age_factor
        elif engagement_per_hour > 50:
            return 0.7 * age_factor
        elif engagement_per_hour > 10:
            return 0.5 * age_factor
        else:
            return 0.3 * age_factor
    
    @property
    def quality_score(self) -> float:
        """Calculate content quality score (0-1)"""
        score = 0.0
        
        # Content length (not too short, not too long)
        if 50 <= self.content_length <= 280:
            score += 0.3
        elif self.content_length < 50:
            score += 0.1
        else:
            score += 0.2
        
        # Has question (invites engagement)
        if self.has_question:
            score += 0.2
        
        # Has media (more engaging)
        if self.has_media:
            score += 0.15
        
        # Engagement score
        score += self.engagement_score * 0.35
        
        return min(score, 1.0)


# ============================================================================
# COMMENT GENERATION PRINCIPLES
# ============================================================================

@dataclass
class CommentGenerationRules:
    """Rules for generating authentic comments"""
    
    # Content requirements
    min_length: int = 50
    max_length: int = 280
    require_specific_reference: bool = True  # Must reference post content
    require_value_add: bool = True  # Must add insight, not just agree
    
    # Tone
    tone: str = "thoughtful"  # Options: thoughtful, curious, supportive, analytical
    use_emojis: bool = False  # Sparingly, if at all
    use_hashtags: bool = False  # Usually no
    
    # Forbidden patterns
    forbidden_phrases: List[str] = None
    
    # Required elements
    must_include_one_of: List[str] = None  # e.g., ["question", "insight", "experience"]
    
    def __post_init__(self):
        if self.forbidden_phrases is None:
            self.forbidden_phrases = [
                "great post", "nice", "awesome", "cool", "interesting",
                "check out my", "follow me", "dm me", "click here",
                "👍", "🔥", "💯", "this", "agreed", "same", "facts"
            ]
        if self.must_include_one_of is None:
            self.must_include_one_of = [
                "question",  # Ask a thoughtful follow-up
                "insight",   # Add a new perspective
                "experience", # Share relevant experience
                "resource"   # Provide helpful resource
            ]


# ============================================================================
# STRATEGY CONFIGURATION
# ============================================================================

class XGrowthStrategy:
    """Complete X growth strategy configuration"""
    
    def __init__(
        self,
        user_niche: List[str] = None,
        target_audience: str = "AI/ML practitioners",
        growth_goal: str = "build authority",
        engagement_style: str = "thoughtful_expert"
    ):
        self.user_niche = user_niche or ["AI", "LangChain", "agents", "LLMs"]
        self.target_audience = target_audience
        self.growth_goal = growth_goal
        self.engagement_style = engagement_style
        
        # Initialize principles
        self.engagement_principles = EngagementPrinciples(
            target_niches=self.user_niche
        )
        self.comment_rules = CommentGenerationRules()
    
    def should_engage_with_account(self, metrics: AccountQualityMetrics) -> tuple[bool, str]:
        """
        Decide if we should engage with this account
        
        Returns:
            (should_engage, reason)
        """
        # Check quality score
        if metrics.quality_score < 0.6:
            return False, f"Quality score too low: {metrics.quality_score:.2f}"
        
        # Check follower range
        min_followers, max_followers = self.engagement_principles.target_follower_range
        if not (min_followers <= metrics.follower_count <= max_followers):
            return False, f"Follower count outside range: {metrics.follower_count}"
        
        # Check engagement rate
        if metrics.engagement_rate < self.engagement_principles.target_engagement_rate:
            return False, f"Engagement rate too low: {metrics.engagement_rate:.2%}"
        
        # Check niche relevance
        if metrics.niche_relevance < 0.5:
            return False, f"Not relevant to niche: {metrics.niche_relevance:.2f}"
        
        return True, f"Good match! Quality: {metrics.quality_score:.2f}, Engagement: {metrics.engagement_rate:.2%}"
    
    def should_engage_with_post(self, metrics: PostQualityMetrics) -> tuple[bool, str]:
        """
        Decide if we should engage with this post
        
        Returns:
            (should_engage, reason)
        """
        # Check age
        if metrics.age_hours > self.engagement_principles.max_post_age_hours:
            return False, f"Post too old: {metrics.age_hours:.1f} hours"
        
        # Check quality score
        if metrics.quality_score < self.engagement_principles.min_post_quality_score:
            return False, f"Quality score too low: {metrics.quality_score:.2f}"
        
        # Check engagement score
        if metrics.engagement_score < 0.3:
            return False, f"Engagement too low: {metrics.engagement_score:.2f}"
        
        return True, f"Good post! Quality: {metrics.quality_score:.2f}, Engagement: {metrics.engagement_score:.2f}"
    
    def validate_comment(self, comment: str) -> tuple[bool, str]:
        """
        Validate that a comment meets quality standards
        
        Returns:
            (is_valid, reason)
        """
        # Check length
        if len(comment) < self.comment_rules.min_length:
            return False, f"Too short: {len(comment)} chars (min: {self.comment_rules.min_length})"
        
        if len(comment) > self.comment_rules.max_length:
            return False, f"Too long: {len(comment)} chars (max: {self.comment_rules.max_length})"
        
        # Check for forbidden phrases
        comment_lower = comment.lower()
        for phrase in self.comment_rules.forbidden_phrases:
            if phrase in comment_lower:
                return False, f"Contains forbidden phrase: '{phrase}'"
        
        # Check for value-add (simple heuristic: has question mark or specific words)
        has_question = "?" in comment
        has_insight_words = any(word in comment_lower for word in [
            "because", "however", "interesting", "perspective", "consider",
            "experience", "found", "suggest", "recommend", "think"
        ])
        
        if not (has_question or has_insight_words):
            return False, "Doesn't add value (no question or insight)"
        
        return True, "Valid comment"


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    # Create strategy
    strategy = XGrowthStrategy(
        user_niche=["AI", "LangChain", "agents"],
        target_audience="AI/ML practitioners",
        growth_goal="build authority"
    )
    
    # Example: Assess an account
    account = AccountQualityMetrics(
        username="ai_researcher",
        follower_count=5000,
        following_count=3000,
        post_count=500,
        engagement_rate=0.03,  # 3%
        niche_relevance=0.9,
        account_age_days=365,
        is_verified=False,
        has_profile_pic=True,
        has_bio=True,
        bio_keywords=["AI", "ML", "research"]
    )
    
    should_engage, reason = strategy.should_engage_with_account(account)
    print(f"Should engage with @{account.username}? {should_engage}")
    print(f"Reason: {reason}")
    print(f"Quality score: {account.quality_score:.2f}")
    
    # Example: Assess a post
    post = PostQualityMetrics(
        post_id="123",
        author="ai_researcher",
        content="Just discovered an interesting pattern in LangGraph agents. Has anyone else noticed that subagents can significantly reduce context bloat?",
        like_count=50,
        comment_count=10,
        repost_count=5,
        view_count=1000,
        age_hours=2.5,
        has_media=False,
        has_link=False,
        has_question=True,
        content_length=150
    )
    
    should_engage, reason = strategy.should_engage_with_post(post)
    print(f"\nShould engage with post? {should_engage}")
    print(f"Reason: {reason}")
    print(f"Quality score: {post.quality_score:.2f}")
    
    # Example: Validate a comment
    good_comment = "Great question! I've found that subagents are especially useful when dealing with large tool outputs. In my experience, delegating web searches to a subagent keeps the main agent focused on high-level strategy. Have you experimented with different subagent configurations?"
    
    is_valid, reason = strategy.validate_comment(good_comment)
    print(f"\nIs comment valid? {is_valid}")
    print(f"Reason: {reason}")
    print(f"Comment: {good_comment}")
    
    bad_comment = "Great post! 👍"
    is_valid, reason = strategy.validate_comment(bad_comment)
    print(f"\nIs comment valid? {is_valid}")
    print(f"Reason: {reason}")
    print(f"Comment: {bad_comment}")

