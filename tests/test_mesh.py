"""Tests for the BrainBot P2P mesh network.

Tests cover:
- PeerInfo and PeerRegistry
- VersionedStore and SyncItem
- URL encoding/decoding
- Conflict resolution (last-write-wins)
- Quorum status calculation
"""

import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import quote, unquote

import pytest

from brainbot.network.mesh.peer import PeerInfo, PeerState, PeerRegistry
from brainbot.network.mesh.store import VersionedStore, SyncItem


class TestPeerInfo:
    """Tests for PeerInfo dataclass."""

    def test_create_peer(self):
        """Test basic peer creation."""
        peer = PeerInfo(
            node_id="test-node-id",
            address="192.168.1.100:7777",
            hostname="testhost",
            persona_name="Test Node",
        )
        assert peer.node_id == "test-node-id"
        assert peer.address == "192.168.1.100:7777"
        assert peer.state == PeerState.ALIVE
        assert peer.missed_heartbeats == 0

    def test_update_heartbeat(self):
        """Test heartbeat updates peer state."""
        peer = PeerInfo(node_id="test", address="127.0.0.1:7777")
        peer.state = PeerState.DEAD
        peer.missed_heartbeats = 5

        previous_state = peer.update_heartbeat()

        assert previous_state == PeerState.DEAD
        assert peer.state == PeerState.ALIVE
        assert peer.missed_heartbeats == 0

    def test_missed_heartbeat_transitions(self):
        """Test state transitions on missed heartbeats."""
        peer = PeerInfo(node_id="test", address="127.0.0.1:7777")
        assert peer.state == PeerState.ALIVE

        # First miss -> SUSPECTED
        peer.record_missed_heartbeat(max_missed=3)
        assert peer.state == PeerState.SUSPECTED
        assert peer.missed_heartbeats == 1

        # Second miss -> still SUSPECTED
        peer.record_missed_heartbeat(max_missed=3)
        assert peer.state == PeerState.SUSPECTED
        assert peer.missed_heartbeats == 2

        # Third miss -> DEAD
        peer.record_missed_heartbeat(max_missed=3)
        assert peer.state == PeerState.DEAD
        assert peer.missed_heartbeats == 3

    def test_configurable_max_missed(self):
        """Test that max_missed_heartbeats is configurable."""
        peer = PeerInfo(node_id="test", address="127.0.0.1:7777")

        # With max_missed=2, should become DEAD after 2 misses
        peer.record_missed_heartbeat(max_missed=2)
        assert peer.state == PeerState.SUSPECTED
        peer.record_missed_heartbeat(max_missed=2)
        assert peer.state == PeerState.DEAD

    def test_is_reachable(self):
        """Test is_reachable method."""
        peer = PeerInfo(node_id="test", address="127.0.0.1:7777")

        assert peer.is_reachable() is True  # ALIVE

        peer.state = PeerState.SUSPECTED
        assert peer.is_reachable() is True  # SUSPECTED still reachable

        peer.state = PeerState.DEAD
        assert peer.is_reachable() is False  # DEAD not reachable

    def test_to_dict_and_from_dict(self):
        """Test serialization round-trip."""
        peer = PeerInfo(
            node_id="test-node",
            address="10.0.0.1:7777",
            hostname="myhost",
            persona_name="My Node",
            capabilities=["gpu_cuda", "display_hdmi"],
            version="1.0.0",
        )

        data = peer.to_dict()
        restored = PeerInfo.from_dict(data)

        assert restored.node_id == peer.node_id
        assert restored.address == peer.address
        assert restored.hostname == peer.hostname
        assert restored.persona_name == peer.persona_name
        assert restored.capabilities == peer.capabilities
        assert restored.version == peer.version


