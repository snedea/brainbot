"""Task routing based on node capabilities."""

import logging
from typing import Optional, TYPE_CHECKING

from .models import (
    CapabilityManifest,
    HardwareCapability,
    NetworkTask,
    NodeRegistryEntry,
)
from .registry import NodeRegistry

if TYPE_CHECKING:
    from .task_queue import TaskQueue

logger = logging.getLogger(__name__)


class TaskRequirements:
    """Requirements for a task to be executed."""

    def __init__(
        self,
        required_capabilities: Optional[list[HardwareCapability]] = None,
        preferred_capabilities: Optional[list[HardwareCapability]] = None,
        min_ram_gb: float = 0.0,
        min_disk_gb: float = 0.0,
        prefer_local: bool = False,
    ):
        """
        Initialize task requirements.

        Args:
            required_capabilities: Capabilities that MUST be present
            preferred_capabilities: Capabilities that are nice to have
            min_ram_gb: Minimum RAM required
            min_disk_gb: Minimum disk space required
            prefer_local: If True, prefer running on the requesting node
        """
        self.required_capabilities = required_capabilities or []
        self.preferred_capabilities = preferred_capabilities or []
        self.min_ram_gb = min_ram_gb
        self.min_disk_gb = min_disk_gb
        self.prefer_local = prefer_local


# Task type to requirements mapping
TASK_REQUIREMENTS = {
    # Display tasks
    "display_text": TaskRequirements(
        required_capabilities=[HardwareCapability.DISPLAY_1INCH],
    ),
    "display_story": TaskRequirements(
        required_capabilities=[HardwareCapability.DISPLAY_5INCH],
    ),
    "display_status": TaskRequirements(
        required_capabilities=[HardwareCapability.DISPLAY_5INCH],
        preferred_capabilities=[HardwareCapability.DISPLAY_1INCH],
    ),

    # LED tasks
    "led_mood": TaskRequirements(
        required_capabilities=[HardwareCapability.LED_STRIP],
    ),
    "led_pattern": TaskRequirements(
        required_capabilities=[HardwareCapability.LED_STRIP],
    ),

    # GPU tasks
    "generate_image": TaskRequirements(
        required_capabilities=[],  # Any GPU
        preferred_capabilities=[
            HardwareCapability.GPU_CUDA,
            HardwareCapability.GPU_ROCM,
            HardwareCapability.GPU_METAL,
        ],
        min_ram_gb=8.0,
    ),
    "process_video": TaskRequirements(
        preferred_capabilities=[
            HardwareCapability.GPU_CUDA,
            HardwareCapability.GPU_ROCM,
        ],
        min_ram_gb=8.0,
        min_disk_gb=10.0,
    ),

    # Audio tasks
    "speak": TaskRequirements(
        required_capabilities=[HardwareCapability.SPEAKER],
    ),
    "transcription": TaskRequirements(
        required_capabilities=[HardwareCapability.MICROPHONE],
    ),

    # Camera tasks
    "photo": TaskRequirements(
        required_capabilities=[],  # Any camera
        preferred_capabilities=[
            HardwareCapability.CAMERA_PI,
            HardwareCapability.CAMERA_USB,
        ],
    ),

    # General tasks - can run anywhere
    "delegate_to_claude": TaskRequirements(
        prefer_local=True,
    ),
    "memory_sync": TaskRequirements(
        prefer_local=True,
    ),
}


