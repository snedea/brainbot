"""Peer management for the BrainBot mesh network.

Tracks known peers, their health state, and manages peer discovery.
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class PeerState(str, Enum):
    """Health state of a peer."""

    ALIVE = "alive"          # Responding to heartbeats
    SUSPECTED = "suspected"  # Missed 1-2 heartbeats
    DEAD = "dead"            # Missed 3+ heartbeats, removed from active


@dataclass
class PeerInfo:
    """Information about a peer node in the mesh."""

    # Identity
    node_id: str
    address: str  # host:port (e.g., "192.168.1.100:7777")

    # Metadata
    hostname: str = ""
    persona_name: str = ""
    capabilities: list[str] = field(default_factory=list)
    version: str = ""

    # Health tracking
    state: PeerState = PeerState.ALIVE
    last_seen: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    missed_heartbeats: int = 0

    # Sync tracking
    last_sync: float = 0.0
    sync_version: int = 0  # Their latest known version

    # Discovery metadata
    discovered_at: float = field(default_factory=time.time)
    discovered_via: str = ""  # "seed", "gossip", "announce"

    def update_heartbeat(self) -> None:
        """Record a successful heartbeat."""
        previous_state = self.state
        self.last_heartbeat = time.time()
        self.last_seen = time.time()
        self.missed_heartbeats = 0
        self.state = PeerState.ALIVE
        if previous_state != PeerState.ALIVE:
            logger.info(f"Peer {self.node_id[:8]} ({self.address}) is back ALIVE")
        return previous_state  # Return previous state for resync detection

    def record_missed_heartbeat(self, max_missed: int = 3) -> None:
        """
        Record a missed heartbeat and update state.

        Args:
            max_missed: Number of missed heartbeats before marking DEAD
        """
        self.missed_heartbeats += 1

        if self.missed_heartbeats >= max_missed:
            if self.state != PeerState.DEAD:
                logger.warning(f"Peer {self.node_id[:8]} ({self.address}) is now DEAD")
            self.state = PeerState.DEAD
        elif self.missed_heartbeats >= 1:
            if self.state == PeerState.ALIVE:
                logger.info(f"Peer {self.node_id[:8]} ({self.address}) is SUSPECTED")
            self.state = PeerState.SUSPECTED

    def is_reachable(self) -> bool:
        """Check if peer is currently reachable."""
        return self.state in (PeerState.ALIVE, PeerState.SUSPECTED)

    def age_seconds(self) -> float:
        """Get seconds since last seen."""
        return time.time() - self.last_seen

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "node_id": self.node_id,
            "address": self.address,
            "hostname": self.hostname,
            "persona_name": self.persona_name,
            "capabilities": self.capabilities,
            "version": self.version,
            "state": self.state.value,
            "last_seen": self.last_seen,
            "last_heartbeat": self.last_heartbeat,
            "discovered_via": self.discovered_via,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PeerInfo":
        """Create from dictionary."""
        state = PeerState(data.get("state", "alive"))
        return cls(
            node_id=data["node_id"],
            address=data["address"],
            hostname=data.get("hostname", ""),
            persona_name=data.get("persona_name", ""),
            capabilities=data.get("capabilities", []),
            version=data.get("version", ""),
            state=state,
            last_seen=data.get("last_seen", time.time()),
            last_heartbeat=data.get("last_heartbeat", time.time()),
            discovered_via=data.get("discovered_via", ""),
        )


class PeerRegistry:
    """Thread-safe registry of known peers in the mesh network."""

    def __init__(self, local_node_id: str, max_missed_heartbeats: int = 3):
        """
        Initialize peer registry.

        Args:
            local_node_id: This node's ID (excluded from peer list)
            max_missed_heartbeats: Heartbeats missed before marking peer DEAD
        """
        self.local_node_id = local_node_id
        self.max_missed_heartbeats = max_missed_heartbeats
        self._peers: dict[str, PeerInfo] = {}  # node_id -> PeerInfo
        self._lock = threading.RLock()

    def add_peer(
        self,
        node_id: str,
        address: str,
        hostname: str = "",
        persona_name: str = "",
        capabilities: list[str] = None,
        version: str = "",
        discovered_via: str = "unknown",
    ) -> Optional[PeerInfo]:
        """
        Add or update a peer.

        Args:
            node_id: Peer's node ID
            address: Peer's address (host:port)
            hostname: Peer's hostname
            persona_name: Peer's persona/display name
            capabilities: Peer's hardware capabilities
            version: Peer's software version
            discovered_via: How we discovered this peer

        Returns:
            PeerInfo if added/updated, None if it's our own node
        """
        if node_id == self.local_node_id:
            return None

        with self._lock:
            if node_id in self._peers:
                # Update existing peer
                peer = self._peers[node_id]
                peer.address = address
                if hostname:
                    peer.hostname = hostname
                if persona_name:
                    peer.persona_name = persona_name
                if capabilities is not None:
                    peer.capabilities = capabilities
                if version:
                    peer.version = version
                peer.last_seen = time.time()
                logger.debug(f"Updated peer {node_id[:8]} at {address}")
            else:
                # New peer
                peer = PeerInfo(
                    node_id=node_id,
                    address=address,
                    hostname=hostname,
                    persona_name=persona_name,
                    capabilities=capabilities or [],
                    version=version,
                    discovered_via=discovered_via,
                )
                self._peers[node_id] = peer
                logger.info(f"Discovered new peer {node_id[:8]} ({persona_name or hostname}) at {address} via {discovered_via}")

            return peer

    def remove_peer(self, node_id: str) -> bool:
        """
        Remove a peer.

        Args:
            node_id: Peer's node ID

        Returns:
            True if removed, False if not found
        """
        with self._lock:
            if node_id in self._peers:
                peer = self._peers.pop(node_id)
                logger.info(f"Removed peer {node_id[:8]} ({peer.persona_name or peer.hostname})")
                return True
            return False

    def get_peer(self, node_id: str) -> Optional[PeerInfo]:
        """Get a specific peer by ID."""
        with self._lock:
            return self._peers.get(node_id)

    def get_peer_by_address(self, address: str) -> Optional[PeerInfo]:
        """Get a peer by address."""
        with self._lock:
            for peer in self._peers.values():
                if peer.address == address:
                    return peer
            return None

    def get_peer_by_name(self, name: str) -> Optional[PeerInfo]:
        """Get a peer by persona name or hostname (case-insensitive)."""
        name_lower = name.lower()
        with self._lock:
            for peer in self._peers.values():
                if (peer.persona_name.lower() == name_lower or
                    peer.hostname.lower() == name_lower):
                    return peer
            return None

    def get_all_peers(self) -> list[PeerInfo]:
        """Get all known peers."""
        with self._lock:
            return list(self._peers.values())

    def get_active_peers(self) -> list[PeerInfo]:
        """Get all peers that are currently reachable (ALIVE or SUSPECTED)."""
        with self._lock:
            return [p for p in self._peers.values() if p.is_reachable()]

    def get_alive_peers(self) -> list[PeerInfo]:
        """Get only peers that are ALIVE (not SUSPECTED or DEAD)."""
        with self._lock:
            return [p for p in self._peers.values() if p.state == PeerState.ALIVE]

    def get_dead_peers(self) -> list[PeerInfo]:
        """Get peers that are DEAD."""
        with self._lock:
            return [p for p in self._peers.values() if p.state == PeerState.DEAD]

    def update_heartbeat(self, node_id: str) -> tuple[bool, Optional[PeerState]]:
        """
        Update heartbeat for a peer.

        Args:
            node_id: Peer's node ID

        Returns:
            Tuple of (found, previous_state) - previous_state is set if peer was found
        """
        with self._lock:
            peer = self._peers.get(node_id)
            if peer:
                previous_state = peer.update_heartbeat()
                return True, previous_state
            return False, None

    def record_missed_heartbeat(self, node_id: str) -> bool:
        """
        Record a missed heartbeat for a peer.

        Args:
            node_id: Peer's node ID

        Returns:
            True if peer found and updated
        """
        with self._lock:
            peer = self._peers.get(node_id)
            if peer:
                peer.record_missed_heartbeat(max_missed=self.max_missed_heartbeats)
                return True
            return False

    def merge_peer_list(self, peers: list[dict], source: str = "gossip") -> int:
        """
        Merge a peer list from gossip into our registry.

        Args:
            peers: List of peer dictionaries
            source: Source of this peer list

        Returns:
            Number of new peers added
        """
        new_count = 0
        with self._lock:
            for peer_data in peers:
                node_id = peer_data.get("node_id")
                if not node_id or node_id == self.local_node_id:
                    continue

                if node_id not in self._peers:
                    new_count += 1

                self.add_peer(
                    node_id=node_id,
                    address=peer_data.get("address", ""),
                    hostname=peer_data.get("hostname", ""),
                    persona_name=peer_data.get("persona_name", ""),
                    capabilities=peer_data.get("capabilities", []),
                    version=peer_data.get("version", ""),
                    discovered_via=source,
                )

        if new_count > 0:
            logger.info(f"Merged {new_count} new peer(s) from {source}")
        return new_count

    def prune_dead_peers(self, max_age_seconds: float = 3600) -> int:
        """
        Remove peers that have been dead for too long.

        Args:
            max_age_seconds: Remove DEAD peers older than this

        Returns:
            Number of peers pruned
        """
        pruned = 0
        with self._lock:
            to_remove = []
            for node_id, peer in self._peers.items():
                if peer.state == PeerState.DEAD and peer.age_seconds() > max_age_seconds:
                    to_remove.append(node_id)

            for node_id in to_remove:
                self._peers.pop(node_id)
                pruned += 1

        if pruned > 0:
            logger.info(f"Pruned {pruned} stale dead peer(s)")
        return pruned

    def get_peer_list_for_gossip(self) -> list[dict]:
        """Get peer list formatted for gossip exchange."""
        with self._lock:
            # Include ourselves and all known peers
            peers = []
            for peer in self._peers.values():
                peers.append(peer.to_dict())
            return peers

    def get_quorum_status(self) -> tuple[str, int]:
        """
        Get quorum status based on number of active nodes.

        Returns:
            Tuple of (status_string, active_node_count)
        """
        active = len(self.get_active_peers())
        total = active + 1  # Include ourselves

        if total >= 3:
            return "quorum", total
        elif total == 2:
            return "pair", total
        else:
            return "standalone", total

    def __len__(self) -> int:
        """Get number of known peers."""
        with self._lock:
            return len(self._peers)

    def __contains__(self, node_id: str) -> bool:
        """Check if a peer is known."""
        with self._lock:
            return node_id in self._peers
