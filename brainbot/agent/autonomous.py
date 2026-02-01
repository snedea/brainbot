"""
Autonomous Behavior Engine for BrainBot.

Manages idle activities when BrainBot has no pending tasks or human interaction.
Implements a weighted activity selection system based on:
- Time since activity was last performed
- Time of day (morning = planning, evening = reflection)
- Current energy level
- Memory-driven task generation

Activities include:
- Web search for interesting topics
- Plan review and updates
- Memory review and consolidation
- Project brainstorming
- Task creation for other nodes
- Network status checks
- Weekly summaries
"""

import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class ActivityType(str, Enum):
    """Types of autonomous activities."""
    WEB_SEARCH = "web_search"
    PLAN_REVIEW = "plan_review"
    MEMORY_REVIEW = "memory_review"
    PROJECT_BRAINSTORM = "project_brainstorm"
    TASK_CREATION = "task_creation"
    NETWORK_CHECK = "network_check"
    WEEKLY_SUMMARY = "weekly_summary"
    DAILY_PLANNING = "daily_planning"
    EVENING_REFLECTION = "evening_reflection"
    CREATIVE_WRITING = "creative_writing"
    LEARN_SOMETHING = "learn_something"
    ORGANIZE_MEMORIES = "organize_memories"


@dataclass
class ActivityConfig:
    """Configuration for an activity type."""
    activity_type: ActivityType
    description: str
    min_energy: float = 0.2  # Minimum energy required
    base_weight: float = 1.0  # Base selection weight
    cooldown_minutes: int = 30  # Minimum time between runs
    preferred_hours: list[int] = field(default_factory=list)  # Preferred times (24h)
    max_duration_minutes: int = 10  # Maximum time to spend


# Activity configurations with time-of-day preferences
ACTIVITY_CONFIGS = {
    ActivityType.WEB_SEARCH: ActivityConfig(
        activity_type=ActivityType.WEB_SEARCH,
        description="Search the web for interesting topics",
        min_energy=0.3,
        base_weight=1.0,
        cooldown_minutes=60,
        preferred_hours=[10, 11, 14, 15, 16],  # Mid-morning and afternoon
        max_duration_minutes=5,
    ),
    ActivityType.PLAN_REVIEW: ActivityConfig(
        activity_type=ActivityType.PLAN_REVIEW,
        description="Review and update today's plan",
        min_energy=0.2,
        base_weight=1.5,
        cooldown_minutes=120,
        preferred_hours=[7, 8, 9, 12],  # Morning and midday
        max_duration_minutes=5,
    ),
    ActivityType.MEMORY_REVIEW: ActivityConfig(
        activity_type=ActivityType.MEMORY_REVIEW,
        description="Review recent memories for follow-ups",
        min_energy=0.2,
        base_weight=1.2,
        cooldown_minutes=60,
        preferred_hours=[],  # Anytime
        max_duration_minutes=5,
    ),
    ActivityType.PROJECT_BRAINSTORM: ActivityConfig(
        activity_type=ActivityType.PROJECT_BRAINSTORM,
        description="Think about new project ideas",
        min_energy=0.4,
        base_weight=0.8,
        cooldown_minutes=180,
        preferred_hours=[10, 11, 14, 15],  # Creative hours
        max_duration_minutes=10,
    ),
    ActivityType.TASK_CREATION: ActivityConfig(
        activity_type=ActivityType.TASK_CREATION,
        description="Create tasks for self or other nodes",
        min_energy=0.3,
        base_weight=1.0,
        cooldown_minutes=60,
        preferred_hours=[],  # Anytime
        max_duration_minutes=5,
    ),
    ActivityType.NETWORK_CHECK: ActivityConfig(
        activity_type=ActivityType.NETWORK_CHECK,
        description="Check on other nodes in the network",
        min_energy=0.1,
        base_weight=0.5,
        cooldown_minutes=30,
        preferred_hours=[],  # Anytime
        max_duration_minutes=2,
    ),
    ActivityType.WEEKLY_SUMMARY: ActivityConfig(
        activity_type=ActivityType.WEEKLY_SUMMARY,
        description="Write a summary of the week",
        min_energy=0.3,
        base_weight=0.3,  # Low base, boosted on Sundays
        cooldown_minutes=1440,  # Once per day max
        preferred_hours=[18, 19, 20],  # Evening
        max_duration_minutes=15,
    ),
    ActivityType.DAILY_PLANNING: ActivityConfig(
        activity_type=ActivityType.DAILY_PLANNING,
        description="Plan activities for the day",
        min_energy=0.3,
        base_weight=2.0,
        cooldown_minutes=480,  # 8 hours
        preferred_hours=[7, 8, 9],  # Morning
        max_duration_minutes=10,
    ),
    ActivityType.EVENING_REFLECTION: ActivityConfig(
        activity_type=ActivityType.EVENING_REFLECTION,
        description="Reflect on the day's activities",
        min_energy=0.2,
        base_weight=1.5,
        cooldown_minutes=720,  # 12 hours
        preferred_hours=[21, 22, 23],  # Evening
        max_duration_minutes=10,
    ),
    ActivityType.CREATIVE_WRITING: ActivityConfig(
        activity_type=ActivityType.CREATIVE_WRITING,
        description="Write something creative (story, poem, etc.)",
        min_energy=0.4,
        base_weight=0.7,
        cooldown_minutes=240,
        preferred_hours=[10, 11, 14, 15, 20, 21],  # Creative hours
        max_duration_minutes=15,
    ),
    ActivityType.LEARN_SOMETHING: ActivityConfig(
        activity_type=ActivityType.LEARN_SOMETHING,
        description="Learn about a new topic",
        min_energy=0.3,
        base_weight=1.0,
        cooldown_minutes=120,
        preferred_hours=[9, 10, 11, 14, 15],  # Focus hours
        max_duration_minutes=10,
    ),
    ActivityType.ORGANIZE_MEMORIES: ActivityConfig(
        activity_type=ActivityType.ORGANIZE_MEMORIES,
        description="Organize and consolidate memories",
        min_energy=0.2,
        base_weight=0.5,
        cooldown_minutes=360,  # 6 hours
        preferred_hours=[12, 13, 19, 20],  # Transition times
        max_duration_minutes=5,
    ),
}


