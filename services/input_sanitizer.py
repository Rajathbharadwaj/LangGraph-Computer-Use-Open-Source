"""
Input Sanitization Service for LLM Prompt Injection Protection

Provides basic protections against prompt injection attacks by:
- Stripping common injection patterns
- Limiting input lengths
- Escaping potentially harmful characters

For more comprehensive protection, consider integrating with Kwality AI.
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Maximum lengths for different input types
MAX_LENGTHS = {
    "user_prompt": 10000,       # User-provided prompts/instructions
    "post_content": 5000,       # Social media post content
    "comment": 1000,            # Comment text
    "username": 50,             # Social media username
    "workflow_name": 100,       # Workflow names
    "custom_instructions": 2000, # Custom workflow instructions
    "default": 5000,            # Default max length
}

# Patterns that indicate potential prompt injection attempts
INJECTION_PATTERNS = [
    # System prompt override attempts
    r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)",
    r"disregard\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)",
    r"forget\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)",
    r"new\s+system\s+prompt",
    r"you\s+are\s+now\s+(a|an|the)",
    r"pretend\s+(you|to\s+be)",
    r"act\s+as\s+(if|though|a)",
    r"roleplay\s+as",

    # Delimiter attacks
    r"</?system>",
    r"\[/?system\]",
    r"###\s*(system|instruction|admin)",
    r"---\s*(system|instruction|admin)",

    # Base64/encoding bypass attempts
    r"decode\s+(this|the\s+following)\s+(base64|encoded)",
    r"eval\s*\(",
    r"exec\s*\(",

    # Jailbreak keywords (not comprehensive, just common patterns)
    r"do\s+anything\s+now",
    r"developer\s+mode",
    r"(enable|activate)\s+developer",
    r"DAN\s+mode",
    r"jailbreak",

    # Context manipulation
    r"the\s+above\s+(is|was)\s+(a\s+)?(test|joke|lie)",
    r"actually,?\s+ignore\s+that",
    r"scratch\s+that",
]

# Compiled patterns for efficiency
_compiled_patterns = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in INJECTION_PATTERNS
]


class InputSanitizer:
    """
    Sanitizes user inputs to protect against prompt injection attacks.

    Usage:
        sanitizer = InputSanitizer()
        clean_prompt = sanitizer.sanitize(user_input, input_type="user_prompt")
    """

    def __init__(self, strict_mode: bool = False):
        """
        Initialize the sanitizer.

        Args:
            strict_mode: If True, reject inputs with injection patterns.
                        If False (default), log warning but allow modified input.
        """
        self.strict_mode = strict_mode

    def sanitize(
        self,
        text: str,
        input_type: str = "default",
        max_length: Optional[int] = None
    ) -> str:
        """
        Sanitize user input for safe use in LLM prompts.

        Args:
            text: The user-provided text to sanitize
            input_type: Type of input for length limits (user_prompt, post_content, etc.)
            max_length: Override the default max length for this input type

        Returns:
            Sanitized text

        Raises:
            ValueError: In strict mode, if injection patterns are detected
        """
        if not text:
            return ""

        original_text = text

        # 1. Enforce length limits
        limit = max_length or MAX_LENGTHS.get(input_type, MAX_LENGTHS["default"])
        if len(text) > limit:
            logger.warning(f"Input truncated from {len(text)} to {limit} chars")
            text = text[:limit]

        # 2. Check for injection patterns
        detected_patterns = self._detect_injection_patterns(text)
        if detected_patterns:
            logger.warning(f"⚠️ Potential injection detected: {detected_patterns}")
            if self.strict_mode:
                raise ValueError(f"Input rejected: potential injection patterns detected")
            # In non-strict mode, we continue but log the warning

        # 3. Escape potentially harmful sequences
        text = self._escape_harmful_sequences(text)

        # 4. Normalize whitespace
        text = self._normalize_whitespace(text)

        return text

    def sanitize_for_prompt(
        self,
        text: str,
        context_label: str = "USER_INPUT",
        max_length: int = 5000
    ) -> str:
        """
        Sanitize and wrap user input for safe inclusion in prompts.

        Wraps the input with clear boundaries to prevent it from
        being interpreted as instructions.

        Args:
            text: User input to sanitize
            context_label: Label to use for wrapping
            max_length: Maximum length

        Returns:
            Sanitized and wrapped text
        """
        clean_text = self.sanitize(text, max_length=max_length)

        # Wrap with clear boundaries
        wrapped = f"[{context_label}_START]\n{clean_text}\n[{context_label}_END]"

        return wrapped

    def _detect_injection_patterns(self, text: str) -> list:
        """
        Detect potential injection patterns in text.

        Returns:
            List of detected pattern names (empty if none found)
        """
        detected = []
        for i, pattern in enumerate(_compiled_patterns):
            if pattern.search(text):
                detected.append(INJECTION_PATTERNS[i][:50])  # Truncate pattern for logging
        return detected

    def _escape_harmful_sequences(self, text: str) -> str:
        """
        Escape potentially harmful sequences.

        This doesn't remove content but makes it less likely to
        be interpreted as control sequences.
        """
        # Escape angle brackets that could be interpreted as XML tags
        text = text.replace("<system>", "[system]")
        text = text.replace("</system>", "[/system]")
        text = text.replace("<instructions>", "[instructions]")
        text = text.replace("</instructions>", "[/instructions]")

        # Escape triple backticks that might be used to break out of code blocks
        text = text.replace("```", "` ` `")

        return text

    def _normalize_whitespace(self, text: str) -> str:
        """
        Normalize excessive whitespace.
        """
        # Replace multiple newlines with double newline
        text = re.sub(r'\n{3,}', '\n\n', text)

        # Replace multiple spaces with single space
        text = re.sub(r' {3,}', ' ', text)

        return text.strip()

    def validate_username(self, username: str) -> str:
        """
        Validate and sanitize a username/handle.

        Args:
            username: The username to validate

        Returns:
            Cleaned username

        Raises:
            ValueError: If username is invalid
        """
        if not username:
            raise ValueError("Username cannot be empty")

        # Remove @ prefix if present
        username = username.lstrip('@')

        # Only allow alphanumeric and underscore
        if not re.match(r'^[a-zA-Z0-9_]+$', username):
            raise ValueError("Username can only contain letters, numbers, and underscores")

        # Enforce length
        if len(username) > MAX_LENGTHS["username"]:
            raise ValueError(f"Username too long (max {MAX_LENGTHS['username']} chars)")

        return username


# Global instance for convenience
_sanitizer = InputSanitizer(strict_mode=False)


def sanitize_input(text: str, input_type: str = "default") -> str:
    """
    Convenience function to sanitize input using the global sanitizer.

    Args:
        text: Text to sanitize
        input_type: Type of input for length limits

    Returns:
        Sanitized text
    """
    return _sanitizer.sanitize(text, input_type)


def sanitize_for_prompt(text: str, context_label: str = "USER_INPUT") -> str:
    """
    Convenience function to sanitize and wrap input for prompts.

    Args:
        text: User input
        context_label: Label for wrapping

    Returns:
        Sanitized and wrapped text
    """
    return _sanitizer.sanitize_for_prompt(text, context_label)


def validate_username(username: str) -> str:
    """
    Convenience function to validate a username.

    Args:
        username: The username to validate

    Returns:
        Cleaned username
    """
    return _sanitizer.validate_username(username)
