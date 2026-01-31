"""BrainBot schedule manager with timezone-aware scheduling."""

import logging
from datetime import datetime, time as dt_time, timedelta
from enum import Enum
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from ..config.settings import Settings
from ..state.manager import StateManager
from ..state.models import BotStatus

logger = logging.getLogger(__name__)


class SchedulePhase(str, Enum):
    """Current phase of the day."""
    SLEEPING = "sleeping"
    WAKING = "waking"
    MORNING_ROUTINE = "morning_routine"
    ACTIVE = "active"
    BEDTIME_STORY = "bedtime_story"
    EVENING_REFLECTION = "evening_reflection"
    GOING_TO_SLEEP = "going_to_sleep"


class ScheduleManager:
    """
    Manages BrainBot's daily schedule using APScheduler.

    All times are in US Central time (America/Chicago).
    """

    def __init__(
        self,
        settings: Settings,
        state_manager: StateManager,
        on_wake: Optional[Callable] = None,
        on_morning_routine: Optional[Callable] = None,
        on_bedtime_story: Optional[Callable] = None,
        on_evening_reflection: Optional[Callable] = None,
        on_sleep: Optional[Callable] = None,
    ):
        """
        Initialize schedule manager.

        Args:
            settings: BrainBot settings
            state_manager: State manager instance
            on_wake: Callback for wake time
            on_morning_routine: Callback for morning routine
            on_bedtime_story: Callback for bedtime story time
            on_evening_reflection: Callback for evening reflection
            on_sleep: Callback for sleep time
        """
        self.settings = settings
        self.state_manager = state_manager
        self.tz = ZoneInfo(settings.timezone)

        # Callbacks
        self.on_wake = on_wake
        self.on_morning_routine = on_morning_routine
        self.on_bedtime_story = on_bedtime_story
        self.on_evening_reflection = on_evening_reflection
        self.on_sleep = on_sleep

        # Scheduler
        self.scheduler = BackgroundScheduler(timezone=self.tz)
        self._running = False

    def start(self) -> None:
        """Start the scheduler and register all jobs."""
        if self._running:
            logger.warning("Scheduler already running")
            return

        schedule = self.settings.schedule

        # Wake up job
        wake_time = schedule.get_wake_time()
        self.scheduler.add_job(
            self._handle_wake,
            CronTrigger(hour=wake_time.hour, minute=wake_time.minute, timezone=self.tz),
            id="wake_up",
            name="Wake Up",
            replace_existing=True,
        )
        logger.info(f"Scheduled wake up at {wake_time.strftime('%H:%M')} Central")

        # Morning routine job (15 minutes after wake)
        morning_time = self._add_minutes(wake_time, schedule.morning_routine_duration_minutes)
        self.scheduler.add_job(
            self._handle_morning_routine,
            CronTrigger(hour=morning_time.hour, minute=morning_time.minute, timezone=self.tz),
            id="morning_routine",
            name="Morning Routine Complete",
            replace_existing=True,
        )
        logger.info(f"Scheduled morning routine completion at {morning_time.strftime('%H:%M')} Central")

        # Bedtime story job
        story_time = schedule.get_bedtime_story_time()
        self.scheduler.add_job(
            self._handle_bedtime_story,
            CronTrigger(hour=story_time.hour, minute=story_time.minute, timezone=self.tz),
            id="bedtime_story",
            name="Bedtime Story",
            replace_existing=True,
        )
        logger.info(f"Scheduled bedtime story at {story_time.strftime('%H:%M')} Central")

        # Evening reflection job
        reflection_time = schedule.get_evening_reflection_time()
        self.scheduler.add_job(
            self._handle_evening_reflection,
            CronTrigger(hour=reflection_time.hour, minute=reflection_time.minute, timezone=self.tz),
            id="evening_reflection",
            name="Evening Reflection",
            replace_existing=True,
        )
        logger.info(f"Scheduled evening reflection at {reflection_time.strftime('%H:%M')} Central")

        # Sleep job
        sleep_time = schedule.get_sleep_time()
        self.scheduler.add_job(
            self._handle_sleep,
            CronTrigger(hour=sleep_time.hour, minute=sleep_time.minute, timezone=self.tz),
            id="go_to_sleep",
            name="Go To Sleep",
            replace_existing=True,
        )
        logger.info(f"Scheduled sleep at {sleep_time.strftime('%H:%M')} Central")

        self.scheduler.start()
        self._running = True
        logger.info("Schedule manager started")

    def stop(self) -> None:
        """Stop the scheduler."""
        if self._running:
            self.scheduler.shutdown(wait=False)
            self._running = False
            logger.info("Schedule manager stopped")

    def get_current_phase(self) -> SchedulePhase:
        """
        Determine the current phase based on current time.

        Returns:
            Current schedule phase
        """
        now = self.get_current_time()
        current_time = now.time()

        schedule = self.settings.schedule
        wake_time = schedule.get_wake_time()
        sleep_time = schedule.get_sleep_time()
        morning_end = self._add_minutes(wake_time, schedule.morning_routine_duration_minutes)
        story_time = schedule.get_bedtime_story_time()
        reflection_time = schedule.get_evening_reflection_time()

        # Handle midnight (00:00) sleep time specially
        if sleep_time == dt_time(0, 0):
            # Sleep period is from midnight to wake time
            if current_time >= dt_time(0, 0) and current_time < wake_time:
                return SchedulePhase.SLEEPING
        else:
            # Normal sleep time after midnight
            if current_time >= sleep_time or current_time < wake_time:
                return SchedulePhase.SLEEPING

        # Morning period
        if wake_time <= current_time < morning_end:
            return SchedulePhase.MORNING_ROUTINE

        # Evening events
        if reflection_time <= current_time:
            return SchedulePhase.EVENING_REFLECTION
        if story_time <= current_time:
            return SchedulePhase.BEDTIME_STORY

        # Active period
        return SchedulePhase.ACTIVE

    def should_be_sleeping(self) -> bool:
        """Check if BrainBot should be sleeping right now."""
        return self.get_current_phase() == SchedulePhase.SLEEPING

    def should_be_active(self) -> bool:
        """Check if BrainBot should be active right now."""
        return self.get_current_phase() == SchedulePhase.ACTIVE

    def get_current_time(self) -> datetime:
        """Get current time in configured timezone."""
        return datetime.now(self.tz)

    def get_time_until_next_event(self) -> tuple[str, timedelta]:
        """
        Get time until the next scheduled event.

        Returns:
            Tuple of (event_name, time_until)
        """
        now = self.get_current_time()
        current_time = now.time()
        schedule = self.settings.schedule

        events = [
            ("wake_up", schedule.get_wake_time()),
            ("morning_routine", self._add_minutes(schedule.get_wake_time(), schedule.morning_routine_duration_minutes)),
            ("bedtime_story", schedule.get_bedtime_story_time()),
            ("evening_reflection", schedule.get_evening_reflection_time()),
            ("sleep", schedule.get_sleep_time()),
        ]

        # Find next event
        for name, event_time in events:
            if event_time > current_time:
                # Event is later today
                event_dt = now.replace(
                    hour=event_time.hour,
                    minute=event_time.minute,
                    second=0,
                    microsecond=0,
                )
                return name, event_dt - now

        # All events passed today, next is tomorrow's wake up
        wake_time = schedule.get_wake_time()
        tomorrow = now + timedelta(days=1)
        wake_dt = tomorrow.replace(
            hour=wake_time.hour,
            minute=wake_time.minute,
            second=0,
            microsecond=0,
        )
        return "wake_up", wake_dt - now

    def sync_state_with_schedule(self) -> None:
        """
        Synchronize bot state with the current schedule phase.

        Called on startup to ensure state matches the time of day.
        """
        phase = self.get_current_phase()
        state = self.state_manager.get_state()

        logger.info(f"Syncing state with schedule. Current phase: {phase.value}, Current status: {state.status.value}")

        if phase == SchedulePhase.SLEEPING and state.status != BotStatus.SLEEPING:
            logger.info("Schedule says we should be sleeping, transitioning to sleep")
            self.state_manager.go_to_sleep()
        elif phase == SchedulePhase.ACTIVE and state.status == BotStatus.SLEEPING:
            logger.info("Schedule says we should be active, triggering wake up")
            self._handle_wake()
        elif phase == SchedulePhase.MORNING_ROUTINE and state.status == BotStatus.SLEEPING:
            logger.info("Schedule says we're in morning routine, triggering wake up")
            self._handle_wake()

    def _add_minutes(self, t: dt_time, minutes: int) -> dt_time:
        """Add minutes to a time object."""
        total_minutes = t.hour * 60 + t.minute + minutes
        new_hour = (total_minutes // 60) % 24
        new_minute = total_minutes % 60
        return dt_time(new_hour, new_minute)

    def _handle_wake(self) -> None:
        """Handle wake up event."""
        logger.info("Wake up event triggered")
        self.state_manager.wake_up()
        if self.on_wake:
            try:
                self.on_wake()
            except Exception as e:
                logger.error(f"Error in wake callback: {e}")

    def _handle_morning_routine(self) -> None:
        """Handle morning routine completion."""
        logger.info("Morning routine complete, becoming active")
        self.state_manager.become_active()
        if self.on_morning_routine:
            try:
                self.on_morning_routine()
            except Exception as e:
                logger.error(f"Error in morning routine callback: {e}")

    def _handle_bedtime_story(self) -> None:
        """Handle bedtime story event."""
        logger.info("Bedtime story event triggered")
        self.state_manager.start_creating()
        if self.on_bedtime_story:
            try:
                self.on_bedtime_story()
            except Exception as e:
                logger.error(f"Error in bedtime story callback: {e}")

    def _handle_evening_reflection(self) -> None:
        """Handle evening reflection event."""
        logger.info("Evening reflection event triggered")
        self.state_manager.start_reflecting()
        if self.on_evening_reflection:
            try:
                self.on_evening_reflection()
            except Exception as e:
                logger.error(f"Error in evening reflection callback: {e}")

    def _handle_sleep(self) -> None:
        """Handle sleep event."""
        logger.info("Sleep event triggered")
        self.state_manager.go_to_sleep()
        if self.on_sleep:
            try:
                self.on_sleep()
            except Exception as e:
                logger.error(f"Error in sleep callback: {e}")
