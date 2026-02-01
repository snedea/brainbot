"""Memory synchronization between nodes via cloud storage."""

import hashlib
import json
import logging
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from pydantic import BaseModel, Field

from .storage import StorageClient
from .event_log import EventLog

if TYPE_CHECKING:
    from ..memory.store import MemoryStore

logger = logging.getLogger(__name__)


class MemoryTier(str, Enum):
    """Memory tiers with different sync strategies."""

    HOT = "hot"  # Local only (state.json, memory.db) - never synced
    WARM = "warm"  # R2 brain/active/ - synced every 5 minutes
    COLD = "cold"  # S3 brain/archive/ - daily backup only


class SyncStatus(str, Enum):
    """Sync status for a memory file."""

    PENDING = "pending"  # Needs to be synced
    SYNCED = "synced"  # Up to date with cloud
    CONFLICT = "conflict"  # Local and cloud have diverged
    LOCAL_ONLY = "local_only"  # Not yet uploaded
    CLOUD_ONLY = "cloud_only"  # Not yet downloaded


class SyncedMemory(BaseModel):
    """Metadata for a synced memory file."""

    filename: str
    local_path: Optional[str] = None
    cloud_key: Optional[str] = None

    local_hash: Optional[str] = None
    cloud_hash: Optional[str] = None

    local_modified: Optional[datetime] = None
    cloud_modified: Optional[datetime] = None

    sync_status: SyncStatus = SyncStatus.PENDING
    origin_node: str = ""  # Node that created this memory
    last_sync: Optional[datetime] = None


