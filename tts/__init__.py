"""
Text-to-speech module for BrainBot.

This module provides offline speech synthesis using Piper TTS.
"""

from .piper_cli import PiperTTS

__all__ = ["PiperTTS"]