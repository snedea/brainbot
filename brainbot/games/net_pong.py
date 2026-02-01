"""Networked Pong game for BrainBot mesh network.

Allows two nodes (e.g., Pi and MacBook) to play Pong against each other
over the mesh network.

Architecture:
- HOST: Runs game physics, serves game state
- CLIENT: Sends paddle input, receives and renders game state
- Both nodes render the game locally on their displays
"""

import asyncio
import json
import logging
import threading
import time
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
from typing import Optional, Callable, TYPE_CHECKING

import aiohttp
from aiohttp import web

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

from .pong import (
    PongGame, PlayerType, Paddle, Ball,
    RAINBOW_COLORS, get_rainbow_color,
    pause_face_animator, resume_face_animator,
)

if TYPE_CHECKING:
    from ..network.mesh.node import MeshNode

logger = logging.getLogger(__name__)


class GameRole(Enum):
    """Role of this node in the networked game."""
    HOST = "host"
    CLIENT = "client"


@dataclass
class NetworkGameState:
    """Game state that gets synced between nodes."""
    # Ball
    ball_x: float
    ball_y: float
    ball_vx: float
    ball_vy: float
    ball_speed: float

    # Paddles (y positions)
    left_y: float
    right_y: float

    # Scores
    left_score: int
    right_score: int

    # Game status
    game_over: bool
    winner: Optional[str]
    rally_count: int

    # Timing
    timestamp: float
    frame_number: int

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "NetworkGameState":
        return cls(**data)


@dataclass
class PaddleInput:
    """Paddle input from a remote node."""
    y_velocity: float  # -1 to 1
    timestamp: float
    node_id: str


