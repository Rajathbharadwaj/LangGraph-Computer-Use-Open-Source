"""
Feedback Processor for Continual Learning

This module implements the feedback loop for the style learning system,
following Letta's continual learning principles:

1. Learning in Token Space: Store learned patterns as retrievable memories
2. Sleep-time Compute: Background processing consolidates feedback into rules
3. Memory Self-awareness: Track what's working and adjust accordingly

Key features:
- Process explicit user feedback (thumbs up/down, text feedback)
- Learn from implicit signals (edits, approvals, rejections)
- Consolidate learnings into actionable rules
- Re-weight few-shot examples based on performance
"""

import difflib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from collections import Counter

# Local imports
from banned_patterns_manager import BannedPatternsManager

logger = logging.getLogger(__name__)


@dataclass
class FeedbackRecord:
    """A single feedback record."""
    feedback_id: str
    user_id: str
    timestamp: datetime

    # Content info
    generation_type: str  # "post" or "comment"
    original_content: str
    edited_content: Optional[str] = None

    # Feedback signals
    action: str = "unknown"  # approved, edited, rejected, thumbs_up, thumbs_down
    feedback_text: Optional[str] = None
    edit_distance: float = 0.0

    # Context
    target_post_content: Optional[str] = None
    target_author: Optional[str] = None

    # Processing status
    processed: bool = False
    learnings_extracted: List[str] = field(default_factory=list)


@dataclass
class Learning:
    """An extracted learning from feedback."""
    learning_id: str
    user_id: str

    category: str  # phrase_to_avoid, phrase_to_use, tone_adjustment, length_preference
    insight: str  # Human-readable description
    evidence: List[str]  # Supporting data
    confidence: float = 0.5  # 0-1, increases with more evidence

    created_at: datetime = field(default_factory=datetime.utcnow)
    times_applied: int = 0
    success_rate: float = 0.0


