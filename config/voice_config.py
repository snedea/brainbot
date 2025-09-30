"""
Voice assistant configuration management.

This module provides a centralized configuration dataclass for all voice
assistant components with validation and path expansion.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class VoiceConfig:
    """
    Centralized configuration for offline voice assistant components.

    This dataclass manages all settings for:
    - Porcupine wake word detection
    - Audio capture and VAD
    - whisper.cpp speech-to-text
    - llama-cpp-python LLM inference
    - Piper text-to-speech

    Attributes:
        access_key: Picovoice access key for Porcupine wake word detection
        wake_keywords: Built-in keyword names (e.g., ['porcupine', 'jarvis'])
        wake_keyword_paths: Custom .ppn keyword file paths
        porcupine_sensitivities: Per-keyword detection sensitivity [0.0-1.0]
        audio_device_index: System audio input device (None = default)
        sample_rate: Audio sample rate in Hz (must be 16000 for whisper.cpp)
        frame_length: Porcupine frame size in samples
        vad_aggressiveness: WebRTC VAD aggressiveness level (0-3)
        max_utterance_sec: Maximum recording duration in seconds
        silence_duration_ms: Trailing silence duration to stop recording
        tmp_dir: Temporary directory for audio files
        whisper_bin: Path to whisper.cpp executable
        whisper_model: Path to whisper GGML model file
        llama_model_path: Path to llama model GGUF file
        piper_bin: Path to Piper TTS executable
        piper_voice: Path to Piper voice model file
        llama_n_ctx: LLM context window size
        llama_threads: Number of CPU threads for LLM inference
        piper_rate: TTS output sample rate
        aplay_cmd: Audio playback command
    """

    # Porcupine wake word settings
    access_key: str
    wake_keywords: Optional[list[str]] = None
    wake_keyword_paths: Optional[list[str]] = None
    porcupine_sensitivities: Optional[list[float]] = None

    # Audio settings
    audio_device_index: Optional[int] = None
    sample_rate: int = 16000
    frame_length: int = 512
    chunk_size: int = 1024  # Audio buffer size for recording

    # VAD (Voice Activity Detection) settings
    vad_aggressiveness: int = 2
    max_utterance_sec: int = 15  # Also used as max_recording_sec
    silence_duration_ms: int = 800

    # Recording settings (for amplitude-based silence detection)
    silence_threshold: int = 500  # RMS threshold for silence detection
    silence_duration_sec: float = 2.0  # Seconds of silence to stop recording
    max_recording_sec: int = 30  # Maximum recording duration

    # File paths
    tmp_dir: Path = field(default_factory=lambda: Path('/tmp/brainbot'))
    whisper_bin: Path = field(default_factory=lambda: Path('../whisper.cpp/build/bin/whisper'))
    whisper_model: Path = field(default_factory=lambda: Path('../whisper.cpp/models/ggml-tiny.en.bin'))
    llama_model_path: Path = field(default_factory=lambda: Path('./models/tinyllama-1b.q4_0.gguf'))
    piper_bin: Path = field(default_factory=lambda: Path('~/piper/piper'))
    piper_voice: Path = field(default_factory=lambda: Path('~/piper/en_US-amy-medium.onnx'))

    # LLM settings
    llama_n_ctx: int = 1024
    llama_threads: int = 4

    # TTS settings
    piper_rate: int = 16000
    aplay_cmd: str = 'aplay -q'

    def __post_init__(self) -> None:
        """
        Post-initialization validation and path expansion.

        Creates temporary directory, expands user paths, and sets default
        sensitivities if not provided.
        """
        # Create temporary directory for audio files
        self.tmp_dir = Path(self.tmp_dir)
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

        # Expand user paths for home directory references
        self.whisper_bin = Path(self.whisper_bin).expanduser().resolve()
        self.whisper_model = Path(self.whisper_model).expanduser().resolve()
        self.llama_model_path = Path(self.llama_model_path).expanduser().resolve()
        self.piper_bin = Path(self.piper_bin).expanduser()
        self.piper_voice = Path(self.piper_voice).expanduser()

        # Default sensitivities if not provided
        if self.porcupine_sensitivities is None:
            keyword_count = len(self.wake_keywords or []) + len(self.wake_keyword_paths or [])
            self.porcupine_sensitivities = [0.6] * max(1, keyword_count)

        # Validate sensitivity values
        if self.porcupine_sensitivities:
            for sens in self.porcupine_sensitivities:
                if not 0.0 <= sens <= 1.0:
                    raise ValueError(f"Sensitivity must be in range [0.0, 1.0], got {sens}")

        # Validate VAD aggressiveness
        if not 0 <= self.vad_aggressiveness <= 3:
            raise ValueError(f"VAD aggressiveness must be in range [0, 3], got {self.vad_aggressiveness}")

    def validate_paths(self) -> list[str]:
        """
        Validate that all required files and executables exist.

        Returns:
            List of missing file paths, empty if all paths are valid
        """
        missing = []

        # Check whisper.cpp
        if not self.whisper_bin.exists():
            missing.append(str(self.whisper_bin))
        if not self.whisper_model.exists():
            missing.append(str(self.whisper_model))

        # Check llama model
        if not self.llama_model_path.exists():
            missing.append(str(self.llama_model_path))

        # Check Piper TTS
        if not self.piper_bin.exists():
            missing.append(str(self.piper_bin))
        if not self.piper_voice.exists():
            missing.append(str(self.piper_voice))

        return missing