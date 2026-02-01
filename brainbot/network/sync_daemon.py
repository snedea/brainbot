"""Background sync daemon for network operations."""

import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from .storage import StorageClient, CloudStorageConfig
from .registry import NodeRegistry
from .event_log import EventLog
from .memory_sync import MemorySyncManager
from .models import CapabilityManifest, NodePersona
from ..version import get_version

logger = logging.getLogger(__name__)


class SyncDaemon:
    """
    Background daemon for network synchronization.

    Runs three background loops:
    - Heartbeat loop: Every 60 seconds, update node status in registry
    - Brain sync loop: Every 5 minutes, sync brain memories
    - Event watch loop: Watch for events from other nodes
    """

    def __init__(
        self,
        storage_config: CloudStorageConfig,
        node_id: str,
        hostname: str,
        persona: NodePersona,
        manifest: CapabilityManifest,
        brain_dir: Path,
        heartbeat_interval: int = 60,
        sync_interval: int = 300,
        on_task_received: Optional[Callable] = None,
    ):
        """
        Initialize sync daemon.

        Args:
            storage_config: Cloud storage configuration
            node_id: This node's unique ID
            hostname: This node's hostname
            persona: This node's persona
            manifest: This node's hardware manifest
            brain_dir: Path to brain directory
            heartbeat_interval: Seconds between heartbeats (default 60)
            sync_interval: Seconds between brain syncs (default 300)
            on_task_received: Callback when a task is received for this node
        """
        self.storage_config = storage_config
        self.node_id = node_id
        self.hostname = hostname
        self.persona = persona
        self.manifest = manifest
        self.brain_dir = brain_dir
        self.heartbeat_interval = heartbeat_interval
        self.sync_interval = sync_interval
        self.on_task_received = on_task_received

        # Initialize components
        self.storage = StorageClient(storage_config)
        self.registry = NodeRegistry(self.storage)
        self.event_log = EventLog(self.storage, node_id)
        self.memory_sync = MemorySyncManager(
            storage=self.storage,
            event_log=self.event_log,
            brain_dir=brain_dir,
            node_id=node_id,
        )

        # Thread control
        self._running = False
        self._threads: list[threading.Thread] = []
        self._stop_event = threading.Event()

        # Stats
        self._last_heartbeat: Optional[datetime] = None
        self._last_sync: Optional[datetime] = None
        self._heartbeat_count = 0
        self._sync_count = 0

    def start(self) -> bool:
        """
        Start the sync daemon.

        Returns:
            True if started successfully
        """
        if self._running:
            logger.warning("Sync daemon already running")
            return False

        if not self.storage_config.is_configured:
            logger.warning("Cloud storage not configured, sync daemon disabled")
            return False

        logger.info("Starting sync daemon...")
        self._running = True
        self._stop_event.clear()

        # Test connection
        conn_status = self.storage.test_connection()
        if not conn_status["r2"]["connected"]:
            logger.error(f"R2 connection failed: {conn_status['r2']['error']}")
            self._running = False
            return False

        logger.info("R2 connection successful")

        # Register this node
        if not self._initial_registration():
            logger.error("Node registration failed")
            self._running = False
            return False

        # Start background threads
        heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name="brainbot-heartbeat",
            daemon=True,
        )
        heartbeat_thread.start()
        self._threads.append(heartbeat_thread)

        sync_thread = threading.Thread(
            target=self._brain_sync_loop,
            name="brainbot-sync",
            daemon=True,
        )
        sync_thread.start()
        self._threads.append(sync_thread)

        event_thread = threading.Thread(
            target=self._event_watch_loop,
            name="brainbot-events",
            daemon=True,
        )
        event_thread.start()
        self._threads.append(event_thread)

        logger.info("Sync daemon started")
        return True

    def stop(self) -> None:
        """Stop the sync daemon."""
        if not self._running:
            return

        logger.info("Stopping sync daemon...")
        self._running = False
        self._stop_event.set()

        # Log shutdown event
        try:
            self.event_log.log_node_shutdown("normal")
        except Exception:
            pass

        # Wait for threads
        for thread in self._threads:
            thread.join(timeout=5)

        self._threads.clear()
        logger.info("Sync daemon stopped")

    def _initial_registration(self) -> bool:
        """Perform initial node registration."""
        try:
            # Register in registry
            success = self.registry.register(
                node_id=self.node_id,
                hostname=self.hostname,
                persona=self.persona,
                manifest=self.manifest,
            )

            if success:
                # Log boot event
                self.event_log.log_node_boot({
                    "hostname": self.hostname,
                    "persona_name": self.persona.display_name,
                    "role": self.persona.role,
                    "capabilities": [c.value for c in self.manifest.get_available_capabilities()],
                    "cpu_cores": self.manifest.cpu_cores,
                    "ram_gb": round(self.manifest.ram_gb, 1),
                    "version": get_version(),
                })
                logger.info(f"Node registered: {self.persona.display_name} (v{get_version()})")

            return success
        except Exception as e:
            logger.error(f"Registration failed: {e}")
            return False

    def _heartbeat_loop(self) -> None:
        """Background loop for heartbeat updates."""
        while self._running:
            try:
                if self._stop_event.wait(timeout=self.heartbeat_interval):
                    break

                # Send heartbeat to registry
                success = self.registry.heartbeat(self.node_id)
                if success:
                    self._last_heartbeat = datetime.now()
                    self._heartbeat_count += 1

                    # Log heartbeat event for network visibility
                    self.event_log.log_heartbeat({
                        "status": "online",
                        "heartbeat_count": self._heartbeat_count,
                        "last_sync": self._last_sync.isoformat() if self._last_sync else None,
                        "sync_count": self._sync_count,
                        "version": get_version(),
                    })

                    logger.debug(f"Heartbeat #{self._heartbeat_count}")
                else:
                    logger.warning("Heartbeat failed")

            except Exception as e:
                logger.error(f"Heartbeat loop error: {e}")

    def _brain_sync_loop(self) -> None:
        """Background loop for brain memory synchronization."""
        while self._running:
            try:
                if self._stop_event.wait(timeout=self.sync_interval):
                    break

                # Perform sync
                stats = self.memory_sync.sync()
                self._last_sync = datetime.now()
                self._sync_count += 1

                if stats["uploaded"] > 0 or stats["downloaded"] > 0:
                    logger.info(
                        f"Sync #{self._sync_count}: "
                        f"{stats['uploaded']} up, {stats['downloaded']} down"
                    )
                else:
                    logger.debug(f"Sync #{self._sync_count}: no changes")

            except Exception as e:
                logger.error(f"Brain sync loop error: {e}")

    def _event_watch_loop(self) -> None:
        """Background loop for watching network events."""
        last_check = datetime.now()

        while self._running:
            try:
                if self._stop_event.wait(timeout=30):  # Check every 30 seconds
                    break

                # Get recent events from other nodes
                from .models import EventType
                events = self.event_log.get_recent_events(
                    hours=1,
                    event_types=[
                        EventType.TASK_CREATED,
                        EventType.MEMORY_CREATED,
                    ],
                    limit=50,
                )

                # Filter for events since last check, not from this node
                new_events = [
                    e for e in events
                    if e.timestamp > last_check and e.node_id != self.node_id
                ]

                for event in new_events:
                    self._handle_network_event(event)

                last_check = datetime.now()

            except Exception as e:
                logger.error(f"Event watch loop error: {e}")

    def _handle_network_event(self, event) -> None:
        """Handle an event from another node."""
        from .models import EventType

        if event.event_type == EventType.TASK_CREATED.value:
            # Check if this task is for us
            task_data = event.data
            required_caps = set(task_data.get("required_capabilities", []))
            our_caps = {c.value for c in self.manifest.get_available_capabilities()}

            if required_caps.issubset(our_caps):
                logger.info(f"Received task: {task_data.get('task_type')}")
                if self.on_task_received:
                    self.on_task_received(task_data)

        elif event.event_type == EventType.MEMORY_CREATED.value:
            # New memory created - will be synced in next sync cycle
            logger.debug(f"New memory from {event.node_id[:8]}: {event.data.get('filename')}")

    def force_sync(self) -> dict:
        """Force an immediate brain sync."""
        return self.memory_sync.sync()

    def force_heartbeat(self) -> bool:
        """Force an immediate heartbeat."""
        return self.registry.heartbeat(self.node_id)

    def get_status(self) -> dict:
        """Get daemon status."""
        return {
            "running": self._running,
            "node_id": self.node_id,
            "persona": self.persona.display_name,
            "last_heartbeat": self._last_heartbeat.isoformat() if self._last_heartbeat else None,
            "last_sync": self._last_sync.isoformat() if self._last_sync else None,
            "heartbeat_count": self._heartbeat_count,
            "sync_count": self._sync_count,
            "threads_alive": sum(1 for t in self._threads if t.is_alive()),
        }

    def get_online_nodes(self) -> list:
        """Get list of online nodes in the network."""
        return self.registry.get_online_nodes()

    @property
    def is_running(self) -> bool:
        """Check if daemon is running."""
        return self._running
