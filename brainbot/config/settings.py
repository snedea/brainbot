"""BrainBot settings management using Pydantic."""

import json
import logging
from pathlib import Path
from typing import Any, Optional
from datetime import time as dt_time

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

from .defaults import DEFAULT_CONFIG, DEFAULT_HARDWARE_CONFIG, DEFAULT_DATA_DIR

logger = logging.getLogger(__name__)


class ScheduleConfig(BaseModel):
    """Schedule configuration."""
    wake_time: str = Field(default="07:00", description="Wake time in HH:MM format")
    sleep_time: str = Field(default="00:00", description="Sleep time in HH:MM format")
    morning_routine_duration_minutes: int = Field(default=15)
    bedtime_story_time: str = Field(default="23:30")
    evening_reflection_time: str = Field(default="23:55")

    def get_wake_time(self) -> dt_time:
        """Parse wake time string to time object."""
        h, m = map(int, self.wake_time.split(":"))
        return dt_time(h, m)

    def get_sleep_time(self) -> dt_time:
        """Parse sleep time string to time object."""
        h, m = map(int, self.sleep_time.split(":"))
        return dt_time(h, m)

    def get_bedtime_story_time(self) -> dt_time:
        """Parse bedtime story time string to time object."""
        h, m = map(int, self.bedtime_story_time.split(":"))
        return dt_time(h, m)

    def get_evening_reflection_time(self) -> dt_time:
        """Parse evening reflection time string to time object."""
        h, m = map(int, self.evening_reflection_time.split(":"))
        return dt_time(h, m)


class LCD1InchConfig(BaseModel):
    """1-inch OLED display configuration."""
    enabled: bool = False
    i2c_address: int = 0x3C
    width: int = 128
    height: int = 64


class LCD5InchConfig(BaseModel):
    """5-inch display configuration."""
    enabled: bool = False
    spi_port: int = 0
    spi_device: int = 0
    width: int = 800
    height: int = 480


class LEDConfig(BaseModel):
    """LED/NeoPixel configuration."""
    enabled: bool = False
    pin: int = 18
    num_pixels: int = 8
    brightness: float = 0.5


class FanConfig(BaseModel):
    """PWM fan configuration."""
    enabled: bool = False
    pin: int = 12
    min_temp: int = 40
    max_temp: int = 70


class HardwareConfig(BaseModel):
    """Hardware configuration."""
    lcd_1inch: LCD1InchConfig = Field(default_factory=LCD1InchConfig)
    lcd_5inch: LCD5InchConfig = Field(default_factory=LCD5InchConfig)
    led: LEDConfig = Field(default_factory=LEDConfig)
    fan: FanConfig = Field(default_factory=FanConfig)


class NetworkConfig(BaseModel):
    """Network/distributed configuration."""
    enabled: bool = False

    # R2 (primary storage - Cloudflare edge)
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = "brainbot-network"

    # S3 (backup storage - cold backup)
    s3_bucket: str = "brainbot-backup"
    s3_region: str = "us-east-1"
    s3_access_key_id: str = ""  # If empty, uses R2 credentials
    s3_secret_access_key: str = ""  # If empty, uses R2 credentials

    # Sync intervals
    heartbeat_interval_seconds: int = 60
    sync_interval_seconds: int = 300

    @property
    def s3_configured(self) -> bool:
        """Check if S3 is configured (at least bucket specified)."""
        return bool(self.s3_bucket)

    def get_s3_access_key(self) -> str:
        """Get S3 access key (falls back to R2 if not specified)."""
        return self.s3_access_key_id or self.r2_access_key_id

    def get_s3_secret_key(self) -> str:
        """Get S3 secret key (falls back to R2 if not specified)."""
        return self.s3_secret_access_key or self.r2_secret_access_key


