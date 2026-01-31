"""5-inch LCD display driver."""

import logging
import textwrap
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Try to import hardware libraries
try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# Try to import display library (varies by display type)
try:
    # Try for SPI-based 5" display
    import spidev
    SPI_AVAILABLE = True
except ImportError:
    SPI_AVAILABLE = False


class LCD5Inch:
    """
    Driver for 5-inch LCD display.

    Used for main status display and bedtime stories.
    """

    DEFAULT_WIDTH = 800
    DEFAULT_HEIGHT = 480

    def __init__(
        self,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        spi_port: int = 0,
        spi_device: int = 0,
    ):
        """
        Initialize the 5-inch LCD.

        Args:
            width: Display width in pixels
            height: Display height in pixels
            spi_port: SPI port number
            spi_device: SPI device number
        """
        self.width = width
        self.height = height
        self.spi_port = spi_port
        self.spi_device = spi_device

        self._initialized = False
        self._font_title: Optional["ImageFont"] = None
        self._font_body: Optional["ImageFont"] = None
        self._font_small: Optional["ImageFont"] = None

        if PIL_AVAILABLE:
            self._load_fonts()

        # Note: Actual hardware initialization would depend on the specific
        # display model being used. This is a framework that can be adapted.
        logger.info("LCD5Inch created (hardware init deferred)")

    def _load_fonts(self) -> None:
        """Load fonts for different text sizes."""
        try:
            font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
            self._font_title = ImageFont.truetype(font_path, 36)
            self._font_body = ImageFont.truetype(font_path, 20)
            self._font_small = ImageFont.truetype(font_path, 14)
        except Exception:
            self._font_title = ImageFont.load_default()
            self._font_body = ImageFont.load_default()
            self._font_small = ImageFont.load_default()

    def display_status(
        self,
        title: str,
        status: str,
        progress: float = 0.0,
        mood: Optional[str] = None,
        energy: Optional[float] = None,
    ) -> None:
        """
        Display status information.

        Args:
            title: Main title
            status: Current status text
            progress: Progress bar value (0.0-1.0)
            mood: Current mood (optional)
            energy: Energy level (optional)
        """
        if not PIL_AVAILABLE:
            logger.debug(f"LCD5Inch (sim): {title} - {status} [{progress:.0%}]")
            return

        try:
            # Create image
            image = Image.new("RGB", (self.width, self.height), color=(20, 20, 30))
            draw = ImageDraw.Draw(image)

            # Title
            draw.text((40, 30), title, font=self._font_title, fill=(100, 200, 255))

            # Status
            draw.text((40, 100), status, font=self._font_body, fill=(200, 200, 200))

            # Progress bar
            if progress > 0:
                bar_y = 160
                bar_width = int((self.width - 80) * progress)
                draw.rectangle([40, bar_y, self.width - 40, bar_y + 20], outline=(100, 100, 100))
                draw.rectangle([42, bar_y + 2, 42 + bar_width, bar_y + 18], fill=(100, 200, 100))
                draw.text(
                    (self.width - 80, bar_y + 2),
                    f"{progress:.0%}",
                    font=self._font_small,
                    fill=(200, 200, 200),
                )

            # Mood and energy (bottom section)
            if mood or energy is not None:
                bottom_y = self.height - 60
                if mood:
                    draw.text((40, bottom_y), f"Mood: {mood}", font=self._font_small, fill=(150, 150, 200))
                if energy is not None:
                    draw.text(
                        (self.width - 150, bottom_y),
                        f"Energy: {energy:.0%}",
                        font=self._font_small,
                        fill=(150, 200, 150),
                    )

            self._render_image(image)

        except Exception as e:
            logger.error(f"Failed to display status: {e}")

    def display_story(self, title: str, text: str, page: int = 1) -> None:
        """
        Display a bedtime story.

        Args:
            title: Story title
            text: Story text
            page: Page number (for multi-page stories)
        """
        if not PIL_AVAILABLE:
            logger.debug(f"LCD5Inch (sim): Story '{title}' page {page}")
            return

        try:
            # Create image with warm bedtime colors
            image = Image.new("RGB", (self.width, self.height), color=(25, 20, 35))
            draw = ImageDraw.Draw(image)

            # Title (centered, with decorative line)
            title_bbox = draw.textbbox((0, 0), title, font=self._font_title)
            title_width = title_bbox[2] - title_bbox[0]
            title_x = (self.width - title_width) // 2
            draw.text((title_x, 30), title, font=self._font_title, fill=(255, 220, 150))

            # Decorative line under title
            line_y = 80
            draw.line([(40, line_y), (self.width - 40, line_y)], fill=(100, 80, 60), width=2)

            # Story text (word-wrapped)
            margin = 50
            text_width = self.width - (margin * 2)
            wrapped_lines = self._wrap_text(text, text_width)

            # Calculate how many lines fit per page
            line_height = 28
            max_lines = (self.height - 150) // line_height

            # Get lines for this page
            start_idx = (page - 1) * max_lines
            end_idx = start_idx + max_lines
            page_lines = wrapped_lines[start_idx:end_idx]

            # Draw text
            y = 100
            for line in page_lines:
                draw.text((margin, y), line, font=self._font_body, fill=(220, 220, 230))
                y += line_height

            # Page indicator if multi-page
            total_pages = (len(wrapped_lines) + max_lines - 1) // max_lines
            if total_pages > 1:
                page_text = f"Page {page} of {total_pages}"
                draw.text(
                    (self.width // 2 - 40, self.height - 40),
                    page_text,
                    font=self._font_small,
                    fill=(150, 150, 170),
                )

            self._render_image(image)

        except Exception as e:
            logger.error(f"Failed to display story: {e}")

    def display_message(
        self,
        message: str,
        title: Optional[str] = None,
        color: Tuple[int, int, int] = (200, 200, 200),
    ) -> None:
        """
        Display a simple message.

        Args:
            message: Message text
            title: Optional title
            color: Text color RGB
        """
        if not PIL_AVAILABLE:
            logger.debug(f"LCD5Inch (sim): {title or 'Message'}: {message}")
            return

        try:
            image = Image.new("RGB", (self.width, self.height), color=(20, 20, 30))
            draw = ImageDraw.Draw(image)

            if title:
                draw.text((40, 30), title, font=self._font_title, fill=(100, 200, 255))

            # Wrap and center message
            wrapped = self._wrap_text(message, self.width - 80)
            y = self.height // 2 - (len(wrapped) * 25) // 2

            for line in wrapped:
                draw.text((40, y), line, font=self._font_body, fill=color)
                y += 25

            self._render_image(image)

        except Exception as e:
            logger.error(f"Failed to display message: {e}")

    def clear(self) -> None:
        """Clear the display."""
        if PIL_AVAILABLE:
            image = Image.new("RGB", (self.width, self.height), color=(0, 0, 0))
            self._render_image(image)
        logger.debug("LCD5Inch cleared")

    def _wrap_text(self, text: str, max_width: int) -> list[str]:
        """Wrap text to fit within width."""
        # Approximate characters per line based on font
        chars_per_line = max_width // 10  # Rough estimate
        wrapped = textwrap.wrap(text, width=chars_per_line)
        return wrapped

    def _render_image(self, image: "Image") -> None:
        """
        Render an image to the display.

        This is a placeholder - actual implementation depends on display type.
        """
        # In a real implementation, this would send the image to the hardware
        # For now, we could save it for debugging
        try:
            # Save to temp file for debugging
            debug_path = "/tmp/brainbot_lcd5inch_debug.png"
            image.save(debug_path)
            logger.debug(f"LCD5Inch image saved to {debug_path}")
        except Exception as e:
            logger.debug(f"Could not save debug image: {e}")

    def is_available(self) -> bool:
        """Check if the display is available."""
        return PIL_AVAILABLE
