"""BrainBot activity selection logic."""

import logging
import random
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from ..state.models import BotState, BotStatus
from ..memory.store import MemoryStore
from ..config.settings import Settings

logger = logging.getLogger(__name__)


class ActivityType(str, Enum):
    """Types of activities BrainBot can do."""
    # Core activities
    CONTINUE_TASK = "continue_task"
    WORK_ON_GOAL = "work_on_goal"
    CONTINUE_PROJECT = "continue_project"
    START_NEW_PROJECT = "start_new_project"

    # Creative activities
    WRITE_BEDTIME_STORY = "write_bedtime_story"
    EXPLORE_IDEAS = "explore_ideas"

    # Learning activities
    LEARN_SOMETHING = "learn_something"
    REVIEW_PAST_PROJECTS = "review_past_projects"

    # Maintenance
    JOURNAL_REFLECTION = "journal_reflection"
    ORGANIZE_GOALS = "organize_goals"

    # Idle
    IDLE = "idle"


class Activity:
    """Represents an activity for BrainBot to do."""

    def __init__(
        self,
        activity_type: ActivityType,
        description: str,
        priority: int = 1,
        estimated_duration_minutes: int = 30,
        context: Optional[dict] = None,
    ):
        self.activity_type = activity_type
        self.description = description
        self.priority = priority
        self.estimated_duration_minutes = estimated_duration_minutes
        self.context = context or {}

    def __repr__(self) -> str:
        return f"Activity({self.activity_type.value}: {self.description})"


class ActivitySelector:
    """
    Selects what BrainBot should do next.

    Priority order:
    1. Complete current task if in progress
    2. Work on daily goals
    3. Continue current project
    4. Start new project from ideas backlog
    5. Generate new project ideas (explore web, find inspiration)
    6. Learn something new (docs, tutorials)
    7. Review and improve past projects
    """

    def __init__(
        self,
        settings: Settings,
        memory_store: MemoryStore,
    ):
        self.settings = settings
        self.memory = memory_store

        # Track how long we've been doing the same type of activity
        self._activity_history: list[tuple[datetime, ActivityType]] = []
        self._max_same_activity_duration = timedelta(hours=2)

    def select_next_activity(self, state: BotState) -> Activity:
        """
        Select the next activity based on current state and priorities.

        Args:
            state: Current bot state

        Returns:
            Activity to perform next
        """
        # 1. If there's a current activity, continue it (unless stuck)
        if state.current_activity:
            return Activity(
                ActivityType.CONTINUE_TASK,
                f"Continue: {state.current_activity}",
                priority=10,
            )

        # 2. Check for pending daily goals
        pending_goals = self.memory.get_pending_goals("daily")
        if pending_goals:
            goal = pending_goals[0]
            return Activity(
                ActivityType.WORK_ON_GOAL,
                f"Work on goal: {goal['description']}",
                priority=8,
                context={"goal_id": goal["id"], "goal": goal},
            )

        # 3. Continue current project
        if state.current_project:
            return Activity(
                ActivityType.CONTINUE_PROJECT,
                f"Continue project: {state.current_project.name}",
                priority=7,
                context={"project": state.current_project},
            )

        # 4. Start new project from backlog
        next_project = self.memory.get_next_project_idea()
        if next_project:
            return Activity(
                ActivityType.START_NEW_PROJECT,
                f"Start new project: {next_project['title']}",
                priority=6,
                context={"project_idea": next_project},
            )

        # 5. Explore and generate new ideas
        if self._should_explore_ideas(state):
            return Activity(
                ActivityType.EXPLORE_IDEAS,
                "Explore the web for new project ideas",
                priority=5,
                estimated_duration_minutes=20,
            )

        # 6. Learn something new
        if self._should_learn(state):
            topic = self._pick_learning_topic()
            return Activity(
                ActivityType.LEARN_SOMETHING,
                f"Learn about: {topic}",
                priority=4,
                estimated_duration_minutes=30,
                context={"topic": topic},
            )

        # 7. Review past projects
        past_projects = self.memory.get_project_ideas("completed", limit=5)
        if past_projects and random.random() < 0.3:
            project = random.choice(past_projects)
            return Activity(
                ActivityType.REVIEW_PAST_PROJECTS,
                f"Review and improve: {project['title']}",
                priority=3,
                context={"project": project},
            )

        # 8. Organize and plan
        if random.random() < 0.2:
            return Activity(
                ActivityType.ORGANIZE_GOALS,
                "Organize goals and plan upcoming work",
                priority=2,
                estimated_duration_minutes=15,
            )

        # Default: generate new ideas (BrainBot is never truly idle)
        return Activity(
            ActivityType.EXPLORE_IDEAS,
            "Think of new things to create",
            priority=1,
            estimated_duration_minutes=15,
        )

    def _should_explore_ideas(self, state: BotState) -> bool:
        """Check if we should explore for new ideas."""
        # Explore if energy is high and mood is curious
        if state.energy > 0.7 and state.mood.value == "curious":
            return True

        # Explore if we have no projects in backlog
        ideas = self.memory.get_project_ideas("idea", limit=1)
        return len(ideas) == 0

    def _should_learn(self, state: BotState) -> bool:
        """Check if we should spend time learning."""
        # Learn if we haven't learned anything recently
        recent_learnings = self.memory.get_learnings(limit=1)
        if not recent_learnings:
            return True

        # Check when last learning was
        last_learning = recent_learnings[0]
        if "created_at" in last_learning:
            last_time = datetime.fromisoformat(last_learning["created_at"])
            hours_since = (datetime.now() - last_time).total_seconds() / 3600
            return hours_since > 4

        return random.random() < 0.25

    def _pick_learning_topic(self) -> str:
        """Pick a topic to learn about."""
        topics = [
            "Python best practices",
            "Hardware and embedded projects",
            "AI/ML concepts",
            "Web development",
            "Game development",
            "Creative coding",
            "System design patterns",
            "Open source projects",
            "Electronics for beginners",
            "Data visualization",
        ]
        return random.choice(topics)

    def _is_stuck_on_activity(self, activity_type: ActivityType) -> bool:
        """Check if we've been stuck on the same activity too long."""
        now = datetime.now()
        same_type_entries = [
            (t, a)
            for t, a in self._activity_history
            if a == activity_type and (now - t) < self._max_same_activity_duration
        ]
        return len(same_type_entries) > 10  # More than 10 ticks on same activity

    def record_activity(self, activity_type: ActivityType) -> None:
        """Record that an activity was performed."""
        now = datetime.now()
        self._activity_history.append((now, activity_type))

        # Keep only recent history
        cutoff = now - timedelta(hours=24)
        self._activity_history = [
            (t, a) for t, a in self._activity_history if t > cutoff
        ]

    def get_activity_summary(self) -> dict:
        """Get a summary of recent activities."""
        now = datetime.now()
        last_hour = now - timedelta(hours=1)

        recent = [a for t, a in self._activity_history if t > last_hour]

        summary = {}
        for activity in recent:
            summary[activity.value] = summary.get(activity.value, 0) + 1

        return {
            "last_hour": summary,
            "total_recorded": len(self._activity_history),
        }
