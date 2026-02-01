"""
BrainBot Face - Expressive animated face for the 5-inch LCD.

Renders cute, expressive eyes that reflect BrainBot's mood and state.
Inspired by Vector/Cozmo style robot faces.
"""

import logging
import math
import random
import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, Callable, Tuple

try:
    from PIL import Image, ImageDraw
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

logger = logging.getLogger(__name__)

# Display dimensions (5-inch LCD)
DISPLAY_WIDTH = 800
DISPLAY_HEIGHT = 480

# Face colors
BACKGROUND_COLOR = (15, 15, 25)  # Dark blue-black
EYE_COLOR = (100, 200, 255)  # Bright cyan/blue
EYE_HIGHLIGHT = (200, 240, 255)  # Light highlight
PUPIL_COLOR = (20, 60, 100)  # Darker blue for pupil
BLUSH_COLOR = (255, 150, 180, 80)  # Pink blush (with alpha)


class Expression(str, Enum):
    """Face expressions."""
    IDLE = "idle"
    HAPPY = "happy"
    THINKING = "thinking"
    SPEAKING = "speaking"
    SLEEPY = "sleepy"
    SLEEPING = "sleeping"
    SURPRISED = "surprised"
    CURIOUS = "curious"
    SAD = "sad"
    EXCITED = "excited"
    LOVE = "love"
    WINK = "wink"
    BLINK = "blink"


@dataclass
class EyeState:
    """State of a single eye."""
    x: float  # Center X position
    y: float  # Center Y position
    width: float  # Eye width
    height: float  # Eye height (changes for blink/squint)
    pupil_x: float  # Pupil offset from center (-1 to 1)
    pupil_y: float  # Pupil offset from center (-1 to 1)
    roundness: float  # Corner roundness (0-1)


@dataclass
class FaceState:
    """Complete face state."""
    left_eye: EyeState
    right_eye: EyeState
    expression: Expression
    blush: float  # 0-1 blush intensity
    mouth_open: float  # 0-1 for speaking animation


