"""BrainBot state manager with JSON persistence."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from threading import Lock

from .models import BotState, BotStatus, Mood, CurrentProject, DailyGoal
from ..config.settings import Settings

logger = logging.getLogger(__name__)


class StateManager:
    """
    Manages BrainBot's state with thread-safe operations and persistence.

    State is persisted to JSON file and loaded on startup.
    """

    def __init__(self, settings: Settings):
        """
        Initialize state manager.

        Args:
            settings: BrainBot settings
        """
        self.settings = settings
        self.state_file = settings.state_file
        self._state: BotState = BotState()
        self._lock = Lock()
        self._dirty = False

    def load(self) -> BotState:
        """
        Load state from file, or create new state if file doesn't exist.

        Returns:
            Current bot state
        """
        with self._lock:
            if self.state_file.exists():
                try:
                    data = json.loads(self.state_file.read_text())
                    self._state = self._deserialize_state(data)
                    logger.info(f"Loaded state from {self.state_file}")
                except Exception as e:
                    logger.error(f"Failed to load state: {e}")
                    self._state = BotState()
            else:
                logger.info("No existing state file, starting fresh")
                self._state = BotState()

            return self._state

    def save(self, force: bool = False) -> None:
        """
        Save current state to file.

        Args:
            force: If True, save even if not marked dirty
        """
        with self._lock:
            if not force and not self._dirty:
                return

            try:
                self.state_file.parent.mkdir(parents=True, exist_ok=True)
                data = self._serialize_state(self._state)
                self.state_file.write_text(json.dumps(data, indent=2, default=str))
                self._state.last_state_save = datetime.now()
                self._dirty = False
                logger.debug(f"Saved state to {self.state_file}")
            except Exception as e:
                logger.error(f"Failed to save state: {e}")

    def get_state(self) -> BotState:
        """Get current state (thread-safe copy)."""
        with self._lock:
            return self._state.model_copy(deep=True)

    def update_status(self, status: BotStatus) -> None:
        """Update bot status."""
        with self._lock:
            old_status = self._state.status
            self._state.status = status
            self._dirty = True
            logger.info(f"Status changed: {old_status.value} -> {status.value}")

    def update_mood(self, mood: Mood) -> None:
        """Update bot mood."""
        with self._lock:
            self._state.mood = mood
            self._dirty = True

    def update_energy(self, energy: float) -> None:
        """Update energy level."""
        with self._lock:
            self._state.energy = max(0.0, min(1.0, energy))
            self._dirty = True

    def deplete_energy(self, amount: float = 0.01) -> None:
        """Deplete energy by a small amount."""
        with self._lock:
            self._state.deplete_energy(amount)
            self._dirty = True

    def start_activity(self, activity: str) -> None:
        """Start a new activity."""
        with self._lock:
            self._state.start_activity(activity)
            self._dirty = True
            logger.info(f"Started activity: {activity}")

    def end_activity(self) -> None:
        """End current activity."""
        with self._lock:
            activity = self._state.current_activity
            self._state.end_activity()
            self._dirty = True
            if activity:
                logger.info(f"Ended activity: {activity}")

    def set_current_project(self, project: CurrentProject) -> None:
        """Set the current project."""
        with self._lock:
            self._state.current_project = project
            self._dirty = True
            logger.info(f"Set current project: {project.name}")

    def clear_current_project(self) -> None:
        """Clear the current project."""
        with self._lock:
            if self._state.current_project:
                logger.info(f"Cleared current project: {self._state.current_project.name}")
            self._state.current_project = None
            self._dirty = True

    def update_project_progress(self, progress: float) -> None:
        """Update current project progress."""
        with self._lock:
            if self._state.current_project:
                self._state.current_project.progress = max(0.0, min(1.0, progress))
                self._state.current_project.last_activity = datetime.now()
                self._dirty = True

    def add_daily_goal(self, description: str, priority: int = 1) -> DailyGoal:
        """Add a new daily goal."""
        with self._lock:
            goal = DailyGoal(
                id=f"goal_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self._state.daily_goals)}",
                description=description,
                priority=priority,
                created_at=datetime.now(),
            )
            self._state.add_daily_goal(goal)
            self._dirty = True
            logger.info(f"Added daily goal: {description}")
            return goal

    def complete_goal(self, goal_id: str) -> bool:
        """Mark a goal as complete."""
        with self._lock:
            result = self._state.complete_goal(goal_id)
            if result:
                self._dirty = True
                logger.info(f"Completed goal: {goal_id}")
            return result

    def get_pending_goals(self) -> list[DailyGoal]:
        """Get all pending goals."""
        with self._lock:
            return self._state.get_pending_goals()

    def wake_up(self) -> None:
        """Transition to waking state."""
        with self._lock:
            self._state.status = BotStatus.WAKING
            self._state.woke_at = datetime.now()
            self._state.restore_energy(1.0)
            self._state.mood = Mood.CONTENT
            self._dirty = True
            logger.info("BrainBot is waking up!")

    def become_active(self) -> None:
        """Transition to active state."""
        with self._lock:
            self._state.status = BotStatus.ACTIVE
            self._state.session_start = datetime.now()
            self._dirty = True
            logger.info("BrainBot is now active")

    def start_creating(self) -> None:
        """Transition to creating state."""
        with self._lock:
            self._state.status = BotStatus.CREATING
            self._dirty = True

    def start_reflecting(self) -> None:
        """Transition to reflecting state."""
        with self._lock:
            self._state.status = BotStatus.REFLECTING
            self._state.mood = Mood.CONTENT
            self._dirty = True
            logger.info("BrainBot is reflecting")

    def prepare_for_sleep(self) -> None:
        """Transition to going to sleep state."""
        with self._lock:
            self._state.status = BotStatus.GOING_TO_SLEEP
            self._dirty = True
            logger.info("BrainBot is preparing for sleep")

    def go_to_sleep(self) -> None:
        """Transition to sleeping state and reset for new day."""
        with self._lock:
            self._state.status = BotStatus.SLEEPING
            self._state.current_activity = None
            self._state.session_start = None
            self._dirty = True
            logger.info("BrainBot is now sleeping")

    def increment_stories_written(self) -> None:
        """Increment stories written counter."""
        with self._lock:
            self._state.stories_written_today += 1
            self._dirty = True

    def increment_projects_completed(self) -> None:
        """Increment projects completed counter."""
        with self._lock:
            self._state.projects_completed_today += 1
            self._dirty = True

    def reset_for_new_day(self) -> None:
        """Reset state for a new day (called after waking)."""
        with self._lock:
            self._state.reset_for_new_day()
            self._dirty = True
            logger.info("Reset state for new day")

    def _serialize_state(self, state: BotState) -> dict:
        """Serialize state to dict for JSON storage."""
        data = state.model_dump()
        # Convert enums to strings
        data["status"] = state.status.value
        data["mood"] = state.mood.value
        return data

    def _deserialize_state(self, data: dict) -> BotState:
        """Deserialize state from dict."""
        # Convert string status/mood back to enums
        if "status" in data:
            data["status"] = BotStatus(data["status"])
        if "mood" in data:
            data["mood"] = Mood(data["mood"])

        # Handle nested models
        if "current_project" in data and data["current_project"]:
            data["current_project"] = CurrentProject(**data["current_project"])

        if "daily_goals" in data:
            data["daily_goals"] = [DailyGoal(**g) for g in data["daily_goals"]]

        return BotState(**data)
