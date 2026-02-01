"""Persona generation based on hardware capabilities."""

import json
import logging
import random
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import (
    CapabilityManifest,
    HardwareCapability,
    NodePersona,
)

logger = logging.getLogger(__name__)

# Role definitions based on primary capability
ROLE_DEFINITIONS = {
    HardwareCapability.GPU_CUDA: {
        "role": "compute",
        "traits": ["powerful", "creative", "fast"],
        "preferred_tasks": ["generate_image", "train_model", "process_video", "render"],
        "name_prefixes": ["GPU", "Compute", "Render", "Studio"],
    },
    HardwareCapability.GPU_ROCM: {
        "role": "compute",
        "traits": ["powerful", "creative", "fast"],
        "preferred_tasks": ["generate_image", "train_model", "process_video"],
        "name_prefixes": ["AMD", "Compute", "Worker"],
    },
    HardwareCapability.GPU_METAL: {
        "role": "compute",
        "traits": ["efficient", "creative", "integrated"],
        "preferred_tasks": ["generate_image", "process_video", "render"],
        "name_prefixes": ["Mac", "Studio", "Creative"],
    },
    HardwareCapability.DISPLAY_5INCH: {
        "role": "display",
        "traits": ["visual", "storyteller", "expressive"],
        "preferred_tasks": ["display_story", "display_status", "show_art"],
        "name_prefixes": ["Display", "Story", "Visual"],
    },
    HardwareCapability.DISPLAY_1INCH: {
        "role": "status",
        "traits": ["informative", "compact", "always-on"],
        "preferred_tasks": ["display_text", "show_status", "notification"],
        "name_prefixes": ["Status", "Mini", "Dash"],
    },
    HardwareCapability.CAMERA_PI: {
        "role": "observer",
        "traits": ["watchful", "curious", "visual"],
        "preferred_tasks": ["photo", "timelapse", "observe"],
        "name_prefixes": ["Eye", "Watch", "Observer"],
    },
    HardwareCapability.CAMERA_USB: {
        "role": "observer",
        "traits": ["watchful", "curious", "visual"],
        "preferred_tasks": ["photo", "video_call", "observe"],
        "name_prefixes": ["Cam", "Eye", "View"],
    },
    HardwareCapability.LED_STRIP: {
        "role": "ambient",
        "traits": ["colorful", "moody", "expressive"],
        "preferred_tasks": ["led_mood", "led_pattern", "ambient_light"],
        "name_prefixes": ["Glow", "Light", "Ambient"],
    },
    HardwareCapability.MICROPHONE: {
        "role": "listener",
        "traits": ["attentive", "responsive", "voice-aware"],
        "preferred_tasks": ["voice_command", "transcription", "listen"],
        "name_prefixes": ["Ear", "Listen", "Voice"],
    },
    HardwareCapability.SPEAKER: {
        "role": "voice",
        "traits": ["vocal", "communicative", "expressive"],
        "preferred_tasks": ["speak", "play_audio", "notify"],
        "name_prefixes": ["Voice", "Speaker", "Audio"],
    },
}

# Location-based name suffixes (can be overridden by user)
LOCATION_SUFFIXES = [
    "Bot", "Node", "Unit", "Hub", "Station",
]

# Fallback for nodes without distinctive capabilities
FALLBACK_DEFINITION = {
    "role": "general",
    "traits": ["versatile", "helpful", "reliable"],
    "preferred_tasks": ["delegate_to_claude", "memory_sync", "coordination"],
    "name_prefixes": ["Brain", "Core", "Node"],
}


