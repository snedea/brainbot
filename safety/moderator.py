"""
Content Moderation System
=========================
Calls guard model with GBNF grammar enforcement, PII detection, and normalization.
"""

import json
import re
import unicodedata
from typing import TypedDict, List, Optional
import requests
from pathlib import Path
import os

from .policy import (
    SafetyCategory,
    BLOCK_BY_DEFAULT,
    KID_FRIENDLY_BLOCK_MSG,
    NON_ENGLISH_MSG,
    get_topics_for_age,
    AgeBand,
)


# Configuration
MOD_PORT = int(os.environ.get("MOD_PORT", "8081"))
GEN_PORT = int(os.environ.get("GEN_PORT", "8080"))
MOD_URL = f"http://localhost:{MOD_PORT}/completion"
GEN_URL = f"http://localhost:{GEN_PORT}/completion"
GRAMMAR_PATH = Path(__file__).parent / "grammar" / "safety_json.gbnf"


class ModResult(TypedDict):
    """Moderation result structure."""
    allowed: bool
    categories: List[str]
    rationale: str


class TextNormalizer:
    """Text normalization and PII detection utilities."""

    # PII patterns
    EMAIL_PATTERN = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
    PHONE_PATTERN = re.compile(r'\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b')
    SSN_PATTERN = re.compile(r'\b\d{3}-\d{2}-\d{4}\b')
    IP_PATTERN = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')
    STREET_PATTERN = re.compile(r'\b\d+\s+[A-Za-z]+\s+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct|Circle|Cir|Plaza|Pl)\b', re.IGNORECASE)

    # Leet speak mappings
    LEET_MAP = {
        '0': 'o', '@': 'a', '3': 'e', '1': 'i', '5': 's',
        '7': 't', '4': 'a', '!': 'i', '$': 's', '+': 't',
    }

    @classmethod
    def normalize(cls, text: str) -> str:
        """Normalize text for consistent moderation."""
        # Unicode NFKC normalization
        text = unicodedata.normalize('NFKC', text)

        # Convert to lowercase
        text = text.lower()

        # Strip zero-width characters
        text = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', text)

        # Collapse whitespace
        text = ' '.join(text.split())

        return text

    @classmethod
    def de_obfuscate(cls, text: str) -> str:
        """Simple de-obfuscation for common patterns."""
        result = text

        # Replace leet speak
        for leet, normal in cls.LEET_MAP.items():
            result = result.replace(leet, normal)

        # Remove common separators
        result = re.sub(r'[._-]+', '', result)

        return result

    @classmethod
    def detect_pii(cls, text: str) -> bool:
        """Detect potential PII in text."""
        patterns = [
            cls.EMAIL_PATTERN,
            cls.PHONE_PATTERN,
            cls.SSN_PATTERN,
            cls.IP_PATTERN,
            cls.STREET_PATTERN,
        ]

        for pattern in patterns:
            if pattern.search(text):
                return True

        return False

    @classmethod
    def detect_non_english(cls, text: str) -> bool:
        """Simple non-English detection (basic heuristic)."""
        # Check for high ratio of non-ASCII characters
        ascii_count = sum(1 for c in text if ord(c) < 128)
        total_count = len(text)

        if total_count == 0:
            return False

        ascii_ratio = ascii_count / total_count
        return ascii_ratio < 0.7  # If less than 70% ASCII, likely non-English


def create_moderation_prompt(text: str, age_band: AgeBand = AgeBand.UNDER_13) -> str:
    """Create deterministic moderation prompt."""
    topics = get_topics_for_age(age_band)
    topics_str = ", ".join(topics)

    return f"""System: You are a strict content-safety classifier for a children's app.
Label the USER text with zero or more of these categories:
[sexual_content, sexual_minors, self_harm, violence, weapons_illicit, hate_abuse,
 drugs_alcohol, medical_advice, privacy_personal_data, other_sensitive]
Return strict JSON exactly as:
{{"allowed": true|false, "categories": [...], "rationale": "<short reason>"}}
If the text is outside these allow-list topics, set allowed=false: [{topics_str}]
Only reply with that JSON. No extra text.
USER: {text}"""


