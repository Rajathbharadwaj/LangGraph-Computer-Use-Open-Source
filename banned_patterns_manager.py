"""
Centralized Banned Patterns Manager for AI-Generated Content

This module consolidates all banned AI-sounding phrases from across the codebase
and provides utilities for detection, user-specific patterns, and learning from edits.

Based on Letta's continual learning principles:
- Per-agent learned contexts (user-specific banned patterns)
- Learning in token space (store patterns as retrievable memories)
- Interpretability (human-readable patterns for inspection)
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Tuple
from datetime import datetime
import difflib
import logging

logger = logging.getLogger(__name__)


@dataclass
class BannedPattern:
    """A single banned pattern with metadata."""
    phrase: str
    category: str  # opener, filler, phrase, structure, closer
    source: str  # global, user_feedback, learned_from_edit
    added_at: datetime = field(default_factory=datetime.utcnow)
    times_detected: int = 0
    confidence: float = 1.0  # 1.0 = definitely banned, <1.0 = learned pattern


class BannedPatternsManager:
    """
    Centralized manager for banned AI-sounding phrases.

    Consolidates all banned phrases from:
    - x_growth_deep_agent.py (multiple subagent prompts)
    - x_writing_style_learner.py (few-shot prompts)

    Features:
    - Global banned patterns (universal AI tells)
    - User-specific patterns (learned from feedback)
    - Auto-learning from user edits
    - Detection and validation
    """

    # ═══════════════════════════════════════════════════════════════════════════
    # GLOBAL BANNED PATTERNS - Consolidated from entire codebase
    # ═══════════════════════════════════════════════════════════════════════════

    BANNED_OPENERS = [
        # Agreement patterns
        "this is spot on", "spot on", "this is so true",
        "this!", "so this!", "all of this!",
        "this resonates", "this hits different", "this hits home",
        "love this", "great post", "great point",
        "really insightful", "super insightful", "incredibly insightful",
        "couldn't agree more", "100% agree", "absolutely agree",
        "adding nuance:", "adding context:", "adding to this:",

        # Generic praise
        "amazing", "brilliant", "genius",
        "wow", "incredible",

        # AI-style openers
        "here's the thing", "here's why", "the thing is",
        "unpopular opinion:", "hot take:",
        "a thread", "thread:",
        "here's what i learned", "lessons from",
        "let me explain", "let's dive in",
    ]

    BANNED_FILLER_WORDS = [
        # Hyperbolic adjectives
        "wild", "insane", "crazy",
        "game changer", "game-changing",
        "underrated", "so underrated", "overrated",
        "mind blown", "mind-blowing",
        "fascinating", "intriguing",
        "powerful", "impactful",
        "brilliant", "genius",
        "nailed it", "crushed it",

        # Generic intensifiers
        "absolutely", "literally", "totally",
        "honestly", "frankly", "truthfully",
    ]

    BANNED_PHRASES = [
        # Gratitude patterns
        "thanks for sharing", "thank you for sharing",

        # Visibility requests
        "this deserves more attention",
        "more people need to see this",
        "saving this for later",

        # Value claims
        "this is gold", "wisdom here", "pure gold",
        "the missing piece", "changed everything for me",

        # LinkedIn-style
        "feels like we're finally getting",
        "changes the whole energy",
        "this reframe hits different",

        # Call-to-action clichés
        "let that sink in",
        "read that again",
        "bookmark this",
    ]

    BANNED_CLOSERS = [
        "changed everything for me",
        "more people need to see this",
        "the missing piece",
        "here's the thing",
        "let that sink in",
        "read that again",
        "game changer",
    ]

    BANNED_STRUCTURES = [
        # Patterns (regex-like descriptions)
        r"the \w+ is \w+",  # "The insight here is powerful"
        r"^\w+!$",  # Single word exclamation "Amazing!"
        r"^(this|so|all of) this!?$",  # "This!" patterns
    ]

    # Emojis that scream AI when overused
    SUSPICIOUS_EMOJI_PATTERNS = [
        "🔥", "💯", "🚀", "💡", "🙌", "👏", "💪", "🎯",
        "✨", "⭐", "🌟", "💎", "🏆", "🥇",
    ]

    def __init__(self, store=None, user_id: str = None):
        """
        Initialize the banned patterns manager.

        Args:
            store: LangGraph store for persistent user patterns
            user_id: User ID for user-specific patterns
        """
        self.store = store
        self.user_id = user_id
        self._user_patterns_cache: Optional[List[BannedPattern]] = None

        # Compile all global patterns for efficient matching
        self._global_patterns = self._compile_global_patterns()

    def _compile_global_patterns(self) -> Set[str]:
        """Compile all global banned patterns into a set for O(1) lookup."""
        patterns = set()

        for phrase in self.BANNED_OPENERS:
            patterns.add(phrase.lower().strip())

        for phrase in self.BANNED_FILLER_WORDS:
            patterns.add(phrase.lower().strip())

        for phrase in self.BANNED_PHRASES:
            patterns.add(phrase.lower().strip())

        for phrase in self.BANNED_CLOSERS:
            patterns.add(phrase.lower().strip())

        return patterns

    # ═══════════════════════════════════════════════════════════════════════════
    # DETECTION METHODS
    # ═══════════════════════════════════════════════════════════════════════════

    def detect_in_text(self, text: str) -> List[Dict]:
        """
        Detect all banned phrases in the given text.

        Args:
            text: Text to analyze

        Returns:
            List of detected patterns with details:
            [{"phrase": "...", "category": "...", "position": (start, end)}]
        """
        if not text:
            return []

        detected = []
        text_lower = text.lower()

        # Check global patterns
        for category, patterns in [
            ("opener", self.BANNED_OPENERS),
            ("filler", self.BANNED_FILLER_WORDS),
            ("phrase", self.BANNED_PHRASES),
            ("closer", self.BANNED_CLOSERS),
        ]:
            for pattern in patterns:
                pattern_lower = pattern.lower()
                if pattern_lower in text_lower:
                    # Find position
                    start = text_lower.find(pattern_lower)
                    detected.append({
                        "phrase": pattern,
                        "category": category,
                        "source": "global",
                        "position": (start, start + len(pattern))
                    })

        # Check user-specific patterns
        user_patterns = self._get_user_patterns()
        for pattern in user_patterns:
            if pattern.phrase.lower() in text_lower:
                start = text_lower.find(pattern.phrase.lower())
                detected.append({
                    "phrase": pattern.phrase,
                    "category": pattern.category,
                    "source": pattern.source,
                    "position": (start, start + len(pattern.phrase))
                })

        # Check structure patterns (regex)
        for pattern in self.BANNED_STRUCTURES:
            matches = re.finditer(pattern, text_lower, re.IGNORECASE)
            for match in matches:
                detected.append({
                    "phrase": match.group(),
                    "category": "structure",
                    "source": "global",
                    "position": (match.start(), match.end())
                })

        # Check suspicious emoji density
        emoji_count = sum(1 for emoji in self.SUSPICIOUS_EMOJI_PATTERNS if emoji in text)
        if emoji_count >= 3:
            detected.append({
                "phrase": f"{emoji_count} suspicious emojis",
                "category": "emoji_overuse",
                "source": "global",
                "position": None
            })

        return detected

    def contains_banned(self, text: str) -> bool:
        """Quick check if text contains any banned patterns."""
        return len(self.detect_in_text(text)) > 0

    def get_banned_count(self, text: str) -> int:
        """Count number of banned patterns in text."""
        return len(self.detect_in_text(text))

    def validate_content(self, text: str) -> Tuple[bool, List[Dict]]:
        """
        Validate content for banned patterns.

        Args:
            text: Content to validate

        Returns:
            (is_valid, detected_patterns)
            is_valid is True if no banned patterns found
        """
        detected = self.detect_in_text(text)
        return len(detected) == 0, detected

    # ═══════════════════════════════════════════════════════════════════════════
    # USER-SPECIFIC PATTERNS
    # ═══════════════════════════════════════════════════════════════════════════

    def _get_user_patterns(self) -> List[BannedPattern]:
        """Get user-specific banned patterns from store."""
        if not self.store or not self.user_id:
            return []

        if self._user_patterns_cache is not None:
            return self._user_patterns_cache

        try:
            namespace = (self.user_id, "banned_patterns")
            result = self.store.get(namespace, "patterns")
            if result and result.value:
                patterns_data = result.value.get("patterns", [])
                self._user_patterns_cache = [
                    BannedPattern(
                        phrase=p["phrase"],
                        category=p.get("category", "user"),
                        source=p.get("source", "user_feedback"),
                        confidence=p.get("confidence", 1.0)
                    )
                    for p in patterns_data
                ]
                return self._user_patterns_cache
        except Exception as e:
            logger.warning(f"Failed to load user patterns: {e}")

        return []

    def add_user_pattern(self, phrase: str, category: str = "user",
                         source: str = "user_feedback", confidence: float = 1.0):
        """
        Add a user-specific banned pattern.

        Args:
            phrase: Phrase to ban
            category: Category (opener, filler, phrase, etc.)
            source: How this pattern was added (user_feedback, learned_from_edit)
            confidence: Confidence level (1.0 = definitely banned)
        """
        if not self.store or not self.user_id:
            logger.warning("Cannot add user pattern: no store or user_id")
            return

        # Get existing patterns
        patterns = self._get_user_patterns()

        # Check if already exists
        existing_phrases = {p.phrase.lower() for p in patterns}
        if phrase.lower() in existing_phrases:
            logger.info(f"Pattern '{phrase}' already exists for user {self.user_id}")
            return

        # Add new pattern
        new_pattern = BannedPattern(
            phrase=phrase,
            category=category,
            source=source,
            confidence=confidence
        )
        patterns.append(new_pattern)

        # Save to store
        namespace = (self.user_id, "banned_patterns")
        patterns_data = [
            {
                "phrase": p.phrase,
                "category": p.category,
                "source": p.source,
                "confidence": p.confidence,
                "added_at": p.added_at.isoformat()
            }
            for p in patterns
        ]
        self.store.put(namespace, "patterns", {"patterns": patterns_data})

        # Invalidate cache
        self._user_patterns_cache = None

        logger.info(f"Added banned pattern '{phrase}' for user {self.user_id}")

    def remove_user_pattern(self, phrase: str):
        """Remove a user-specific banned pattern (user actually uses this phrase)."""
        if not self.store or not self.user_id:
            return

        patterns = self._get_user_patterns()
        patterns = [p for p in patterns if p.phrase.lower() != phrase.lower()]

        # Save updated patterns
        namespace = (self.user_id, "banned_patterns")
        patterns_data = [
            {
                "phrase": p.phrase,
                "category": p.category,
                "source": p.source,
                "confidence": p.confidence
            }
            for p in patterns
        ]
        self.store.put(namespace, "patterns", {"patterns": patterns_data})

        # Invalidate cache
        self._user_patterns_cache = None

        logger.info(f"Removed banned pattern '{phrase}' for user {self.user_id}")

    # ═══════════════════════════════════════════════════════════════════════════
    # LEARNING FROM EDITS
    # ═══════════════════════════════════════════════════════════════════════════

    def learn_from_edit(self, original: str, edited: str) -> Dict:
        """
        Learn from user edits to identify patterns to ban or allow.

        When user edits AI-generated content:
        - Removed phrases → potential banned patterns
        - Added phrases → style signals (user actually uses these)

        Args:
            original: Original AI-generated content
            edited: User's edited version

        Returns:
            {
                "removed_phrases": [...],  # Potential bans
                "added_phrases": [...],     # User's style
                "edit_distance": 0.3,       # How much was changed
                "patterns_added": [...]     # Patterns added to banned list
            }
        """
        if not original or not edited:
            return {"removed_phrases": [], "added_phrases": [], "edit_distance": 0.0}

        # Calculate edit distance
        edit_distance = 1.0 - difflib.SequenceMatcher(None, original, edited).ratio()

        # Find removed and added text
        original_words = set(original.lower().split())
        edited_words = set(edited.lower().split())

        removed_words = original_words - edited_words
        added_words = edited_words - original_words

        # Check if removed words match any global patterns
        removed_patterns = []
        for pattern in self._global_patterns:
            pattern_words = set(pattern.split())
            if pattern_words.issubset(removed_words):
                removed_patterns.append(pattern)

        # Extract multi-word phrases that were removed
        # Use sequence matching to find removed substrings
        removed_phrases = []
        matcher = difflib.SequenceMatcher(None, original.lower(), edited.lower())
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'delete' or tag == 'replace':
                removed_text = original[i1:i2].strip()
                if len(removed_text) > 5:  # Only track meaningful removals
                    removed_phrases.append(removed_text)

        # Learn: If user consistently removes certain phrases, add to banned
        patterns_added = []
        for phrase in removed_phrases:
            phrase_lower = phrase.lower()
            # Check if it looks like a banned pattern (not just random text)
            if any(banned in phrase_lower for banned in self._global_patterns):
                # Add user-specific ban with lower confidence
                self.add_user_pattern(
                    phrase=phrase,
                    category="learned",
                    source="learned_from_edit",
                    confidence=0.7
                )
                patterns_added.append(phrase)

        return {
            "removed_phrases": removed_phrases,
            "added_phrases": list(added_words),
            "edit_distance": edit_distance,
            "patterns_added": patterns_added
        }

    # ═══════════════════════════════════════════════════════════════════════════
    # PROMPT GENERATION
    # ═══════════════════════════════════════════════════════════════════════════

    def get_banned_phrases_prompt(self) -> str:
        """
        Generate a prompt section listing all banned phrases.

        Returns:
            Formatted string for inclusion in generation prompts
        """
        prompt_parts = []

        prompt_parts.append("🚨🚨🚨 BANNED AI PHRASES - NEVER USE THESE 🚨🚨🚨")
        prompt_parts.append("These phrases INSTANTLY reveal AI wrote the content. NEVER use them:\n")

        prompt_parts.append("BANNED OPENERS:")
        for phrase in self.BANNED_OPENERS[:15]:  # Top 15
            prompt_parts.append(f"- \"{phrase}\"")

        prompt_parts.append("\nBANNED FILLER WORDS:")
        for phrase in self.BANNED_FILLER_WORDS[:10]:
            prompt_parts.append(f"- \"{phrase}\"")

        prompt_parts.append("\nBANNED PHRASES:")
        for phrase in self.BANNED_PHRASES[:10]:
            prompt_parts.append(f"- \"{phrase}\"")

        # Add user-specific patterns
        user_patterns = self._get_user_patterns()
        if user_patterns:
            prompt_parts.append("\n🚫 USER-SPECIFIC BANNED PATTERNS (learned from your feedback):")
            for pattern in user_patterns[:10]:
                prompt_parts.append(f"- \"{pattern.phrase}\"")

        prompt_parts.append("\n✅ WHAT TO DO INSTEAD:")
        prompt_parts.append("- Reference SPECIFIC parts of the post (quote or paraphrase)")
        prompt_parts.append("- Add a personal anecdote, experience, or opinion")
        prompt_parts.append("- Ask a genuine follow-up question")
        prompt_parts.append("- Disagree or add nuance (not just agree)")
        prompt_parts.append("- Use incomplete thoughts or casual phrasing")
        prompt_parts.append("- Have slight imperfections (occasional typo, trailing off...)")

        return "\n".join(prompt_parts)

    def get_all_banned(self) -> List[str]:
        """Get all banned phrases (global + user-specific)."""
        all_banned = list(self._global_patterns)

        user_patterns = self._get_user_patterns()
        for pattern in user_patterns:
            all_banned.append(pattern.phrase.lower())

        return list(set(all_banned))

    # ═══════════════════════════════════════════════════════════════════════════
    # STATISTICS
    # ═══════════════════════════════════════════════════════════════════════════

    def get_stats(self) -> Dict:
        """Get statistics about banned patterns."""
        user_patterns = self._get_user_patterns()

        return {
            "global_patterns_count": len(self._global_patterns),
            "user_patterns_count": len(user_patterns),
            "total_patterns_count": len(self._global_patterns) + len(user_patterns),
            "user_patterns": [
                {
                    "phrase": p.phrase,
                    "source": p.source,
                    "confidence": p.confidence
                }
                for p in user_patterns
            ],
            "categories": {
                "openers": len(self.BANNED_OPENERS),
                "fillers": len(self.BANNED_FILLER_WORDS),
                "phrases": len(self.BANNED_PHRASES),
                "closers": len(self.BANNED_CLOSERS),
                "structures": len(self.BANNED_STRUCTURES),
            }
        }


# ═══════════════════════════════════════════════════════════════════════════════
# UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def quick_validate(text: str) -> Tuple[bool, List[str]]:
    """
    Quick validation without store access.

    Args:
        text: Text to validate

    Returns:
        (is_valid, list_of_detected_phrases)
    """
    manager = BannedPatternsManager()
    is_valid, detected = manager.validate_content(text)
    return is_valid, [d["phrase"] for d in detected]


def get_banned_prompt() -> str:
    """Get the banned phrases prompt section for inclusion in prompts."""
    manager = BannedPatternsManager()
    return manager.get_banned_phrases_prompt()
