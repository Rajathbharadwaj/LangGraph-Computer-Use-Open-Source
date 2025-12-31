"""
Style Match Scorer and LLM Grader for AI-Generated Content

This module provides:
1. StyleMatchScorer: Rule-based scoring using NLP analysis
2. LLMStyleGrader: Claude-based grading for authenticity validation

The grader acts as a final quality gate before content is shown to users,
ensuring generated content is indistinguishable from user's writing.
"""

import re
import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime

# NLP imports
import spacy
import nltk
from nltk.util import ngrams
from collections import Counter
import textstat

# Local imports
from banned_patterns_manager import BannedPatternsManager, quick_validate

logger = logging.getLogger(__name__)

# Ensure NLTK data is available
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt', quiet=True)

try:
    nltk.data.find('tokenizers/punkt_tab')
except LookupError:
    nltk.download('punkt_tab', quiet=True)

# Load spaCy model
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    logger.warning("spaCy model not found. Run: python -m spacy download en_core_web_sm")
    nlp = None


@dataclass
class StyleScore:
    """Detailed style matching score."""
    overall_score: float  # 0-1, composite score
    vocabulary_match: float  # 0-1, word choice similarity
    length_match: float  # 0-1, within typical range
    tone_match: float  # 0-1, tone alignment
    structure_match: float  # 0-1, sentence structure
    punctuation_match: float  # 0-1, punctuation patterns
    banned_phrase_penalty: float  # 0-1, 0 = no banned phrases
    confidence: str  # "high", "medium", "low"
    warnings: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    should_regenerate: bool = False
    regeneration_reason: Optional[str] = None


