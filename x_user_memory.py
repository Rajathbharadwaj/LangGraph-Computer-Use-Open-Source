"""
X Growth - User-Specific Long-Term Memory

Uses LangGraph Store with namespaces to persist user-specific data:
- User preferences (niche, tone, goals)
- Engagement history (who they've engaged with)
- Learning (what works, what doesn't)
- Account profiles (cached account research)

Namespace structure:
- (user_id, "preferences") - User settings
- (user_id, "engagement_history") - Past engagements
- (user_id, "learnings") - What works
- (user_id, "account_profiles") - Cached account research
"""

import uuid
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
from langgraph.store.memory import InMemoryStore
from langgraph.store.postgres import PostgresStore


# ============================================================================
# USER MEMORY SCHEMAS
# ============================================================================

@dataclass
class UserPreferences:
    """User-specific preferences for X growth"""
    user_id: str
    niche: List[str]  # e.g., ["AI", "LangChain", "agents"]
    target_audience: str  # e.g., "AI/ML practitioners"
    growth_goal: str  # e.g., "build authority", "grow followers"
    engagement_style: str  # e.g., "thoughtful_expert", "casual_friendly"
    tone: str  # e.g., "professional", "casual", "technical"
    daily_limits: Dict[str, int]  # e.g., {"likes": 50, "comments": 20}
    optimal_times: List[str]  # e.g., ["9-11am EST", "7-9pm EST"]
    avoid_topics: List[str]  # e.g., ["politics", "religion"]
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EngagementMemory:
    """Memory of a past engagement"""
    memory_id: str
    timestamp: str
    action: str  # "liked", "commented", "followed", "dm"
    target_username: str
    target_post_id: Optional[str]
    target_post_url: Optional[str]
    comment_text: Optional[str]
    result: str  # "success", "failed"
    engagement_received: Optional[int]  # likes/replies received
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AccountProfile:
    """Cached research about an account"""
    username: str
    follower_count: int
    engagement_rate: float
    quality_score: float
    niche_relevance: float
    last_researched: str
    engagement_count: int  # How many times we've engaged
    last_engagement: Optional[str]
    notes: str  # e.g., "High quality AI researcher, very responsive"
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Learning:
    """What the agent has learned"""
    learning_id: str
    timestamp: str
    category: str  # "engagement_strategy", "comment_style", "timing"
    insight: str  # e.g., "Questions get 2x more replies than statements"
    evidence: str  # e.g., "10 question comments got 20 replies, 10 statements got 10"
    confidence: float  # 0-1
    
    def to_dict(self) -> dict:
        return asdict(self)


# ============================================================================
# USER MEMORY MANAGER
# ============================================================================