class PersonaGenerator:
    """
    Generates node persona based on hardware capabilities.

    The persona includes:
    - Auto-generated name based on primary capability
    - Role (compute, display, observer, etc.)
    - Personality traits
    - Preferred task types
    """

    def __init__(self, config_dir: Path):
        """
        Initialize persona generator.

        Args:
            config_dir: Path to config directory for storing persona
        """
        self.config_dir = config_dir
        self.persona_file = config_dir / "persona.json"

    def generate(
        self,
        manifest: CapabilityManifest,
        hostname: str,
        force_regenerate: bool = False,
    ) -> NodePersona:
        """
        Generate or load persona for this node.

        Args:
            manifest: Hardware capability manifest
            hostname: Node hostname
            force_regenerate: If True, regenerate even if persona exists

        Returns:
            NodePersona for this node
        """
        # Load existing persona if it exists
        if not force_regenerate and self.persona_file.exists():
            try:
                data = json.loads(self.persona_file.read_text())
                persona = NodePersona(**data)
                logger.info(f"Loaded existing persona: {persona.display_name}")
                return persona
            except Exception as e:
                logger.warning(f"Failed to load persona: {e}")

        # Generate new persona
        persona = self._generate_new(manifest, hostname)
        self._save(persona)
        logger.info(f"Generated new persona: {persona.display_name}")
        return persona

    def _generate_new(
        self,
        manifest: CapabilityManifest,
        hostname: str,
    ) -> NodePersona:
        """Generate a new persona based on capabilities."""
        # Find primary capability
        primary = manifest.get_primary_capability()

        # Get role definition
        if primary and primary in ROLE_DEFINITIONS:
            definition = ROLE_DEFINITIONS[primary]
        else:
            definition = FALLBACK_DEFINITION

        # Generate name
        prefix = random.choice(definition["name_prefixes"])
        suffix = random.choice(LOCATION_SUFFIXES)

        # Use hostname hint for location if reasonable
        hostname_clean = hostname.split(".")[0].lower()
        location_hints = ["kitchen", "living", "bedroom", "office", "garage", "lab", "studio"]
        location = None
        for hint in location_hints:
            if hint in hostname_clean:
                location = hint.capitalize()
                break

        if location:
            name = f"{location} {prefix}"
        else:
            name = f"{prefix} {suffix}"

        # Collect all traits from available capabilities
        all_traits = list(definition["traits"])
        all_preferred_tasks = list(definition["preferred_tasks"])

        for cap in manifest.get_available_capabilities():
            if cap in ROLE_DEFINITIONS and cap != primary:
                cap_def = ROLE_DEFINITIONS[cap]
                # Add secondary traits (avoid duplicates)
                for trait in cap_def["traits"]:
                    if trait not in all_traits:
                        all_traits.append(trait)
                # Add secondary preferred tasks
                for task in cap_def["preferred_tasks"]:
                    if task not in all_preferred_tasks:
                        all_preferred_tasks.append(task)

        return NodePersona(
            name=name,
            role=definition["role"],
            traits=all_traits[:5],  # Limit to 5 traits
            preferred_tasks=all_preferred_tasks,
            primary_capability=primary.value if primary else None,
            generated_at=datetime.now(),
            generation_version="1.0.0",
        )

    def _save(self, persona: NodePersona) -> None:
        """Save persona to disk."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        data = persona.model_dump(mode="json")
        self.persona_file.write_text(json.dumps(data, indent=2, default=str))

    def load(self) -> Optional[NodePersona]:
        """Load existing persona if it exists."""
        if not self.persona_file.exists():
            return None

        try:
            data = json.loads(self.persona_file.read_text())
            return NodePersona(**data)
        except Exception as e:
            logger.warning(f"Failed to load persona: {e}")
            return None

    def update(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Optional[NodePersona]:
        """
        Update persona with user overrides.

        Args:
            name: User's preferred name for this node
            description: User's description of this node

        Returns:
            Updated persona or None if no persona exists
        """
        persona = self.load()
        if persona is None:
            return None

        if name is not None:
            persona.user_name_override = name
        if description is not None:
            persona.user_description_override = description

        self._save(persona)
        return persona

    def reset(self) -> bool:
        """Delete existing persona file."""
        if self.persona_file.exists():
            self.persona_file.unlink()
            return True
        return False


def format_persona_display(persona: NodePersona) -> str:
    """Format persona for CLI display."""
    lines = [
        f"Node Persona: {persona.display_name}",
        f"=" * 40,
        f"Role:     {persona.role}",
        f"Traits:   {', '.join(persona.traits)}",
        f"Primary:  {persona.primary_capability or 'general'}",
        "",
        "Preferred Tasks:",
    ]

    for task in persona.preferred_tasks:
        lines.append(f"  - {task}")

    if persona.user_name_override or persona.user_description_override:
        lines.append("")
        lines.append("User Overrides:")
        if persona.user_name_override:
            lines.append(f"  Name: {persona.user_name_override}")
        if persona.user_description_override:
            lines.append(f"  Description: {persona.user_description_override}")

    lines.append("")
    lines.append(f"Generated: {persona.generated_at}")

    return "\n".join(lines)