class TestPeerRegistry:
    """Tests for PeerRegistry."""

    def test_add_peer(self):
        """Test adding a peer."""
        registry = PeerRegistry("local-node")

        peer = registry.add_peer(
            node_id="remote-node",
            address="192.168.1.100:7777",
            persona_name="Remote",
            discovered_via="test",
        )

        assert peer is not None
        assert peer.node_id == "remote-node"
        assert len(registry) == 1

    def test_add_self_returns_none(self):
        """Test that adding self returns None."""
        registry = PeerRegistry("local-node")
        peer = registry.add_peer(
            node_id="local-node",
            address="127.0.0.1:7777",
        )
        assert peer is None
        assert len(registry) == 0

    def test_get_peer_by_name(self):
        """Test case-insensitive name lookup."""
        registry = PeerRegistry("local")
        registry.add_peer(
            node_id="remote",
            address="192.168.1.100:7777",
            persona_name="Echo",
        )

        assert registry.get_peer_by_name("Echo") is not None
        assert registry.get_peer_by_name("echo") is not None
        assert registry.get_peer_by_name("ECHO") is not None
        assert registry.get_peer_by_name("unknown") is None

    def test_quorum_status(self):
        """Test quorum status calculation."""
        registry = PeerRegistry("local")

        # Just us -> standalone
        status, count = registry.get_quorum_status()
        assert status == "standalone"
        assert count == 1

        # Add one peer -> pair
        registry.add_peer("peer1", "192.168.1.100:7777")
        status, count = registry.get_quorum_status()
        assert status == "pair"
        assert count == 2

        # Add another -> quorum
        registry.add_peer("peer2", "192.168.1.101:7777")
        status, count = registry.get_quorum_status()
        assert status == "quorum"
        assert count == 3

    def test_update_heartbeat_returns_previous_state(self):
        """Test that update_heartbeat returns previous state."""
        registry = PeerRegistry("local")
        registry.add_peer("remote", "192.168.1.100:7777")

        # Mark as dead
        peer = registry.get_peer("remote")
        peer.state = PeerState.DEAD

        # Update heartbeat should return previous state
        found, previous = registry.update_heartbeat("remote")
        assert found is True
        assert previous == PeerState.DEAD

    def test_configurable_max_missed(self):
        """Test that registry uses configurable max_missed_heartbeats."""
        registry = PeerRegistry("local", max_missed_heartbeats=2)
        registry.add_peer("remote", "192.168.1.100:7777")

        # With max_missed=2, should become DEAD after 2 misses
        registry.record_missed_heartbeat("remote")
        assert registry.get_peer("remote").state == PeerState.SUSPECTED

        registry.record_missed_heartbeat("remote")
        assert registry.get_peer("remote").state == PeerState.DEAD

    def test_merge_peer_list(self):
        """Test merging peer list from gossip."""
        registry = PeerRegistry("local")

        peers = [
            {"node_id": "peer1", "address": "192.168.1.100:7777"},
            {"node_id": "peer2", "address": "192.168.1.101:7777"},
            {"node_id": "local", "address": "127.0.0.1:7777"},  # Should be skipped
        ]

        new_count = registry.merge_peer_list(peers, source="test")

        assert new_count == 2
        assert len(registry) == 2
        assert "peer1" in registry
        assert "peer2" in registry
        assert "local" not in registry


class TestVersionedStore:
    """Tests for VersionedStore."""

    def test_put_and_get(self):
        """Test basic put and get operations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = VersionedStore("node1", Path(tmpdir))

            item = store.put("test/key", {"data": "value"})

            assert item.key == "test/key"
            assert item.value == {"data": "value"}
            assert item.origin_node == "node1"
            assert item.version > 0

            retrieved = store.get("test/key")
            assert retrieved is not None
            assert retrieved.value == {"data": "value"}

    def test_get_manifest(self):
        """Test manifest generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = VersionedStore("node1", Path(tmpdir))
            store.put("key1", "value1")
            store.put("key2", "value2")

            manifest = store.get_manifest()

            assert "key1" in manifest
            assert "key2" in manifest
            assert "timestamp" in manifest["key1"]
            assert "version" in manifest["key1"]

    def test_merge_newer_item(self):
        """Test merging a newer item (should be accepted)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = VersionedStore("node1", Path(tmpdir))
            store.put("test", "old_value", timestamp=100.0)

            newer = SyncItem(
                key="test",
                value="new_value",
                timestamp=200.0,
                origin_node="node2",
                version=1,
            )

            accepted, reason = store.merge_item(newer)

            assert accepted is True
            assert reason == "newer"
            assert store.get_value("test") == "new_value"

    def test_reject_older_item(self):
        """Test merging an older item (should be rejected)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = VersionedStore("node1", Path(tmpdir))
            store.put("test", "new_value", timestamp=200.0)

            older = SyncItem(
                key="test",
                value="old_value",
                timestamp=100.0,
                origin_node="node2",
                version=1,
            )

            accepted, reason = store.merge_item(older)

            assert accepted is False
            assert reason == "older"
            assert store.get_value("test") == "new_value"

    def test_tiebreaker_by_origin(self):
        """Test that equal timestamps use origin_node as tiebreaker."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = VersionedStore("node_a", Path(tmpdir))
            store.put("test", "value_a", timestamp=100.0, origin_node="node_a")

            # Same timestamp, but "node_b" > "node_a" lexically -> should win
            item_b = SyncItem(
                key="test",
                value="value_b",
                timestamp=100.0,
                origin_node="node_b",
                version=1,
            )

            accepted, reason = store.merge_item(item_b)
            assert accepted is True
            assert store.get_value("test") == "value_b"

    def test_get_items_for_sync(self):
        """Test determining what to push/pull."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = VersionedStore("node1", Path(tmpdir))
            store.put("local_only", "value", timestamp=100.0)
            store.put("local_newer", "value", timestamp=200.0)
            store.put("local_older", "value", timestamp=50.0)

            peer_manifest = {
                "remote_only": {"timestamp": 100.0, "origin_node": "node2"},
                "local_newer": {"timestamp": 100.0, "origin_node": "node2"},
                "local_older": {"timestamp": 100.0, "origin_node": "node2"},
            }

            to_push, to_pull = store.get_items_for_sync(peer_manifest)

            push_keys = [item.key for item in to_push]
            assert "local_only" in push_keys  # They don't have it
            assert "local_newer" in push_keys  # Ours is newer
            assert "local_older" not in push_keys  # Theirs is newer

            assert "remote_only" in to_pull  # We don't have it
            assert "local_older" in to_pull  # Theirs is newer