class FeedbackProcessor:
    """
    Process user feedback to improve content generation.

    Implements continual learning by:
    1. Processing immediate feedback (edits, approvals)
    2. Extracting patterns from feedback
    3. Consolidating learnings during "sleep time"
    4. Applying learnings to future generations
    """

    def __init__(self, store=None, user_id: str = None, model=None):
        """
        Initialize the feedback processor.

        Args:
            store: LangGraph store for persistence
            user_id: User ID for personalization
            model: LLM for extracting insights (optional)
        """
        self.store = store
        self.user_id = user_id
        self.model = model
        self.banned_manager = BannedPatternsManager(store, user_id)

    # ═══════════════════════════════════════════════════════════════════════════
    # PROCESS IMMEDIATE FEEDBACK
    # ═══════════════════════════════════════════════════════════════════════════

    async def process_feedback(self, feedback: FeedbackRecord) -> Dict:
        """
        Process a single feedback record and extract learnings.

        Args:
            feedback: FeedbackRecord to process

        Returns:
            {
                "learnings": [...],
                "patterns_added": [...],
                "example_weights_updated": bool
            }
        """
        result = {
            "learnings": [],
            "patterns_added": [],
            "example_weights_updated": False
        }

        # 1. Process based on action type
        if feedback.action == "edited" and feedback.edited_content:
            edit_result = await self.learn_from_edit(
                feedback.original_content,
                feedback.edited_content,
                feedback.generation_type
            )
            result["learnings"].extend(edit_result.get("learnings", []))
            result["patterns_added"].extend(edit_result.get("patterns_added", []))

        elif feedback.action == "rejected":
            reject_result = await self.learn_from_rejection(
                feedback.original_content,
                feedback.feedback_text,
                feedback.generation_type
            )
            result["learnings"].extend(reject_result.get("learnings", []))

        elif feedback.action == "thumbs_down":
            # User explicitly said this was bad
            await self._add_negative_example(feedback.original_content)

        elif feedback.action in ["approved", "thumbs_up"]:
            # User liked this - boost similar examples
            await self._boost_similar_examples(feedback.original_content)
            result["example_weights_updated"] = True

        # 2. Extract patterns if we have explicit text feedback
        if feedback.feedback_text:
            text_result = await self.process_text_feedback(
                feedback.feedback_text,
                feedback.original_content
            )
            result["learnings"].extend(text_result.get("learnings", []))

        # 3. Save feedback record
        await self._save_feedback_record(feedback)

        # 4. Mark as processed
        feedback.processed = True
        feedback.learnings_extracted = [l["insight"] for l in result["learnings"]]

        return result

    async def learn_from_edit(
        self,
        original: str,
        edited: str,
        content_type: str
    ) -> Dict:
        """
        Learn from user edits to identify patterns.

        When user edits AI-generated content:
        - Removed phrases → potential banned patterns
        - Added phrases → style signals (user actually uses these)
        - Length changes → length preference adjustment
        - Tone changes → tone preference adjustment

        Args:
            original: Original AI-generated content
            edited: User's edited version
            content_type: "post" or "comment"

        Returns:
            Extracted learnings and patterns
        """
        learnings = []
        patterns_added = []

        if not original or not edited:
            return {"learnings": [], "patterns_added": []}

        # 1. Calculate edit distance
        edit_distance = 1.0 - difflib.SequenceMatcher(None, original, edited).ratio()

        # 2. Find specific changes using diff
        changes = self._extract_changes(original, edited)

        # 3. Analyze removed text
        for removed in changes["removed"]:
            removed_lower = removed.lower().strip()

            # Check if it's a known AI phrase
            is_ai_phrase = self.banned_manager.contains_banned(removed)

            if is_ai_phrase or len(removed) > 10:
                # Add to user's banned patterns
                self.banned_manager.add_user_pattern(
                    phrase=removed,
                    category="learned",
                    source="learned_from_edit",
                    confidence=0.7 if is_ai_phrase else 0.5
                )
                patterns_added.append(removed)

                learnings.append({
                    "category": "phrase_to_avoid",
                    "insight": f"User removed '{removed}' - avoid this phrase",
                    "evidence": [f"Removed in edit (distance: {edit_distance:.2f})"],
                    "confidence": 0.7
                })

        # 4. Analyze added text (user's authentic style)
        for added in changes["added"]:
            if len(added) > 5:
                learnings.append({
                    "category": "phrase_to_use",
                    "insight": f"User added '{added}' - this is their authentic voice",
                    "evidence": [f"Added in edit"],
                    "confidence": 0.6
                })

        # 5. Analyze length change
        length_diff = len(edited) - len(original)
        if abs(length_diff) > 20:
            direction = "shorter" if length_diff < 0 else "longer"
            learnings.append({
                "category": "length_preference",
                "insight": f"User prefers {direction} {content_type}s (changed by {abs(length_diff)} chars)",
                "evidence": [f"Edit: {len(original)} → {len(edited)} chars"],
                "confidence": 0.5
            })

        # 6. Save learnings to store
        for learning in learnings:
            await self._save_learning(learning)

        return {
            "learnings": learnings,
            "patterns_added": patterns_added,
            "edit_distance": edit_distance,
            "changes": changes
        }

    async def learn_from_rejection(
        self,
        original: str,
        reason: Optional[str],
        content_type: str
    ) -> Dict:
        """
        Learn from rejected content.

        Args:
            original: Rejected content
            reason: User's reason for rejection (optional)
            content_type: "post" or "comment"

        Returns:
            Extracted learnings
        """
        learnings = []

        # Add to negative examples
        await self._add_negative_example(original)

        # Check for common rejection patterns
        if reason:
            reason_lower = reason.lower()

            if "doesn't sound like me" in reason_lower or "not my style" in reason_lower:
                learnings.append({
                    "category": "style_mismatch",
                    "insight": "Generated content didn't match user's voice",
                    "evidence": [f"Rejection reason: {reason}"],
                    "confidence": 0.8
                })

            elif "too formal" in reason_lower:
                learnings.append({
                    "category": "tone_adjustment",
                    "insight": "User prefers more casual tone",
                    "evidence": [f"Rejection reason: {reason}"],
                    "confidence": 0.8
                })

            elif "too casual" in reason_lower:
                learnings.append({
                    "category": "tone_adjustment",
                    "insight": "User prefers more professional tone",
                    "evidence": [f"Rejection reason: {reason}"],
                    "confidence": 0.8
                })

            elif "generic" in reason_lower or "ai" in reason_lower:
                learnings.append({
                    "category": "authenticity",
                    "insight": "Content was too generic/AI-sounding",
                    "evidence": [f"Rejection reason: {reason}"],
                    "confidence": 0.9
                })

        for learning in learnings:
            await self._save_learning(learning)

        return {"learnings": learnings}

    async def process_text_feedback(
        self,
        feedback_text: str,
        original_content: str
    ) -> Dict:
        """
        Process explicit text feedback from user.

        Args:
            feedback_text: User's feedback text
            original_content: The content being reviewed

        Returns:
            Extracted learnings
        """
        learnings = []
        feedback_lower = feedback_text.lower()

        # Pattern: "I never say X"
        never_patterns = [
            r"i never say[s]? ['\"]?([^'\"]+)['\"]?",
            r"i don't say ['\"]?([^'\"]+)['\"]?",
            r"i wouldn't say ['\"]?([^'\"]+)['\"]?"
        ]

        import re
        for pattern in never_patterns:
            matches = re.findall(pattern, feedback_lower, re.IGNORECASE)
            for match in matches:
                phrase = match.strip()
                if len(phrase) > 2:
                    self.banned_manager.add_user_pattern(
                        phrase=phrase,
                        category="user_feedback",
                        source="explicit_feedback",
                        confidence=1.0
                    )
                    learnings.append({
                        "category": "phrase_to_avoid",
                        "insight": f"User explicitly said they never say '{phrase}'",
                        "evidence": [f"User feedback: {feedback_text}"],
                        "confidence": 1.0
                    })

        # Pattern: "More like X" or "I usually say X"
        preference_patterns = [
            r"i (?:usually|typically|always) say ['\"]?([^'\"]+)['\"]?",
            r"more like ['\"]?([^'\"]+)['\"]?",
            r"i would say ['\"]?([^'\"]+)['\"]?"
        ]

        for pattern in preference_patterns:
            matches = re.findall(pattern, feedback_lower, re.IGNORECASE)
            for match in matches:
                phrase = match.strip()
                if len(phrase) > 2:
                    learnings.append({
                        "category": "phrase_to_use",
                        "insight": f"User prefers saying '{phrase}'",
                        "evidence": [f"User feedback: {feedback_text}"],
                        "confidence": 0.9
                    })

        for learning in learnings:
            await self._save_learning(learning)

        return {"learnings": learnings}

    # ═══════════════════════════════════════════════════════════════════════════
    # SLEEP-TIME COMPUTE (Background Consolidation)
    # ═══════════════════════════════════════════════════════════════════════════

    async def consolidate_learnings(self) -> Dict:
        """
        Consolidate all feedback into actionable rules.

        This is the "sleep-time compute" that should run periodically
        (e.g., daily) to:
        1. Aggregate feedback patterns
        2. Identify consistent patterns
        3. Update confidence scores
        4. Prune low-confidence learnings
        5. Update style profile weights

        Returns:
            Consolidation results
        """
        if not self.store or not self.user_id:
            return {"error": "No store or user_id"}

        results = {
            "learnings_processed": 0,
            "patterns_consolidated": 0,
            "low_confidence_pruned": 0,
            "profile_updates": []
        }

        # 1. Get all learnings
        learnings = await self._get_all_learnings()
        results["learnings_processed"] = len(learnings)

        # 2. Group by category
        by_category = {}
        for learning in learnings:
            cat = learning.get("category", "unknown")
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(learning)

        # 3. Consolidate phrase_to_avoid patterns
        if "phrase_to_avoid" in by_category:
            phrase_counts = Counter()
            for l in by_category["phrase_to_avoid"]:
                # Extract phrase from insight
                insight = l.get("insight", "")
                if "'" in insight:
                    phrase = insight.split("'")[1]
                    phrase_counts[phrase] += 1

            # Patterns that appear multiple times get higher confidence
            for phrase, count in phrase_counts.items():
                if count >= 2:
                    self.banned_manager.add_user_pattern(
                        phrase=phrase,
                        category="consolidated",
                        source="consolidated_feedback",
                        confidence=min(1.0, 0.5 + count * 0.2)
                    )
                    results["patterns_consolidated"] += 1

        # 4. Consolidate tone preferences
        if "tone_adjustment" in by_category:
            tone_prefs = {"casual": 0, "professional": 0}
            for l in by_category["tone_adjustment"]:
                insight = l.get("insight", "").lower()
                if "casual" in insight:
                    tone_prefs["casual"] += 1
                elif "professional" in insight:
                    tone_prefs["professional"] += 1

            # Determine dominant preference
            if tone_prefs["casual"] > tone_prefs["professional"]:
                results["profile_updates"].append({
                    "field": "tone",
                    "value": "casual",
                    "confidence": tone_prefs["casual"] / (tone_prefs["casual"] + tone_prefs["professional"])
                })
            elif tone_prefs["professional"] > tone_prefs["casual"]:
                results["profile_updates"].append({
                    "field": "tone",
                    "value": "professional",
                    "confidence": tone_prefs["professional"] / (tone_prefs["casual"] + tone_prefs["professional"])
                })

        # 5. Prune low-confidence learnings older than 30 days
        cutoff = datetime.utcnow() - timedelta(days=30)
        pruned = await self._prune_old_learnings(cutoff, min_confidence=0.3)
        results["low_confidence_pruned"] = pruned

        return results

    # ═══════════════════════════════════════════════════════════════════════════
    # APPLY LEARNINGS TO GENERATION
    # ═══════════════════════════════════════════════════════════════════════════

    async def get_learnings_prompt(self) -> str:
        """
        Generate a prompt section with learned rules.

        Returns:
            Formatted string for inclusion in generation prompts
        """
        if not self.store or not self.user_id:
            return ""

        learnings = await self._get_all_learnings()

        if not learnings:
            return ""

        prompt_parts = ["📚 LEARNED FROM YOUR FEEDBACK:"]

        # Group by category
        by_category = {}
        for learning in learnings:
            cat = learning.get("category", "unknown")
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(learning)

        # Format each category
        if "phrase_to_avoid" in by_category:
            prompt_parts.append("\n🚫 Phrases to AVOID (you've told me you never say these):")
            for l in by_category["phrase_to_avoid"][:5]:
                insight = l.get("insight", "")
                prompt_parts.append(f"  - {insight}")

        if "phrase_to_use" in by_category:
            prompt_parts.append("\n✅ Your preferred phrases:")
            for l in by_category["phrase_to_use"][:5]:
                insight = l.get("insight", "")
                prompt_parts.append(f"  - {insight}")

        if "tone_adjustment" in by_category:
            prompt_parts.append("\n🎭 Tone preferences:")
            for l in by_category["tone_adjustment"][:3]:
                insight = l.get("insight", "")
                prompt_parts.append(f"  - {insight}")

        if "length_preference" in by_category:
            prompt_parts.append("\n📏 Length preferences:")
            for l in by_category["length_preference"][:2]:
                insight = l.get("insight", "")
                prompt_parts.append(f"  - {insight}")

        return "\n".join(prompt_parts)

    # ═══════════════════════════════════════════════════════════════════════════
    # HELPER METHODS
    # ═══════════════════════════════════════════════════════════════════════════

    def _extract_changes(self, original: str, edited: str) -> Dict:
        """Extract added and removed text using diff."""
        changes = {"added": [], "removed": []}

        # Word-level diff
        original_words = original.split()
        edited_words = edited.split()

        matcher = difflib.SequenceMatcher(None, original_words, edited_words)

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'delete':
                removed = " ".join(original_words[i1:i2])
                if removed.strip():
                    changes["removed"].append(removed)
            elif tag == 'insert':
                added = " ".join(edited_words[j1:j2])
                if added.strip():
                    changes["added"].append(added)
            elif tag == 'replace':
                removed = " ".join(original_words[i1:i2])
                added = " ".join(edited_words[j1:j2])
                if removed.strip():
                    changes["removed"].append(removed)
                if added.strip():
                    changes["added"].append(added)

        return changes

    async def _save_learning(self, learning: Dict):
        """Save a learning to the store."""
        if not self.store or not self.user_id:
            return

        try:
            namespace = (self.user_id, "learnings")
            learning_id = f"learning_{datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}"

            self.store.put(namespace, learning_id, {
                **learning,
                "created_at": datetime.utcnow().isoformat()
            })
        except Exception as e:
            logger.error(f"Failed to save learning: {e}")

    async def _get_all_learnings(self) -> List[Dict]:
        """Get all learnings from store."""
        if not self.store or not self.user_id:
            return []

        try:
            namespace = (self.user_id, "learnings")
            results = self.store.search(namespace, query="")
            return [r.value for r in results] if results else []
        except Exception as e:
            logger.error(f"Failed to get learnings: {e}")
            return []

    async def _prune_old_learnings(self, cutoff: datetime, min_confidence: float) -> int:
        """Prune old low-confidence learnings."""
        if not self.store or not self.user_id:
            return 0

        # This would need store.delete() support
        # For now, just return 0
        return 0

    async def _save_feedback_record(self, feedback: FeedbackRecord):
        """Save feedback record to store."""
        if not self.store or not self.user_id:
            return

        try:
            namespace = (self.user_id, "feedback_history")
            self.store.put(namespace, feedback.feedback_id, {
                "generation_type": feedback.generation_type,
                "original_content": feedback.original_content,
                "edited_content": feedback.edited_content,
                "action": feedback.action,
                "feedback_text": feedback.feedback_text,
                "edit_distance": feedback.edit_distance,
                "processed": feedback.processed,
                "learnings_extracted": feedback.learnings_extracted,
                "timestamp": feedback.timestamp.isoformat()
            })
        except Exception as e:
            logger.error(f"Failed to save feedback record: {e}")

    async def _add_negative_example(self, content: str):
        """Add content to negative examples (content that didn't work)."""
        if not self.store or not self.user_id:
            return

        try:
            namespace = (self.user_id, "negative_examples")
            example_id = f"neg_{datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}"
            self.store.put(namespace, example_id, {
                "content": content,
                "created_at": datetime.utcnow().isoformat()
            })
        except Exception as e:
            logger.error(f"Failed to add negative example: {e}")

    async def _boost_similar_examples(self, content: str):
        """Boost weight of examples similar to approved content."""
        # This would integrate with the writing style manager
        # to increase weight of similar examples
        pass


# ═══════════════════════════════════════════════════════════════════════════════
# FACTORY FUNCTION
# ═══════════════════════════════════════════════════════════════════════════════

def create_feedback_processor(store, user_id: str, model=None) -> FeedbackProcessor:
    """
    Create a FeedbackProcessor instance.

    Args:
        store: LangGraph store
        user_id: User ID
        model: Optional LLM model for advanced processing

    Returns:
        FeedbackProcessor instance
    """
    return FeedbackProcessor(store=store, user_id=user_id, model=model)