class TaskRouter:
    """
    Routes tasks to the most capable node in the network.

    Considers:
    - Required capabilities
    - Preferred capabilities
    - Resource requirements (RAM, disk)
    - Node availability (online status)
    - Load balancing (prefer least busy)
    """

    def __init__(self, registry: NodeRegistry, local_node_id: str):
        """
        Initialize task router.

        Args:
            registry: Node registry for looking up nodes
            local_node_id: This node's ID (for prefer_local)
        """
        self.registry = registry
        self.local_node_id = local_node_id

    def route_task(self, task: NetworkTask) -> Optional[str]:
        """
        Find the best node for a task.

        Args:
            task: The task to route

        Returns:
            Node ID of the best node, or None if no suitable node
        """
        # Get requirements for this task type
        requirements = TASK_REQUIREMENTS.get(
            task.task_type,
            TaskRequirements(),
        )

        # Override with task-specific requirements
        if task.required_capabilities:
            requirements.required_capabilities = [
                HardwareCapability(c) for c in task.required_capabilities
            ]
        if task.preferred_capabilities:
            requirements.preferred_capabilities = [
                HardwareCapability(c) for c in task.preferred_capabilities
            ]
        if task.min_ram_gb > 0:
            requirements.min_ram_gb = task.min_ram_gb
        if task.min_disk_gb > 0:
            requirements.min_disk_gb = task.min_disk_gb

        # Find capable nodes
        candidates = self._find_capable_nodes(requirements)

        if not candidates:
            logger.warning(f"No capable nodes for task {task.task_type}")
            return None

        # Select best candidate
        return self._select_best(candidates, requirements)

    def _find_capable_nodes(
        self,
        requirements: TaskRequirements,
    ) -> list[NodeRegistryEntry]:
        """Find nodes that meet the requirements."""
        candidates = []

        # Get all online nodes
        nodes = self.registry.get_online_nodes()

        for node in nodes:
            # Check required capabilities
            if requirements.required_capabilities:
                node_caps = set(node.capabilities)
                required = {c.value for c in requirements.required_capabilities}

                if not required.issubset(node_caps):
                    continue

            # Check resource requirements
            manifest = self.registry.get_manifest(node.node_id)
            if manifest:
                if requirements.min_ram_gb > 0 and manifest.ram_gb < requirements.min_ram_gb:
                    continue
                if requirements.min_disk_gb > 0 and manifest.disk_gb < requirements.min_disk_gb:
                    continue

            candidates.append(node)

        return candidates

    def _select_best(
        self,
        candidates: list[NodeRegistryEntry],
        requirements: TaskRequirements,
    ) -> str:
        """Select the best node from candidates."""
        if not candidates:
            return None

        # Score each candidate
        scored = []
        for node in candidates:
            score = self._score_node(node, requirements)
            scored.append((score, node))

        # Sort by score (highest first)
        scored.sort(key=lambda x: x[0], reverse=True)

        best = scored[0][1]
        logger.debug(
            f"Selected node {best.persona.display_name} "
            f"(score: {scored[0][0]})"
        )
        return best.node_id

    def _score_node(
        self,
        node: NodeRegistryEntry,
        requirements: TaskRequirements,
    ) -> float:
        """Score a node for a task (higher is better)."""
        score = 0.0
        node_caps = set(node.capabilities)

        # Preferred capabilities bonus
        for cap in requirements.preferred_capabilities:
            if cap.value in node_caps:
                score += 10.0

        # Local node preference
        if requirements.prefer_local and node.node_id == self.local_node_id:
            score += 50.0

        # Role match bonus
        if node.persona.role == self._task_to_role(requirements):
            score += 20.0

        # More capabilities = more versatile
        score += len(node_caps) * 0.5

        # Recent heartbeat = more reliable
        if node.is_online(60):  # Very recent heartbeat
            score += 5.0

        return score

    def _task_to_role(self, requirements: TaskRequirements) -> Optional[str]:
        """Map task requirements to a node role."""
        if requirements.required_capabilities:
            first_cap = requirements.required_capabilities[0]
            role_map = {
                HardwareCapability.GPU_CUDA: "compute",
                HardwareCapability.GPU_ROCM: "compute",
                HardwareCapability.GPU_METAL: "compute",
                HardwareCapability.DISPLAY_5INCH: "display",
                HardwareCapability.DISPLAY_1INCH: "status",
                HardwareCapability.LED_STRIP: "ambient",
                HardwareCapability.CAMERA_PI: "observer",
                HardwareCapability.CAMERA_USB: "observer",
                HardwareCapability.MICROPHONE: "listener",
                HardwareCapability.SPEAKER: "voice",
            }
            return role_map.get(first_cap)
        return None

    def can_handle_locally(
        self,
        task: NetworkTask,
        manifest: CapabilityManifest,
    ) -> bool:
        """
        Check if this node can handle a task locally.

        Args:
            task: The task to check
            manifest: This node's capability manifest

        Returns:
            True if this node can handle the task
        """
        requirements = TASK_REQUIREMENTS.get(
            task.task_type,
            TaskRequirements(),
        )

        # Override with task-specific requirements
        if task.required_capabilities:
            requirements.required_capabilities = [
                HardwareCapability(c) for c in task.required_capabilities
            ]

        # Check required capabilities
        if requirements.required_capabilities:
            for cap in requirements.required_capabilities:
                if not manifest.has_capability(cap):
                    return False

        # Check resources
        if requirements.min_ram_gb > 0 and manifest.ram_gb < requirements.min_ram_gb:
            return False
        if requirements.min_disk_gb > 0 and manifest.disk_gb < requirements.min_disk_gb:
            return False

        return True

    def get_routable_task_types(
        self,
        manifest: CapabilityManifest,
    ) -> list[str]:
        """
        Get task types that this node can handle.

        Args:
            manifest: This node's capability manifest

        Returns:
            List of task type strings
        """
        routable = []
        our_caps = set(c.value for c in manifest.get_available_capabilities())

        for task_type, requirements in TASK_REQUIREMENTS.items():
            # Check if we have all required capabilities
            if requirements.required_capabilities:
                required = {c.value for c in requirements.required_capabilities}
                if not required.issubset(our_caps):
                    continue

            # Check if we have any preferred capabilities
            if requirements.preferred_capabilities:
                preferred = {c.value for c in requirements.preferred_capabilities}
                if not preferred.intersection(our_caps):
                    # No preferred caps, but maybe required was empty
                    if requirements.required_capabilities:
                        continue

            routable.append(task_type)

        return routable


