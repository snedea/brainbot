"""
Display Loop for BrainBot LCD screens.

Provides a cycling display that rotates through different states:
1. Current Task - What BrainBot is currently working on
2. Network Status - Online nodes and pending tasks
3. BrainBot Banner - Rainbow ASCII art logo
4. Recent Memory - Last thing learned or created

Works with both the 1-inch OLED and 5-inch DSI displays.
"""

import logging
import threading
import time
from datetime import datetime
from enum import Enum
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Try to import PIL for image generation
try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


class DisplayState(str, Enum):
    """States the display can show."""
    BANNER = "banner"
    STATUS = "status"
    TASK = "task"
    MEMORY = "memory"
    NETWORK = "network"
    CUSTOM = "custom"


# Rainbow colors for banner
RAINBOW_COLORS = [
    (255, 0, 0),      # Red
    (255, 127, 0),    # Orange
    (255, 255, 0),    # Yellow
    (0, 255, 0),      # Green
    (0, 0, 255),      # Blue
    (75, 0, 130),     # Indigo
    (148, 0, 211),    # Violet
]

# ASCII art banner for BrainBot
BRAINBOT_BANNER = [
    " ____  ____      _    ___ _   _ ",
    "| __ )|  _ \\    / \\  |_ _| \\ | |",
    "|  _ \\| |_) |  / _ \\  | ||  \\| |",
    "| |_) |  _ <  / ___ \\ | || |\\  |",
    "|____/|_| \\_\\/_/   \\_\\___|_| \\_|",
    "         B O T                  ",
]

# Compact banner for 1-inch display
BRAINBOT_BANNER_SMALL = [
    "BRAIN",
    " BOT ",
]


