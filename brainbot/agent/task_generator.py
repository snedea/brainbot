"""
Memory-Driven Task Generator for BrainBot.

Analyzes BrainBot's memories to generate tasks, including:
- Follow-up tasks from past conversations
- Research tasks from noted interests
- Delegation tasks for other nodes based on capabilities
- Maintenance tasks for memory organization

Works with the autonomous engine to create meaningful work
when BrainBot is idle.
"""

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class TaskPriority(int, Enum):
    """Task priority levels."""
    LOW = 1
    NORMAL = 3
    HIGH = 5
    URGENT = 8
    CRITICAL = 10


class GeneratedTaskType(str, Enum):
    """Types of tasks that can be generated."""
    RESEARCH = "research"
    FOLLOW_UP = "follow_up"
    DELEGATE = "delegate"
    CREATIVE = "creative"
    MAINTENANCE = "maintenance"
    LEARNING = "learning"
    PROJECT = "project"


@dataclass
class GeneratedTask:
    """A task generated from memory analysis."""
    task_id: str
    task_type: GeneratedTaskType
    title: str
    description: str
    priority: TaskPriority
    source_memory: Optional[str] = None  # Which memory triggered this
    target_node: Optional[str] = None  # If delegation task
    required_capabilities: list[str] = None
    created_at: datetime = None

    def __post_init__(self):
        if not self.task_id:
            self.task_id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = datetime.now()
        if self.required_capabilities is None:
            self.required_capabilities = []


# Patterns to detect actionable items in memories
ACTION_PATTERNS = [
    # "I wanted to..." patterns
    (r"[Ii] wanted to (?:learn|research|look into|explore|find out about|understand) (.+?)(?:\.|$)", GeneratedTaskType.RESEARCH),
    (r"[Ii] should (?:learn|research|look into|explore|find out about) (.+?)(?:\.|$)", GeneratedTaskType.RESEARCH),

    # "I need to..." patterns
    (r"[Ii] need to (.+?)(?:\.|$)", GeneratedTaskType.FOLLOW_UP),
    (r"[Ii] should (.+?)(?:\.|$)", GeneratedTaskType.FOLLOW_UP),

    # "TODO" and explicit task markers
    (r"TODO[:\s]+(.+?)(?:\.|$)", GeneratedTaskType.FOLLOW_UP),
    (r"TASK[:\s]+(.+?)(?:\.|$)", GeneratedTaskType.FOLLOW_UP),
    (r"FOLLOW[- ]UP[:\s]+(.+?)(?:\.|$)", GeneratedTaskType.FOLLOW_UP),

    # "Delegate to..." patterns
    (r"[Dd]elegate (?:to )?(\w+)[:\s]+(.+?)(?:\.|$)", GeneratedTaskType.DELEGATE),
    (r"[Aa]sk (\w+) to (.+?)(?:\.|$)", GeneratedTaskType.DELEGATE),

    # "Write about..." patterns
    (r"[Ww]rite (?:a |about )?(.+?)(?:\.|$)", GeneratedTaskType.CREATIVE),
    (r"[Cc]reate (?:a |an )?(.+?)(?:\.|$)", GeneratedTaskType.CREATIVE),

    # "Learn about..." patterns
    (r"[Ll]earn (?:about |more about )?(.+?)(?:\.|$)", GeneratedTaskType.LEARNING),
    (r"[Ss]tudy (.+?)(?:\.|$)", GeneratedTaskType.LEARNING),

    # Project patterns
    (r"[Pp]roject[:\s]+(.+?)(?:\.|$)", GeneratedTaskType.PROJECT),
    (r"[Bb]uild (?:a |an )?(.+?)(?:\.|$)", GeneratedTaskType.PROJECT),
]

# Capability keywords for delegation
CAPABILITY_KEYWORDS = {
    "display": ["display", "show", "screen", "LCD", "visual"],
    "led": ["LED", "light", "color", "glow", "brightness"],
    "camera": ["camera", "photo", "picture", "image", "capture", "snapshot"],
    "gpu": ["GPU", "generate", "render", "compute", "process"],
    "audio": ["speak", "say", "voice", "sound", "audio", "music"],
}