class FaceRenderer:
    """Renders BrainBot's face to an image."""

    # Base eye dimensions
    EYE_WIDTH = 140
    EYE_HEIGHT = 160
    EYE_SPACING = 180  # Distance between eye centers
    EYE_Y = 200  # Vertical position

    def __init__(self):
        if not PIL_AVAILABLE:
            raise ImportError("PIL/Pillow required for face rendering")

        # Default face state
        self.state = self._create_default_state()

    def _create_default_state(self) -> FaceState:
        """Create default face state."""
        center_x = DISPLAY_WIDTH // 2

        left_eye = EyeState(
            x=center_x - self.EYE_SPACING // 2,
            y=self.EYE_Y,
            width=self.EYE_WIDTH,
            height=self.EYE_HEIGHT,
            pupil_x=0,
            pupil_y=0,
            roundness=0.4,
        )

        right_eye = EyeState(
            x=center_x + self.EYE_SPACING // 2,
            y=self.EYE_Y,
            width=self.EYE_WIDTH,
            height=self.EYE_HEIGHT,
            pupil_x=0,
            pupil_y=0,
            roundness=0.4,
        )

        return FaceState(
            left_eye=left_eye,
            right_eye=right_eye,
            expression=Expression.IDLE,
            blush=0,
            mouth_open=0,
        )

    def set_expression(self, expression: Expression) -> None:
        """Set the face expression."""
        self.state.expression = expression
        self._apply_expression(expression)

    def _apply_expression(self, expression: Expression) -> None:
        """Apply expression to eye states."""
        # Reset to defaults first
        for eye in [self.state.left_eye, self.state.right_eye]:
            eye.width = self.EYE_WIDTH
            eye.height = self.EYE_HEIGHT
            eye.roundness = 0.4
            eye.pupil_x = 0
            eye.pupil_y = 0
        self.state.blush = 0
        self.state.mouth_open = 0

        if expression == Expression.HAPPY:
            # Squinted happy eyes (like ^_^)
            for eye in [self.state.left_eye, self.state.right_eye]:
                eye.height = self.EYE_HEIGHT * 0.4
                eye.roundness = 0.8
            self.state.blush = 0.5

        elif expression == Expression.THINKING:
            # Looking up and to the side
            for eye in [self.state.left_eye, self.state.right_eye]:
                eye.pupil_x = 0.4
                eye.pupil_y = -0.3
                eye.height = self.EYE_HEIGHT * 0.85

        elif expression == Expression.SPEAKING:
            self.state.mouth_open = 0.5

        elif expression == Expression.SLEEPY:
            # Half-closed droopy eyes
            for eye in [self.state.left_eye, self.state.right_eye]:
                eye.height = self.EYE_HEIGHT * 0.35
                eye.pupil_y = 0.2

        elif expression == Expression.SLEEPING:
            # Closed eyes (just lines)
            for eye in [self.state.left_eye, self.state.right_eye]:
                eye.height = self.EYE_HEIGHT * 0.08
                eye.roundness = 0.9

        elif expression == Expression.SURPRISED:
            # Wide eyes
            for eye in [self.state.left_eye, self.state.right_eye]:
                eye.width = self.EYE_WIDTH * 1.2
                eye.height = self.EYE_HEIGHT * 1.3
                eye.roundness = 0.6

        elif expression == Expression.CURIOUS:
            # One eye bigger, looking to side
            self.state.left_eye.width = self.EYE_WIDTH * 1.1
            self.state.left_eye.height = self.EYE_HEIGHT * 1.1
            self.state.right_eye.height = self.EYE_HEIGHT * 0.9
            for eye in [self.state.left_eye, self.state.right_eye]:
                eye.pupil_x = 0.3

        elif expression == Expression.SAD:
            # Droopy sad eyes
            for eye in [self.state.left_eye, self.state.right_eye]:
                eye.height = self.EYE_HEIGHT * 0.7
                eye.pupil_y = 0.3
            # Eyebrows would angle down (simplified)

        elif expression == Expression.EXCITED:
            # Sparkly wide eyes
            for eye in [self.state.left_eye, self.state.right_eye]:
                eye.width = self.EYE_WIDTH * 1.15
                eye.height = self.EYE_HEIGHT * 1.2
            self.state.blush = 0.3

        elif expression == Expression.LOVE:
            # Heart eyes effect via blush and happy squint
            for eye in [self.state.left_eye, self.state.right_eye]:
                eye.height = self.EYE_HEIGHT * 0.5
                eye.roundness = 0.7
            self.state.blush = 0.8

        elif expression == Expression.WINK:
            # Right eye closed
            self.state.right_eye.height = self.EYE_HEIGHT * 0.08
            self.state.right_eye.roundness = 0.9
            self.state.left_eye.height = self.EYE_HEIGHT * 0.6
            self.state.blush = 0.3

        elif expression == Expression.BLINK:
            # Both eyes closed briefly
            for eye in [self.state.left_eye, self.state.right_eye]:
                eye.height = self.EYE_HEIGHT * 0.05

    def look_at(self, x: float, y: float) -> None:
        """Make eyes look at a position (-1 to 1 range)."""
        x = max(-1, min(1, x))
        y = max(-1, min(1, y))
        for eye in [self.state.left_eye, self.state.right_eye]:
            eye.pupil_x = x * 0.5  # Limit pupil movement
            eye.pupil_y = y * 0.5

    def render(self) -> Image.Image:
        """Render the face to an image."""
        # Create image
        img = Image.new('RGB', (DISPLAY_WIDTH, DISPLAY_HEIGHT), BACKGROUND_COLOR)
        draw = ImageDraw.Draw(img, 'RGBA')

        # Draw blush if present
        if self.state.blush > 0:
            self._draw_blush(draw, self.state.left_eye, self.state.blush)
            self._draw_blush(draw, self.state.right_eye, self.state.blush)

        # Draw eyes
        self._draw_eye(draw, self.state.left_eye)
        self._draw_eye(draw, self.state.right_eye)

        # Draw mouth if speaking
        if self.state.mouth_open > 0:
            self._draw_mouth(draw, self.state.mouth_open)

        return img

    def _draw_eye(self, draw: ImageDraw.Draw, eye: EyeState) -> None:
        """Draw a single eye."""
        # Calculate eye bounds
        half_w = eye.width / 2
        half_h = eye.height / 2

        left = eye.x - half_w
        top = eye.y - half_h
        right = eye.x + half_w
        bottom = eye.y + half_h

        # Calculate corner radius
        radius = int(min(eye.width, eye.height) * eye.roundness)

        # Draw eye background (white/light part)
        draw.rounded_rectangle(
            [left, top, right, bottom],
            radius=radius,
            fill=EYE_COLOR,
        )

        # Draw highlight (top-left shine)
        highlight_size = min(eye.width, eye.height) * 0.25
        highlight_x = eye.x - half_w * 0.4
        highlight_y = eye.y - half_h * 0.4
        draw.ellipse(
            [
                highlight_x - highlight_size/2,
                highlight_y - highlight_size/2,
                highlight_x + highlight_size/2,
                highlight_y + highlight_size/2,
            ],
            fill=EYE_HIGHLIGHT,
        )

        # Draw pupil (only if eye is open enough)
        if eye.height > self.EYE_HEIGHT * 0.15:
            pupil_size = min(eye.width, eye.height) * 0.35
            pupil_x = eye.x + eye.pupil_x * (half_w - pupil_size/2)
            pupil_y = eye.y + eye.pupil_y * (half_h - pupil_size/2)

            draw.ellipse(
                [
                    pupil_x - pupil_size/2,
                    pupil_y - pupil_size/2,
                    pupil_x + pupil_size/2,
                    pupil_y + pupil_size/2,
                ],
                fill=PUPIL_COLOR,
            )

            # Small highlight in pupil
            small_highlight = pupil_size * 0.3
            draw.ellipse(
                [
                    pupil_x - pupil_size/4 - small_highlight/2,
                    pupil_y - pupil_size/4 - small_highlight/2,
                    pupil_x - pupil_size/4 + small_highlight/2,
                    pupil_y - pupil_size/4 + small_highlight/2,
                ],
                fill=EYE_HIGHLIGHT,
            )

    def _draw_blush(self, draw: ImageDraw.Draw, eye: EyeState, intensity: float) -> None:
        """Draw blush under an eye."""
        blush_color = (255, 150, 180, int(80 * intensity))
        blush_x = eye.x
        blush_y = eye.y + eye.height * 0.6
        blush_w = eye.width * 0.8
        blush_h = eye.height * 0.3

        draw.ellipse(
            [
                blush_x - blush_w/2,
                blush_y - blush_h/2,
                blush_x + blush_w/2,
                blush_y + blush_h/2,
            ],
            fill=blush_color,
        )

    def _draw_mouth(self, draw: ImageDraw.Draw, openness: float) -> None:
        """Draw a simple mouth."""
        center_x = DISPLAY_WIDTH // 2
        mouth_y = self.EYE_Y + self.EYE_HEIGHT * 0.9
        mouth_w = 60
        mouth_h = 20 + openness * 30

        draw.ellipse(
            [
                center_x - mouth_w/2,
                mouth_y - mouth_h/2,
                center_x + mouth_w/2,
                mouth_y + mouth_h/2,
            ],
            fill=PUPIL_COLOR,
        )


