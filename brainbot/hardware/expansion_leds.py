"""
Freenove Expansion Board LED Controller for BrainBot
=====================================================

Controls the 4 RGB LEDs on the Freenove case via I2C.
Provides expressive mood lighting so BrainBot can communicate through light.

States:
- SLEEPING: Very dim or off, BrainBot is resting
- IDLE: Calm breathing, waiting for interaction
- LISTENING: Bright blue, paying attention
- THINKING: Rainbow cycling, processing
- SPEAKING: Green waves, talking to user
- HAPPY: Bright warm colors, cheerful
- EXCITED: Fast rainbow/sparkle, very energetic
- ATTENTION: Flashing to get user's attention
- ERROR: Red alert
- SUCCESS: Green confirmation
"""

import sys
import time
import threading
import logging
from typing import Tuple, Optional
from enum import Enum

# Add Freenove code path before importing
FREENOVE_PATH = '/home/brainbot/homelab/freenove/Code'
if FREENOVE_PATH not in sys.path:
    sys.path.insert(0, FREENOVE_PATH)

logger = logging.getLogger(__name__)

# Try to import expansion board
EXPANSION_AVAILABLE = False
Expansion = None

try:
    from expansion import Expansion
    EXPANSION_AVAILABLE = True
except ImportError as e:
    # Try direct import as fallback
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("expansion", f"{FREENOVE_PATH}/expansion.py")
        expansion_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(expansion_module)
        Expansion = expansion_module.Expansion
        EXPANSION_AVAILABLE = True
    except Exception as e2:
        logger.warning(f"Freenove expansion board not available: {e2}")


class BrainBotMood(str, Enum):
    """BrainBot's emotional/activity states expressed through LEDs."""
    OFF = "off"
    SLEEPING = "sleeping"
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    HAPPY = "happy"
    EXCITED = "excited"
    CALM = "calm"
    ATTENTION = "attention"
    ERROR = "error"
    SUCCESS = "success"


# Color definitions (R, G, B)
COLORS = {
    'off': (0, 0, 0),
    'white': (255, 255, 255),
    'warm_white': (255, 200, 150),
    'red': (255, 0, 0),
    'green': (0, 255, 0),
    'blue': (0, 0, 255),
    'cyan': (0, 255, 255),
    'yellow': (255, 200, 0),
    'orange': (255, 100, 0),
    'purple': (128, 0, 255),
    'pink': (255, 80, 120),
    'gold': (255, 180, 0),

    # Dim versions for sleep/calm
    'dim_purple': (20, 0, 40),
    'dim_blue': (0, 0, 30),
    'dim_cyan': (0, 20, 20),
}


