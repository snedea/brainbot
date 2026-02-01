"""Local task execution with built-in handlers."""

import json
import logging
from pathlib import Path
from typing import Callable, Optional

from .models import CapabilityManifest, HardwareCapability, NetworkTask
from .task_queue import TaskQueue
from .safety import PolicyEnforcer

logger = logging.getLogger(__name__)


# Mapping from task types to required capabilities for policy enforcement
TASK_CAPABILITY_MAP: dict[str, list[HardwareCapability]] = {
    # Display tasks
    "display_text": [HardwareCapability.DISPLAY_1INCH],
    "display_story": [HardwareCapability.DISPLAY_5INCH],
    "display_status": [HardwareCapability.DISPLAY_5INCH],
    # LED tasks
    "led_mood": [HardwareCapability.LED_STRIP],
    "led_pattern": [HardwareCapability.LED_STRIP],
    # Audio output tasks
    "speak": [HardwareCapability.SPEAKER],
    "play_audio": [HardwareCapability.SPEAKER],
    # Camera tasks (sensitive - require explicit permission by default)
    "photo": [HardwareCapability.CAMERA_PI, HardwareCapability.CAMERA_USB],
    "video": [HardwareCapability.CAMERA_PI, HardwareCapability.CAMERA_USB],
    # Microphone tasks (sensitive - require explicit permission by default)
    "transcription": [HardwareCapability.MICROPHONE],
    "record_audio": [HardwareCapability.MICROPHONE],
    "listen": [HardwareCapability.MICROPHONE],
    # GPU tasks
    "generate_image": [
        HardwareCapability.GPU_CUDA,
        HardwareCapability.GPU_ROCM,
        HardwareCapability.GPU_METAL,
    ],
    "process_video": [
        HardwareCapability.GPU_CUDA,
        HardwareCapability.GPU_ROCM,
    ],
}

# Type alias for task handlers
TaskHandler = Callable[[NetworkTask], dict]


