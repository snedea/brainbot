"""1-inch B&W OLED display driver (SSD1306) using luma.oled."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Try to import hardware libraries
try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    from luma.core.interface.serial import i2c
    from luma.oled.device import ssd1306
    HARDWARE_AVAILABLE = True
except ImportError:
    HARDWARE_AVAILABLE = False


class LCD1Inch:
    """
    Driver for 1-inch B&W OLED display (SSD1306) using luma.oled.

    Used for quick status updates and minimal information display.
    Displays BrainBot's current state, incoming messages, and activity.
    """

    DEFAULT_WIDTH = 128
    DEFAULT_HEIGHT = 64
    DEFAULT_I2C_ADDRESS = 0x3C

    def __init__(
        self,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        i2c_address: int = DEFAULT_I2C_ADDRESS,
        bus_number: int = 1,
    ):
        """
        Initialize the 1-inch LCD.

        Args:
            width: Display width in pixels
            height: Display height in pixels
            i2c_address: I2C address of the display
            bus_number: I2C bus number (default 1 for Raspberry Pi)
        """
        self.width = width
        self.height = height
        self.i2c_address = i2c_address
        self.bus_number = bus_number

        self._device = None
        self._font: Optional["ImageFont.FreeTypeFont"] = None
        self._font_small: Optional["ImageFont.FreeTypeFont"] = None
        self._initialized = False

        if HARDWARE_AVAILABLE and PIL_AVAILABLE:
            self._initialize()
        else:
            missing = []
            if not PIL_AVAILABLE:
                missing.append("PIL")
            if not HARDWARE_AVAILABLE:
                missing.append("luma.oled")
            logger.warning(f"LCD1Inch: missing {', '.join(missing)} (simulation mode)")

    def _initialize(self) -> bool:
        """Initialize the hardware."""
        try:
            serial = i2c(port=self.bus_number, address=self.i2c_address)
            self._device = ssd1306(serial, width=self.width, height=self.height)

            # Load fonts
            try:
                font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
                self._font = ImageFont.truetype(font_path, 14)
                self._font_small = ImageFont.truetype(font_path, 10)
            except Exception:
                self._font = ImageFont.load_default()
                self._font_small = ImageFont.load_default()

            self._initialized = True
            logger.info("LCD1Inch initialized (luma.oled SSD1306)")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize LCD1Inch: {e}")
            return False

    def display_text(self, line1: str, line2: str = "", line3: str = "") -> None:
        """
        Display up to three lines of text.

        Args:
            line1: First line of text
            line2: Second line of text
            line3: Third line of text
        """
        if not self._initialized:
            logger.debug(f"LCD1Inch (sim): {line1} | {line2} | {line3}")
            return

        try:
            # Create image
            image = Image.new("1", (self.width, self.height), 0)
            draw = ImageDraw.Draw(image)

            # Draw text lines
            y_positions = [2, 24, 46]
            lines = [line1, line2, line3]

            for i, (line, y) in enumerate(zip(lines, y_positions)):
                if line:
                    # Truncate to fit
                    max_chars = 18 if i == 0 else 21
                    text = line[:max_chars]
                    font = self._font if i == 0 else self._font_small
                    draw.text((2, y), text, font=font, fill=255)

            # Display
            self._device.display(image)

        except Exception as e:
            logger.error(f"Failed to display text: {e}")

    def display_status(self, status: str, value: str = "") -> None:
        """
        Display a status indicator.

        Args:
            status: Status label (e.g., "Mood", "State")
            value: Status value (e.g., "Happy", "Thinking")
        """
        self.display_text(status, value)

    def display_chat(self, source: str, message: str) -> None:
        """
        Display incoming chat message.

        Args:
            source: Message source (e.g., "Slack", "Terminal")
            message: The message text (will be truncated)
        """
        # Truncate message to fit on two lines
        msg_preview = message[:40] + "..." if len(message) > 40 else message
        line2 = msg_preview[:20]
        line3 = msg_preview[20:40] if len(msg_preview) > 20 else ""
        self.display_text(f"[{source}]", line2, line3)

    def display_thinking(self) -> None:
        """Display thinking/processing state."""
        if not self._initialized:
            logger.debug("LCD1Inch (sim): Thinking...")
            return

        try:
            image = Image.new("1", (self.width, self.height), 0)
            draw = ImageDraw.Draw(image)

            # Draw "Thinking..." with animation dots indicator
            draw.text((20, 20), "Thinking", font=self._font, fill=255)
            draw.text((20, 40), "...", font=self._font, fill=255)

            # Draw spinning indicator
            draw.ellipse([100, 25, 120, 45], outline=255)
            draw.arc([100, 25, 120, 45], 0, 90, fill=255, width=2)

            self._device.display(image)

        except Exception as e:
            logger.error(f"Failed to display thinking: {e}")

    def display_speaking(self) -> None:
        """Display speaking/responding state."""
        if not self._initialized:
            logger.debug("LCD1Inch (sim): Speaking...")
            return

        try:
            image = Image.new("1", (self.width, self.height), 0)
            draw = ImageDraw.Draw(image)

            draw.text((20, 20), "Speaking", font=self._font, fill=255)

            # Draw sound waves
            for i, offset in enumerate([0, 8, 16]):
                height = 10 + (i * 5)
                x = 100 + offset
                draw.line([(x, 32 - height // 2), (x, 32 + height // 2)], fill=255, width=2)

            self._device.display(image)

        except Exception as e:
            logger.error(f"Failed to display speaking: {e}")

    def display_idle(self, mood: str = "content") -> None:
        """Display idle state with mood."""
        self.display_text("BrainBot", f"Mood: {mood}", "Ready...")

    def show_progress(self, label: str, progress: float) -> None:
        """
        Show a progress bar.

        Args:
            label: Label for the progress bar
            progress: Progress value 0.0 to 1.0
        """
        if not self._initialized:
            logger.debug(f"LCD1Inch (sim): {label} [{int(progress * 100)}%]")
            return

        try:
            image = Image.new("1", (self.width, self.height), 0)
            draw = ImageDraw.Draw(image)

            # Label
            draw.text((2, 5), label[:18], font=self._font, fill=255)

            # Progress bar
            bar_width = int((self.width - 20) * min(1.0, max(0.0, progress)))
            draw.rectangle([10, 35, self.width - 10, 50], outline=255)
            if bar_width > 0:
                draw.rectangle([12, 37, 12 + bar_width, 48], fill=255)

            # Percentage
            percent_text = f"{int(progress * 100)}%"
            draw.text((self.width // 2 - 15, 52), percent_text, font=self._font_small, fill=255)

            self._device.display(image)

        except Exception as e:
            logger.error(f"Failed to show progress: {e}")

    def clear(self) -> None:
        """Clear the display."""
        if not self._initialized:
            logger.debug("LCD1Inch (sim): cleared")
            return

        try:
            image = Image.new("1", (self.width, self.height), 0)
            self._device.display(image)
        except Exception as e:
            logger.error(f"Failed to clear display: {e}")

    def is_available(self) -> bool:
        """Check if the display is available."""
        return self._initialized


# Singleton instance
_lcd_instance: Optional[LCD1Inch] = None


def get_lcd_1inch() -> Optional[LCD1Inch]:
    """Get or create the LCD1Inch singleton."""
    global _lcd_instance
    if _lcd_instance is None:
        try:
            _lcd_instance = LCD1Inch()
        except Exception as e:
            logger.warning(f"Could not initialize LCD1Inch: {e}")
            return None
    return _lcd_instance
