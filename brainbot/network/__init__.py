"""BrainBot Distributed Network Package.

Enables BrainBot nodes to:
- Self-identify based on hardware capabilities
- Share a unified brain via cloud storage (R2/S3) or P2P mesh
- Route tasks to capable nodes
- Enforce safety policies on sensitive capabilities
- Detect user intent using LLM for smart routing
"""

from .models import (
    HardwareCapability,
    CapabilitySpec,
    CapabilityManifest,
    NodeIdentity,
    NodePersona,
    UsagePolicy,
    EventType,
    NetworkEvent,
    NetworkTask,
    NodeRegistryEntry,
)
from .node_id import NodeIdManager
from .hardware_scanner import HardwareScanner
from .persona import PersonaGenerator
from .intent_detector import IntentDetector, DetectedIntent, IntentType, detect_intent
from .slack_network import SlackNetworkBot, get_slack_network

# P2P Mesh Network (optional, may not be installed)
try:
    from .mesh import (
        MeshNode,
        PeerInfo,
        PeerState,
        PeerRegistry,
        VersionedStore,
        SyncItem,
    )
    MESH_AVAILABLE = True
except ImportError:
    MESH_AVAILABLE = False
    MeshNode = None
    PeerInfo = None
    PeerState = None
    PeerRegistry = None
    VersionedStore = None
    SyncItem = None

__all__ = [
    # Models
    "HardwareCapability",
    "CapabilitySpec",
    "CapabilityManifest",
    "NodeIdentity",
    "NodePersona",
    "UsagePolicy",
    "EventType",
    "NetworkEvent",
    "NetworkTask",
    "NodeRegistryEntry",
    # Managers
    "NodeIdManager",
    "HardwareScanner",
    "PersonaGenerator",
    # Intent Detection
    "IntentDetector",
    "DetectedIntent",
    "IntentType",
    "detect_intent",
    # Slack Network
    "SlackNetworkBot",
    "get_slack_network",
    # Mesh Network
    "MESH_AVAILABLE",
    "MeshNode",
    "PeerInfo",
    "PeerState",
    "PeerRegistry",
    "VersionedStore",
    "SyncItem",
]