class TaskExecutor:
    """
    Executes tasks locally using registered handlers.

    Built-in handlers:
    - display_text: Show text on 1-inch OLED
    - display_story: Show story on 5-inch display
    - display_status: Show status on 5-inch display
    - led_mood: Set LED mood pattern
    - led_pattern: Set LED pattern
    """

    def __init__(
        self,
        queue: TaskQueue,
        manifest: CapabilityManifest,
        config_dir: Optional[Path] = None,
    ):
        """
        Initialize task executor.

        Args:
            queue: Task queue for claiming/completing tasks
            manifest: This node's capability manifest
            config_dir: Path to config directory for policy enforcement
        """
        self.queue = queue
        self.manifest = manifest
        self._handlers: dict[str, TaskHandler] = {}

        # Initialize policy enforcer for safety checks
        if config_dir is None:
            config_dir = Path.home() / ".brainbot" / "config"
        self.policy_enforcer = PolicyEnforcer(config_dir)

        # Register built-in handlers
        self._register_builtin_handlers()

    def _register_builtin_handlers(self) -> None:
        """Register built-in task handlers."""
        self.register_handler("display_text", self._handle_display_text)
        self.register_handler("display_story", self._handle_display_story)
        self.register_handler("display_status", self._handle_display_status)
        self.register_handler("led_mood", self._handle_led_mood)
        self.register_handler("led_pattern", self._handle_led_pattern)
        self.register_handler("speak", self._handle_speak)
        self.register_handler("play_audio", self._handle_play_audio)

    def register_handler(self, task_type: str, handler: TaskHandler) -> None:
        """
        Register a handler for a task type.

        Args:
            task_type: Task type string
            handler: Handler function that takes task and returns result dict
        """
        self._handlers[task_type] = handler
        logger.debug(f"Registered handler for: {task_type}")

    def execute(
        self,
        task: NetworkTask,
        is_explicit_request: bool = False,
    ) -> dict:
        """
        Execute a task using its registered handler.

        Args:
            task: Task to execute
            is_explicit_request: If True, bypass EXPLICIT policy requirement

        Returns:
            Result dict with 'success' and 'data' or 'error'
        """
        handler = self._handlers.get(task.task_type)
        if handler is None:
            return {
                "success": False,
                "error": f"No handler for task type: {task.task_type}",
            }

        # Check safety policies before execution
        policy_result = self._check_task_policy(task, is_explicit_request)
        if not policy_result["allowed"]:
            error_msg = f"Policy denied: {policy_result['reason']}"
            logger.warning(f"Task blocked by policy: {task.task_type} - {policy_result['reason']}")
            self.queue.fail(task.task_id, error_msg)
            return {"success": False, "error": error_msg}

        try:
            logger.info(f"Executing task: {task.task_type} ({task.task_id[:8]})")
            result = handler(task)

            # Mark task as complete
            if result.get("success"):
                self.queue.complete(task.task_id, result.get("data"))
            else:
                self.queue.fail(task.task_id, result.get("error", "Unknown error"))

            return result

        except Exception as e:
            error_msg = f"Handler failed: {e}"
            logger.error(error_msg)
            self.queue.fail(task.task_id, error_msg)
            return {"success": False, "error": error_msg}

    def _check_task_policy(
        self,
        task: NetworkTask,
        is_explicit_request: bool = False,
    ) -> dict:
        """
        Check if task is allowed by safety policies.

        Args:
            task: The task to check
            is_explicit_request: Whether this was explicitly requested by user

        Returns:
            Dict with 'allowed' bool and 'reason' string
        """
        # Get required capabilities for this task type
        required_caps = TASK_CAPABILITY_MAP.get(task.task_type)
        if not required_caps:
            # No capability mapping = no policy restrictions
            return {"allowed": True, "reason": "No capability restrictions"}

        # Determine if this is a network task (not created by local node)
        is_network_task = task.created_by != self.queue.node_id if hasattr(self.queue, 'node_id') else False

        # Check policy for each required capability
        # Task is allowed if at least one capability passes (OR logic for multi-cap tasks)
        for cap in required_caps:
            allowed, reason = self.policy_enforcer.can_use(
                capability=cap,
                task_type=task.task_type,
                is_network_task=is_network_task,
                is_explicit_request=is_explicit_request,
            )
            if allowed:
                return {"allowed": True, "reason": reason}

        # All capabilities denied - return the last denial reason
        return {"allowed": False, "reason": reason}

    def poll_and_execute(self, limit: int = 1) -> int:
        """
        Poll for tasks and execute them.

        Args:
            limit: Maximum tasks to execute

        Returns:
            Number of tasks executed
        """
        # Get claimable tasks
        tasks = self.queue.get_pending_for_node(self.manifest, limit=limit * 2)

        executed = 0
        for task in tasks:
            if executed >= limit:
                break

            # Check if we have a handler
            if task.task_type not in self._handlers:
                continue

            # Try to claim
            claimed = self.queue.claim(task.task_id)
            if claimed:
                self.execute(claimed)
                executed += 1

        return executed

    def get_supported_task_types(self) -> list[str]:
        """Get task types this executor can handle."""
        return list(self._handlers.keys())

    # ============ Built-in Handlers ============

    def _handle_display_text(self, task: NetworkTask) -> dict:
        """Handle display_text task."""
        try:
            from ..hardware.mcp_server import _lcd_1inch_text

            line1 = task.payload.get("line1", "")
            line2 = task.payload.get("line2", "")

            result = _lcd_1inch_text(line1, line2)
            result_data = json.loads(result)

            return {
                "success": result_data.get("success", False),
                "data": result_data,
                "error": result_data.get("error"),
            }
        except ImportError:
            return {"success": False, "error": "LCD 1-inch not available"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _handle_display_story(self, task: NetworkTask) -> dict:
        """Handle display_story task."""
        try:
            from ..hardware.mcp_server import _lcd_5inch_story

            title = task.payload.get("title", "Story")
            text = task.payload.get("text", "")

            result = _lcd_5inch_story(title, text)
            result_data = json.loads(result)

            return {
                "success": result_data.get("success", False),
                "data": result_data,
                "error": result_data.get("error"),
            }
        except ImportError:
            return {"success": False, "error": "LCD 5-inch not available"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _handle_display_status(self, task: NetworkTask) -> dict:
        """Handle display_status task."""
        try:
            from ..hardware.mcp_server import _lcd_5inch_status

            title = task.payload.get("title", "Status")
            status = task.payload.get("status", "")
            progress = task.payload.get("progress", 0.0)

            result = _lcd_5inch_status(title, status, progress)
            result_data = json.loads(result)

            return {
                "success": result_data.get("success", False),
                "data": result_data,
                "error": result_data.get("error"),
            }
        except ImportError:
            return {"success": False, "error": "LCD 5-inch not available"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _handle_led_mood(self, task: NetworkTask) -> dict:
        """Handle led_mood task."""
        try:
            from ..hardware.mcp_server import _led_mood

            mood = task.payload.get("mood", "content")

            result = _led_mood(mood)
            result_data = json.loads(result)

            return {
                "success": result_data.get("success", False),
                "data": result_data,
                "error": result_data.get("error"),
            }
        except ImportError:
            return {"success": False, "error": "LED controller not available"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _handle_led_pattern(self, task: NetworkTask) -> dict:
        """Handle led_pattern task."""
        try:
            from ..hardware.mcp_server import _led_set_pattern

            pattern = task.payload.get("pattern", "solid")
            color = task.payload.get("color", "white")
            speed = task.payload.get("speed", 1.0)

            result = _led_set_pattern(pattern, color, speed)
            result_data = json.loads(result)

            return {
                "success": result_data.get("success", False),
                "data": result_data,
                "error": result_data.get("error"),
            }
        except ImportError:
            return {"success": False, "error": "LED controller not available"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _handle_speak(self, task: NetworkTask) -> dict:
        """Handle speak task (text-to-speech)."""
        try:
            import subprocess
            import shutil

            text = task.payload.get("text", "")
            if not text:
                return {"success": False, "error": "No text to speak"}

            # Try piper first (if available)
            piper = shutil.which("piper")
            if piper:
                # Write text to temp file, pipe to aplay
                result = subprocess.run(
                    f'echo "{text}" | piper --model en_US-lessac-medium --output_raw | aplay -r 22050 -f S16_LE -t raw -',
                    shell=True,
                    capture_output=True,
                    timeout=60,
                )
                if result.returncode == 0:
                    return {"success": True, "data": {"method": "piper"}}

            # Fall back to espeak
            espeak = shutil.which("espeak")
            if espeak:
                result = subprocess.run(
                    ["espeak", text],
                    capture_output=True,
                    timeout=60,
                )
                if result.returncode == 0:
                    return {"success": True, "data": {"method": "espeak"}}

            # Fall back to say (macOS)
            say = shutil.which("say")
            if say:
                result = subprocess.run(
                    ["say", text],
                    capture_output=True,
                    timeout=60,
                )
                if result.returncode == 0:
                    return {"success": True, "data": {"method": "say"}}

            return {"success": False, "error": "No TTS engine available"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _handle_play_audio(self, task: NetworkTask) -> dict:
        """Handle play_audio task."""
        try:
            import subprocess
            import shutil

            file_path = task.payload.get("file")
            if not file_path:
                return {"success": False, "error": "No audio file specified"}

            # Try aplay (Linux/Pi)
            aplay = shutil.which("aplay")
            if aplay:
                result = subprocess.run(
                    ["aplay", file_path],
                    capture_output=True,
                    timeout=300,
                )
                if result.returncode == 0:
                    return {"success": True, "data": {"method": "aplay"}}

            # Try afplay (macOS)
            afplay = shutil.which("afplay")
            if afplay:
                result = subprocess.run(
                    ["afplay", file_path],
                    capture_output=True,
                    timeout=300,
                )
                if result.returncode == 0:
                    return {"success": True, "data": {"method": "afplay"}}

            return {"success": False, "error": "No audio player available"}

        except Exception as e:
            return {"success": False, "error": str(e)}
