"""
Local LLM inference using llama-cpp-python.

This module provides a singleton wrapper around llama-cpp-python for
efficient model loading and text generation.
"""

import logging
from typing import Optional
from pathlib import Path
from threading import Lock

# Import from existing brain_bot.py LLM dependencies
from llama_cpp import Llama

from config.voice_config import VoiceConfig

logger = logging.getLogger(__name__)

# Friendly system prompt for voice interactions
VOICE_SYSTEM_PROMPT = """You are BrainBot, a friendly and helpful AI assistant.
Keep your responses concise and conversational, perfect for voice interaction.
Be creative, positive, and encouraging. Answer questions clearly and helpfully."""


class LocalLLM:
    """
    Singleton wrapper for llama-cpp-python model inference.

    Provides thread-safe access to a single loaded LLM instance with
    conversation management for voice interactions.

    Attributes:
        config: Voice configuration with model settings
        model: Loaded Llama model instance
        conversation_history: List of (role, content) message tuples

    Example:
        >>> config = VoiceConfig(access_key="key")
        >>> llm = LocalLLM.get_instance(config)
        >>> response = llm.generate("What is the weather?")
        >>> print(response)
    """

    _instance: Optional["LocalLLM"] = None
    _lock: Lock = Lock()

    def __init__(self, config: VoiceConfig) -> None:
        """
        Initialize LLM instance (use get_instance() instead).

        Args:
            config: VoiceConfig with model path and settings

        Raises:
            FileNotFoundError: If model file doesn't exist
        """
        if not config.llama_model_path.exists():
            raise FileNotFoundError(f"LLM model not found: {config.llama_model_path}")

        self.config = config
        self.model: Optional[Llama] = None
        self.conversation_history: list[tuple[str, str]] = []

        # Model will be loaded lazily in load_model()

    @classmethod
    def get_instance(cls, config: Optional[VoiceConfig] = None) -> "LocalLLM":
        """
        Get or create singleton LLM instance.

        Args:
            config: VoiceConfig (required on first call)

        Returns:
            Singleton LocalLLM instance

        Raises:
            ValueError: If config not provided on first call
        """
        if cls._instance is None:
            with cls._lock:
                # Double-check locking pattern
                if cls._instance is None:
                    if config is None:
                        raise ValueError("Config required for first initialization")
                    cls._instance = cls(config)
        return cls._instance

    def load_model(self) -> None:
        """Load the GGUF model into memory."""
        if self.model is not None:
            return  # Already loaded

        logger.info(f"Loading LLM model from {self.config.llama_model_path}...")

        try:
            self.model = Llama(
                model_path=str(self.config.llama_model_path),
                n_ctx=self.config.llama_n_ctx,
                n_threads=self.config.llama_threads,
                n_gpu_layers=0,  # CPU only for Pi
                verbose=False,
                seed=42
            )
            logger.info("LLM model loaded successfully")

        except Exception as e:
            logger.error(f"Error loading LLM model: {e}")
            raise

    def generate(
        self,
        prompt: str,
        max_tokens: int = 256,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None
    ) -> str:
        """
        Generate response to user prompt.

        Args:
            prompt: User input text
            max_tokens: Maximum response length
            temperature: Sampling temperature (0.0-1.0)
            system_prompt: Optional system prompt override

        Returns:
            Generated response text
        """
        if self.model is None:
            self.load_model()

        # Use default system prompt if not provided
        if system_prompt is None:
            system_prompt = VOICE_SYSTEM_PROMPT

        # Build chat-formatted prompt using TinyLlama chat template
        formatted_prompt = f"<|system|>\n{system_prompt}</s>\n"

        # Add conversation history for context
        for role, content in self.conversation_history[-6:]:  # Keep last 3 exchanges
            if role == "user":
                formatted_prompt += f"<|user|>\n{content}</s>\n"
            elif role == "assistant":
                formatted_prompt += f"<|assistant|>\n{content}</s>\n"

        # Add current user message
        formatted_prompt += f"<|user|>\n{prompt}</s>\n<|assistant|>\n"

        logger.debug(f"Generating response for: {prompt}")

        # Generate response
        response = self.model(
            formatted_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=["</s>", "<|user|>"],
            echo=False
        )
        response_text = response['choices'][0]['text'].strip()

        logger.debug(f"Generated response: {response_text}")

        # Update conversation history
        self.conversation_history.append(("user", prompt))
        self.conversation_history.append(("assistant", response_text))

        return response_text

    def generate_streaming(
        self,
        prompt: str,
        max_tokens: int = 256,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None
    ):
        """
        Generate response with streaming output.

        Args:
            prompt: User input text
            max_tokens: Maximum response length
            temperature: Sampling temperature
            system_prompt: Optional system prompt override

        Yields:
            Response text chunks as they are generated
        """
        if self.model is None:
            self.load_model()

        # Use default system prompt if not provided
        if system_prompt is None:
            system_prompt = VOICE_SYSTEM_PROMPT

        # Build chat-formatted prompt (same as generate())
        formatted_prompt = f"<|system|>\n{system_prompt}</s>\n"

        for role, content in self.conversation_history[-6:]:
            if role == "user":
                formatted_prompt += f"<|user|>\n{content}</s>\n"
            elif role == "assistant":
                formatted_prompt += f"<|assistant|>\n{content}</s>\n"

        formatted_prompt += f"<|user|>\n{prompt}</s>\n<|assistant|>\n"

        logger.debug(f"Streaming response for: {prompt}")

        # Generate with streaming
        full_response = ""
        for output in self.model(
            formatted_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=["</s>", "<|user|>"],
            echo=False,
            stream=True
        ):
            chunk = output['choices'][0]['text']
            full_response += chunk
            yield chunk

        # Update conversation history with full response
        self.conversation_history.append(("user", prompt))
        self.conversation_history.append(("assistant", full_response.strip()))

    def reset_conversation(self) -> None:
        """
        Clear conversation history.

        Call this to start a fresh conversation context.
        """
        self.conversation_history.clear()

    def get_conversation_context(self) -> list[tuple[str, str]]:
        """
        Get current conversation history.

        Returns:
            List of (role, content) tuples
        """
        return self.conversation_history.copy()

    def unload_model(self) -> None:
        """Unload model from memory."""
        if self.model is not None:
            del self.model
            self.model = None
            logger.info("LLM model unloaded from memory")

        self.conversation_history.clear()

    @staticmethod
    def estimate_memory_usage(model_path: Path) -> int:
        """
        Estimate memory usage for model in MB.

        Args:
            model_path: Path to GGUF model file

        Returns:
            Estimated RAM usage in megabytes
        """
        if not model_path.exists():
            return 0

        # Get model file size
        file_size_mb = model_path.stat().st_size / (1024 * 1024)

        # Q4_K_M quantized models typically use ~1.3x file size in RAM
        estimated_ram_mb = int(file_size_mb * 1.3)

        return estimated_ram_mb