"""Append-only event log for network events."""

import hashlib
import json
import logging
import uuid
from datetime import datetime, date
from typing import Optional, Generator

from .models import EventType, NetworkEvent
from .storage import StorageClient

logger = logging.getLogger(__name__)


class EventLog:
    """
    Append-only event log stored in R2.

    Events are stored as individual JSON files:
    events/{YYYY-MM-DD}/{timestamp}_{node_id}_{type}.json

    This structure allows:
    - Easy date-based filtering
    - Parallel writes from multiple nodes
    - Efficient prefix-based listing
    """

    def __init__(self, storage: StorageClient, node_id: str):
        """
        Initialize event log.

        Args:
            storage: Storage client for R2/S3
            node_id: This node's ID for event attribution
        """
        self.storage = storage
        self.node_id = node_id
        self._last_event_id: Optional[str] = None

    def append(self, event_type: EventType, data: dict) -> Optional[NetworkEvent]:
        """
        Append an event to the log.

        Args:
            event_type: Type of event
            data: Event data payload

        Returns:
            The created NetworkEvent, or None if failed
        """
        event_id = str(uuid.uuid4())
        timestamp = datetime.now()

        # Create event
        event = NetworkEvent(
            event_id=event_id,
            timestamp=timestamp,
            node_id=self.node_id,
            event_type=event_type.value,
            data=data,
            previous_event_id=self._last_event_id,
        )

        # Compute checksum
        event.checksum = self._compute_checksum(event)

        # Generate key
        date_str = timestamp.strftime("%Y-%m-%d")
        time_str = timestamp.strftime("%H%M%S%f")[:12]  # Include microseconds
        key = f"events/{date_str}/{time_str}_{self.node_id[:8]}_{event_type.value}.json"

        # Write to storage
        if self.storage.write(key, event.model_dump(mode="json")):
            self._last_event_id = event_id
            logger.debug(f"Logged event: {event_type.value}")
            return event
        else:
            logger.error(f"Failed to log event: {event_type.value}")
            return None

    def _compute_checksum(self, event: NetworkEvent) -> str:
        """Compute blake2b checksum for event integrity."""
        # Serialize event data for hashing (excluding checksum itself)
        data_to_hash = {
            "event_id": event.event_id,
            "timestamp": event.timestamp.isoformat(),
            "node_id": event.node_id,
            "event_type": event.event_type,
            "data": event.data,
            "previous_event_id": event.previous_event_id,
        }
        json_str = json.dumps(data_to_hash, sort_keys=True, default=str)
        return hashlib.blake2b(json_str.encode(), digest_size=16).hexdigest()

    def get_events(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        node_id: Optional[str] = None,
        event_types: Optional[list[EventType]] = None,
        limit: int = 100,
    ) -> list[NetworkEvent]:
        """
        Get events matching filters.

        Args:
            since: Only events after this time
            until: Only events before this time
            node_id: Only events from this node
            event_types: Only these event types
            limit: Maximum events to return

        Returns:
            List of matching events
        """
        events = []

        # Determine date range for prefix filtering
        start_date = since.date() if since else date.today()
        end_date = until.date() if until else date.today()

        # List events by date
        current_date = start_date
        while current_date <= end_date and len(events) < limit:
            prefix = f"events/{current_date.strftime('%Y-%m-%d')}/"
            keys = self.storage.list_keys(prefix, max_keys=1000)

            for key in keys:
                if len(events) >= limit:
                    break

                # Parse event
                event_data = self.storage.read_json(key)
                if event_data is None:
                    continue

                try:
                    event = NetworkEvent(**event_data)
                except Exception as e:
                    logger.warning(f"Failed to parse event {key}: {e}")
                    continue

                # Apply filters
                if since and event.timestamp < since:
                    continue
                if until and event.timestamp > until:
                    continue
                if node_id and event.node_id != node_id:
                    continue
                if event_types:
                    type_values = [t.value for t in event_types]
                    if event.event_type not in type_values:
                        continue

                events.append(event)

            # Move to next date
            from datetime import timedelta
            current_date += timedelta(days=1)

        return events

    def get_recent_events(
        self,
        hours: int = 24,
        event_types: Optional[list[EventType]] = None,
        limit: int = 100,
    ) -> list[NetworkEvent]:
        """Get events from the last N hours."""
        from datetime import timedelta
        since = datetime.now() - timedelta(hours=hours)
        return self.get_events(since=since, event_types=event_types, limit=limit)

    def stream_events(
        self,
        since: Optional[datetime] = None,
        event_types: Optional[list[EventType]] = None,
    ) -> Generator[NetworkEvent, None, None]:
        """
        Stream events as a generator.

        Args:
            since: Only events after this time
            event_types: Only these event types

        Yields:
            NetworkEvent objects
        """
        # Start from since date or today
        start_date = since.date() if since else date.today()
        current_date = start_date

        while current_date <= date.today():
            prefix = f"events/{current_date.strftime('%Y-%m-%d')}/"
            keys = self.storage.list_keys(prefix, max_keys=1000)

            for key in keys:
                event_data = self.storage.read_json(key)
                if event_data is None:
                    continue

                try:
                    event = NetworkEvent(**event_data)
                except Exception:
                    continue

                # Apply filters
                if since and event.timestamp < since:
                    continue
                if event_types:
                    type_values = [t.value for t in event_types]
                    if event.event_type not in type_values:
                        continue

                yield event

            from datetime import timedelta
            current_date += timedelta(days=1)

    def log_node_boot(self, manifest_summary: dict) -> Optional[NetworkEvent]:
        """Log node boot event with hardware summary."""
        return self.append(EventType.NODE_BOOT, manifest_summary)

    def log_node_shutdown(self, reason: str = "normal") -> Optional[NetworkEvent]:
        """Log node shutdown event."""
        return self.append(EventType.NODE_SHUTDOWN, {"reason": reason})

    def log_heartbeat(self, status: dict) -> Optional[NetworkEvent]:
        """Log heartbeat event with node status."""
        return self.append(EventType.NODE_HEARTBEAT, status)

    def log_memory_created(
        self,
        filename: str,
        category: str,
        content_hash: str,
    ) -> Optional[NetworkEvent]:
        """Log memory file creation."""
        return self.append(
            EventType.MEMORY_CREATED,
            {
                "filename": filename,
                "category": category,
                "content_hash": content_hash,
            },
        )

    def log_memory_updated(
        self,
        filename: str,
        content_hash: str,
        previous_hash: Optional[str] = None,
        update_source: str = "local",  # "local", "network", "merge"
    ) -> Optional[NetworkEvent]:
        """Log memory file update."""
        return self.append(
            EventType.MEMORY_UPDATED,
            {
                "filename": filename,
                "content_hash": content_hash,
                "previous_hash": previous_hash,
                "update_source": update_source,
            },
        )

    def log_memory_synced(
        self,
        filename: str,
        direction: str,  # "upload" or "download"
        content_hash: str,
    ) -> Optional[NetworkEvent]:
        """Log memory sync event."""
        return self.append(
            EventType.MEMORY_SYNCED,
            {
                "filename": filename,
                "direction": direction,
                "content_hash": content_hash,
            },
        )

    def log_task_created(
        self,
        task_id: str,
        task_type: str,
        required_capabilities: list[str],
    ) -> Optional[NetworkEvent]:
        """Log task creation."""
        return self.append(
            EventType.TASK_CREATED,
            {
                "task_id": task_id,
                "task_type": task_type,
                "required_capabilities": required_capabilities,
            },
        )

    def log_task_claimed(
        self,
        task_id: str,
        task_type: str,
    ) -> Optional[NetworkEvent]:
        """Log task claim by this node."""
        return self.append(
            EventType.TASK_CLAIMED,
            {
                "task_id": task_id,
                "task_type": task_type,
            },
        )

    def log_task_completed(
        self,
        task_id: str,
        task_type: str,
        success: bool,
    ) -> Optional[NetworkEvent]:
        """Log task completion."""
        return self.append(
            EventType.TASK_COMPLETED,
            {
                "task_id": task_id,
                "task_type": task_type,
                "success": success,
            },
        )