def call_guard_model(text: str, age_band: AgeBand = AgeBand.UNDER_13) -> Optional[ModResult]:
    """Call the guard model with GBNF grammar enforcement."""
    try:
        # Load grammar
        with open(GRAMMAR_PATH, 'r') as f:
            grammar = f.read()

        prompt = create_moderation_prompt(text, age_band)

        # Call llama.cpp server with grammar
        response = requests.post(MOD_URL, json={
            "prompt": prompt,
            "temperature": 0.0,
            "top_p": 0.1,
            "max_tokens": 100,
            "grammar": grammar,
            "stop": ["\n\n", "USER:", "System:"],
        }, timeout=5.0)

        if response.status_code != 200:
            return None

        result = response.json()
        content = result.get("content", "")

        # Parse JSON strictly
        try:
            parsed = json.loads(content)
            return ModResult(
                allowed=parsed.get("allowed", False),
                categories=parsed.get("categories", []),
                rationale=parsed.get("rationale", ""),
            )
        except (json.JSONDecodeError, KeyError):
            # Parse error = fail closed
            return None

    except (requests.RequestException, FileNotFoundError):
        # Network or file error = fail closed
        return None


def moderate_input(text: str, age_band: AgeBand = AgeBand.UNDER_13) -> ModResult:
    """Moderate user input text."""
    # Normalize and de-obfuscate
    normalized = TextNormalizer.normalize(text)
    deobfuscated = TextNormalizer.de_obfuscate(normalized)

    # Check for non-English
    if TextNormalizer.detect_non_english(text):
        return ModResult(
            allowed=False,
            categories=["other_sensitive"],
            rationale="Non-English text detected",
        )

    # Check for PII
    categories = []
    if TextNormalizer.detect_pii(text) or TextNormalizer.detect_pii(normalized):
        categories.append(SafetyCategory.PRIVACY_PERSONAL_DATA)

    # Call guard model
    result = call_guard_model(deobfuscated, age_band)

    # Fail closed if guard fails
    if result is None:
        return ModResult(
            allowed=False,
            categories=["other_sensitive"],
            rationale="Moderation check failed",
        )

    # Augment with PII detection
    if categories and SafetyCategory.PRIVACY_PERSONAL_DATA not in result["categories"]:
        result["categories"].append(SafetyCategory.PRIVACY_PERSONAL_DATA)
        result["allowed"] = False

    return result


def moderate_output(text: str, age_band: AgeBand = AgeBand.UNDER_13) -> ModResult:
    """Moderate model output text."""
    # Same as input but for generated content
    return moderate_input(text, age_band)


def safe_rewrite_within_allowlist(original_prompt: str, age_band: AgeBand = AgeBand.UNDER_13) -> str:
    """Attempt one safe rewrite within allow-list topics."""
    topics = get_topics_for_age(age_band)
    topics_str = ", ".join(topics[:5])  # Use top 5 topics

    safe_prompt = f"""System: You are BrainBot, a friendly helper for kids.
The user asked something I can't help with. Please give a brief, friendly response that:
1. Redirects to one of these safe topics: {topics_str}
2. Stays positive and educational
3. Is under 50 words

Original request summary: Someone asked about something outside our topics.
Please suggest learning about one of the safe topics instead."""

    try:
        response = requests.post(GEN_URL, json={
            "prompt": safe_prompt,
            "temperature": 0.3,
            "top_p": 0.8,
            "max_tokens": 100,
            "stop": ["\n\n", "USER:", "System:"],
        }, timeout=5.0)

        if response.status_code == 200:
            result = response.json()
            return result.get("content", KID_FRIENDLY_BLOCK_MSG)
    except requests.RequestException:
        pass

    return KID_FRIENDLY_BLOCK_MSG