class ExpansionLEDs:
    """
    LED controller for BrainBot using Freenove expansion board.

    Provides mood-based lighting that lets BrainBot express itself
    and communicate with humans through light patterns.
    """

    def __init__(self):
        """Initialize the LED controller."""
        self.expansion: Optional[Expansion] = None
        self._animation_thread: Optional[threading.Thread] = None
        self._stop_animation = threading.Event()
        self._current_mood = BrainBotMood.OFF
        self._brightness = 1.0  # Global brightness multiplier (0.0-1.0)

        if EXPANSION_AVAILABLE:
            try:
                self.expansion = Expansion()
                # Start in RGB mode for direct control
                self.expansion.set_led_mode(1)
                logger.info("Expansion board LED controller initialized")
            except Exception as e:
                logger.error(f"Failed to initialize expansion board: {e}")
                self.expansion = None

    def _scale_color(self, r: int, g: int, b: int) -> Tuple[int, int, int]:
        """Apply brightness scaling to a color."""
        return (
            int(r * self._brightness),
            int(g * self._brightness),
            int(b * self._brightness)
        )

    def _set_all(self, r: int, g: int, b: int):
        """Set all LEDs to a color."""
        if self.expansion:
            r, g, b = self._scale_color(r, g, b)
            self.expansion.set_led_mode(1)
            self.expansion.set_all_led_color(r, g, b)

    def _set_led(self, led_id: int, r: int, g: int, b: int):
        """Set a specific LED (0-3)."""
        if self.expansion and 0 <= led_id <= 3:
            r, g, b = self._scale_color(r, g, b)
            self.expansion.set_led_color(led_id, r, g, b)

    def _stop_current_animation(self):
        """Stop any running animation."""
        self._stop_animation.set()
        if self._animation_thread and self._animation_thread.is_alive():
            self._animation_thread.join(timeout=1.0)
        self._stop_animation.clear()

    def _start_animation(self, func):
        """Start an animation in a background thread."""
        self._stop_current_animation()
        self._animation_thread = threading.Thread(target=func, daemon=True)
        self._animation_thread.start()

    # ========== Public API ==========

    def set_brightness(self, level: float):
        """Set global brightness (0.0 to 1.0)."""
        self._brightness = max(0.0, min(1.0, level))

    def set_mood(self, mood: str):
        """
        Set BrainBot's mood/state.

        Args:
            mood: One of: off, sleeping, idle, listening, thinking,
                  speaking, happy, excited, calm, attention, error, success
        """
        try:
            mood_enum = BrainBotMood(mood.lower())
        except ValueError:
            logger.warning(f"Unknown mood: {mood}")
            return

        self._current_mood = mood_enum

        # Map moods to their display functions
        mood_handlers = {
            BrainBotMood.OFF: self.off,
            BrainBotMood.SLEEPING: self.sleeping,
            BrainBotMood.IDLE: self.idle,
            BrainBotMood.LISTENING: self.listening,
            BrainBotMood.THINKING: self.thinking,
            BrainBotMood.SPEAKING: self.speaking,
            BrainBotMood.HAPPY: self.happy,
            BrainBotMood.EXCITED: self.excited,
            BrainBotMood.CALM: self.calm,
            BrainBotMood.ATTENTION: self.attention,
            BrainBotMood.ERROR: self.error,
            BrainBotMood.SUCCESS: self.success,
        }

        handler = mood_handlers.get(mood_enum)
        if handler:
            handler()

    def get_mood(self) -> str:
        """Get current mood."""
        return self._current_mood.value

    # ========== Mood States ==========

    def off(self):
        """Turn off all LEDs."""
        self._stop_current_animation()
        self._set_all(0, 0, 0)
        self._current_mood = BrainBotMood.OFF

    def sleeping(self):
        """Very dim, slow breathing - BrainBot is resting."""
        self._current_mood = BrainBotMood.SLEEPING

        def _animate():
            if self.expansion:
                self.expansion.set_all_led_color(15, 0, 30)  # Very dim purple
                self.expansion.set_led_mode(3)  # Hardware breathing

        self._stop_current_animation()
        _animate()

    def idle(self):
        """Calm breathing cyan - waiting for interaction."""
        self._current_mood = BrainBotMood.IDLE

        def _animate():
            if self.expansion:
                self.expansion.set_all_led_color(0, 80, 100)
                self.expansion.set_led_mode(3)  # Hardware breathing

        self._stop_current_animation()
        _animate()

    def listening(self):
        """Bright solid blue - paying attention to user."""
        self._stop_current_animation()
        self._current_mood = BrainBotMood.LISTENING
        self._set_all(0, 100, 255)

    def thinking(self):
        """Rainbow cycling - processing/generating response."""
        self._current_mood = BrainBotMood.THINKING

        def _animate():
            if self.expansion:
                self.expansion.set_led_mode(4)  # Hardware rainbow

        self._stop_current_animation()
        _animate()

    def speaking(self):
        """Green wave animation - BrainBot is talking."""
        self._current_mood = BrainBotMood.SPEAKING

        def _animate():
            if not self.expansion:
                return
            self.expansion.set_led_mode(1)
            offset = 0
            while not self._stop_animation.is_set():
                # Wave pattern across the 4 LEDs
                for i in range(4):
                    # Create wave effect
                    wave = [255, 180, 100, 50]
                    brightness = wave[(i + offset) % 4]
                    self.expansion.set_led_color(i, 0, brightness, int(brightness * 0.3))
                offset = (offset + 1) % 4
                time.sleep(0.12)

        self._start_animation(_animate)

    def happy(self):
        """Bright warm colors - cheerful and content."""
        self._current_mood = BrainBotMood.HAPPY

        def _animate():
            if not self.expansion:
                return
            self.expansion.set_led_mode(1)
            colors = [
                (255, 200, 0),   # Gold
                (255, 150, 0),   # Orange
                (255, 100, 50),  # Warm
                (255, 180, 80),  # Peachy
            ]
            while not self._stop_animation.is_set():
                for i, (r, g, b) in enumerate(colors):
                    self.expansion.set_led_color(i, r, g, b)
                # Rotate colors slowly
                colors = colors[1:] + colors[:1]
                time.sleep(0.5)

        self._start_animation(_animate)

    def excited(self):
        """Fast sparkle/rainbow - very energetic!"""
        self._current_mood = BrainBotMood.EXCITED

        def _animate():
            if not self.expansion:
                return
            self.expansion.set_led_mode(1)
            import random
            bright_colors = [
                (255, 0, 0), (0, 255, 0), (0, 0, 255),
                (255, 255, 0), (255, 0, 255), (0, 255, 255),
            ]
            while not self._stop_animation.is_set():
                for i in range(4):
                    r, g, b = random.choice(bright_colors)
                    self.expansion.set_led_color(i, r, g, b)
                time.sleep(0.08)

        self._start_animation(_animate)

    def calm(self):
        """Soft, slow color transitions - peaceful."""
        self._current_mood = BrainBotMood.CALM

        def _animate():
            if self.expansion:
                self.expansion.set_all_led_color(60, 40, 100)  # Soft lavender
                self.expansion.set_led_mode(3)  # Breathing

        self._stop_current_animation()
        _animate()

    def attention(self):
        """Flashing to get user's attention - "Hey! Look at me!" """
        self._current_mood = BrainBotMood.ATTENTION

        def _animate():
            if not self.expansion:
                return
            self.expansion.set_led_mode(1)
            flash_count = 0
            while not self._stop_animation.is_set() and flash_count < 10:
                # Flash cyan
                self.expansion.set_all_led_color(0, 255, 255)
                time.sleep(0.15)
                self.expansion.set_all_led_color(0, 0, 0)
                time.sleep(0.1)
                flash_count += 1
            # End with solid cyan so user knows we want attention
            if not self._stop_animation.is_set():
                self.expansion.set_all_led_color(0, 200, 200)

        self._start_animation(_animate)

    def error(self):
        """Red alert - something went wrong."""
        self._stop_current_animation()
        self._current_mood = BrainBotMood.ERROR
        self._set_all(255, 0, 0)

    def success(self):
        """Green flash then fade - task completed!"""
        self._stop_current_animation()
        self._current_mood = BrainBotMood.SUCCESS

        if not self.expansion:
            return

        self.expansion.set_led_mode(1)
        # Flash green 3 times
        for _ in range(3):
            self.expansion.set_all_led_color(0, 255, 0)
            time.sleep(0.15)
            self.expansion.set_all_led_color(0, 80, 0)
            time.sleep(0.1)
        # End on dim green
        self.expansion.set_all_led_color(0, 60, 0)

    # ========== Quick Actions ==========

    def flash(self, color: str = "cyan", times: int = 2):
        """Quick flash to acknowledge user input."""
        self._stop_current_animation()
        if not self.expansion:
            return

        r, g, b = COLORS.get(color, COLORS['cyan'])
        self.expansion.set_led_mode(1)

        for _ in range(times):
            self.expansion.set_all_led_color(r, g, b)
            time.sleep(0.1)
            self.expansion.set_all_led_color(0, 0, 0)
            time.sleep(0.08)

    def acknowledge(self):
        """Quick cyan flash to show BrainBot heard something."""
        self.flash("cyan", 2)

    def confirm(self):
        """Green flash to confirm an action."""
        self.flash("green", 2)

    def warn(self):
        """Yellow flash for warnings."""
        self.flash("yellow", 3)

    def pulse(self, color: str = "blue", duration: float = 1.0):
        """Single smooth pulse."""
        if not self.expansion:
            return

        r, g, b = COLORS.get(color, COLORS['blue'])
        self.expansion.set_led_mode(1)

        # Fade in
        steps = 20
        for i in range(steps):
            factor = i / steps
            self.expansion.set_all_led_color(
                int(r * factor), int(g * factor), int(b * factor)
            )
            time.sleep(duration / (steps * 2))

        # Fade out
        for i in range(steps, 0, -1):
            factor = i / steps
            self.expansion.set_all_led_color(
                int(r * factor), int(g * factor), int(b * factor)
            )
            time.sleep(duration / (steps * 2))

    # ========== Cleanup ==========

    def cleanup(self):
        """Clean up resources."""
        self._stop_animation.set()
        # Give animation thread time to notice and exit
        if self._animation_thread and self._animation_thread.is_alive():
            self._animation_thread.join(timeout=0.5)

        if self.expansion:
            try:
                self.expansion.set_led_mode(1)
                self.expansion.set_all_led_color(0, 0, 0)
            except:
                pass
            try:
                self.expansion.end()
            except:
                pass
            self.expansion = None

    def __del__(self):
        """Destructor."""
        self.cleanup()


