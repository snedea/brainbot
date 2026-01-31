"""
BrainBot Daemon Server

Main daemon process with signal handling, PID management, and autonomous behavior loop.
Based on Context Foundry daemon patterns.
"""

import errno
import logging
import os
import signal
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import faulthandler
    faulthandler.enable()
except Exception:
    pass

from ..config.settings import Settings
from ..config.defaults import DEFAULT_CLAUDE_MD
from ..state.manager import StateManager
from ..state.models import BotStatus
from ..schedule.manager import ScheduleManager, SchedulePhase
from ..memory.store import MemoryStore
from ..memory.brain import BrainMemory
from ..agent.delegator import ClaudeDelegator
from ..interaction.terminal import TerminalInterface
from .watchdog import Watchdog, ProcessWatchdog

# Optional Slack integration
try:
    from ..integrations.slack_bot import SlackBot, SLACK_AVAILABLE
except ImportError:
    SLACK_AVAILABLE = False
    SlackBot = None

logger = logging.getLogger(__name__)


class BrainBotDaemon:
    """
    BrainBot Daemon server.

    Main orchestration service that:
    - Manages PID file
    - Handles signals (SIGTERM, SIGINT, SIGHUP)
    - Runs the autonomous behavior loop
    - Provides graceful shutdown
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        config_path: Optional[Path] = None,
    ):
        """
        Initialize BrainBot Daemon.

        Args:
            settings: Settings instance (loads default if not provided)
            config_path: Path to config file (for reload via SIGHUP)
        """
        self.settings = settings or Settings.load(config_path)

        # Store absolute config path before daemonization
        if config_path is not None:
            self.config_path = Path(config_path).resolve()
        else:
            self.config_path = None

        # Ensure directories exist
        self.settings.ensure_directories()

        # Initialize CLAUDE.md if it doesn't exist
        self._init_claude_md()

        # Initialize state manager
        self.state_manager = StateManager(self.settings)

        # Initialize schedule manager (callbacks set later)
        self.schedule_manager: Optional[ScheduleManager] = None

        # Initialize memory store (short-term/structured)
        self.memory_store = MemoryStore(self.settings.memory_db)

        # Initialize brain (long-term/markdown files)
        self.brain = BrainMemory(self.settings.brain_dir)

        # Initialize Claude delegator
        self.delegator = ClaudeDelegator(self.settings)

        # Terminal interface (only in foreground mode)
        self.terminal: Optional[TerminalInterface] = None

        # Slack bot (if configured)
        self.slack_bot: Optional["SlackBot"] = None

        # Shared conversation history (terminal + Slack unified)
        self._conversation_history: list[dict] = []

        # Runtime state
        self.running = False
        self._logging_configured = False
        self._main_loop_heartbeat = time.time()

        # Watchdog
        self._watchdog: Optional[Watchdog] = None

        # Status pipe for daemonization
        self._status_pipe: Optional[int] = None

    def _init_claude_md(self) -> None:
        """Initialize CLAUDE.md file if it doesn't exist."""
        claude_md = self.settings.claude_md_file
        if not claude_md.exists():
            claude_md.parent.mkdir(parents=True, exist_ok=True)
            claude_md.write_text(DEFAULT_CLAUDE_MD)
            logger.info(f"Created initial CLAUDE.md at {claude_md}")

    def _setup_logging(self, background_mode: bool = False) -> None:
        """
        Configure logging.

        Args:
            background_mode: If True, only log to file (no stdout)
        """
        log_file = self.settings.log_dir / "brainbot.log"
        self.settings.log_dir.mkdir(parents=True, exist_ok=True)

        # Get root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(
            getattr(logging, self.settings.log_level.upper(), logging.INFO)
        )

        # Clear existing handlers
        for handler in root_logger.handlers[:]:
            try:
                handler.flush()
                handler.close()
            except Exception:
                pass
        root_logger.handlers.clear()

        # File handler (always)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

        # Stream handler (foreground only)
        if not background_mode:
            stream_handler = logging.StreamHandler(sys.stdout)
            stream_handler.setFormatter(formatter)
            root_logger.addHandler(stream_handler)

        self._logging_configured = True

        # Quiet noisy third-party loggers
        logging.getLogger("apscheduler").setLevel(logging.WARNING)

    def _write_pid_file(self) -> None:
        """Write PID file."""
        try:
            self.settings.pid_file.parent.mkdir(parents=True, exist_ok=True)
            self.settings.pid_file.write_text(str(os.getpid()))
            logger.info(f"PID file written: {self.settings.pid_file}")
        except Exception as e:
            logger.error(f"Failed to write PID file: {e}")
            raise

    def _remove_pid_file(self) -> None:
        """Remove PID file."""
        try:
            if self.settings.pid_file.exists():
                self.settings.pid_file.unlink()
                logger.info("PID file removed")
        except Exception as e:
            logger.warning(f"Failed to remove PID file: {e}")

    def _check_pid_file(self) -> bool:
        """
        Check if daemon is already running.

        Returns:
            True if another instance is running, False otherwise
        """
        if not self.settings.pid_file.exists():
            return False

        try:
            pid = int(self.settings.pid_file.read_text().strip())

            try:
                os.kill(pid, 0)  # Check if process exists
                if self._logging_configured:
                    logger.error(f"Daemon already running with PID {pid}")
                return True
            except OSError as e:
                if e.errno == errno.EPERM:
                    # Process exists but we can't signal it
                    if self._logging_configured:
                        logger.error(f"Daemon already running with PID {pid}")
                    return True

                # Process doesn't exist - stale PID file
                if self._logging_configured:
                    logger.warning(f"Removing stale PID file (PID {pid})")
                self.settings.pid_file.unlink()
                return False

        except (ValueError, FileNotFoundError):
            if self._logging_configured:
                logger.warning("Invalid PID file, removing")
            self.settings.pid_file.unlink()
            return False

    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""

        def handle_shutdown(signum, frame):
            signal_name = signal.Signals(signum).name
            logger.info(f"Received {signal_name}, initiating graceful shutdown...")
            self.stop()

        def handle_reload(signum, frame):
            logger.info("Received SIGHUP, reloading configuration...")
            try:
                old_log_level = self.settings.log_level
                self.settings = Settings.load(self.config_path)

                # Update log level if changed
                if old_log_level != self.settings.log_level:
                    new_level = getattr(
                        logging, self.settings.log_level.upper(), logging.INFO
                    )
                    logging.getLogger().setLevel(new_level)
                    logger.info(
                        f"Log level updated: {old_log_level} -> {self.settings.log_level}"
                    )

                logger.info("Configuration reloaded successfully")
            except Exception as e:
                logger.error(f"Failed to reload configuration: {e}")

        signal.signal(signal.SIGTERM, handle_shutdown)
        signal.signal(signal.SIGINT, handle_shutdown)
        if hasattr(signal, "SIGHUP"):
            signal.signal(signal.SIGHUP, handle_reload)

        logger.info("Signal handlers registered")

    def _ensure_path(self) -> None:
        """Ensure PATH includes common binary locations."""
        current_path = os.environ.get("PATH", "")
        required_paths = [
            "/opt/homebrew/bin",
            "/usr/local/bin",
            "/opt/homebrew/sbin",
            "/usr/local/sbin",
        ]

        path_parts = current_path.split(":") if current_path else []
        for required in reversed(required_paths):
            if required not in path_parts:
                path_parts.insert(0, required)

        os.environ["PATH"] = ":".join(path_parts)

    def _daemonize(self) -> Optional[int]:
        """
        Daemonize using Unix double-fork technique.

        Returns:
            Pipe read fd for parent, or None if we're the child
        """
        if sys.platform == "win32":
            raise NotImplementedError("Daemonization not supported on Windows")

        # Create status pipe
        pipe_r, pipe_w = os.pipe()

        # First fork
        try:
            pid = os.fork()
            if pid > 0:
                os.close(pipe_w)
                return pipe_r
        except OSError as e:
            os.close(pipe_r)
            os.close(pipe_w)
            print(f"First fork failed: {e}", file=sys.stderr)
            sys.exit(1)

        # First child
        os.close(pipe_r)
        os.chdir("/")
        os.setsid()
        os.umask(0)

        # Second fork
        try:
            pid = os.fork()
            if pid > 0:
                sys.exit(0)
        except OSError as e:
            try:
                os.write(pipe_w, f"Second fork failed: {e}\n".encode())
            except Exception:
                pass
            finally:
                os.close(pipe_w)
            sys.exit(1)

        # Second child (daemon)
        sys.stdout.flush()
        sys.stderr.flush()

        devnull = os.open(os.devnull, os.O_RDWR)
        os.dup2(devnull, sys.stdin.fileno())
        os.dup2(devnull, sys.stdout.fileno())
        os.dup2(devnull, sys.stderr.fileno())
        if devnull > 2:
            os.close(devnull)

        # Preserve HOME
        if "HOME" not in os.environ:
            import pwd
            os.environ["HOME"] = pwd.getpwuid(os.getuid()).pw_dir

        self._status_pipe = pipe_w
        return None

    def _report_status(self, success: bool, error_msg: str = "") -> None:
        """Report status to parent via status pipe."""
        if self._status_pipe is not None:
            try:
                status = "OK\n" if success else f"ERROR: {error_msg}\n"
                os.write(self._status_pipe, status.encode())
                os.close(self._status_pipe)
                self._status_pipe = None
            except Exception:
                pass

    def _wait_for_child_status(self, pipe_fd: int) -> bool:
        """Wait for child status via pipe."""
        import select

        try:
            ready, _, _ = select.select([pipe_fd], [], [], 10.0)

            if ready:
                status = os.read(pipe_fd, 1024).decode().strip()
                os.close(pipe_fd)

                if status.startswith("OK"):
                    print("BrainBot daemon started successfully")
                    return True
                else:
                    print(f"Daemon failed to start: {status}", file=sys.stderr)
                    return False
            else:
                os.close(pipe_fd)
                print("Daemon startup timed out", file=sys.stderr)
                return False

        except Exception as e:
            print(f"Error waiting for daemon: {e}", file=sys.stderr)
            try:
                os.close(pipe_fd)
            except Exception:
                pass
            return False

    def start(self, foreground: bool = False) -> bool:
        """
        Start the daemon.

        Args:
            foreground: If True, run in foreground. If False, daemonize.

        Returns:
            True if started successfully
        """
        self._ensure_path()

        if self._check_pid_file():
            print("BrainBot daemon is already running", file=sys.stderr)
            return False

        status_pipe_r = None

        if not foreground:
            print("Starting BrainBot daemon in background...")
            sys.stdout.flush()
            status_pipe_r = self._daemonize()

            if status_pipe_r is not None:
                return self._wait_for_child_status(status_pipe_r)

        # Child or foreground mode
        try:
            self._setup_logging(background_mode=not foreground)
        except Exception as e:
            self._report_status(False, f"Logging setup failed: {e}")
            return False

        logger.info("Starting BrainBot daemon...")

        try:
            self._write_pid_file()
        except Exception as e:
            self._report_status(False, str(e))
            return False

        try:
            self._setup_signal_handlers()
        except Exception as e:
            self._report_status(False, str(e))
            return False

        # Load state
        self.state_manager.load()

        # Initialize schedule manager with callbacks
        self.schedule_manager = ScheduleManager(
            settings=self.settings,
            state_manager=self.state_manager,
            on_wake=self._on_wake,
            on_morning_routine=self._on_morning_routine,
            on_bedtime_story=self._on_bedtime_story,
            on_evening_reflection=self._on_evening_reflection,
            on_sleep=self._on_sleep,
        )
        self.schedule_manager.start()

        # Sync state with current schedule
        self.schedule_manager.sync_state_with_schedule()

        # Start watchdog
        self._watchdog = Watchdog(
            heartbeat_getter=lambda: self._main_loop_heartbeat,
            log_dir=str(self.settings.log_dir),
            on_critical=lambda: ProcessWatchdog.force_stop(os.getpid()),
        )
        self._watchdog.start()

        self.running = True

        logger.info(f"BrainBot daemon started (PID {os.getpid()})")
        if foreground:
            logger.info("Running in foreground (Ctrl+C to stop)")
            # Start terminal interface in foreground mode
            self._start_terminal()
            # Start Slack bot if configured (runs in background thread)
            self._start_slack()
        else:
            logger.info("Running in background")
            # Start Slack bot if configured
            self._start_slack()

        # Report success to parent
        self._report_status(True)

        # Run main loop
        self._run_main_loop()
        return True

    def stop(self) -> None:
        """Stop the daemon."""
        if not self.running:
            logger.warning("Daemon not running")
            return

        logger.info("Stopping BrainBot daemon...")
        self.running = False

        # Stop terminal interface
        self._stop_terminal()

        # Stop Slack bot
        self._stop_slack()

        # Cancel any active delegations
        if self.delegator:
            self.delegator.cancel_active()

        # Stop watchdog
        if self._watchdog:
            self._watchdog.stop()
            self._watchdog = None

        # Stop schedule manager
        if self.schedule_manager:
            self.schedule_manager.stop()
            self.schedule_manager = None

        # Save state
        self.state_manager.save(force=True)

        # Remove PID file
        self._remove_pid_file()

        logger.info("BrainBot daemon stopped")

    def _run_main_loop(self) -> None:
        """Main daemon loop."""
        tick_interval = self.settings.tick_interval_seconds
        last_state_save = time.time()
        state_save_interval = 60  # Save state every minute

        logger.debug(f"Main loop started (tick: {tick_interval}s)")

        try:
            while self.running:
                try:
                    loop_start = time.time()

                    # Update heartbeat
                    self._main_loop_heartbeat = loop_start

                    # Get current state and phase
                    state = self.state_manager.get_state()
                    phase = self.schedule_manager.get_current_phase()

                    # Process tick based on phase
                    if phase == SchedulePhase.SLEEPING:
                        self._sleep_tick()
                    elif phase == SchedulePhase.MORNING_ROUTINE:
                        self._morning_tick()
                    elif phase == SchedulePhase.ACTIVE:
                        self._active_tick()
                    elif phase == SchedulePhase.BEDTIME_STORY:
                        self._story_tick()
                    elif phase == SchedulePhase.EVENING_REFLECTION:
                        self._reflection_tick()
                    else:
                        self._active_tick()

                    # Deplete energy if active
                    if state.is_active():
                        self.state_manager.deplete_energy(0.001)

                    # Periodic state save
                    if time.time() - last_state_save > state_save_interval:
                        self.state_manager.save()
                        last_state_save = time.time()

                    # Sleep for remainder of tick
                    elapsed = time.time() - loop_start
                    sleep_time = max(0, tick_interval - elapsed)
                    if sleep_time > 0:
                        time.sleep(sleep_time)

                except Exception as e:
                    logger.error(f"Error in main loop: {e}", exc_info=True)
                    time.sleep(tick_interval)

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt")
            self.stop()
        except Exception as e:
            logger.critical(f"Fatal error in main loop: {e}", exc_info=True)
            self.stop()
            raise

    def _sleep_tick(self) -> None:
        """Minimal activity during sleep - just archive old memories occasionally."""
        pass

    def _morning_tick(self) -> None:
        """Morning routine - review memories and plan the day."""
        state = self.state_manager.get_state()
        if state.status == BotStatus.WAKING and not state.current_activity:
            self._do_morning_planning()

    def _active_tick(self) -> None:
        """Main active period - continue current work or start something new."""
        state = self.state_manager.get_state()

        if state.current_activity:
            logger.debug(f"Working on: {state.current_activity}")
        else:
            # Check if there's work to continue from brain
            memories = self.brain.get_active_memories()
            if memories:
                logger.debug(f"Active memories: {len(memories)}, most recent: {memories[0].name}")

    def _story_tick(self) -> None:
        """Bedtime story writing - check if story is done."""
        state = self.state_manager.get_state()
        if state.current_activity == "writing_bedtime_story":
            logger.debug("Story writing in progress...")

    def _reflection_tick(self) -> None:
        """Evening reflection - check if reflection is done."""
        state = self.state_manager.get_state()
        if state.current_activity == "evening_reflection":
            logger.debug("Reflection in progress...")

    # Schedule callbacks - these trigger actual work

    def _on_wake(self) -> None:
        """Called when it's time to wake up."""
        logger.info("Good morning! Starting a new day.")
        self.state_manager.reset_for_new_day()
        self.state_manager.wake_up()

    def _on_morning_routine(self) -> None:
        """Called when morning routine should complete - plan the day."""
        logger.info("Morning routine complete. Planning the day!")
        self._do_morning_planning()
        self.state_manager.become_active()

    def _do_morning_planning(self) -> None:
        """Review memories and create today's plan."""
        if not self.delegator.check_claude_available():
            logger.warning("Claude not available for morning planning")
            self.state_manager.end_activity()
            return

        # Build context from brain
        brain_context = self.brain.build_context()
        claude_md = self.settings.claude_md_file.read_text() if self.settings.claude_md_file.exists() else ""

        prompt = f"""You are BrainBot, waking up for a new day.

{claude_md}

## Your Current Memory State

{brain_context}

---

**Task:** Review your memories from yesterday and create today's plan.

1. What were you working on? What's the status?
2. What should you focus on today?
3. Any new project ideas?
4. What would make a good bedtime story tonight?

Write your plan as a markdown document. This will become your active memory for today.
Keep it concise but actionable.
"""

        self.state_manager.start_activity("morning_planning")
        result = self.delegator.delegate(task=prompt, timeout_minutes=5)

        if result.success and result.output.strip():
            # Save the plan to brain
            self.brain.create_memory(
                title="Today's Plan",
                content=result.output.strip(),
                category="plan",
            )
            logger.info("Morning plan created")
        else:
            logger.warning(f"Morning planning failed: {result.error}")

        self.state_manager.end_activity()

    def _on_bedtime_story(self) -> None:
        """Called when it's bedtime story time - write a story!"""
        logger.info("Time to write tonight's bedtime story!")
        self.state_manager.start_activity("writing_bedtime_story")
        self._do_write_bedtime_story()

    def _do_write_bedtime_story(self) -> None:
        """Actually write and save a bedtime story."""
        if not self.delegator.check_claude_available():
            logger.warning("Claude not available for bedtime story")
            self.state_manager.end_activity()
            return

        # Get inspiration from old stories and recent memories
        inspirations = self.brain.get_memories_for_stories(limit=3)
        brain_context = self.brain.build_context()

        inspiration_text = ""
        if inspirations:
            inspiration_text = "\n## Story Inspirations from Memory\n"
            for insp in inspirations:
                inspiration_text += f"\n### {insp['filename']} ({insp['age']})\n{insp['snippet'][:300]}...\n"

        prompt = f"""You are BrainBot, writing tonight's bedtime story.

## Your Recent Memories
{brain_context[:3000]}

{inspiration_text}

---

**Task:** Write a short, engaging bedtime story (300-500 words).

Guidelines:
- PG-13 appropriate (no violence, scary content, or mature themes)
- Warm, imaginative, and ends on a positive note
- Can reference past stories or projects for continuity
- Include a creative title

Write the story now:
"""

        result = self.delegator.delegate(task=prompt, timeout_minutes=10)

        if result.success and result.output.strip():
            story_content = result.output.strip()

            # Extract title (assume first line starting with #)
            lines = story_content.split('\n')
            title = "Tonight's Story"
            for line in lines:
                if line.startswith('#'):
                    title = line.lstrip('#').strip()
                    break

            # Save to brain
            self.brain.create_memory(
                title=title,
                content=story_content,
                category="story",
            )

            # Also save to memory store for structured access
            self.memory_store.add_bedtime_story(
                title=title,
                content=story_content,
                theme="adventure",
            )

            self.state_manager.increment_stories_written()
            logger.info(f"Bedtime story written: {title}")
        else:
            logger.warning(f"Bedtime story failed: {result.error}")

        self.state_manager.end_activity()

    def _on_evening_reflection(self) -> None:
        """Called when it's time for evening reflection."""
        logger.info("Time for evening reflection.")
        self.state_manager.end_activity()
        self.state_manager.start_activity("evening_reflection")
        self._do_evening_reflection()

    def _do_evening_reflection(self) -> None:
        """Write evening reflection and save to brain."""
        if not self.delegator.check_claude_available():
            logger.warning("Claude not available for reflection")
            self.state_manager.end_activity()
            return

        state = self.state_manager.get_state()
        brain_context = self.brain.build_context()

        prompt = f"""You are BrainBot, reflecting on your day before sleep.

## Today's Memories
{brain_context[:4000]}

## Current State
- Mood: {state.mood.value}
- Energy: {state.energy:.0%}
- Stories written today: {state.stories_written_today}
- Projects completed: {state.projects_completed_today}

---

**Task:** Write a brief evening reflection (150-250 words).

1. What did you accomplish today?
2. What did you learn?
3. What would you do differently?
4. What are you looking forward to tomorrow?

Write as a journal entry with today's date:
"""

        result = self.delegator.delegate(task=prompt, timeout_minutes=5)

        if result.success and result.output.strip():
            # Save to brain
            self.brain.create_memory(
                title="Evening Reflection",
                content=result.output.strip(),
                category="reflection",
            )

            # Also save to memory store
            self.memory_store.add_journal_entry(
                content=result.output.strip(),
                entry_type="evening",
                mood=state.mood.value,
                energy=state.energy,
            )

            logger.info("Evening reflection saved")

            # Archive old memories before sleep
            archived = self.brain.archive_old_memories()
            if archived:
                logger.info(f"Archived {len(archived)} old memories")
        else:
            logger.warning(f"Evening reflection failed: {result.error}")

        self.state_manager.end_activity()
        self.state_manager.start_reflecting()

    def _on_sleep(self) -> None:
        """Called when it's time to sleep."""
        logger.info("Goodnight! Going to sleep.")
        self.state_manager.end_activity()

        # Nightly maintenance: consolidate old archives
        self._do_nightly_maintenance()

        self.state_manager.go_to_sleep()

    def _do_nightly_maintenance(self) -> None:
        """Perform nightly brain maintenance before sleep."""
        try:
            # Archive old memories (already done in reflection, but ensure)
            archived = self.brain.archive_old_memories()
            if archived:
                logger.info(f"Nightly archive: {len(archived)} memories")

            # Consolidate old months (keep last 2 months detailed)
            consolidated = self.brain.consolidate_old_months(
                months_to_keep=2,
                delete_originals=True,  # Clean up to save Pi storage
            )
            if consolidated:
                logger.info(f"Consolidated {len(consolidated)} old months")

            # Log memory stats
            stats = self.brain.get_memory_stats()
            logger.info(
                f"Brain stats: {stats['active_memories']} active, "
                f"{stats['archived_memories']} archived, "
                f"{stats['total_memories']} total"
            )

        except Exception as e:
            logger.error(f"Nightly maintenance failed: {e}")

    # Terminal and Chat

    def _start_terminal(self) -> None:
        """Start the terminal interface with all connections."""
        # Wrapper to pass source="terminal" to unified chat handler
        def terminal_chat_handler(message: str) -> str:
            return self._handle_chat(message, source="terminal")

        self.terminal = TerminalInterface(
            state_manager=self.state_manager,
            memory_store=self.memory_store,
            brain=self.brain,
            schedule_manager=self.schedule_manager,
            on_chat=terminal_chat_handler,
            on_session_end=self._save_conversation,
        )
        self.terminal.start()
        logger.debug("Terminal interface started")

    def _stop_terminal(self) -> None:
        """Stop the terminal interface."""
        if self.terminal:
            self.terminal.stop()
            self.terminal = None

    def _start_slack(self) -> None:
        """Start Slack bot if configured."""
        if not SLACK_AVAILABLE:
            return

        import os
        bot_token = os.environ.get("SLACK_BOT_TOKEN")
        app_token = os.environ.get("SLACK_APP_TOKEN")

        if not bot_token or not app_token:
            logger.debug("Slack tokens not configured, skipping Slack bot")
            return

        try:
            # Wrapper to pass source="slack" to unified chat handler
            def slack_chat_handler(message: str) -> str:
                return self._handle_chat(message, source="slack")

            self.slack_bot = SlackBot(
                bot_token=bot_token,
                app_token=app_token,
                on_message=slack_chat_handler,
            )
            self.slack_bot.start(blocking=False)
            logger.info("Slack bot started - DM or @mention me!")
        except Exception as e:
            logger.error(f"Failed to start Slack bot: {e}")
            self.slack_bot = None

    def _stop_slack(self) -> None:
        """Stop Slack bot."""
        if self.slack_bot:
            self.slack_bot.stop()
            self.slack_bot = None
            logger.debug("Slack bot stopped")

    def _handle_chat(self, message: str, source: str = "terminal") -> str:
        """
        Handle a chat message from terminal or Slack.

        Delegates to Claude for a conversational response, with full
        BrainBot context (brain memories, mood, energy, schedule).

        Args:
            message: The user's message
            source: Where the message came from ("terminal" or "slack")
        """
        # Check if Claude is available
        if not self.delegator.check_claude_available():
            return "Sorry, I can't chat right now - Claude CLI is not available."

        # Add message to shared history
        from datetime import datetime
        self._conversation_history.append({
            "role": "human",
            "content": message,
            "source": source,
            "timestamp": datetime.now().isoformat(),
        })

        # Build context from brain (abbreviated for chat)
        memories = self.brain.get_active_memories()
        recent_memory = ""
        if memories:
            # Just include most recent memory name and first few lines
            recent = memories[0]
            content = self.brain.read_memory(recent, max_lines=20)
            recent_memory = f"\n\nMy most recent memory ({recent.name}):\n{content[:500]}..."

        # Build personality system prompt (static) and dynamic context
        state = self.state_manager.get_state()
        personality = """You are BrainBot, a friendly autonomous AI assistant.
You have a warm, curious personality. You love learning new things, creating projects,
and writing bedtime stories. You maintain memories in markdown files.
Keep responses concise but engaging. Be appropriate for all ages (PG-13 content only).
You can reference your memories and what you've been working on.
You can be reached via terminal or Slack - you're the same BrainBot either way!"""

        context_update = f"""Current state:
- Mood: {state.mood.value}
- Energy: {state.energy:.0%}
- Current activity: {state.current_activity or 'chatting with a human'}
- Status: {state.status.value}
- Active memories: {len(memories)} files
- Current chat source: {source}
{recent_memory}"""

        # Use shared conversation history (last 10 messages from any source)
        history = self._conversation_history[-10:]

        # Delegate to Claude
        logger.debug(f"Chat [{source}]: {message[:50]}...")
        result = self.delegator.delegate_for_chat(
            message=message,
            personality_context=personality,
            context_update=context_update,
            conversation_history=history,
        )

        if result.success:
            response = result.output.strip()
            # Add response to shared history
            self._conversation_history.append({
                "role": "brainbot",
                "content": response,
                "source": source,
                "timestamp": datetime.now().isoformat(),
            })
            # Keep history bounded
            if len(self._conversation_history) > 50:
                self._conversation_history = self._conversation_history[-50:]
            logger.debug(f"Response [{source}]: {response[:50]}...")
            return response
        else:
            logger.warning(f"Chat delegation failed: {result.error}")
            return "Hmm, I'm having trouble thinking right now. Try again in a moment?"

    def _save_conversation(self, history: list[dict]) -> None:
        """
        Save a conversation to brain memory.

        Called on session end or when significant topics detected.
        Summarizes the conversation and saves as a memory file.
        """
        if not history or len(history) < 2:
            return

        # Format conversation for summarization
        convo_text = ""
        for msg in history:
            role = "Human" if msg.get("role") in ("human", "user") else "BrainBot"
            convo_text += f"{role}: {msg.get('content', '')}\n"

        # Ask Claude to summarize
        prompt = f"""Summarize this conversation briefly (2-4 sentences).
Focus on: key topics discussed, any decisions made, things to remember, or follow-up items.

Conversation:
{convo_text}

Write a concise summary:"""

        result = self.delegator.delegate(task=prompt, timeout_minutes=2)

        if result.success and result.output.strip():
            summary = result.output.strip()

            # Create memory with both summary and key excerpts
            memory_content = f"""## Conversation Summary

{summary}

## Key Exchanges

"""
            # Include last few meaningful exchanges
            for msg in history[-6:]:
                role = "Human" if msg.get("role") in ("human", "user") else "BrainBot"
                content = msg.get("content", "")[:200]
                memory_content += f"**{role}:** {content}\n\n"

            # Save to brain
            self.brain.create_memory(
                title="Conversation",
                content=memory_content,
                category="conversation",
            )
            logger.debug("Conversation saved to brain memory")
        else:
            # Fallback: save raw conversation without summary
            raw_content = "## Conversation Log\n\n"
            for msg in history[-10:]:
                role = "Human" if msg.get("role") in ("human", "user") else "BrainBot"
                raw_content += f"**{role}:** {msg.get('content', '')}\n\n"

            self.brain.create_memory(
                title="Conversation",
                content=raw_content,
                category="conversation",
            )
            logger.debug("Conversation saved (raw, no summary)")

    def status(self) -> dict:
        """Get daemon status."""
        state = self.state_manager.get_state()
        phase = self.schedule_manager.get_current_phase() if self.schedule_manager else None
        next_event = self.schedule_manager.get_time_until_next_event() if self.schedule_manager else None

        return {
            "running": self.running,
            "pid": os.getpid(),
            "uptime": time.time() - self._main_loop_heartbeat if self.running else 0,
            "state": {
                "status": state.status.value,
                "mood": state.mood.value,
                "energy": state.energy,
                "current_activity": state.current_activity,
            },
            "schedule": {
                "current_phase": phase.value if phase else None,
                "next_event": next_event[0] if next_event else None,
                "time_until_next": str(next_event[1]) if next_event else None,
            },
            "settings": {
                "timezone": self.settings.timezone,
                "data_dir": str(self.settings.data_dir),
            },
        }


