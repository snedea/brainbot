"""HTTP transport layer for the mesh network.

Provides an HTTP server for receiving peer requests and
an HTTP client for making requests to peers.

Security Note: This transport layer does not implement authentication
or TLS. It is designed for use within trusted networks (e.g., Tailscale).
For untrusted networks, consider adding:
- TLS termination via a reverse proxy
- Token-based authentication
- IP allowlisting
"""

import asyncio
import json
import logging
import threading
import time
from typing import Any, Callable, Optional, TYPE_CHECKING
from urllib.parse import quote, unquote

import aiohttp
from aiohttp import web

if TYPE_CHECKING:
    from .node import MeshNode

logger = logging.getLogger(__name__)

# Default timeouts
CONNECT_TIMEOUT = 5.0
READ_TIMEOUT = 30.0


class MeshClient:
    """HTTP client for making requests to mesh peers."""

    def __init__(self, timeout_seconds: float = READ_TIMEOUT):
        """
        Initialize mesh client.

        Args:
            timeout_seconds: Default timeout for requests
        """
        self.timeout = aiohttp.ClientTimeout(
            total=timeout_seconds,
            connect=CONNECT_TIMEOUT,
        )
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self._session

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def get(self, url: str) -> tuple[int, Any]:
        """
        Make a GET request.

        Args:
            url: Full URL to request

        Returns:
            Tuple of (status_code, response_data)
        """
        session = await self._get_session()
        try:
            async with session.get(url) as resp:
                data = await resp.json()
                return resp.status, data
        except asyncio.TimeoutError:
            logger.debug(f"GET {url} timed out")
            return 0, {"error": "timeout"}
        except aiohttp.ClientError as e:
            logger.debug(f"GET {url} failed: {e}")
            return 0, {"error": str(e)}
        except Exception as e:
            logger.debug(f"GET {url} error: {e}")
            return 0, {"error": str(e)}

    async def post(self, url: str, data: dict) -> tuple[int, Any]:
        """
        Make a POST request.

        Args:
            url: Full URL to request
            data: JSON data to send

        Returns:
            Tuple of (status_code, response_data)
        """
        session = await self._get_session()
        try:
            async with session.post(url, json=data) as resp:
                response_data = await resp.json()
                return resp.status, response_data
        except asyncio.TimeoutError:
            logger.debug(f"POST {url} timed out")
            return 0, {"error": "timeout"}
        except aiohttp.ClientError as e:
            logger.debug(f"POST {url} failed: {e}")
            return 0, {"error": str(e)}
        except Exception as e:
            logger.debug(f"POST {url} error: {e}")
            return 0, {"error": str(e)}

    # Convenience methods for common mesh operations

    async def health(self, address: str) -> tuple[bool, dict]:
        """
        Check peer health.

        Args:
            address: Peer address (host:port)

        Returns:
            Tuple of (is_healthy, response_data)
        """
        url = f"http://{address}/health"
        status, data = await self.get(url)
        return status == 200, data

    async def info(self, address: str) -> tuple[bool, dict]:
        """
        Get peer info.

        Args:
            address: Peer address (host:port)

        Returns:
            Tuple of (success, info_dict)
        """
        url = f"http://{address}/info"
        status, data = await self.get(url)
        return status == 200, data

    async def get_peers(self, address: str) -> tuple[bool, list]:
        """
        Get peer's known peers.

        Args:
            address: Peer address (host:port)

        Returns:
            Tuple of (success, peer_list)
        """
        url = f"http://{address}/peers"
        status, data = await self.get(url)
        if status == 200:
            return True, data.get("peers", [])
        return False, []

    async def announce(self, address: str, my_info: dict) -> tuple[bool, dict]:
        """
        Announce ourselves to a peer.

        Args:
            address: Peer address (host:port)
            my_info: Our node info to send

        Returns:
            Tuple of (success, response_data)
        """
        url = f"http://{address}/peers/announce"
        status, data = await self.post(url, my_info)
        return status == 200, data

    async def get_manifest(self, address: str) -> tuple[bool, dict]:
        """
        Get peer's sync manifest.

        Args:
            address: Peer address (host:port)

        Returns:
            Tuple of (success, manifest_dict)
        """
        url = f"http://{address}/sync/manifest"
        status, data = await self.get(url)
        if status == 200:
            return True, data.get("manifest", {})
        return False, {}

    async def get_sync_item(self, address: str, key: str) -> tuple[bool, dict]:
        """
        Get a specific sync item from peer.

        Args:
            address: Peer address (host:port)
            key: Item key to fetch

        Returns:
            Tuple of (success, item_dict)
        """
        # URL-encode the key for path (safe='' encodes everything including /)
        encoded_key = quote(key, safe='')
        url = f"http://{address}/sync/data/{encoded_key}"
        status, data = await self.get(url)
        return status == 200, data

    async def push_sync_item(self, address: str, item: dict) -> tuple[bool, dict]:
        """
        Push a sync item to peer.

        Args:
            address: Peer address (host:port)
            item: Item dict to push

        Returns:
            Tuple of (success, response_data)
        """
        key = item.get("key", "")
        encoded_key = quote(key, safe='')
        url = f"http://{address}/sync/data/{encoded_key}"
        status, data = await self.post(url, item)
        return status in (200, 201), data

    async def send_chat(self, address: str, message: str, source: str = "mesh") -> tuple[bool, dict]:
        """
        Send a chat message to peer.

        Args:
            address: Peer address (host:port)
            message: Message to send
            source: Source identifier

        Returns:
            Tuple of (success, response_data)
        """
        url = f"http://{address}/chat"
        status, data = await self.post(url, {"message": message, "source": source})
        return status == 200, data

    async def send_task(self, address: str, task: dict) -> tuple[bool, dict]:
        """
        Send a task to peer.

        Args:
            address: Peer address (host:port)
            task: Task dict to send

        Returns:
            Tuple of (success, response_data)
        """
        url = f"http://{address}/task"
        status, data = await self.post(url, task)
        return status in (200, 202), data


