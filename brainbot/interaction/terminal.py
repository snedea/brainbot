"""Terminal interface for human interaction with BrainBot."""

import logging
import sys
import threading
import time
from datetime import datetime
from typing import Callable, Optional, TYPE_CHECKING
from enum import Enum

# Rainbow colors for BrainBot name
RAINBOW_COLORS = [
    "\033[31m",  # Red
    "\033[33m",  # Yellow
    "\033[32m",  # Green
    "\033[36m",  # Cyan
    "\033[34m",  # Blue
    "\033[35m",  # Magenta
]
RESET = "\033[0m"


def rainbow_text(text: str) -> str:
    """Apply rainbow colors to text."""
    result = []
    for i, char in enumerate(text):
        color = RAINBOW_COLORS[i % len(RAINBOW_COLORS)]
        result.append(f"{color}{char}")
    result.append(RESET)
    return "".join(result)

if TYPE_CHECKING:
    from ..state.manager import StateManager
    from ..memory.store import MemoryStore
    from ..memory.brain import BrainMemory
    from ..schedule.manager import ScheduleManager

logger = logging.getLogger(__name__)


class RequestType(str, Enum):
    """Types of human requests."""
    RESTART = "restart"
    APPROVAL = "approval"
    HELP = "help"
    FEEDBACK = "feedback"
    COMMAND = "command"
    CHAT = "chat"


