"""Versioned data store for mesh network synchronization.

Stores data items with timestamps and version numbers for
last-write-wins conflict resolution.
"""

import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Optional

logger = logging.getLogger(__name__)


@dataclass
class SyncItem:
    """A versioned data item in the store."""

    key: str
    value: Any  # The actual data (usually dict or string)
    timestamp: float  # Unix timestamp with ms precision
    origin_node: str  # Node that originally created/modified this
    version: int  # Monotonic version counter

    # Metadata
    content_hash: str = ""  # blake2b hash of value
    size_bytes: int = 0

    def __post_init__(self):
        """Compute hash and size after initialization."""
        if not self.content_hash:
            self.content_hash = self._compute_hash()
        if not self.size_bytes:
            self.size_bytes = len(self._serialize_value())

    def _serialize_value(self) -> bytes:
        """Serialize value to bytes for hashing/size."""
        if isinstance(self.value, bytes):
            return self.value
        elif isinstance(self.value, str):
            return self.value.encode("utf-8")
        else:
            return json.dumps(self.value, sort_keys=True).encode("utf-8")

    def _compute_hash(self) -> str:
        """Compute blake2b hash of value."""
        h = hashlib.blake2b(self._serialize_value(), digest_size=16)
        return h.hexdigest()

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "key": self.key,
            "value": self.value,
            "timestamp": self.timestamp,
            "origin_node": self.origin_node,
            "version": self.version,
            "content_hash": self.content_hash,
            "size_bytes": self.size_bytes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SyncItem":
        """Create from dictionary."""
        return cls(
            key=data["key"],
            value=data["value"],
            timestamp=data["timestamp"],
            origin_node=data["origin_node"],
            version=data["version"],
            content_hash=data.get("content_hash", ""),
            size_bytes=data.get("size_bytes", 0),
        )

    def to_manifest_entry(self) -> dict:
        """Get minimal info for manifest (excludes value)."""
        return {
            "timestamp": self.timestamp,
            "version": self.version,
            "origin_node": self.origin_node,
            "content_hash": self.content_hash,
            "size_bytes": self.size_bytes,
        }

    def is_newer_than(self, other: "SyncItem") -> bool:
        """
        Check if this item is newer than another.

        Uses last-write-wins with origin_node as tiebreaker.
        """
        if self.timestamp > other.timestamp:
            return True
        elif self.timestamp < other.timestamp:
            return False
        else:
            # Equal timestamps - use origin_node lexically as tiebreaker
            return self.origin_node > other.origin_node