class MeshServer:
    """HTTP server for handling mesh network requests."""

    def __init__(
        self,
        node: "MeshNode",
        host: str = "0.0.0.0",
        port: int = 7777,
    ):
        """
        Initialize mesh server.

        Args:
            node: The MeshNode this server belongs to
            host: Host to bind to
            port: Port to listen on
        """
        self.node = node
        self.host = host
        self.port = port

        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def _setup_routes(self) -> web.Application:
        """Set up HTTP routes."""
        app = web.Application()

        # Health and info
        app.router.add_get("/health", self._handle_health)
        app.router.add_get("/info", self._handle_info)

        # Peer discovery
        app.router.add_get("/peers", self._handle_get_peers)
        app.router.add_post("/peers/announce", self._handle_announce)

        # Sync protocol
        app.router.add_get("/sync/manifest", self._handle_get_manifest)
        app.router.add_get("/sync/data/{key:.*}", self._handle_get_data)
        app.router.add_post("/sync/data/{key:.*}", self._handle_post_data)

        # Chat and tasks
        app.router.add_post("/chat", self._handle_chat)
        app.router.add_post("/task", self._handle_task)

        return app

    async def _handle_health(self, request: web.Request) -> web.Response:
        """Handle GET /health - liveness check."""
        return web.json_response({
            "status": "healthy",
            "node_id": self.node.node_id[:8],
            "timestamp": time.time(),
        })

    async def _handle_info(self, request: web.Request) -> web.Response:
        """Handle GET /info - node information."""
        return web.json_response({
            "node_id": self.node.node_id,
            "hostname": self.node.hostname,
            "persona_name": self.node.persona_name,
            "capabilities": self.node.capabilities,
            "version": self.node.version,
            "address": f"{self.host}:{self.port}",
            "uptime": time.time() - self.node.start_time if self.node.start_time else 0,
            "quorum": self.node.get_quorum_status(),
        })

    async def _handle_get_peers(self, request: web.Request) -> web.Response:
        """Handle GET /peers - return known peers for gossip."""
        peers = self.node.peers.get_peer_list_for_gossip()

        # Add ourselves to the peer list
        peers.append({
            "node_id": self.node.node_id,
            "address": self.node.advertise_address,
            "hostname": self.node.hostname,
            "persona_name": self.node.persona_name,
            "capabilities": self.node.capabilities,
            "version": self.node.version,
            "state": "alive",
        })

        return web.json_response({
            "peers": peers,
            "timestamp": time.time(),
        })

    async def _handle_announce(self, request: web.Request) -> web.Response:
        """Handle POST /peers/announce - peer announcement."""
        try:
            data = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": "invalid JSON"}, status=400)

        node_id = data.get("node_id")
        address = data.get("address")

        if not node_id or not address:
            return web.json_response({"error": "missing node_id or address"}, status=400)

        # Add or update peer
        peer = self.node.peers.add_peer(
            node_id=node_id,
            address=address,
            hostname=data.get("hostname", ""),
            persona_name=data.get("persona_name", ""),
            capabilities=data.get("capabilities", []),
            version=data.get("version", ""),
            discovered_via="announce",
        )

        if peer:
            peer.update_heartbeat()
            logger.info(f"Peer announced: {node_id[:8]} ({data.get('persona_name', '')}) at {address}")

        # Return our info
        return web.json_response({
            "accepted": True,
            "node_id": self.node.node_id,
            "hostname": self.node.hostname,
            "persona_name": self.node.persona_name,
            "capabilities": self.node.capabilities,
            "version": self.node.version,
        })

    async def _handle_get_manifest(self, request: web.Request) -> web.Response:
        """Handle GET /sync/manifest - return data manifest for sync."""
        manifest = self.node.store.get_manifest()
        return web.json_response({
            "manifest": manifest,
            "node_id": self.node.node_id,
            "timestamp": time.time(),
        })

    async def _handle_get_data(self, request: web.Request) -> web.Response:
        """Handle GET /sync/data/{key} - return specific data item."""
        key = request.match_info["key"]
        # URL-decode the key (handles all percent-encoded characters)
        key = unquote(key)

        item = self.node.store.get(key)
        if item is None:
            return web.json_response({"error": "not found"}, status=404)

        return web.json_response(item.to_dict())

    async def _handle_post_data(self, request: web.Request) -> web.Response:
        """Handle POST /sync/data/{key} - receive data item from peer."""
        key = request.match_info["key"]
        key = unquote(key)

        try:
            data = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": "invalid JSON"}, status=400)

        # Validate item
        if data.get("key") != key:
            return web.json_response({"error": "key mismatch"}, status=400)

        # Import SyncItem here to avoid circular import
        from .store import SyncItem

        try:
            item = SyncItem.from_dict(data)
        except (KeyError, TypeError) as e:
            return web.json_response({"error": f"invalid item: {e}"}, status=400)

        # Merge item
        accepted, reason = self.node.store.merge_item(item)

        return web.json_response({
            "accepted": accepted,
            "reason": reason,
            "node_id": self.node.node_id,
        }, status=201 if accepted else 200)

    async def _handle_chat(self, request: web.Request) -> web.Response:
        """Handle POST /chat - receive chat message."""
        try:
            data = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": "invalid JSON"}, status=400)

        message = data.get("message", "")
        source = data.get("source", "mesh")

        if not message:
            return web.json_response({"error": "missing message"}, status=400)

        # Call node's chat handler
        if self.node.on_chat:
            try:
                response = self.node.on_chat(message, source)
                return web.json_response({
                    "response": response,
                    "node_id": self.node.node_id,
                    "persona_name": self.node.persona_name,
                })
            except Exception as e:
                logger.error(f"Chat handler error: {e}")
                return web.json_response({"error": str(e)}, status=500)
        else:
            return web.json_response({"error": "no chat handler"}, status=501)

    async def _handle_task(self, request: web.Request) -> web.Response:
        """Handle POST /task - receive task."""
        try:
            data = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": "invalid JSON"}, status=400)

        task_id = data.get("task_id")
        task_type = data.get("task_type")

        if not task_id or not task_type:
            return web.json_response({"error": "missing task_id or task_type"}, status=400)

        # Call node's task handler
        if self.node.on_task:
            try:
                result = self.node.on_task(data)
                return web.json_response({
                    "accepted": True,
                    "task_id": task_id,
                    "result": result,
                    "node_id": self.node.node_id,
                }, status=202)
            except Exception as e:
                logger.error(f"Task handler error: {e}")
                return web.json_response({"error": str(e)}, status=500)
        else:
            return web.json_response({"error": "no task handler"}, status=501)

    def _run_server(self) -> None:
        """Run the server in a separate thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        try:
            self._loop.run_until_complete(self._start_server())
            self._running = True
            self._loop.run_forever()
        except Exception as e:
            logger.error(f"Server error: {e}")
        finally:
            self._loop.run_until_complete(self._stop_server())
            self._loop.close()

    async def _start_server(self) -> None:
        """Start the HTTP server."""
        self._app = self._setup_routes()
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()
        logger.info(f"Mesh server listening on {self.host}:{self.port}")

    async def _stop_server(self) -> None:
        """Stop the HTTP server."""
        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()
        logger.info("Mesh server stopped")

    def start(self) -> None:
        """Start the server in a background thread."""
        if self._running:
            return

        self._thread = threading.Thread(target=self._run_server, daemon=True)
        self._thread.start()

        # Wait for server to be ready
        for _ in range(50):
            if self._running:
                break
            time.sleep(0.1)

    def stop(self) -> None:
        """Stop the server."""
        if not self._running:
            return

        self._running = False
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)

        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None

    @property
    def is_running(self) -> bool:
        """Check if server is running."""
        return self._running
