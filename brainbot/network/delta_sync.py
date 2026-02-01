"""Delta synchronization using content hashing."""

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from .storage import StorageClient

logger = logging.getLogger(__name__)


class FileManifestEntry(BaseModel):
    """Entry in a file manifest."""

    filename: str
    content_hash: str
    size_bytes: int
    modified: datetime
    origin_node: Optional[str] = None


class FileManifest(BaseModel):
    """Manifest of files for delta sync."""

    entries: dict[str, FileManifestEntry] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=datetime.now)
    node_id: str = ""


class SyncDelta(BaseModel):
    """Computed delta between local and cloud."""

    to_upload: list[str] = Field(default_factory=list)  # Local files to upload
    to_download: list[str] = Field(default_factory=list)  # Cloud files to download
    conflicts: list[str] = Field(default_factory=list)  # Files with conflicts
    unchanged: list[str] = Field(default_factory=list)  # Already in sync


class DeltaSync:
    """
    Efficient delta synchronization using content hashing.

    Instead of transferring all files, computes hashes to identify
    only the files that have changed and need to be synced.
    """

    MANIFEST_KEY = "sync/manifests/{node_id}.json"

    def __init__(
        self,
        storage: StorageClient,
        local_dir: Path,
        cloud_prefix: str,
        node_id: str,
    ):
        """
        Initialize delta sync.

        Args:
            storage: Cloud storage client
            local_dir: Local directory to sync
            cloud_prefix: Cloud prefix for files
            node_id: This node's ID
        """
        self.storage = storage
        self.local_dir = local_dir
        self.cloud_prefix = cloud_prefix
        self.node_id = node_id

    def compute_local_manifest(self) -> FileManifest:
        """
        Compute manifest of local files.

        Returns:
            FileManifest with all local files
        """
        manifest = FileManifest(node_id=self.node_id)

        for path in self.local_dir.glob("**/*.md"):
            # Compute relative path
            rel_path = path.relative_to(self.local_dir)
            filename = str(rel_path)

            content = path.read_bytes()
            content_hash = self._compute_hash(content)

            manifest.entries[filename] = FileManifestEntry(
                filename=filename,
                content_hash=content_hash,
                size_bytes=len(content),
                modified=datetime.fromtimestamp(path.stat().st_mtime),
                origin_node=self.node_id,
            )

        return manifest

    def get_cloud_manifest(self) -> Optional[FileManifest]:
        """
        Get the cached cloud manifest for efficient comparison.

        Returns:
            FileManifest from cloud, or None if not found
        """
        # Try to get cached manifest
        manifest_key = self.MANIFEST_KEY.format(node_id="global")
        data = self.storage.read_json(manifest_key)

        if data:
            try:
                return FileManifest(**data)
            except Exception as e:
                logger.warning(f"Failed to parse cloud manifest: {e}")

        return None

    def compute_cloud_manifest(self) -> FileManifest:
        """
        Compute manifest of cloud files.

        This is slower than using cached manifest but provides
        accurate current state.

        Returns:
            FileManifest with all cloud files
        """
        manifest = FileManifest(node_id="cloud")

        keys = self.storage.list_keys(self.cloud_prefix)

        for key in keys:
            if not key.endswith(".md"):
                continue

            filename = key[len(self.cloud_prefix):]
            content = self.storage.read(key)

            if content:
                content_hash = self._compute_hash(content)
                metadata = self.storage.get_metadata(key)

                manifest.entries[filename] = FileManifestEntry(
                    filename=filename,
                    content_hash=content_hash,
                    size_bytes=len(content),
                    modified=metadata.get("last_modified", datetime.now()) if metadata else datetime.now(),
                )

        return manifest

    def compute_delta(
        self,
        local_manifest: Optional[FileManifest] = None,
        cloud_manifest: Optional[FileManifest] = None,
    ) -> SyncDelta:
        """
        Compute what needs to be synced.

        Args:
            local_manifest: Local file manifest (computed if not provided)
            cloud_manifest: Cloud file manifest (computed if not provided)

        Returns:
            SyncDelta with upload/download/conflict lists
        """
        if local_manifest is None:
            local_manifest = self.compute_local_manifest()

        if cloud_manifest is None:
            cloud_manifest = self.get_cloud_manifest()
            if cloud_manifest is None:
                cloud_manifest = self.compute_cloud_manifest()

        delta = SyncDelta()

        all_files = set(local_manifest.entries.keys()) | set(cloud_manifest.entries.keys())

        for filename in all_files:
            local = local_manifest.entries.get(filename)
            cloud = cloud_manifest.entries.get(filename)

            if local and not cloud:
                # Local only - needs upload
                delta.to_upload.append(filename)

            elif cloud and not local:
                # Cloud only - needs download
                delta.to_download.append(filename)

            elif local and cloud:
                if local.content_hash == cloud.content_hash:
                    # Same content - no sync needed
                    delta.unchanged.append(filename)
                else:
                    # Different content - conflict or sync needed
                    # Use modification time to decide direction
                    if local.modified > cloud.modified:
                        delta.to_upload.append(filename)
                    elif cloud.modified > local.modified:
                        delta.to_download.append(filename)
                    else:
                        # Same time but different content - conflict
                        delta.conflicts.append(filename)

        return delta

    def apply_delta(self, delta: SyncDelta) -> dict:
        """
        Apply computed delta - perform actual sync.

        Args:
            delta: Computed sync delta

        Returns:
            Dict with sync statistics
        """
        stats = {
            "uploaded": 0,
            "downloaded": 0,
            "conflicts": len(delta.conflicts),
            "errors": 0,
        }

        # Upload local files
        for filename in delta.to_upload:
            local_path = self.local_dir / filename
            cloud_key = self.cloud_prefix + filename

            try:
                content = local_path.read_text()
                if self.storage.write(cloud_key, content):
                    stats["uploaded"] += 1
                else:
                    stats["errors"] += 1
            except Exception as e:
                logger.error(f"Upload failed for {filename}: {e}")
                stats["errors"] += 1

        # Download cloud files
        for filename in delta.to_download:
            cloud_key = self.cloud_prefix + filename
            local_path = self.local_dir / filename

            try:
                content = self.storage.read_text(cloud_key)
                if content:
                    local_path.parent.mkdir(parents=True, exist_ok=True)
                    local_path.write_text(content)
                    stats["downloaded"] += 1
                else:
                    stats["errors"] += 1
            except Exception as e:
                logger.error(f"Download failed for {filename}: {e}")
                stats["errors"] += 1

        # Update cloud manifest
        self._update_cloud_manifest()

        return stats

    def _update_cloud_manifest(self) -> bool:
        """Update the global cloud manifest after sync."""
        manifest = self.compute_cloud_manifest()
        manifest_key = self.MANIFEST_KEY.format(node_id="global")
        return self.storage.write(manifest_key, manifest.model_dump(mode="json"))

    def quick_sync(self) -> dict:
        """
        Perform a quick delta sync.

        Returns:
            Dict with sync statistics
        """
        logger.info("Computing delta...")
        delta = self.compute_delta()

        logger.info(
            f"Delta: {len(delta.to_upload)} up, {len(delta.to_download)} down, "
            f"{len(delta.conflicts)} conflicts, {len(delta.unchanged)} unchanged"
        )

        if not delta.to_upload and not delta.to_download:
            logger.info("Already in sync")
            return {"uploaded": 0, "downloaded": 0, "conflicts": 0, "errors": 0}

        logger.info("Applying delta...")
        return self.apply_delta(delta)

    def _compute_hash(self, content: bytes) -> str:
        """Compute blake2b hash of content."""
        return hashlib.blake2b(content, digest_size=16).hexdigest()


