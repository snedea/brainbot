"""
Offline speech-to-text using whisper.cpp.

This module provides a wrapper around the whisper.cpp command-line tool
for fast, accurate speech recognition on Raspberry Pi.
"""

import subprocess
import json
import logging
import wave
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from config.voice_config import VoiceConfig

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionResult:
    """
    Result from whisper.cpp transcription.

    Attributes:
        text: Transcribed text content
        language: Detected language code
        duration_sec: Audio duration in seconds
        success: Whether transcription succeeded
        error: Error message if transcription failed
    """
    text: str
    language: str = "en"
    duration_sec: float = 0.0
    success: bool = True
    error: Optional[str] = None


class WhisperSTT:
    """
    Wrapper for whisper.cpp command-line speech recognition.

    Provides offline speech-to-text using the whisper.cpp binary with
    GGML models for efficient inference on ARM devices.

    Attributes:
        config: Voice configuration with whisper paths

    Example:
        >>> config = VoiceConfig(access_key="key")
        >>> stt = WhisperSTT(config)
        >>> result = stt.transcribe("audio.wav")
        >>> if result.success:
        ...     print(result.text)
    """

    def __init__(self, config: VoiceConfig) -> None:
        """
        Initialize WhisperSTT wrapper.

        Args:
            config: VoiceConfig with whisper binary and model paths

        Raises:
            FileNotFoundError: If whisper binary or model doesn't exist
        """
        self.config = config

        # Validate paths exist
        if not self.config.whisper_bin.exists():
            raise FileNotFoundError(f"whisper.cpp binary not found: {self.config.whisper_bin}")
        if not self.config.whisper_model.exists():
            raise FileNotFoundError(f"Whisper model not found: {self.config.whisper_model}")

    def transcribe(self, audio_path: Path, language: str = "en") -> TranscriptionResult:
        """
        Transcribe audio file to text using whisper.cpp.

        Args:
            audio_path: Path to 16kHz mono WAV file
            language: Language hint for transcription (default: "en")

        Returns:
            TranscriptionResult with transcribed text or error
        """
        if not audio_path.exists():
            return TranscriptionResult(
                text="",
                success=False,
                error=f"Audio file not found: {audio_path}"
            )

        logger.info(f"Transcribing {audio_path}...")

        try:
            # Build whisper.cpp command
            cmd = [
                str(self.config.whisper_bin),
                "-m", str(self.config.whisper_model),
                "-l", language,
                "-t", str(self.config.llama_threads),
                "-f", str(audio_path),
                "--output-txt",
                "--no-timestamps"
            ]

            logger.debug(f"Running: {' '.join(cmd)}")

            # Execute subprocess
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
                cwd=str(audio_path.parent)  # Run in same dir as audio file
            )

            # whisper.cpp writes output to <audio_path>.txt
            output_file = audio_path.with_suffix(audio_path.suffix + '.txt')
            if not output_file.exists():
                # Try alternate name pattern
                output_file = audio_path.parent / (audio_path.stem + ".txt")

            if output_file.exists():
                with open(output_file, 'r') as f:
                    text = f.read().strip()

                # Clean up output file
                output_file.unlink()

                logger.info(f"Transcription: '{text}'")

                return TranscriptionResult(
                    text=text,
                    language=language,
                    success=True
                )
            else:
                # Try to get text from stdout
                text = result.stdout.strip()
                if text:
                    logger.info(f"Transcription from stdout: '{text}'")
                    return TranscriptionResult(text=text, language=language, success=True)
                else:
                    return TranscriptionResult(
                        text="",
                        success=False,
                        error="No transcription output found"
                    )

        except subprocess.TimeoutExpired:
            return TranscriptionResult(
                text="",
                success=False,
                error="Transcription timed out after 30 seconds"
            )
        except subprocess.CalledProcessError as e:
            return TranscriptionResult(
                text="",
                success=False,
                error=f"Transcription failed: {e.stderr}"
            )
        except Exception as e:
            return TranscriptionResult(
                text="",
                success=False,
                error=f"Unexpected error: {str(e)}"
            )

    @staticmethod
    def validate_audio_format(audio_path: Path) -> tuple[bool, str]:
        """
        Validate that audio file meets whisper.cpp requirements.

        Args:
            audio_path: Path to audio file

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            with wave.open(str(audio_path), 'rb') as wf:
                channels = wf.getnchannels()
                sample_width = wf.getsampwidth()
                framerate = wf.getframerate()

                if channels != 1:
                    return False, f"Must be mono (1 channel), got {channels}"
                if sample_width != 2:
                    return False, f"Must be 16-bit (2 bytes), got {sample_width}"
                if framerate != 16000:
                    return False, f"Must be 16kHz, got {framerate}Hz"

            return True, ""
        except Exception as e:
            return False, str(e)