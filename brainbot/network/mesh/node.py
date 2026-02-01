"""MeshNode - Main coordinator for the P2P mesh network.

Coordinates all mesh components:
- PeerRegistry for tracking known peers
- VersionedStore for synced data
- GossipProtocol for peer discovery
- SyncProtocol for data synchronization
- MeshServer for handling incoming requests
"""

import logging
import socket
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from .peer import PeerRegistry
from .store import VersionedStore
from .gossip import GossipProtocol
from .sync import SyncProtocol, BrainMemorySync
from .transport import MeshServer, MeshClient

logger = logging.getLogger(__name__)


class MeshNode:
    """
    A node in the BrainBot mesh network.

    Main coordinator that manages all mesh components and
    provides a unified interface for mesh operations.
    """

    def __init__(
        self,
        node_id: str,
        hostname: str = "",
        persona_name: str = "",
        capabilities: list[str] = None,
        version: str = "",
        listen_port: int = 7777,
        listen_host: str = "0.0.0.0",
        advertise_address: str = "",
        seed_peers: list[str] = None,
        data_dir: Optional[Path] = None,
        brain_dir: Optional[Path] = None,
        gossip_interval: float = 30.0,
        heartbeat_interval: float = 10.0,
        sync_interval: float = 60.0,
        max_missed_heartbeats: int = 3,
        on_chat: Callable[[str, str], str] = None,
        on_task: Callable[[dict], dict] = None,
    ):
        """
        Initialize a mesh node.

        Args:
            node_id: Unique identifier for this node
            hostname: This node's hostname
            persona_name: Display name for this node
            capabilities: List of hardware capabilities
            version: Software version string
            listen_port: Port to listen on
            listen_host: Host to bind to
            advertise_address: Address to advertise to peers (host:port)
            seed_peers: Initial peers to bootstrap from
            data_dir: Directory for persistent data
            brain_dir: Directory for brain memories (for import)
            gossip_interval: Seconds between gossip rounds
            heartbeat_interval: Seconds between heartbeats
            sync_interval: Seconds between sync rounds
            max_missed_heartbeats: Missed heartbeats before marking peer DEAD
            on_chat: Callback for chat messages (message, source) -> response
            on_task: Callback for tasks (task_dict) -> result_dict
        """
        self.node_id = node_id
        self.hostname = hostname or socket.gethostname()
        self.persona_name = persona_name or self.hostname
        self.capabilities = capabilities or []
        self.version = version

        self.listen_port = listen_port
        self.listen_host = listen_host

        # Determine advertise address
        if advertise_address:
            self.advertise_address = advertise_address
        else:
            # Try to get a usable IP address
            self.advertise_address = f"{self._get_local_ip()}:{listen_port}"

        self.seed_peers = seed_peers or []
        self.data_dir = Path(data_dir) if data_dir else None
        self.brain_dir = Path(brain_dir) if brain_dir else None

        # Callbacks
        self.on_chat = on_chat
        self.on_task = on_task

        # Initialize components
        self.peers = PeerRegistry(node_id, max_missed_heartbeats=max_missed_heartbeats)
        self.store = VersionedStore(
            node_id=node_id,
            data_dir=self.data_dir,
            persist=self.data_dir is not None,
        )

        self.server = MeshServer(
            node=self,
            host=listen_host,
            port=listen_port,
        )

        self.gossip = GossipProtocol(
            node=self,
            seed_peers=self.seed_peers,
            gossip_interval=gossip_interval,
            heartbeat_interval=heartbeat_interval,
            max_missed_heartbeats=max_missed_heartbeats,
        )

        self.sync = SyncProtocol(
            node=self,
            sync_interval=sync_interval,
        )

        # Brain memory sync helper
        self.brain_sync = BrainMemorySync(
            node=self,
            brain_dir=str(brain_dir) if brain_dir else None,
        )

        # Runtime state
        self.start_time: Optional[float] = None
        self._running = False
        self._client = MeshClient()

    def _get_local_ip(self) -> str:
        """Get a usable local IP address."""
        try:
            # Try to get the IP that would be used to connect externally
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def start(self) -> bool:
        """
        Start the mesh node.

        Returns:
            True if started successfully
        """
        if self._running:
            logger.warning("Mesh node already running")
            return False

        logger.info(f"Starting mesh node {self.node_id[:8]} ({self.persona_name})...")

        try:
            self.start_time = time.time()

            # Start HTTP server
            self.server.start()

            # Start gossip protocol (includes bootstrap)
            self.gossip.start()

            # Wait for bootstrap to complete
            for _ in range(50):
                if self.gossip.bootstrap_complete:
                    break
                time.sleep(0.1)

            # Start sync protocol
            self.sync.start()

            # Import brain memories if configured
            if self.brain_dir and self.brain_dir.exists():
                imported = self.brain_sync.import_from_brain_dir()
                if imported > 0:
                    logger.info(f"Imported {imported} brain memories to mesh")

            self._running = True

            # Log startup info
            status, total = self.peers.get_quorum_status()
            logger.info(
                f"Mesh node started: {self.advertise_address}, "
                f"{len(self.peers)} peer(s), status: {status}"
            )

            return True

        except Exception as e:
            logger.error(f"Failed to start mesh node: {e}")
            self.stop()
            return False

    def stop(self) -> None:
        """Stop the mesh node."""
        if not self._running:
            return

        logger.info("Stopping mesh node...")

        # Stop in reverse order
        self.sync.stop()
        self.gossip.stop()
        self.server.stop()

        self._running = False
        logger.info("Mesh node stopped")

    def get_quorum_status(self) -> tuple[str, int]:
        """
        Get current quorum status.

        Returns:
            Tuple of (status_string, total_node_count)
        """
        return self.peers.get_quorum_status()

    def trigger_sync_with_peer(self, node_id: str) -> None:
        """Request immediate sync with a specific peer."""
        self.sync.request_sync(node_id)

    def force_sync(self) -> None:
        """Force immediate sync with all peers."""
        self.sync.trigger_force_sync()

    def force_announce(self) -> None:
        """Force announcement to all peers."""
        self.gossip.force_announce()

    # Convenience methods for data operations

    def put(self, key: str, value) -> None:
        """Store a value in the mesh."""
        self.store.put(key, value)

    def get(self, key: str):
        """Get a value from the mesh."""
        return self.store.get_value(key)

    def delete(self, key: str) -> bool:
        """Delete a value from the mesh."""
        return self.store.delete(key)

    # Memory operations

    def save_memory(self, title: str, content: str, category: str = "memory") -> str:
        """Save a brain memory to the mesh."""
        return self.brain_sync.put_memory(title, content, category)

    def get_recent_memories(self, limit: int = 10) -> list[dict]:
        """Get recent brain memories from mesh."""
        return self.brain_sync.get_recent_memories(limit)

    # Status and info

    def get_status(self) -> dict:
        """Get comprehensive status information."""
        quorum_status, node_count = self.get_quorum_status()

        return {
            "node_id": self.node_id,
            "hostname": self.hostname,
            "persona_name": self.persona_name,
            "address": self.advertise_address,
            "running": self._running,
            "uptime": time.time() - self.start_time if self.start_time else 0,
            "version": self.version,
            "quorum": {
                "status": quorum_status,
                "node_count": node_count,
            },
            "peers": {
                "total": len(self.peers),
                "active": len(self.peers.get_active_peers()),
                "alive": len(self.peers.get_alive_peers()),
                "dead": len(self.peers.get_dead_peers()),
            },
            "store": self.store.get_stats(),
            "protocols": {
                "gossip_running": self.gossip.is_running,
                "gossip_bootstrapped": self.gossip.bootstrap_complete,
                "sync_running": self.sync.is_running,
                "server_running": self.server.is_running,
            },
        }

    def get_peer_info(self) -> list[dict]:
        """Get information about all known peers."""
        peers = []
        for peer in self.peers.get_all_peers():
            peers.append({
                "node_id": peer.node_id,
                "address": peer.address,
                "hostname": peer.hostname,
                "persona_name": peer.persona_name,
                "state": peer.state.value,
                "capabilities": peer.capabilities,
                "last_seen": peer.last_seen,
                "age_seconds": peer.age_seconds(),
            })
        return peers

    @property
    def is_running(self) -> bool:
        """Check if node is running."""
        return self._running

    @property
    def is_healthy(self) -> bool:
        """Check if node is healthy (running and bootstrapped)."""
        return (
            self._running and
            self.server.is_running and
            self.gossip.bootstrap_complete
        )


def create_mesh_node(
    node_id: str,
    hostname: str = "",
    persona_name: str = "",
    capabilities: list[str] = None,
    version: str = "",
    port: int = 7777,
    seed_peers: list[str] = None,
    data_dir: str = None,
    brain_dir: str = None,
    gossip_interval: float = 30.0,
    heartbeat_interval: float = 10.0,
    sync_interval: float = 60.0,
    max_missed_heartbeats: int = 3,
    on_chat: Callable[[str, str], str] = None,
    on_task: Callable[[dict], dict] = None,
) -> MeshNode:
    """
    Create a mesh node with common defaults.

    This is a convenience function for creating a MeshNode
    with sensible defaults.
    """
    return MeshNode(
        node_id=node_id,
        hostname=hostname,
        persona_name=persona_name,
        capabilities=capabilities,
        version=version,
        listen_port=port,
        seed_peers=seed_peers,
        data_dir=Path(data_dir) if data_dir else None,
        brain_dir=Path(brain_dir) if brain_dir else None,
        gossip_interval=gossip_interval,
        heartbeat_interval=heartbeat_interval,
        sync_interval=sync_interval,
        max_missed_heartbeats=max_missed_heartbeats,
        on_chat=on_chat,
        on_task=on_task,
    )
