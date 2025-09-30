"""
Speech-to-text module for BrainBot.

This module provides offline speech recognition using whisper.cpp.
"""

from .whisper_cli import WhisperSTT

__all__ = ["WhisperSTT"]