class MemorySyncManager:
    """
    Manages synchronization of brain memories between nodes.

    Memory tiers:
    - HOT: Local only (state.json, memory.db) - critical state, never synced
    - WARM: brain/active/ - synced to R2 every 5 minutes
    - COLD: brain/archive/ - backed up to S3 daily
    """

    def __init__(
        self,
        storage: StorageClient,
        event_log: EventLog,
        brain_dir: Path,
        node_id: str,
        memory_store: Optional["MemoryStore"] = None,
    ):
        """
        Initialize memory sync manager.

        Args:
            storage: Cloud storage client
            event_log: Event log for recording sync events
            brain_dir: Local brain directory path
            node_id: This node's ID
            memory_store: Optional MemoryStore for tracking sync status in SQLite
        """
        self.storage = storage
        self.event_log = event_log
        self.brain_dir = brain_dir
        self.node_id = node_id
        self.memory_store = memory_store

        self.active_dir = brain_dir / "active"
        self.archive_dir = brain_dir / "archive"

        # Ensure directories exist
        self.active_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

    def sync(self) -> dict:
        """
        Perform bidirectional sync of brain memories.

        Returns:
            Dict with sync statistics
        """
        logger.info("Starting memory sync...")

        stats = {
            "uploaded": 0,
            "downloaded": 0,
            "conflicts": 0,
            "unchanged": 0,
            "errors": 0,
        }

        # Sync active memories (WARM tier)
        active_stats = self._sync_directory(
            local_dir=self.active_dir,
            cloud_prefix="brain/active/",
        )
        for key in stats:
            stats[key] += active_stats.get(key, 0)

        logger.info(
            f"Sync complete: {stats['uploaded']} up, {stats['downloaded']} down, "
            f"{stats['conflicts']} conflicts"
        )
        return stats

    def _sync_directory(
        self,
        local_dir: Path,
        cloud_prefix: str,
    ) -> dict:
        """Sync a local directory with cloud prefix."""
        stats = {
            "uploaded": 0,
            "downloaded": 0,
            "conflicts": 0,
            "unchanged": 0,
            "errors": 0,
        }

        # Get local files
        local_files = {}
        for path in local_dir.glob("*.md"):
            content = path.read_text()
            local_files[path.name] = {
                "path": path,
                "hash": self._compute_hash(content),
                "modified": datetime.fromtimestamp(path.stat().st_mtime),
            }

        # Get cloud files
        cloud_files = {}
        cloud_keys = self.storage.list_keys(cloud_prefix)
        for key in cloud_keys:
            if not key.endswith(".md"):
                continue
            filename = key.split("/")[-1]

            # Get hash from metadata or content
            content = self.storage.read_text(key)
            if content:
                cloud_files[filename] = {
                    "key": key,
                    "hash": self._compute_hash(content),
                    "content": content,
                }

        # Find files to sync
        all_files = set(local_files.keys()) | set(cloud_files.keys())

        for filename in all_files:
            local = local_files.get(filename)
            cloud = cloud_files.get(filename)

            try:
                if local and not cloud:
                    # Local only - upload (first time to network = MEMORY_CREATED)
                    if self._upload_file(local["path"], cloud_prefix + filename):
                        stats["uploaded"] += 1
                        # Emit memory created event (new to network)
                        self.event_log.log_memory_created(
                            filename=filename,
                            category="active",
                            content_hash=local["hash"],
                        )
                    else:
                        stats["errors"] += 1

                elif cloud and not local:
                    # Cloud only - download
                    if self._download_file(cloud_prefix + filename, local_dir / filename):
                        stats["downloaded"] += 1
                        # This is a new memory from the network (created by another node)
                        # MEMORY_SYNCED is already logged in _download_file
                    else:
                        stats["errors"] += 1

                elif local and cloud:
                    # Both exist - check for changes
                    if local["hash"] == cloud["hash"]:
                        stats["unchanged"] += 1
                    else:
                        # Conflict - use append-only merge
                        old_hash = local["hash"]
                        resolution = self._resolve_conflict(
                            local["path"],
                            cloud["content"],
                            cloud_prefix + filename,
                        )
                        if resolution == "merged":
                            stats["uploaded"] += 1
                            # Emit memory updated event (merged content)
                            new_content = local["path"].read_text()
                            new_hash = self._compute_hash(new_content)
                            self.event_log.log_memory_updated(
                                filename=filename,
                                content_hash=new_hash,
                                previous_hash=old_hash,
                                update_source="merge",
                            )
                        elif resolution == "conflict":
                            stats["conflicts"] += 1
                            # Emit memory updated event (conflict markers added)
                            new_content = local["path"].read_text()
                            new_hash = self._compute_hash(new_content)
                            self.event_log.log_memory_updated(
                                filename=filename,
                                content_hash=new_hash,
                                previous_hash=old_hash,
                                update_source="merge",
                            )
                        else:
                            stats["errors"] += 1

            except Exception as e:
                logger.error(f"Error syncing {filename}: {e}")
                stats["errors"] += 1

        return stats

    def _upload_file(self, local_path: Path, cloud_key: str) -> bool:
        """Upload a local file to cloud."""
        try:
            content = local_path.read_text()
            content_hash = self._compute_hash(content)

            if self.storage.write(cloud_key, content):
                self.event_log.log_memory_synced(
                    filename=local_path.name,
                    direction="upload",
                    content_hash=content_hash,
                )

                # Track in SQLite if memory_store is available
                if self.memory_store:
                    self.memory_store.upsert_sync_entry(
                        filename=local_path.name,
                        local_hash=content_hash,
                        cloud_hash=content_hash,
                        origin_node=self.node_id,
                        sync_status="synced",
                    )

                logger.debug(f"Uploaded: {local_path.name}")
                return True
            return False
        except Exception as e:
            logger.error(f"Upload failed for {local_path}: {e}")
            return False

    def _download_file(self, cloud_key: str, local_path: Path) -> bool:
        """Download a cloud file to local."""
        try:
            content = self.storage.read_text(cloud_key)
            if content is None:
                return False

            local_path.write_text(content)
            content_hash = self._compute_hash(content)

            self.event_log.log_memory_synced(
                filename=local_path.name,
                direction="download",
                content_hash=content_hash,
            )

            # Track in SQLite if memory_store is available
            if self.memory_store:
                self.memory_store.upsert_sync_entry(
                    filename=local_path.name,
                    local_hash=content_hash,
                    cloud_hash=content_hash,
                    origin_node=self.node_id,  # We now have a local copy
                    sync_status="synced",
                )

            logger.debug(f"Downloaded: {local_path.name}")
            return True
        except Exception as e:
            logger.error(f"Download failed for {cloud_key}: {e}")
            return False

    def _resolve_conflict(
        self,
        local_path: Path,
        cloud_content: str,
        cloud_key: str,
    ) -> str:
        """
        Resolve a conflict between local and cloud versions.

        Strategy: Append-only merge
        - Keep all content from both versions
        - Add conflict markers with timestamps
        - Upload merged result

        Returns:
            "merged", "conflict", or "error"
        """
        try:
            local_content = local_path.read_text()

            # Check if one is a superset of the other
            if cloud_content in local_content:
                # Local has more - just upload
                return "merged" if self._upload_file(local_path, cloud_key) else "error"
            elif local_content in cloud_content:
                # Cloud has more - just download
                local_path.write_text(cloud_content)
                return "merged"

            # True conflict - merge with markers
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            merged = f"""<!-- SYNC CONFLICT - {timestamp} -->
<!-- This file was edited on multiple nodes -->

<!-- === LOCAL VERSION (from this node) === -->

{local_content}

<!-- === CLOUD VERSION (from network) === -->

{cloud_content}

<!-- Please review and consolidate manually -->
"""

            # Save merged locally
            local_path.write_text(merged)

            # Upload merged version
            if self.storage.write(cloud_key, merged):
                merged_hash = self._compute_hash(merged)

                # Track conflict in SQLite
                if self.memory_store:
                    self.memory_store.upsert_sync_entry(
                        filename=local_path.name,
                        local_hash=merged_hash,
                        cloud_hash=merged_hash,
                        origin_node=self.node_id,
                        sync_status="conflict",  # Mark as conflict for review
                    )

                logger.warning(f"Conflict merged: {local_path.name}")
                return "conflict"
            else:
                return "error"

        except Exception as e:
            logger.error(f"Conflict resolution failed: {e}")
            return "error"

    def push_memory(self, filename: str) -> bool:
        """
        Push a specific memory file to cloud.

        Args:
            filename: Name of memory file in active directory

        Returns:
            True if successful
        """
        local_path = self.active_dir / filename
        if not local_path.exists():
            logger.warning(f"Memory file not found: {filename}")
            return False

        cloud_key = f"brain/active/{filename}"
        return self._upload_file(local_path, cloud_key)

    def pull_memory(self, filename: str) -> bool:
        """
        Pull a specific memory file from cloud.

        Args:
            filename: Name of memory file to download

        Returns:
            True if successful
        """
        cloud_key = f"brain/active/{filename}"
        local_path = self.active_dir / filename
        return self._download_file(cloud_key, local_path)

    def backup_archives(self) -> dict:
        """
        Backup archive directory to S3 (cold storage).

        Returns:
            Dict with backup statistics
        """
        stats = {"backed_up": 0, "errors": 0}

        for path in self.archive_dir.glob("*.md"):
            cloud_key = f"brain/archive/{path.name}"
            content = path.read_text()

            try:
                if self.storage.write(cloud_key, content, backup=True):
                    stats["backed_up"] += 1
                else:
                    stats["errors"] += 1
            except Exception as e:
                logger.error(f"Backup failed for {path.name}: {e}")
                stats["errors"] += 1

        logger.info(f"Archive backup: {stats['backed_up']} files")
        return stats

    def get_sync_status(self) -> list[SyncedMemory]:
        """Get sync status for all memory files."""
        memories = []

        # Get local files
        for path in self.active_dir.glob("*.md"):
            content = path.read_text()
            local_hash = self._compute_hash(content)

            cloud_key = f"brain/active/{path.name}"
            cloud_content = self.storage.read_text(cloud_key)

            if cloud_content:
                cloud_hash = self._compute_hash(cloud_content)
                if local_hash == cloud_hash:
                    status = SyncStatus.SYNCED
                else:
                    status = SyncStatus.CONFLICT
            else:
                status = SyncStatus.LOCAL_ONLY
                cloud_hash = None

            memories.append(
                SyncedMemory(
                    filename=path.name,
                    local_path=str(path),
                    cloud_key=cloud_key,
                    local_hash=local_hash,
                    cloud_hash=cloud_hash,
                    local_modified=datetime.fromtimestamp(path.stat().st_mtime),
                    sync_status=status,
                    origin_node=self.node_id,
                )
            )

        # Check for cloud-only files
        cloud_keys = self.storage.list_keys("brain/active/")
        local_filenames = {m.filename for m in memories}

        for key in cloud_keys:
            if not key.endswith(".md"):
                continue
            filename = key.split("/")[-1]
            if filename not in local_filenames:
                cloud_content = self.storage.read_text(key)
                memories.append(
                    SyncedMemory(
                        filename=filename,
                        cloud_key=key,
                        cloud_hash=self._compute_hash(cloud_content) if cloud_content else None,
                        sync_status=SyncStatus.CLOUD_ONLY,
                    )
                )

        return memories

    def _compute_hash(self, content: str) -> str:
        """Compute blake2b hash of content."""
        return hashlib.blake2b(content.encode(), digest_size=16).hexdigest()

    def delta_sync(self) -> dict:
        """
        Perform efficient delta-based sync using content hashing.

        This is more efficient than full sync for large brain directories
        as it only transfers files that have actually changed.

        Returns:
            Dict with sync statistics
        """
        from .delta_sync import DeltaSync

        delta_syncer = DeltaSync(
            storage=self.storage,
            local_dir=self.active_dir,
            cloud_prefix="brain/active/",
            node_id=self.node_id,
        )

        logger.info("Starting delta sync...")
        stats = delta_syncer.quick_sync()

        # Also log any synced files as events
        if stats.get("uploaded", 0) > 0 or stats.get("downloaded", 0) > 0:
            self.event_log.log_memory_synced(
                filename="*delta*",
                direction="bidirectional",
                content_hash=f"up:{stats.get('uploaded', 0)},down:{stats.get('downloaded', 0)}",
            )

        return stats

    def get_delta(self) -> "SyncDelta":
        """
        Get sync delta without applying it.

        Useful for previewing what would change.

        Returns:
            SyncDelta with upload/download/conflict lists
        """
        from .delta_sync import DeltaSync, SyncDelta

        delta_syncer = DeltaSync(
            storage=self.storage,
            local_dir=self.active_dir,
            cloud_prefix="brain/active/",
            node_id=self.node_id,
        )

        return delta_syncer.compute_delta()
