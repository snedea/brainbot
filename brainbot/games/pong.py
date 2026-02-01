"""Pong game for BrainBot's 5-inch display."""

import logging
import math
import os
import time
import random
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Tuple, Callable

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# Try to import LED controller
try:
    from ..hardware.expansion_leds import ExpansionLEDs, get_leds
    LED_AVAILABLE = True
except ImportError:
    LED_AVAILABLE = False
    ExpansionLEDs = None

logger = logging.getLogger(__name__)

# Face animator pause control
FACE_PAUSE_FILE = Path("/tmp/brainbot_face_pause")

# Rainbow colors for BrainBot's paddle
RAINBOW_COLORS = [
    (255, 0, 0),      # Red
    (255, 127, 0),    # Orange
    (255, 255, 0),    # Yellow
    (0, 255, 0),      # Green
    (0, 127, 255),    # Blue
    (75, 0, 130),     # Indigo
    (148, 0, 211),    # Violet
]


def pause_face_animator() -> None:
    """Pause the face animator so we can use the display."""
    FACE_PAUSE_FILE.touch()
    logger.info("Face animator paused for Pong")
    # Give it a moment to notice the pause
    time.sleep(0.2)


def resume_face_animator() -> None:
    """Resume the face animator after we're done."""
    try:
        FACE_PAUSE_FILE.unlink()
        logger.info("Face animator resumed")
    except FileNotFoundError:
        pass


def get_rainbow_color(offset: float) -> Tuple[int, int, int]:
    """Get a rainbow color based on offset (0-1 cycles through rainbow)."""
    offset = offset % 1.0
    idx = int(offset * len(RAINBOW_COLORS))
    next_idx = (idx + 1) % len(RAINBOW_COLORS)
    t = (offset * len(RAINBOW_COLORS)) % 1.0

    c1 = RAINBOW_COLORS[idx]
    c2 = RAINBOW_COLORS[next_idx]

    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


class PlayerType(Enum):
    """Type of player controlling a paddle."""
    AI = "ai"
    HUMAN = "human"
    COMPUTER = "computer"  # Simple computer opponent


@dataclass
class Paddle:
    """A paddle in the game."""
    x: float
    y: float
    width: int = 15
    height: int = 70  # Slightly smaller for more challenge
    speed: float = 6.0
    player_type: PlayerType = PlayerType.AI
    score: int = 0

    # AI tracking
    target_y: float = 0
    reaction_delay: float = 0.0
    last_update: float = 0.0

    def top(self) -> float:
        return self.y

    def bottom(self) -> float:
        return self.y + self.height

    def center_y(self) -> float:
        return self.y + self.height / 2

    def rect(self) -> Tuple[float, float, float, float]:
        return (self.x, self.y, self.x + self.width, self.y + self.height)


@dataclass
class Ball:
    """The pong ball."""
    x: float
    y: float
    radius: int = 10
    vx: float = 5.0
    vy: float = 3.0
    speed: float = 5.0
    max_speed: float = 12.0

    def rect(self) -> Tuple[float, float, float, float]:
        return (
            self.x - self.radius,
            self.y - self.radius,
            self.x + self.radius,
            self.y + self.radius
        )