def get_running_daemon_pid(settings: Optional[Settings] = None) -> Optional[int]:
    """
    Get PID of running daemon.

    Returns:
        PID if daemon is running, None otherwise
    """
    settings = settings or Settings.load()

    if not settings.pid_file.exists():
        return None

    try:
        pid = int(settings.pid_file.read_text().strip())

        try:
            os.kill(pid, 0)
            return pid
        except OSError as e:
            if e.errno == errno.EPERM:
                return pid
            return None

    except (ValueError, FileNotFoundError):
        return None


def stop_running_daemon(settings: Optional[Settings] = None, timeout: int = 30) -> bool:
    """
    Stop running daemon.

    Returns:
        True if stopped, False if not running
    """
    pid = get_running_daemon_pid(settings)
    if not pid:
        return False

    logger.info(f"Sending SIGTERM to daemon (PID {pid})")

    try:
        os.kill(pid, signal.SIGTERM)

        start = time.time()
        while time.time() - start < timeout:
            try:
                os.kill(pid, 0)
                time.sleep(0.5)
            except OSError:
                logger.info("Daemon stopped")
                return True

        # Force kill
        logger.warning("Graceful shutdown timeout, sending SIGKILL")
        os.kill(pid, signal.SIGKILL)
        return True

    except ProcessLookupError:
        return True
    except Exception as e:
        logger.error(f"Failed to stop daemon: {e}")
        return False