def format_delta_display(delta: SyncDelta) -> str:
    """Format delta for CLI display."""
    lines = [
        "Sync Delta",
        "=" * 40,
        "",
    ]

    if delta.to_upload:
        lines.append(f"To Upload ({len(delta.to_upload)}):")
        for f in delta.to_upload[:10]:
            lines.append(f"  + {f}")
        if len(delta.to_upload) > 10:
            lines.append(f"  ... and {len(delta.to_upload) - 10} more")
        lines.append("")

    if delta.to_download:
        lines.append(f"To Download ({len(delta.to_download)}):")
        for f in delta.to_download[:10]:
            lines.append(f"  v {f}")
        if len(delta.to_download) > 10:
            lines.append(f"  ... and {len(delta.to_download) - 10} more")
        lines.append("")

    if delta.conflicts:
        lines.append(f"Conflicts ({len(delta.conflicts)}):")
        for f in delta.conflicts[:10]:
            lines.append(f"  ! {f}")
        if len(delta.conflicts) > 10:
            lines.append(f"  ... and {len(delta.conflicts) - 10} more")
        lines.append("")

    if delta.unchanged:
        lines.append(f"Unchanged: {len(delta.unchanged)} files")

    if not delta.to_upload and not delta.to_download and not delta.conflicts:
        lines.append("Everything is in sync!")

    return "\n".join(lines)