class TaskGenerator:
    """
    Generates tasks from BrainBot's memories.

    Analyzes memory content to identify:
    - Things BrainBot wanted to do but hasn't yet
    - Follow-up items from conversations
    - Tasks suitable for delegation to other nodes
    - Maintenance and organization tasks
    """

    def __init__(
        self,
        brain=None,
        network_registry=None,
        task_queue=None,
        delegator=None,
    ):
        """
        Initialize the task generator.

        Args:
            brain: BrainMemory instance for memory access
            network_registry: NodeRegistry for finding capable nodes
            task_queue: TaskQueue for submitting tasks
            delegator: ClaudeDelegator for AI-assisted task generation
        """
        self.brain = brain
        self.network_registry = network_registry
        self.task_queue = task_queue
        self.delegator = delegator

        # Track generated tasks to avoid duplicates
        self._generated_task_hashes: set[str] = set()

    def _hash_task(self, title: str, description: str) -> str:
        """Create a hash to identify duplicate tasks."""
        import hashlib
        content = f"{title.lower()}:{description.lower()[:100]}"
        return hashlib.md5(content.encode()).hexdigest()

    def scan_memories_for_tasks(
        self,
        max_memories: int = 10,
        max_tasks: int = 5,
    ) -> list[GeneratedTask]:
        """
        Scan recent memories for potential tasks.

        Args:
            max_memories: Maximum memories to scan
            max_tasks: Maximum tasks to generate

        Returns:
            List of generated tasks
        """
        if not self.brain:
            return []

        tasks = []
        memories = self.brain.get_active_memories()[:max_memories]

        for memory in memories:
            content = self.brain.read_memory(memory, max_lines=100)
            if not content:
                continue

            # Scan for action patterns
            memory_tasks = self._extract_tasks_from_text(content, memory.name)
            tasks.extend(memory_tasks)

            if len(tasks) >= max_tasks:
                break

        # Filter duplicates
        unique_tasks = []
        for task in tasks:
            task_hash = self._hash_task(task.title, task.description)
            if task_hash not in self._generated_task_hashes:
                self._generated_task_hashes.add(task_hash)
                unique_tasks.append(task)

        return unique_tasks[:max_tasks]

    def _extract_tasks_from_text(
        self,
        text: str,
        source_memory: str,
    ) -> list[GeneratedTask]:
        """
        Extract tasks from a text using pattern matching.

        Args:
            text: Text to analyze
            source_memory: Name of source memory

        Returns:
            List of extracted tasks
        """
        tasks = []

        for pattern, task_type in ACTION_PATTERNS:
            matches = re.finditer(pattern, text, re.MULTILINE)
            for match in matches:
                if task_type == GeneratedTaskType.DELEGATE:
                    # Delegation patterns have two groups
                    if len(match.groups()) >= 2:
                        target = match.group(1)
                        action = match.group(2)
                        task = self._create_delegation_task(target, action, source_memory)
                    else:
                        continue
                else:
                    action = match.group(1).strip()
                    if len(action) < 5 or len(action) > 200:
                        continue  # Skip too short or too long

                    task = GeneratedTask(
                        task_id=str(uuid.uuid4()),
                        task_type=task_type,
                        title=self._create_title(task_type, action),
                        description=action,
                        priority=self._determine_priority(task_type, action),
                        source_memory=source_memory,
                    )

                tasks.append(task)

        return tasks

    def _create_title(self, task_type: GeneratedTaskType, action: str) -> str:
        """Create a concise title for a task."""
        # Truncate action for title
        action_short = action[:50] + "..." if len(action) > 50 else action

        prefixes = {
            GeneratedTaskType.RESEARCH: "Research:",
            GeneratedTaskType.FOLLOW_UP: "Follow up:",
            GeneratedTaskType.DELEGATE: "Delegate:",
            GeneratedTaskType.CREATIVE: "Create:",
            GeneratedTaskType.MAINTENANCE: "Maintain:",
            GeneratedTaskType.LEARNING: "Learn:",
            GeneratedTaskType.PROJECT: "Project:",
        }

        prefix = prefixes.get(task_type, "Task:")
        return f"{prefix} {action_short}"

    def _determine_priority(
        self,
        task_type: GeneratedTaskType,
        action: str,
    ) -> TaskPriority:
        """Determine priority based on task type and content."""
        action_lower = action.lower()

        # High priority keywords
        if any(kw in action_lower for kw in ["urgent", "important", "critical", "asap"]):
            return TaskPriority.HIGH

        # Type-based defaults
        priority_map = {
            GeneratedTaskType.FOLLOW_UP: TaskPriority.NORMAL,
            GeneratedTaskType.RESEARCH: TaskPriority.LOW,
            GeneratedTaskType.DELEGATE: TaskPriority.NORMAL,
            GeneratedTaskType.CREATIVE: TaskPriority.LOW,
            GeneratedTaskType.MAINTENANCE: TaskPriority.LOW,
            GeneratedTaskType.LEARNING: TaskPriority.LOW,
            GeneratedTaskType.PROJECT: TaskPriority.NORMAL,
        }

        return priority_map.get(task_type, TaskPriority.NORMAL)

    def _create_delegation_task(
        self,
        target: str,
        action: str,
        source_memory: str,
    ) -> GeneratedTask:
        """Create a task for delegation to another node."""
        # Detect required capabilities from action text
        capabilities = self._detect_capabilities(action)

        # Try to find actual node
        target_node_id = None
        if self.network_registry:
            target_node_id = self._find_node_by_name(target)

        return GeneratedTask(
            task_id=str(uuid.uuid4()),
            task_type=GeneratedTaskType.DELEGATE,
            title=f"Delegate to {target}: {action[:40]}...",
            description=action,
            priority=TaskPriority.NORMAL,
            source_memory=source_memory,
            target_node=target_node_id or target,
            required_capabilities=capabilities,
        )

    def _detect_capabilities(self, text: str) -> list[str]:
        """Detect required capabilities from text."""
        text_lower = text.lower()
        capabilities = []

        for cap_name, keywords in CAPABILITY_KEYWORDS.items():
            if any(kw.lower() in text_lower for kw in keywords):
                capabilities.append(cap_name)

        return capabilities

    def _find_node_by_name(self, name: str) -> Optional[str]:
        """Find a node ID by name."""
        if not self.network_registry:
            return None

        try:
            nodes = self.network_registry.get_all_nodes()
            name_lower = name.lower()

            for node in nodes:
                if node.persona.display_name.lower() == name_lower:
                    return node.node_id
                if node.persona.name.lower() == name_lower:
                    return node.node_id

        except Exception as e:
            logger.error(f"Error finding node by name: {e}")

        return None

    def generate_tasks_with_ai(
        self,
        max_tasks: int = 3,
    ) -> list[GeneratedTask]:
        """
        Use AI to analyze memories and generate tasks.

        Args:
            max_tasks: Maximum tasks to generate

        Returns:
            List of generated tasks
        """
        if not self.delegator or not self.brain:
            return []

        if not self.delegator.check_claude_available():
            return []

        # Get brain context
        brain_context = self.brain.build_context()[:3000]

        prompt = f"""You are BrainBot, reviewing your memories to find tasks.

## Your Current Memories

{brain_context}

---

**Task:** Identify 1-3 concrete tasks from your memories that you should work on.

For each task, provide:
1. TYPE: research, follow_up, creative, learning, or project
2. TITLE: Brief title (under 60 chars)
3. DESCRIPTION: What needs to be done (1-2 sentences)
4. PRIORITY: low, normal, or high

Format each task as:
---
TYPE: <type>
TITLE: <title>
DESCRIPTION: <description>
PRIORITY: <priority>
---

Focus on:
- Things you said you wanted to do
- Follow-ups from conversations
- Interesting topics to explore
- Projects to work on

Only include concrete, actionable tasks. If there's nothing clear to do, say "No tasks found."
"""

        result = self.delegator.delegate(task=prompt, timeout_minutes=5)

        if not result.success:
            logger.warning(f"AI task generation failed: {result.error}")
            return []

        return self._parse_ai_tasks(result.output)

    def _parse_ai_tasks(self, output: str) -> list[GeneratedTask]:
        """Parse tasks from AI output."""
        tasks = []

        if "No tasks found" in output:
            return tasks

        # Split by task delimiter
        task_blocks = re.split(r'\n---+\n', output)

        for block in task_blocks:
            if not block.strip():
                continue

            # Extract fields
            type_match = re.search(r'TYPE:\s*(\w+)', block, re.IGNORECASE)
            title_match = re.search(r'TITLE:\s*(.+)', block, re.IGNORECASE)
            desc_match = re.search(r'DESCRIPTION:\s*(.+?)(?=\n[A-Z]+:|$)', block, re.IGNORECASE | re.DOTALL)
            priority_match = re.search(r'PRIORITY:\s*(\w+)', block, re.IGNORECASE)

            if not (type_match and title_match and desc_match):
                continue

            # Parse type
            type_str = type_match.group(1).lower()
            type_map = {
                "research": GeneratedTaskType.RESEARCH,
                "follow_up": GeneratedTaskType.FOLLOW_UP,
                "followup": GeneratedTaskType.FOLLOW_UP,
                "creative": GeneratedTaskType.CREATIVE,
                "learning": GeneratedTaskType.LEARNING,
                "project": GeneratedTaskType.PROJECT,
                "maintenance": GeneratedTaskType.MAINTENANCE,
            }
            task_type = type_map.get(type_str, GeneratedTaskType.FOLLOW_UP)

            # Parse priority
            priority_str = priority_match.group(1).lower() if priority_match else "normal"
            priority_map = {
                "low": TaskPriority.LOW,
                "normal": TaskPriority.NORMAL,
                "high": TaskPriority.HIGH,
            }
            priority = priority_map.get(priority_str, TaskPriority.NORMAL)

            task = GeneratedTask(
                task_id=str(uuid.uuid4()),
                task_type=task_type,
                title=title_match.group(1).strip()[:60],
                description=desc_match.group(1).strip(),
                priority=priority,
            )

            # Check for duplicate
            task_hash = self._hash_task(task.title, task.description)
            if task_hash not in self._generated_task_hashes:
                self._generated_task_hashes.add(task_hash)
                tasks.append(task)

        return tasks

    def submit_task_to_queue(self, task: GeneratedTask) -> bool:
        """
        Submit a generated task to the network task queue.

        Args:
            task: Task to submit

        Returns:
            True if submitted successfully
        """
        if not self.task_queue:
            logger.warning("No task queue available")
            return False

        try:
            from ..network.models import NetworkTask

            network_task = NetworkTask(
                task_id=task.task_id,
                task_type=task.task_type.value,
                payload={
                    "title": task.title,
                    "description": task.description,
                    "source_memory": task.source_memory,
                    "generated_at": task.created_at.isoformat(),
                },
                priority=task.priority.value,
                target_node=task.target_node,
                required_capabilities=task.required_capabilities,
            )

            return self.task_queue.enqueue(network_task)

        except Exception as e:
            logger.error(f"Failed to submit task to queue: {e}")
            return False

    def generate_maintenance_tasks(self) -> list[GeneratedTask]:
        """
        Generate maintenance tasks based on memory state.

        Returns:
            List of maintenance tasks
        """
        tasks = []

        if not self.brain:
            return tasks

        # Check memory stats
        stats = self.brain.get_memory_stats()

        # Task: Archive old memories
        if stats.get("active_memories", 0) > 20:
            tasks.append(GeneratedTask(
                task_id=str(uuid.uuid4()),
                task_type=GeneratedTaskType.MAINTENANCE,
                title="Archive old memories",
                description=f"There are {stats['active_memories']} active memories. Consider archiving older ones.",
                priority=TaskPriority.LOW,
            ))

        # Task: Consolidate archives
        if stats.get("archived_memories", 0) > 100:
            tasks.append(GeneratedTask(
                task_id=str(uuid.uuid4()),
                task_type=GeneratedTaskType.MAINTENANCE,
                title="Consolidate old archives",
                description="Archive has grown large. Consider consolidating old months.",
                priority=TaskPriority.LOW,
            ))

        return tasks

    def get_pending_generated_tasks(self) -> int:
        """Get count of tasks generated this session."""
        return len(self._generated_task_hashes)

    def clear_task_history(self) -> None:
        """Clear the generated task history to allow re-generation."""
        self._generated_task_hashes.clear()
