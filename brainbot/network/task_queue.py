"""Distributed task queue using R2 storage."""

import json
import logging
import uuid
from datetime import datetime
from typing import Optional

from .models import CapabilityManifest, HardwareCapability, NetworkTask
from .storage import StorageClient
from .event_log import EventLog

logger = logging.getLogger(__name__)


class TaskQueue:
    """
    Distributed task queue stored in R2.

    Structure:
    - tasks/pending/{task_id}.json - Tasks waiting to be claimed
    - tasks/claimed/{task_id}.json - Tasks being worked on
    - tasks/completed/{task_id}.json - Finished tasks
    - tasks/failed/{task_id}.json - Failed tasks
    """

    def __init__(
        self,
        storage: StorageClient,
        event_log: EventLog,
        node_id: str,
    ):
        """
        Initialize task queue.

        Args:
            storage: Cloud storage client
            event_log: Event log for recording task events
            node_id: This node's ID
        """
        self.storage = storage
        self.event_log = event_log
        self.node_id = node_id

    def enqueue(self, task: NetworkTask) -> bool:
        """
        Add a task to the pending queue.

        Args:
            task: Task to enqueue

        Returns:
            True if successful
        """
        # Ensure task has an ID
        if not task.task_id:
            task.task_id = str(uuid.uuid4())

        task.status = "pending"
        task.created_by = self.node_id
        task.created_at = datetime.now()

        key = f"tasks/pending/{task.task_id}.json"

        if self.storage.write(key, task.model_dump(mode="json")):
            self.event_log.log_task_created(
                task_id=task.task_id,
                task_type=task.task_type,
                required_capabilities=task.required_capabilities,
            )
            logger.info(f"Enqueued task: {task.task_type} ({task.task_id[:8]})")
            return True

        return False

    def get_pending_tasks(
        self,
        limit: int = 100,
    ) -> list[NetworkTask]:
        """
        Get all pending tasks.

        Args:
            limit: Maximum tasks to return

        Returns:
            List of pending tasks
        """
        tasks = []
        keys = self.storage.list_keys("tasks/pending/", max_keys=limit)

        for key in keys:
            data = self.storage.read_json(key)
            if data:
                try:
                    task = NetworkTask(**data)
                    tasks.append(task)
                except Exception as e:
                    logger.warning(f"Failed to parse task {key}: {e}")

        # Sort by priority (highest first) then creation time
        tasks.sort(key=lambda t: (-t.priority, t.created_at))
        return tasks

    def get_pending_for_node(
        self,
        manifest: CapabilityManifest,
        limit: int = 10,
    ) -> list[NetworkTask]:
        """
        Get pending tasks that this node can handle.

        Args:
            manifest: This node's capability manifest
            limit: Maximum tasks to return

        Returns:
            List of claimable tasks
        """
        all_pending = self.get_pending_tasks(limit=100)
        our_caps = {c.value for c in manifest.get_available_capabilities()}

        claimable = []
        for task in all_pending:
            # Check if targeted at a specific node
            if task.target_node and task.target_node != self.node_id:
                continue

            # Check required capabilities
            if task.required_capabilities:
                required = set(task.required_capabilities)
                if not required.issubset(our_caps):
                    continue

            # Check resources
            if task.min_ram_gb > 0 and manifest.ram_gb < task.min_ram_gb:
                continue
            if task.min_disk_gb > 0 and manifest.disk_gb < task.min_disk_gb:
                continue

            claimable.append(task)

            if len(claimable) >= limit:
                break

        return claimable

    def claim(self, task_id: str) -> Optional[NetworkTask]:
        """
        Attempt to claim a task (atomic operation).

        Args:
            task_id: Task ID to claim

        Returns:
            The claimed task, or None if claim failed
        """
        pending_key = f"tasks/pending/{task_id}.json"
        claimed_key = f"tasks/claimed/{task_id}.json"

        # Read pending task
        data = self.storage.read_json(pending_key)
        if data is None:
            logger.debug(f"Task {task_id[:8]} not found or already claimed")
            return None

        try:
            task = NetworkTask(**data)
        except Exception as e:
            logger.warning(f"Failed to parse task {task_id}: {e}")
            return None

        # Update task status
        task.status = "claimed"
        task.claimed_by = self.node_id
        task.claimed_at = datetime.now()

        # Attempt atomic claim by writing to claimed and deleting from pending
        # Note: This is not truly atomic in S3/R2, but works for low-contention scenarios
        if self.storage.write(claimed_key, task.model_dump(mode="json")):
            if self.storage.delete(pending_key):
                self.event_log.log_task_claimed(
                    task_id=task.task_id,
                    task_type=task.task_type,
                )
                logger.info(f"Claimed task: {task.task_type} ({task_id[:8]})")
                return task
            else:
                # Rollback: delete claimed
                self.storage.delete(claimed_key)

        return None

    def complete(
        self,
        task_id: str,
        result: Optional[dict] = None,
    ) -> bool:
        """
        Mark a task as completed.

        Args:
            task_id: Task ID to complete
            result: Optional result data

        Returns:
            True if successful
        """
        claimed_key = f"tasks/claimed/{task_id}.json"
        completed_key = f"tasks/completed/{task_id}.json"

        # Read claimed task
        data = self.storage.read_json(claimed_key)
        if data is None:
            logger.warning(f"Claimed task {task_id[:8]} not found")
            return False

        try:
            task = NetworkTask(**data)
        except Exception as e:
            logger.warning(f"Failed to parse task {task_id}: {e}")
            return False

        # Update task
        task.status = "completed"
        task.completed_at = datetime.now()
        task.result = result

        # Move to completed
        if self.storage.write(completed_key, task.model_dump(mode="json")):
            self.storage.delete(claimed_key)
            self.event_log.log_task_completed(
                task_id=task.task_id,
                task_type=task.task_type,
                success=True,
            )
            logger.info(f"Completed task: {task.task_type} ({task_id[:8]})")
            return True

        return False

    def fail(
        self,
        task_id: str,
        error: str,
    ) -> bool:
        """
        Mark a task as failed.

        Args:
            task_id: Task ID that failed
            error: Error message

        Returns:
            True if successful
        """
        claimed_key = f"tasks/claimed/{task_id}.json"
        failed_key = f"tasks/failed/{task_id}.json"

        # Read claimed task
        data = self.storage.read_json(claimed_key)
        if data is None:
            logger.warning(f"Claimed task {task_id[:8]} not found")
            return False

        try:
            task = NetworkTask(**data)
        except Exception as e:
            logger.warning(f"Failed to parse task {task_id}: {e}")
            return False

        # Update task
        task.status = "failed"
        task.completed_at = datetime.now()
        task.error = error

        # Move to failed
        if self.storage.write(failed_key, task.model_dump(mode="json")):
            self.storage.delete(claimed_key)
            self.event_log.log_task_completed(
                task_id=task.task_id,
                task_type=task.task_type,
                success=False,
            )
            logger.warning(f"Failed task: {task.task_type} ({task_id[:8]}): {error}")
            return True

        return False

    def get_task(self, task_id: str) -> Optional[NetworkTask]:
        """Get a task by ID (from any status)."""
        for status in ["pending", "claimed", "completed", "failed"]:
            key = f"tasks/{status}/{task_id}.json"
            data = self.storage.read_json(key)
            if data:
                try:
                    return NetworkTask(**data)
                except Exception:
                    pass
        return None

    def get_my_claimed_tasks(self) -> list[NetworkTask]:
        """Get tasks claimed by this node."""
        tasks = []
        keys = self.storage.list_keys("tasks/claimed/")

        for key in keys:
            data = self.storage.read_json(key)
            if data:
                try:
                    task = NetworkTask(**data)
                    if task.claimed_by == self.node_id:
                        tasks.append(task)
                except Exception:
                    pass

        return tasks

    def get_queue_stats(self) -> dict:
        """Get queue statistics."""
        return {
            "pending": len(self.storage.list_keys("tasks/pending/")),
            "claimed": len(self.storage.list_keys("tasks/claimed/")),
            "completed": len(self.storage.list_keys("tasks/completed/", max_keys=100)),
            "failed": len(self.storage.list_keys("tasks/failed/", max_keys=100)),
        }

    def cleanup_old_tasks(self, days: int = 7) -> int:
        """
        Clean up old completed/failed tasks.

        Args:
            days: Remove tasks older than this many days

        Returns:
            Number of tasks removed
        """
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(days=days)
        removed = 0

        for status in ["completed", "failed"]:
            keys = self.storage.list_keys(f"tasks/{status}/")
            for key in keys:
                data = self.storage.read_json(key)
                if data:
                    try:
                        task = NetworkTask(**data)
                        if task.completed_at and task.completed_at < cutoff:
                            if self.storage.delete(key):
                                removed += 1
                    except Exception:
                        pass

        if removed:
            logger.info(f"Cleaned up {removed} old tasks")
        return removed
