"""BrainBot state models using Pydantic."""

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class BotStatus(str, Enum):
    """BrainBot's current status."""
    SLEEPING = "sleeping"
    WAKING = "waking"
    ACTIVE = "active"
    CREATING = "creating"
    REFLECTING = "reflecting"
    GOING_TO_SLEEP = "going_to_sleep"


class Mood(str, Enum):
    """BrainBot's current mood."""
    CONTENT = "content"
    EXCITED = "excited"
    FOCUSED = "focused"
    TIRED = "tired"
    BORED = "bored"
    CURIOUS = "curious"
    ACCOMPLISHED = "accomplished"


class CurrentProject(BaseModel):
    """Information about the current project BrainBot is working on."""
    id: str
    name: str
    description: str
    started_at: datetime
    last_activity: datetime
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    status: str = "in_progress"  # in_progress, paused, completed, abandoned


class DailyGoal(BaseModel):
    """A daily goal for BrainBot."""
    id: str
    description: str
    priority: int = Field(default=1, ge=1, le=5)
    completed: bool = False
    created_at: datetime
    completed_at: Optional[datetime] = None


class BotState(BaseModel):
    """Complete state of BrainBot at any moment."""

    # Status
    status: BotStatus = Field(default=BotStatus.SLEEPING)

    # Energy and mood
    energy: float = Field(default=1.0, ge=0.0, le=1.0)
    mood: Mood = Field(default=Mood.CONTENT)

    # Current activity
    current_activity: Optional[str] = None
    current_project: Optional[CurrentProject] = None

    # Daily goals
    daily_goals: list[DailyGoal] = Field(default_factory=list)

    # Session tracking
    session_start: Optional[datetime] = None
    last_activity: Optional[datetime] = None

    # Statistics
    projects_completed_today: int = 0
    stories_written_today: int = 0

    # Timestamps
    woke_at: Optional[datetime] = None
    last_state_save: Optional[datetime] = None

    def is_sleeping(self) -> bool:
        """Check if BrainBot is sleeping."""
        return self.status == BotStatus.SLEEPING

    def is_active(self) -> bool:
        """Check if BrainBot is in an active state."""
        return self.status in (BotStatus.ACTIVE, BotStatus.CREATING)

    def deplete_energy(self, amount: float = 0.01) -> None:
        """Deplete energy by a small amount."""
        self.energy = max(0.0, self.energy - amount)
        # Update mood based on energy
        if self.energy < 0.2:
            self.mood = Mood.TIRED
        elif self.energy < 0.4:
            self.mood = Mood.CONTENT

    def restore_energy(self, amount: float = 1.0) -> None:
        """Restore energy (typically during sleep or after rest)."""
        self.energy = min(1.0, self.energy + amount)

    def update_mood(self, mood: Mood) -> None:
        """Update the current mood."""
        self.mood = mood

    def start_activity(self, activity: str) -> None:
        """Start a new activity."""
        self.current_activity = activity
        self.last_activity = datetime.now()
        self.session_start = self.session_start or datetime.now()

    def end_activity(self) -> None:
        """End the current activity."""
        self.current_activity = None
        self.last_activity = datetime.now()

    def add_daily_goal(self, goal: DailyGoal) -> None:
        """Add a daily goal."""
        self.daily_goals.append(goal)

    def complete_goal(self, goal_id: str) -> bool:
        """Mark a goal as complete."""
        for goal in self.daily_goals:
            if goal.id == goal_id:
                goal.completed = True
                goal.completed_at = datetime.now()
                return True
        return False

    def get_pending_goals(self) -> list[DailyGoal]:
        """Get all incomplete goals."""
        return [g for g in self.daily_goals if not g.completed]

    def reset_for_new_day(self) -> None:
        """Reset state for a new day."""
        self.daily_goals = []
        self.projects_completed_today = 0
        self.stories_written_today = 0
        self.energy = 1.0
        self.mood = Mood.CONTENT
        self.current_activity = None
        self.session_start = None
