"""Gamepad controller input for BrainBot games."""

import logging
import threading
import time
from typing import Optional, Callable, Dict

logger = logging.getLogger(__name__)

try:
    import evdev
    from evdev import InputDevice, categorize, ecodes
    EVDEV_AVAILABLE = True
except ImportError:
    EVDEV_AVAILABLE = False
    evdev = None


class GamepadInput:
    """
    Handles gamepad/controller input using evdev.

    Supports Xbox controllers and compatible gamepads.
    """

    # Xbox controller axis codes
    AXIS_LEFT_Y = 1      # Left stick vertical
    AXIS_RIGHT_Y = 4     # Right stick vertical
    AXIS_DPAD_Y = 17     # D-pad vertical

    # Button codes
    BTN_A = 304
    BTN_B = 305
    BTN_X = 307
    BTN_Y = 308
    BTN_START = 315
    BTN_SELECT = 314

    def __init__(self, device_path: Optional[str] = None):
        """
        Initialize gamepad input.

        Args:
            device_path: Path to input device (auto-detect if None)
        """
        self.device: Optional["InputDevice"] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Input state
        self._axis_values: Dict[int, float] = {}
        self._button_states: Dict[int, bool] = {}

        # Callbacks
        self.on_button: Optional[Callable[[int, bool], None]] = None

        if EVDEV_AVAILABLE:
            self._find_device(device_path)

    def _find_device(self, device_path: Optional[str] = None) -> None:
        """Find and connect to a gamepad."""
        if device_path:
            try:
                self.device = InputDevice(device_path)
                logger.info(f"Connected to gamepad: {self.device.name}")
                return
            except Exception as e:
                logger.warning(f"Failed to open {device_path}: {e}")

        # Auto-detect gamepad
        try:
            devices = [InputDevice(path) for path in evdev.list_devices()]
            for dev in devices:
                name = dev.name.lower()
                # Look for Xbox or generic gamepad
                if any(x in name for x in ['xbox', 'controller', 'gamepad', 'joystick']):
                    self.device = dev
                    logger.info(f"Found gamepad: {dev.name} at {dev.path}")
                    return

            # No gamepad found
            if devices:
                logger.debug(f"Available devices: {[d.name for d in devices]}")
            logger.warning("No gamepad found")

        except Exception as e:
            logger.warning(f"Error scanning for gamepads: {e}")

    def is_connected(self) -> bool:
        """Check if a gamepad is connected."""
        return self.device is not None

    def start(self) -> bool:
        """Start reading input in background thread."""
        if not self.device:
            logger.warning("No gamepad to start reading from")
            return False

        if self._running:
            return True

        self._running = True
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()
        logger.info("Gamepad input started")
        return True

    def stop(self) -> None:
        """Stop reading input."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)
            self._thread = None
        logger.debug("Gamepad input stopped")

    def _read_loop(self) -> None:
        """Background thread to read gamepad events."""
        try:
            for event in self.device.read_loop():
                if not self._running:
                    break

                if event.type == ecodes.EV_ABS:
                    # Analog axis event
                    self._handle_axis(event.code, event.value)
                elif event.type == ecodes.EV_KEY:
                    # Button event
                    self._handle_button(event.code, event.value)

        except Exception as e:
            if self._running:
                logger.error(f"Gamepad read error: {e}")

    def _handle_axis(self, code: int, value: int) -> None:
        """Handle axis input."""
        # Normalize to -1.0 to 1.0
        # Xbox controller typically uses 0-65535 range with 32768 center
        if code in (self.AXIS_LEFT_Y, self.AXIS_RIGHT_Y):
            # Analog sticks
            normalized = (value - 32768) / 32768.0
            # Apply deadzone
            if abs(normalized) < 0.15:
                normalized = 0.0
            self._axis_values[code] = normalized
        elif code == self.AXIS_DPAD_Y:
            # D-pad (digital, values are -1, 0, 1)
            self._axis_values[code] = float(value)

    def _handle_button(self, code: int, value: int) -> None:
        """Handle button input."""
        pressed = value == 1
        self._button_states[code] = pressed

        if self.on_button:
            self.on_button(code, pressed)

    def get_vertical_axis(self) -> float:
        """
        Get vertical movement input (-1 = up, 1 = down).

        Uses left stick, right stick, or d-pad.
        """
        # Check left stick first
        left_y = self._axis_values.get(self.AXIS_LEFT_Y, 0.0)
        if abs(left_y) > 0.1:
            return left_y

        # Check right stick
        right_y = self._axis_values.get(self.AXIS_RIGHT_Y, 0.0)
        if abs(right_y) > 0.1:
            return right_y

        # Check d-pad
        dpad_y = self._axis_values.get(self.AXIS_DPAD_Y, 0.0)
        return dpad_y

    def is_button_pressed(self, button_code: int) -> bool:
        """Check if a button is currently pressed."""
        return self._button_states.get(button_code, False)

    def is_start_pressed(self) -> bool:
        """Check if start/menu button is pressed."""
        return self._button_states.get(self.BTN_START, False)

    def is_a_pressed(self) -> bool:
        """Check if A button is pressed."""
        return self._button_states.get(self.BTN_A, False)


def find_gamepad() -> Optional[GamepadInput]:
    """
    Find and return a connected gamepad, or None.
    """
    if not EVDEV_AVAILABLE:
        logger.warning("evdev not available - no gamepad support")
        return None

    gamepad = GamepadInput()
    if gamepad.is_connected():
        return gamepad
    return None


def list_input_devices() -> list:
    """List all available input devices."""
    if not EVDEV_AVAILABLE:
        return []

    try:
        devices = []
        for path in evdev.list_devices():
            dev = InputDevice(path)
            devices.append({
                "path": path,
                "name": dev.name,
                "phys": dev.phys,
            })
        return devices
    except Exception as e:
        logger.error(f"Error listing devices: {e}")
        return []


if __name__ == "__main__":
    # Test gamepad detection
    print("Scanning for gamepads...")
    devices = list_input_devices()
    for d in devices:
        print(f"  {d['path']}: {d['name']}")

    gamepad = find_gamepad()
    if gamepad:
        print(f"\nFound gamepad: {gamepad.device.name}")
        print("Reading input (Ctrl+C to stop)...")

        def on_btn(code, pressed):
            state = "pressed" if pressed else "released"
            print(f"Button {code} {state}")

        gamepad.on_button = on_btn
        gamepad.start()

        try:
            while True:
                y = gamepad.get_vertical_axis()
                if abs(y) > 0.1:
                    print(f"Y axis: {y:.2f}")
                time.sleep(0.1)
        except KeyboardInterrupt:
            pass

        gamepad.stop()
    else:
        print("No gamepad found")
