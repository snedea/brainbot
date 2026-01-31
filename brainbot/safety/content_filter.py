"""BrainBot content filter for PG-13 compliance."""

import logging
import re
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class FilterResult:
    """Result of content filtering."""
    is_safe: bool
    original_content: str
    filtered_content: Optional[str] = None
    violations: list[str] = None
    confidence: float = 1.0

    def __post_init__(self):
        if self.violations is None:
            self.violations = []
        if self.filtered_content is None:
            self.filtered_content = self.original_content


class ContentFilter:
    """
    PG-13 content filter for BrainBot-generated content.

    Filters content to ensure it's appropriate for all audiences.
    Used for bedtime stories and any public-facing content.
    """

    # Words/phrases that indicate potentially inappropriate content
    PROHIBITED_PATTERNS = [
        # Violence
        r'\b(kill|murder|death|dead|die|dies|dying|blood|gore|violent|weapon|gun|knife|stab|shoot|attack)\b',
        r'\b(torture|abuse|hurt|harm|pain|suffer|wound|injure)\b',

        # Horror/scary
        r'\b(horror|scary|terrifying|nightmare|monster|demon|devil|evil|curse|haunted|zombie)\b',
        r'\b(scream|shriek|terror|frightening|creepy|sinister)\b',

        # Inappropriate language (mild - just flag for review)
        r'\b(damn|hell|crap|stupid|idiot|dumb|hate)\b',

        # Adult themes
        r'\b(drunk|alcohol|beer|wine|drugs|smoking|cigarette)\b',
        r'\b(kiss|romance|dating|boyfriend|girlfriend|love\s+interest)\b',

        # Controversial
        r'\b(politics|politician|election|vote|democrat|republican)\b',
        r'\b(religion|religious|god|jesus|allah|buddha|pray|prayer)\b',
    ]

    # Themes that are encouraged
    POSITIVE_THEMES = [
        "adventure",
        "friendship",
        "discovery",
        "learning",
        "nature",
        "science",
        "creativity",
        "problem-solving",
        "teamwork",
        "kindness",
        "imagination",
        "exploration",
        "courage",
        "perseverance",
        "family",
        "animals",
        "space",
        "ocean",
        "forest",
    ]

    def __init__(self, strict_mode: bool = True):
        """
        Initialize content filter.

        Args:
            strict_mode: If True, reject content with any violations.
                        If False, allow mild violations with warnings.
        """
        self.strict_mode = strict_mode
        self._compiled_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.PROHIBITED_PATTERNS
        ]

    def filter_content(self, content: str) -> FilterResult:
        """
        Filter content for PG-13 compliance.

        Args:
            content: Content to filter

        Returns:
            FilterResult with safety status and any violations
        """
        if not content or not content.strip():
            return FilterResult(is_safe=True, original_content=content)

        violations = []

        # Check against prohibited patterns
        for i, pattern in enumerate(self._compiled_patterns):
            matches = pattern.findall(content)
            if matches:
                violations.extend([f"Found prohibited term: '{m}'" for m in set(matches)])

        # Calculate confidence (lower if many violations)
        if violations:
            confidence = max(0.0, 1.0 - (len(violations) * 0.1))
        else:
            confidence = 1.0

        # Determine if safe
        is_safe = len(violations) == 0 or (not self.strict_mode and len(violations) < 3)

        if violations:
            logger.warning(f"Content filter found {len(violations)} violation(s)")
            for v in violations[:5]:  # Log first 5
                logger.debug(f"  - {v}")

        return FilterResult(
            is_safe=is_safe,
            original_content=content,
            filtered_content=content if is_safe else None,
            violations=violations,
            confidence=confidence,
        )

    def filter_story(self, story: str) -> FilterResult:
        """
        Filter a bedtime story with story-specific rules.

        Args:
            story: Story content

        Returns:
            FilterResult
        """
        # First do basic filtering
        result = self.filter_content(story)

        if not result.is_safe:
            return result

        # Additional story-specific checks
        additional_violations = []

        # Check length (stories shouldn't be too short or too long)
        word_count = len(story.split())
        if word_count < 100:
            additional_violations.append("Story too short (< 100 words)")
        elif word_count > 2000:
            additional_violations.append("Story too long (> 2000 words)")

        # Check for positive ending indicators
        ending_markers = ["happily", "smiled", "happy", "joy", "learned", "friends", "together", "home"]
        last_paragraph = story.split("\n\n")[-1].lower() if "\n\n" in story else story[-500:].lower()

        has_positive_ending = any(marker in last_paragraph for marker in ending_markers)
        if not has_positive_ending:
            additional_violations.append("Story may not have a positive ending")

        # Combine violations
        all_violations = result.violations + additional_violations
        is_safe = len(all_violations) == 0 or (not self.strict_mode and len(all_violations) < 3)

        return FilterResult(
            is_safe=is_safe,
            original_content=story,
            filtered_content=story if is_safe else None,
            violations=all_violations,
            confidence=result.confidence,
        )

    def suggest_improvements(self, filter_result: FilterResult) -> list[str]:
        """
        Suggest improvements for content that failed filtering.

        Args:
            filter_result: Result from filtering

        Returns:
            List of improvement suggestions
        """
        suggestions = []

        for violation in filter_result.violations:
            if "prohibited term" in violation.lower():
                term = violation.split("'")[1] if "'" in violation else "the term"
                suggestions.append(f"Replace '{term}' with a more positive alternative")

            elif "too short" in violation.lower():
                suggestions.append("Expand the story with more descriptive details")

            elif "too long" in violation.lower():
                suggestions.append("Consider condensing the story for bedtime reading")

            elif "positive ending" in violation.lower():
                suggestions.append("Add a warm, happy conclusion to the story")

        # Add general suggestions
        if filter_result.violations:
            suggestions.append(f"Consider incorporating themes like: {', '.join(self.POSITIVE_THEMES[:5])}")

        return suggestions

    def validate_theme(self, theme: str) -> bool:
        """
        Validate that a theme is appropriate.

        Args:
            theme: Theme to validate

        Returns:
            True if theme is appropriate
        """
        theme_lower = theme.lower()

        # Check if it's a known positive theme
        if theme_lower in [t.lower() for t in self.POSITIVE_THEMES]:
            return True

        # Check against prohibited patterns
        for pattern in self._compiled_patterns:
            if pattern.search(theme):
                return False

        return True

    def get_random_theme(self) -> str:
        """Get a random appropriate theme."""
        import random
        return random.choice(self.POSITIVE_THEMES)
