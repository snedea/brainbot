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
            self._font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            # Check if bold exists, fall back to regular
            import os
            if not os.path.exists(self._font_path):
                self._font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
            self._font_title = ImageFont.truetype(self._font_path, 36)
            self._font_body = ImageFont.truetype(self._font_path, 20)
            self._font_small = ImageFont.truetype(self._font_path, 14)
        except Exception:
            self._font_path = None
            self._font_title = ImageFont.load_default()
            self._font_body = ImageFont.load_default()
            self._font_small = ImageFont.load_default()

    def _calculate_optimal_font_size(
        self,
        text: str,
        max_width: int,
        max_height: int,
        min_size: int = 24,
        max_size: int = 120,
    ) -> Tuple[int, list[str]]:
        """
        Calculate the largest font size that fits text in the given area.

        Args:
            text: Text to display
            max_width: Maximum width in pixels
            max_height: Maximum height in pixels
            min_size: Minimum font size to try
            max_size: Maximum font size to try

        Returns:
            Tuple of (font_size, wrapped_lines)
        """
        if not self._font_path:
            return (min_size, [text])

        # Try font sizes from large to small
        for size in range(max_size, min_size - 1, -4):
            try:
                font = ImageFont.truetype(self._font_path, size)

                # Calculate line height (approximately 1.2x font size)
                line_height = int(size * 1.3)

                # Calculate approximate characters per line
                # Use a test character to get average width
                test_bbox = font.getbbox("M")
                avg_char_width = test_bbox[2] - test_bbox[0]
                chars_per_line = max(1, int(max_width / avg_char_width))

                # Wrap text
                wrapped = textwrap.wrap(text, width=chars_per_line)

                # Calculate total height needed
                total_height = len(wrapped) * line_height

                # Check if it fits
                if total_height <= max_height:
                    # Verify width of each line
                    fits = True
                    for line in wrapped:
                        bbox = font.getbbox(line)
                        if (bbox[2] - bbox[0]) > max_width:
                            fits = False
                            break

                    if fits:
                        return (size, wrapped)

            except Exception:
                continue

        # Fall back to minimum size
        font = ImageFont.truetype(self._font_path, min_size)
        test_bbox = font.getbbox("M")
        avg_char_width = test_bbox[2] - test_bbox[0]
        chars_per_line = max(1, int(max_width / avg_char_width))
        wrapped = textwrap.wrap(text, width=chars_per_line)
        return (min_size, wrapped)

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
        color: Tuple[int, int, int] = (255, 255, 255),
    ) -> None:
        """
        Display a simple message with dynamic font sizing.

        The font size is automatically calculated to be as large as possible
        while still fitting the text on screen. Short messages get huge fonts,
        longer messages get smaller fonts.

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

            # Calculate available space
            margin = 40
            content_width = self.width - (margin * 2)

            # Reserve space for title if present
            title_height = 0
            if title:
                title_font = ImageFont.truetype(self._font_path, 28) if self._font_path else self._font_title
                draw.text((margin, 20), title, font=title_font, fill=(100, 200, 255))
                title_height = 70  # Title + padding

            # Available height for message
            content_height = self.height - title_height - (margin * 2)
            content_top = title_height + margin

            # Calculate optimal font size for the message
            font_size, wrapped_lines = self._calculate_optimal_font_size(
                message,
                max_width=content_width,
                max_height=content_height,
                min_size=24,
                max_size=140,  # Allow really big fonts for short messages
            )

            # Load the calculated font
            if self._font_path:
                message_font = ImageFont.truetype(self._font_path, font_size)
            else:
                message_font = self._font_body

            # Calculate line height
            line_height = int(font_size * 1.3)

            # Calculate total text height and center vertically
            total_text_height = len(wrapped_lines) * line_height
            start_y = content_top + (content_height - total_text_height) // 2

            # Draw each line, centered horizontally
            for i, line in enumerate(wrapped_lines):
                bbox = message_font.getbbox(line)
                line_width = bbox[2] - bbox[0]
                x = (self.width - line_width) // 2  # Center horizontally
                y = start_y + (i * line_height)
                draw.text((x, y), line, font=message_font, fill=color)

            logger.debug(f"Displaying message with font size {font_size}px, {len(wrapped_lines)} lines")
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
        Render an image to the display via framebuffer.

        Writes directly to /dev/fb0 (DSI display) if available.
        """
        # Save debug image
        try:
            debug_path = "/tmp/brainbot_lcd5inch_debug.png"
            image.save(debug_path)
            logger.debug(f"LCD5Inch image saved to {debug_path}")
        except Exception as e:
            logger.debug(f"Could not save debug image: {e}")

        # Try to render to framebuffer
        try:
            import os
            fb_path = "/dev/fb0"
            if os.path.exists(fb_path):
                # Convert to RGB and resize to framebuffer size if needed
                rgb_image = image.convert("RGB")

                # Get framebuffer info
                with open("/sys/class/graphics/fb0/virtual_size", "r") as f:
                    fb_size = f.read().strip().split(",")
                    fb_width, fb_height = int(fb_size[0]), int(fb_size[1])

                # Resize image to fit framebuffer
                if rgb_image.size != (fb_width, fb_height):
                    rgb_image = rgb_image.resize((fb_width, fb_height), Image.LANCZOS)

                # Convert to BGRA for framebuffer (32-bit)
                rgba_image = rgb_image.convert("RGBA")
                # Swap R and B channels for BGR format
                r, g, b, a = rgba_image.split()
                bgra_image = Image.merge("RGBA", (b, g, r, a))

                # Write to framebuffer
                with open(fb_path, "wb") as fb:
                    fb.write(bgra_image.tobytes())

                logger.info("LCD5Inch rendered to framebuffer")
        except Exception as e:
            logger.warning(f"Could not render to framebuffer: {e}")

    def is_available(self) -> bool:
        """Check if the display is available."""
        return PIL_AVAILABLE
