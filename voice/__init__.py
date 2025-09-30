"""
Voice input module for BrainBot.

This module handles wake word detection and speech recording using
Porcupine and WebRTC VAD.
"""

from .wake_listener import WakeWordListener
from .recorder import VoiceRecorder

__all__ = ["WakeWordListener", "VoiceRecorder"]