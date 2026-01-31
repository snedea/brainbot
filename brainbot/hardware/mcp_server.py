"""BrainBot Hardware MCP Server using FastMCP."""

import json
import logging
import sys
from typing import Optional

from fastmcp import FastMCP

# Import hardware controllers (with graceful fallback)
try:
    from .lcd_1inch import LCD1Inch
    LCD_1INCH_AVAILABLE = True
except ImportError:
    LCD_1INCH_AVAILABLE = False

try:
    from .lcd_5inch import LCD5Inch
    LCD_5INCH_AVAILABLE = True
except ImportError:
    LCD_5INCH_AVAILABLE = False

try:
    from .led_controller import LEDController
    LED_AVAILABLE = True
except ImportError:
    LED_AVAILABLE = False

try:
    from .fan_controller import FanController
    FAN_AVAILABLE = True
except ImportError:
    FAN_AVAILABLE = False

logger = logging.getLogger(__name__)

# Create FastMCP server
mcp = FastMCP("BrainBot Hardware MCP Server")

# Hardware instances (initialized on demand)
_lcd_1inch: Optional["LCD1Inch"] = None
_lcd_5inch: Optional["LCD5Inch"] = None
_led: Optional["LEDController"] = None
_fan: Optional["FanController"] = None


def _get_lcd_1inch():
    """Get or create 1-inch LCD instance."""
    global _lcd_1inch
    if _lcd_1inch is None and LCD_1INCH_AVAILABLE:
        _lcd_1inch = LCD1Inch()
    return _lcd_1inch


def _get_lcd_5inch():
    """Get or create 5-inch LCD instance."""
    global _lcd_5inch
    if _lcd_5inch is None and LCD_5INCH_AVAILABLE:
        _lcd_5inch = LCD5Inch()
    return _lcd_5inch


def _get_led():
    """Get or create LED controller instance."""
    global _led
    if _led is None and LED_AVAILABLE:
        _led = LEDController()
    return _led


def _get_fan():
    """Get or create fan controller instance."""
    global _fan
    if _fan is None and FAN_AVAILABLE:
        _fan = FanController()
    return _fan


# ============ LCD 1-inch Tools ============

def _lcd_1inch_text(line1: str, line2: str = "") -> str:
    """Display text on 1-inch B&W OLED display."""
    lcd = _get_lcd_1inch()
    if lcd is None:
        return json.dumps({
            "success": False,
            "error": "1-inch LCD not available",
        })

    try:
        lcd.display_text(line1, line2)
        return json.dumps({
            "success": True,
            "displayed": {"line1": line1, "line2": line2},
        })
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e),
        })


lcd_1inch_text = mcp.tool()(_lcd_1inch_text)


def _lcd_1inch_clear() -> str:
    """Clear the 1-inch display."""
    lcd = _get_lcd_1inch()
    if lcd is None:
        return json.dumps({"success": False, "error": "1-inch LCD not available"})

    try:
        lcd.clear()
        return json.dumps({"success": True})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


lcd_1inch_clear = mcp.tool()(_lcd_1inch_clear)


# ============ LCD 5-inch Tools ============

