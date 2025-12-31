"""
X Writing Style Learner

Captures and learns from user's past X posts/threads to generate content
that matches their writing style.

Features:
1. Store user's past posts with embeddings (semantic search)
2. Analyze writing style (tone, vocabulary, sentence structure)
3. Retrieve similar examples for few-shot prompting
4. Generate comments/posts that sound like the user
5. Deep style analysis with NLP (spaCy, NLTK, textstat)
6. Multi-word phrase extraction (bigrams/trigrams)
7. Time-weighted example retrieval
8. Integration with feedback processor and style grader
"""

import uuid
import re
import math
from typing import List, Optional, Dict, Union, Tuple
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from collections import Counter
from pydantic import BaseModel, Field
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy

# NLP imports - graceful fallback if not installed
try:
    import spacy
    SPACY_AVAILABLE = True
except ImportError:
    SPACY_AVAILABLE = False
    spacy = None

try:
    import nltk
    from nltk.util import ngrams
    from nltk.corpus import stopwords
    NLTK_AVAILABLE = True
except ImportError:
    NLTK_AVAILABLE = False
    nltk = None

try:
    import textstat
    TEXTSTAT_AVAILABLE = True
except ImportError:
    TEXTSTAT_AVAILABLE = False
    textstat = None

# Local imports for style system integration
try:
    from banned_patterns_manager import BannedPatternsManager
    from feedback_processor import FeedbackProcessor
    from style_match_scorer import StyleMatchScorer, LLMStyleGrader
    from style_evolution_tracker import StyleEvolutionTracker
    STYLE_SYSTEM_AVAILABLE = True
except ImportError:
    STYLE_SYSTEM_AVAILABLE = False


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

    # NEW: Thread context for comments (enables context-aware generation)
    thread_context: Optional[List[Dict]] = None  # Full conversation chain
    parent_author: Optional[str] = None  # Who they're replying to
    thread_depth: int = 0  # 0=post, 1=reply, 2=reply-to-reply

    # NEW: Source tracking for analytics
    source: str = "manual"  # "import", "manual", "scraped"

    def to_dict(self) -> dict:
        return asdict(self)

    def get_total_engagement(self) -> int:
        """Calculate total engagement score"""
        return sum(self.engagement.values()) if self.engagement else 0

    def get_age_days(self) -> float:
        """Get age in days from timestamp"""
        try:
            ts = datetime.fromisoformat(self.timestamp.replace('Z', '+00:00'))
            return (datetime.now(ts.tzinfo) - ts).days
        except:
            return 0.0


@dataclass
class WritingStyleProfile:
    """Analysis of user's writing style (basic profile for backwards compatibility)"""
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