class VersionedStore:
    """
    Thread-safe versioned data store for mesh synchronization.

    Stores data items with timestamps and versions, supporting
    manifest generation and conflict resolution.
    """

    def __init__(
        self,
        node_id: str,
        data_dir: Optional[Path] = None,
        persist: bool = True,
    ):
        """
        Initialize versioned store.

        Args:
            node_id: This node's ID (used as origin for new items)
            data_dir: Directory for persistent storage
            persist: Whether to persist to disk
        """
        self.node_id = node_id
        self.data_dir = data_dir
        self.persist = persist and data_dir is not None

        self._items: dict[str, SyncItem] = {}
        self._version_counter = 0
        self._lock = threading.RLock()

        # Load persisted data
        if self.persist:
            self._store_file = self.data_dir / "mesh_store.json"
            self._load()

    def _load(self) -> None:
        """Load store from disk."""
        if not self._store_file.exists():
            return

        try:
            with open(self._store_file) as f:
                data = json.load(f)

            self._version_counter = data.get("version_counter", 0)
            items_data = data.get("items", {})

            for key, item_data in items_data.items():
                self._items[key] = SyncItem.from_dict(item_data)

            logger.info(f"Loaded {len(self._items)} items from mesh store")

        except Exception as e:
            logger.error(f"Failed to load mesh store: {e}")

    def _save(self) -> None:
        """Save store to disk."""
        if not self.persist:
            return

        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)

            data = {
                "version_counter": self._version_counter,
                "items": {key: item.to_dict() for key, item in self._items.items()},
                "saved_at": time.time(),
                "node_id": self.node_id,
            }

            # Write atomically
            tmp_file = self._store_file.with_suffix(".tmp")
            with open(tmp_file, "w") as f:
                json.dump(data, f, indent=2)
            tmp_file.rename(self._store_file)

        except Exception as e:
            logger.error(f"Failed to save mesh store: {e}")

    def put(
        self,
        key: str,
        value: Any,
        timestamp: Optional[float] = None,
        origin_node: Optional[str] = None,
        version: Optional[int] = None,
    ) -> SyncItem:
        """
        Store a data item.

        Args:
            key: Unique key for this item
            value: The data to store
            timestamp: Creation/modification time (default: now)
            origin_node: Node that created this (default: this node)
            version: Version number (default: auto-increment)

        Returns:
            The stored SyncItem
        """
        with self._lock:
            if timestamp is None:
                timestamp = time.time()
            if origin_node is None:
                origin_node = self.node_id
            if version is None:
                self._version_counter += 1
                version = self._version_counter

            item = SyncItem(
                key=key,
                value=value,
                timestamp=timestamp,
                origin_node=origin_node,
                version=version,
            )

            self._items[key] = item
            self._save()

            logger.debug(f"Stored item: {key} (v{version}, from {origin_node[:8]})")
            return item

    def get(self, key: str) -> Optional[SyncItem]:
        """Get an item by key."""
        with self._lock:
            return self._items.get(key)

    def get_value(self, key: str) -> Optional[Any]:
        """Get just the value of an item."""
        with self._lock:
            item = self._items.get(key)
            return item.value if item else None

    def delete(self, key: str) -> bool:
        """
        Delete an item.

        Args:
            key: Key to delete

        Returns:
            True if deleted, False if not found
        """
        with self._lock:
            if key in self._items:
                del self._items[key]
                self._save()
                logger.debug(f"Deleted item: {key}")
                return True
            return False

    def exists(self, key: str) -> bool:
        """Check if a key exists."""
        with self._lock:
            return key in self._items

    def keys(self) -> list[str]:
        """Get all keys."""
        with self._lock:
            return list(self._items.keys())

    def items(self) -> list[tuple[str, SyncItem]]:
        """Get all key-item pairs."""
        with self._lock:
            return list(self._items.items())

    def get_manifest(self) -> dict[str, dict]:
        """
        Get manifest for sync protocol.

        Returns dict of {key: {timestamp, version, origin_node, content_hash}}
        """
        with self._lock:
            return {
                key: item.to_manifest_entry()
                for key, item in self._items.items()
            }

    def merge_item(self, item: SyncItem) -> tuple[bool, str]:
        """
        Merge an item from another node.

        Uses last-write-wins conflict resolution.

        Args:
            item: The item to merge

        Returns:
            Tuple of (accepted, reason)
        """
        with self._lock:
            existing = self._items.get(item.key)

            if existing is None:
                # New item - accept
                self._items[item.key] = item
                self._save()
                logger.debug(f"Merged new item: {item.key}")
                return True, "new"

            if item.is_newer_than(existing):
                # Incoming is newer - accept
                self._items[item.key] = item
                self._save()
                logger.debug(f"Merged newer item: {item.key} (their ts={item.timestamp:.3f} > ours={existing.timestamp:.3f})")
                return True, "newer"

            if existing.is_newer_than(item):
                # Ours is newer - reject
                logger.debug(f"Rejected older item: {item.key} (their ts={item.timestamp:.3f} < ours={existing.timestamp:.3f})")
                return False, "older"

            # Same timestamps and origin (shouldn't happen) - keep existing
            logger.debug(f"Rejected identical item: {item.key}")
            return False, "identical"

    def get_items_for_sync(
        self,
        peer_manifest: dict[str, dict],
    ) -> tuple[list[SyncItem], list[str]]:
        """
        Determine what to push/pull based on peer's manifest.

        Args:
            peer_manifest: Peer's manifest {key: {timestamp, version, ...}}

        Returns:
            Tuple of (items_to_push, keys_to_pull)
        """
        with self._lock:
            items_to_push = []
            keys_to_pull = []

            # Check what we have that they need
            for key, item in self._items.items():
                peer_entry = peer_manifest.get(key)

                if peer_entry is None:
                    # They don't have it - push
                    items_to_push.append(item)
                elif item.timestamp > peer_entry.get("timestamp", 0):
                    # Ours is newer - push
                    items_to_push.append(item)
                elif item.timestamp == peer_entry.get("timestamp", 0):
                    # Same timestamp - use origin_node tiebreaker
                    if item.origin_node > peer_entry.get("origin_node", ""):
                        items_to_push.append(item)

            # Check what they have that we need
            for key, peer_entry in peer_manifest.items():
                our_item = self._items.get(key)

                if our_item is None:
                    # We don't have it - pull
                    keys_to_pull.append(key)
                elif our_item.timestamp < peer_entry.get("timestamp", 0):
                    # Theirs is newer - pull
                    keys_to_pull.append(key)
                elif our_item.timestamp == peer_entry.get("timestamp", 0):
                    # Same timestamp - use origin_node tiebreaker
                    if our_item.origin_node < peer_entry.get("origin_node", ""):
                        keys_to_pull.append(key)

            return items_to_push, keys_to_pull

    def get_keys_by_prefix(self, prefix: str) -> list[str]:
        """Get all keys starting with a prefix."""
        with self._lock:
            return [k for k in self._items.keys() if k.startswith(prefix)]

    def get_items_by_prefix(self, prefix: str) -> list[SyncItem]:
        """Get all items with keys starting with a prefix."""
        with self._lock:
            return [v for k, v in self._items.items() if k.startswith(prefix)]

    def get_stats(self) -> dict:
        """Get store statistics."""
        with self._lock:
            total_size = sum(item.size_bytes for item in self._items.values())
            return {
                "item_count": len(self._items),
                "total_size_bytes": total_size,
                "version_counter": self._version_counter,
                "node_id": self.node_id,
            }

    def clear(self) -> None:
        """Clear all items (use with caution!)."""
        with self._lock:
            self._items.clear()
            self._version_counter = 0
            self._save()
            logger.warning("Mesh store cleared")

    def __len__(self) -> int:
        """Get number of items."""
        with self._lock:
            return len(self._items)

    def __contains__(self, key: str) -> bool:
        """Check if key exists."""
        with self._lock:
            return key in self._items

    def __iter__(self) -> Iterator[str]:
        """Iterate over keys."""
        with self._lock:
            return iter(list(self._items.keys()))
