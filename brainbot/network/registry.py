"""Node registry for tracking online nodes in the network."""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from .models import (
    CapabilityManifest,
    HardwareCapability,
    NodePersona,
    NodeRegistryEntry,
)
from .storage import StorageClient

logger = logging.getLogger(__name__)


class NodeRegistry:
    """
    Registry of nodes in the BrainBot network.

    Stores node information in R2:
    - nodes/{node_id}/manifest.json - Hardware capabilities
    - nodes/{node_id}/persona.json - Node persona
    - nodes/{node_id}/heartbeat.json - Last heartbeat
    - registry/nodes.json - Cached registry (rebuilt periodically)
    """

    HEARTBEAT_TIMEOUT_SECONDS = 300  # 5 minutes

    def __init__(self, storage: StorageClient):
        """
        Initialize registry.

        Args:
            storage: Storage client for R2/S3
        """
        self.storage = storage
        self._cache: Optional[dict[str, NodeRegistryEntry]] = None
        self._cache_time: Optional[datetime] = None
        self._cache_ttl = timedelta(seconds=60)  # Cache for 1 minute

    def register(
        self,
        node_id: str,
        hostname: str,
        persona: NodePersona,
        manifest: CapabilityManifest,
        ip_address: Optional[str] = None,
    ) -> bool:
        """
        Register or update a node in the registry.

        Args:
            node_id: Unique node identifier
            hostname: Node hostname
            persona: Node persona
            manifest: Hardware manifest
            ip_address: Optional IP address

        Returns:
            True if successful
        """
        # Store manifest
        manifest_key = f"nodes/{node_id}/manifest.json"
        if not self.storage.write(manifest_key, manifest.model_dump(mode="json")):
            return False

        # Store persona
        persona_key = f"nodes/{node_id}/persona.json"
        if not self.storage.write(persona_key, persona.model_dump(mode="json")):
            return False

        # Create registry entry
        entry = NodeRegistryEntry(
            node_id=node_id,
            hostname=hostname,
            persona=persona,
            capabilities=[c.value for c in manifest.get_available_capabilities()],
            last_heartbeat=datetime.now(),
            status="online",
            ip_address=ip_address,
        )

        # Store heartbeat (also serves as initial registration)
        heartbeat_key = f"nodes/{node_id}/heartbeat.json"
        if not self.storage.write(heartbeat_key, entry.model_dump(mode="json")):
            return False

        # Invalidate cache
        self._cache = None

        logger.info(f"Registered node: {node_id} ({persona.display_name})")
        return True

    def heartbeat(
        self,
        node_id: str,
        status: str = "online",
        ip_address: Optional[str] = None,
    ) -> bool:
        """
        Update node heartbeat.

        Args:
            node_id: Node identifier
            status: Current status (online, degraded)
            ip_address: Current IP address

        Returns:
            True if successful
        """
        heartbeat_key = f"nodes/{node_id}/heartbeat.json"

        # Read existing entry
        existing = self.storage.read_json(heartbeat_key)
        if existing is None:
            logger.warning(f"Heartbeat for unregistered node: {node_id}")
            return False

        try:
            entry = NodeRegistryEntry(**existing)
        except Exception as e:
            logger.error(f"Failed to parse registry entry: {e}")
            return False

        # Update heartbeat
        entry.last_heartbeat = datetime.now()
        entry.status = status
        if ip_address:
            entry.ip_address = ip_address
            entry.last_seen_from = ip_address

        # Write back
        if not self.storage.write(heartbeat_key, entry.model_dump(mode="json")):
            return False

        logger.debug(f"Heartbeat from {node_id}")
        return True

    def get_node(self, node_id: str) -> Optional[NodeRegistryEntry]:
        """Get a specific node's registry entry."""
        heartbeat_key = f"nodes/{node_id}/heartbeat.json"
        data = self.storage.read_json(heartbeat_key)
        if data is None:
            return None

        try:
            return NodeRegistryEntry(**data)
        except Exception as e:
            logger.warning(f"Failed to parse node {node_id}: {e}")
            return None

    def get_all_nodes(self, include_offline: bool = False) -> list[NodeRegistryEntry]:
        """
        Get all registered nodes.

        Args:
            include_offline: If True, include nodes that haven't heartbeated recently

        Returns:
            List of node registry entries
        """
        # Check cache
        if self._cache is not None and self._cache_time is not None:
            if datetime.now() - self._cache_time < self._cache_ttl:
                entries = list(self._cache.values())
                if not include_offline:
                    entries = [e for e in entries if e.is_online(self.HEARTBEAT_TIMEOUT_SECONDS)]
                return entries

        # Rebuild from storage
        entries = []
        prefix = "nodes/"
        keys = self.storage.list_keys(prefix, max_keys=1000)

        # Group by node_id and find heartbeat files
        seen_nodes = set()
        for key in keys:
            if "/heartbeat.json" not in key:
                continue

            # Extract node_id from path
            parts = key.split("/")
            if len(parts) >= 2:
                node_id = parts[1]
                if node_id in seen_nodes:
                    continue
                seen_nodes.add(node_id)

                entry = self.get_node(node_id)
                if entry:
                    entries.append(entry)

        # Update cache
        self._cache = {e.node_id: e for e in entries}
        self._cache_time = datetime.now()

        # Persist cache to registry/nodes.json for quick network overview
        self._write_registry_cache()

        if not include_offline:
            entries = [e for e in entries if e.is_online(self.HEARTBEAT_TIMEOUT_SECONDS)]

        return entries

    def _write_registry_cache(self) -> bool:
        """
        Write the registry cache to registry/nodes.json.

        This provides a quick overview of all nodes without
        needing to scan individual node directories.

        Returns:
            True if successful
        """
        if self._cache is None:
            return False

        try:
            registry_data = {
                "updated_at": datetime.now().isoformat(),
                "node_count": len(self._cache),
                "nodes": {
                    node_id: entry.model_dump(mode="json")
                    for node_id, entry in self._cache.items()
                },
            }

            if self.storage.write("registry/nodes.json", registry_data):
                logger.debug(f"Registry cache written: {len(self._cache)} nodes")
                return True
            else:
                logger.warning("Failed to write registry cache")
                return False

        except Exception as e:
            logger.error(f"Error writing registry cache: {e}")
            return False

    def read_registry_cache(self) -> Optional[dict]:
        """
        Read the cached registry from registry/nodes.json.

        This can be used for quick lookups without scanning
        individual node directories.

        Returns:
            Registry data dict or None
        """
        data = self.storage.read_json("registry/nodes.json")
        if data is None:
            return None

        # Populate cache from file if our in-memory cache is stale
        if self._cache is None:
            try:
                nodes_data = data.get("nodes", {})
                self._cache = {
                    node_id: NodeRegistryEntry(**node_data)
                    for node_id, node_data in nodes_data.items()
                }
                self._cache_time = datetime.now()
            except Exception as e:
                logger.warning(f"Failed to parse registry cache: {e}")

        return data

    def get_online_nodes(self) -> list[NodeRegistryEntry]:
        """Get nodes that have heartbeated within the timeout period."""
        return self.get_all_nodes(include_offline=False)

    def find_nodes_with_capability(
        self,
        capability: HardwareCapability,
        only_online: bool = True,
    ) -> list[NodeRegistryEntry]:
        """
        Find nodes that have a specific capability.

        Args:
            capability: The capability to search for
            only_online: If True, only return online nodes

        Returns:
            List of matching nodes
        """
        all_nodes = self.get_all_nodes(include_offline=not only_online)
        cap_value = capability.value

        matching = []
        for node in all_nodes:
            if cap_value in node.capabilities:
                matching.append(node)

        return matching

    def find_nodes_with_capabilities(
        self,
        capabilities: list[HardwareCapability],
        require_all: bool = True,
        only_online: bool = True,
    ) -> list[NodeRegistryEntry]:
        """
        Find nodes that have specific capabilities.

        Args:
            capabilities: List of required capabilities
            require_all: If True, node must have all capabilities
            only_online: If True, only return online nodes

        Returns:
            List of matching nodes
        """
        all_nodes = self.get_all_nodes(include_offline=not only_online)
        cap_values = {c.value for c in capabilities}

        matching = []
        for node in all_nodes:
            node_caps = set(node.capabilities)

            if require_all:
                if cap_values.issubset(node_caps):
                    matching.append(node)
            else:
                if cap_values.intersection(node_caps):
                    matching.append(node)

        return matching

    def mark_offline(self, node_id: str) -> bool:
        """Mark a node as offline."""
        return self.heartbeat(node_id, status="offline")

    def remove_node(self, node_id: str) -> bool:
        """
        Remove a node from the registry.

        Args:
            node_id: Node to remove

        Returns:
            True if successful
        """
        prefix = f"nodes/{node_id}/"
        keys = self.storage.list_keys(prefix)

        success = True
        for key in keys:
            if not self.storage.delete(key):
                success = False

        # Invalidate cache
        self._cache = None

        logger.info(f"Removed node: {node_id}")
        return success

    def get_manifest(self, node_id: str) -> Optional[CapabilityManifest]:
        """Get a node's hardware manifest."""
        key = f"nodes/{node_id}/manifest.json"
        data = self.storage.read_json(key)
        if data is None:
            return None

        try:
            return CapabilityManifest(**data)
        except Exception as e:
            logger.warning(f"Failed to parse manifest for {node_id}: {e}")
            return None

    def get_persona(self, node_id: str) -> Optional[NodePersona]:
        """Get a node's persona."""
        key = f"nodes/{node_id}/persona.json"
        data = self.storage.read_json(key)
        if data is None:
            return None

        try:
            return NodePersona(**data)
        except Exception as e:
            logger.warning(f"Failed to parse persona for {node_id}: {e}")
            return None

    def invalidate_cache(self) -> None:
        """Force cache invalidation."""
        self._cache = None
        self._cache_time = None


def format_registry_display(nodes: list[NodeRegistryEntry]) -> str:
    """Format registry for CLI display."""
    if not nodes:
        return "No nodes registered"

    lines = [
        "BrainBot Network Nodes",
        "=" * 60,
        "",
    ]

    for node in nodes:
        status_icon = "*" if node.is_online(300) else " "
        lines.append(f"{status_icon} {node.persona.display_name}")
        lines.append(f"  ID:       {node.node_id[:8]}...")
        lines.append(f"  Hostname: {node.hostname}")
        lines.append(f"  Role:     {node.persona.role}")
        lines.append(f"  Status:   {node.status}")

        if node.capabilities:
            caps = ", ".join(node.capabilities[:5])
            if len(node.capabilities) > 5:
                caps += f" (+{len(node.capabilities) - 5} more)"
            lines.append(f"  Caps:     {caps}")

        lines.append(f"  Last:     {node.last_heartbeat.strftime('%Y-%m-%d %H:%M')}")
        lines.append("")

    lines.append(f"Total: {len(nodes)} node(s)")
    online = sum(1 for n in nodes if n.is_online(300))
    lines.append(f"Online: {online}")

    return "\n".join(lines)