# Singleton instance
_instance: Optional[ExpansionLEDs] = None


def get_leds() -> ExpansionLEDs:
    """Get the singleton LED controller instance."""
    global _instance
    if _instance is None:
        _instance = ExpansionLEDs()
    return _instance


# Demo
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="BrainBot Expansion LEDs")
    parser.add_argument("--mood", type=str, help="Set mood state")
    parser.add_argument("--demo", action="store_true", help="Run demo")
    parser.add_argument("--off", action="store_true", help="Turn off")
    args = parser.parse_args()

    leds = ExpansionLEDs()

    try:
        if args.off:
            leds.off()
            print("LEDs off")

        elif args.mood:
            leds.set_mood(args.mood)
            print(f"Mood set to: {args.mood}")
            input("Press Enter to exit...")

        elif args.demo:
            print("BrainBot LED Mood Demo")
            print("=" * 40)

            moods = [
                ("sleeping", "Sleeping - very dim, resting", 3),
                ("idle", "Idle - calm breathing", 3),
                ("listening", "Listening - bright blue", 2),
                ("thinking", "Thinking - rainbow", 3),
                ("speaking", "Speaking - green waves", 4),
                ("happy", "Happy - warm colors", 3),
                ("excited", "Excited - sparkle!", 3),
                ("calm", "Calm - soft lavender", 3),
                ("attention", "Attention - flash!", 3),
                ("success", "Success - green flash", 2),
                ("error", "Error - red", 2),
                ("idle", "Back to idle", 2),
            ]

            for mood, desc, duration in moods:
                print(f"\n{desc}")
                leds.set_mood(mood)
                time.sleep(duration)

            print("\nDemo complete!")

        else:
            print("Available moods:", ", ".join(m.value for m in BrainBotMood))
            print("\nUsage:")
            print("  --mood <name>  Set a mood")
            print("  --demo         Run demo sequence")
            print("  --off          Turn off LEDs")

    except KeyboardInterrupt:
        print("\nInterrupted")
    finally:
        if args.demo or args.off:
            leds.cleanup()
