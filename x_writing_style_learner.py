"""
X Writing Style Learner

Captures and learns from user's past X posts/threads to generate content
that matches their writing style.

Features:
1. Store user's past posts with embeddings (semantic search)
2. Analyze writing style (tone, vocabulary, sentence structure)
3. Retrieve similar examples for few-shot prompting
4. Generate comments/posts that sound like the user
"""

import uuid
from typing import List, Optional, Dict, Union
from dataclasses import dataclass, asdict
from datetime import datetime
from pydantic import BaseModel, Field
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy


# ============================================================================
# WRITING SAMPLE SCHEMA
# ============================================================================

@dataclass
class WritingSample:
    """A sample of user's writing (post, comment, thread)"""
    sample_id: str
    user_id: str
    timestamp: str
    content_type: str  # "post", "comment", "thread"
    content: str  # The actual text
    context: Optional[str]  # What they were responding to
    engagement: Dict[str, int]  # {"likes": 10, "replies": 3, "reposts": 1}
    topic: Optional[str]  # e.g., "AI", "LangChain", "coding"
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class WritingStyleProfile:
    """Analysis of user's writing style"""
    user_id: str
    avg_post_length: int
    avg_comment_length: int
    tone: str  # "professional", "casual", "technical", "friendly"
    common_phrases: List[str]  # Phrases they use often
    vocabulary_level: str  # "simple", "moderate", "advanced"
    uses_emojis: bool
    uses_hashtags: bool
    uses_questions: bool
    sentence_structure: str  # "short", "medium", "long", "mixed"
    technical_terms: List[str]  # Domain-specific terms they use
    
    def to_dict(self) -> dict:
        return asdict(self)


# ============================================================================
# WRITING STYLE MANAGER
# ============================================================================