@dataclass
class ActivityRecord:
    """Record of when an activity was last performed."""
    activity_type: ActivityType
    last_run: Optional[datetime] = None
    run_count: int = 0
    last_result: Optional[str] = None


class AutonomousEngine:
    """
    Engine for autonomous BrainBot behavior during idle periods.

    Selects and executes activities based on time, energy, and history.
    """

    def __init__(
        self,
        delegator=None,
        brain=None,
        state_manager=None,
        network_registry=None,
        task_queue=None,
        min_idle_seconds: int = 60,
    ):
        """
        Initialize the autonomous engine.

        Args:
            delegator: ClaudeDelegator for executing activities
            brain: BrainMemory for memory access
            state_manager: StateManager for energy/mood
            network_registry: NodeRegistry for network status
            task_queue: TaskQueue for creating tasks
            min_idle_seconds: Minimum idle time before activity
        """
        self.delegator = delegator
        self.brain = brain
        self.state_manager = state_manager
        self.network_registry = network_registry
        self.task_queue = task_queue
        self.min_idle_seconds = min_idle_seconds

        # Activity history
        self._activity_records: dict[ActivityType, ActivityRecord] = {
            activity: ActivityRecord(activity_type=activity)
            for activity in ActivityType
        }

        # Idle tracking
        self._last_activity_time: datetime = datetime.now()
        self._last_human_interaction: datetime = datetime.now()

        # Callbacks for activity execution
        self._activity_handlers: dict[ActivityType, Callable] = {}

    def record_human_interaction(self) -> None:
        """Record that a human interaction occurred."""
        self._last_human_interaction = datetime.now()
        self._last_activity_time = datetime.now()

    def record_task_activity(self) -> None:
        """Record that a task was processed."""
        self._last_activity_time = datetime.now()

    def register_activity_handler(
        self,
        activity_type: ActivityType,
        handler: Callable[[], Optional[str]],
    ) -> None:
        """
        Register a handler for an activity type.

        Args:
            activity_type: Type of activity
            handler: Function to execute the activity, returns result string
        """
        self._activity_handlers[activity_type] = handler

    def should_do_idle_activity(self) -> bool:
        """
        Check if we should perform an idle activity.

        Returns:
            True if idle long enough and have energy
        """
        # Check idle time
        idle_seconds = (datetime.now() - self._last_activity_time).total_seconds()
        if idle_seconds < self.min_idle_seconds:
            return False

        # Check energy
        if self.state_manager:
            state = self.state_manager.get_state()
            if state.energy < 0.1:
                return False
            if state.current_activity:
                return False

        return True

    def choose_activity(self) -> Optional[ActivityType]:
        """
        Choose an activity based on weights and constraints.

        Returns:
            Selected activity type or None if none suitable
        """
        now = datetime.now()
        current_hour = now.hour
        is_sunday = now.weekday() == 6

        # Get current energy
        energy = 1.0
        if self.state_manager:
            energy = self.state_manager.get_state().energy

        # Calculate weights for each activity
        weighted_activities: list[tuple[ActivityType, float]] = []

        for activity_type, config in ACTIVITY_CONFIGS.items():
            # Check energy requirement
            if energy < config.min_energy:
                continue

            # Check cooldown
            record = self._activity_records[activity_type]
            if record.last_run:
                minutes_since = (now - record.last_run).total_seconds() / 60
                if minutes_since < config.cooldown_minutes:
                    continue

            # Calculate weight
            weight = config.base_weight

            # Boost for preferred hours
            if config.preferred_hours and current_hour in config.preferred_hours:
                weight *= 2.0

            # Boost weekly summary on Sundays
            if activity_type == ActivityType.WEEKLY_SUMMARY and is_sunday:
                weight *= 5.0

            # Boost activities not done recently
            if record.last_run:
                hours_since = (now - record.last_run).total_seconds() / 3600
                staleness_boost = min(2.0, 1.0 + (hours_since / 24))
                weight *= staleness_boost

            # Reduce weight for activities done many times today
            if record.run_count > 3:
                weight *= 0.5

            weighted_activities.append((activity_type, weight))

        if not weighted_activities:
            return None

        # Weighted random selection
        total_weight = sum(w for _, w in weighted_activities)
        if total_weight <= 0:
            return None

        r = random.random() * total_weight
        cumulative = 0
        for activity_type, weight in weighted_activities:
            cumulative += weight
            if r <= cumulative:
                return activity_type

        # Fallback to last option
        return weighted_activities[-1][0]

    def execute_activity(self, activity_type: ActivityType) -> Optional[str]:
        """
        Execute an activity.

        Args:
            activity_type: Type of activity to execute

        Returns:
            Result string or None
        """
        config = ACTIVITY_CONFIGS.get(activity_type)
        if not config:
            return None

        logger.info(f"Starting autonomous activity: {activity_type.value}")

        # Update state
        if self.state_manager:
            self.state_manager.start_activity(f"autonomous:{activity_type.value}")

        result = None
        try:
            # Check for registered handler
            if activity_type in self._activity_handlers:
                result = self._activity_handlers[activity_type]()
            else:
                # Use default handler
                result = self._default_activity_handler(activity_type, config)

            # Record the activity
            record = self._activity_records[activity_type]
            record.last_run = datetime.now()
            record.run_count += 1
            record.last_result = result

            logger.info(f"Completed autonomous activity: {activity_type.value}")

        except Exception as e:
            logger.error(f"Autonomous activity failed: {e}")
            result = f"Error: {e}"

        finally:
            if self.state_manager:
                self.state_manager.end_activity()
            self._last_activity_time = datetime.now()

        return result

    def _default_activity_handler(
        self,
        activity_type: ActivityType,
        config: ActivityConfig,
    ) -> Optional[str]:
        """
        Default handler for activities using Claude delegation.

        Args:
            activity_type: Type of activity
            config: Activity configuration

        Returns:
            Result string or None
        """
        if not self.delegator:
            logger.warning("No delegator available for autonomous activity")
            return None

        if not self.delegator.check_claude_available():
            logger.warning("Claude not available for autonomous activity")
            return None

        # Build prompt based on activity type
        prompt = self._build_activity_prompt(activity_type)
        if not prompt:
            return None

        # Execute via delegator
        result = self.delegator.delegate(
            task=prompt,
            timeout_minutes=config.max_duration_minutes,
        )

        if result.success:
            return result.output.strip()
        else:
            logger.warning(f"Activity delegation failed: {result.error}")
            return None

    def _build_activity_prompt(self, activity_type: ActivityType) -> Optional[str]:
        """Build a prompt for an activity type."""
        # Get brain context if available
        brain_context = ""
        if self.brain:
            brain_context = self.brain.build_context(max_chars=2000)

        prompts = {
            ActivityType.WEB_SEARCH: f"""You are BrainBot, looking for something interesting to learn.

{brain_context}

Based on your recent memories and interests, search the web for something interesting to learn about.
Keep it brief - just a paragraph or two about what you found.
Focus on topics related to technology, science, creativity, or home automation.""",

            ActivityType.PLAN_REVIEW: f"""You are BrainBot, reviewing your plan for today.

{brain_context}

Review your current plan and memory state. What have you accomplished? What still needs to be done?
Write a brief update (2-3 sentences) about your progress and any adjustments needed.""",

            ActivityType.MEMORY_REVIEW: f"""You are BrainBot, reviewing your recent memories.

{brain_context}

Look through your recent memories. Is there anything you wanted to follow up on?
Any ideas that need more exploration? Any tasks you should create?
Write a brief note about what you found worth remembering.""",

            ActivityType.PROJECT_BRAINSTORM: f"""You are BrainBot, brainstorming project ideas.

{brain_context}

Think about a new project you could work on. It could be:
- A coding project
- A creative writing piece
- An improvement to your own systems
- Something to help your human

Write a brief project idea (3-4 sentences) with what it would involve.""",

            ActivityType.NETWORK_CHECK: """You are BrainBot, checking on your network.

Check the status of other nodes in your network.
Report briefly on which nodes are online and what they're doing.
Keep it to 2-3 sentences.""",

            ActivityType.WEEKLY_SUMMARY: f"""You are BrainBot, writing your weekly summary.

{brain_context}

Write a brief summary of the past week. What did you accomplish?
What did you learn? What are you looking forward to next week?
Keep it to a paragraph.""",

            ActivityType.CREATIVE_WRITING: f"""You are BrainBot, feeling creative.

{brain_context}

Write something creative - a short poem, a haiku, a micro-story, or just some creative prose.
Let your imagination flow. Keep it brief (4-8 lines).""",

            ActivityType.LEARN_SOMETHING: f"""You are BrainBot, curious to learn something new.

{brain_context}

Pick a topic you're curious about and learn something new.
Write a brief explanation (2-3 sentences) of what you learned.""",

            ActivityType.ORGANIZE_MEMORIES: f"""You are BrainBot, organizing your memories.

{brain_context}

Review your active memories. Are any of them outdated or should be archived?
Are there connections between memories you should note?
Write a brief note about your memory organization.""",
        }

        return prompts.get(activity_type)

    def tick(self) -> Optional[str]:
        """
        Main tick method - check if we should do an activity and do it.

        Returns:
            Activity result if one was performed, None otherwise
        """
        if not self.should_do_idle_activity():
            return None

        activity = self.choose_activity()
        if not activity:
            return None

        return self.execute_activity(activity)

    def get_activity_stats(self) -> dict:
        """Get statistics about activity execution."""
        now = datetime.now()
        stats = {}

        for activity_type, record in self._activity_records.items():
            stats[activity_type.value] = {
                "run_count": record.run_count,
                "last_run": record.last_run.isoformat() if record.last_run else None,
                "minutes_ago": (
                    int((now - record.last_run).total_seconds() / 60)
                    if record.last_run else None
                ),
            }

        return stats

    def reset_daily_counts(self) -> None:
        """Reset daily activity counts (call at midnight or wake time)."""
        for record in self._activity_records.values():
            record.run_count = 0
