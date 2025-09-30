"""
Local LLM inference module for BrainBot.

This module provides offline language model inference using llama-cpp-python.
"""

from .llama_local import LocalLLM

__all__ = ["LocalLLM"]