"""Core data models for the BrainBot distributed network."""

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class HardwareCapability(str, Enum):
    """Hardware capabilities that a node can have."""

    # Displays
    DISPLAY_1INCH = "display_1inch"  # Small OLED status display
    DISPLAY_5INCH = "display_5inch"  # Main story/status display
    DISPLAY_HDMI = "display_hdmi"  # Standard monitor via HDMI
    DISPLAY_HEADLESS = "display_headless"  # Virtual framebuffer

    # GPU/Compute
    GPU_CUDA = "gpu_cuda"  # NVIDIA GPU with CUDA
    GPU_ROCM = "gpu_rocm"  # AMD GPU with ROCm
    GPU_METAL = "gpu_metal"  # Apple Metal GPU
    GPU_NONE = "gpu_none"  # CPU only

    # Camera/Vision
    CAMERA_USB = "camera_usb"  # USB webcam
    CAMERA_PI = "camera_pi"  # Raspberry Pi camera module
    CAMERA_NONE = "camera_none"

    # Audio
    MICROPHONE = "microphone"  # Audio input
    SPEAKER = "speaker"  # Audio output
    AUDIO_NONE = "audio_none"

    # Lighting
    LED_STRIP = "led_strip"  # NeoPixel/WS2812 LED strip
    LED_NONE = "led_none"

    # Cooling
    FAN_PWM = "fan_pwm"  # PWM-controlled fan
    FAN_NONE = "fan_none"

    # Sensors
    SENSOR_TEMP = "sensor_temp"  # Temperature sensor
    SENSOR_HUMIDITY = "sensor_humidity"
    SENSOR_MOTION = "sensor_motion"
    SENSOR_LIGHT = "sensor_light"

    # Networking
    NETWORK_ETHERNET = "network_ethernet"
    NETWORK_WIFI = "network_wifi"
    NETWORK_BLUETOOTH = "network_bluetooth"

    # Storage
    STORAGE_SSD = "storage_ssd"
    STORAGE_HDD = "storage_hdd"
    STORAGE_SD = "storage_sd"
    STORAGE_NAS = "storage_nas"


class UsagePolicy(str, Enum):
    """How a capability can be used."""

    ALWAYS = "always"  # Can always use
    SCHEDULED = "scheduled"  # Only during certain times
    EXPLICIT = "explicit"  # Requires explicit confirmation
    NEVER = "never"  # Disabled by user
    LOCAL_ONLY = "local_only"  # Only for local tasks, not network


class CapabilitySpec(BaseModel):
    """Specification for a single hardware capability."""

    capability: HardwareCapability
    available: bool = True
    details: dict = Field(default_factory=dict)  # Capability-specific details

    # Safety policy
    usage_policy: UsagePolicy = UsagePolicy.ALWAYS
    requires_confirmation: bool = False
    allowed_task_types: list[str] = Field(default_factory=list)  # Empty = all allowed

    # Metadata
    detected_at: datetime = Field(default_factory=datetime.now)
    detection_method: str = ""  # How it was detected

    class Config:
        use_enum_values = True


class CapabilityManifest(BaseModel):
    """Complete hardware manifest for a node."""

    capabilities: list[CapabilitySpec] = Field(default_factory=list)

    # System info
    platform: str = ""  # darwin, linux, win32
    platform_version: str = ""
    hostname: str = ""
    cpu_cores: int = 0
    ram_gb: float = 0.0
    disk_gb: float = 0.0

    # Raspberry Pi specific
    is_raspberry_pi: bool = False
    pi_model: Optional[str] = None

    # Scan metadata
    scanned_at: datetime = Field(default_factory=datetime.now)
    scan_version: str = "1.0.0"

    def has_capability(self, cap: HardwareCapability) -> bool:
        """Check if this node has a specific capability."""
        for spec in self.capabilities:
            if spec.capability == cap and spec.available:
                return True
        return False

    def get_capability(self, cap: HardwareCapability) -> Optional[CapabilitySpec]:
        """Get the spec for a capability if available."""
        for spec in self.capabilities:
            if spec.capability == cap:
                return spec
        return None

    def get_available_capabilities(self) -> list[HardwareCapability]:
        """Get list of available capabilities."""
        return [
            HardwareCapability(spec.capability)
            for spec in self.capabilities
            if spec.available
        ]

    def get_primary_capability(self) -> Optional[HardwareCapability]:
        """Get the primary/most distinctive capability of this node."""
        # Priority order for determining primary role
        priority = [
            HardwareCapability.GPU_CUDA,
            HardwareCapability.GPU_ROCM,
            HardwareCapability.GPU_METAL,
            HardwareCapability.DISPLAY_5INCH,
            HardwareCapability.CAMERA_PI,
            HardwareCapability.CAMERA_USB,
            HardwareCapability.LED_STRIP,
            HardwareCapability.DISPLAY_1INCH,
            HardwareCapability.SPEAKER,
            HardwareCapability.MICROPHONE,
        ]

        for cap in priority:
            if self.has_capability(cap):
                return cap
        return None


