#!/usr/bin/env python3
"""
Run dual llama.cpp servers for generation and moderation.
"""

import os
import sys
import subprocess
import time
import signal
import requests
from pathlib import Path
from typing import Optional, List


# Configuration
GEN_PORT = int(os.environ.get("GEN_PORT", "8080"))
MOD_PORT = int(os.environ.get("MOD_PORT", "8081"))
GEN_MODEL = Path("models/generation/model.gguf")
MOD_MODEL = Path("models/moderation/guard.gguf")

# Find llama-server executable
LLAMA_SERVER_PATHS = [
    "llama-server",  # In PATH
    "./llama-server",  # Current directory
    "../llama.cpp/llama-server",  # Parent directory
    "~/llama.cpp/llama-server",  # Home directory
]


def find_llama_server() -> Optional[str]:
    """Find llama-server executable."""
    for path in LLAMA_SERVER_PATHS:
        expanded = os.path.expanduser(path)
        if os.path.isfile(expanded) or subprocess.run(
            ["which", path], capture_output=True
        ).returncode == 0:
            return path
    return None


def check_model_files() -> bool:
    """Check if model files exist."""
    if not GEN_MODEL.exists():
        print(f"❌ Generation model not found: {GEN_MODEL}")
        print("   Run: bash scripts/setup_models.sh")
        return False

    if not MOD_MODEL.exists():
        print(f"❌ Moderation model not found: {MOD_MODEL}")
        print("   Run: bash scripts/setup_models.sh")
        return False

    print(f"✅ Generation model: {GEN_MODEL}")
    print(f"✅ Moderation model: {MOD_MODEL}")
    return True


def health_check(port: int, name: str, max_retries: int = 30) -> bool:
    """Check if server is healthy."""
    url = f"http://localhost:{port}/health"

    for i in range(max_retries):
        try:
            response = requests.get(url, timeout=1)
            if response.status_code == 200:
                print(f"✅ {name} server healthy on port {port}")
                return True
        except requests.RequestException:
            pass

        if i < max_retries - 1:
            print(f"⏳ Waiting for {name} server... ({i+1}/{max_retries})")
            time.sleep(2)

    print(f"❌ {name} server failed to start on port {port}")
    return False


class DualModelServer:
    """Manages two llama.cpp server processes."""

    def __init__(self):
        self.llama_server = find_llama_server()
        if not self.llama_server:
            print("❌ llama-server not found. Please install llama.cpp")
            sys.exit(1)

        self.gen_process: Optional[subprocess.Popen] = None
        self.mod_process: Optional[subprocess.Popen] = None

    def start_generation_server(self) -> bool:
        """Start generation model server."""
        cmd = [
            self.llama_server,
            "--model", str(GEN_MODEL),
            "--port", str(GEN_PORT),
            "--ctx-size", "2048",
            "--n-gpu-layers", "0",  # CPU only for compatibility
            "--threads", "4",
            "--temp", "0.4",  # Conservative temperature
            "--top-p", "0.8",
            "--repeat-penalty", "1.1",
            "--no-mmap",  # Better for some systems
        ]

        print(f"🚀 Starting generation server on port {GEN_PORT}...")
        self.gen_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        return health_check(GEN_PORT, "Generation")

    def start_moderation_server(self) -> bool:
        """Start moderation model server."""
        cmd = [
            self.llama_server,
            "--model", str(MOD_MODEL),
            "--port", str(MOD_PORT),
            "--ctx-size", "1024",  # Smaller context for classification
            "--n-gpu-layers", "0",  # CPU only
            "--threads", "2",  # Fewer threads for guard
            "--temp", "0.0",  # Deterministic
            "--top-p", "0.1",  # Very conservative
            "--seed", "42",  # Fixed seed
            "--no-mmap",
        ]

        print(f"🚀 Starting moderation server on port {MOD_PORT}...")
        self.mod_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        return health_check(MOD_PORT, "Moderation")

    def start_all(self) -> bool:
        """Start both servers."""
        if not check_model_files():
            return False

        print("\n" + "="*50)
        print("Starting BrainBot Dual-Model System")
        print("="*50 + "\n")

        # Start generation server
        if not self.start_generation_server():
            self.shutdown()
            return False

        # Start moderation server
        if not self.start_moderation_server():
            self.shutdown()
            return False

        print("\n" + "="*50)
        print("✅ Both servers running successfully!")
        print(f"   Generation: http://localhost:{GEN_PORT}")
        print(f"   Moderation: http://localhost:{MOD_PORT}")
        print("="*50 + "\n")
        print("Press Ctrl+C to stop servers...")

        return True

    def shutdown(self):
        """Shutdown both servers."""
        print("\n🛑 Shutting down servers...")

        if self.gen_process:
            self.gen_process.terminate()
            try:
                self.gen_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.gen_process.kill()
            print("   Generation server stopped")

        if self.mod_process:
            self.mod_process.terminate()
            try:
                self.mod_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.mod_process.kill()
            print("   Moderation server stopped")

    def run(self):
        """Run servers and wait for interrupt."""
        if not self.start_all():
            sys.exit(1)

        # Handle shutdown signals
        def signal_handler(sig, frame):
            self.shutdown()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Keep running
        try:
            while True:
                # Check if processes are still running
                if self.gen_process and self.gen_process.poll() is not None:
                    print("⚠️  Generation server crashed!")
                    break
                if self.mod_process and self.mod_process.poll() is not None:
                    print("⚠️  Moderation server crashed!")
                    break
                time.sleep(5)
        except KeyboardInterrupt:
            pass
        finally:
            self.shutdown()


def main():
    """Main entry point."""
    server = DualModelServer()
    server.run()


if __name__ == "__main__":
    main()