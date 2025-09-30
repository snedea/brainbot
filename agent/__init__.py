"""
Voice agent orchestration module for BrainBot.

This module provides the main state machine that coordinates wake word
detection, speech recording, transcription, LLM inference, and TTS output.
"""

from .voice_agent import VoiceAgent, VoiceAgentState

__all__ = ["VoiceAgent", "VoiceAgentState"]