"""
AI-powered hardware command detection and execution for BrainBot.

Uses Claude to understand natural language commands and execute
corresponding hardware actions (display, LED, etc).

No brittle regex - just semantic understanding.
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Optional, Callable

logger = logging.getLogger(__name__)


@dataclass
class HardwareCommand:
    """Detected hardware command."""
    command_type: str  # display, led, speak, etc.
    action: str  # show_message, show_banner, set_mood, etc.
    parameters: dict  # message, color, duration, etc.
    confidence: float  # 0.0 to 1.0


class HardwareCommandHandler:
    """
    Handles hardware commands using AI intent detection.

    When a message comes in, uses Claude to determine if it's
    a hardware command, then executes the appropriate action.
    """

    DETECTION_PROMPT = '''Analyze this message and determine if the user is asking for a hardware action.

Hardware actions include:
- DISPLAY: Show something on the LCD screen (message, banner, image, status)
- LED: Control the LED lights (color, mood, pattern)
- SPEAK: Text-to-speech output
- CLEAR: Clear/turn off displays or LEDs

Message: "{message}"

Respond with a JSON object:
{{
  "is_hardware_command": true/false,
  "command_type": "display" | "led" | "speak" | "clear" | null,
  "action": "show_message" | "show_banner" | "show_status" | "set_color" | "set_mood" | "say" | "clear_display" | "clear_led" | null,
  "parameters": {{
    "message": "text to display if applicable",
    "title": "optional title",
    "color": "color name if applicable",
    "mood": "mood name if applicable",
    "duration": seconds as number
  }},
  "confidence": 0.0-1.0
}}

Only set is_hardware_command=true if the user clearly wants hardware action.
If they're just chatting about displays/LEDs without wanting action, set false.'''

    def __init__(self, delegator=None):
        """
        Initialize the command handler.

        Args:
            delegator: ClaudeDelegator for AI detection
        """
        self.delegator = delegator

        # Hardware action executors
        self._executors: dict[str, Callable] = {}

    def register_executor(self, action: str, executor: Callable) -> None:
        """Register an executor function for an action."""
        self._executors[action] = executor

    def detect_command(self, message: str) -> Optional[HardwareCommand]:
        """
        Use AI to detect if message is a hardware command.

        Args:
            message: User message

        Returns:
            HardwareCommand if detected, None otherwise
        """
        if not self.delegator:
            return None

        if not self.delegator.check_claude_available():
            logger.warning("Claude not available for command detection")
            return None

        prompt = self.DETECTION_PROMPT.format(message=message)

        # Use quick_query for fast, non-agentic detection (30 second timeout)
        result = self.delegator.quick_query(prompt, timeout_seconds=30)

        if not result.success:
            logger.warning(f"Command detection failed: {result.error}")
            return None

        try:
            # Extract JSON from response
            response = result.output.strip()

            # Find JSON in response (might have explanation text around it)
            json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
            if not json_match:
                # Try to find a larger JSON block
                json_match = re.search(r'\{.*\}', response, re.DOTALL)

            if not json_match:
                logger.debug(f"No JSON found in response: {response[:200]}")
                return None

            data = json.loads(json_match.group())

            if not data.get("is_hardware_command"):
                return None

            return HardwareCommand(
                command_type=data.get("command_type", ""),
                action=data.get("action", ""),
                parameters=data.get("parameters", {}),
                confidence=data.get("confidence", 0.5),
            )

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse command detection response: {e}")
            return None
        except Exception as e:
            logger.error(f"Command detection error: {e}")
            return None

    def execute(self, command: HardwareCommand) -> tuple[bool, str]:
        """
        Execute a hardware command.

        Args:
            command: The command to execute

        Returns:
            (success, message) tuple
        """
        action = command.action
        params = command.parameters

        if action in self._executors:
            try:
                result = self._executors[action](**params)
                return True, f"Done! {action} executed."
            except Exception as e:
                logger.error(f"Failed to execute {action}: {e}")
                return False, f"Failed to execute: {e}"
        else:
            # Try default executors
            return self._execute_default(command)

    def _execute_default(self, command: HardwareCommand) -> tuple[bool, str]:
        """Execute using default hardware modules."""
        action = command.action
        params = command.parameters

        try:
            if action == "show_message":
                from ..hardware.display_manager import show_message
                message = params.get("message", "Hello!")
                title = params.get("title", "BrainBot")
                duration = params.get("duration", 15)
                show_message(message, title=title, duration=duration)
                return True, f"Displayed message on LCD: {message[:50]}..."

            elif action == "show_banner":
                from ..hardware.display_loop import get_display_loop
                loop = get_display_loop()
                if loop:
                    loop._show_banner()
                    return True, "Showing the BrainBot banner!"
                return False, "Display loop not available"

            elif action == "show_status":
                from ..hardware.display_manager import show_status
                status = params.get("message", "Ready")
                mood = params.get("mood", "content")
                duration = params.get("duration", 15)
                show_status(status, mood=mood, duration=duration)
                return True, f"Showing status: {status}"

            elif action == "set_mood" or action == "set_color":
                from ..hardware.expansion_leds import get_leds
                leds = get_leds()
                if leds:
                    mood = params.get("mood") or params.get("color", "idle")
                    leds.set_mood(mood)
                    return True, f"LED mood set to: {mood}"
                return False, "LEDs not available"

            elif action == "clear_display":
                from ..hardware.display_manager import close_display
                close_display()
                return True, "Display cleared"

            elif action == "clear_led":
                from ..hardware.expansion_leds import get_leds
                leds = get_leds()
                if leds:
                    leds.off()
                    return True, "LEDs turned off"
                return False, "LEDs not available"

            elif action == "say":
                # TTS would be handled elsewhere
                return False, "TTS not implemented in command handler"

            else:
                return False, f"Unknown action: {action}"

        except ImportError as e:
            logger.error(f"Hardware module not available: {e}")
            return False, f"Hardware not available: {e}"
        except Exception as e:
            logger.error(f"Hardware command failed: {e}")
            return False, f"Command failed: {e}"

    def process_message(self, message: str) -> Optional[tuple[bool, str]]:
        """
        Process a message - detect and execute if it's a hardware command.

        Args:
            message: User message

        Returns:
            (success, response) if hardware command, None if not a command
        """
        command = self.detect_command(message)

        if not command:
            return None

        if command.confidence < 0.6:
            logger.debug(f"Low confidence command ignored: {command}")
            return None

        logger.info(f"Executing hardware command: {command.action} ({command.command_type})")
        return self.execute(command)


# Singleton
_handler: Optional[HardwareCommandHandler] = None


def get_hardware_handler(delegator=None) -> HardwareCommandHandler:
    """Get or create the hardware command handler."""
    global _handler
    if _handler is None:
        _handler = HardwareCommandHandler(delegator)
    elif delegator and _handler.delegator is None:
        _handler.delegator = delegator
    return _handler