class NetPongServer:
    """HTTP server for hosting a networked Pong game."""

    def __init__(
        self,
        game: "NetPongGame",
        host: str = "0.0.0.0",
        port: int = 7778,
    ):
        self.game = game
        self.host = host
        self.port = port
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self.is_running = False

    def _setup_routes(self) -> web.Application:
        """Set up HTTP routes."""
        app = web.Application()
        app.router.add_get("/game/state", self._handle_get_state)
        app.router.add_post("/game/input", self._handle_input)
        app.router.add_get("/game/join", self._handle_join)
        return app

    async def _handle_get_state(self, request: web.Request) -> web.Response:
        """Return current game state."""
        state = self.game.get_network_state()
        return web.json_response(state.to_dict())

    async def _handle_input(self, request: web.Request) -> web.Response:
        """Receive paddle input from remote player."""
        try:
            data = await request.json()
            paddle_input = PaddleInput(
                y_velocity=data.get("y_velocity", 0),
                timestamp=data.get("timestamp", time.time()),
                node_id=data.get("node_id", "unknown"),
            )
            self.game.receive_remote_input(paddle_input)
            return web.json_response({"status": "ok"})
        except Exception as e:
            logger.error(f"Error handling input: {e}")
            return web.json_response({"error": str(e)}, status=400)

    async def _handle_join(self, request: web.Request) -> web.Response:
        """Handle a client joining the game."""
        node_id = request.query.get("node_id", "unknown")
        persona = request.query.get("persona", "Remote Player")

        logger.info(f"Player joining: {persona} ({node_id[:8]})")
        self.game.on_player_joined(node_id, persona)

        return web.json_response({
            "status": "ok",
            "game_port": self.port,
            "host_persona": self.game.host_persona,
            "you_are": "right",  # Client always plays right paddle
        })

    async def _run_server(self) -> None:
        """Run the server in an async context."""
        self._app = self._setup_routes()
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()

        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()

        logger.info(f"NetPong server started on {self.host}:{self.port}")
        self.is_running = True

        # Keep running until stopped
        while self.is_running:
            await asyncio.sleep(0.1)

        await self._runner.cleanup()

    def _server_thread(self) -> None:
        """Thread function for running the server."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._run_server())

    def start(self) -> None:
        """Start the server in a background thread."""
        self._thread = threading.Thread(target=self._server_thread, daemon=True)
        self._thread.start()

        # Wait for server to start
        for _ in range(50):
            if self.is_running:
                break
            time.sleep(0.1)

    def stop(self) -> None:
        """Stop the server."""
        self.is_running = False
        if self._thread:
            self._thread.join(timeout=2)


class NetPongClient:
    """HTTP client for connecting to a networked Pong game."""

    def __init__(self, node_id: str, persona: str):
        self.node_id = node_id
        self.persona = persona
        self._session: Optional[aiohttp.ClientSession] = None
        self.host_address: Optional[str] = None
        self.game_port: int = 7778

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=5, connect=2)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def join_game(self, host_address: str, port: int = 7778) -> dict:
        """Join a game hosted at the given address."""
        self.host_address = host_address
        self.game_port = port

        session = await self._get_session()
        url = f"http://{host_address}:{port}/game/join"
        params = {"node_id": self.node_id, "persona": self.persona}

        async with session.get(url, params=params) as resp:
            return await resp.json()

    async def get_game_state(self) -> Optional[NetworkGameState]:
        """Fetch current game state from host."""
        if not self.host_address:
            return None

        session = await self._get_session()
        url = f"http://{self.host_address}:{self.game_port}/game/state"

        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return NetworkGameState.from_dict(data)
        except Exception as e:
            logger.debug(f"Error fetching game state: {e}")

        return None

    async def send_input(self, y_velocity: float) -> bool:
        """Send paddle input to host."""
        if not self.host_address:
            return False

        session = await self._get_session()
        url = f"http://{self.host_address}:{self.game_port}/game/input"

        data = {
            "y_velocity": y_velocity,
            "timestamp": time.time(),
            "node_id": self.node_id,
        }

        try:
            async with session.post(url, json=data) as resp:
                return resp.status == 200
        except Exception as e:
            logger.debug(f"Error sending input: {e}")
            return False


class NetPongGame(PongGame):
    """
    Networked Pong game for mesh network play.

    Extends PongGame with network synchronization capabilities.
    """

    def __init__(
        self,
        role: GameRole,
        node_id: str,
        persona: str,
        mesh_node: Optional["MeshNode"] = None,
        game_port: int = 7778,
        **kwargs
    ):
        """
        Initialize networked Pong.

        Args:
            role: HOST or CLIENT
            node_id: This node's unique ID
            persona: This node's display name
            mesh_node: Optional mesh node for peer discovery
            game_port: Port for game server
            **kwargs: Passed to PongGame
        """
        # Set up player types based on role
        if role == GameRole.HOST:
            # Host plays left paddle
            left_player = PlayerType.AI
            right_player = PlayerType.HUMAN  # Will be remote
        else:
            # Client plays right paddle
            left_player = PlayerType.AI  # Remote host's AI
            right_player = PlayerType.HUMAN

        super().__init__(
            left_player=left_player,
            right_player=right_player,
            **kwargs
        )

        self.role = role
        self.node_id = node_id
        self.host_persona = persona if role == GameRole.HOST else ""
        self.client_persona = persona if role == GameRole.CLIENT else ""
        self.mesh_node = mesh_node
        self.game_port = game_port

        # Network components
        self.server: Optional[NetPongServer] = None
        self.client: Optional[NetPongClient] = None

        # Remote input buffer
        self._remote_input: float = 0.0
        self._remote_input_time: float = 0.0

        # State sync
        self._frame_number = 0
        self._last_state_sync: float = 0.0
        self._connected = False

        # Opponent info
        self.opponent_node_id: Optional[str] = None
        self.opponent_persona: Optional[str] = None

    def start_hosting(self) -> None:
        """Start hosting a game (for HOST role)."""
        if self.role != GameRole.HOST:
            raise RuntimeError("Only HOST can start hosting")

        self.server = NetPongServer(self, port=self.game_port)
        self.server.start()
        logger.info(f"Hosting NetPong game on port {self.game_port}")

    def on_player_joined(self, node_id: str, persona: str) -> None:
        """Called when a remote player joins."""
        self.opponent_node_id = node_id
        self.opponent_persona = persona
        self._connected = True
        logger.info(f"Player joined: {persona}")

    async def connect_to_host(self, host_address: str) -> bool:
        """Connect to a hosted game (for CLIENT role)."""
        if self.role != GameRole.CLIENT:
            raise RuntimeError("Only CLIENT can connect to host")

        self.client = NetPongClient(self.node_id, self.client_persona)

        try:
            result = await self.client.join_game(host_address, self.game_port)
            if result.get("status") == "ok":
                self.host_persona = result.get("host_persona", "Host")
                self.opponent_persona = self.host_persona
                self._connected = True
                logger.info(f"Connected to game hosted by {self.host_persona}")
                return True
        except Exception as e:
            logger.error(f"Failed to connect to host: {e}")

        return False

    def receive_remote_input(self, paddle_input: PaddleInput) -> None:
        """Receive and buffer remote player input."""
        self._remote_input = paddle_input.y_velocity
        self._remote_input_time = paddle_input.timestamp

    def get_network_state(self) -> NetworkGameState:
        """Get current game state for network sync."""
        return NetworkGameState(
            ball_x=self.ball.x,
            ball_y=self.ball.y,
            ball_vx=self.ball.vx,
            ball_vy=self.ball.vy,
            ball_speed=self.ball.speed,
            left_y=self.left_paddle.y,
            right_y=self.right_paddle.y,
            left_score=self.left_paddle.score,
            right_score=self.right_paddle.score,
            game_over=self.game_over,
            winner=self.winner,
            rally_count=self.rally_count,
            timestamp=time.time(),
            frame_number=self._frame_number,
        )

    def apply_network_state(self, state: NetworkGameState) -> None:
        """Apply game state received from host."""
        self.ball.x = state.ball_x
        self.ball.y = state.ball_y
        self.ball.vx = state.ball_vx
        self.ball.vy = state.ball_vy
        self.ball.speed = state.ball_speed

        self.left_paddle.y = state.left_y
        self.right_paddle.y = state.right_y

        self.left_paddle.score = state.left_score
        self.right_paddle.score = state.right_score

        self.game_over = state.game_over
        self.winner = state.winner
        self.rally_count = state.rally_count

    def update(self, dt: float, human_input: Optional[float] = None) -> None:
        """Update game state with network awareness."""
        self._frame_number += 1

        if self.role == GameRole.HOST:
            # Host runs full physics
            # Remote player controls right paddle
            remote_input = self._remote_input if self._connected else None

            # Apply remote input to right paddle
            if remote_input is not None:
                self.right_paddle.y += remote_input * self.right_paddle.speed
                self.right_paddle.y = max(
                    0, min(self.HEIGHT - self.right_paddle.height, self.right_paddle.y)
                )

            # Run normal update for left paddle (AI) and ball
            super().update(dt, human_input=None)

        else:
            # Client just animates locally, state comes from network
            self._rainbow_offset = (self._rainbow_offset + dt * 0.5) % 1.0

    def render(self) -> "Image":
        """Render with network player labels."""
        if not PIL_AVAILABLE:
            raise RuntimeError("PIL not available")

        # Use parent render
        image = super().render()
        draw = ImageDraw.Draw(image)

        # Override labels with network player names
        if self._font:
            # Clear existing labels area
            draw.rectangle(
                [0, self.HEIGHT - 40, self.WIDTH, self.HEIGHT],
                fill=self.BG_COLOR
            )

            # Left player (host's AI)
            left_label = f"{self.host_persona or 'Host'} (AI)"
            draw.text((20, self.HEIGHT - 35), left_label, font=self._font, fill=self.TEXT_COLOR)

            # Right player (client)
            right_label = self.opponent_persona or self.client_persona or "Remote"
            if self.role == GameRole.HOST:
                right_label = self.opponent_persona or "Waiting..."
            bbox = self._font.getbbox(right_label)
            draw.text(
                (self.WIDTH - 20 - (bbox[2] - bbox[0]), self.HEIGHT - 35),
                right_label,
                font=self._font,
                fill=self.TEXT_COLOR
            )

            # Connection status
            status = "Connected" if self._connected else "Waiting for player..."
            status_color = (100, 255, 100) if self._connected else (255, 200, 100)
            bbox = self._font.getbbox(status)
            draw.text(
                (self.WIDTH // 2 - (bbox[2] - bbox[0]) // 2, 10),
                status,
                font=self._font,
                fill=status_color
            )

        return image

    async def run_host(
        self,
        max_duration: float = 300.0,
        save_path: Optional[str] = None,
    ) -> dict:
        """Run the game as host."""
        if self.role != GameRole.HOST:
            raise RuntimeError("Must be HOST to run_host")

        # Start server
        self.start_hosting()

        # Pause face animator
        face_was_paused = Path("/tmp/brainbot_face_pause").exists()
        if not save_path and not face_was_paused:
            pause_face_animator()

        self.running = True
        start_time = time.time()
        frame_count = 0

        logger.info("Waiting for player to connect...")

        try:
            while self.running and not self.game_over:
                frame_start = time.time()

                if frame_start - start_time > max_duration:
                    logger.info("NetPong: max duration reached")
                    break

                # Update game
                self.update(self.frame_time)

                # Render
                if save_path:
                    self.save_frame(save_path)
                else:
                    self.render_to_framebuffer()

                frame_count += 1

                # Frame timing
                elapsed = time.time() - frame_start
                sleep_time = self.frame_time - elapsed
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

        except KeyboardInterrupt:
            logger.info("NetPong host interrupted")
        finally:
            if self.server:
                self.server.stop()
            if not save_path and not face_was_paused:
                resume_face_animator()

        self.running = False

        return {
            "winner": self.winner,
            "left_score": self.left_paddle.score,
            "right_score": self.right_paddle.score,
            "max_rally": self.max_rally,
            "duration": time.time() - start_time,
            "frames": frame_count,
            "opponent": self.opponent_persona,
        }

    async def run_client(
        self,
        host_address: str,
        max_duration: float = 300.0,
        save_path: Optional[str] = None,
        input_callback: Optional[Callable[[], float]] = None,
    ) -> dict:
        """Run the game as client."""
        if self.role != GameRole.CLIENT:
            raise RuntimeError("Must be CLIENT to run_client")

        # Connect to host
        if not await self.connect_to_host(host_address):
            return {"error": "Failed to connect to host"}

        # Pause face animator
        face_was_paused = Path("/tmp/brainbot_face_pause").exists()
        if not save_path and not face_was_paused:
            pause_face_animator()

        self.running = True
        start_time = time.time()
        frame_count = 0

        try:
            while self.running and not self.game_over:
                frame_start = time.time()

                if frame_start - start_time > max_duration:
                    break

                # Get input (from callback or AI)
                if input_callback:
                    paddle_input = input_callback()
                else:
                    # Simple AI for client
                    paddle_input = self._simple_ai_input()

                # Send input to host
                await self.client.send_input(paddle_input)

                # Get state from host
                state = await self.client.get_game_state()
                if state:
                    self.apply_network_state(state)

                # Local animation
                self.update(self.frame_time)

                # Render
                if save_path:
                    self.save_frame(save_path)
                else:
                    self.render_to_framebuffer()

                frame_count += 1

                # Frame timing (slightly slower for network)
                elapsed = time.time() - frame_start
                sleep_time = (self.frame_time * 1.5) - elapsed
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

        except KeyboardInterrupt:
            logger.info("NetPong client interrupted")
        finally:
            if self.client:
                await self.client.close()
            if not save_path and not face_was_paused:
                resume_face_animator()

        self.running = False

        return {
            "winner": self.winner,
            "left_score": self.left_paddle.score,
            "right_score": self.right_paddle.score,
            "max_rally": self.max_rally,
            "duration": time.time() - start_time,
            "frames": frame_count,
            "host": self.host_persona,
        }

    def _simple_ai_input(self) -> float:
        """Simple AI input for client (tracks ball)."""
        target = self.ball.y
        current = self.right_paddle.center_y()
        diff = target - current

        # Normalize to -1 to 1
        if abs(diff) < 10:
            return 0
        return max(-1, min(1, diff / 50))


async def host_game(
    node_id: str,
    persona: str,
    port: int = 7778,
    max_duration: float = 300.0,
    difficulty: float = 0.7,
) -> dict:
    """
    Host a networked Pong game.

    Args:
        node_id: This node's unique ID
        persona: This node's display name
        port: Port to host on
        max_duration: Maximum game duration
        difficulty: AI difficulty

    Returns:
        Game results
    """
    game = NetPongGame(
        role=GameRole.HOST,
        node_id=node_id,
        persona=persona,
        game_port=port,
        difficulty=difficulty,
    )

    return await game.run_host(max_duration=max_duration)


async def join_game(
    node_id: str,
    persona: str,
    host_address: str,
    port: int = 7778,
    max_duration: float = 300.0,
    input_callback: Optional[Callable[[], float]] = None,
) -> dict:
    """
    Join a networked Pong game.

    Args:
        node_id: This node's unique ID
        persona: This node's display name
        host_address: Address of the host
        port: Port the host is on
        max_duration: Maximum game duration
        input_callback: Optional callback for paddle input

    Returns:
        Game results
    """
    game = NetPongGame(
        role=GameRole.CLIENT,
        node_id=node_id,
        persona=persona,
        game_port=port,
    )

    return await game.run_client(
        host_address=host_address,
        max_duration=max_duration,
        input_callback=input_callback,
    )


def find_game_peers(mesh_node: "MeshNode") -> list[dict]:
    """
    Find peers that can play Pong via the mesh network.

    Args:
        mesh_node: The mesh node to query

    Returns:
        List of peer info dicts
    """
    peers = []
    for peer in mesh_node.peers.get_alive_peers():
        peers.append({
            "node_id": peer.node_id,
            "address": peer.address.split(":")[0],  # Just IP
            "persona": peer.persona_name,
            "hostname": peer.hostname,
        })
    return peers


# CLI entry point
async def main():
    """CLI for testing networked Pong."""
    import argparse
    import uuid

    parser = argparse.ArgumentParser(description="BrainBot NetPong")
    parser.add_argument("--host", action="store_true", help="Host a game")
    parser.add_argument("--join", type=str, help="Join a game at this address")
    parser.add_argument("--port", type=int, default=7778, help="Game port")
    parser.add_argument("--persona", type=str, default="Player", help="Your name")
    parser.add_argument("--duration", type=float, default=300, help="Max duration")
    parser.add_argument("--difficulty", type=float, default=0.7, help="AI difficulty")
    parser.add_argument("--loop", action="store_true", help="Loop games continuously")
    args = parser.parse_args()

    game_number = 0
    while True:
        game_number += 1
        node_id = str(uuid.uuid4())

        if args.host:
            print(f"\n{'='*40}")
            print(f"Game #{game_number}")
            print(f"Hosting NetPong game as {args.persona}")
            print(f"Port: {args.port}")
            print("Waiting for player to connect...")
            print()

            result = await host_game(
                node_id=node_id,
                persona=args.persona,
                port=args.port,
                max_duration=args.duration,
                difficulty=args.difficulty,
            )
        elif args.join:
            print(f"\n{'='*40}")
            print(f"Game #{game_number}")
            print(f"Joining NetPong game at {args.join}")
            print(f"Playing as: {args.persona}")
            print()

            result = await join_game(
                node_id=node_id,
                persona=args.persona,
                host_address=args.join,
                port=args.port,
                max_duration=args.duration,
            )
        else:
            print("Use --host to host a game or --join <address> to join")
            return

        print()
        print("=" * 40)
        print(f"Game Over!")
        print(f"Winner: {result.get('winner', 'Unknown')}")
        print(f"Score: {result.get('left_score', 0)} - {result.get('right_score', 0)}")
        print(f"Max Rally: {result.get('max_rally', 0)}")

        if not args.loop:
            break

        print("\nStarting next game in 3 seconds...")
        await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(main())
