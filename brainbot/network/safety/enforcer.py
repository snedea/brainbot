"""Policy enforcement for capability access."""

import logging
from datetime import datetime, time as dt_time
from pathlib import Path
from typing import Optional, Tuple

from ..models import HardwareCapability, UsagePolicy
from .policies import (
    CapabilityPolicy,
    SafetyPolicies,
    SafetyPoliciesManager,
    DEFAULT_POLICIES,
)

logger = logging.getLogger(__name__)


class PolicyEnforcer:
    """
    Enforces safety policies for capability access.

    Checks:
    - Usage policy (ALWAYS, SCHEDULED, EXPLICIT, NEVER, LOCAL_ONLY)
    - Task type restrictions
    - Schedule restrictions
    - Confirmation requirements
    """

    def __init__(
        self,
        config_dir: Path,
        confirmation_callback: Optional[callable] = None,
    ):
        """
        Initialize policy enforcer.

        Args:
            config_dir: Path to config directory
            confirmation_callback: Async function to request user confirmation
        """
        self.manager = SafetyPoliciesManager(config_dir)
        self.confirmation_callback = confirmation_callback

        # Pending confirmations (capability -> granted)
        self._pending_confirmations: dict[str, bool] = {}
        self._granted_until: dict[str, datetime] = {}

    def can_use(
        self,
        capability: HardwareCapability,
        task_type: Optional[str] = None,
        is_network_task: bool = False,
        is_explicit_request: bool = False,
    ) -> Tuple[bool, str]:
        """
        Check if a capability can be used.

        Args:
            capability: The capability to check
            task_type: Type of task requesting access
            is_network_task: Whether this is from a network task
            is_explicit_request: Whether user explicitly requested this

        Returns:
            Tuple of (allowed, reason)
        """
        policies = self.manager.load()

        # Check global network task setting
        if is_network_task and not policies.network_tasks_enabled:
            return False, "Network tasks are disabled"

        # Get policy for this capability
        policy = policies.get_policy(capability)
        if policy is None:
            # Check defaults
            policy = DEFAULT_POLICIES.get_policy(capability)

        if policy is None:
            # No policy = allowed
            return True, "No policy restrictions"

        # Check usage policy
        if policy.usage == UsagePolicy.NEVER:
            return False, policy.reason or "Capability is disabled"

        if policy.usage == UsagePolicy.LOCAL_ONLY and is_network_task:
            return False, "Capability is restricted to local use only"

        if policy.usage == UsagePolicy.SCHEDULED:
            if policy.schedule:
                current_time = datetime.now().time()
                if not policy.schedule.is_within(current_time):
                    return False, f"Outside scheduled hours ({policy.schedule.start} - {policy.schedule.end})"

        if policy.usage == UsagePolicy.EXPLICIT:
            if not is_explicit_request:
                # Check if we have a recent grant
                if self._check_recent_grant(capability):
                    pass  # OK, recently granted
                else:
                    return False, "Requires explicit user permission"

        # Check task type restrictions
        if task_type:
            if policy.blocked_task_types and task_type in policy.blocked_task_types:
                return False, f"Task type '{task_type}' is blocked for this capability"

            if policy.allowed_task_types and task_type not in policy.allowed_task_types:
                return False, f"Task type '{task_type}' is not in allowed list"

        # Check global confirmation requirement
        if policies.require_confirmation_for_all or policy.requires_confirmation:
            if not is_explicit_request and not self._check_recent_grant(capability):
                return False, "Requires user confirmation"

        return True, "Allowed by policy"

    def _check_recent_grant(self, capability: HardwareCapability) -> bool:
        """Check if capability was recently granted (within 5 minutes)."""
        granted_time = self._granted_until.get(capability.value)
        if granted_time and datetime.now() < granted_time:
            return True
        return False

    def grant_temporary(
        self,
        capability: HardwareCapability,
        duration_minutes: int = 5,
    ) -> None:
        """Grant temporary access to a capability."""
        from datetime import timedelta
        self._granted_until[capability.value] = datetime.now() + timedelta(minutes=duration_minutes)
        logger.info(f"Granted temporary access to {capability.value} for {duration_minutes} minutes")

    def revoke_grant(self, capability: HardwareCapability) -> None:
        """Revoke temporary grant for a capability."""
        if capability.value in self._granted_until:
            del self._granted_until[capability.value]

    async def request_confirmation(
        self,
        capability: HardwareCapability,
        task_description: str,
    ) -> bool:
        """
        Request user confirmation for capability access.

        Args:
            capability: The capability being requested
            task_description: Description of what will be done

        Returns:
            True if user confirms
        """
        if self.confirmation_callback is None:
            logger.warning("No confirmation callback configured")
            return False

        try:
            granted = await self.confirmation_callback(
                capability=capability.value,
                description=task_description,
            )

            if granted:
                self.grant_temporary(capability)

            return granted

        except Exception as e:
            logger.error(f"Confirmation request failed: {e}")
            return False

    def check_and_request(
        self,
        capability: HardwareCapability,
        task_type: Optional[str] = None,
        task_description: str = "",
        is_network_task: bool = False,
    ) -> Tuple[bool, str]:
        """
        Check policy and request confirmation if needed (sync version).

        For async confirmation, use can_use() + request_confirmation().

        Args:
            capability: The capability to check
            task_type: Type of task
            task_description: Description for confirmation prompt
            is_network_task: Whether from network

        Returns:
            Tuple of (allowed, reason)
        """
        allowed, reason = self.can_use(
            capability=capability,
            task_type=task_type,
            is_network_task=is_network_task,
            is_explicit_request=False,
        )

        if not allowed and "confirmation" in reason.lower():
            # Could request confirmation here if we had a sync callback
            return False, "Confirmation required - use explicit request"

        return allowed, reason

    def get_all_policies(self) -> SafetyPolicies:
        """Get all current policies."""
        return self.manager.load()

    def disable_capability(
        self,
        capability: HardwareCapability,
        reason: str = "Disabled by user",
    ) -> bool:
        """Disable a capability."""
        return self.manager.disable_capability(capability, reason)

    def enable_capability(
        self,
        capability: HardwareCapability,
        require_confirmation: bool = False,
    ) -> bool:
        """Enable a capability."""
        return self.manager.enable_capability(capability, require_confirmation)

    def reset_capability(self, capability: HardwareCapability) -> bool:
        """Reset a capability to default policy."""
        return self.manager.reset_policy(capability)

    def get_restricted_capabilities(self) -> list[str]:
        """Get list of capabilities with restrictions."""
        policies = self.manager.load()
        restricted = []

        for cap, policy in policies.policies.items():
            if policy.usage != UsagePolicy.ALWAYS:
                restricted.append(cap)

        return restricted

    def get_disabled_capabilities(self) -> list[str]:
        """Get list of disabled capabilities."""
        policies = self.manager.load()
        disabled = []

        for cap, policy in policies.policies.items():
            if policy.usage == UsagePolicy.NEVER:
                disabled.append(cap)

        return disabled


def create_default_enforcer(config_dir: Path) -> PolicyEnforcer:
    """Create a policy enforcer with default settings."""
    return PolicyEnforcer(config_dir)