@dataclass
class DeepStyleProfile:
    """
    Enhanced style analysis with NLP-powered multi-dimensional analysis.

    This profile captures the nuanced aspects of a user's writing style
    that make their content uniquely identifiable.
    """
    user_id: str

    # Basic metrics (from WritingStyleProfile)
    avg_post_length: int = 0
    avg_comment_length: int = 0

    # Multi-dimensional tone scores (LLM-analyzed)
    tone_scores: Dict[str, float] = field(default_factory=lambda: {
        "professional": 0.0,
        "casual": 0.0,
        "technical": 0.0,
        "sarcastic": 0.0,
        "enthusiastic": 0.0,
        "analytical": 0.0,
        "friendly": 0.0
    })
    primary_tone: str = "neutral"

    # Vocabulary analysis
    vocabulary_complexity: float = 0.5  # 0-1 based on readability scores
    vocabulary_richness: float = 0.5  # Type-token ratio
    domain_vocabulary: List[str] = field(default_factory=list)  # Auto-extracted technical terms
    colloquialisms: List[str] = field(default_factory=list)  # Slang, informal expressions
    filler_words: List[str] = field(default_factory=list)  # "like", "basically", "honestly"

    # Multi-word patterns (the key differentiator)
    signature_phrases: List[str] = field(default_factory=list)  # Unique bigrams/trigrams
    common_bigrams: List[Tuple[str, int]] = field(default_factory=list)  # Top bigrams with counts
    common_trigrams: List[Tuple[str, int]] = field(default_factory=list)  # Top trigrams with counts

    # Sentence structure patterns
    avg_sentence_length: float = 0.0  # In words
    sentence_length_variance: float = 0.0  # How much length varies
    avg_words_per_sentence: float = 0.0

    # Punctuation and formatting patterns
    punctuation_patterns: Dict[str, float] = field(default_factory=lambda: {
        "ellipsis": 0.0,  # "..."
        "exclamation": 0.0,  # "!"
        "question": 0.0,  # "?"
        "dash": 0.0,  # "-" or "—"
        "comma_heavy": 0.0  # frequent comma usage
    })
    capitalization_style: str = "standard"  # "standard", "lowercase", "mixed", "shouty"

    # Emoji and hashtag patterns
    uses_emojis: bool = False
    emoji_frequency: float = 0.0  # emojis per post
    common_emojis: List[str] = field(default_factory=list)
    uses_hashtags: bool = False
    hashtag_frequency: float = 0.0

    # Engagement patterns
    avg_engagement_score: float = 0.0
    high_engagement_characteristics: List[str] = field(default_factory=list)

    # Versioning for drift detection
    style_version: str = "1.0"
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())
    sample_count: int = 0

    def to_dict(self) -> dict:
        """Convert to dictionary with serializable values"""
        result = asdict(self)
        # Convert tuples to lists for JSON serialization
        result["common_bigrams"] = [[b, c] for b, c in self.common_bigrams]
        result["common_trigrams"] = [[t, c] for t, c in self.common_trigrams]
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "DeepStyleProfile":
        """Create from dictionary"""
        # Convert lists back to tuples for bigrams/trigrams
        if "common_bigrams" in data and data["common_bigrams"]:
            data["common_bigrams"] = [(b, c) for b, c in data["common_bigrams"]]
        if "common_trigrams" in data and data["common_trigrams"]:
            data["common_trigrams"] = [(t, c) for t, c in data["common_trigrams"]]
        return cls(**data)

    def get_style_summary(self) -> str:
        """Generate a human-readable style summary for prompts"""
        summary = f"""DEEP STYLE PROFILE:
- Primary tone: {self.primary_tone}
- Tone scores: {', '.join(f'{k}={v:.1%}' for k, v in self.tone_scores.items() if v > 0.1)}
- Vocabulary complexity: {'simple' if self.vocabulary_complexity < 0.3 else 'moderate' if self.vocabulary_complexity < 0.7 else 'advanced'}
- Average sentence length: {self.avg_words_per_sentence:.1f} words
- Capitalization: {self.capitalization_style}
- Uses emojis: {self.uses_emojis} ({self.emoji_frequency:.1f}/post)
- Signature phrases: {', '.join(self.signature_phrases[:5]) if self.signature_phrases else 'None detected'}
- Domain terms: {', '.join(self.domain_vocabulary[:5]) if self.domain_vocabulary else 'None detected'}
- Colloquialisms: {', '.join(self.colloquialisms[:5]) if self.colloquialisms else 'None detected'}
"""
        return summary

    def to_basic_profile(self) -> WritingStyleProfile:
        """Convert to basic WritingStyleProfile for backwards compatibility"""
        return WritingStyleProfile(
            user_id=self.user_id,
            avg_post_length=self.avg_post_length,
            avg_comment_length=self.avg_comment_length,
            tone=self.primary_tone,
            common_phrases=self.signature_phrases[:10],
            vocabulary_level="simple" if self.vocabulary_complexity < 0.3 else "moderate" if self.vocabulary_complexity < 0.7 else "advanced",
            uses_emojis=self.uses_emojis,
            uses_hashtags=self.uses_hashtags,
            uses_questions=self.punctuation_patterns.get("question", 0) > 0.1,
            sentence_structure="short" if self.avg_words_per_sentence < 10 else "medium" if self.avg_words_per_sentence < 20 else "long",
            technical_terms=self.domain_vocabulary[:10]
        )


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

    def get_all_posts(self) -> List[Dict]:
        """
        Get all posts from the store for this user.

        Returns:
            List of post dictionaries with content, timestamp, engagement, etc.
        """
        namespace = (self.user_id, "writing_samples")
        all_items = list(self.store.search(namespace, limit=1000))
        return [item.value for item in all_items]
    
    # ========================================================================
    # RETRIEVE SIMILAR EXAMPLES (Few-Shot)
    # ========================================================================
    
    def get_similar_examples(
        self,
        query: str,
        content_type: Optional[str] = None,
        limit: int = 5,
        recency_weight: float = 0.3,
        engagement_weight: float = 0.2,
        topic: Optional[str] = None
    ) -> List[WritingSample]:
        """
        Get writing samples similar to the query with multi-factor ranking.

        The ranking combines:
        - Semantic similarity (50% weight by default)
        - Recency (30% weight by default) - recent posts are more representative
        - Engagement (20% weight by default) - high-performing content patterns

        Args:
            query: The context/topic to find similar examples for
            content_type: Filter by type ("post", "comment", "thread")
            limit: Number of examples to return
            recency_weight: Weight for recency scoring (0-1)
            engagement_weight: Weight for engagement scoring (0-1)
            topic: Optional topic filter

        Returns:
            List of similar WritingSample objects, ranked by combined score
        """
        namespace = (self.user_id, "writing_samples")

        # Semantic search with optional filter - get more than needed for reranking
        filter_dict = {"content_type": content_type} if content_type else None

        items = self.store.search(
            namespace,
            query=query,
            filter=filter_dict,
            limit=limit * 3  # Get more for reranking
        )

        # Convert to WritingSample objects
        samples = []
        for item in items:
            try:
                # Handle missing fields gracefully
                value = item.value
                sample = WritingSample(
                    sample_id=value.get("sample_id", ""),
                    user_id=value.get("user_id", self.user_id),
                    timestamp=value.get("timestamp", datetime.now().isoformat()),
                    content_type=value.get("content_type", "post"),
                    content=value.get("content", ""),
                    context=value.get("context"),
                    engagement=value.get("engagement", {"likes": 0, "replies": 0, "reposts": 0}),
                    topic=value.get("topic"),
                    thread_context=value.get("thread_context"),
                    parent_author=value.get("parent_author"),
                    thread_depth=value.get("thread_depth", 0),
                    source=value.get("source", "manual")
                )
                samples.append(sample)
            except Exception as e:
                print(f"⚠️ Error parsing sample: {e}")
                continue

        if not samples:
            return []

        # Calculate multi-factor scores
        semantic_weight = 1.0 - recency_weight - engagement_weight
        now = datetime.now()

        def calculate_combined_score(sample: WritingSample, rank: int) -> float:
            # Semantic score based on search rank (higher rank = higher score)
            semantic_score = 1.0 - (rank / (len(samples) + 1))

            # Recency score (exponential decay)
            try:
                ts = datetime.fromisoformat(sample.timestamp.replace('Z', '+00:00'))
                days_old = (now - ts.replace(tzinfo=None)).days if ts.tzinfo else (now - ts).days
                recency_score = math.exp(-days_old / 90)  # 90-day half-life
            except:
                recency_score = 0.5

            # Engagement score (normalized)
            total_engagement = sum(sample.engagement.values()) if sample.engagement else 0
            engagement_score = min(1.0, total_engagement / 50)  # Cap at 50 engagement

            # Combined score
            return (
                semantic_weight * semantic_score +
                recency_weight * recency_score +
                engagement_weight * engagement_score
            )

        # Score and sort samples
        scored_samples = [
            (sample, calculate_combined_score(sample, i))
            for i, sample in enumerate(samples)
        ]
        scored_samples.sort(key=lambda x: x[1], reverse=True)

        # Return top N
        return [sample for sample, score in scored_samples[:limit]]

    def get_similar_examples_simple(
        self,
        query: str,
        content_type: Optional[str] = None,
        limit: int = 5
    ) -> List[WritingSample]:
        """
        Simple semantic search without reranking (for backwards compatibility).

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
    # DEEP STYLE ANALYSIS (NLP-Powered)
    # ========================================================================

    def deep_analyze_writing_style(
        self,
        use_llm_for_tone: bool = True,
        anthropic_client=None
    ) -> DeepStyleProfile:
        """
        Perform deep NLP-powered analysis of user's writing style.

        This method uses spaCy, NLTK, and textstat to extract:
        - Multi-word signature phrases (bigrams/trigrams)
        - Vocabulary complexity and richness
        - Punctuation and capitalization patterns
        - Sentence structure analysis
        - Domain-specific vocabulary via TF-IDF
        - Multi-dimensional tone analysis (via LLM if enabled)

        Args:
            use_llm_for_tone: Whether to use Claude for tone analysis
            anthropic_client: Anthropic client for LLM tone analysis

        Returns:
            DeepStyleProfile with comprehensive style analysis
        """
        namespace = (self.user_id, "writing_samples")

        # Get all writing samples
        items = self.store.search(namespace, limit=1000)
        samples = []
        for item in items:
            try:
                samples.append(WritingSample(**item.value))
            except:
                continue

        if not samples:
            return DeepStyleProfile(user_id=self.user_id)

        # Separate posts and comments
        posts = [s for s in samples if s.content_type == "post"]
        comments = [s for s in samples if s.content_type == "comment"]
        all_content = [s.content for s in samples]

        # Initialize profile
        profile = DeepStyleProfile(user_id=self.user_id)
        profile.sample_count = len(samples)

        # ============================================================
        # 1. BASIC LENGTH METRICS
        # ============================================================
        profile.avg_post_length = sum(len(p.content) for p in posts) // max(len(posts), 1)
        profile.avg_comment_length = sum(len(c.content) for c in comments) // max(len(comments), 1)

        # ============================================================
        # 2. VOCABULARY COMPLEXITY (using textstat if available)
        # ============================================================
        combined_text = " ".join(all_content)

        if TEXTSTAT_AVAILABLE:
            # Flesch Reading Ease: 0-30 = very difficult, 60-70 = standard, 90-100 = very easy
            # We invert it to 0-1 complexity score
            flesch_score = textstat.flesch_reading_ease(combined_text)
            profile.vocabulary_complexity = max(0, min(1, (100 - flesch_score) / 100))

            # Additional metrics for richness
            try:
                # Dale-Chall readability
                dale_chall = textstat.dale_chall_readability_score(combined_text)
                # SMOG index
                smog = textstat.smog_index(combined_text)
            except:
                pass
        else:
            # Fallback: estimate complexity from average word length
            words = combined_text.split()
            avg_word_len = sum(len(w) for w in words) / max(len(words), 1)
            profile.vocabulary_complexity = min(1.0, avg_word_len / 8)

        # Vocabulary richness (type-token ratio)
        words = combined_text.lower().split()
        unique_words = set(words)
        profile.vocabulary_richness = len(unique_words) / max(len(words), 1)

        # ============================================================
        # 3. N-GRAM EXTRACTION (Signature Phrases)
        # ============================================================
        profile.common_bigrams = self._extract_ngrams(all_content, n=2, top_k=20)
        profile.common_trigrams = self._extract_ngrams(all_content, n=3, top_k=15)

        # Signature phrases are frequent ngrams that appear across multiple posts
        signature_candidates = []
        for phrase, count in profile.common_bigrams[:10]:
            if count >= 3:  # Used at least 3 times
                signature_candidates.append(phrase)
        for phrase, count in profile.common_trigrams[:10]:
            if count >= 2:  # Used at least twice
                signature_candidates.append(phrase)
        profile.signature_phrases = signature_candidates[:15]

        # ============================================================
        # 4. DOMAIN VOCABULARY EXTRACTION (TF-IDF style)
        # ============================================================
        profile.domain_vocabulary = self._extract_domain_terms(all_content)

        # ============================================================
        # 5. COLLOQUIALISMS AND FILLER WORDS
        # ============================================================
        profile.colloquialisms = self._detect_colloquialisms(combined_text)
        profile.filler_words = self._detect_filler_words(combined_text)

        # ============================================================
        # 6. SENTENCE STRUCTURE ANALYSIS
        # ============================================================
        sentence_stats = self._analyze_sentence_structure(all_content)
        profile.avg_sentence_length = sentence_stats["avg_length"]
        profile.sentence_length_variance = sentence_stats["variance"]
        profile.avg_words_per_sentence = sentence_stats["avg_words"]

        # ============================================================
        # 7. PUNCTUATION PATTERNS
        # ============================================================
        profile.punctuation_patterns = self._analyze_punctuation(combined_text, len(samples))

        # ============================================================
        # 8. CAPITALIZATION STYLE
        # ============================================================
        profile.capitalization_style = self._detect_capitalization_style(all_content)

        # ============================================================
        # 9. EMOJI ANALYSIS
        # ============================================================
        emoji_stats = self._analyze_emoji_usage(all_content)
        profile.uses_emojis = emoji_stats["uses_emojis"]
        profile.emoji_frequency = emoji_stats["frequency"]
        profile.common_emojis = emoji_stats["common_emojis"]

        # ============================================================
        # 10. HASHTAG ANALYSIS
        # ============================================================
        hashtag_count = sum(content.count("#") for content in all_content)
        profile.uses_hashtags = hashtag_count > 0
        profile.hashtag_frequency = hashtag_count / max(len(samples), 1)

        # ============================================================
        # 11. ENGAGEMENT PATTERNS
        # ============================================================
        total_engagement = sum(
            sum(s.engagement.values()) if s.engagement else 0
            for s in samples
        )
        profile.avg_engagement_score = total_engagement / max(len(samples), 1)

        # ============================================================
        # 12. TONE ANALYSIS (LLM-based if enabled)
        # ============================================================
        if use_llm_for_tone and anthropic_client:
            tone_scores = self._analyze_tone_with_llm(all_content[:20], anthropic_client)
            profile.tone_scores = tone_scores
            profile.primary_tone = max(tone_scores, key=tone_scores.get)
        else:
            # Fallback to heuristic tone detection
            profile.tone_scores = self._analyze_tone_heuristic(combined_text)
            profile.primary_tone = max(profile.tone_scores, key=profile.tone_scores.get)

        # Update version and timestamp
        profile.style_version = "2.0"
        profile.last_updated = datetime.now().isoformat()

        # Save deep profile
        self.save_deep_style_profile(profile)

        return profile

    def _extract_ngrams(
        self,
        texts: List[str],
        n: int = 2,
        top_k: int = 20
    ) -> List[Tuple[str, int]]:
        """Extract top n-grams from texts"""
        all_ngrams = []

        # Get stopwords if NLTK available
        stop_words = set()
        if NLTK_AVAILABLE:
            try:
                stop_words = set(stopwords.words('english'))
            except:
                # Download if not available
                try:
                    nltk.download('stopwords', quiet=True)
                    stop_words = set(stopwords.words('english'))
                except:
                    pass

        for text in texts:
            # Tokenize
            words = re.findall(r'\b[a-zA-Z]+\b', text.lower())
            # Filter stopwords for better phrases
            filtered_words = [w for w in words if w not in stop_words and len(w) > 2]

            if NLTK_AVAILABLE:
                text_ngrams = list(ngrams(filtered_words, n))
            else:
                # Manual ngram extraction
                text_ngrams = [
                    tuple(filtered_words[i:i+n])
                    for i in range(len(filtered_words) - n + 1)
                ]

            all_ngrams.extend(text_ngrams)

        # Count frequencies
        ngram_freq = Counter(all_ngrams)

        # Convert to strings and return top k
        result = [
            (" ".join(gram), count)
            for gram, count in ngram_freq.most_common(top_k)
        ]
        return result

    def _extract_domain_terms(self, texts: List[str], top_k: int = 20) -> List[str]:
        """Extract domain-specific vocabulary using TF-IDF-like scoring"""
        # Common English words to exclude (expanded stopwords)
        common_words = {
            'the', 'be', 'to', 'of', 'and', 'a', 'in', 'that', 'have', 'i',
            'it', 'for', 'not', 'on', 'with', 'he', 'as', 'you', 'do', 'at',
            'this', 'but', 'his', 'by', 'from', 'they', 'we', 'say', 'her',
            'she', 'or', 'an', 'will', 'my', 'one', 'all', 'would', 'there',
            'their', 'what', 'so', 'up', 'out', 'if', 'about', 'who', 'get',
            'which', 'go', 'me', 'when', 'make', 'can', 'like', 'time', 'no',
            'just', 'him', 'know', 'take', 'people', 'into', 'year', 'your',
            'good', 'some', 'could', 'them', 'see', 'other', 'than', 'then',
            'now', 'look', 'only', 'come', 'its', 'over', 'think', 'also',
            'back', 'after', 'use', 'two', 'how', 'our', 'work', 'first',
            'well', 'way', 'even', 'new', 'want', 'because', 'any', 'these',
            'give', 'day', 'most', 'us', 'very', 'really', 'been', 'being',
            'much', 'more', 'here', 'still', 'many', 'thing', 'things'
        }

        word_doc_freq = Counter()  # How many documents contain each word
        word_total_freq = Counter()  # Total occurrences

        for text in texts:
            words = set(re.findall(r'\b[a-zA-Z]{3,}\b', text.lower()))
            for word in words:
                if word not in common_words:
                    word_doc_freq[word] += 1

            all_words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
            for word in all_words:
                if word not in common_words:
                    word_total_freq[word] += 1

        # Calculate TF-IDF-like score
        # High doc frequency + high total freq = domain term
        scored_words = []
        for word, doc_freq in word_doc_freq.items():
            if doc_freq >= 2:  # Appears in at least 2 posts
                total_freq = word_total_freq[word]
                # Score: balance between appearing often and in many docs
                score = total_freq * math.log(doc_freq + 1)
                scored_words.append((word, score))

        # Sort by score and return top k
        scored_words.sort(key=lambda x: x[1], reverse=True)
        return [word for word, _ in scored_words[:top_k]]

    def _detect_colloquialisms(self, text: str) -> List[str]:
        """Detect informal/slang expressions"""
        # Common internet/social media colloquialisms
        colloquial_patterns = [
            'tbh', 'ngl', 'imo', 'imho', 'fwiw', 'afaik', 'tl;dr', 'ftfy',
            'lol', 'lmao', 'rofl', 'omg', 'wtf', 'smh', 'fomo', 'yolo',
            'gonna', 'wanna', 'gotta', 'kinda', 'sorta', 'prolly', 'ya',
            'yeah', 'yep', 'nope', 'nah', 'haha', 'hehe', 'meh', 'ugh',
            'bruh', 'bro', 'dude', 'fam', 'lowkey', 'highkey', 'vibe',
            'slay', 'bet', 'cap', 'no cap', 'sus', 'lit', 'fire',
            'deadass', 'fr', 'rn', 'idk', 'idc', 'idgaf', 'fyi',
            'btw', 'jk', 'pls', 'plz', 'thx', 'ty', 'np', 'yw',
            "y'all", 'ain\'t', 'gonna', 'lemme', 'gimme', 'dunno'
        ]

        text_lower = text.lower()
        found = []
        for pattern in colloquial_patterns:
            if re.search(r'\b' + re.escape(pattern) + r'\b', text_lower):
                found.append(pattern)

        return found

    def _detect_filler_words(self, text: str) -> List[str]:
        """Detect filler words/phrases that indicate personal style"""
        filler_patterns = [
            'like', 'basically', 'honestly', 'actually', 'literally',
            'obviously', 'clearly', 'definitely', 'essentially', 'probably',
            'maybe', 'perhaps', 'kind of', 'sort of', 'i mean', 'you know',
            'i think', 'i feel', 'i guess', 'i suppose', 'in my opinion',
            'to be honest', 'to be fair', 'at the end of the day',
            'at this point', 'the thing is', 'the fact is'
        ]

        text_lower = text.lower()
        found = []
        for pattern in filler_patterns:
            count = len(re.findall(r'\b' + re.escape(pattern) + r'\b', text_lower))
            if count >= 2:  # Used at least twice
                found.append(pattern)

        return found

    def _analyze_sentence_structure(self, texts: List[str]) -> Dict:
        """Analyze sentence structure patterns"""
        all_sentences = []

        for text in texts:
            # Split into sentences (simple approach)
            sentences = re.split(r'[.!?]+', text)
            sentences = [s.strip() for s in sentences if s.strip()]
            all_sentences.extend(sentences)

        if not all_sentences:
            return {"avg_length": 0, "variance": 0, "avg_words": 0}

        # Calculate metrics
        lengths = [len(s) for s in all_sentences]
        word_counts = [len(s.split()) for s in all_sentences]

        avg_length = sum(lengths) / len(lengths)
        avg_words = sum(word_counts) / len(word_counts)

        # Variance
        variance = sum((l - avg_length) ** 2 for l in lengths) / len(lengths)

        return {
            "avg_length": avg_length,
            "variance": variance ** 0.5,  # Standard deviation
            "avg_words": avg_words
        }

    def _analyze_punctuation(self, text: str, sample_count: int) -> Dict[str, float]:
        """Analyze punctuation usage patterns"""
        patterns = {
            "ellipsis": len(re.findall(r'\.{3}|…', text)) / max(sample_count, 1),
            "exclamation": len(re.findall(r'!', text)) / max(sample_count, 1),
            "question": len(re.findall(r'\?', text)) / max(sample_count, 1),
            "dash": len(re.findall(r'[-–—]', text)) / max(sample_count, 1),
            "comma_heavy": len(re.findall(r',', text)) / max(len(text), 1) * 100
        }
        return patterns

    def _detect_capitalization_style(self, texts: List[str]) -> str:
        """Detect predominant capitalization style"""
        lowercase_count = 0
        standard_count = 0
        shouty_count = 0

        for text in texts:
            if text == text.lower():
                lowercase_count += 1
            elif text == text.upper() and len(text) > 10:
                shouty_count += 1
            elif text[0].isupper() if text else False:
                standard_count += 1

        total = len(texts)
        if total == 0:
            return "standard"

        if lowercase_count / total > 0.6:
            return "lowercase"
        elif shouty_count / total > 0.3:
            return "shouty"
        else:
            return "standard"

    def _analyze_emoji_usage(self, texts: List[str]) -> Dict:
        """Analyze emoji usage patterns"""
        # Emoji regex pattern
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"  # symbols & pictographs
            "\U0001F680-\U0001F6FF"  # transport & map symbols
            "\U0001F1E0-\U0001F1FF"  # flags
            "\U00002702-\U000027B0"  # dingbats
            "\U000024C2-\U0001F251"
            "]+",
            flags=re.UNICODE
        )

        all_emojis = []
        for text in texts:
            emojis = emoji_pattern.findall(text)
            all_emojis.extend(emojis)

        emoji_freq = Counter(all_emojis)

        return {
            "uses_emojis": len(all_emojis) > 0,
            "frequency": len(all_emojis) / max(len(texts), 1),
            "common_emojis": [e for e, _ in emoji_freq.most_common(10)]
        }

    def _analyze_tone_heuristic(self, text: str) -> Dict[str, float]:
        """Heuristic-based tone analysis (fallback when LLM not available)"""
        text_lower = text.lower()

        # Keyword-based tone detection
        tone_keywords = {
            "professional": ["accordingly", "furthermore", "implementation", "strategic", "optimize", "leverage"],
            "casual": ["lol", "haha", "gonna", "wanna", "tbh", "ngl", "dude", "bro", "yeah", "cool"],
            "technical": ["api", "algorithm", "framework", "architecture", "implementation", "deploy", "code"],
            "sarcastic": ["obviously", "clearly", "sure", "right", "totally", "wow", "great"],
            "enthusiastic": ["amazing", "awesome", "incredible", "love", "excited", "fantastic", "!"],
            "analytical": ["however", "therefore", "analysis", "data", "suggests", "indicates", "compared"],
            "friendly": ["thanks", "appreciate", "hope", "glad", "happy", "welcome", "please"]
        }

        scores = {}
        total_words = len(text_lower.split())

        for tone, keywords in tone_keywords.items():
            count = sum(text_lower.count(kw) for kw in keywords)
            scores[tone] = min(1.0, count / max(total_words, 1) * 50)

        # Normalize scores
        total = sum(scores.values())
        if total > 0:
            scores = {k: v / total for k, v in scores.items()}

        return scores

    def _analyze_tone_with_llm(
        self,
        sample_texts: List[str],
        anthropic_client
    ) -> Dict[str, float]:
        """Use Claude to analyze tone across multiple dimensions"""
        # Take a representative sample
        sample = "\n---\n".join(sample_texts[:10])

        prompt = f"""Analyze the writing tone in these social media posts/comments.

