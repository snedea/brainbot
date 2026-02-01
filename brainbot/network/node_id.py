"""Node identity management for BrainBot network."""

import hashlib
import json
import logging
import socket
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import NodeIdentity

logger = logging.getLogger(__name__)


class NodeIdManager:
    """
    Manages unique node identity.

    - Generates UUID v4 on first boot
    - Persists to ~/.brainbot/config/node_id.json
    - Creates machine fingerprint from system identifiers
    """

    def __init__(self, config_dir: Path):
        """
        Initialize node ID manager.

        Args:
            config_dir: Path to config directory (e.g., ~/.brainbot/config)
        """
        self.config_dir = config_dir
        self.id_file = config_dir / "node_id.json"
        self._identity: Optional[NodeIdentity] = None

    def get_identity(self) -> NodeIdentity:
        """Get or create node identity."""
        if self._identity is None:
            self._identity = self._load_or_create()
        return self._identity

    def _load_or_create(self) -> NodeIdentity:
        """Load existing identity or create new one."""
        if self.id_file.exists():
            try:
                data = json.loads(self.id_file.read_text())
                identity = NodeIdentity(**data)

                # Update last boot time
                identity.last_boot = datetime.now()
                self._save(identity)

                logger.info(f"Loaded node identity: {identity.node_id}")
                return identity
            except Exception as e:
                logger.warning(f"Failed to load node identity: {e}")

        # Create new identity
        return self._create_new()

    def _create_new(self) -> NodeIdentity:
        """Create a new node identity."""
        node_id = str(uuid.uuid4())
        hostname = socket.gethostname()
        fingerprint = self._generate_fingerprint()

        identity = NodeIdentity(
            node_id=node_id,
            hostname=hostname,
            machine_fingerprint=fingerprint,
            created_at=datetime.now(),
            last_boot=datetime.now(),
        )

        self._save(identity)
        logger.info(f"Created new node identity: {node_id}")
        return identity

    def _save(self, identity: NodeIdentity) -> None:
        """Save identity to disk."""
        self.config_dir.mkdir(parents=True, exist_ok=True)

        data = identity.model_dump(mode="json")
        self.id_file.write_text(json.dumps(data, indent=2, default=str))

    def _generate_fingerprint(self) -> str:
        """
        Generate a machine fingerprint from system identifiers.

        Uses multiple sources to create a stable identifier:
        - /etc/machine-id (Linux)
        - IOPlatformUUID (macOS)
        - Hostname + MAC address (fallback)
        """
        fingerprint_sources = []

        # Try /etc/machine-id (Linux)
        machine_id_path = Path("/etc/machine-id")
        if machine_id_path.exists():
            try:
                machine_id = machine_id_path.read_text().strip()
                if machine_id:
                    fingerprint_sources.append(f"machine_id:{machine_id}")
            except Exception:
                pass

        # Try macOS IOPlatformUUID
        try:
            import subprocess

            result = subprocess.run(
                [
                    "ioreg",
                    "-rd1",
                    "-c",
                    "IOPlatformExpertDevice",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                for line in result.stdout.split("\n"):
                    if "IOPlatformUUID" in line:
                        # Extract UUID from line like: "IOPlatformUUID" = "..."
                        parts = line.split("=")
                        if len(parts) > 1:
                            platform_uuid = parts[1].strip().strip('"')
                            fingerprint_sources.append(f"platform_uuid:{platform_uuid}")
                            break
        except Exception:
            pass

        # Try Raspberry Pi serial number
        try:
            cpuinfo_path = Path("/proc/cpuinfo")
            if cpuinfo_path.exists():
                content = cpuinfo_path.read_text()
                for line in content.split("\n"):
                    if line.startswith("Serial"):
                        serial = line.split(":")[1].strip()
                        fingerprint_sources.append(f"pi_serial:{serial}")
                        break
        except Exception:
            pass

        # Fallback: hostname + primary MAC address
        hostname = socket.gethostname()
        fingerprint_sources.append(f"hostname:{hostname}")

        try:
            import uuid as uuid_mod

            mac = uuid_mod.getnode()
            mac_str = ":".join(f"{(mac >> i) & 0xff:02x}" for i in range(0, 48, 8))
            fingerprint_sources.append(f"mac:{mac_str}")
        except Exception:
            pass

        # Hash all sources together
        fingerprint_data = "|".join(sorted(fingerprint_sources))
        fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()[:32]

        return fingerprint

    def reset(self) -> NodeIdentity:
        """Reset and regenerate node identity."""
        if self.id_file.exists():
            self.id_file.unlink()

        self._identity = None
        return self.get_identity()

    @property
    def node_id(self) -> str:
        """Get the node ID string."""
        return self.get_identity().node_id

    @property
    def hostname(self) -> str:
        """Get the hostname."""
        return self.get_identity().hostname
