"""BrainBot resource limits and safety constraints."""

import logging
import os
import psutil
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ResourceStatus:
    """Current resource usage status."""
    cpu_percent: float
    memory_percent: float
    memory_available_mb: float
    disk_percent: float
    disk_available_gb: float
    temperature: Optional[float] = None  # CPU temperature in Celsius
    is_within_limits: bool = True
    warnings: list[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class ResourceLimits:
    """
    Manages resource limits and safety constraints for BrainBot.

    Prevents excessive resource usage and provides safety boundaries.
    """

    # Default limits
    DEFAULT_CPU_LIMIT = 80.0  # Percent
    DEFAULT_MEMORY_LIMIT = 80.0  # Percent
    DEFAULT_DISK_LIMIT = 90.0  # Percent
    DEFAULT_TEMP_LIMIT = 70.0  # Celsius

    # Session limits
    DEFAULT_MAX_SESSION_MINUTES = 60
    DEFAULT_MAX_API_CALLS_PER_HOUR = 100
    DEFAULT_MAX_PROJECTS_PER_DAY = 5

    def __init__(
        self,
        cpu_limit: float = DEFAULT_CPU_LIMIT,
        memory_limit: float = DEFAULT_MEMORY_LIMIT,
        disk_limit: float = DEFAULT_DISK_LIMIT,
        temp_limit: float = DEFAULT_TEMP_LIMIT,
        max_session_minutes: int = DEFAULT_MAX_SESSION_MINUTES,
        max_api_calls_per_hour: int = DEFAULT_MAX_API_CALLS_PER_HOUR,
        max_projects_per_day: int = DEFAULT_MAX_PROJECTS_PER_DAY,
    ):
        """
        Initialize resource limits.

        Args:
            cpu_limit: Maximum CPU usage percent
            memory_limit: Maximum memory usage percent
            disk_limit: Maximum disk usage percent
            temp_limit: Maximum CPU temperature in Celsius
            max_session_minutes: Maximum Claude session duration
            max_api_calls_per_hour: Maximum API calls per hour
            max_projects_per_day: Maximum new projects per day
        """
        self.cpu_limit = cpu_limit
        self.memory_limit = memory_limit
        self.disk_limit = disk_limit
        self.temp_limit = temp_limit
        self.max_session_minutes = max_session_minutes
        self.max_api_calls_per_hour = max_api_calls_per_hour
        self.max_projects_per_day = max_projects_per_day

        # Track usage
        self._api_calls_this_hour: list[float] = []  # Timestamps
        self._projects_today: int = 0

    def check_resources(self) -> ResourceStatus:
        """
        Check current resource usage.

        Returns:
            ResourceStatus with current usage and any warnings
        """
        warnings = []
        is_within_limits = True

        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)
        if cpu_percent > self.cpu_limit:
            warnings.append(f"CPU usage high: {cpu_percent:.1f}%")
            is_within_limits = False

        # Memory usage
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        memory_available_mb = memory.available / (1024 * 1024)
        if memory_percent > self.memory_limit:
            warnings.append(f"Memory usage high: {memory_percent:.1f}%")
            is_within_limits = False

        # Disk usage
        disk = psutil.disk_usage("/")
        disk_percent = disk.percent
        disk_available_gb = disk.free / (1024 * 1024 * 1024)
        if disk_percent > self.disk_limit:
            warnings.append(f"Disk usage high: {disk_percent:.1f}%")
            is_within_limits = False

        # Temperature (Raspberry Pi specific)
        temperature = self._get_cpu_temperature()
        if temperature and temperature > self.temp_limit:
            warnings.append(f"CPU temperature high: {temperature:.1f}°C")
            is_within_limits = False

        if warnings:
            for w in warnings:
                logger.warning(f"Resource limit: {w}")

        return ResourceStatus(
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            memory_available_mb=memory_available_mb,
            disk_percent=disk_percent,
            disk_available_gb=disk_available_gb,
            temperature=temperature,
            is_within_limits=is_within_limits,
            warnings=warnings,
        )

    def can_start_activity(self) -> tuple[bool, Optional[str]]:
        """
        Check if we can start a new activity.

        Returns:
            Tuple of (can_start, reason_if_not)
        """
        # Check resources
        status = self.check_resources()
        if not status.is_within_limits:
            return False, f"Resource limits exceeded: {', '.join(status.warnings)}"

        # Check API rate limit
        import time
        now = time.time()
        hour_ago = now - 3600

        # Clean old calls
        self._api_calls_this_hour = [t for t in self._api_calls_this_hour if t > hour_ago]

        if len(self._api_calls_this_hour) >= self.max_api_calls_per_hour:
            return False, f"API rate limit reached ({self.max_api_calls_per_hour}/hour)"

        return True, None

    def can_start_project(self) -> tuple[bool, Optional[str]]:
        """
        Check if we can start a new project today.

        Returns:
            Tuple of (can_start, reason_if_not)
        """
        if self._projects_today >= self.max_projects_per_day:
            return False, f"Daily project limit reached ({self.max_projects_per_day}/day)"

        return self.can_start_activity()

    def record_api_call(self) -> None:
        """Record an API call for rate limiting."""
        import time
        self._api_calls_this_hour.append(time.time())

    def record_project_started(self) -> None:
        """Record a new project started."""
        self._projects_today += 1

    def reset_daily_counters(self) -> None:
        """Reset daily counters (call at midnight/wake)."""
        self._projects_today = 0
        logger.info("Daily resource counters reset")

    def _get_cpu_temperature(self) -> Optional[float]:
        """
        Get CPU temperature (Raspberry Pi specific).

        Returns:
            Temperature in Celsius, or None if not available
        """
        # Try Raspberry Pi thermal zone
        thermal_file = "/sys/class/thermal/thermal_zone0/temp"
        if os.path.exists(thermal_file):
            try:
                with open(thermal_file) as f:
                    temp_millicelsius = int(f.read().strip())
                    return temp_millicelsius / 1000.0
            except Exception:
                pass

        # Try psutil sensors
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                for name, entries in temps.items():
                    for entry in entries:
                        if entry.current:
                            return entry.current
        except Exception:
            pass

        return None

    def get_recommended_fan_speed(self) -> int:
        """
        Get recommended fan speed based on temperature.

        Returns:
            Fan speed 0-100 percent
        """
        temp = self._get_cpu_temperature()
        if temp is None:
            return 30  # Default low speed

        if temp < 40:
            return 0
        elif temp < 50:
            return 30
        elif temp < 60:
            return 50
        elif temp < 70:
            return 75
        else:
            return 100