class FaceAnimator:
    """
    Animates BrainBot's face with idle movements, blinking, and expressions.
    """

    def __init__(
        self,
        get_mood: Optional[Callable[[], str]] = None,
        get_activity: Optional[Callable[[], Optional[str]]] = None,
        get_energy: Optional[Callable[[], float]] = None,
    ):
        """
        Initialize the face animator.

        Args:
            get_mood: Callback to get current mood
            get_activity: Callback to get current activity
            get_energy: Callback to get energy level (0-1)
        """
        self.renderer = FaceRenderer()
        self.get_mood = get_mood
        self.get_activity = get_activity
        self.get_energy = get_energy

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Animation state
        self._last_blink = time.time()
        self._blink_interval = 3.0  # Seconds between blinks
        self._last_look = time.time()
        self._look_interval = 2.0  # Seconds between look changes
        self._current_look = (0.0, 0.0)
        self._target_look = (0.0, 0.0)

        # Speaking animation
        self._speaking = False
        self._speak_phase = 0.0

        # Framebuffer path
        self._fb_path = Path("/dev/fb0")

    def start(self) -> None:
        """Start the face animation loop."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._animation_loop, daemon=True)
        self._thread.start()
        logger.info("Face animator started")

    def stop(self) -> None:
        """Stop the face animation loop."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        logger.info("Face animator stopped")

    def set_speaking(self, speaking: bool) -> None:
        """Set speaking state for mouth animation."""
        self._speaking = speaking

    def trigger_expression(self, expression: Expression, duration: float = 2.0) -> None:
        """Trigger a temporary expression."""
        # This would be enhanced to support temporary expressions
        with self._lock:
            self.renderer.set_expression(expression)

    def _animation_loop(self) -> None:
        """Main animation loop."""
        frame_interval = 1/30  # 30 FPS

        while self._running:
            try:
                loop_start = time.time()

                # Update expression based on mood/activity
                self._update_expression()

                # Handle blinking
                self._update_blink()

                # Handle looking around
                self._update_look()

                # Handle speaking animation
                self._update_speaking()

                # Render and display
                with self._lock:
                    img = self.renderer.render()
                self._display_to_framebuffer(img)

                # Maintain frame rate
                elapsed = time.time() - loop_start
                sleep_time = max(0, frame_interval - elapsed)
                if sleep_time > 0:
                    time.sleep(sleep_time)

            except Exception as e:
                logger.error(f"Face animation error: {e}")
                time.sleep(0.1)

    def _update_expression(self) -> None:
        """Update expression based on current state."""
        expression = Expression.IDLE

        # Check activity first
        if self.get_activity:
            activity = self.get_activity()
            if activity:
                if "thinking" in activity.lower() or "planning" in activity.lower():
                    expression = Expression.THINKING
                elif "speaking" in activity.lower() or "chat" in activity.lower():
                    expression = Expression.HAPPY
                elif "sleep" in activity.lower():
                    expression = Expression.SLEEPING
                elif "story" in activity.lower() or "creative" in activity.lower():
                    expression = Expression.EXCITED

        # Check energy level
        if self.get_energy:
            energy = self.get_energy()
            if energy < 0.2:
                expression = Expression.SLEEPY
            elif energy < 0.1:
                expression = Expression.SLEEPING

        # Check mood
        if self.get_mood and expression == Expression.IDLE:
            mood = self.get_mood()
            mood_map = {
                "happy": Expression.HAPPY,
                "content": Expression.IDLE,
                "curious": Expression.CURIOUS,
                "excited": Expression.EXCITED,
                "tired": Expression.SLEEPY,
                "sad": Expression.SAD,
            }
            expression = mood_map.get(mood, Expression.IDLE)

        # Apply expression (avoid redundant updates)
        if self.renderer.state.expression != expression:
            with self._lock:
                self.renderer.set_expression(expression)

    def _update_blink(self) -> None:
        """Handle natural blinking."""
        now = time.time()

        # Random blink interval (2-5 seconds)
        if now - self._last_blink > self._blink_interval:
            # Do a blink
            current_expr = self.renderer.state.expression

            # Don't blink if eyes already closed
            if current_expr not in (Expression.SLEEPING, Expression.BLINK):
                with self._lock:
                    self.renderer.set_expression(Expression.BLINK)
                time.sleep(0.1)  # Brief blink
                with self._lock:
                    self.renderer.set_expression(current_expr)

            self._last_blink = now
            self._blink_interval = random.uniform(2, 5)

    def _update_look(self) -> None:
        """Handle eye movement (looking around)."""
        now = time.time()

        # Occasionally pick a new look target
        if now - self._last_look > self._look_interval:
            # Random look direction
            self._target_look = (
                random.uniform(-0.6, 0.6),
                random.uniform(-0.4, 0.4),
            )
            self._last_look = now
            self._look_interval = random.uniform(1.5, 4)

        # Smoothly interpolate to target
        lerp_speed = 0.1
        self._current_look = (
            self._current_look[0] + (self._target_look[0] - self._current_look[0]) * lerp_speed,
            self._current_look[1] + (self._target_look[1] - self._current_look[1]) * lerp_speed,
        )

        with self._lock:
            self.renderer.look_at(*self._current_look)

    def _update_speaking(self) -> None:
        """Handle mouth animation when speaking."""
        if self._speaking:
            # Oscillate mouth open/close
            self._speak_phase += 0.3
            openness = (math.sin(self._speak_phase) + 1) / 2 * 0.8
            with self._lock:
                self.renderer.state.mouth_open = openness
        else:
            with self._lock:
                self.renderer.state.mouth_open = 0

    def _display_to_framebuffer(self, img: Image.Image) -> None:
        """Write image directly to framebuffer."""
        try:
            # Convert to RGB565 or BGRA depending on framebuffer format
            # Most Pi setups use 32-bit BGRA
            img_rgba = img.convert('RGBA')

            # Swap R and B for BGRA format
            r, g, b, a = img_rgba.split()
            img_bgra = Image.merge('RGBA', (b, g, r, a))

            # Write to framebuffer
            with open(self._fb_path, 'wb') as fb:
                fb.write(img_bgra.tobytes())

        except PermissionError:
            logger.warning("No permission to write to framebuffer")
        except Exception as e:
            logger.debug(f"Framebuffer write failed: {e}")


# Singleton instance
_animator: Optional[FaceAnimator] = None


def get_face_animator(
    get_mood: Optional[Callable[[], str]] = None,
    get_activity: Optional[Callable[[], Optional[str]]] = None,
    get_energy: Optional[Callable[[], float]] = None,
) -> FaceAnimator:
    """Get or create the face animator singleton."""
    global _animator
    if _animator is None:
        _animator = FaceAnimator(
            get_mood=get_mood,
            get_activity=get_activity,
            get_energy=get_energy,
        )
    return _animator


def stop_face_animator() -> None:
    """Stop the face animator if running."""
    global _animator
    if _animator:
        _animator.stop()
        _animator = None