class XUserMemory:
    """
    Manages user-specific long-term memory using LangGraph Store.
    
    Each user gets their own namespace for:
    - Preferences
    - Engagement history
    - Learnings
    - Account profiles
    """
    
    def __init__(self, store: InMemoryStore, user_id: str):
        """
        Initialize user memory manager
        
        Args:
            store: LangGraph Store (InMemoryStore or PostgresStore)
            user_id: Unique user identifier
        """
        self.store = store
        self.user_id = user_id
    
    # ========================================================================
    # PREFERENCES
    # ========================================================================
    
    def save_preferences(self, preferences: UserPreferences):
        """Save user preferences"""
        namespace = (self.user_id, "preferences")
        self.store.put(namespace, "current", preferences.to_dict())
    
    def get_preferences(self) -> Optional[UserPreferences]:
        """Get user preferences"""
        namespace = (self.user_id, "preferences")
        item = self.store.get(namespace, "current")
        if item:
            return UserPreferences(**item.value)
        return None
    
    # ========================================================================
    # ENGAGEMENT HISTORY
    # ========================================================================
    
    def save_engagement(self, engagement: EngagementMemory):
        """Save an engagement to history"""
        namespace = (self.user_id, "engagement_history")
        memory_id = engagement.memory_id or str(uuid.uuid4())
        self.store.put(namespace, memory_id, engagement.to_dict())
    
    def get_engagement_history(
        self,
        limit: int = 100,
        action: Optional[str] = None
    ) -> List[EngagementMemory]:
        """
        Get engagement history
        
        Args:
            limit: Max number of engagements to return
            action: Filter by action type (e.g., "liked", "commented")
        """
        namespace = (self.user_id, "engagement_history")
        
        # Search with filter if action specified
        if action:
            items = self.store.search(
                namespace,
                filter={"action": action},
                limit=limit
            )
        else:
            items = self.store.search(namespace, limit=limit)
        
        return [EngagementMemory(**item.value) for item in items]
    
    def check_already_engaged(
        self,
        username: str,
        post_id: Optional[str] = None
    ) -> bool:
        """
        Check if we've already engaged with this user/post
        
        Args:
            username: Target username
            post_id: Optional post ID
        
        Returns:
            True if already engaged
        """
        namespace = (self.user_id, "engagement_history")
        
        if post_id:
            # Check specific post
            items = self.store.search(
                namespace,
                filter={"target_post_id": post_id}
            )
        else:
            # Check user (any engagement)
            items = self.store.search(
                namespace,
                filter={"target_username": username}
            )
        
        return len(items) > 0
    
    def get_daily_stats(self, date: str = None) -> Dict[str, int]:
        """
        Get daily engagement stats
        
        Args:
            date: Date string (YYYY-MM-DD), defaults to today
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        namespace = (self.user_id, "engagement_history")
        
        # Get all engagements for this date
        items = self.store.search(namespace, limit=1000)
        
        # Filter by date and count
        stats = {"likes": 0, "comments": 0, "follows": 0, "dms": 0}
        for item in items:
            engagement = EngagementMemory(**item.value)
            if engagement.timestamp.startswith(date):
                action = engagement.action.lower()
                if action in stats:
                    stats[action] += 1
        
        return stats
    
    # ========================================================================
    # ACCOUNT PROFILES (Cached Research)
    # ========================================================================
    
    def save_account_profile(self, profile: AccountProfile):
        """Save researched account profile"""
        namespace = (self.user_id, "account_profiles")
        self.store.put(namespace, profile.username, profile.to_dict())
    
    def get_account_profile(self, username: str) -> Optional[AccountProfile]:
        """Get cached account profile"""
        namespace = (self.user_id, "account_profiles")
        item = self.store.get(namespace, username)
        if item:
            return AccountProfile(**item.value)
        return None
    
    def update_account_engagement(self, username: str):
        """Update engagement count for an account"""
        profile = self.get_account_profile(username)
        if profile:
            profile.engagement_count += 1
            profile.last_engagement = datetime.now().isoformat()
            self.save_account_profile(profile)
    
    # ========================================================================
    # LEARNINGS (What Works)
    # ========================================================================
    
    def save_learning(self, learning: Learning):
        """Save a learning/insight"""
        namespace = (self.user_id, "learnings")
        learning_id = learning.learning_id or str(uuid.uuid4())
        self.store.put(namespace, learning_id, learning.to_dict())
    
    def get_learnings(
        self,
        category: Optional[str] = None,
        min_confidence: float = 0.5
    ) -> List[Learning]:
        """
        Get learnings
        
        Args:
            category: Filter by category
            min_confidence: Minimum confidence threshold
        """
        namespace = (self.user_id, "learnings")
        
        if category:
            items = self.store.search(
                namespace,
                filter={"category": category}
            )
        else:
            items = self.store.search(namespace)
        
        # Filter by confidence
        learnings = [Learning(**item.value) for item in items]
        return [l for l in learnings if l.confidence >= min_confidence]
    
    def search_learnings(self, query: str) -> List[Learning]:
        """
        Semantic search for relevant learnings
        
        Args:
            query: Search query (e.g., "best time to post")
        """
        namespace = (self.user_id, "learnings")
        items = self.store.search(namespace, query=query)
        return [Learning(**item.value) for item in items]


# ============================================================================
# DEEPAGENT INTEGRATION
# ============================================================================

def create_agent_with_user_memory(user_id: str, store: InMemoryStore = None):
    """
    Create a DeepAgent with user-specific long-term memory
    
    Args:
        user_id: Unique user identifier
        store: LangGraph Store (creates InMemoryStore if not provided)
    
    Returns:
        Configured DeepAgent with long-term memory
    """
    from deepagents import create_deep_agent
    from x_growth_deep_agent import MAIN_AGENT_PROMPT
    from x_strategic_subagents import get_all_subagents
    
    # Create store if not provided
    if store is None:
        store = InMemoryStore()
    
    # Initialize user memory
    user_memory = XUserMemory(store, user_id)
    
    # Get user preferences
    preferences = user_memory.get_preferences()
    
    # Customize system prompt with user preferences
    custom_prompt = MAIN_AGENT_PROMPT
    if preferences:
        custom_prompt += f"""