class TaskSubmitter:
    """
    Helper class to submit tasks to the network.

    Combines TaskRouter (to find target) and TaskQueue (to enqueue).
    """

    def __init__(
        self,
        router: TaskRouter,
        queue: "TaskQueue",
        local_manifest: CapabilityManifest,
    ):
        """
        Initialize task submitter.

        Args:
            router: Task router for finding target nodes
            queue: Task queue for enqueueing tasks
            local_manifest: This node's capability manifest
        """
        self.router = router
        self.queue = queue
        self.local_manifest = local_manifest

    def submit(
        self,
        task_type: str,
        payload: dict,
        priority: int = 1,
        force_remote: bool = False,
    ) -> tuple[bool, str]:
        """
        Submit a task to the network.

        Args:
            task_type: Type of task (e.g., "display_story", "led_mood")
            payload: Task-specific payload data
            priority: Task priority (1-10, higher = more urgent)
            force_remote: If True, don't execute locally even if capable

        Returns:
            Tuple of (success, message)
        """
        import uuid

        # Build task
        task = NetworkTask(
            task_id=str(uuid.uuid4()),
            task_type=task_type,
            payload=payload,
            priority=priority,
            created_by=self.router.local_node_id,
        )

        # Check if we can handle locally
        if not force_remote and self.router.can_handle_locally(task, self.local_manifest):
            # Execute locally - will be picked up by local executor
            task.target_node = self.router.local_node_id
            if self.queue.enqueue(task):
                return True, f"Task queued for local execution ({task.task_id[:8]})"
            return False, "Failed to enqueue task"

        # Route to remote node
        target_node = self.router.route_task(task)
        if target_node is None:
            return False, f"No capable nodes found for task type: {task_type}"

        task.target_node = target_node
        if self.queue.enqueue(task):
            return True, f"Task routed to node {target_node[:8]} ({task.task_id[:8]})"
        return False, "Failed to enqueue task"

    def submit_to_node(
        self,
        node_id: str,
        task_type: str,
        payload: dict,
        priority: int = 1,
    ) -> tuple[bool, str]:
        """
        Submit a task to a specific node.

        Args:
            node_id: Target node ID
            task_type: Type of task
            payload: Task-specific payload
            priority: Task priority

        Returns:
            Tuple of (success, message)
        """
        import uuid

        task = NetworkTask(
            task_id=str(uuid.uuid4()),
            task_type=task_type,
            payload=payload,
            priority=priority,
            created_by=self.router.local_node_id,
            target_node=node_id,
        )

        if self.queue.enqueue(task):
            return True, f"Task sent to node {node_id[:8]} ({task.task_id[:8]})"
        return False, "Failed to enqueue task"

    def broadcast(
        self,
        task_type: str,
        payload: dict,
        priority: int = 1,
    ) -> tuple[int, list[str]]:
        """
        Broadcast a task to all capable nodes.

        Args:
            task_type: Type of task
            payload: Task-specific payload
            priority: Task priority

        Returns:
            Tuple of (count of nodes, list of error messages)
        """
        import uuid

        # Find all capable nodes
        base_task = NetworkTask(
            task_id="",  # Will be set per-node
            task_type=task_type,
            payload=payload,
            priority=priority,
        )

        requirements = TASK_REQUIREMENTS.get(task_type, TaskRequirements())
        if requirements.required_capabilities:
            capable_nodes = self.router.registry.find_nodes_with_capabilities(
                requirements.required_capabilities,
                require_all=True,
                only_online=True,
            )
        else:
            capable_nodes = self.router.registry.get_online_nodes()

        if not capable_nodes:
            return 0, ["No capable nodes online"]

        sent = 0
        errors = []

        for node in capable_nodes:
            task = NetworkTask(
                task_id=str(uuid.uuid4()),
                task_type=task_type,
                payload=payload,
                priority=priority,
                created_by=self.router.local_node_id,
                target_node=node.node_id,
            )

            if self.queue.enqueue(task):
                sent += 1
            else:
                errors.append(f"Failed to send to {node.node_id[:8]}")

        return sent, errors