class Settings(BaseSettings):
    """BrainBot settings with Pydantic validation."""

    # Paths
    data_dir: Path = Field(default=DEFAULT_DATA_DIR)

    # Core settings
    timezone: str = Field(default="America/Chicago")
    tick_interval_seconds: int = Field(default=30)

    # Schedule
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)

    # Activity settings
    max_session_minutes: int = Field(default=60)
    default_model: str = Field(default="sonnet")
    complex_model: str = Field(default="opus")

    # Content settings
    content_rating: str = Field(default="PG-13")
    allowed_themes: list[str] = Field(default_factory=lambda: DEFAULT_CONFIG["allowed_themes"])

    # Logging
    log_level: str = Field(default="INFO")

    # Hardware
    hardware: HardwareConfig = Field(default_factory=HardwareConfig)

    # Network (distributed mode)
    network: NetworkConfig = Field(default_factory=NetworkConfig)

    model_config = {
        "env_prefix": "BRAINBOT_",
    }

    @property
    def config_dir(self) -> Path:
        """Config directory path."""
        return self.data_dir / "config"

    @property
    def state_dir(self) -> Path:
        """State directory path."""
        return self.data_dir / "state"

    @property
    def log_dir(self) -> Path:
        """Log directory path."""
        return self.data_dir / "logs"

    @property
    def projects_dir(self) -> Path:
        """Projects directory path."""
        return self.data_dir / "projects"

    @property
    def stories_dir(self) -> Path:
        """Bedtime stories directory path."""
        return self.data_dir / "bedtime_stories"

    @property
    def journal_dir(self) -> Path:
        """Journal directory path."""
        return self.state_dir / "journal"

    @property
    def goals_dir(self) -> Path:
        """Goals directory path."""
        return self.state_dir / "goals"

    @property
    def pid_file(self) -> Path:
        """PID file path."""
        return self.data_dir / "brainbot.pid"

    @property
    def state_file(self) -> Path:
        """State file path."""
        return self.state_dir / "state.json"

    @property
    def memory_db(self) -> Path:
        """Memory database path."""
        return self.state_dir / "memory.db"

    @property
    def brain_dir(self) -> Path:
        """Brain directory for long-term memory files."""
        return self.data_dir / "brain"

    @property
    def claude_md_file(self) -> Path:
        """CLAUDE.md file path."""
        return self.config_dir / "CLAUDE.md"

    @property
    def config_file(self) -> Path:
        """Main config file path."""
        return self.config_dir / "config.json"

    @property
    def hardware_config_file(self) -> Path:
        """Hardware config file path."""
        return self.config_dir / "hardware.json"

    def ensure_directories(self) -> None:
        """Create all required directories if they don't exist."""
        dirs = [
            self.data_dir,
            self.config_dir,
            self.state_dir,
            self.log_dir,
            self.projects_dir,
            self.stories_dir,
            self.journal_dir,
            self.goals_dir,
            self.brain_dir,
            self.brain_dir / "active",
            self.brain_dir / "archive",
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> "Settings":
        """
        Load settings from config file, falling back to defaults.

        Args:
            config_path: Optional path to config file

        Returns:
            Settings instance
        """
        settings = cls()

        if config_path is None:
            config_path = settings.config_file

        if config_path.exists():
            try:
                with open(config_path) as f:
                    config_data = json.load(f)

                # Handle nested schedule config
                if "schedule" in config_data and isinstance(config_data["schedule"], dict):
                    config_data["schedule"] = ScheduleConfig(**config_data["schedule"])

                # Handle nested hardware config
                if "hardware" in config_data and isinstance(config_data["hardware"], dict):
                    hw = config_data["hardware"]
                    hw_config = HardwareConfig(
                        lcd_1inch=LCD1InchConfig(**hw.get("lcd_1inch", {})),
                        lcd_5inch=LCD5InchConfig(**hw.get("lcd_5inch", {})),
                        led=LEDConfig(**hw.get("led", {})),
                        fan=FanConfig(**hw.get("fan", {})),
                    )
                    config_data["hardware"] = hw_config

                # Handle nested network config
                if "network" in config_data and isinstance(config_data["network"], dict):
                    config_data["network"] = NetworkConfig(**config_data["network"])

                settings = cls(**config_data)
                logger.info(f"Loaded settings from {config_path}")
            except Exception as e:
                logger.warning(f"Failed to load settings from {config_path}: {e}")

        # Load network config from separate file if it exists
        network_file = settings.config_dir / "network.json"
        if network_file.exists():
            try:
                with open(network_file) as f:
                    network_data = json.load(f)
                settings.network = NetworkConfig(**network_data)
                logger.debug("Loaded network config")
            except Exception as e:
                logger.warning(f"Failed to load network config: {e}")

        return settings

    def save(self, config_path: Optional[Path] = None) -> None:
        """
        Save current settings to config file.

        Args:
            config_path: Optional path to save config
        """
        if config_path is None:
            config_path = self.config_file

        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert to dict, handling nested models
        data = self.model_dump(exclude={"data_dir"})

        with open(config_path, "w") as f:
            json.dump(data, f, indent=2, default=str)

        logger.info(f"Saved settings to {config_path}")
