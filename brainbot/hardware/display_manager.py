"""Display manager for 5-inch LCD - works with both framebuffer and desktop environments."""

import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Singleton LCD instance
_lcd_instance = None
_display_process: Optional[subprocess.Popen] = None
_clear_timer: Optional[threading.Timer] = None

# Temp file for desktop mode (needed for feh)
_TEMP_IMAGE = "/tmp/brainbot_display.png"


def _get_lcd():
    """Get or create the LCD instance."""
    global _lcd_instance
    if _lcd_instance is None:
        from .lcd_5inch import LCD5Inch
        _lcd_instance = LCD5Inch()
    return _lcd_instance


def _is_desktop_environment() -> bool:
    """Check if running in a desktop environment (X11/Wayland)."""
    return os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")


def _cancel_clear_timer():
    """Cancel any pending clear timer."""
    global _clear_timer
    if _clear_timer:
        _clear_timer.cancel()
        _clear_timer = None


def _schedule_clear(duration: int):
    """Schedule display clear after duration seconds."""
    global _clear_timer
    _cancel_clear_timer()

    if duration > 0:
        _clear_timer = threading.Timer(duration, close_display)
        _clear_timer.daemon = True
        _clear_timer.start()


def _show_with_feh(image_path: str) -> bool:
    """Display image fullscreen using feh (for desktop environments)."""
    global _display_process

    # Kill any existing feh/eom processes
    try:
        subprocess.run(["pkill", "-9", "feh"], capture_output=True, timeout=2)
        subprocess.run(["pkill", "-9", "eom"], capture_output=True, timeout=2)
    except:
        pass

    # Close existing display process
    if _display_process:
        try:
            _display_process.terminate()
            _display_process.wait(timeout=1)
        except:
            try:
                _display_process.kill()
            except:
                pass
        _display_process = None

    try:
        env = os.environ.copy()
        env["DISPLAY"] = ":0"

        # feh with proper fullscreen flags
        cmd = [
            "feh",
            "--fullscreen",        # Fullscreen mode
            "--auto-zoom",         # Zoom to fit
            "--hide-pointer",      # Hide mouse cursor
            "--no-menus",          # Disable menus
            "--borderless",        # No window border
            "--image-bg", "black", # Black background
            image_path
        ]

        _display_process = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        logger.debug(f"feh started with PID {_display_process.pid}")
        return True

    except Exception as e:
        logger.error(f"Failed to start feh: {e}")
        return False


def _render_and_display(render_func, duration: int) -> bool:
    """Render using LCD class and display appropriately."""
    try:
        lcd = _get_lcd()

        # Create the image
        from PIL import Image, ImageDraw
        image = Image.new("RGB", (lcd.width, lcd.height), color=(20, 20, 30))

        # Let the render function draw on it
        render_func(lcd, image)

        if _is_desktop_environment():
            # Desktop mode: save and display with feh
            image.save(_TEMP_IMAGE, "PNG")
            _show_with_feh(_TEMP_IMAGE)
        else:
            # Console mode: direct framebuffer
            lcd._render_image(image)

        _schedule_clear(duration)
        return True

    except Exception as e:
        logger.error(f"Display failed: {e}")
        return False


def show_message(message: str, title: str = "BrainBot", duration: int = 10) -> bool:
    """
    Display a message on the 5-inch LCD.

    Uses dynamic font sizing - short messages get huge fonts.

    Args:
        message: Message text
        title: Optional title
        duration: Seconds before clearing (0 = stay indefinitely)

    Returns:
        True if successful
    """
    try:
        lcd = _get_lcd()
        lcd.display_message(message, title=title)

        if _is_desktop_environment():
            # The LCD class saved to a temp file, we need to get it
            # Actually, let's make LCD save to our standard path
            from PIL import Image
            # Re-render to our temp path
            lcd.display_message(message, title=title, save_path=_TEMP_IMAGE)
            _show_with_feh(_TEMP_IMAGE)
        # For console, LCD already wrote to framebuffer

        _schedule_clear(duration)
        logger.info(f"Displayed message: {message[:50]}...")
        return True

    except Exception as e:
        logger.error(f"Failed to display message: {e}")
        return False


