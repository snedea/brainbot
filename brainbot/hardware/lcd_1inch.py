"""1-inch B&W OLED display driver (SSD1306)."""

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
    import board
    import busio
    from adafruit_ssd1306 import SSD1306_I2C
    HARDWARE_AVAILABLE = True
except ImportError:
    HARDWARE_AVAILABLE = False


class LCD1Inch:
    """
    Driver for 1-inch B&W OLED display (SSD1306).

    Used for quick status updates and minimal information display.
    """

    DEFAULT_WIDTH = 128
    DEFAULT_HEIGHT = 64
    DEFAULT_I2C_ADDRESS = 0x3C

    def __init__(
        self,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        i2c_address: int = DEFAULT_I2C_ADDRESS,
    ):
        """
        Initialize the 1-inch LCD.

        Args:
            width: Display width in pixels
            height: Display height in pixels
            i2c_address: I2C address of the display
        """
        self.width = width
        self.height = height
        self.i2c_address = i2c_address

        self._display: Optional["SSD1306_I2C"] = None
        self._font: Optional["ImageFont"] = None
        self._initialized = False

        if HARDWARE_AVAILABLE and PIL_AVAILABLE:
            self._initialize()
        else:
            logger.warning("LCD1Inch hardware libraries not available (simulation mode)")

    def _initialize(self) -> bool:
        """Initialize the hardware."""
        try:
            i2c = busio.I2C(board.SCL, board.SDA)
            self._display = SSD1306_I2C(
                self.width, self.height, i2c, addr=self.i2c_address
            )

            # Try to load a nice font, fall back to default
            try:
                self._font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
            except Exception:
                self._font = ImageFont.load_default()

            self._initialized = True
            logger.info("LCD1Inch initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize LCD1Inch: {e}")
            return False

    def display_text(self, line1: str, line2: str = "") -> None:
        """
        Display two lines of text.

        Args:
            line1: First line of text
            line2: Second line of text
        """
        if not self._initialized:
            logger.debug(f"LCD1Inch (sim): {line1} | {line2}")
            return

        try:
            # Create image
            image = Image.new("1", (self.width, self.height))
            draw = ImageDraw.Draw(image)

            # Draw text
            draw.text((0, 0), line1[:21], font=self._font, fill=255)
            if line2:
                draw.text((0, 32), line2[:21], font=self._font, fill=255)

            # Display
            self._display.image(image)
            self._display.show()

        except Exception as e:
            logger.error(f"Failed to display text: {e}")

    def display_status(self, status: str, value: str = "") -> None:
        """
        Display a status with optional value.

        Args:
            status: Status label
            value: Status value
        """
        self.display_text(status, value)

    def display_icon_text(self, icon: str, text: str) -> None:
        """
        Display an icon character with text.

        Args:
            icon: Single character icon (e.g., emoji or symbol)
            text: Text to display next to icon
        """
        # Combine icon and text
        self.display_text(f"{icon} {text}")

    def clear(self) -> None:
        """Clear the display."""
        if not self._initialized:
            logger.debug("LCD1Inch (sim): cleared")
            return

        try:
            self._display.fill(0)
            self._display.show()
        except Exception as e:
            logger.error(f"Failed to clear display: {e}")

    def show_progress(self, label: str, progress: float) -> None:
        """
        Show a progress bar.

        Args:
            label: Label for the progress bar
            progress: Progress value 0.0 to 1.0
        """
        if not self._initialized:
            logger.debug(f"LCD1Inch (sim): {label} [{int(progress*100)}%]")
            return

        try:
            image = Image.new("1", (self.width, self.height))
            draw = ImageDraw.Draw(image)

            # Label
            draw.text((0, 0), label[:21], font=self._font, fill=255)

            # Progress bar
            bar_width = int((self.width - 10) * progress)
            draw.rectangle([5, 40, self.width - 5, 55], outline=255)
            draw.rectangle([7, 42, 7 + bar_width, 53], fill=255)

            # Percentage
            percent_text = f"{int(progress * 100)}%"
            draw.text((self.width // 2 - 10, 25), percent_text, font=self._font, fill=255)

            self._display.image(image)
            self._display.show()

        except Exception as e:
            logger.error(f"Failed to show progress: {e}")

    def is_available(self) -> bool:
        """Check if the display is available."""
        return self._initialized
