"""Safety policies for hardware capability access."""

import json
import logging
from datetime import time as dt_time
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from ..models import HardwareCapability, UsagePolicy

logger = logging.getLogger(__name__)


class TimeRange(BaseModel):
    """Time range for scheduled access."""

    start: str = "00:00"  # HH:MM format
    end: str = "23:59"

    def is_within(self, current_time: dt_time) -> bool:
        """Check if current time is within range."""
        start_h, start_m = map(int, self.start.split(":"))
        end_h, end_m = map(int, self.end.split(":"))

        start = dt_time(start_h, start_m)
        end = dt_time(end_h, end_m)

        if start <= end:
            return start <= current_time <= end
        else:
            # Range wraps around midnight
            return current_time >= start or current_time <= end


class CapabilityPolicy(BaseModel):
    """Policy for a specific capability."""

    capability: str  # HardwareCapability value
    usage: UsagePolicy = UsagePolicy.ALWAYS

    # Additional restrictions
    requires_confirmation: bool = False
    allowed_task_types: list[str] = Field(default_factory=list)  # Empty = all
    blocked_task_types: list[str] = Field(default_factory=list)

    # Scheduled access
    schedule: Optional[TimeRange] = None

    # User-provided reason for policy
    reason: Optional[str] = None

    # Network restrictions
    local_only: bool = False  # If True, only local tasks can use this

    class Config:
        use_enum_values = True


class SafetyPolicies(BaseModel):
    """Collection of safety policies for a node."""

    policies: dict[str, CapabilityPolicy] = Field(default_factory=dict)

    # Global settings
    require_confirmation_for_all: bool = False
    network_tasks_enabled: bool = True

    def get_policy(self, capability: HardwareCapability) -> Optional[CapabilityPolicy]:
        """Get policy for a capability."""
        return self.policies.get(capability.value)

    def set_policy(self, policy: CapabilityPolicy) -> None:
        """Set or update a policy."""
        self.policies[policy.capability] = policy

    def remove_policy(self, capability: HardwareCapability) -> bool:
        """Remove a policy (revert to default)."""
        if capability.value in self.policies:
            del self.policies[capability.value]
            return True
        return False


# Default policies for sensitive capabilities
DEFAULT_POLICIES = SafetyPolicies(
    policies={
        # Cameras require explicit consent
        HardwareCapability.CAMERA_USB.value: CapabilityPolicy(
            capability=HardwareCapability.CAMERA_USB.value,
            usage=UsagePolicy.EXPLICIT,
            requires_confirmation=True,
            allowed_task_types=["photo", "timelapse", "security"],
            reason="Camera access requires explicit user confirmation",
        ),
        HardwareCapability.CAMERA_PI.value: CapabilityPolicy(
            capability=HardwareCapability.CAMERA_PI.value,
            usage=UsagePolicy.EXPLICIT,
            requires_confirmation=True,
            allowed_task_types=["photo", "timelapse", "security"],
            reason="Camera access requires explicit user confirmation",
        ),
        # Microphone requires explicit consent
        HardwareCapability.MICROPHONE.value: CapabilityPolicy(
            capability=HardwareCapability.MICROPHONE.value,
            usage=UsagePolicy.EXPLICIT,
            requires_confirmation=True,
            allowed_task_types=["voice_command", "recording", "transcription"],
            reason="Microphone access requires explicit user confirmation",
        ),
    }
)


