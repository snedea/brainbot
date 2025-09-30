"""
Configuration module for BrainBot voice assistant.

This module provides centralized configuration management for all voice
assistant components including wake word detection, speech recognition,
LLM inference, and text-to-speech.
"""

from .voice_config import VoiceConfig

# Try to import env_loader (requires python-dotenv)
try:
    from .env_loader import load_voice_config, check_voice_mode_ready
    ENV_LOADER_AVAILABLE = True
except ImportError:
    # python-dotenv not installed
    ENV_LOADER_AVAILABLE = False
    load_voice_config = None
    check_voice_mode_ready = None

__all__ = [
    "VoiceConfig",
    "load_voice_config",
    "check_voice_mode_ready",
    "ENV_LOADER_AVAILABLE"
]