"""LED/NeoPixel controller for mood lighting."""

import logging
import time
import threading
from typing import Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)

# Try to import NeoPixel library
try:
    import board
    import neopixel
    NEOPIXEL_AVAILABLE = True
except ImportError:
    NEOPIXEL_AVAILABLE = False


class LEDPattern(str, Enum):
    """Available LED patterns."""
    SOLID = "solid"
    BREATHE = "breathe"
    PULSE = "pulse"
    RAINBOW = "rainbow"
    CHASE = "chase"
    SPARKLE = "sparkle"


# Predefined colors
COLORS = {
    "red": (255, 0, 0),
    "green": (0, 255, 0),
    "blue": (0, 0, 255),
    "yellow": (255, 255, 0),
    "orange": (255, 165, 0),
    "purple": (128, 0, 128),
    "cyan": (0, 255, 255),
    "white": (255, 255, 255),
    "warm_white": (255, 200, 150),
    "gold": (255, 215, 0),
    "pink": (255, 105, 180),
    "dim_blue": (20, 20, 80),
    "dim_green": (20, 80, 20),
}


class LEDController:
    """
    Controller for NeoPixel LED strip.

    Provides mood-based lighting patterns for BrainBot.
    """

    DEFAULT_PIN = 18  # GPIO18 (PWM)
    DEFAULT_NUM_PIXELS = 8
    DEFAULT_BRIGHTNESS = 0.5

    def __init__(
        self,
        pin: int = DEFAULT_PIN,
        num_pixels: int = DEFAULT_NUM_PIXELS,
        brightness: float = DEFAULT_BRIGHTNESS,
    ):
        """
        Initialize LED controller.

        Args:
            pin: GPIO pin for data
            num_pixels: Number of LEDs in strip
            brightness: Default brightness (0.0-1.0)
        """
        self.pin = pin
        self.num_pixels = num_pixels
        self.brightness = brightness

        self._pixels: Optional["neopixel.NeoPixel"] = None
        self._animation_thread: Optional[threading.Thread] = None
        self._stop_animation = threading.Event()
        self._current_pattern = LEDPattern.SOLID
        self._current_color = COLORS["white"]
        self._current_speed = 1.0

        if NEOPIXEL_AVAILABLE:
            self._initialize()
        else:
            logger.warning("NeoPixel library not available (simulation mode)")

    def _initialize(self) -> bool:
        """Initialize hardware."""
        try:
            # Get the correct GPIO pin
            gpio_pin = getattr(board, f"D{self.pin}", None)
            if gpio_pin is None:
                logger.error(f"Invalid GPIO pin: {self.pin}")
                return False

            self._pixels = neopixel.NeoPixel(
                gpio_pin,
                self.num_pixels,
                brightness=self.brightness,
                auto_write=False,
            )
            logger.info(f"LED controller initialized with {self.num_pixels} pixels")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize LED controller: {e}")
            return False

    def set_pattern(
        self,
        pattern: str,
        color: str = "white",
        speed: float = 1.0,
    ) -> None:
        """
        Set LED pattern and color.

        Args:
            pattern: Pattern name (solid, breathe, pulse, rainbow, chase)
            color: Color name or 'rainbow'
            speed: Animation speed (0.1-5.0)
        """
        # Stop any existing animation
        self._stop_animation.set()
        if self._animation_thread and self._animation_thread.is_alive():
            self._animation_thread.join(timeout=1.0)

        # Parse color
        if color == "rainbow":
            self._current_color = None
        elif color in COLORS:
            self._current_color = COLORS[color]
        else:
            # Try to parse hex color
            try:
                if color.startswith("#"):
                    color = color[1:]
                self._current_color = tuple(int(color[i:i+2], 16) for i in (0, 2, 4))
            except Exception:
                self._current_color = COLORS["white"]

        self._current_speed = max(0.1, min(5.0, speed))
        self._current_pattern = LEDPattern(pattern.lower()) if pattern.lower() in [p.value for p in LEDPattern] else LEDPattern.SOLID

        logger.debug(f"Setting LED pattern: {pattern}, color: {color}, speed: {speed}")

        # Start animation if not solid
        if self._current_pattern != LEDPattern.SOLID:
            self._stop_animation.clear()
            self._animation_thread = threading.Thread(
                target=self._run_animation,
                daemon=True,
            )
            self._animation_thread.start()
        else:
            # Just set solid color
            self._set_all_pixels(self._current_color or COLORS["white"])

    def _run_animation(self) -> None:
        """Run the current animation pattern."""
        while not self._stop_animation.is_set():
            try:
                if self._current_pattern == LEDPattern.BREATHE:
                    self._animate_breathe()
                elif self._current_pattern == LEDPattern.PULSE:
                    self._animate_pulse()
                elif self._current_pattern == LEDPattern.RAINBOW:
                    self._animate_rainbow()
                elif self._current_pattern == LEDPattern.CHASE:
                    self._animate_chase()
                elif self._current_pattern == LEDPattern.SPARKLE:
                    self._animate_sparkle()
            except Exception as e:
                logger.error(f"Animation error: {e}")
                break

    def _animate_breathe(self) -> None:
        """Smooth breathing animation."""
        import math
        color = self._current_color or COLORS["white"]
        step = 0

        while not self._stop_animation.is_set():
            # Sine wave for smooth breathing
            brightness = (math.sin(step * 0.1 * self._current_speed) + 1) / 2
            brightness = max(0.1, brightness)  # Keep minimum brightness

            dimmed = tuple(int(c * brightness) for c in color)
            self._set_all_pixels(dimmed)

            step += 1
            time.sleep(0.05)

    def _animate_pulse(self) -> None:
        """Quick pulsing animation."""
        color = self._current_color or COLORS["white"]

        while not self._stop_animation.is_set():
            # Fade up
            for i in range(10):
                brightness = i / 10
                dimmed = tuple(int(c * brightness) for c in color)
                self._set_all_pixels(dimmed)
                time.sleep(0.02 / self._current_speed)

            # Hold
            self._set_all_pixels(color)
            time.sleep(0.1 / self._current_speed)

            # Fade down
            for i in range(10, 0, -1):
                brightness = i / 10
                dimmed = tuple(int(c * brightness) for c in color)
                self._set_all_pixels(dimmed)
                time.sleep(0.02 / self._current_speed)

            time.sleep(0.1 / self._current_speed)

    def _animate_rainbow(self) -> None:
        """Rainbow color cycle."""
        step = 0

        while not self._stop_animation.is_set():
            for i in range(self.num_pixels):
                pixel_index = (i * 256 // self.num_pixels + step) % 256
                self._set_pixel(i, self._wheel(pixel_index))

            self._show()
            step = (step + int(2 * self._current_speed)) % 256
            time.sleep(0.02)

    def _animate_chase(self) -> None:
        """Chasing light animation."""
        color = self._current_color or COLORS["white"]
        position = 0

        while not self._stop_animation.is_set():
            self._clear_pixels()

            # Light up 2-3 consecutive pixels
            for offset in range(3):
                idx = (position + offset) % self.num_pixels
                brightness = 1.0 - (offset * 0.3)
                dimmed = tuple(int(c * brightness) for c in color)
                self._set_pixel(idx, dimmed)

            self._show()
            position = (position + 1) % self.num_pixels
            time.sleep(0.1 / self._current_speed)

    def _animate_sparkle(self) -> None:
        """Random sparkle effect."""
        import random
        color = self._current_color or COLORS["white"]

        while not self._stop_animation.is_set():
            self._clear_pixels()

            # Random sparkles
            num_sparkles = max(1, self.num_pixels // 3)
            for _ in range(num_sparkles):
                idx = random.randint(0, self.num_pixels - 1)
                brightness = random.uniform(0.5, 1.0)
                dimmed = tuple(int(c * brightness) for c in color)
                self._set_pixel(idx, dimmed)

            self._show()
            time.sleep(0.05 / self._current_speed)

    def _wheel(self, pos: int) -> Tuple[int, int, int]:
        """Generate rainbow colors across 0-255 positions."""
        if pos < 85:
            return (pos * 3, 255 - pos * 3, 0)
        elif pos < 170:
            pos -= 85
            return (255 - pos * 3, 0, pos * 3)
        else:
            pos -= 170
            return (0, pos * 3, 255 - pos * 3)

    def _set_all_pixels(self, color: Tuple[int, int, int]) -> None:
        """Set all pixels to same color."""
        if self._pixels:
            self._pixels.fill(color)
            self._pixels.show()
        else:
            logger.debug(f"LED (sim): all pixels -> {color}")

    def _set_pixel(self, index: int, color: Tuple[int, int, int]) -> None:
        """Set a single pixel."""
        if self._pixels and 0 <= index < self.num_pixels:
            self._pixels[index] = color

    def _clear_pixels(self) -> None:
        """Clear all pixels (set to black)."""
        if self._pixels:
            self._pixels.fill((0, 0, 0))

    def _show(self) -> None:
        """Update the LED strip."""
        if self._pixels:
            self._pixels.show()

    def off(self) -> None:
        """Turn off all LEDs."""
        self._stop_animation.set()
        if self._animation_thread and self._animation_thread.is_alive():
            self._animation_thread.join(timeout=1.0)

        self._set_all_pixels((0, 0, 0))
        logger.debug("LEDs turned off")

    def set_brightness(self, brightness: float) -> None:
        """Set overall brightness."""
        self.brightness = max(0.0, min(1.0, brightness))
        if self._pixels:
            self._pixels.brightness = self.brightness
            self._pixels.show()

    def is_available(self) -> bool:
        """Check if LEDs are available."""
        return self._pixels is not None
