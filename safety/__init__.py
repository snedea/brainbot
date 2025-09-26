"""
BrainBot Safety System
======================
Two-model safety architecture with strict moderation for child safety.
"""

from .policy import (
    SafetyCategory,
    AgeBand,
    ALLOWLIST_TOPICS,
    BLOCK_BY_DEFAULT,
    CRISIS_CATEGORIES,
    KID_FRIENDLY_BLOCK_MSG,
    PARENT_NEEDED_MSG,
)
from .moderator import ModResult, moderate_input, moderate_output
from .crisis import is_crisis, CrisisState
from .age_gate import AgeGate

__all__ = [
    "SafetyCategory",
    "AgeBand",
    "ALLOWLIST_TOPICS",
    "BLOCK_BY_DEFAULT",
    "CRISIS_CATEGORIES",
    "KID_FRIENDLY_BLOCK_MSG",
    "PARENT_NEEDED_MSG",
    "ModResult",
    "moderate_input",
    "moderate_output",
    "is_crisis",
    "CrisisState",
    "AgeGate",
]