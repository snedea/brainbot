"""State synchronization protocol for the mesh network.

Implements bidirectional sync using:
- Manifest exchange (lightweight metadata comparison)
- Last-write-wins conflict resolution
- Push/pull based on timestamp comparison
"""

import asyncio
import logging
import random
import threading
import time
from typing import Optional, TYPE_CHECKING

from .peer import PeerInfo, PeerState
from .store import SyncItem, VersionedStore
from .transport import MeshClient

if TYPE_CHECKING:
    from .node import MeshNode

logger = logging.getLogger(__name__)


class SyncProtocol:
    """
    State synchronization protocol for the mesh network.

    Synchronizes data between peers using manifest comparison
    and bidirectional push/pull.
    """

    def __init__(
        self,
        node: "MeshNode",
        sync_interval: float = 60.0,
        batch_size: int = 10,
    ):
        """
        Initialize sync protocol.

        Args:
            node: The MeshNode this protocol belongs to
            sync_interval: Seconds between sync rounds
            batch_size: Max items to sync per peer per round
        """
        self.node = node
        self.sync_interval = sync_interval
        self.batch_size = batch_size

        self._client = MeshClient()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

        # Pending sync requests (from gossip detecting returned peers)
        self._pending_syncs: list[str] = []
        self._pending_lock = threading.Lock()

    def start(self) -> None:
        """Start the sync protocol."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("Sync protocol started")

    def stop(self) -> None:
        """Stop the sync protocol."""
        if not self._running:
            return

        self._running = False
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)

        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None

        logger.info("Sync protocol stopped")

    def _run(self) -> None:
        """Main sync loop."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        try:
            while self._running:
                try:
                    # Process any pending immediate syncs
                    self._loop.run_until_complete(self._process_pending_syncs())

                    # Run periodic sync cycle
                    self._loop.run_until_complete(self._sync_cycle())

                    # Sleep until next cycle
                    time.sleep(self.sync_interval)

                except Exception as e:
                    logger.error(f"Sync cycle error: {e}")
                    time.sleep(10.0)  # Back off on error

        finally:
            self._loop.run_until_complete(self._client.close())
            self._loop.close()

    async def _process_pending_syncs(self) -> None:
        """Process any pending sync requests."""
        with self._pending_lock:
            pending = list(self._pending_syncs)
            self._pending_syncs.clear()

        for node_id in pending:
            peer = self.node.peers.get_peer(node_id)
            if peer and peer.is_reachable():
                logger.info(f"Processing pending sync with {peer.persona_name or peer.node_id[:8]}")
                await self._sync_with_peer(peer)

    async def _sync_cycle(self) -> None:
        """Run one sync cycle with all active peers."""
        active_peers = self.node.peers.get_active_peers()
        if not active_peers:
            logger.debug("No active peers for sync")
            return

        logger.debug(f"Starting sync cycle with {len(active_peers)} peer(s)")

        # Sync with each active peer
        for peer in active_peers:
            try:
                await self._sync_with_peer(peer)
            except Exception as e:
                logger.error(f"Sync with {peer.address} failed: {e}")

        # Report sync stats
        stats = self.node.store.get_stats()
        status, total = self.node.peers.get_quorum_status()
        logger.debug(f"Sync cycle complete: {stats['item_count']} items, {total} nodes ({status})")

    async def _sync_with_peer(self, peer: PeerInfo) -> tuple[int, int]:
        """
        Synchronize data with a single peer.

        Args:
            peer: The peer to sync with

        Returns:
            Tuple of (items_pushed, items_pulled)
        """
        items_pushed = 0
        items_pulled = 0

        # Get peer's manifest
        success, peer_manifest = await self._client.get_manifest(peer.address)
        if not success:
            logger.debug(f"Failed to get manifest from {peer.address}")
            return 0, 0

        # Determine what to push/pull
        items_to_push, keys_to_pull = self.node.store.get_items_for_sync(peer_manifest)

        # Push our newer items (limited by batch size)
        for item in items_to_push[:self.batch_size]:
            try:
                success, response = await self._client.push_sync_item(
                    peer.address, item.to_dict()
                )
                if success:
                    items_pushed += 1
                    logger.debug(f"Pushed {item.key} to {peer.node_id[:8]}")
            except Exception as e:
                logger.debug(f"Failed to push {item.key}: {e}")

        # Pull their newer items (limited by batch size)
        for key in keys_to_pull[:self.batch_size]:
            try:
                success, item_data = await self._client.get_sync_item(peer.address, key)
                if success:
                    item = SyncItem.from_dict(item_data)
                    accepted, reason = self.node.store.merge_item(item)
                    if accepted:
                        items_pulled += 1
                        logger.debug(f"Pulled {key} from {peer.node_id[:8]}")
            except Exception as e:
                logger.debug(f"Failed to pull {key}: {e}")

        # Update peer's sync tracking
        peer.last_sync = time.time()

        if items_pushed > 0 or items_pulled > 0:
            logger.info(
                f"Synced with {peer.persona_name or peer.node_id[:8]}: "
                f"+{items_pushed} pushed, +{items_pulled} pulled"
            )

        return items_pushed, items_pulled

    def request_sync(self, node_id: str) -> None:
        """
        Request an immediate sync with a specific peer.

        Args:
            node_id: The peer's node ID
        """
        with self._pending_lock:
            if node_id not in self._pending_syncs:
                self._pending_syncs.append(node_id)
                logger.debug(f"Queued sync request for {node_id[:8]}")

    async def force_sync_all(self) -> tuple[int, int]:
        """
        Force immediate sync with all active peers.

        Returns:
            Tuple of (total_pushed, total_pulled)
        """
        total_pushed = 0
        total_pulled = 0

        active_peers = self.node.peers.get_active_peers()
        for peer in active_peers:
            try:
                pushed, pulled = await self._sync_with_peer(peer)
                total_pushed += pushed
                total_pulled += pulled
            except Exception as e:
                logger.error(f"Force sync with {peer.address} failed: {e}")

        return total_pushed, total_pulled

    def trigger_force_sync(self) -> None:
        """Trigger a forced sync (async, non-blocking)."""
        if self._loop and self._running:
            asyncio.run_coroutine_threadsafe(self.force_sync_all(), self._loop)

    @property
    def is_running(self) -> bool:
        """Check if sync protocol is running."""
        return self._running


