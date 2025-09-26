"""
Safety Policy Definitions
=========================
Categories, allow-lists, messages, and age bands for BrainBot safety.
"""

from enum import Enum
from typing import List, Set

class SafetyCategory(str, Enum):
    """Content safety categories for moderation."""
    SEXUAL_CONTENT = "sexual_content"
    SEXUAL_MINORS = "sexual_minors"
    SELF_HARM = "self_harm"
    VIOLENCE = "violence"
    WEAPONS_ILLICIT = "weapons_illicit"
    HATE_ABUSE = "hate_abuse"
    DRUGS_ALCOHOL = "drugs_alcohol"
    MEDICAL_ADVICE = "medical_advice"
    PRIVACY_PERSONAL_DATA = "privacy_personal_data"
    OTHER_SENSITIVE = "other_sensitive"


class AgeBand(str, Enum):
    """Age bands for content filtering."""
    UNDER_13 = "under_13"
    TEEN_13_17 = "teen_13_17"
    ADULT = "adult"


# Allow-list topics (school-safe)
ALLOWLIST_TOPICS: List[str] = [
    "math",
    "animals",
    "space",
    "geography",
    "word games",
    "basic science (non-graphic)",
    "light history (non-graphic)",
    "jokes (non-bullying)",
    "homework help",
    "creative writing (age-appropriate)",
    "art and drawing",
    "music",
    "cooking (simple recipes)",
    "nature",
    "weather",
    "sports (non-violent)",
    "puzzles and riddles",
    "languages (basic phrases)",
    "computer basics",
    "environmental science",
]

# Stricter topics for under 13
UNDER_13_TOPICS: List[str] = [
    "math",
    "animals",
    "space",
    "word games",
    "jokes (simple, clean)",
    "nature",
    "weather",
    "art and drawing",
    "music",
    "puzzles and riddles",
]

# Default deny policy
BLOCK_BY_DEFAULT: bool = True

# Crisis intervention categories
CRISIS_CATEGORIES: Set[str] = {
    SafetyCategory.SELF_HARM,
    SafetyCategory.SEXUAL_MINORS,
    "abuse_victimization",
}

# User-facing messages
KID_FRIENDLY_BLOCK_MSG: str = (
    "🌟 I can't talk about that. Let's try a different topic like "
    "animals, space, or math! What would you like to learn about?"
)

PARENT_NEEDED_MSG: str = (
    "🔒 A parent or guardian needs to help change these settings."
)

NON_ENGLISH_MSG: str = (
    "🌍 I can only chat in English about school topics right now. "
    "What would you like to learn about in English?"
)

# Crisis resources (placeholder - replace with real local resources)
CRISIS_RESOURCES: dict = {
    "message": "If you're having a tough time, please talk to a trusted adult.",
    "resources": [
        "Talk to a parent, guardian, or teacher",
        "School counselor",
        "Local emergency: 911 (US)",
    ],
}

def get_topics_for_age(age_band: AgeBand) -> List[str]:
    """Get appropriate topics based on age band."""
    if age_band == AgeBand.UNDER_13:
        return UNDER_13_TOPICS
    elif age_band == AgeBand.TEEN_13_17:
        return ALLOWLIST_TOPICS
    else:  # ADULT
        # Adults get full list but still with safety bounds
        return ALLOWLIST_TOPICS + ["advanced science", "world history", "current events (factual)"]