class TerminalInterface:
    """
    Terminal interface for human interaction with BrainBot.

    Provides a simple text-based interface for monitoring and
    interacting with the daemon.
    """

    def __init__(
        self,
        state_manager: Optional["StateManager"] = None,
        memory_store: Optional["MemoryStore"] = None,
        brain: Optional["BrainMemory"] = None,
        schedule_manager: Optional["ScheduleManager"] = None,
        on_command: Optional[Callable[[str], str]] = None,
        on_chat: Optional[Callable[[str], str]] = None,
        on_session_end: Optional[Callable[[list[dict]], None]] = None,
    ):
        """
        Initialize terminal interface.

        Args:
            state_manager: BrainBot state manager for real-time state
            memory_store: Memory store for goals, stories, etc.
            brain: Brain memory for long-term memories
            schedule_manager: Schedule manager for phase info
            on_command: Callback for processing commands
            on_chat: Callback for processing chat messages
            on_session_end: Callback when session ends, receives conversation history
        """
        self.state_manager = state_manager
        self.memory_store = memory_store
        self.brain = brain
        self.schedule_manager = schedule_manager
        self.on_command = on_command
        self.on_chat = on_chat
        self.on_session_end = on_session_end

        self._running = False
        self._input_thread: Optional[threading.Thread] = None
        self._conversation_history: list[dict] = []
        self._total_message_count = 0  # Track total for checkpoints (not capped)
        self._session_saved = False  # Prevent double-saving

    def start(self) -> None:
        """Start the terminal interface."""
        if self._running:
            return

        self._running = True
        self._input_thread = threading.Thread(
            target=self._input_loop,
            daemon=True,
        )
        self._input_thread.start()
        logger.info("Terminal interface started")

    def stop(self) -> None:
        """Stop the terminal interface."""
        self._running = False

        # Save conversation if we had meaningful exchanges (and not already saved)
        if self.on_session_end and len(self._conversation_history) >= 2 and not self._session_saved:
            try:
                self._session_saved = True
                self.on_session_end(self._conversation_history)
            except Exception as e:
                logger.error(f"Failed to save session: {e}")

        logger.info("Terminal interface stopped")

    # Keywords that indicate a conversation worth saving
    SIGNIFICANT_KEYWORDS = [
        "remember", "important", "idea", "project", "plan", "goal",
        "learn", "discovered", "realized", "decided", "promise",
        "tomorrow", "next time", "don't forget", "save this",
    ]

    def add_to_history(self, role: str, content: str) -> None:
        """Add a message to conversation history."""
        self._conversation_history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        })
        self._total_message_count += 1

        # Auto-save check: significant conversation detected
        if self._should_auto_save(content):
            self._trigger_auto_save()

        # Keep last 20 messages in memory (but total count continues)
        if len(self._conversation_history) > 20:
            self._conversation_history = self._conversation_history[-20:]

    def _should_auto_save(self, latest_content: str) -> bool:
        """Check if conversation should be auto-saved."""
        # Need at least 6 messages for a meaningful conversation
        if len(self._conversation_history) < 6:
            return False

        # Check for significant keywords in recent messages
        recent = self._conversation_history[-4:]
        all_text = " ".join(m["content"].lower() for m in recent)

        for keyword in self.SIGNIFICANT_KEYWORDS:
            if keyword in all_text:
                return True

        # Also save every 10 messages as a checkpoint (uses total, not capped history)
        if self._total_message_count > 0 and self._total_message_count % 10 == 0:
            return True

        return False

    def _trigger_auto_save(self) -> None:
        """Trigger auto-save of conversation."""
        if not self.on_session_end:
            return

        # Don't save too frequently - check last save time
        if not hasattr(self, "_last_auto_save"):
            self._last_auto_save = 0

        now = time.time()
        if now - self._last_auto_save < 300:  # 5 minute cooldown
            return

        self._last_auto_save = now
        logger.info("Auto-saving significant conversation...")

        try:
            # Pass a copy so we don't affect ongoing conversation
            self.on_session_end(list(self._conversation_history))
        except Exception as e:
            logger.error(f"Auto-save failed: {e}")

    def get_conversation_history(self) -> list[dict]:
        """Get recent conversation history."""
        return self._conversation_history[-10:]

    def _save_on_exit(self) -> None:
        """Save conversation when user types quit/exit."""
        if self.on_session_end and len(self._conversation_history) >= 2 and not self._session_saved:
            logger.info("Saving conversation on exit...")
            try:
                self._session_saved = True
                self.on_session_end(list(self._conversation_history))
            except Exception as e:
                logger.error(f"Failed to save on exit: {e}")

    def _input_loop(self) -> None:
        """Main input loop."""
        self._print_welcome()

        while self._running:
            try:
                user_input = input("\n> ").strip()

                if not user_input:
                    continue

                if user_input.lower() in ("quit", "exit", "q"):
                    print("Goodbye!")
                    self._save_on_exit()
                    break

                if user_input.startswith("/"):
                    # Command
                    response = self._handle_command(user_input[1:])
                else:
                    # Chat message
                    self.add_to_history("human", user_input)
                    response = self._handle_chat(user_input)
                    if response:
                        self.add_to_history("brainbot", response)

                if response:
                    # Cyan color for BrainBot responses
                    print(f"\n\033[36m{response}\033[0m")

            except EOFError:
                break
            except KeyboardInterrupt:
                print("\n\nInterrupted. Type 'quit' to exit.")
            except Exception as e:
                logger.error(f"Terminal input error: {e}")

    def _print_welcome(self) -> None:
        """Print welcome message."""
        print("\n" + "=" * 50)
        print(f"  🧠 {rainbow_text('BrainBot')} Terminal Interface")
        print("=" * 50)
        print("\nCommands:")
        print("  /status    - Show BrainBot's current status")
        print("  /goals     - Show today's goals")
        print("  /story     - Request a bedtime story")
        print("  /project   - Show current project")
        print("  /help      - Show this help")
        print("  /quit      - Exit")
        print("\nOr just type a message to chat!")
        print("-" * 50)

    def _handle_command(self, command: str) -> str:
        """Handle a command."""
        parts = command.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd == "help":
            return self._get_help()

        if cmd == "status":
            return self._get_status()

        if cmd == "goals":
            return self._get_goals()

        if cmd == "story":
            return self._request_story(args)

        if cmd == "project":
            return self._get_project()

        if cmd == "mood":
            return self._get_mood()

        if cmd == "energy":
            return self._get_energy()

        if cmd in ("quit", "exit", "q"):
            self._running = False
            return "Goodbye!"

        # Pass to custom command handler
        if self.on_command:
            return self.on_command(command)

        return f"Unknown command: {cmd}. Type /help for available commands."

    def _handle_chat(self, message: str) -> str:
        """Handle a chat message."""
        if self.on_chat:
            return self.on_chat(message)

        return "Chat functionality not connected. BrainBot is running autonomously."

    def _get_help(self) -> str:
        """Get help text."""
        return """
Available Commands:
==================
  /status    - Show BrainBot's current status
  /goals     - Show today's goals
  /story     - Request a bedtime story (optionally: /story <theme>)
  /project   - Show current project info
  /mood      - Show current mood
  /energy    - Show energy level
  /help      - Show this help
  /quit      - Exit terminal

You can also type messages directly to chat with BrainBot.
"""

    def _get_status(self) -> str:
        """Get real status from state manager."""
        now = datetime.now().strftime("%H:%M:%S")

        if not self.state_manager:
            return f"[{now}] Status unavailable - not connected to daemon"

        state = self.state_manager.get_state()

        # Get schedule info if available
        phase_info = ""
        next_event_info = ""
        if self.schedule_manager:
            phase = self.schedule_manager.get_current_phase()
            phase_info = f"Phase:   {phase.value if phase else 'unknown'}"

            next_event = self.schedule_manager.get_time_until_next_event()
            if next_event:
                event_name, time_until = next_event
                next_event_info = f"Next:    {event_name} in {time_until}"

        # Get brain stats if available
        brain_info = ""
        if self.brain:
            stats = self.brain.get_memory_stats()
            brain_info = f"""
Brain Memory:
  Active:   {stats['active_memories']} ({stats['active_size_kb']:.1f} KB)
  Archived: {stats['archived_memories']} ({stats['archived_size_kb']:.1f} KB)
  Total:    {stats['total_memories']} memories"""

        brainbot_header = f"🧠 {rainbow_text('BrainBot')} Status at {now}"
        return f"""
{brainbot_header}
========================
Status:  {state.status.value}
Mood:    {state.mood.value}
Energy:  {state.energy:.0%}
{phase_info}

Current Activity: {state.current_activity or 'Idle'}
{next_event_info}

Goals today:      {len(state.daily_goals)}
Stories written:  {state.stories_written_today}
{brain_info}
"""

    def _get_goals(self) -> str:
        """Get real goals from memory store or state manager."""
        # Try memory store first
        if self.memory_store:
            goals = self.memory_store.get_todays_goals()
            if goals:
                lines = ["Today's Goals", "============="]
                completed = 0
                for goal in goals:
                    status = "x" if goal.get("status") == "completed" else " "
                    if goal.get("status") == "completed":
                        completed += 1
                    lines.append(f"[{status}] {goal['description']}")
                lines.append(f"\nProgress: {completed}/{len(goals)} completed")
                return "\n".join(lines)

        # Fall back to state manager
        if self.state_manager:
            pending_goals = self.state_manager.get_pending_goals()
            if pending_goals:
                lines = ["Today's Goals", "============="]
                for goal in pending_goals:
                    status = "x" if goal.completed else " "
                    lines.append(f"[{status}] {goal.description}")
                return "\n".join(lines)

        return """
Today's Goals
=============
No goals set for today.

Use the daemon's activity selection to create goals,
or wait for the morning routine.
"""

    def _request_story(self, theme: str = "") -> str:
        """Request a bedtime story."""
        if theme:
            # If there's a chat handler, use it to request a story
            if self.on_chat:
                return self.on_chat(f"Write me a bedtime story about: {theme}")

            return f"Story about '{theme}' requested. Check back at bedtime!"

        # Check for today's story
        if self.memory_store:
            story = self.memory_store.get_todays_story()
            if story:
                return f"""
Tonight's Story: {story['title']}
{'=' * (len(story['title']) + 17)}

{story['content']}
"""

        return """
No story written yet today.

Themes available:
- Adventure
- Friendship
- Discovery
- Nature

Use: /story <theme> to request a specific story theme!
"""

    def _get_project(self) -> str:
        """Get current project info from state manager."""
        if self.state_manager:
            state = self.state_manager.get_state()
            if state.current_project:
                proj = state.current_project
                progress_bar = "█" * int(proj.progress * 20) + "░" * (20 - int(proj.progress * 20))
                return f"""
Current Project: {proj.name}
{'=' * (len(proj.name) + 17)}

Description: {proj.description or 'No description'}
Status:      {proj.status}
Progress:    [{progress_bar}] {proj.progress:.0%}
Started:     {proj.started_at.strftime('%Y-%m-%d %H:%M') if proj.started_at else 'Not started'}
"""

        # Check for next project idea
        if self.memory_store:
            next_idea = self.memory_store.get_next_project_idea()
            if next_idea:
                return f"""
Current Project: (None active)

Next in queue:
  {next_idea['title']}
  {next_idea.get('description', '')[:100]}...
"""

        return """
Current Project: (None)

No project currently in progress.
BrainBot will select a new project from the ideas backlog.
"""

    def _get_mood(self) -> str:
        """Get current mood."""
        if self.state_manager:
            state = self.state_manager.get_state()
            mood = state.mood.value

            # Add emoji based on mood
            mood_emoji = {
                "content": "😊",
                "excited": "🎉",
                "focused": "🎯",
                "tired": "😴",
                "curious": "🤔",
            }.get(mood, "")

            return f"Current mood: {mood} {mood_emoji}"

        return "Mood unavailable - not connected to daemon"

    def _get_energy(self) -> str:
        """Get current energy level."""
        if self.state_manager:
            state = self.state_manager.get_state()
            energy = state.energy
            bar = "█" * int(energy * 20) + "░" * (20 - int(energy * 20))
            return f"Energy: [{bar}] {energy:.0%}"

        return "Energy unavailable - not connected to daemon"


def run_interactive_terminal():
    """Run the terminal interface standalone (for testing)."""
    def echo_command(cmd: str) -> str:
        return f"Command received: {cmd}"

    def echo_chat(msg: str) -> str:
        return f"You said: {msg}\n(BrainBot is running in standalone mode)"

    terminal = TerminalInterface(
        on_command=echo_command,
        on_chat=echo_chat,
    )

    try:
        terminal.start()
        # Keep main thread alive
        while terminal._running:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nGoodbye!")
    finally:
        terminal.stop()


if __name__ == "__main__":
    run_interactive_terminal()
