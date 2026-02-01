"""LLM-based intent detection for message routing.

Replaces brittle regex keyword matching with semantic understanding.
Uses Claude CLI (rides existing subscription) for intent classification.
"""

import json
import logging
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .models import HardwareCapability

logger = logging.getLogger(__name__)

# Cache for recent intent detections to avoid repeated CLI calls
_intent_cache: dict[str, tuple[float, "DetectedIntent"]] = {}
_CACHE_TTL_SECONDS = 300  # 5 minutes


class IntentType(str, Enum):
    """High-level intent categories."""

    # Hardware commands
    DISPLAY_CONTENT = "display_content"  # Show something on a display
    CAPTURE_IMAGE = "capture_image"  # Take a photo/video
    CONTROL_LIGHTING = "control_lighting"  # LED/light control
    CONTROL_AUDIO = "control_audio"  # Play sound, speak, listen
    CONTROL_HARDWARE = "control_hardware"  # Fan, sensors, etc.

    # AI/Compute tasks
    GENERATE_IMAGE = "generate_image"  # AI image generation
    GENERATE_TEXT = "generate_text"  # AI text generation
    ANALYZE_IMAGE = "analyze_image"  # Vision/image analysis

    # Conversational
    CONVERSATION = "conversation"  # General chat, questions
    QUESTION_ABOUT_SYSTEM = "question_about_system"  # Questions about capabilities

    # Meta
    DELEGATE_TO_NODE = "delegate_to_node"  # Explicit node targeting
    UNKNOWN = "unknown"


@dataclass
class DetectedIntent:
    """Result of intent detection."""

    intent_type: IntentType
    confidence: float  # 0.0 to 1.0

    # What hardware capabilities are needed (if any)
    required_capabilities: list[HardwareCapability] = field(default_factory=list)
    preferred_capabilities: list[HardwareCapability] = field(default_factory=list)

    # Extracted parameters
    target_node_name: Optional[str] = None  # If explicitly targeting a node
    action_verb: Optional[str] = None  # The main action (show, take, turn on, etc.)
    subject: Optional[str] = None  # What to act on (picture, LEDs, story, etc.)
    parameters: dict = field(default_factory=dict)  # Additional extracted params

    # For display tasks
    content_to_display: Optional[str] = None

    # Reasoning (for debugging)
    reasoning: str = ""

    @property
    def is_hardware_command(self) -> bool:
        """Check if this intent requires hardware."""
        return self.intent_type in {
            IntentType.DISPLAY_CONTENT,
            IntentType.CAPTURE_IMAGE,
            IntentType.CONTROL_LIGHTING,
            IntentType.CONTROL_AUDIO,
            IntentType.CONTROL_HARDWARE,
        }

    @property
    def is_conversational(self) -> bool:
        """Check if this is just conversation."""
        return self.intent_type in {
            IntentType.CONVERSATION,
            IntentType.QUESTION_ABOUT_SYSTEM,
        }


# System prompt for intent detection
INTENT_DETECTION_PROMPT = """You are an intent classifier for a smart home AI system called BrainBot.
BrainBot runs on multiple nodes (Raspberry Pis, Macs, servers) with different hardware capabilities.

Analyze the user's message and determine their intent. Respond with JSON only.

Available hardware capabilities:
- display_5inch: 5-inch LCD screen for showing images, stories, status
- display_1inch: Small OLED status display
- camera_pi: Raspberry Pi camera module
- camera_usb: USB webcam
- led_strip: NeoPixel/RGB LED strip for mood lighting
- speaker: Audio output for text-to-speech
- microphone: Audio input for voice commands
- fan_pwm: Cooling fan control
- gpu_cuda/gpu_metal/gpu_rocm: GPU compute capabilities

Intent types:
- display_content: Show/display something on a screen
- capture_image: Take a photo or video with a camera
- control_lighting: Control LEDs or lights
- control_audio: Play sound, speak, or listen
- control_hardware: Control fan, read sensors
- generate_image: Create/generate/draw an image using AI
- generate_text: Generate text/stories using AI
- analyze_image: Analyze or describe an image
- conversation: General chat or questions
- question_about_system: Questions about what BrainBot can do
- delegate_to_node: Explicitly targeting a specific node by name
- unknown: Cannot determine intent

Respond with this JSON structure:
{
  "intent_type": "one of the types above",
  "confidence": 0.0-1.0,
  "required_capabilities": ["list of required hardware capabilities"],
  "preferred_capabilities": ["nice-to-have capabilities"],
  "target_node_name": "node name if explicitly mentioned, null otherwise",
  "action_verb": "the main action verb",
  "subject": "what the action is about",
  "parameters": {},
  "reasoning": "brief explanation of classification"
}

Examples:
- "Take a picture of the room" -> capture_image, requires camera_pi or camera_usb
- "Show a picture on the display" -> display_content, requires display_5inch
- "Draw me a picture of a sunset" -> generate_image (AI generation, no camera needed), then optionally display_content
- "Turn on the LEDs" -> control_lighting, requires led_strip
- "What can you do?" -> question_about_system, no hardware needed
- "Echo, show me the status" -> delegate_to_node targeting "Echo", then display_content
- "How does it feel having two bodies?" -> conversation, no hardware needed"""