def _lcd_5inch_status(title: str, status: str, progress: float = 0.0) -> str:
    """Display status information on 5-inch main display."""
    lcd = _get_lcd_5inch()
    if lcd is None:
        return json.dumps({"success": False, "error": "5-inch LCD not available"})

    try:
        lcd.display_status(title, status, progress)
        return json.dumps({
            "success": True,
            "displayed": {"title": title, "status": status, "progress": progress},
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


lcd_5inch_status = mcp.tool()(_lcd_5inch_status)


def _lcd_5inch_story(title: str, text: str) -> str:
    """Display a bedtime story on 5-inch display."""
    lcd = _get_lcd_5inch()
    if lcd is None:
        return json.dumps({"success": False, "error": "5-inch LCD not available"})

    try:
        lcd.display_story(title, text)
        return json.dumps({
            "success": True,
            "displayed": {"title": title, "text_length": len(text)},
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


lcd_5inch_story = mcp.tool()(_lcd_5inch_story)


def _lcd_5inch_clear() -> str:
    """Clear the 5-inch display."""
    lcd = _get_lcd_5inch()
    if lcd is None:
        return json.dumps({"success": False, "error": "5-inch LCD not available"})

    try:
        lcd.clear()
        return json.dumps({"success": True})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


lcd_5inch_clear = mcp.tool()(_lcd_5inch_clear)


# ============ LED Tools ============

def _led_set_pattern(pattern: str, color: str = "white", speed: float = 1.0) -> str:
    """
    Set LED pattern and color.

    Args:
        pattern: Pattern name (solid, breathe, pulse, rainbow, chase)
        color: Color name or hex code
        speed: Animation speed (0.1 to 5.0)
    """
    led = _get_led()
    if led is None:
        return json.dumps({"success": False, "error": "LED controller not available"})

    try:
        led.set_pattern(pattern, color, speed)
        return json.dumps({
            "success": True,
            "pattern": pattern,
            "color": color,
            "speed": speed,
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


led_set_pattern = mcp.tool()(_led_set_pattern)


def _led_mood(mood: str) -> str:
    """
    Set LED to match BrainBot's mood.

    Args:
        mood: Mood name (content, excited, focused, tired, bored, curious, sleeping)
    """
    led = _get_led()
    if led is None:
        return json.dumps({"success": False, "error": "LED controller not available"})

    # Mood to pattern/color mapping
    mood_patterns = {
        "content": ("breathe", "green", 1.0),
        "excited": ("pulse", "yellow", 2.0),
        "focused": ("solid", "blue", 1.0),
        "tired": ("breathe", "orange", 0.5),
        "bored": ("chase", "purple", 0.8),
        "curious": ("rainbow", "rainbow", 1.5),
        "sleeping": ("breathe", "dim_blue", 0.3),
        "accomplished": ("pulse", "gold", 1.5),
    }

    pattern_info = mood_patterns.get(mood.lower(), ("solid", "white", 1.0))

    try:
        led.set_pattern(*pattern_info)
        return json.dumps({
            "success": True,
            "mood": mood,
            "pattern": pattern_info[0],
            "color": pattern_info[1],
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


led_mood = mcp.tool()(_led_mood)


def _led_off() -> str:
    """Turn off all LEDs."""
    led = _get_led()
    if led is None:
        return json.dumps({"success": False, "error": "LED controller not available"})

    try:
        led.off()
        return json.dumps({"success": True})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


led_off = mcp.tool()(_led_off)


# ============ Fan Tools ============

def _fan_set_speed(percent: int) -> str:
    """
    Set fan speed.

    Args:
        percent: Fan speed 0-100
    """
    fan = _get_fan()
    if fan is None:
        return json.dumps({"success": False, "error": "Fan controller not available"})

    try:
        fan.set_speed(percent)
        return json.dumps({
            "success": True,
            "speed_percent": percent,
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


fan_set_speed = mcp.tool()(_fan_set_speed)


def _fan_auto() -> str:
    """Enable automatic fan control based on temperature."""
    fan = _get_fan()
    if fan is None:
        return json.dumps({"success": False, "error": "Fan controller not available"})

    try:
        fan.enable_auto()
        return json.dumps({
            "success": True,
            "mode": "auto",
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


fan_auto = mcp.tool()(_fan_auto)


# ============ System Tools ============

def _get_system_health() -> str:
    """Get system health information (CPU temp, memory, etc)."""
    import psutil
    import os

    try:
        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=0.5)

        # Memory
        memory = psutil.virtual_memory()

        # Disk
        disk = psutil.disk_usage("/")

        # Temperature
        temp = None
        thermal_file = "/sys/class/thermal/thermal_zone0/temp"
        if os.path.exists(thermal_file):
            try:
                with open(thermal_file) as f:
                    temp = int(f.read().strip()) / 1000.0
            except Exception:
                pass

        return json.dumps({
            "success": True,
            "cpu_percent": cpu_percent,
            "memory": {
                "percent": memory.percent,
                "available_mb": memory.available / (1024 * 1024),
                "total_mb": memory.total / (1024 * 1024),
            },
            "disk": {
                "percent": disk.percent,
                "free_gb": disk.free / (1024 * 1024 * 1024),
                "total_gb": disk.total / (1024 * 1024 * 1024),
            },
            "temperature_celsius": temp,
        }, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


get_system_health = mcp.tool()(_get_system_health)


def _get_hardware_status() -> str:
    """Get status of all hardware components."""
    status = {
        "lcd_1inch": {
            "available": LCD_1INCH_AVAILABLE,
            "initialized": _lcd_1inch is not None,
        },
        "lcd_5inch": {
            "available": LCD_5INCH_AVAILABLE,
            "initialized": _lcd_5inch is not None,
        },
        "led": {
            "available": LED_AVAILABLE,
            "initialized": _led is not None,
        },
        "fan": {
            "available": FAN_AVAILABLE,
            "initialized": _fan is not None,
        },
    }
    return json.dumps(status, indent=2)


get_hardware_status = mcp.tool()(_get_hardware_status)


# Entry point
def main():
    """Run the MCP server."""
    # Log startup to stderr (stdout is for MCP protocol)
    print("Starting BrainBot Hardware MCP Server...", file=sys.stderr)
    print(f"Hardware availability:", file=sys.stderr)
    print(f"  LCD 1-inch: {LCD_1INCH_AVAILABLE}", file=sys.stderr)
    print(f"  LCD 5-inch: {LCD_5INCH_AVAILABLE}", file=sys.stderr)
    print(f"  LED: {LED_AVAILABLE}", file=sys.stderr)
    print(f"  Fan: {FAN_AVAILABLE}", file=sys.stderr)

    mcp.run()


if __name__ == "__main__":
    main()