USER PREFERENCES (from long-term memory):
- Niche: {', '.join(preferences.niche)}
- Target Audience: {preferences.target_audience}
- Growth Goal: {preferences.growth_goal}
- Engagement Style: {preferences.engagement_style}
- Daily Limits: {preferences.daily_limits}

IMPORTANT: Use these preferences to guide your strategy.
Access user memory via /memories/ filesystem:
- /memories/preferences.txt - User preferences
- /memories/engagement_history/ - Past engagements
- /memories/learnings/ - What works for this user
- /memories/account_profiles/ - Cached account research
"""
    
    # Create agent with long-term memory
    agent = create_deep_agent(
        store=store,
        use_longterm_memory=True,
        system_prompt=custom_prompt,
        tools=[],
        subagents=get_all_subagents()
    )
    
    return agent, user_memory


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    # Create store
    store = InMemoryStore()
    
    # Create user memory
    user_id = "user_123"
    user_memory = XUserMemory(store, user_id)
    
    # Save user preferences
    print("=" * 60)
    print("1. Saving User Preferences")
    print("=" * 60)
    preferences = UserPreferences(
        user_id=user_id,
        niche=["AI", "LangChain", "agents", "LLMs"],
        target_audience="AI/ML practitioners",
        growth_goal="build authority",
        engagement_style="thoughtful_expert",
        tone="professional",
        daily_limits={"likes": 50, "comments": 20, "follows": 10},
        optimal_times=["9-11am EST", "1-3pm EST", "7-9pm EST"],
        avoid_topics=["politics", "religion", "crypto scams"]
    )
    user_memory.save_preferences(preferences)
    print("✅ Preferences saved!")
    
    # Save engagement history
    print("\n" + "=" * 60)
    print("2. Saving Engagement History")
    print("=" * 60)
    engagement = EngagementMemory(
        memory_id=str(uuid.uuid4()),
        timestamp=datetime.now().isoformat(),
        action="commented",
        target_username="ai_researcher",
        target_post_id="123456",
        target_post_url="https://x.com/ai_researcher/status/123456",
        comment_text="Great insight about LangGraph subagents!",
        result="success",
        engagement_received=5
    )
    user_memory.save_engagement(engagement)
    print("✅ Engagement saved!")
    
    # Save account profile
    print("\n" + "=" * 60)
    print("3. Saving Account Profile")
    print("=" * 60)
    profile = AccountProfile(
        username="ai_researcher",
        follower_count=5000,
        engagement_rate=0.03,
        quality_score=0.85,
        niche_relevance=0.9,
        last_researched=datetime.now().isoformat(),
        engagement_count=1,
        last_engagement=datetime.now().isoformat(),
        notes="High quality AI researcher, very responsive to comments"
    )
    user_memory.save_account_profile(profile)
    print("✅ Account profile saved!")
    
    # Save learning
    print("\n" + "=" * 60)
    print("4. Saving Learning")
    print("=" * 60)
    learning = Learning(
        learning_id=str(uuid.uuid4()),
        timestamp=datetime.now().isoformat(),
        category="comment_style",
        insight="Questions get 2x more replies than statements",
        evidence="10 question comments got 20 replies, 10 statements got 10",
        confidence=0.8
    )
    user_memory.save_learning(learning)
    print("✅ Learning saved!")
    
    # Retrieve data
    print("\n" + "=" * 60)
    print("5. Retrieving Data")
    print("=" * 60)
    
    # Get preferences
    prefs = user_memory.get_preferences()
    print(f"\n📋 User Preferences:")
    print(f"   Niche: {prefs.niche}")
    print(f"   Goal: {prefs.growth_goal}")
    
    # Check if already engaged
    already_engaged = user_memory.check_already_engaged("ai_researcher", "123456")
    print(f"\n🔍 Already engaged with post? {already_engaged}")
    
    # Get daily stats
    stats = user_memory.get_daily_stats()
    print(f"\n📊 Daily Stats: {stats}")
    
    # Get account profile
    cached_profile = user_memory.get_account_profile("ai_researcher")
    print(f"\n👤 Cached Profile:")
    print(f"   Username: @{cached_profile.username}")
    print(f"   Quality Score: {cached_profile.quality_score}")
    print(f"   Engagement Count: {cached_profile.engagement_count}")
    
    # Get learnings
    learnings = user_memory.get_learnings(category="comment_style")
    print(f"\n💡 Learnings ({len(learnings)}):")
    for l in learnings:
        print(f"   - {l.insight} (confidence: {l.confidence})")
    
    print("\n" + "=" * 60)
    print("✅ All memory operations successful!")
    print("=" * 60)

