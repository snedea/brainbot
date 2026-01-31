"""PWM fan controller for temperature management."""

import logging
import os
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Try to import GPIO library
try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False


class FanController:
    """
    PWM fan controller for Raspberry Pi.

    Provides automatic temperature-based fan control.
    """

    DEFAULT_PIN = 12  # GPIO12 (PWM0)
    DEFAULT_MIN_TEMP = 40  # Start fan at 40°C
    DEFAULT_MAX_TEMP = 70  # Full speed at 70°C
    DEFAULT_MIN_SPEED = 30  # Minimum fan speed when active
    PWM_FREQUENCY = 25000  # 25kHz for quiet operation

    def __init__(
        self,
        pin: int = DEFAULT_PIN,
        min_temp: int = DEFAULT_MIN_TEMP,
        max_temp: int = DEFAULT_MAX_TEMP,
        min_speed: int = DEFAULT_MIN_SPEED,
    ):
        """
        Initialize fan controller.

        Args:
            pin: GPIO pin for PWM control
            min_temp: Temperature at which fan starts
            max_temp: Temperature at which fan is at 100%
            min_speed: Minimum fan speed when running (0-100)
        """
        self.pin = pin
        self.min_temp = min_temp
        self.max_temp = max_temp
        self.min_speed = min_speed

        self._pwm: Optional["GPIO.PWM"] = None
        self._current_speed = 0
        self._auto_mode = False
        self._auto_thread: Optional[threading.Thread] = None
        self._stop_auto = threading.Event()

        if GPIO_AVAILABLE:
            self._initialize()
        else:
            logger.warning("RPi.GPIO not available (simulation mode)")

    def _initialize(self) -> bool:
        """Initialize GPIO PWM."""
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.pin, GPIO.OUT)

            self._pwm = GPIO.PWM(self.pin, self.PWM_FREQUENCY)
            self._pwm.start(0)

            logger.info(f"Fan controller initialized on GPIO{self.pin}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize fan controller: {e}")
            return False

    def set_speed(self, percent: int) -> None:
        """
        Set fan speed.

        Args:
            percent: Speed 0-100
        """
        percent = max(0, min(100, percent))
        self._current_speed = percent

        if self._pwm:
            self._pwm.ChangeDutyCycle(percent)
            logger.debug(f"Fan speed set to {percent}%")
        else:
            logger.debug(f"Fan (sim): speed set to {percent}%")

    def enable_auto(self) -> None:
        """Enable automatic temperature-based control."""
        if self._auto_mode:
            return

        self._auto_mode = True
        self._stop_auto.clear()

        self._auto_thread = threading.Thread(
            target=self._auto_control_loop,
            daemon=True,
        )
        self._auto_thread.start()
        logger.info("Fan auto control enabled")

    def disable_auto(self) -> None:
        """Disable automatic control."""
        self._auto_mode = False
        self._stop_auto.set()

        if self._auto_thread and self._auto_thread.is_alive():
            self._auto_thread.join(timeout=2.0)

        logger.info("Fan auto control disabled")

    def _auto_control_loop(self) -> None:
        """Automatic temperature control loop."""
        while not self._stop_auto.is_set():
            try:
                temp = self._get_cpu_temperature()

                if temp is None:
                    # Can't read temperature, set to medium speed
                    self.set_speed(50)
                elif temp < self.min_temp:
                    # Below minimum, turn off
                    self.set_speed(0)
                elif temp >= self.max_temp:
                    # At or above max, full speed
                    self.set_speed(100)
                else:
                    # Calculate proportional speed
                    temp_range = self.max_temp - self.min_temp
                    temp_offset = temp - self.min_temp
                    speed_range = 100 - self.min_speed

                    speed = self.min_speed + int((temp_offset / temp_range) * speed_range)
                    self.set_speed(speed)

            except Exception as e:
                logger.error(f"Auto control error: {e}")

            # Check every 5 seconds
            self._stop_auto.wait(timeout=5.0)

    def _get_cpu_temperature(self) -> Optional[float]:
        """Get CPU temperature in Celsius."""
        thermal_file = "/sys/class/thermal/thermal_zone0/temp"

        if os.path.exists(thermal_file):
            try:
                with open(thermal_file) as f:
                    temp_millicelsius = int(f.read().strip())
                    return temp_millicelsius / 1000.0
            except Exception:
                pass

        return None

    def get_temperature(self) -> Optional[float]:
        """Get current CPU temperature."""
        return self._get_cpu_temperature()

    def get_speed(self) -> int:
        """Get current fan speed."""
        return self._current_speed

    def get_status(self) -> dict:
        """Get fan status."""
        return {
            "speed_percent": self._current_speed,
            "auto_mode": self._auto_mode,
            "temperature": self._get_cpu_temperature(),
            "min_temp": self.min_temp,
            "max_temp": self.max_temp,
        }

    def cleanup(self) -> None:
        """Clean up GPIO resources."""
        self.disable_auto()

        if self._pwm:
            self._pwm.stop()

        if GPIO_AVAILABLE:
            try:
                GPIO.cleanup(self.pin)
            except Exception:
                pass

        logger.info("Fan controller cleaned up")

    def is_available(self) -> bool:
        """Check if fan control is available."""
        return self._pwm is not None

    def __del__(self):
        """Destructor to ensure cleanup."""
        try:
            self.cleanup()
        except Exception:
            pass