class StyleMatchScorer:
    """
    Rule-based style matching scorer using NLP analysis.

    Compares generated content against user's style profile
    using linguistic features extracted via spaCy and NLTK.
    """

    def __init__(self, store=None, user_id: str = None):
        """
        Initialize the style match scorer.

        Args:
            store: LangGraph store for user data
            user_id: User ID for personalization
        """
        self.store = store
        self.user_id = user_id
        self.banned_manager = BannedPatternsManager(store, user_id)

    def score_content(
        self,
        generated_text: str,
        content_type: str,  # "post" or "comment"
        style_profile: Optional[Dict] = None,
        user_examples: Optional[List[str]] = None
    ) -> StyleScore:
        """
        Score generated content against user's style.

        Args:
            generated_text: The AI-generated content
            content_type: "post" or "comment"
            style_profile: User's DeepStyleProfile as dict
            user_examples: List of user's past posts for comparison

        Returns:
            StyleScore with detailed metrics
        """
        warnings = []
        suggestions = []

        # 1. Banned phrase check
        is_valid, detected_banned = self.banned_manager.validate_content(generated_text)
        if not is_valid:
            banned_penalty = min(1.0, len(detected_banned) * 0.3)  # 0.3 per banned phrase
            warnings.append(f"Contains {len(detected_banned)} banned phrases: {[d['phrase'] for d in detected_banned]}")
        else:
            banned_penalty = 0.0

        # 2. Length match
        length_score = 1.0
        if style_profile:
            target_length = style_profile.get(
                "avg_comment_length" if content_type == "comment" else "avg_post_length",
                100
            )
            actual_length = len(generated_text)
            # Allow 50% variance
            length_ratio = actual_length / target_length if target_length > 0 else 1.0
            if length_ratio < 0.5:
                length_score = 0.5
                warnings.append(f"Too short: {actual_length} chars vs typical {target_length}")
                suggestions.append(f"Expand to ~{target_length} characters")
            elif length_ratio > 1.5:
                length_score = 0.5
                warnings.append(f"Too long: {actual_length} chars vs typical {target_length}")
                suggestions.append(f"Shorten to ~{target_length} characters")
            else:
                length_score = 1.0 - abs(1.0 - length_ratio) * 0.5

        # 3. Vocabulary match (if we have examples)
        vocab_score = 0.8  # Default
        if user_examples and nlp:
            vocab_score = self._score_vocabulary(generated_text, user_examples)
            if vocab_score < 0.6:
                warnings.append("Vocabulary doesn't match user's typical word choices")
                suggestions.append("Use more words from user's vocabulary")

        # 4. Tone match
        tone_score = 0.8  # Default
        if style_profile:
            tone_score = self._score_tone(generated_text, style_profile)
            if tone_score < 0.6:
                expected_tone = style_profile.get("tone", "unknown")
                warnings.append(f"Tone doesn't match user's typical {expected_tone} style")

        # 5. Structure match
        structure_score = 0.8  # Default
        if style_profile and nlp:
            structure_score = self._score_structure(generated_text, style_profile)
            if structure_score < 0.6:
                warnings.append("Sentence structure differs from user's typical patterns")

        # 6. Punctuation match
        punct_score = 0.9  # Default
        if style_profile:
            punct_score = self._score_punctuation(generated_text, style_profile)

        # Calculate overall score
        overall = (
            vocab_score * 0.25 +
            length_score * 0.15 +
            tone_score * 0.20 +
            structure_score * 0.15 +
            punct_score * 0.10 +
            (1.0 - banned_penalty) * 0.15  # Banned phrases heavily penalized
        )

        # Determine confidence and regeneration
        if overall >= 0.8:
            confidence = "high"
        elif overall >= 0.6:
            confidence = "medium"
        else:
            confidence = "low"

        should_regenerate = overall < 0.6 or banned_penalty > 0
        regeneration_reason = None
        if should_regenerate:
            if banned_penalty > 0:
                regeneration_reason = f"Contains banned phrases: {[d['phrase'] for d in detected_banned]}"
            else:
                regeneration_reason = "Style match score too low"

        return StyleScore(
            overall_score=round(overall, 3),
            vocabulary_match=round(vocab_score, 3),
            length_match=round(length_score, 3),
            tone_match=round(tone_score, 3),
            structure_match=round(structure_score, 3),
            punctuation_match=round(punct_score, 3),
            banned_phrase_penalty=round(banned_penalty, 3),
            confidence=confidence,
            warnings=warnings,
            suggestions=suggestions,
            should_regenerate=should_regenerate,
            regeneration_reason=regeneration_reason
        )

    def _score_vocabulary(self, generated: str, examples: List[str]) -> float:
        """Score vocabulary similarity using word overlap and embeddings."""
        if not nlp:
            return 0.8

        # Extract lemmatized content words from generated text
        gen_doc = nlp(generated.lower())
        gen_words = set(
            token.lemma_ for token in gen_doc
            if not token.is_stop and not token.is_punct and len(token.text) > 2
        )

        # Extract from user examples
        user_words = set()
        for example in examples[:20]:  # Limit to 20 examples
            doc = nlp(example.lower())
            for token in doc:
                if not token.is_stop and not token.is_punct and len(token.text) > 2:
                    user_words.add(token.lemma_)

        if not gen_words or not user_words:
            return 0.7

        # Calculate Jaccard similarity
        overlap = len(gen_words & user_words)
        union = len(gen_words | user_words)
        jaccard = overlap / union if union > 0 else 0

        # Boost score if using user's unique words
        user_vocab_usage = overlap / len(gen_words) if gen_words else 0

        return min(1.0, jaccard * 0.5 + user_vocab_usage * 0.5 + 0.3)

    def _score_tone(self, generated: str, profile: Dict) -> float:
        """Score tone alignment with user's profile."""
        # Get expected tone
        expected_tone = profile.get("tone", "neutral")
        tone_scores = profile.get("tone_scores", {})

        # Analyze generated text tone
        text_lower = generated.lower()

        # Simple tone indicators
        casual_indicators = ["lol", "haha", "tbh", "ngl", "gonna", "wanna", "kinda"]
        professional_indicators = ["furthermore", "however", "therefore", "regarding"]
        technical_indicators = ["api", "function", "implementation", "algorithm", "parameter"]

        casual_count = sum(1 for ind in casual_indicators if ind in text_lower)
        professional_count = sum(1 for ind in professional_indicators if ind in text_lower)
        technical_count = sum(1 for ind in technical_indicators if ind in text_lower)

        # Determine generated tone
        if casual_count > professional_count and casual_count > technical_count:
            detected_tone = "casual"
        elif professional_count > casual_count:
            detected_tone = "professional"
        elif technical_count > 0:
            detected_tone = "technical"
        else:
            detected_tone = "neutral"

        # Score based on match
        if detected_tone == expected_tone:
            return 1.0
        elif expected_tone == "neutral":
            return 0.8
        else:
            return 0.5

    def _score_structure(self, generated: str, profile: Dict) -> float:
        """Score sentence structure similarity."""
        if not nlp:
            return 0.8

        doc = nlp(generated)
        sentences = list(doc.sents)

        if not sentences:
            return 0.5

        # Calculate average sentence length
        avg_sent_len = sum(len(sent) for sent in sentences) / len(sentences)
        expected_len = profile.get("avg_sentence_length", 15)

        # Score based on similarity
        if expected_len > 0:
            ratio = avg_sent_len / expected_len
            if 0.7 <= ratio <= 1.3:
                return 1.0
            elif 0.5 <= ratio <= 1.5:
                return 0.7
            else:
                return 0.4

        return 0.8

    def _score_punctuation(self, generated: str, profile: Dict) -> float:
        """Score punctuation pattern similarity."""
        expected_patterns = profile.get("punctuation_patterns", {})

        if not expected_patterns:
            return 0.9

        # Analyze generated punctuation
        text_len = len(generated) if generated else 1
        punct_counts = {
            "...": generated.count("...") / text_len * 100,
            "!": generated.count("!") / text_len * 100,
            "?": generated.count("?") / text_len * 100,
        }

        # Compare with expected
        score = 1.0
        for punct, expected_freq in expected_patterns.items():
            actual_freq = punct_counts.get(punct, 0)
            diff = abs(expected_freq - actual_freq)
            if diff > 0.5:  # More than 0.5% difference
                score -= 0.1

        return max(0.5, score)


