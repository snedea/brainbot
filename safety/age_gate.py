"""
Age Gate and PIN System
========================
Manages age verification, parent PIN, and settings protection.
"""

import json
import secrets
from pathlib import Path
from typing import Optional, Dict
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta

try:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError
except ImportError:
    # Fallback to hashlib if argon2 not available
    import hashlib

    class PasswordHasher:
        def hash(self, password: str) -> str:
            salt = secrets.token_hex(16)
            return salt + ":" + hashlib.pbkdf2_hmac('sha256',
                                                     password.encode(),
                                                     salt.encode(),
                                                     100000).hex()

        def verify(self, hash_str: str, password: str) -> None:
            salt, hash_val = hash_str.split(":", 1)
            test_hash = hashlib.pbkdf2_hmac('sha256',
                                           password.encode(),
                                           salt.encode(),
                                           100000).hex()
            if test_hash != hash_val:
                raise VerifyMismatchError("Invalid password")

    class VerifyMismatchError(Exception):
        pass


from .policy import AgeBand


@dataclass
class ParentConfig:
    """Parent configuration settings."""
    age_band: AgeBand
    pin_hash: str
    created_at: str
    last_verified: Optional[str] = None
    transcript_enabled: bool = False
    safety_stats_enabled: bool = True
    max_session_minutes: int = 30
    daily_limit_minutes: int = 120


class AgeGate:
    """Manages age verification and parental controls."""

    CONFIG_FILE = Path.home() / ".brainbot" / "parent_config.json"
    MAX_PIN_ATTEMPTS = 3
    LOCKOUT_DURATION = timedelta(minutes=15)

    def __init__(self):
        self.ph = PasswordHasher()
        self.config: Optional[ParentConfig] = None
        self.failed_attempts = 0
        self.lockout_until: Optional[datetime] = None
        self._load_config()

    def _load_config(self) -> None:
        """Load parent configuration from file."""
        if self.CONFIG_FILE.exists():
            try:
                with open(self.CONFIG_FILE, 'r') as f:
                    data = json.load(f)
                    self.config = ParentConfig(**data)
            except (json.JSONDecodeError, TypeError):
                self.config = None

    def _save_config(self) -> None:
        """Save parent configuration to file."""
        if self.config:
            self.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(self.CONFIG_FILE, 'w') as f:
                json.dump(asdict(self.config), f, indent=2)
            # Set restrictive permissions (Unix-like systems)
            try:
                import os
                os.chmod(self.CONFIG_FILE, 0o600)
            except:
                pass

    def is_configured(self) -> bool:
        """Check if age gate has been configured."""
        return self.config is not None

    def needs_setup(self) -> bool:
        """Check if initial setup is needed."""
        return not self.is_configured()

    def setup(self, age_band: AgeBand, pin: str) -> bool:
        """Initial setup with age band and PIN.

        Args:
            age_band: The age band selection
            pin: Parent PIN (minimum 4 digits)

        Returns:
            True if setup successful
        """
        if len(pin) < 4:
            return False

        pin_hash = self.ph.hash(pin)

        self.config = ParentConfig(
            age_band=age_band,
            pin_hash=pin_hash,
            created_at=datetime.now().isoformat(),
        )

        self._save_config()
        return True

    def verify_pin(self, pin: str) -> bool:
        """Verify parent PIN.

        Returns:
            True if PIN is correct
        """
        if not self.config:
            return False

        # Check if locked out
        if self.lockout_until and datetime.now() < self.lockout_until:
            return False

        try:
            self.ph.verify(self.config.pin_hash, pin)
            self.failed_attempts = 0
            self.config.last_verified = datetime.now().isoformat()
            self._save_config()
            return True
        except VerifyMismatchError:
            self.failed_attempts += 1
            if self.failed_attempts >= self.MAX_PIN_ATTEMPTS:
                self.lockout_until = datetime.now() + self.LOCKOUT_DURATION
            return False

    def change_pin(self, current_pin: str, new_pin: str) -> bool:
        """Change parent PIN.

        Returns:
            True if PIN changed successfully
        """
        if not self.verify_pin(current_pin):
            return False

        if len(new_pin) < 4:
            return False

        self.config.pin_hash = self.ph.hash(new_pin)
        self._save_config()
        return True

    def get_age_band(self) -> AgeBand:
        """Get configured age band."""
        if self.config:
            return self.config.age_band
        return AgeBand.UNDER_13  # Default to strictest

    def get_settings(self, pin_verified: bool = False) -> Dict:
        """Get current settings (requires PIN for sensitive info)."""
        if not self.config:
            return {"configured": False}

        basic_info = {
            "configured": True,
            "age_band": self.config.age_band,
            "safety_stats_enabled": self.config.safety_stats_enabled,
            "max_session_minutes": self.config.max_session_minutes,
            "daily_limit_minutes": self.config.daily_limit_minutes,
        }

        if pin_verified:
            basic_info.update({
                "transcript_enabled": self.config.transcript_enabled,
                "created_at": self.config.created_at,
                "last_verified": self.config.last_verified,
            })

        return basic_info

    def update_settings(self, pin: str, **kwargs) -> bool:
        """Update settings (requires PIN).

        Args:
            pin: Parent PIN
            **kwargs: Settings to update

        Returns:
            True if settings updated
        """
        if not self.verify_pin(pin):
            return False

        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)

        self._save_config()
        return True

    def is_locked_out(self) -> bool:
        """Check if PIN entry is locked out."""
        return self.lockout_until and datetime.now() < self.lockout_until

    def get_lockout_remaining(self) -> int:
        """Get remaining lockout time in seconds."""
        if not self.is_locked_out():
            return 0
        return int((self.lockout_until - datetime.now()).total_seconds())