class PongGame:
    """
    Classic Pong game for BrainBot.

    Renders to the 5-inch LCD display (800x480).
    Supports AI vs Computer or AI vs Human modes.
    """

    # Display dimensions
    WIDTH = 800
    HEIGHT = 480

    # Colors
    BG_COLOR = (10, 10, 20)
    PADDLE_COLOR = (100, 200, 255)
    BALL_COLOR = (255, 220, 100)
    NET_COLOR = (50, 50, 70)
    TEXT_COLOR = (200, 200, 220)
    SCORE_COLOR = (150, 150, 180)

    # Game settings
    WINNING_SCORE = 5
    PADDLE_MARGIN = 40

    def __init__(
        self,
        left_player: PlayerType = PlayerType.AI,
        right_player: PlayerType = PlayerType.COMPUTER,
        difficulty: float = 0.7,  # 0.0-1.0, affects AI reaction time
        use_leds: bool = True,
    ):
        """
        Initialize the Pong game.

        Args:
            left_player: Who controls the left paddle
            right_player: Who controls the right paddle
            difficulty: AI difficulty (0.0 = easy, 1.0 = hard)
            use_leds: Whether to use LED effects
        """
        self.left_player_type = left_player
        self.right_player_type = right_player
        self.difficulty = difficulty

        # Initialize game objects
        self.left_paddle = Paddle(
            x=self.PADDLE_MARGIN,
            y=self.HEIGHT / 2 - 35,
            player_type=left_player,
        )
        self.right_paddle = Paddle(
            x=self.WIDTH - self.PADDLE_MARGIN - 15,
            y=self.HEIGHT / 2 - 35,
            player_type=right_player,
        )

        self.ball = Ball(
            x=self.WIDTH / 2,
            y=self.HEIGHT / 2,
        )

        # Game state
        self.running = False
        self.paused = False
        self.game_over = False
        self.winner: Optional[str] = None
        self.rally_count = 0
        self.max_rally = 0

        # Timing
        self.fps = 60
        self.frame_time = 1.0 / self.fps
        self.last_frame = 0.0

        # Animation state
        self._rainbow_offset = 0.0
        self._hit_flash_time = 0.0
        self._score_flash_time = 0.0
        self._last_scorer = None  # "left" or "right"

        # LED controller
        self._leds: Optional["ExpansionLEDs"] = None
        self._use_leds = use_leds
        if use_leds and LED_AVAILABLE:
            try:
                self._leds = get_leds()
                logger.info("LED controller connected for Pong")
            except Exception as e:
                logger.warning(f"LED init failed: {e}")

        # Font
        self._font: Optional["ImageFont"] = None
        self._font_large: Optional["ImageFont"] = None
        self._load_fonts()

        # Reset ball with random direction
        self._reset_ball()

    def _load_fonts(self) -> None:
        """Load fonts for rendering."""
        if not PIL_AVAILABLE:
            return

        try:
            font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            if not os.path.exists(font_path):
                font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
            self._font = ImageFont.truetype(font_path, 24)
            self._font_large = ImageFont.truetype(font_path, 72)
        except Exception:
            self._font = ImageFont.load_default()
            self._font_large = ImageFont.load_default()

    def _reset_ball(self, direction: int = 0) -> None:
        """Reset ball to center with random velocity."""
        self.ball.x = self.WIDTH / 2
        self.ball.y = self.HEIGHT / 2

        # Random direction if not specified
        if direction == 0:
            direction = random.choice([-1, 1])

        angle = random.uniform(-0.5, 0.5)  # Random angle
        self.ball.speed = 5.0
        self.ball.vx = self.ball.speed * direction
        self.ball.vy = self.ball.speed * angle

        self.rally_count = 0

    def _update_ai_paddle(self, paddle: Paddle, dt: float) -> None:
        """Update AI-controlled paddle."""
        now = time.time()

        # AI reaction delay based on difficulty
        reaction_time = 0.3 * (1.0 - self.difficulty)

        if now - paddle.last_update > reaction_time:
            paddle.last_update = now

            # Predict where ball will be
            if paddle.player_type == PlayerType.AI:
                # Smart AI: predict ball trajectory
                paddle.target_y = self._predict_ball_y(paddle)
            else:
                # Simple computer: just track ball
                paddle.target_y = self.ball.y

            # Add some imperfection based on difficulty
            # More error for lower difficulty, but always some randomness
            error = random.uniform(-40, 40) * (1.0 - self.difficulty * 0.7)
            paddle.target_y += error

        # Move toward target
        target = paddle.target_y - paddle.height / 2
        diff = target - paddle.y

        # Speed based on difficulty
        speed = paddle.speed * (0.5 + 0.5 * self.difficulty)

        if abs(diff) > speed:
            if diff > 0:
                paddle.y += speed
            else:
                paddle.y -= speed
        else:
            paddle.y = target

        # Keep in bounds
        paddle.y = max(0, min(self.HEIGHT - paddle.height, paddle.y))

    def _predict_ball_y(self, paddle: Paddle) -> float:
        """Predict where ball will intersect paddle's x position."""
        if self.ball.vx == 0:
            return self.ball.y

        # Calculate time to reach paddle
        if paddle.x < self.WIDTH / 2:
            # Left paddle
            if self.ball.vx > 0:
                # Ball moving away
                return self.HEIGHT / 2
            time_to_paddle = (paddle.x + paddle.width - self.ball.x) / self.ball.vx
        else:
            # Right paddle
            if self.ball.vx < 0:
                # Ball moving away
                return self.HEIGHT / 2
            time_to_paddle = (paddle.x - self.ball.x) / self.ball.vx

        # Predict y position
        predicted_y = self.ball.y + self.ball.vy * abs(time_to_paddle)

        # Account for bounces
        while predicted_y < 0 or predicted_y > self.HEIGHT:
            if predicted_y < 0:
                predicted_y = -predicted_y
            elif predicted_y > self.HEIGHT:
                predicted_y = 2 * self.HEIGHT - predicted_y

        return predicted_y

    def _check_paddle_collision(self, paddle: Paddle) -> bool:
        """Check if ball collides with paddle."""
        ball_rect = self.ball.rect()
        paddle_rect = paddle.rect()

        # Simple AABB collision
        if (ball_rect[2] >= paddle_rect[0] and
            ball_rect[0] <= paddle_rect[2] and
            ball_rect[3] >= paddle_rect[1] and
            ball_rect[1] <= paddle_rect[3]):
            return True
        return False

    def _handle_paddle_collision(self, paddle: Paddle) -> None:
        """Handle ball bouncing off paddle."""
        # Calculate hit position (-1 to 1, center = 0)
        hit_pos = (self.ball.y - paddle.center_y()) / (paddle.height / 2)
        hit_pos = max(-1, min(1, hit_pos))

        # Reverse x direction
        self.ball.vx = -self.ball.vx

        # Adjust y velocity based on hit position
        self.ball.vy = hit_pos * self.ball.speed * 1.5

        # Speed up ball more aggressively after each hit
        self.ball.speed = min(self.ball.speed * 1.08, self.ball.max_speed)

        # Update velocity magnitude
        speed = (self.ball.vx**2 + self.ball.vy**2) ** 0.5
        if speed > 0:
            self.ball.vx = self.ball.vx / speed * self.ball.speed
            self.ball.vy = self.ball.vy / speed * self.ball.speed

        # Move ball out of paddle
        if paddle.x < self.WIDTH / 2:
            self.ball.x = paddle.x + paddle.width + self.ball.radius + 1
        else:
            self.ball.x = paddle.x - self.ball.radius - 1

        self.rally_count += 1
        self.max_rally = max(self.max_rally, self.rally_count)

        # Visual and LED feedback for hit
        self._hit_flash_time = time.time()
        self._on_paddle_hit(paddle)

    def update(self, dt: float, human_input: Optional[float] = None) -> None:
        """
        Update game state.

        Args:
            dt: Delta time in seconds
            human_input: Human paddle movement (-1 to 1) if applicable
        """
        # Animate rainbow paddle
        self._rainbow_offset = (self._rainbow_offset + dt * 0.5) % 1.0

        # Update LEDs based on game state
        self._update_leds_for_gameplay()

        if self.paused or self.game_over:
            return

        # Update paddles
        if self.left_paddle.player_type == PlayerType.HUMAN and human_input is not None:
            self.left_paddle.y += human_input * self.left_paddle.speed
            self.left_paddle.y = max(0, min(self.HEIGHT - self.left_paddle.height, self.left_paddle.y))
        else:
            self._update_ai_paddle(self.left_paddle, dt)

        if self.right_paddle.player_type == PlayerType.HUMAN and human_input is not None:
            self.right_paddle.y += human_input * self.right_paddle.speed
            self.right_paddle.y = max(0, min(self.HEIGHT - self.right_paddle.height, self.right_paddle.y))
        else:
            self._update_ai_paddle(self.right_paddle, dt)

        # Update ball
        self.ball.x += self.ball.vx
        self.ball.y += self.ball.vy

        # Wall collisions (top/bottom)
        if self.ball.y - self.ball.radius <= 0:
            self.ball.y = self.ball.radius
            self.ball.vy = abs(self.ball.vy)
        elif self.ball.y + self.ball.radius >= self.HEIGHT:
            self.ball.y = self.HEIGHT - self.ball.radius
            self.ball.vy = -abs(self.ball.vy)

        # Paddle collisions
        if self._check_paddle_collision(self.left_paddle):
            self._handle_paddle_collision(self.left_paddle)
        elif self._check_paddle_collision(self.right_paddle):
            self._handle_paddle_collision(self.right_paddle)

        # Score (ball goes past paddle)
        if self.ball.x < 0:
            self.right_paddle.score += 1
            self._score_flash_time = time.time()
            self._last_scorer = "right"
            # Right scored = BrainBot missed (if BrainBot is on left)
            is_brainbot_score = self.right_paddle.player_type == PlayerType.AI
            self._on_score("brainbot" if is_brainbot_score else "opponent")
            self._reset_ball(direction=1)
            self._check_winner()
        elif self.ball.x > self.WIDTH:
            self.left_paddle.score += 1
            self._score_flash_time = time.time()
            self._last_scorer = "left"
            # Left scored = BrainBot scored (if BrainBot is on left)
            is_brainbot_score = self.left_paddle.player_type == PlayerType.AI
            self._on_score("brainbot" if is_brainbot_score else "opponent")
            self._reset_ball(direction=-1)
            self._check_winner()

    def _check_winner(self) -> None:
        """Check if someone won."""
        if self.left_paddle.score >= self.WINNING_SCORE:
            self.game_over = True
            self.winner = "BrainBot" if self.left_paddle.player_type == PlayerType.AI else "Left"
            self._on_game_over(won=self.left_paddle.player_type == PlayerType.AI)
        elif self.right_paddle.score >= self.WINNING_SCORE:
            self.game_over = True
            self.winner = "BrainBot" if self.right_paddle.player_type == PlayerType.AI else "Computer"
            self._on_game_over(won=self.right_paddle.player_type == PlayerType.AI)

    # ========== LED Event Handlers ==========

    def _on_paddle_hit(self, paddle: Paddle) -> None:
        """Called when ball hits a paddle - flash LEDs."""
        if not self._leds:
            return

        try:
            if paddle.player_type == PlayerType.AI:
                # BrainBot hit - cyan flash
                self._leds._set_all(0, 200, 255)
            else:
                # Computer/human hit - orange flash
                self._leds._set_all(255, 150, 0)
        except Exception:
            pass

    def _on_score(self, scorer: str) -> None:
        """Called when someone scores - celebration or sad LEDs."""
        if not self._leds:
            return

        try:
            if scorer == "brainbot":
                # BrainBot scored! Rainbow celebration
                self._leds.set_mood("excited")
            else:
                # BrainBot missed - brief red
                self._leds._set_all(255, 50, 0)
        except Exception:
            pass

    def _on_game_over(self, won: bool) -> None:
        """Called when game ends."""
        if not self._leds:
            return

        try:
            if won:
                # BrainBot won! Big celebration
                self._leds.set_mood("excited")
            else:
                # BrainBot lost
                self._leds._set_all(100, 0, 150)  # Purple/sad
        except Exception:
            pass

    def _draw_paddle(self, draw: "ImageDraw", paddle: Paddle) -> None:
        """Draw a paddle, with rainbow effect for BrainBot."""
        rect = paddle.rect()

        if paddle.player_type == PlayerType.AI:
            # BrainBot's paddle - animated rainbow stripes!
            stripe_count = 7
            stripe_height = paddle.height / stripe_count

            for i in range(stripe_count):
                # Animated rainbow offset
                color_offset = (i / stripe_count + self._rainbow_offset) % 1.0
                color = get_rainbow_color(color_offset)

                y1 = rect[1] + i * stripe_height
                y2 = y1 + stripe_height

                draw.rectangle(
                    [rect[0], y1, rect[2], y2],
                    fill=color
                )

            # Add white highlight edge for polish
            draw.line(
                [(rect[0], rect[1]), (rect[0], rect[3])],
                fill=(255, 255, 255),
                width=2
            )
        else:
            # Regular paddle for computer/human
            draw.rectangle(rect, fill=self.PADDLE_COLOR)

    def _update_leds_for_gameplay(self) -> None:
        """Update LEDs based on current game state."""
        if not self._leds:
            return

        try:
            now = time.time()

            # Check if we're in a flash state
            if now - self._hit_flash_time < 0.15:
                return  # Let hit flash play out

            if now - self._score_flash_time < 1.0:
                return  # Let score celebration play out

            # Default: pulse based on ball speed (intensity matches game pace)
            intensity = min(1.0, self.ball.speed / self.ball.max_speed)
            base_color = int(50 + intensity * 100)

            # Color based on ball position (which side)
            if self.ball.x < self.WIDTH / 2:
                # Ball on left (BrainBot's side) - cyan tint
                self._leds._set_all(0, base_color, int(base_color * 1.2))
            else:
                # Ball on right side - orange tint
                self._leds._set_all(int(base_color * 1.2), base_color, 0)

        except Exception:
            pass

    def render(self) -> "Image":
        """Render the game to a PIL Image."""
        if not PIL_AVAILABLE:
            raise RuntimeError("PIL not available")

        # Create frame
        image = Image.new("RGB", (self.WIDTH, self.HEIGHT), self.BG_COLOR)
        draw = ImageDraw.Draw(image)

        # Draw center line (net)
        for y in range(0, self.HEIGHT, 30):
            draw.rectangle(
                [self.WIDTH // 2 - 2, y, self.WIDTH // 2 + 2, y + 15],
                fill=self.NET_COLOR
            )

        # Draw scores
        left_score = str(self.left_paddle.score)
        right_score = str(self.right_paddle.score)

        if self._font_large:
            # Left score
            bbox = self._font_large.getbbox(left_score)
            score_x = self.WIDTH // 4 - (bbox[2] - bbox[0]) // 2
            draw.text((score_x, 30), left_score, font=self._font_large, fill=self.SCORE_COLOR)

            # Right score
            bbox = self._font_large.getbbox(right_score)
            score_x = 3 * self.WIDTH // 4 - (bbox[2] - bbox[0]) // 2
            draw.text((score_x, 30), right_score, font=self._font_large, fill=self.SCORE_COLOR)

        # Draw paddles
        # BrainBot's paddle gets rainbow stripes!
        self._draw_paddle(draw, self.left_paddle)
        self._draw_paddle(draw, self.right_paddle)

        # Draw ball
        draw.ellipse(self.ball.rect(), fill=self.BALL_COLOR)

        # Draw player labels
        if self._font:
            left_label = "BrainBot" if self.left_paddle.player_type == PlayerType.AI else "Player"
            right_label = "Computer" if self.right_paddle.player_type == PlayerType.COMPUTER else "BrainBot"

            draw.text((20, self.HEIGHT - 35), left_label, font=self._font, fill=self.TEXT_COLOR)

            bbox = self._font.getbbox(right_label)
            draw.text(
                (self.WIDTH - 20 - (bbox[2] - bbox[0]), self.HEIGHT - 35),
                right_label,
                font=self._font,
                fill=self.TEXT_COLOR
            )

            # Rally counter
            rally_text = f"Rally: {self.rally_count}"
            bbox = self._font.getbbox(rally_text)
            draw.text(
                (self.WIDTH // 2 - (bbox[2] - bbox[0]) // 2, self.HEIGHT - 35),
                rally_text,
                font=self._font,
                fill=self.TEXT_COLOR
            )

        # Game over overlay
        if self.game_over and self._font_large:
            # Semi-transparent overlay
            overlay = Image.new("RGBA", (self.WIDTH, self.HEIGHT), (0, 0, 0, 180))
            image = image.convert("RGBA")
            image = Image.alpha_composite(image, overlay)
            draw = ImageDraw.Draw(image)

            # Winner text
            win_text = f"{self.winner} Wins!"
            bbox = self._font_large.getbbox(win_text)
            text_x = (self.WIDTH - (bbox[2] - bbox[0])) // 2
            text_y = self.HEIGHT // 2 - 50
            draw.text((text_x, text_y), win_text, font=self._font_large, fill=(255, 220, 100))

            # Stats
            if self._font:
                stats = f"Max Rally: {self.max_rally}"
                bbox = self._font.getbbox(stats)
                draw.text(
                    ((self.WIDTH - (bbox[2] - bbox[0])) // 2, text_y + 100),
                    stats,
                    font=self._font,
                    fill=self.TEXT_COLOR
                )

            image = image.convert("RGB")

        return image

    def render_to_framebuffer(self) -> None:
        """Render directly to the framebuffer."""
        image = self.render()

        try:
            fb_path = "/dev/fb0"
            if os.path.exists(fb_path):
                # Get framebuffer info
                with open("/sys/class/graphics/fb0/virtual_size", "r") as f:
                    fb_size = f.read().strip().split(",")
                    fb_width, fb_height = int(fb_size[0]), int(fb_size[1])

                # Resize if needed
                if image.size != (fb_width, fb_height):
                    image = image.resize((fb_width, fb_height), Image.LANCZOS)

                # Convert to BGRA
                rgba_image = image.convert("RGBA")
                r, g, b, a = rgba_image.split()
                bgra_image = Image.merge("RGBA", (b, g, r, a))

                # Write to framebuffer
                with open(fb_path, "wb") as fb:
                    fb.write(bgra_image.tobytes())
        except Exception as e:
            logger.warning(f"Could not render to framebuffer: {e}")

    def save_frame(self, path: str) -> None:
        """Save current frame to file."""
        image = self.render()
        image.save(path, "PNG")

    def run(
        self,
        max_duration: float = 60.0,
        save_path: Optional[str] = None,
        gamepad: Optional["GamepadInput"] = None,
    ) -> dict:
        """
        Run the game loop.

        Args:
            max_duration: Maximum game duration in seconds
            save_path: If set, save frames here instead of framebuffer
            gamepad: Optional gamepad for human player control

        Returns:
            Game results dict
        """
        if not PIL_AVAILABLE:
            logger.error("Cannot run Pong: PIL not available")
            return {"error": "PIL not available"}

        # Pause face animator if we're using the framebuffer
        face_was_paused = FACE_PAUSE_FILE.exists()
        if not save_path and not face_was_paused:
            pause_face_animator()

        # Start gamepad input if provided
        if gamepad:
            gamepad.start()
            logger.info(f"Gamepad connected: {gamepad.device.name if gamepad.device else 'unknown'}")

        self.running = True
        start_time = time.time()
        frame_count = 0

        logger.info(f"Starting Pong: {self.left_paddle.player_type.value} vs {self.right_paddle.player_type.value}")

        try:
            while self.running and not self.game_over:
                frame_start = time.time()

                # Check duration
                if frame_start - start_time > max_duration:
                    logger.info("Pong: max duration reached")
                    break

                # Get human input from gamepad
                human_input = None
                if gamepad:
                    human_input = gamepad.get_vertical_axis()
                    # Check for pause (start button)
                    if gamepad.is_start_pressed():
                        self.paused = not self.paused
                        time.sleep(0.3)  # Debounce

                # Update game
                self.update(self.frame_time, human_input=human_input)

                # Render
                if save_path:
                    self.save_frame(save_path)
                else:
                    self.render_to_framebuffer()

                frame_count += 1

                # Frame timing
                elapsed = time.time() - frame_start
                sleep_time = self.frame_time - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

        except KeyboardInterrupt:
            logger.info("Pong interrupted")
        finally:
            # Stop gamepad
            if gamepad:
                gamepad.stop()

            # Resume face animator if we paused it
            if not save_path and not face_was_paused:
                resume_face_animator()

        self.running = False

        return {
            "winner": self.winner,
            "left_score": self.left_paddle.score,
            "right_score": self.right_paddle.score,
            "max_rally": self.max_rally,
            "duration": time.time() - start_time,
            "frames": frame_count,
        }

    def reset(self) -> None:
        """Reset the game."""
        self.left_paddle.score = 0
        self.right_paddle.score = 0
        self.left_paddle.y = self.HEIGHT / 2 - self.left_paddle.height / 2
        self.right_paddle.y = self.HEIGHT / 2 - self.right_paddle.height / 2
        self.game_over = False
        self.winner = None
        self.rally_count = 0
        self.max_rally = 0
        self._reset_ball()


def main():
    """Test the Pong game."""
    import argparse

    parser = argparse.ArgumentParser(description="BrainBot Pong")
    parser.add_argument("--save", type=str, help="Save frames to this path")
    parser.add_argument("--duration", type=float, default=60, help="Max duration in seconds")
    parser.add_argument("--difficulty", type=float, default=0.7, help="AI difficulty (0-1)")
    args = parser.parse_args()

    game = PongGame(
        left_player=PlayerType.AI,
        right_player=PlayerType.COMPUTER,
        difficulty=args.difficulty,
    )

    print(f"Starting Pong: BrainBot (AI) vs Computer")
    print(f"Difficulty: {args.difficulty}")
    print(f"First to {game.WINNING_SCORE} wins!")
    print()

    result = game.run(max_duration=args.duration, save_path=args.save)

    print()
    print("=" * 40)
    print(f"Game Over!")
    print(f"Winner: {result['winner']}")
    print(f"Score: {result['left_score']} - {result['right_score']}")
    print(f"Max Rally: {result['max_rally']}")
    print(f"Duration: {result['duration']:.1f}s")
    print(f"Frames: {result['frames']}")


if __name__ == "__main__":
    main()