class NodeIdentity(BaseModel):
    """Unique identity for a BrainBot node."""

    node_id: str  # UUID v4
    hostname: str
    machine_fingerprint: str = ""  # From /etc/machine-id or hardware serial

    created_at: datetime = Field(default_factory=datetime.now)
    last_boot: datetime = Field(default_factory=datetime.now)


class NodePersona(BaseModel):
    """Personality and role for a BrainBot node."""

    # Auto-generated based on hardware
    name: str = ""  # e.g., "Studio", "Kitchen Bot", "GPU Worker"
    role: str = ""  # e.g., "display", "compute", "sensor"
    traits: list[str] = Field(default_factory=list)  # e.g., ["visual", "creative"]
    preferred_tasks: list[str] = Field(default_factory=list)

    # User overrides
    user_name_override: Optional[str] = None
    user_description_override: Optional[str] = None

    # Derived from hardware
    primary_capability: Optional[str] = None

    # Metadata
    generated_at: datetime = Field(default_factory=datetime.now)
    generation_version: str = "1.0.0"

    @property
    def display_name(self) -> str:
        """Get the display name (user override or generated)."""
        return self.user_name_override or self.name


class NodeRegistryEntry(BaseModel):
    """Entry in the node registry (stored in R2)."""

    node_id: str
    hostname: str
    persona: NodePersona
    capabilities: list[str] = Field(default_factory=list)  # Capability enum values

    # Status
    last_heartbeat: datetime = Field(default_factory=datetime.now)
    status: str = "online"  # online, offline, degraded

    # Version tracking
    version: str = "unknown"  # Git commit hash

    # Network info
    ip_address: Optional[str] = None
    last_seen_from: Optional[str] = None  # Where the heartbeat came from

    def is_online(self, timeout_seconds: int = 300) -> bool:
        """Check if node is considered online (heartbeat within timeout)."""
        age = (datetime.now() - self.last_heartbeat).total_seconds()
        return age < timeout_seconds


class NetworkEvent(BaseModel):
    """Event in the append-only network event log."""

    event_id: str  # UUID
    timestamp: datetime = Field(default_factory=datetime.now)
    node_id: str  # Which node generated this event
    event_type: str  # Type of event (see EventType enum)
    data: dict = Field(default_factory=dict)

    # Integrity
    checksum: str = ""  # blake2b hash of event data
    previous_event_id: Optional[str] = None  # Chain link


class EventType(str, Enum):
    """Types of events in the network log."""

    # Node lifecycle
    NODE_BOOT = "node_boot"
    NODE_SHUTDOWN = "node_shutdown"
    NODE_HEARTBEAT = "node_heartbeat"

    # Memory operations
    MEMORY_CREATED = "memory_created"
    MEMORY_UPDATED = "memory_updated"
    MEMORY_ARCHIVED = "memory_archived"
    MEMORY_SYNCED = "memory_synced"

    # Task operations
    TASK_CREATED = "task_created"
    TASK_CLAIMED = "task_claimed"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"

    # Safety
    CAPABILITY_ENABLED = "capability_enabled"
    CAPABILITY_DISABLED = "capability_disabled"
    CONFIRMATION_REQUESTED = "confirmation_requested"
    CONFIRMATION_GRANTED = "confirmation_granted"


class NetworkTask(BaseModel):
    """A task that can be routed to capable nodes."""

    task_id: str  # UUID
    task_type: str  # e.g., "display_text", "generate_image", "led_mood"
    payload: dict = Field(default_factory=dict)

    # Requirements
    required_capabilities: list[str] = Field(default_factory=list)
    preferred_capabilities: list[str] = Field(default_factory=list)
    min_ram_gb: float = 0.0
    min_disk_gb: float = 0.0

    # Status
    status: str = "pending"  # pending, claimed, running, completed, failed
    created_by: str = ""  # node_id that created this task
    claimed_by: Optional[str] = None  # node_id that claimed it
    created_at: datetime = Field(default_factory=datetime.now)
    claimed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Result
    result: Optional[dict] = None
    error: Optional[str] = None

    # Routing hints
    priority: int = 1  # 1-10, higher = more urgent
    target_node: Optional[str] = None  # Specific node to route to