class SafetyPoliciesManager:
    """
    Manages safety policies with persistence.

    Policies are stored in:
    - ~/.brainbot/config/safety_policies.json - User overrides
    """

    def __init__(self, config_dir: Path):
        """
        Initialize policies manager.

        Args:
            config_dir: Path to config directory
        """
        self.config_dir = config_dir
        self.policies_file = config_dir / "safety_policies.json"
        self._policies: Optional[SafetyPolicies] = None

    def load(self) -> SafetyPolicies:
        """Load policies from disk, falling back to defaults."""
        if self._policies is not None:
            return self._policies

        # Start with defaults
        policies = DEFAULT_POLICIES.model_copy(deep=True)

        # Load overrides from file
        if self.policies_file.exists():
            try:
                data = json.loads(self.policies_file.read_text())
                overrides = SafetyPolicies(**data)

                # Merge overrides into defaults
                for cap, policy in overrides.policies.items():
                    policies.policies[cap] = policy

                policies.require_confirmation_for_all = overrides.require_confirmation_for_all
                policies.network_tasks_enabled = overrides.network_tasks_enabled

                logger.info(f"Loaded {len(overrides.policies)} policy overrides")
            except Exception as e:
                logger.warning(f"Failed to load policy overrides: {e}")

        self._policies = policies
        return policies

    def save(self) -> bool:
        """Save current policies to disk."""
        if self._policies is None:
            return False

        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            data = self._policies.model_dump(mode="json")
            self.policies_file.write_text(json.dumps(data, indent=2))
            return True
        except Exception as e:
            logger.error(f"Failed to save policies: {e}")
            return False

    def set_policy(
        self,
        capability: HardwareCapability,
        usage: UsagePolicy,
        requires_confirmation: bool = False,
        reason: Optional[str] = None,
    ) -> bool:
        """Set a policy for a capability."""
        policies = self.load()

        policy = CapabilityPolicy(
            capability=capability.value,
            usage=usage,
            requires_confirmation=requires_confirmation,
            reason=reason,
        )
        policies.set_policy(policy)

        return self.save()

    def reset_policy(self, capability: HardwareCapability) -> bool:
        """Reset a policy to default."""
        policies = self.load()
        policies.remove_policy(capability)
        return self.save()

    def disable_capability(
        self,
        capability: HardwareCapability,
        reason: str = "Disabled by user",
    ) -> bool:
        """Disable a capability entirely."""
        return self.set_policy(
            capability=capability,
            usage=UsagePolicy.NEVER,
            reason=reason,
        )

    def enable_capability(
        self,
        capability: HardwareCapability,
        require_confirmation: bool = False,
    ) -> bool:
        """Enable a capability."""
        usage = UsagePolicy.EXPLICIT if require_confirmation else UsagePolicy.ALWAYS
        return self.set_policy(
            capability=capability,
            usage=usage,
            requires_confirmation=require_confirmation,
        )

    def reload(self) -> SafetyPolicies:
        """Force reload from disk."""
        self._policies = None
        return self.load()


def format_policies_display(policies: SafetyPolicies) -> str:
    """Format policies for CLI display."""
    lines = [
        "Safety Policies",
        "=" * 50,
        "",
    ]

    if policies.require_confirmation_for_all:
        lines.append("! All capabilities require confirmation")
        lines.append("")

    if not policies.network_tasks_enabled:
        lines.append("! Network tasks disabled")
        lines.append("")

    if not policies.policies:
        lines.append("No custom policies (using defaults)")
    else:
        for cap, policy in sorted(policies.policies.items()):
            icon = {
                UsagePolicy.ALWAYS: "+",
                UsagePolicy.SCHEDULED: "~",
                UsagePolicy.EXPLICIT: "?",
                UsagePolicy.NEVER: "x",
                UsagePolicy.LOCAL_ONLY: "L",
            }.get(policy.usage, " ")

            lines.append(f"{icon} {cap}")
            lines.append(f"    Usage: {policy.usage}")

            if policy.requires_confirmation:
                lines.append("    Requires confirmation: Yes")

            if policy.allowed_task_types:
                lines.append(f"    Allowed tasks: {', '.join(policy.allowed_task_types)}")

            if policy.blocked_task_types:
                lines.append(f"    Blocked tasks: {', '.join(policy.blocked_task_types)}")

            if policy.schedule:
                lines.append(f"    Schedule: {policy.schedule.start} - {policy.schedule.end}")

            if policy.reason:
                lines.append(f"    Reason: {policy.reason}")

            lines.append("")

    return "\n".join(lines)