class BrainMemorySync:
    """
    Synchronizes brain memories with the mesh store.

    Provides a bridge between the existing brain memory system
    (markdown files) and the mesh sync store.
    """

    def __init__(self, node: "MeshNode", brain_dir: str = None):
        """
        Initialize brain memory sync.

        Args:
            node: The MeshNode
            brain_dir: Path to brain directory (for initial import)
        """
        self.node = node
        self.brain_dir = brain_dir

    def put_memory(
        self,
        title: str,
        content: str,
        category: str = "memory",
    ) -> str:
        """
        Store a memory in the mesh.

        Args:
            title: Memory title
            content: Memory content (markdown)
            category: Memory category

        Returns:
            The key used to store the memory
        """
        # Generate key based on category and title
        safe_title = "".join(c if c.isalnum() or c in "-_" else "_" for c in title)
        timestamp = time.time()
        key = f"brain/{category}/{safe_title}-{int(timestamp)}"

        self.node.store.put(
            key=key,
            value={
                "title": title,
                "content": content,
                "category": category,
                "created_at": timestamp,
            },
        )

        return key

    def get_memory(self, key: str) -> Optional[dict]:
        """
        Get a memory by key.

        Args:
            key: Memory key

        Returns:
            Memory dict or None
        """
        return self.node.store.get_value(key)

    def get_memories_by_category(self, category: str) -> list[dict]:
        """
        Get all memories in a category.

        Args:
            category: Category to filter by

        Returns:
            List of memory dicts
        """
        prefix = f"brain/{category}/"
        items = self.node.store.get_items_by_prefix(prefix)

        memories = []
        for item in items:
            if isinstance(item.value, dict):
                memories.append({
                    "key": item.key,
                    **item.value,
                    "timestamp": item.timestamp,
                    "origin_node": item.origin_node,
                })

        # Sort by timestamp descending (newest first)
        memories.sort(key=lambda m: m.get("timestamp", 0), reverse=True)
        return memories

    def get_recent_memories(self, limit: int = 10) -> list[dict]:
        """
        Get the most recent memories across all categories.

        Args:
            limit: Maximum number of memories

        Returns:
            List of memory dicts
        """
        prefix = "brain/"
        items = self.node.store.get_items_by_prefix(prefix)

        memories = []
        for item in items:
            if isinstance(item.value, dict):
                memories.append({
                    "key": item.key,
                    **item.value,
                    "timestamp": item.timestamp,
                    "origin_node": item.origin_node,
                })

        # Sort by timestamp descending and limit
        memories.sort(key=lambda m: m.get("timestamp", 0), reverse=True)
        return memories[:limit]

    def import_from_brain_dir(self) -> int:
        """
        Import existing brain memories from filesystem.

        Returns:
            Number of memories imported
        """
        if not self.brain_dir:
            return 0

        from pathlib import Path
        import os

        brain_path = Path(self.brain_dir)
        if not brain_path.exists():
            return 0

        imported = 0

        # Walk brain directory
        for root, dirs, files in os.walk(brain_path):
            for filename in files:
                if not filename.endswith(".md"):
                    continue

                filepath = Path(root) / filename
                try:
                    content = filepath.read_text()

                    # Determine category from path
                    rel_path = filepath.relative_to(brain_path)
                    parts = list(rel_path.parts)

                    if parts[0] in ("active", "archive"):
                        category = parts[0]
                    else:
                        category = "memory"

                    # Use filename as title
                    title = filename[:-3]  # Remove .md

                    # Use file mtime as timestamp
                    mtime = filepath.stat().st_mtime

                    # Generate key
                    safe_title = "".join(c if c.isalnum() or c in "-_" else "_" for c in title)
                    key = f"brain/{category}/{safe_title}"

                    # Only import if not already in store
                    if not self.node.store.exists(key):
                        self.node.store.put(
                            key=key,
                            value={
                                "title": title,
                                "content": content,
                                "category": category,
                                "imported_from": str(filepath),
                            },
                            timestamp=mtime,
                        )
                        imported += 1

                except Exception as e:
                    logger.warning(f"Failed to import {filepath}: {e}")

        if imported > 0:
            logger.info(f"Imported {imported} memories from brain directory")

        return imported
