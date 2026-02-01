"""Smart message routing for multi-node BrainBot network.

Routes messages to the appropriate node based on:
1. Explicit node name in message ("Echo, turn on the LEDs")
2. Capability requirements ("turn on the LEDs" -> needs LED_STRIP)
3. Default to local node for general chat
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

from .models import HardwareCapability, NetworkTask
from .registry import NodeRegistry

if TYPE_CHECKING:
    from .task_router import TaskRouter, TaskSubmitter

logger = logging.getLogger(__name__)


# Keywords that map to capabilities
CAPABILITY_KEYWORDS = {
    # LED-related
    HardwareCapability.LED_STRIP: [
        r"\bled\b", r"\bleds\b", r"\blight\b", r"\blights\b",
        r"\bneopixel\b", r"\brgb\b", r"\bmood\s*light",
        r"\bambient\b", r"\bglow\b",
    ],

    # Display-related
    HardwareCapability.DISPLAY_5INCH: [
        r"\bdisplay\b", r"\bscreen\b", r"\bshow\b.*\b(image|picture|story|status)\b",
        r"\b5\s*inch\b", r"\blcd\b", r"\bmonitor\b",
    ],
    HardwareCapability.DISPLAY_1INCH: [
        r"\boled\b", r"\b1\s*inch\b", r"\bsmall\s*display\b",
        r"\bstatus\s*display\b",
    ],

    # Audio-related
    HardwareCapability.SPEAKER: [
        r"\bspeak\b", r"\bsay\b", r"\btalk\b", r"\bvoice\b",
        r"\baudio\b", r"\bsound\b", r"\bplay\b.*\b(sound|audio)\b",
        r"\bread\s*aloud\b", r"\btts\b", r"\btext.to.speech\b",
    ],
    HardwareCapability.MICROPHONE: [
        r"\blisten\b", r"\bhear\b", r"\brecord\b.*\b(audio|voice)\b",
        r"\bmicrophone\b", r"\bmic\b", r"\bstt\b", r"\bspeech.to.text\b",
    ],

    # Camera-related
    HardwareCapability.CAMERA_PI: [
        r"\bcamera\b", r"\bphoto\b", r"\bpicture\b", r"\bsnapshot\b",
        r"\bcapture\b", r"\bsee\b", r"\blook\b", r"\bwatch\b",
    ],
    HardwareCapability.CAMERA_USB: [
        r"\bwebcam\b", r"\busb\s*camera\b",
    ],

    # Fan control
    HardwareCapability.FAN_PWM: [
        r"\bfan\b", r"\bcooling\b", r"\btemperature\b",
    ],

    # GPU/Compute
    HardwareCapability.GPU_CUDA: [
        r"\bcuda\b", r"\bnvidia\b", r"\bgpu\b.*\b(compute|render)\b",
    ],
    HardwareCapability.GPU_METAL: [
        r"\bmetal\b", r"\bapple\s*gpu\b",
    ],
    HardwareCapability.GPU_ROCM: [
        r"\brocm\b", r"\bamd\s*gpu\b",
    ],
}

# Device type keywords (for general references)
DEVICE_KEYWORDS = {
    "raspberry_pi": [
        r"\braspberry\s*pi\b", r"\bpi\b", r"\brpi\b", r"\braspi\b",
    ],
    "mac": [
        r"\bmac\b", r"\bmacbook\b", r"\bimac\b", r"\bmac\s*mini\b",
    ],
    "server": [
        r"\bserver\b", r"\bheadless\b",
    ],
}

# Action verbs that indicate a command (not just a mention)
# Only route to capability nodes when these action patterns are present
# Note: Avoid words that are both nouns and verbs (like "display", "light")
ACTION_PATTERNS = [
    # Imperatives / commands (clear verbs only)
    r"\b(turn|switch|set|make|get|show|take|capture|snap|record)\b",
    r"\b(start|stop|enable|disable|activate|deactivate)\b",
    r"\b(play|pause|say|speak|read aloud|announce)\b",
    r"\b(check|measure|sense|detect|monitor)\b",
    # "display" as a verb (followed by object)
    r"\bdisplay\s+(this|the|a|my|some|that)\b",
    # Requests
    r"\b(can you|could you|please|would you)\b.*\b(turn|show|take|play|set)\b",
    r"\b(i want|i need|i'd like)\b.*\b(to see|to hear|a photo|a picture)\b",
    # Questions that imply action
    r"\bwhat('s| is) the (temperature|status|reading)\b",
    r"\bhow (hot|cold|bright|loud)\b",
]

# Phrases that indicate conversation ABOUT capabilities, not commands
CONVERSATIONAL_PATTERNS = [
    r"\b(has|have|got)\s+(a|an|the)\s+\w*\b",  # "has a camera", "have the display"
    r"\b(it|that|this|which)\s+is\s+(a|an)\b",  # "it is a Raspberry Pi" (not "what is the")
    r"\bhow does it feel\b",
    r"\bwhat do you think\b",
    r"\btell me about\b",
    r"\bdo you (like|enjoy|feel)\b",
    r"\b(feels?|think|believe|wonder)\b.*\b(about|that)\b",
    r"\b(two|multiple|both|several)\s+(nodes?|bodies|instances)\b",
    r"\bi love the\b",  # "I love the camera"
    r"\bthe \w+ is (nice|great|cool|awesome)\b",  # "the display is nice"
]


@dataclass
class RoutingDecision:
    """Result of message routing analysis."""

    # Where to route
    target_node_id: Optional[str] = None
    target_node_name: Optional[str] = None
    route_type: str = "local"  # "local", "explicit", "capability", "broadcast"

    # What capabilities are needed
    required_capabilities: list[HardwareCapability] = None

    # Task to create (if routing remotely)
    task_type: Optional[str] = None
    task_payload: Optional[dict] = None

    # Original message (cleaned of routing info)
    cleaned_message: str = ""

    # For errors/info
    message: str = ""

    def __post_init__(self):
        if self.required_capabilities is None:
            self.required_capabilities = []


class MessageRouter:
    """
    Analyzes messages and decides where to route them.

    Priority:
    1. Explicit node name -> route to that node
    2. Capability keywords -> route to capable node
    3. No special routing -> handle locally
    """

    def __init__(
        self,
        registry: NodeRegistry,
        local_node_id: str,
        local_persona_name: str,
    ):
        """
        Initialize message router.

        Args:
            registry: Node registry for looking up nodes
            local_node_id: This node's ID
            local_persona_name: This node's persona name (e.g., "Creative Unit")
        """
        self.registry = registry
        self.local_node_id = local_node_id
        self.local_persona_name = local_persona_name

        # Build node name lookup (cached, refreshed periodically)
        self._node_name_cache: dict[str, str] = {}  # name -> node_id
        self._cache_refresh_count = 0

    def route(self, message: str) -> RoutingDecision:
        """
        Analyze a message and decide where to route it.

        Args:
            message: The user's message

        Returns:
            RoutingDecision with routing info
        """
        # Refresh node cache periodically
        self._maybe_refresh_cache()

        # Step 1: Check for explicit node name
        explicit_result = self._check_explicit_node(message)
        if explicit_result:
            return explicit_result

        # Step 2: Check for capability keywords
        capability_result = self._check_capability_keywords(message)
        if capability_result:
            return capability_result

        # Step 3: Default to local handling
        return RoutingDecision(
            target_node_id=self.local_node_id,
            target_node_name=self.local_persona_name,
            route_type="local",
            cleaned_message=message,
            message="Handling locally",
        )

    def _check_explicit_node(self, message: str) -> Optional[RoutingDecision]:
        """Check if message explicitly mentions a node name."""
        message_lower = message.lower()

        # Check against known node names
        for name, node_id in self._node_name_cache.items():
            name_lower = name.lower()

            # Check for patterns like:
            # "Echo, do something"
            # "tell Echo to do something"
            # "on Echo, do something"
            # "ask Echo to do something"
            patterns = [
                rf"\b{re.escape(name_lower)}\s*[,:]",  # "Echo, ..."
                rf"\btell\s+{re.escape(name_lower)}\s+to\b",  # "tell Echo to"
                rf"\bask\s+{re.escape(name_lower)}\s+to\b",  # "ask Echo to"
                rf"\bon\s+{re.escape(name_lower)}\b",  # "on Echo"
                rf"\b{re.escape(name_lower)}\s+node\b",  # "Echo node"
                rf"@{re.escape(name_lower)}\b",  # "@Echo"
            ]

            for pattern in patterns:
                if re.search(pattern, message_lower):
                    # Remove the node reference from the message
                    cleaned = re.sub(pattern, "", message, flags=re.IGNORECASE).strip()
                    cleaned = re.sub(r"^\s*[,:\-]\s*", "", cleaned)  # Clean up punctuation

                    # Skip if targeting self
                    if node_id == self.local_node_id:
                        return RoutingDecision(
                            target_node_id=self.local_node_id,
                            target_node_name=self.local_persona_name,
                            route_type="local",
                            cleaned_message=cleaned or message,
                            message=f"Targeting self ({name}), handling locally",
                        )

                    return RoutingDecision(
                        target_node_id=node_id,
                        target_node_name=name,
                        route_type="explicit",
                        cleaned_message=cleaned or message,
                        task_type="delegate_chat",
                        task_payload={"message": cleaned or message},
                        message=f"Routing to {name} (explicit)",
                    )

        return None

    def _check_capability_keywords(self, message: str) -> Optional[RoutingDecision]:
        """Check if message requires specific capabilities."""
        message_lower = message.lower()

        # First, check if this is conversational (talking ABOUT capabilities)
        # rather than a command (asking TO USE capabilities)
        is_conversational = any(
            re.search(pattern, message_lower)
            for pattern in CONVERSATIONAL_PATTERNS
        )

        # Check for action verbs that indicate a command
        has_action = any(
            re.search(pattern, message_lower)
            for pattern in ACTION_PATTERNS
        )

        # If it looks conversational and has no clear action verb, don't route
        if is_conversational and not has_action:
            logger.debug(f"Message appears conversational, not routing: {message[:50]}...")
            return None

        required_caps = []

        for capability, patterns in CAPABILITY_KEYWORDS.items():
            for pattern in patterns:
                if re.search(pattern, message_lower):
                    required_caps.append(capability)
                    break  # Only add each capability once

        if not required_caps:
            return None

        # Even with capability keywords, require action intent for remote routing
        if not has_action:
            logger.debug(f"Capability keywords found but no action intent: {message[:50]}...")
            return None

        # Check if local node has these capabilities
        local_entry = self.registry.get_node(self.local_node_id)
        if local_entry:
            local_caps = set(local_entry.capabilities)
            required_cap_values = {c.value for c in required_caps}

            if required_cap_values.issubset(local_caps):
                # We can handle it locally
                return RoutingDecision(
                    target_node_id=self.local_node_id,
                    target_node_name=self.local_persona_name,
                    route_type="local",
                    required_capabilities=required_caps,
                    cleaned_message=message,
                    message=f"Local node has required capabilities: {required_cap_values}",
                )

        # Find a node with these capabilities
        capable_nodes = self.registry.find_nodes_with_capabilities(
            required_caps,
            require_all=True,
            only_online=True,
        )

        if not capable_nodes:
            # No node can handle this
            cap_names = [c.value for c in required_caps]
            return RoutingDecision(
                route_type="error",
                required_capabilities=required_caps,
                cleaned_message=message,
                message=f"No online nodes have required capabilities: {cap_names}",
            )

        # Pick the best one (first match for now, could add scoring)
        target = capable_nodes[0]
        target_name = target.persona.display_name if target.persona else target.node_id[:8]

        return RoutingDecision(
            target_node_id=target.node_id,
            target_node_name=target_name,
            route_type="capability",
            required_capabilities=required_caps,
            cleaned_message=message,
            task_type="delegate_chat",
            task_payload={"message": message},
            message=f"Routing to {target_name} (has {[c.value for c in required_caps]})",
        )

    def _maybe_refresh_cache(self) -> None:
        """Refresh node name cache periodically."""
        self._cache_refresh_count += 1

        # Refresh every 10 calls or if empty
        if self._cache_refresh_count >= 10 or not self._node_name_cache:
            self._refresh_node_cache()
            self._cache_refresh_count = 0

    def _refresh_node_cache(self) -> None:
        """Refresh the node name -> ID cache."""
        self._node_name_cache.clear()

        try:
            nodes = self.registry.get_all_nodes()
            for node in nodes:
                if node.persona and node.persona.display_name:
                    name = node.persona.display_name
                    self._node_name_cache[name] = node.node_id

                    # Also add without spaces for easier matching
                    name_no_spaces = name.replace(" ", "")
                    if name_no_spaces != name:
                        self._node_name_cache[name_no_spaces] = node.node_id

                # Also index by hostname
                if node.hostname:
                    self._node_name_cache[node.hostname] = node.node_id

            logger.debug(f"Refreshed node cache: {list(self._node_name_cache.keys())}")

        except Exception as e:
            logger.warning(f"Failed to refresh node cache: {e}")

    def get_known_nodes(self) -> dict[str, str]:
        """Get dict of known node names -> IDs."""
        self._maybe_refresh_cache()
        return dict(self._node_name_cache)


def extract_task_from_message(
    message: str,
    required_capabilities: list[HardwareCapability],
) -> tuple[str, dict]:
    """
    Extract a task type and payload from a message.

    Args:
        message: The user's message
        required_capabilities: Capabilities needed

    Returns:
        Tuple of (task_type, payload)
    """
    message_lower = message.lower()

    # LED tasks
    if HardwareCapability.LED_STRIP in required_capabilities:
        if any(word in message_lower for word in ["on", "enable", "start", "activate"]):
            return "led_on", {"message": message}
        elif any(word in message_lower for word in ["off", "disable", "stop", "deactivate"]):
            return "led_off", {"message": message}
        elif "mood" in message_lower or "color" in message_lower:
            # Try to extract mood/color
            moods = ["happy", "sad", "excited", "calm", "focused", "tired", "curious"]
            for mood in moods:
                if mood in message_lower:
                    return "led_mood", {"mood": mood, "message": message}
            return "led_mood", {"mood": "content", "message": message}
        else:
            return "led_pattern", {"message": message}

    # Display tasks
    if HardwareCapability.DISPLAY_5INCH in required_capabilities:
        if "story" in message_lower:
            return "display_story", {"message": message}
        elif "status" in message_lower:
            return "display_status", {"message": message}
        else:
            return "display_text", {"message": message}

    if HardwareCapability.DISPLAY_1INCH in required_capabilities:
        return "display_status", {"message": message}

    # Audio tasks
    if HardwareCapability.SPEAKER in required_capabilities:
        return "speak", {"text": message}

    if HardwareCapability.MICROPHONE in required_capabilities:
        return "listen", {"message": message}

    # Camera tasks
    if any(cap in required_capabilities for cap in [
        HardwareCapability.CAMERA_PI,
        HardwareCapability.CAMERA_USB,
    ]):
        return "photo", {"message": message}

    # Default
    return "delegate_chat", {"message": message}