class TestSyncItem:
    """Tests for SyncItem."""

    def test_is_newer_than(self):
        """Test timestamp comparison."""
        older = SyncItem("key", "v1", timestamp=100.0, origin_node="a", version=1)
        newer = SyncItem("key", "v2", timestamp=200.0, origin_node="b", version=2)

        assert newer.is_newer_than(older) is True
        assert older.is_newer_than(newer) is False

    def test_is_newer_than_tiebreaker(self):
        """Test origin_node tiebreaker."""
        item_a = SyncItem("key", "v1", timestamp=100.0, origin_node="node_a", version=1)
        item_b = SyncItem("key", "v2", timestamp=100.0, origin_node="node_b", version=1)

        # "node_b" > "node_a" lexically
        assert item_b.is_newer_than(item_a) is True
        assert item_a.is_newer_than(item_b) is False

    def test_content_hash(self):
        """Test content hash computation."""
        item1 = SyncItem("key", {"data": "value"}, timestamp=100.0, origin_node="a", version=1)
        item2 = SyncItem("key", {"data": "value"}, timestamp=100.0, origin_node="a", version=1)
        item3 = SyncItem("key", {"data": "different"}, timestamp=100.0, origin_node="a", version=1)

        assert item1.content_hash == item2.content_hash
        assert item1.content_hash != item3.content_hash


class TestURLEncoding:
    """Tests for URL encoding of sync keys."""

    def test_encode_decode_special_characters(self):
        """Test encoding/decoding keys with special characters."""
        keys_to_test = [
            "brain/memories/2024-01-15.md",
            "data/with spaces/file.txt",
            "path/with/slashes/and spaces",
            "special!@#$%chars",
            "unicode/\u00e9\u00e8\u00ea/test",
        ]

        for key in keys_to_test:
            encoded = quote(key, safe='')
            decoded = unquote(encoded)
            assert decoded == key, f"Round-trip failed for: {key}"

    def test_slash_encoding(self):
        """Test that slashes are properly encoded."""
        key = "path/to/file"
        encoded = quote(key, safe='')

        assert "/" not in encoded
        assert "%2F" in encoded
        assert unquote(encoded) == key


class TestIntegration:
    """Integration tests for mesh components working together."""

    def test_peer_recovery_triggers_resync(self):
        """Test that recovering peer detection works."""
        registry = PeerRegistry("local")
        registry.add_peer("remote", "192.168.1.100:7777")

        # Simulate peer going dead
        peer = registry.get_peer("remote")
        peer.state = PeerState.DEAD

        # Simulate recovery (heartbeat succeeds)
        found, previous_state = registry.update_heartbeat("remote")

        assert found is True
        assert previous_state == PeerState.DEAD
        assert peer.state == PeerState.ALIVE

        # This is the trigger for resync
        if previous_state == PeerState.DEAD:
            # Should trigger resync - this is what gossip protocol checks
            pass  # In real code: self.node.trigger_sync_with_peer(peer.node_id)

    def test_store_persistence(self):
        """Test that store persists across restarts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create store and add data
            store1 = VersionedStore("node1", Path(tmpdir))
            store1.put("persistent/key", {"value": 42})
            del store1

            # Recreate store from same directory
            store2 = VersionedStore("node1", Path(tmpdir))

            assert store2.get_value("persistent/key") == {"value": 42}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
