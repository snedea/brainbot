"""BrainBot P2P Mesh Network Package.

A true peer-to-peer distributed network inspired by LimeWire/Napster/BitTorrent:
- Nodes discover each other via gossip protocol
- Sync state directly between peers (no central registry required)
- Gracefully handle nodes joining/leaving
- Last-write-wins with timestamp conflict resolution
- Quorum-aware (3+ nodes recommended, but works with 1-2)
"""

from .peer import PeerInfo, PeerState, PeerRegistry
from .store import VersionedStore, SyncItem
from .transport import MeshServer, MeshClient
from .gossip import GossipProtocol
from .sync import SyncProtocol
from .node import MeshNode

__all__ = [
    # Peer management
    "PeerInfo",
    "PeerState",
    "PeerRegistry",
    # Data store
    "VersionedStore",
    "SyncItem",
    # Transport
    "MeshServer",
    "MeshClient",
    # Protocols
    "GossipProtocol",
    "SyncProtocol",
    # Main coordinator
    "MeshNode",
]