class DisplayLoop:
    """
    Manages cycling display content for BrainBot's LCD screens.

    Provides visual feedback about BrainBot's current state, network
    status, and activity through rotating display states.
    """

    DEFAULT_CYCLE_INTERVAL = 5  # Seconds between state changes

    def __init__(
        self,
        lcd_1inch=None,
        lcd_5inch=None,
        cycle_interval: int = DEFAULT_CYCLE_INTERVAL,
        get_current_task: Optional[Callable[[], Optional[str]]] = None,
        get_network_status: Optional[Callable[[], dict]] = None,
        get_recent_memory: Optional[Callable[[], Optional[str]]] = None,
        get_mood: Optional[Callable[[], str]] = None,
    ):
        """
        Initialize the display loop.

        Args:
            lcd_1inch: LCD1Inch instance (optional)
            lcd_5inch: 5-inch display controller (optional)
            cycle_interval: Seconds between state changes
            get_current_task: Callback to get current task description
            get_network_status: Callback to get network status dict
            get_recent_memory: Callback to get recent memory summary
            get_mood: Callback to get current mood
        """
        self.lcd_1inch = lcd_1inch
        self.lcd_5inch = lcd_5inch
        self.cycle_interval = cycle_interval

        # Callbacks for dynamic data
        self._get_current_task = get_current_task
        self._get_network_status = get_network_status
        self._get_recent_memory = get_recent_memory
        self._get_mood = get_mood

        # State machine
        self._states = [
            DisplayState.BANNER,
            DisplayState.STATUS,
            DisplayState.TASK,
            DisplayState.NETWORK,
            DisplayState.MEMORY,
        ]
        self._current_state_idx = 0
        self._current_state = DisplayState.BANNER

        # Threading
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Override state (for temporary messages)
        self._override_state: Optional[DisplayState] = None
        self._override_content: Optional[str] = None
        self._override_until: Optional[float] = None

        # Font loading for PIL
        self._font: Optional["ImageFont.FreeTypeFont"] = None
        self._font_small: Optional["ImageFont.FreeTypeFont"] = None
        self._font_large: Optional["ImageFont.FreeTypeFont"] = None
        self._load_fonts()

    def _load_fonts(self) -> None:
        """Load fonts for display rendering."""
        if not PIL_AVAILABLE:
            return

        try:
            font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
            self._font = ImageFont.truetype(font_path, 12)
            self._font_small = ImageFont.truetype(font_path, 10)
            self._font_large = ImageFont.truetype(font_path, 16)
        except Exception:
            self._font = ImageFont.load_default()
            self._font_small = ImageFont.load_default()
            self._font_large = ImageFont.load_default()

    def start(self) -> None:
        """Start the display loop."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("Display loop started")

    def stop(self) -> None:
        """Stop the display loop."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        logger.info("Display loop stopped")

    def _loop(self) -> None:
        """Main display loop."""
        while self._running:
            try:
                # Check for override expiration
                if self._override_until and time.time() > self._override_until:
                    self._override_state = None
                    self._override_content = None
                    self._override_until = None

                # Determine what to show
                if self._override_state:
                    self._show_override()
                else:
                    self._show_current_state()

                # Wait for next cycle
                time.sleep(self.cycle_interval)

                # Advance to next state (if no override)
                if not self._override_state:
                    self._advance_state()

            except Exception as e:
                logger.error(f"Display loop error: {e}")
                time.sleep(1)

    def _advance_state(self) -> None:
        """Advance to the next display state."""
        with self._lock:
            self._current_state_idx = (self._current_state_idx + 1) % len(self._states)
            self._current_state = self._states[self._current_state_idx]

    def _show_current_state(self) -> None:
        """Show the current state on displays."""
        state = self._current_state

        if state == DisplayState.BANNER:
            self._show_banner()
        elif state == DisplayState.STATUS:
            self._show_status()
        elif state == DisplayState.TASK:
            self._show_task()
        elif state == DisplayState.NETWORK:
            self._show_network()
        elif state == DisplayState.MEMORY:
            self._show_memory()

    def _show_override(self) -> None:
        """Show override content."""
        if self._override_content:
            if self.lcd_1inch:
                lines = self._override_content.split("\n")
                self.lcd_1inch.display_text(
                    lines[0] if len(lines) > 0 else "",
                    lines[1] if len(lines) > 1 else "",
                    lines[2] if len(lines) > 2 else "",
                )

    # ========== Display States ==========

    def _show_banner(self) -> None:
        """Show the BrainBot banner."""
        if self.lcd_1inch:
            # Use compact banner for small display
            self.lcd_1inch.display_text(
                "BRAINBOT",
                self._get_time_string(),
                self._get_mood_string(),
            )

        if self.lcd_5inch:
            # Render rainbow banner for larger display
            self._render_rainbow_banner_5inch()

    def _show_status(self) -> None:
        """Show current status."""
        mood = self._get_mood() if self._get_mood else "content"
        time_str = self._get_time_string()

        if self.lcd_1inch:
            self.lcd_1inch.display_text(
                "BrainBot",
                f"Mood: {mood}",
                time_str,
            )

    def _show_task(self) -> None:
        """Show current task."""
        task = self._get_current_task() if self._get_current_task else None

        if self.lcd_1inch:
            if task:
                # Truncate task description for display
                task_short = task[:18] + "..." if len(task) > 18 else task
                self.lcd_1inch.display_text(
                    "Working on:",
                    task_short,
                    "",
                )
            else:
                self.lcd_1inch.display_text(
                    "Status:",
                    "Idle",
                    "Ready to help!",
                )

    def _show_network(self) -> None:
        """Show network status."""
        status = self._get_network_status() if self._get_network_status else {}

        nodes_online = status.get("online_nodes", 0)
        tasks_pending = status.get("pending_tasks", 0)

        if self.lcd_1inch:
            self.lcd_1inch.display_text(
                "Network:",
                f"{nodes_online} nodes online",
                f"{tasks_pending} tasks pending",
            )

    def _show_memory(self) -> None:
        """Show recent memory."""
        memory = self._get_recent_memory() if self._get_recent_memory else None

        if self.lcd_1inch:
            if memory:
                # Truncate memory for display
                mem_short = memory[:35] + "..." if len(memory) > 35 else memory
                line1 = mem_short[:18]
                line2 = mem_short[18:36] if len(mem_short) > 18 else ""
                self.lcd_1inch.display_text(
                    "Recent:",
                    line1,
                    line2,
                )
            else:
                self.lcd_1inch.display_text(
                    "Memory:",
                    "No recent",
                    "memories",
                )

    def _render_rainbow_banner_5inch(self) -> None:
        """Render rainbow banner on 5-inch display."""
        if not self.lcd_5inch or not PIL_AVAILABLE:
            return

        try:
            # Create image for 5-inch display (800x480)
            width, height = 800, 480
            image = Image.new("RGB", (width, height), (0, 0, 0))
            draw = ImageDraw.Draw(image)

            # Load a larger font for the banner
            try:
                banner_font = ImageFont.truetype(
                    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
                    28
                )
            except Exception:
                banner_font = self._font_large

            # Calculate banner position (centered)
            banner_height = len(BRAINBOT_BANNER) * 32
            start_y = (height - banner_height) // 2

            # Draw each line with rainbow colors
            for i, line in enumerate(BRAINBOT_BANNER):
                y = start_y + (i * 32)

                # Draw each character with its own color
                x = (width - len(line) * 17) // 2  # Center horizontally
                for j, char in enumerate(line):
                    if char != " ":
                        color_idx = (i + j) % len(RAINBOW_COLORS)
                        color = RAINBOW_COLORS[color_idx]
                        draw.text((x, y), char, font=banner_font, fill=color)
                    x += 17  # Character width

            # Add timestamp at bottom
            time_str = datetime.now().strftime("%H:%M:%S")
            draw.text(
                (width // 2 - 50, height - 40),
                time_str,
                font=self._font_large,
                fill=(100, 100, 100),
            )

            # Display the image (implementation depends on lcd_5inch interface)
            if hasattr(self.lcd_5inch, "display_image"):
                self.lcd_5inch.display_image(image)
            elif hasattr(self.lcd_5inch, "show"):
                self.lcd_5inch.show(image)

        except Exception as e:
            logger.error(f"Failed to render rainbow banner: {e}")

    # ========== Helper Methods ==========

    def _get_time_string(self) -> str:
        """Get formatted time string."""
        return datetime.now().strftime("%H:%M")

    def _get_mood_string(self) -> str:
        """Get mood string."""
        if self._get_mood:
            return self._get_mood()
        return "content"

    # ========== Public API ==========

    def show_message(
        self,
        message: str,
        duration: float = 5.0,
    ) -> None:
        """
        Show a temporary message.

        Args:
            message: Message to display
            duration: How long to show (seconds)
        """
        with self._lock:
            self._override_state = DisplayState.CUSTOM
            self._override_content = message
            self._override_until = time.time() + duration

    def show_thinking(self, topic: Optional[str] = None) -> None:
        """
        Show thinking state.

        Args:
            topic: What we're thinking about
        """
        if self.lcd_1inch:
            self.lcd_1inch.display_thinking()

        msg = "Thinking..."
        if topic:
            msg = f"Thinking:\n{topic[:35]}"
        self.show_message(msg, duration=30)

    def show_speaking(self) -> None:
        """Show speaking state."""
        if self.lcd_1inch:
            self.lcd_1inch.display_speaking()

    def show_chat(self, source: str, message: str) -> None:
        """
        Show incoming chat message.

        Args:
            source: Message source (terminal, slack, email)
            message: Message preview
        """
        if self.lcd_1inch:
            self.lcd_1inch.display_chat(source, message)

        preview = message[:40] + "..." if len(message) > 40 else message
        self.show_message(f"[{source}]\n{preview}", duration=5)

    def show_task_progress(
        self,
        task_name: str,
        progress: float,
    ) -> None:
        """
        Show task progress.

        Args:
            task_name: Name of the task
            progress: Progress 0.0 to 1.0
        """
        if self.lcd_1inch:
            self.lcd_1inch.show_progress(task_name, progress)

    def clear_override(self) -> None:
        """Clear any override and return to normal cycling."""
        with self._lock:
            self._override_state = None
            self._override_content = None
            self._override_until = None

    def set_cycle_interval(self, seconds: int) -> None:
        """Set the cycle interval."""
        self.cycle_interval = max(1, seconds)

    def skip_to_state(self, state: DisplayState) -> None:
        """
        Skip to a specific state.

        Args:
            state: State to skip to
        """
        with self._lock:
            try:
                idx = self._states.index(state)
                self._current_state_idx = idx
                self._current_state = state
            except ValueError:
                pass


# Singleton instance
_instance: Optional[DisplayLoop] = None


def get_display_loop(
    lcd_1inch=None,
    lcd_5inch=None,
    **kwargs,
) -> DisplayLoop:
    """
    Get or create the display loop singleton.

    Args:
        lcd_1inch: LCD1Inch instance
        lcd_5inch: 5-inch display instance
        **kwargs: Additional arguments for DisplayLoop

    Returns:
        DisplayLoop instance
    """
    global _instance
    if _instance is None:
        _instance = DisplayLoop(
            lcd_1inch=lcd_1inch,
            lcd_5inch=lcd_5inch,
            **kwargs,
        )
    return _instance