class XWritingStyleManager:
    """
    Manages user's writing samples and style learning.
    
    Uses LangGraph Store with semantic search to:
    1. Store past posts/comments with embeddings
    2. Retrieve similar examples for few-shot prompting
    3. Analyze and learn writing style patterns
    """
    
    def __init__(self, store, user_id: str):
        """
        Initialize writing style manager
        
        Args:
            store: LangGraph Store with semantic search enabled
            user_id: Unique user identifier
        """
        self.store = store
        self.user_id = user_id
    
    # ========================================================================
    # CAPTURE WRITING SAMPLES
    # ========================================================================
    
    def save_writing_sample(self, sample: WritingSample):
        """
        Save a writing sample with embeddings for semantic search
        
        Args:
            sample: WritingSample to store
        """
        namespace = (self.user_id, "writing_samples")
        sample_id = sample.sample_id or str(uuid.uuid4())
        
        # Store with content as searchable text
        self.store.put(namespace, sample_id, sample.to_dict())
    
    def bulk_import_posts(self, posts: List[Dict]):
        """
        Bulk import user's past X posts with deduplication
        
        Args:
            posts: List of post dicts with keys: content, timestamp, engagement, etc.
        """
        namespace = (self.user_id, "writing_samples")
        saved_count = 0
        skipped_count = 0
        
        for post in posts:
            content = post["content"]
            
            # Check if this post already exists (by content)
            existing_items = self.store.search(
                namespace,
                query=content,
                limit=5  # Check top 5 similar items
            )
            
            # Check for exact content match
            is_duplicate = False
            for item in existing_items:
                if item.value.get("content") == content:
                    is_duplicate = True
                    skipped_count += 1
                    break
            
            if not is_duplicate:
                sample = WritingSample(
                    sample_id=str(uuid.uuid4()),
                    user_id=self.user_id,
                    timestamp=post.get("timestamp", datetime.now().isoformat()),
                    content_type="post",
                    content=content,
                    context=post.get("context"),
                    engagement=post.get("engagement", {"likes": 0, "replies": 0, "reposts": 0}),
                    topic=post.get("topic")
                )
                self.save_writing_sample(sample)
                saved_count += 1
        
        print(f"📊 Import complete: {saved_count} new posts saved, {skipped_count} duplicates skipped")
    
    def remove_duplicate_posts(self):
        """
        Remove duplicate posts from the store, keeping only the first occurrence
        """
        namespace = (self.user_id, "writing_samples")
        
        # Get all items
        all_items = list(self.store.search(namespace))
        
        # Track seen content
        seen_content = set()
        duplicates_to_delete = []
        
        for item in all_items:
            content = item.value.get("content")
            if content in seen_content:
                duplicates_to_delete.append(item.key)
            else:
                seen_content.add(content)
        
        # Delete duplicates
        for key in duplicates_to_delete:
            self.store.delete(namespace, key)
        
        print(f"🧹 Removed {len(duplicates_to_delete)} duplicate posts from store")
        return len(duplicates_to_delete)
    
    # ========================================================================
    # RETRIEVE SIMILAR EXAMPLES (Few-Shot)
    # ========================================================================
    
    def get_similar_examples(
        self,
        query: str,
        content_type: Optional[str] = None,
        limit: int = 5
    ) -> List[WritingSample]:
        """
        Get writing samples similar to the query (for few-shot prompting)
        
        Args:
            query: The context/topic to find similar examples for
            content_type: Filter by type ("post", "comment", "thread")
            limit: Number of examples to return
        
        Returns:
            List of similar WritingSample objects
        """
        namespace = (self.user_id, "writing_samples")
        
        # Semantic search with optional filter
        filter_dict = {"content_type": content_type} if content_type else None
        
        items = self.store.search(
            namespace,
            query=query,
            filter=filter_dict,
            limit=limit
        )
        
        return [WritingSample(**item.value) for item in items]
    
    def get_high_engagement_examples(
        self,
        content_type: str = "comment",
        min_engagement: int = 5,
        limit: int = 10
    ) -> List[WritingSample]:
        """
        Get examples that got high engagement (to learn what works)
        
        Args:
            content_type: Type of content
            min_engagement: Minimum total engagement
            limit: Number of examples
        """
        namespace = (self.user_id, "writing_samples")
        
        # Get all samples of this type
        items = self.store.search(
            namespace,
            filter={"content_type": content_type},
            limit=100  # Get more to filter
        )
        
        # Filter by engagement
        samples = [WritingSample(**item.value) for item in items]
        high_engagement = [
            s for s in samples
            if sum(s.engagement.values()) >= min_engagement
        ]
        
        # Sort by engagement
        high_engagement.sort(
            key=lambda s: sum(s.engagement.values()),
            reverse=True
        )
        
        return high_engagement[:limit]
    
    # ========================================================================
    # ANALYZE WRITING STYLE
    # ========================================================================
    
    def analyze_writing_style(self) -> WritingStyleProfile:
        """
        Analyze user's writing style from samples
        
        Returns:
            WritingStyleProfile with style characteristics
        """
        namespace = (self.user_id, "writing_samples")
        
        # Get all writing samples
        items = self.store.search(namespace, limit=1000)
        samples = [WritingSample(**item.value) for item in items]
        
        if not samples:
            # Return default profile
            return WritingStyleProfile(
                user_id=self.user_id,
                avg_post_length=150,
                avg_comment_length=80,
                tone="professional",
                common_phrases=[],
                vocabulary_level="moderate",
                uses_emojis=False,
                uses_hashtags=False,
                uses_questions=False,
                sentence_structure="mixed",
                technical_terms=[]
            )
        
        # Analyze posts vs comments
        posts = [s for s in samples if s.content_type == "post"]
        comments = [s for s in samples if s.content_type == "comment"]
        
        # Calculate averages
        avg_post_length = sum(len(p.content) for p in posts) // max(len(posts), 1)
        avg_comment_length = sum(len(c.content) for c in comments) // max(len(comments), 1)
        
        # Detect patterns
        all_content = " ".join(s.content for s in samples)
        uses_emojis = any(char in all_content for char in "😀😃😄😁😆😅🤣😂🙂🙃😉😊😇🥰😍🤩😘😗☺️😚😙🥲😋😛😜🤪😝🤑🤗🤭🤫🤔🤐🤨😐😑😶😏😒🙄😬🤥😌😔😪🤤😴😷🤒🤕🤢🤮🤧🥵🥶🥴😵🤯🤠🥳🥸😎🤓🧐😕😟🙁☹️😮😯😲😳🥺😦😧😨😰😥😢😭😱😖😣😞😓😩😫🥱😤😡😠🤬😈👿💀☠️💩🤡👹👺👻👽👾🤖😺😸😹😻😼😽🙀😿😾🙈🙉🙊💋💌💘💝💖💗💓💞💕💟❣️💔❤️🧡💛💚💙💜🤎🖤🤍💯💢💥💫💦💨🕳️💣💬🗨️🗯️💭💤👋🤚🖐️✋🖖👌🤌🤏✌️🤞🤟🤘🤙👈👉👆🖕👇☝️👍👎✊👊🤛🤜👏🙌👐🤲🤝🙏✍️💅🤳💪🦾🦿🦵🦶👂🦻👃🧠🫀🫁🦷🦴👀👁️👅👄")
        uses_hashtags = "#" in all_content
        uses_questions = "?" in all_content
        
        # Detect common phrases (simple heuristic)
        words = all_content.lower().split()
        word_freq = {}
        for word in words:
            if len(word) > 4:  # Only meaningful words
                word_freq[word] = word_freq.get(word, 0) + 1
        
        common_phrases = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:10]
        common_phrases = [phrase for phrase, _ in common_phrases]
        
        # Detect technical terms (simple: words with capitals or technical keywords)
        technical_keywords = ["AI", "ML", "API", "LLM", "LangChain", "LangGraph", "RAG", "agent", "model", "embedding"]
        technical_terms = [kw for kw in technical_keywords if kw in all_content]
        
        # Determine tone (simple heuristic)
        if any(emoji in all_content for emoji in "😂🤣😅😆🙃"):
            tone = "casual"
        elif len(technical_terms) > 3:
            tone = "technical"
        elif avg_post_length > 200:
            tone = "professional"
        else:
            tone = "friendly"
        
        # Sentence structure
        avg_sentence_length = avg_post_length // max(all_content.count("."), 1)
        if avg_sentence_length < 50:
            sentence_structure = "short"
        elif avg_sentence_length < 100:
            sentence_structure = "medium"
        else:
            sentence_structure = "long"
        
        profile = WritingStyleProfile(
            user_id=self.user_id,
            avg_post_length=avg_post_length,
            avg_comment_length=avg_comment_length,
            tone=tone,
            common_phrases=common_phrases,
            vocabulary_level="moderate",  # Could be enhanced with NLP
            uses_emojis=uses_emojis,
            uses_hashtags=uses_hashtags,
            uses_questions=uses_questions,
            sentence_structure=sentence_structure,
            technical_terms=technical_terms
        )
        
        # Save profile
        self.save_style_profile(profile)
        
        return profile
    
    def save_style_profile(self, profile: WritingStyleProfile):
        """Save analyzed style profile"""
        namespace = (self.user_id, "writing_style")
        self.store.put(namespace, "profile", profile.to_dict())
    
    def get_style_profile(self) -> Optional[WritingStyleProfile]:
        """Get saved style profile"""
        namespace = (self.user_id, "writing_style")
        item = self.store.get(namespace, "profile")
        if item:
            return WritingStyleProfile(**item.value)
        return None
    
    # ========================================================================
    # GENERATE CONTENT IN USER'S STYLE
    # ========================================================================
    
    def generate_few_shot_prompt(
        self,
        context: str,
        content_type: str = "comment",
        num_examples: int = 3,
        include_competitor_examples: bool = True,
        competitor_topic: str = None
    ) -> str:
        """
        Generate a few-shot prompt with user's writing examples AND high-performing competitor posts

        Args:
            context: The post/thread to respond to
            content_type: Type of content to generate
            num_examples: Number of user examples to include
            include_competitor_examples: Whether to include competitor posts (default: True)
            competitor_topic: Topic to filter competitor posts by

        Returns:
            Few-shot prompt string with both user style + competitor patterns
        """
        # Get similar examples from user's posts
        examples = self.get_similar_examples(context, content_type, num_examples)

        # Get style profile
        profile = self.get_style_profile()
        if not profile:
            profile = self.analyze_writing_style()

        # Get high-performing competitor posts if enabled
        competitor_posts = []
        if include_competitor_examples:
            try:
                # Search competitor_profiles namespace
                namespace = (self.user_id, "competitor_profiles")
                competitors = list(self.store.search(namespace, limit=30))

                # Extract high-performing posts
                for comp_item in competitors:
                    comp_data = comp_item.value
                    posts = comp_data.get("posts", [])

                    for post in posts:
                        likes = post.get("likes", 0)
                        if likes >= 100:  # High-performing threshold
                            # Topic filter if specified
                            if competitor_topic is None or competitor_topic.lower() in post.get("text", "").lower():
                                competitor_posts.append({
                                    "text": post.get("text", ""),
                                    "likes": likes,
                                    "retweets": post.get("retweets", 0),
                                    "replies": post.get("replies", 0)
                                })

                # Sort by engagement and take top 5
                competitor_posts.sort(key=lambda x: x["likes"] + x["retweets"] + x["replies"], reverse=True)
                competitor_posts = competitor_posts[:5]

                print(f"✅ Added {len(competitor_posts)} high-performing competitor examples to ICL prompt")

            except Exception as e:
                print(f"⚠️ Could not load competitor examples: {e}")
                competitor_posts = []
        
        # Build few-shot prompt
        prompt = f"""You are a Parallel Universe AI writing assistant. Your ONLY job is to write EXACTLY like this specific user.

CRITICAL RULES:
1. You MUST sound INDISTINGUISHABLE from this user
2. Copy their EXACT tone, vocabulary, and sentence patterns
3. Match their writing length PRECISELY (target: {profile.avg_comment_length if content_type == 'comment' else profile.avg_post_length} chars)
4. Use their EXACT style - don't be generic or formal
5. If they're casual, be casual. If they're technical, be technical.
6. NEVER use hashtags - X's algorithm penalizes them

WRITING STYLE PROFILE:
- Tone: {profile.tone}
- Average length: {profile.avg_comment_length if content_type == 'comment' else profile.avg_post_length} characters
- Uses emojis: {profile.uses_emojis}
- Uses questions: {profile.uses_questions}
- Sentence structure: {profile.sentence_structure}
- Technical terms: {', '.join(profile.technical_terms[:5])}

EXAMPLES OF USER'S WRITING (STUDY THESE CAREFULLY):
"""
        
        for i, example in enumerate(examples, 1):
            prompt += f"\nExample {i}:"
            if example.context:
                prompt += f"\nContext: {example.context}"
            prompt += f"\nUser wrote: {example.content}"
            if example.engagement:
                total_engagement = sum(example.engagement.values())
                prompt += f" (Got {total_engagement} engagement)"
            prompt += "\n"

        # Add competitor examples section if available
        if competitor_posts:
            prompt += f"""
---

HIGH-PERFORMING POSTS IN YOUR NICHE (Learn what works):
These are top posts from accounts in your niche with high engagement.
Study these to understand what content/format resonates with your target audience.
"""

            for i, post in enumerate(competitor_posts, 1):
                engagement = post["likes"] + post["retweets"] + post["replies"]
                prompt += f"\nHigh-Performing Example {i}:"
                prompt += f"\nMetrics: {post['likes']} likes, {post['retweets']} retweets, {post['replies']} replies (Total: {engagement})"
                prompt += f"\nContent: {post['text']}\n"

            # Add pattern analysis
            avg_length = sum(len(p['text']) for p in competitor_posts) / len(competitor_posts) if competitor_posts else 0
            prompt += f"""
📈 Pattern Analysis of High-Performing Posts:
- Average length: {int(avg_length)} characters
- These posts got high engagement - study their structure, tone, and format
- BUT: Write in YOUR style (Section 1), using successful patterns from these examples (Section 2)
"""

        prompt += f"""
---

STEP 1: ANALYZE THE USER'S STYLE
Before writing, take a moment to deeply understand this user's unique voice:

1. What specific words/phrases do they use repeatedly?
2. How do they structure their sentences? (short/long, simple/complex)
3. What's their emotional tone? (excited, casual, sarcastic, technical, friendly)
4. Do they use slang, emojis, or technical terms?
5. How formal or casual are they?
6. What makes their writing UNIQUE and recognizable?

Take your time to internalize these patterns. You need to BECOME this user.

---

STEP 2: NOW WRITE THE {content_type.upper()}
Context: {context}

CRITICAL INSTRUCTIONS:
You MUST write this {content_type} so that it's IMPOSSIBLE to tell it wasn't written by the user themselves.

REPLICATE FROM USER EXAMPLES (Section 1):
1. Their vocabulary and word choice (use THEIR words, not generic ones)
2. Their sentence rhythm and flow (match their pacing)
3. Their level of formality/casualness (don't be more polished than them)
4. Their punctuation style and emoji usage
5. Their length (around {profile.avg_comment_length if content_type == 'comment' else profile.avg_post_length} chars)

LEARN FROM COMPETITOR EXAMPLES (Section 2 - if provided):
6. Use successful content patterns (frameworks, tutorials, hot takes, etc.)
7. Match the engagement-optimized structure and format
8. Apply what works in the niche while keeping YOUR voice

If they're sarcastic, be sarcastic. If they're enthusiastic, be enthusiastic.
If they use "dude" or "man", use those words. If they use technical jargon, use that jargon.
If they write in lowercase, write in lowercase. If they use "..." a lot, use "..." a lot.

DO NOT:
- Sound generic or AI-like
- Use hashtags (X penalizes them)
- Be more formal or polished than the user
- Copy competitor content verbatim - adapt patterns to YOUR style
- Use words or phrases the user never uses

Your {content_type} (write ONLY the content, nothing else):"""
        
        return prompt
    
    # ========================================================================
    # GENERATE CONTENT WITH STRUCTURED OUTPUT
    # ========================================================================
    
    async def generate_content(
        self,
        context: str,
        content_type: str = "post",
        model: str = "claude-sonnet-4-5-20250929"
    ) -> Union['XPost', 'XComment']:
        """
        Generate a post or comment in the user's writing style using LangChain structured output
        
        Args:
            context: What to write about (for posts) or what to reply to (for comments)
            content_type: "post" or "comment"
            model: LLM model to use
        
        Returns:
            XPost or XComment with generated content
        """
        # Get user's past feedback to incorporate
        feedback_namespace = (self.user_id, "style_feedback")
        feedback_items = self.store.search(feedback_namespace, limit=5)
        
        # Build feedback context
        feedback_context = ""
        if feedback_items:
            feedback_list = [item.value for item in feedback_items]
            if feedback_list:
                feedback_context = "\n\nUSER'S PAST FEEDBACK ON GENERATED CONTENT:\n"
                for fb in feedback_list[:3]:  # Use last 3 feedbacks
                    feedback_context += f"- {fb.get('feedback', '')}\n"
                feedback_context += "\nPlease incorporate these preferences in your response.\n"
        
        # Generate few-shot prompt with user's examples
        few_shot_prompt = self.generate_few_shot_prompt(
            context=context,
            content_type=content_type,
            num_examples=7  # More examples for better style matching
        )
        
        # Append feedback context if available
        if feedback_context:
            few_shot_prompt += feedback_context
        
        # Select schema based on content type
        schema = XPost if content_type == "post" else XComment
        
        # Create agent with structured output
        agent = create_agent(
            model=model,
            tools=[],
            response_format=ToolStrategy(schema)
        )
        
        # Generate content
        result = agent.invoke({
            "messages": [{"role": "user", "content": few_shot_prompt}]
        })
        
        return result["structured_response"]