class IntentDetector:
    """
    Detects user intent using Claude CLI.

    Uses the existing Claude subscription via CLI - no API keys needed.
    Includes caching to avoid repeated calls for similar messages.
    """

    def __init__(self, cache_ttl: int = 300):
        """
        Initialize intent detector.

        Args:
            cache_ttl: Cache time-to-live in seconds (default 5 minutes)
        """
        self.cache_ttl = cache_ttl

    def detect(self, message: str, available_nodes: list[dict] = None) -> DetectedIntent:
        """
        Detect intent from a user message.

        Args:
            message: The user's message
            available_nodes: Optional list of available nodes for context

        Returns:
            DetectedIntent with classification results
        """
        import time

        # Check cache first
        cache_key = message.lower().strip()
        if cache_key in _intent_cache:
            cached_time, cached_intent = _intent_cache[cache_key]
            if time.time() - cached_time < self.cache_ttl:
                logger.debug(f"Intent cache hit for: {message[:30]}...")
                return cached_intent

        # Build the prompt
        prompt = self._build_prompt(message, available_nodes)

        # Get Claude CLI response
        try:
            response = self._call_claude_cli(prompt)

            if response:
                intent = self._parse_response(response, message)
            else:
                intent = self._fallback_detection(message)

            # Cache the result
            _intent_cache[cache_key] = (time.time(), intent)

            # Prune old cache entries
            self._prune_cache()

            return intent

        except Exception as e:
            logger.warning(f"Intent detection failed: {e}, falling back to heuristics")
            return self._fallback_detection(message)

    def _build_prompt(self, message: str, available_nodes: list[dict] = None) -> str:
        """Build the full prompt for intent detection."""
        prompt = INTENT_DETECTION_PROMPT

        if available_nodes:
            node_info = "\n\nAvailable nodes in the network:\n"
            for node in available_nodes:
                node_info += f"- {node.get('name', 'Unknown')}: {', '.join(node.get('capabilities', []))}\n"
            prompt += node_info

        prompt += f"\n\nUser message: {message}\n\nRespond with JSON only:"
        return prompt

    def _call_claude_cli(self, prompt: str) -> str:
        """Call Claude via CLI (uses existing subscription)."""
        try:
            result = subprocess.run(
                ["claude", "-p", prompt, "--output-format", "text"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return result.stdout.strip()
            else:
                logger.warning(f"Claude CLI failed: {result.stderr}")
                return ""
        except FileNotFoundError:
            logger.warning("Claude CLI not found - install with: npm install -g @anthropic-ai/claude-code")
            return ""
        except subprocess.TimeoutExpired:
            logger.warning("Claude CLI timed out")
            return ""

    def _prune_cache(self) -> None:
        """Remove expired cache entries."""
        import time
        now = time.time()
        expired = [k for k, (t, _) in _intent_cache.items() if now - t > self.cache_ttl]
        for k in expired:
            del _intent_cache[k]

    def _parse_response(self, response: str, original_message: str) -> DetectedIntent:
        """Parse LLM response into DetectedIntent."""
        # Try to extract JSON from response
        try:
            # Handle markdown code blocks
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                response = response.split("```")[1].split("```")[0]

            # Find JSON object
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = response[start:end]
                data = json.loads(json_str)
            else:
                raise ValueError("No JSON found in response")

            # Map string to enum
            intent_type_str = data.get("intent_type", "unknown")
            try:
                intent_type = IntentType(intent_type_str)
            except ValueError:
                intent_type = IntentType.UNKNOWN

            # Map capability strings to enums
            required_caps = []
            for cap_str in data.get("required_capabilities", []):
                try:
                    required_caps.append(HardwareCapability(cap_str))
                except ValueError:
                    logger.debug(f"Unknown capability: {cap_str}")

            preferred_caps = []
            for cap_str in data.get("preferred_capabilities", []):
                try:
                    preferred_caps.append(HardwareCapability(cap_str))
                except ValueError:
                    pass

            return DetectedIntent(
                intent_type=intent_type,
                confidence=float(data.get("confidence", 0.5)),
                required_capabilities=required_caps,
                preferred_capabilities=preferred_caps,
                target_node_name=data.get("target_node_name"),
                action_verb=data.get("action_verb"),
                subject=data.get("subject"),
                parameters=data.get("parameters", {}),
                reasoning=data.get("reasoning", ""),
            )

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.warning(f"Failed to parse intent response: {e}")
            return self._fallback_detection(original_message)

    def _fallback_detection(self, message: str) -> DetectedIntent:
        """Simple heuristic fallback when LLM fails."""
        message_lower = message.lower()

        # Check for explicit node targeting
        # Pattern: "NodeName, do something" or "@NodeName"
        import re
        node_match = re.match(r"^@?(\w+)[,:]?\s+", message)
        target_node = node_match.group(1) if node_match else None

        # Simple keyword-based detection
        if any(word in message_lower for word in ["take a photo", "take a picture", "capture", "snapshot"]):
            return DetectedIntent(
                intent_type=IntentType.CAPTURE_IMAGE,
                confidence=0.7,
                required_capabilities=[HardwareCapability.CAMERA_PI],
                action_verb="capture",
                subject="image",
                reasoning="Fallback: detected capture keywords",
            )

        if any(word in message_lower for word in ["draw", "generate", "create"]) and "picture" in message_lower:
            return DetectedIntent(
                intent_type=IntentType.GENERATE_IMAGE,
                confidence=0.7,
                preferred_capabilities=[HardwareCapability.GPU_CUDA, HardwareCapability.GPU_METAL],
                action_verb="generate",
                subject="image",
                reasoning="Fallback: detected generation keywords",
            )

        if any(word in message_lower for word in ["show", "display"]):
            return DetectedIntent(
                intent_type=IntentType.DISPLAY_CONTENT,
                confidence=0.7,
                required_capabilities=[HardwareCapability.DISPLAY_5INCH],
                action_verb="display",
                subject="content",
                reasoning="Fallback: detected display keywords",
            )

        if any(word in message_lower for word in ["led", "light", "glow", "mood"]):
            return DetectedIntent(
                intent_type=IntentType.CONTROL_LIGHTING,
                confidence=0.7,
                required_capabilities=[HardwareCapability.LED_STRIP],
                action_verb="control",
                subject="lighting",
                reasoning="Fallback: detected lighting keywords",
            )

        # Default to conversation
        return DetectedIntent(
            intent_type=IntentType.CONVERSATION,
            confidence=0.5,
            target_node_name=target_node,
            reasoning="Fallback: no specific intent detected",
        )


def detect_intent(
    message: str,
    available_nodes: list[dict] = None,
) -> DetectedIntent:
    """
    Convenience function to detect intent.

    Uses Claude CLI (existing subscription) for intent detection.

    Args:
        message: User message to analyze
        available_nodes: Optional list of available nodes

    Returns:
        DetectedIntent with classification
    """
    detector = IntentDetector()
    return detector.detect(message, available_nodes)