def show_status(status: str, mood: str = "content", energy: float = 1.0,
                duration: int = 0) -> bool:
    """
    Display BrainBot's status on the 5-inch LCD.

    Args:
        status: Current activity/status
        mood: Current mood
        energy: Energy level 0.0-1.0
        duration: Seconds before clearing (0 = stay indefinitely)

    Returns:
        True if successful
    """
    try:
        lcd = _get_lcd()
        lcd.display_status("BrainBot", status, mood=mood, energy=energy, save_path=_TEMP_IMAGE)

        if _is_desktop_environment():
            _show_with_feh(_TEMP_IMAGE)

        _schedule_clear(duration)
        logger.info(f"Displayed status: {status}")
        return True

    except Exception as e:
        logger.error(f"Failed to display status: {e}")
        return False


def show_story(title: str, text: str, duration: int = 60) -> bool:
    """
    Display a bedtime story on the 5-inch LCD.

    Args:
        title: Story title
        text: Story content
        duration: Seconds before clearing (0 = stay indefinitely)

    Returns:
        True if successful
    """
    try:
        lcd = _get_lcd()
        lcd.display_story(title, text, page=1, save_path=_TEMP_IMAGE)

        if _is_desktop_environment():
            _show_with_feh(_TEMP_IMAGE)

        _schedule_clear(duration)
        logger.info(f"Displayed story: {title}")
        return True

    except Exception as e:
        logger.error(f"Failed to display story: {e}")
        return False


def show_banner() -> bool:
    """
    Display the BrainBot banner on the 5-inch LCD.

    Returns:
        True if successful
    """
    try:
        lcd = _get_lcd()
        lcd.display_banner(save_path=_TEMP_IMAGE)

        if _is_desktop_environment():
            _show_with_feh(_TEMP_IMAGE)

        logger.info("Displayed banner")
        return True

    except Exception as e:
        logger.error(f"Failed to display banner: {e}")
        return False


def show_image(image_path: str, duration: int = 30) -> bool:
    """
    Display an image file on the 5-inch LCD.

    Args:
        image_path: Path to image file (PNG, JPG, etc.)
        duration: Seconds before clearing (0 = stay indefinitely)

    Returns:
        True if successful
    """
    if not os.path.exists(image_path):
        logger.error(f"Image not found: {image_path}")
        return False

    try:
        if _is_desktop_environment():
            _show_with_feh(image_path)
        else:
            from PIL import Image
            lcd = _get_lcd()
            image = Image.open(image_path)
            if image.size != (lcd.width, lcd.height):
                image = image.resize((lcd.width, lcd.height), Image.LANCZOS)
            lcd._render_image(image)

        _schedule_clear(duration)
        logger.info(f"Displayed image: {image_path}")
        return True

    except Exception as e:
        logger.error(f"Failed to display image: {e}")
        return False


def close_display() -> None:
    """Clear/close the display."""
    global _display_process
    _cancel_clear_timer()

    # Kill feh if running
    if _display_process:
        try:
            _display_process.terminate()
            _display_process.wait(timeout=2)
        except:
            try:
                _display_process.kill()
            except:
                pass
        _display_process = None

    # Also kill any stray feh/eom
    try:
        subprocess.run(["pkill", "-9", "feh"], capture_output=True, timeout=2)
        subprocess.run(["pkill", "-9", "eom"], capture_output=True, timeout=2)
    except:
        pass

    # For console mode, clear framebuffer
    if not _is_desktop_environment():
        try:
            lcd = _get_lcd()
            lcd.clear()
        except:
            pass

    logger.debug("Display closed")