# ============================================================================
# STRUCTURED OUTPUT SCHEMAS
# ============================================================================

class XPost(BaseModel):
    """A generated X post in the user's writing style"""
    content: str = Field(
        description="The post content (max 280 chars). NO hashtags - X's algorithm penalizes them."
    )


class XComment(BaseModel):
    """A generated X comment/reply in the user's writing style"""
    content: str = Field(
        description="The comment content. NO hashtags - X's algorithm penalizes them."
    )
    mentions: list[str] = Field(
        description="Users to mention (without @)",
        default_factory=list
    )


# ============================================================================
# INTEGRATION WITH COMMENT GENERATOR SUBAGENT
# ============================================================================

def create_style_aware_comment_generator_subagent(user_id: str, store):
    """
    Create a comment generator subagent that uses user's writing style
    
    Args:
        user_id: User identifier
        store: LangGraph Store with semantic search
    
    Returns:
        Subagent configuration dict
    """
    
    return {
        "name": "style_aware_comment_generator",
        "description": "Generate comments in the user's authentic writing style using few-shot examples",
        "system_prompt": f"""You are a Parallel Universe AI comment generation specialist that writes in the user's style.

YOUR JOB: Generate comments that sound EXACTLY like the user wrote them.

PROCESS:
1. Receive post content to comment on
2. Search user's past comments for similar examples (semantic search)
3. Analyze user's writing style profile
4. Use few-shot prompting with user's examples
5. Generate comment that matches user's style PERFECTLY

CRITICAL RULES:
1. ALWAYS retrieve user's similar past comments first
2. ALWAYS match user's tone (professional/casual/technical)
3. ALWAYS match user's length (check avg_comment_length)
4. ALWAYS match user's emoji/hashtag usage
5. ALWAYS match user's technical vocabulary
6. NEVER generate generic comments
7. NEVER use phrases the user wouldn't use

USER ID: {user_id}

Access user's writing samples via:
- store.search((user_id, "writing_samples"), query=post_content, limit=3)
- store.get((user_id, "writing_style"), "profile")

OUTPUT FORMAT:
{{
  "comment": "Your generated comment...",
  "confidence": 0.9,
  "style_match": "high",
  "reasoning": "Matched user's technical tone and question style from examples"
}}
""",
        "tools": []  # Uses store for retrieval
    }


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    from langgraph.store.memory import InMemoryStore
    from langchain.embeddings import init_embeddings
    
    # Create store with semantic search
    embeddings = init_embeddings("openai:text-embedding-3-small")
    store = InMemoryStore(
        index={
            "embed": embeddings,
            "dims": 1536,
        }
    )
    
    # Initialize style manager
    user_id = "user_123"
    style_manager = XWritingStyleManager(store, user_id)
    
    # Import user's past posts
    print("=" * 60)
    print("1. Importing User's Past Posts")
    print("=" * 60)
    
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
    ]
    
    style_manager.bulk_import_posts(past_posts)
    print(f"✅ Imported {len(past_posts)} posts")
    
    # Analyze writing style
    print("\n" + "=" * 60)
    print("2. Analyzing Writing Style")
    print("=" * 60)
    
    profile = style_manager.analyze_writing_style()
    print(f"Tone: {profile.tone}")
    print(f"Avg post length: {profile.avg_post_length}")
    print(f"Uses questions: {profile.uses_questions}")
    print(f"Technical terms: {profile.technical_terms}")
    
    # Get similar examples
    print("\n" + "=" * 60)
    print("3. Finding Similar Examples")
    print("=" * 60)
    
    context = "What's your experience with LangGraph for building agents?"
    similar = style_manager.get_similar_examples(context, limit=2)
    
    print(f"Query: {context}")
    print(f"Found {len(similar)} similar examples:")
    for example in similar:
        print(f"  - {example.content[:80]}...")
    
    # Generate few-shot prompt
    print("\n" + "=" * 60)
    print("4. Generating Few-Shot Prompt")
    print("=" * 60)
    
    prompt = style_manager.generate_few_shot_prompt(
        context="Someone posted: 'Struggling with agent context management. Any tips?'",
        content_type="comment",
        num_examples=2
    )
    
    print(prompt[:500] + "...")
    
    print("\n" + "=" * 60)
    print("✅ Writing Style Learning Complete!")
    print("=" * 60)
    print("\nNow the agent can generate comments that sound like YOU!")