class LLMStyleGrader:
    """
    LLM-based style authenticity grader.

    Uses Claude to grade generated content against user's style,
    providing detailed feedback and improvement suggestions.

    Acts as the final quality gate before content is shown to users.
    """

    GRADER_PROMPT = """You are a style authenticity grader. Your job is to determine if the GENERATED content sounds like it was written by the USER based on their examples.

USER'S WRITING EXAMPLES:
{user_examples}

USER'S STYLE PROFILE:
{style_profile}

GENERATED CONTENT:
{generated_content}

CONTENT TYPE: {content_type}

GRADE on these dimensions (0-10 each):

1. **Vocabulary Match** (0-10): Does it use words/phrases the user actually uses?
   - Check for user's specific vocabulary patterns
   - Look for domain-specific terms they use
   - Identify any words that seem out of character

2. **Tone Match** (0-10): Does the formality/casualness match?
   - Compare energy level (enthusiastic vs reserved)
   - Check formality (casual slang vs professional)
   - Assess emotional tone alignment

3. **Structure Match** (0-10): Sentence length, punctuation patterns?
   - Compare sentence length distribution
   - Check punctuation usage (ellipsis, exclamations, questions)
   - Assess paragraph/flow structure

4. **Authenticity Score** (0-10): Would this fool someone who knows the user?
   - Overall natural feel
   - Presence of user's unique quirks/patterns
   - Absence of generic AI patterns

5. **AI Detection Score** (0-10): Does it contain any AI-sounding phrases?
   - 10 = No AI tells detected
   - Check for generic praise ("Great post!", "Love this!")
   - Check for LinkedIn-style phrasing
   - Check for overly enthusiastic language

OUTPUT FORMAT (JSON only, no other text):
{{
    "vocabulary_score": 8,
    "tone_score": 7,
    "structure_score": 9,
    "authenticity_score": 7,
    "ai_detection_score": 9,
    "overall_score": 8.0,
    "pass": true,
    "issues": ["specific issue 1", "specific issue 2"],
    "suggestions": ["specific improvement 1", "specific improvement 2"],
    "detected_ai_phrases": [],
    "missing_user_patterns": ["pattern user typically uses but is missing"]
}}

SCORING RULES:
- overall_score = average of all 5 scores
- pass = true if overall_score >= 7.0
- Be STRICT - users want authentic content, not obvious AI
- If you detect ANY banned phrases, ai_detection_score should be <= 5
- Issues should be specific and actionable
- Suggestions should reference user's actual patterns"""

    IMPROVEMENT_PROMPT = """The generated content failed the style authenticity check.

ORIGINAL CONTENT:
{original_content}

GRADER FEEDBACK:
- Overall Score: {overall_score}/10
- Issues: {issues}
- Suggestions: {suggestions}
- Detected AI Phrases: {detected_ai_phrases}

USER'S STYLE PROFILE:
{style_profile}

USER'S TOP EXAMPLES:
{user_examples}

REWRITE the content to fix all issues while:
1. Matching the user's EXACT vocabulary and tone
2. Removing ALL detected AI phrases
3. Incorporating the grader's specific suggestions
4. Keeping the core message/intent intact

OUTPUT only the rewritten content, nothing else."""

    def __init__(self, model=None, store=None, user_id: str = None):
        """
        Initialize the LLM style grader.

        Args:
            model: Anthropic model instance
            store: LangGraph store for user data
            user_id: User ID for personalization
        """
        self.model = model
        self.store = store
        self.user_id = user_id
        self.rule_scorer = StyleMatchScorer(store, user_id)

    async def grade(
        self,
        generated_text: str,
        content_type: str,
        style_profile: Dict,
        user_examples: List[str],
    ) -> Dict:
        """
        Grade content using LLM.

        Args:
            generated_text: Content to grade
            content_type: "post" or "comment"
            style_profile: User's style profile dict
            user_examples: List of user's example posts

        Returns:
            Grading result dict with scores and feedback
        """
        if not self.model:
            # Fallback to rule-based scoring
            logger.warning("No model provided, using rule-based scoring only")
            rule_score = self.rule_scorer.score_content(
                generated_text, content_type, style_profile, user_examples
            )
            return {
                "vocabulary_score": int(rule_score.vocabulary_match * 10),
                "tone_score": int(rule_score.tone_match * 10),
                "structure_score": int(rule_score.structure_match * 10),
                "authenticity_score": 7,
                "ai_detection_score": int((1 - rule_score.banned_phrase_penalty) * 10),
                "overall_score": rule_score.overall_score * 10,
                "pass": not rule_score.should_regenerate,
                "issues": rule_score.warnings,
                "suggestions": rule_score.suggestions,
                "detected_ai_phrases": [],
                "missing_user_patterns": []
            }

        # Format examples
        examples_text = "\n\n".join([
            f"Example {i+1}:\n{example}"
            for i, example in enumerate(user_examples[:10])
        ])

        # Format profile
        profile_text = json.dumps(style_profile, indent=2, default=str)

        # Build prompt
        prompt = self.GRADER_PROMPT.format(
            user_examples=examples_text,
            style_profile=profile_text,
            generated_content=generated_text,
            content_type=content_type
        )

        try:
            # Call model
            response = await self.model.ainvoke(prompt)

            # Parse response
            response_text = response.content if hasattr(response, 'content') else str(response)

            # Extract JSON from response
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                result = json.loads(json_match.group())
                return result
            else:
                logger.error(f"Could not parse grader response: {response_text}")
                return self._default_result()

        except Exception as e:
            logger.error(f"LLM grading failed: {e}")
            return self._default_result()

    async def grade_and_improve(
        self,
        generated_text: str,
        content_type: str,
        style_profile: Dict,
        user_examples: List[str],
        max_attempts: int = 3
    ) -> Tuple[str, Dict]:
        """
        Grade content and iteratively improve until it passes.

        Args:
            generated_text: Initial content
            content_type: "post" or "comment"
            style_profile: User's style profile
            user_examples: User's example posts
            max_attempts: Max improvement iterations

        Returns:
            (final_content, final_grade)
        """
        current_content = generated_text
        current_grade = None

        for attempt in range(max_attempts):
            # Grade current content
            grade = await self.grade(
                current_content, content_type, style_profile, user_examples
            )
            current_grade = grade

            logger.info(f"Grade attempt {attempt + 1}: {grade.get('overall_score', 0)}/10")

            # Check if passes
            if grade.get("pass", False):
                logger.info(f"Content passed on attempt {attempt + 1}")
                return current_content, grade

            # If doesn't pass and we have more attempts, improve
            if attempt < max_attempts - 1 and self.model:
                improved = await self._improve_content(
                    current_content,
                    grade,
                    style_profile,
                    user_examples
                )
                if improved:
                    current_content = improved
                else:
                    break

        logger.warning(f"Content failed to pass after {max_attempts} attempts")
        return current_content, current_grade

    async def _improve_content(
        self,
        original: str,
        grade: Dict,
        style_profile: Dict,
        user_examples: List[str]
    ) -> Optional[str]:
        """Improve content based on grader feedback."""
        if not self.model:
            return None

        # Format examples
        examples_text = "\n\n".join([
            f"Example {i+1}:\n{example}"
            for i, example in enumerate(user_examples[:5])
        ])

        prompt = self.IMPROVEMENT_PROMPT.format(
            original_content=original,
            overall_score=grade.get("overall_score", 0),
            issues=json.dumps(grade.get("issues", [])),
            suggestions=json.dumps(grade.get("suggestions", [])),
            detected_ai_phrases=json.dumps(grade.get("detected_ai_phrases", [])),
            style_profile=json.dumps(style_profile, indent=2, default=str),
            user_examples=examples_text
        )

        try:
            response = await self.model.ainvoke(prompt)
            improved = response.content if hasattr(response, 'content') else str(response)

            # Basic cleanup
            improved = improved.strip()
            if improved.startswith('"') and improved.endswith('"'):
                improved = improved[1:-1]

            return improved

        except Exception as e:
            logger.error(f"Content improvement failed: {e}")
            return None

    def _default_result(self) -> Dict:
        """Return default result when grading fails."""
        return {
            "vocabulary_score": 5,
            "tone_score": 5,
            "structure_score": 5,
            "authenticity_score": 5,
            "ai_detection_score": 5,
            "overall_score": 5.0,
            "pass": False,
            "issues": ["Grading failed - manual review recommended"],
            "suggestions": [],
            "detected_ai_phrases": [],
            "missing_user_patterns": []
        }


# ═══════════════════════════════════════════════════════════════════════════════
# UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def quick_score(text: str, content_type: str = "comment") -> StyleScore:
    """
    Quick score without user-specific data.

    Args:
        text: Text to score
        content_type: "post" or "comment"

    Returns:
        Basic StyleScore
    """
    scorer = StyleMatchScorer()
    return scorer.score_content(text, content_type)


def should_regenerate(text: str) -> Tuple[bool, str]:
    """
    Quick check if content should be regenerated.

    Returns:
        (should_regenerate, reason)
    """
    score = quick_score(text)
    return score.should_regenerate, score.regeneration_reason or ""
