"""Gossip protocol for peer discovery in the mesh network.

Implements peer discovery via:
- Bootstrap from seed peers
- Periodic gossip exchange with known peers
- Health checking via heartbeats
- Peer state management (ALIVE/SUSPECTED/DEAD)
"""

import asyncio
import logging
import random
import threading
import time
from typing import Optional, TYPE_CHECKING

from .peer import PeerInfo, PeerState, PeerRegistry
from .transport import MeshClient

if TYPE_CHECKING:
    from .node import MeshNode

logger = logging.getLogger(__name__)


class GossipProtocol:
    """
    Gossip-based peer discovery protocol.

    Discovers peers by:
    1. Connecting to seed peers on startup
    2. Asking each peer for their known peers
    3. Periodically re-gossiping to discover new nodes
    4. Health checking peers with heartbeats
    """

    def __init__(
        self,
        node: "MeshNode",
        seed_peers: list[str] = None,
        gossip_interval: float = 30.0,
        heartbeat_interval: float = 10.0,
        max_missed_heartbeats: int = 3,
    ):
        """
        Initialize gossip protocol.

        Args:
            node: The MeshNode this protocol belongs to
            seed_peers: List of seed peer addresses (host:port)
            gossip_interval: Seconds between gossip rounds
            heartbeat_interval: Seconds between heartbeat checks
            max_missed_heartbeats: Heartbeats missed before marking DEAD
        """
        self.node = node
        self.seed_peers = seed_peers or []
        self.gossip_interval = gossip_interval
        self.heartbeat_interval = heartbeat_interval
        self.max_missed_heartbeats = max_missed_heartbeats

        self._client = MeshClient()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._bootstrap_done = False

    def start(self) -> None:
        """Start the gossip protocol."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("Gossip protocol started")

    def stop(self) -> None:
        """Stop the gossip protocol."""
        if not self._running:
            return

        self._running = False
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)

        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None

        logger.info("Gossip protocol stopped")

    def _run(self) -> None:
        """Main gossip loop with separate heartbeat and gossip intervals."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        try:
            # Bootstrap from seeds
            self._loop.run_until_complete(self._bootstrap())

            # Track last heartbeat and gossip times
            last_heartbeat = time.time()
            last_gossip = time.time()

            # Run main loop
            while self._running:
                try:
                    now = time.time()

                    # Run heartbeat if interval elapsed
                    if now - last_heartbeat >= self.heartbeat_interval:
                        self._loop.run_until_complete(self._heartbeat_all())
                        last_heartbeat = now

                    # Run gossip if interval elapsed
                    if now - last_gossip >= self.gossip_interval:
                        self._loop.run_until_complete(self._gossip_random())
                        # Prune long-dead peers during gossip cycle
                        self.node.peers.prune_dead_peers(max_age_seconds=3600)
                        last_gossip = now

                    # Sleep for a short interval to check both conditions
                    time.sleep(1.0)

                except Exception as e:
                    logger.error(f"Gossip cycle error: {e}")
                    time.sleep(5.0)  # Back off on error

        finally:
            self._loop.run_until_complete(self._client.close())
            self._loop.close()

    async def _bootstrap(self) -> None:
        """Bootstrap by connecting to seed peers."""
        if not self.seed_peers:
            logger.info("No seed peers configured, running standalone")
            self._bootstrap_done = True
            return

        logger.info(f"Bootstrapping from {len(self.seed_peers)} seed peer(s)...")

        for seed_address in self.seed_peers:
            try:
                await self._discover_from_peer(seed_address, source="seed")
            except Exception as e:
                logger.warning(f"Failed to connect to seed {seed_address}: {e}")

        # Announce ourselves to all discovered peers
        await self._announce_to_all()

        self._bootstrap_done = True
        peer_count = len(self.node.peers)
        status, total = self.node.peers.get_quorum_status()
        logger.info(f"Bootstrap complete: {peer_count} peer(s) discovered, status: {status} ({total} nodes)")

    async def _discover_from_peer(self, address: str, source: str = "gossip") -> bool:
        """
        Discover peers from a single peer.

        Args:
            address: Peer address (host:port)
            source: Discovery source for logging

        Returns:
            True if successful
        """
        # First get peer info
        success, info = await self._client.info(address)
        if not success:
            logger.debug(f"Failed to get info from {address}")
            return False

        node_id = info.get("node_id")
        if not node_id or node_id == self.node.node_id:
            return False

        # Add this peer
        self.node.peers.add_peer(
            node_id=node_id,
            address=address,
            hostname=info.get("hostname", ""),
            persona_name=info.get("persona_name", ""),
            capabilities=info.get("capabilities", []),
            version=info.get("version", ""),
            discovered_via=source,
        )
        self.node.peers.update_heartbeat(node_id)

        # Get their peer list
        success, peers = await self._client.get_peers(address)
        if success and peers:
            self.node.peers.merge_peer_list(peers, source=f"gossip-{node_id[:8]}")

        return True

    async def _announce_to_all(self) -> None:
        """Announce ourselves to all known peers."""
        my_info = {
            "node_id": self.node.node_id,
            "address": self.node.advertise_address,
            "hostname": self.node.hostname,
            "persona_name": self.node.persona_name,
            "capabilities": self.node.capabilities,
            "version": self.node.version,
        }

        peers = self.node.peers.get_all_peers()
        for peer in peers:
            try:
                success, response = await self._client.announce(peer.address, my_info)
                if success:
                    logger.debug(f"Announced to {peer.node_id[:8]}")
                    peer.update_heartbeat()
            except Exception as e:
                logger.debug(f"Failed to announce to {peer.address}: {e}")

    async def _heartbeat_all(self) -> None:
        """Send heartbeat to all known peers."""
        peers = self.node.peers.get_all_peers()

        for peer in peers:
            # Capture state BEFORE attempting heartbeat
            was_dead = peer.state == PeerState.DEAD

            try:
                success, _ = await self._client.health(peer.address)
                if success:
                    found, previous_state = self.node.peers.update_heartbeat(peer.node_id)

                    # If peer was dead but is now responding, trigger resync
                    if found and previous_state == PeerState.DEAD:
                        logger.info(f"Dead peer {peer.node_id[:8]} is back, triggering resync")
                        self.node.trigger_sync_with_peer(peer.node_id)
                else:
                    self.node.peers.record_missed_heartbeat(peer.node_id)

            except Exception as e:
                logger.debug(f"Heartbeat to {peer.address} failed: {e}")
                self.node.peers.record_missed_heartbeat(peer.node_id)

    async def _gossip_random(self) -> None:
        """Gossip with a random subset of alive peers."""
        alive_peers = self.node.peers.get_alive_peers()
        if not alive_peers:
            # No alive peers - try seeds again
            if self.seed_peers:
                logger.debug("No alive peers, trying seeds again")
                for seed in random.sample(self.seed_peers, min(2, len(self.seed_peers))):
                    await self._discover_from_peer(seed, source="seed-retry")
            return

        # Gossip with up to 3 random peers
        sample_size = min(3, len(alive_peers))
        selected = random.sample(alive_peers, sample_size)

        for peer in selected:
            try:
                # Get their peer list
                success, peer_list = await self._client.get_peers(peer.address)
                if success and peer_list:
                    new_count = self.node.peers.merge_peer_list(
                        peer_list,
                        source=f"gossip-{peer.node_id[:8]}",
                    )

                    # If we learned about new peers, announce to them
                    if new_count > 0:
                        await self._announce_to_new_peers(new_count)

            except Exception as e:
                logger.debug(f"Gossip with {peer.address} failed: {e}")

    async def _announce_to_new_peers(self, count: int) -> None:
        """Announce to recently discovered peers."""
        # Get peers discovered recently (within last minute)
        all_peers = self.node.peers.get_all_peers()
        recent = [p for p in all_peers if time.time() - p.discovered_at < 60]

        if not recent:
            return

        my_info = {
            "node_id": self.node.node_id,
            "address": self.node.advertise_address,
            "hostname": self.node.hostname,
            "persona_name": self.node.persona_name,
            "capabilities": self.node.capabilities,
            "version": self.node.version,
        }

        for peer in recent:
            try:
                success, _ = await self._client.announce(peer.address, my_info)
                if success:
                    logger.debug(f"Announced to new peer {peer.node_id[:8]}")
            except Exception as e:
                logger.debug(f"Failed to announce to new peer {peer.address}: {e}")

    async def discover_peer(self, address: str) -> bool:
        """
        Manually discover a peer by address.

        Args:
            address: Peer address (host:port)

        Returns:
            True if successful
        """
        return await self._discover_from_peer(address, source="manual")

    def force_announce(self) -> None:
        """Force announcement to all peers (async)."""
        if self._loop and self._running:
            asyncio.run_coroutine_threadsafe(self._announce_to_all(), self._loop)

    @property
    def is_running(self) -> bool:
        """Check if gossip protocol is running."""
        return self._running

    @property
    def bootstrap_complete(self) -> bool:
        """Check if initial bootstrap is complete."""
        return self._bootstrap_done