Rate each dimension from 0.0 to 1.0:
- professional: formal, business-like language
- casual: informal, conversational
- technical: uses jargon, domain-specific terms
- sarcastic: uses irony, dry humor
- enthusiastic: excited, energetic, uses exclamations
- analytical: data-driven, logical reasoning
- friendly: warm, approachable, supportive

POSTS TO ANALYZE:
{sample}

Return ONLY a JSON object with the scores, no explanation:
{{"professional": 0.0, "casual": 0.0, "technical": 0.0, "sarcastic": 0.0, "enthusiastic": 0.0, "analytical": 0.0, "friendly": 0.0}}"""

        try:
            response = anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}]
            )

            # Parse JSON response
            import json
            result_text = response.content[0].text.strip()
            # Extract JSON from response
            json_match = re.search(r'\{[^}]+\}', result_text)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            print(f"⚠️ LLM tone analysis failed: {e}")

        # Fallback to heuristic
        return self._analyze_tone_heuristic(" ".join(sample_texts))

    def save_deep_style_profile(self, profile: DeepStyleProfile):
        """Save deep style profile"""
        namespace = (self.user_id, "writing_style")
        self.store.put(namespace, "deep_profile", profile.to_dict())

    def get_deep_style_profile(self) -> Optional[DeepStyleProfile]:
        """Get saved deep style profile"""
        namespace = (self.user_id, "writing_style")
        item = self.store.get(namespace, "deep_profile")
        if item:
            return DeepStyleProfile.from_dict(item.value)
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

🚨 BANNED AI-SOUNDING PHRASES (NEVER USE THESE):
- "Great post!" / "Love this!" / "This is amazing!"
- "I couldn't agree more" / "Spot on" / "Nailed it"
- "So underrated" / "This deserves more attention"
- "Love the deep dive" / "Great breakdown" / "Really insightful"
- "This resonates with me" / "Couldn't have said it better"
- "Thanks for sharing" / "This is gold"
- "Game changer" / "Mind blown"
- Any phrase that sounds like a LinkedIn comment

These phrases SCREAM "AI wrote this" - real humans don't comment like that.

✅ WHAT MAKES COMMENTS SOUND HUMAN:
- Reference SPECIFIC parts of the post (quote or paraphrase something unique)
- Add a personal anecdote, experience, or opinion
- Ask a genuine follow-up question
- Disagree or add nuance (not just agree)
- Use incomplete thoughts or casual phrasing
- Have a slight imperfection or typo occasionally
- Show real curiosity, not performative enthusiasm

🔍 BACKGROUND RESEARCH AVAILABLE:
Before writing, you have access to web search research about the topic. Use this to:
- Add specific facts, stats, or recent developments
- Reference related news or trends
- Show genuine knowledge beyond surface-level understanding
- Make your comment uniquely informed and valuable

CRITICAL FORMATTING RULES (MUST FOLLOW):
- NEVER use dashes (-) or bullet points to list things
- NEVER use emphasis formatting like **bold** or *italic* or _underscores_
- NEVER use markdown formatting of any kind
- NEVER structure text as numbered or bulleted lists
- Write in natural flowing sentences like a human typing casually
- No structured formatting - just plain conversational text
- If you want to list things, weave them into natural sentences instead

Your {content_type} (write ONLY the content, nothing else):"""

        return prompt

    def generate_enhanced_few_shot_prompt(
        self,
        context: str,
        content_type: str = "comment",
        num_examples: int = 5,
        include_competitor_examples: bool = True,
        competitor_topic: str = None,
        banned_patterns_manager: "BannedPatternsManager" = None,
        feedback_processor: "FeedbackProcessor" = None
    ) -> str:
        """
        Generate an enhanced few-shot prompt using DeepStyleProfile and style system integration.

        This method provides:
        - Deep style analysis (signature phrases, tone scores, punctuation patterns)
        - Comprehensive banned phrases from centralized manager
        - Learned rules from feedback processor
        - Time-weighted example selection

        Args:
            context: The post/thread to respond to
            content_type: Type of content to generate
            num_examples: Number of user examples to include
            include_competitor_examples: Whether to include competitor posts
            competitor_topic: Topic to filter competitor posts by
            banned_patterns_manager: BannedPatternsManager instance for banned phrases
            feedback_processor: FeedbackProcessor instance for learned rules

        Returns:
            Enhanced few-shot prompt string
        """
        # Get similar examples with time/engagement weighting
        examples = self.get_similar_examples(
            context,
            content_type,
            num_examples,
            recency_weight=0.3,
            engagement_weight=0.2
        )

        # Get deep style profile (fall back to basic if not available)
        deep_profile = self.get_deep_style_profile()
        if not deep_profile:
            deep_profile = self.deep_analyze_writing_style(use_llm_for_tone=False)

        # Get basic profile for backwards compatibility
        basic_profile = deep_profile.to_basic_profile() if deep_profile else self.get_style_profile()

        # Get banned phrases
        banned_phrases = []
        if banned_patterns_manager:
            all_banned = banned_patterns_manager.get_all_banned(self.user_id)
            banned_phrases = [bp.phrase for bp in all_banned[:50]]  # Top 50
        else:
            # Fallback to hardcoded list
            banned_phrases = [
                "great post", "love this", "this is amazing", "spot on", "nailed it",
                "couldn't agree more", "so underrated", "this deserves more attention",
                "this resonates", "thanks for sharing", "game changer", "mind blown"
            ]

        # Get learned rules from feedback processor
        learned_rules = ""
        if feedback_processor:
            try:
                import asyncio
                # Try to get learnings synchronously if possible
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # We're in an async context, can't block
                    learned_rules = ""
                else:
                    learned_rules = loop.run_until_complete(
                        feedback_processor.get_learnings_prompt()
                    )
            except Exception as e:
                print(f"⚠️ Could not load learned rules: {e}")

        # Get high-performing competitor posts if enabled
        competitor_posts = []
        if include_competitor_examples:
            try:
                namespace = (self.user_id, "competitor_profiles")
                competitors = list(self.store.search(namespace, limit=30))

                for comp_item in competitors:
                    comp_data = comp_item.value
                    posts = comp_data.get("posts", [])

                    for post in posts:
                        likes = post.get("likes", 0)
                        if likes >= 100:
                            if competitor_topic is None or competitor_topic.lower() in post.get("text", "").lower():
                                competitor_posts.append({
                                    "text": post.get("text", ""),
                                    "likes": likes,
                                    "retweets": post.get("retweets", 0),
                                    "replies": post.get("replies", 0)
                                })

                competitor_posts.sort(key=lambda x: x["likes"] + x["retweets"] + x["replies"], reverse=True)
                competitor_posts = competitor_posts[:5]
            except Exception as e:
                print(f"⚠️ Could not load competitor examples: {e}")

        # Build enhanced prompt
        target_length = deep_profile.avg_comment_length if content_type == 'comment' else deep_profile.avg_post_length

        prompt = f"""You are a Parallel Universe AI writing assistant. Your ONLY job is to write content that is INDISTINGUISHABLE from this specific user.

═══════════════════════════════════════════════════════════════════════════════
                          DEEP WRITING STYLE PROFILE
═══════════════════════════════════════════════════════════════════════════════

PRIMARY CHARACTERISTICS:
- Primary Tone: {deep_profile.primary_tone}
- Tone Breakdown: {', '.join(f'{k}={v:.0%}' for k, v in deep_profile.tone_scores.items() if v > 0.1)}
- Vocabulary Complexity: {'Simple' if deep_profile.vocabulary_complexity < 0.3 else 'Moderate' if deep_profile.vocabulary_complexity < 0.7 else 'Advanced'}
- Vocabulary Richness: {deep_profile.vocabulary_richness:.0%}
- Capitalization: {deep_profile.capitalization_style}

LENGTH REQUIREMENTS:
- Target Length: ~{target_length} characters
- Average Words/Sentence: {deep_profile.avg_words_per_sentence:.1f}

SIGNATURE PHRASES (User uses these often - incorporate them!):
{chr(10).join(f'• "{phrase}"' for phrase in deep_profile.signature_phrases[:8]) if deep_profile.signature_phrases else '• None detected yet'}

DOMAIN VOCABULARY (User's technical/niche terms):
{', '.join(deep_profile.domain_vocabulary[:10]) if deep_profile.domain_vocabulary else 'None detected'}

COLLOQUIALISMS (Informal expressions user uses):
{', '.join(deep_profile.colloquialisms[:8]) if deep_profile.colloquialisms else 'None detected'}

FILLER WORDS (User's verbal tics):
{', '.join(deep_profile.filler_words[:8]) if deep_profile.filler_words else 'None detected'}

PUNCTUATION PATTERNS:
- Ellipsis (...): {'Frequently' if deep_profile.punctuation_patterns.get('ellipsis', 0) > 0.5 else 'Sometimes' if deep_profile.punctuation_patterns.get('ellipsis', 0) > 0.1 else 'Rarely'}
- Exclamation (!): {'Frequently' if deep_profile.punctuation_patterns.get('exclamation', 0) > 0.5 else 'Sometimes' if deep_profile.punctuation_patterns.get('exclamation', 0) > 0.1 else 'Rarely'}
- Questions (?): {'Frequently' if deep_profile.punctuation_patterns.get('question', 0) > 0.5 else 'Sometimes' if deep_profile.punctuation_patterns.get('question', 0) > 0.1 else 'Rarely'}

EMOJI USAGE:
- Uses Emojis: {deep_profile.uses_emojis} ({deep_profile.emoji_frequency:.1f} per post)
- Common Emojis: {' '.join(deep_profile.common_emojis[:5]) if deep_profile.common_emojis else 'None'}

═══════════════════════════════════════════════════════════════════════════════
                          USER'S WRITING EXAMPLES
═══════════════════════════════════════════════════════════════════════════════
Study these examples CAREFULLY. Match their EXACT style, vocabulary, and rhythm.
"""

        for i, example in enumerate(examples, 1):
            engagement = sum(example.engagement.values()) if example.engagement else 0
            prompt += f"""
EXAMPLE {i}:
"""
            if example.context:
                prompt += f"Replying to: {example.context[:200]}...\n" if len(example.context) > 200 else f"Replying to: {example.context}\n"
            prompt += f"""User wrote: {example.content}
Engagement: {engagement} total ({example.engagement if example.engagement else 'N/A'})
"""

        # Add competitor examples if available
        if competitor_posts:
            prompt += """
═══════════════════════════════════════════════════════════════════════════════
                     HIGH-PERFORMING COMPETITOR EXAMPLES
═══════════════════════════════════════════════════════════════════════════════
Learn PATTERNS from these (format, hooks, structure), but write in USER'S voice.
"""
            for i, post in enumerate(competitor_posts, 1):
                prompt += f"""
COMPETITOR {i} ({post['likes']} likes):
{post['text'][:300]}{'...' if len(post['text']) > 300 else ''}
"""

        # Add learned rules from feedback
        if learned_rules:
            prompt += f"""
═══════════════════════════════════════════════════════════════════════════════
                        LEARNED FROM USER FEEDBACK
═══════════════════════════════════════════════════════════════════════════════
{learned_rules}
"""

        # Add banned phrases
        prompt += f"""
═══════════════════════════════════════════════════════════════════════════════
                     🚨 ABSOLUTELY BANNED PHRASES 🚨
═══════════════════════════════════════════════════════════════════════════════
NEVER use ANY of these. They instantly mark content as AI-generated:

{chr(10).join(f'❌ "{phrase}"' for phrase in banned_phrases[:30])}

These phrases are banned because they're generic AI patterns. Real humans don't write like this.

═══════════════════════════════════════════════════════════════════════════════
                          GENERATION TASK
═══════════════════════════════════════════════════════════════════════════════

CONTEXT TO RESPOND TO:
{context}

CONTENT TYPE: {content_type.upper()}
TARGET LENGTH: ~{target_length} characters

YOUR TASK:
Write a {content_type} that:
1. Is INDISTINGUISHABLE from the user's examples above
2. Uses the user's vocabulary, phrases, and tone
3. Matches the user's punctuation and emoji patterns
4. Incorporates their signature phrases naturally
5. Follows any learned rules from feedback
6. AVOIDS all banned phrases completely

FORMATTING RULES:
- NEVER use dashes (-) or bullet points
- NEVER use markdown (**bold**, *italic*, etc.)
- Write in natural flowing sentences
- Match the user's capitalization style: {deep_profile.capitalization_style}

Your {content_type} (write ONLY the content, nothing else):"""

        return prompt

    def generate_style_from_description(
        self,
        description: str,
        context: str,
        content_type: str = "comment"
    ) -> str:
        """
        Generate content based on user's style description when no writing samples exist.

        This is a fallback method for users who don't have imported posts yet but have
        described their desired tone/style in their profile description.

        Args:
            description: User's profile/style description text
            context: The post/content to respond to
            content_type: Type of content to generate ("post" or "comment")

        Returns:
            Prompt for LLM to generate content in the described style

        Example:
            >>> manager = XWritingStyleManager(store, user_id)
            >>> description = "I like to write in a casual, friendly tone with occasional humor"
            >>> prompt = manager.generate_style_from_description(description, "Post about AI", "comment")
        """
        # Determine appropriate length based on content type
        length_guidance = "~50 characters for comment, ~200 for post"
        if content_type == "comment":
            length_guidance = "Keep it short and concise (~40-80 characters)"
        elif content_type == "post":
            length_guidance = "Keep it engaging but not too long (~150-250 characters)"

        return f"""Generate a {content_type} about: {context}

USER'S STYLE DESCRIPTION:
{description}

INSTRUCTIONS:
- Follow the style guidelines provided by the user EXACTLY
- Match the tone, formality, and approach they described
- {length_guidance}
- Sound authentic and natural, not robotic
- If style is unclear, use a professional but friendly tone
- DO NOT use hashtags (X penalizes them)
- Avoid generic AI-like phrases

CRITICAL FORMATTING RULES (MUST FOLLOW):
- NEVER use dashes (-) or bullet points to list things
- NEVER use emphasis formatting like **bold** or *italic* or _underscores_
- NEVER use markdown formatting of any kind
- NEVER structure text as numbered or bulleted lists
- Write in natural flowing sentences like a human typing casually
- No structured formatting - just plain conversational text
- If you want to list things, weave them into natural sentences instead

CRITICAL: The user described their style above. Honor their preferences precisely.
If they said "casual", be casual. If they said "professional", be professional.
If they mentioned humor, add subtle wit. If they said formal, stay formal.

Your {content_type} (write ONLY the content, nothing else):"""

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

