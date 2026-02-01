"""Display manager for 5-inch LCD - handles showing images without keyboard."""

import logging
import subprocess
import os
import signal
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Track the current display process
_display_process: Optional[subprocess.Popen] = None


def show_image(image_path: str, duration: int = 30) -> bool:
    """
    Display an image fullscreen on the 5-inch LCD.

    Auto-closes after duration seconds, or can be replaced by calling again.

    Args:
        image_path: Path to the image file
        duration: How long to show (seconds), 0 = indefinite

    Returns:
        True if display started successfully
    """
    global _display_process

    # Close any existing display
    close_display()

    if not os.path.exists(image_path):
        logger.error(f"Image not found: {image_path}")
        return False

    try:
        env = os.environ.copy()
        env["DISPLAY"] = ":0"

        # Build feh command
        cmd = ["feh", "--fullscreen", "--auto-zoom", "--hide-pointer"]
        if duration > 0:
            cmd.extend(["--slideshow-delay", str(duration)])
        cmd.append(image_path)

        _display_process = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        logger.info(f"Displaying {image_path} for {duration}s")

        # If duration specified, schedule auto-close
        if duration > 0:
            import threading
            def auto_close():
                import time
                time.sleep(duration)
                close_display()
            threading.Thread(target=auto_close, daemon=True).start()

        return True

    except Exception as e:
        logger.error(f"Failed to display image: {e}")
        return False


def close_display() -> None:
    """Close the current display."""
    global _display_process

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
        logger.debug("Display closed")

    # Also kill any stray feh processes
    try:
        subprocess.run(["pkill", "-f", "feh.*fullscreen"],
                      capture_output=True, timeout=2)
    except:
        pass


def show_story(title: str, text: str, duration: int = 60) -> bool:
    """
    Render and display a story on the 5-inch LCD.

    Args:
        title: Story title
        text: Story content
        duration: Display duration in seconds

    Returns:
        True if successful
    """
    from .lcd_5inch import LCD5Inch

    # Render story to image
    lcd = LCD5Inch()
    lcd.display_story(title, text, page=1)

    # Display the rendered image
    return show_image("/tmp/brainbot_lcd5inch_debug.png", duration=duration)


def show_message(message: str, title: str = "BrainBot", duration: int = 10) -> bool:
    """
    Display a simple message on the 5-inch LCD.

    Args:
        message: Message text
        title: Optional title
        duration: Display duration in seconds

    Returns:
        True if successful
    """
    from .lcd_5inch import LCD5Inch

    lcd = LCD5Inch()
    lcd.display_message(message, title=title)

    return show_image("/tmp/brainbot_lcd5inch_debug.png", duration=duration)


def show_status(status: str, mood: str = "content", energy: float = 1.0,
                duration: int = 0) -> bool:
    """
    Display BrainBot's current status on the 5-inch LCD.

    Args:
        status: Current activity/status
        mood: Current mood
        energy: Energy level 0.0-1.0
        duration: Display duration (0 = stay until replaced)

    Returns:
        True if successful
    """
    from .lcd_5inch import LCD5Inch

    lcd = LCD5Inch()
    lcd.display_status("BrainBot", status, mood=mood, energy=energy)

    return show_image("/tmp/brainbot_lcd5inch_debug.png", duration=duration)
