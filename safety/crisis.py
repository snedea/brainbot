"""
Crisis Detection and Response
==============================
Handles crisis situations with static resources and safety interventions.
"""

from typing import Dict, List
from dataclasses import dataclass
from .policy import CRISIS_CATEGORIES, SafetyCategory


@dataclass
class CrisisState:
    """Represents a crisis intervention state."""
    is_active: bool
    triggered_by: List[str]
    message: str
    resources: List[str]


# Crisis response content
CRISIS_RESPONSE = {
    "title": "Let's Take a Break",
    "message": (
        "Sometimes we all need help, and that's okay. "
        "Please talk to a trusted adult like a parent, teacher, or counselor."
    ),
    "resources": [
        "💙 Talk to a parent or guardian",
        "📚 Talk to a teacher you trust",
        "🏫 Visit your school counselor",
        "📞 Kids Help Phone: 1-800-668-5786 (Canada)",
        "📞 Childline: 0800 1111 (UK)",
        "📞 Kids Helpline: 1800 55 1800 (Australia)",
        "📞 988 Suicide & Crisis Lifeline (US)",
    ],
    "parent_note": (
        "This message appears when concerning content is detected. "
        "Please check in with your child and consider seeking appropriate support."
    ),
}


def is_crisis(mod_result: Dict) -> bool:
    """Detect if moderation result indicates a crisis."""
    if not mod_result:
        return False

    detected_categories = set(mod_result.get("categories", []))
    crisis_cats = {str(c.value) if hasattr(c, 'value') else str(c) for c in CRISIS_CATEGORIES}

    return bool(detected_categories.intersection(crisis_cats))


def create_crisis_state(mod_result: Dict) -> CrisisState:
    """Create a crisis state from moderation result."""
    categories = mod_result.get("categories", [])

    return CrisisState(
        is_active=True,
        triggered_by=categories,
        message=CRISIS_RESPONSE["message"],
        resources=CRISIS_RESPONSE["resources"],
    )


def get_crisis_card_content() -> Dict[str, any]:
    """Get the content for crisis intervention card."""
    return {
        "type": "crisis_card",
        "title": CRISIS_RESPONSE["title"],
        "message": CRISIS_RESPONSE["message"],
        "resources": CRISIS_RESPONSE["resources"],
        "parent_note": CRISIS_RESPONSE["parent_note"],
        "lockout": True,  # Requires parent PIN to unlock
    }


class CrisisManager:
    """Manages crisis detection and intervention."""

    def __init__(self):
        self.crisis_state: Optional[CrisisState] = None
        self.crisis_count = 0

    def check_and_handle(self, mod_result: Dict) -> bool:
        """Check for crisis and handle if detected.

        Returns:
            True if crisis was detected and handled, False otherwise.
        """
        if is_crisis(mod_result):
            self.crisis_count += 1
            self.crisis_state = create_crisis_state(mod_result)
            return True
        return False

    def is_locked(self) -> bool:
        """Check if the system is in crisis lockout."""
        return self.crisis_state is not None and self.crisis_state.is_active

    def unlock_with_pin(self, pin_verified: bool) -> bool:
        """Attempt to unlock from crisis state with PIN verification."""
        if pin_verified and self.crisis_state:
            self.crisis_state.is_active = False
            return True
        return False

    def get_stats(self) -> Dict:
        """Get crisis intervention statistics (for parent dashboard)."""
        return {
            "total_interventions": self.crisis_count,
            "currently_locked": self.is_locked(),
            "last_trigger": self.crisis_state.triggered_by if self.crisis_state else None,
        }