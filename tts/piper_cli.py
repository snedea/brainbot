"""
Offline text-to-speech using Piper.

This module provides a wrapper around the Piper TTS command-line tool
for high-quality offline speech synthesis.
"""

import subprocess
import logging
import time
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from config.voice_config import VoiceConfig

logger = logging.getLogger(__name__)


@dataclass
class TTSResult:
    """
    Result from Piper TTS synthesis.

    Attributes:
        audio_path: Path to generated audio file
        duration_sec: Audio duration in seconds
        success: Whether synthesis succeeded
        error: Error message if synthesis failed
    """
    audio_path: Optional[Path] = None
    duration_sec: float = 0.0
    success: bool = True
    error: Optional[str] = None


class PiperTTS:
    """
    Wrapper for Piper TTS command-line speech synthesis.

    Provides offline text-to-speech using Piper with ONNX voice models
    for natural-sounding speech output.

    Attributes:
        config: Voice configuration with Piper paths

    Example:
        >>> config = VoiceConfig(access_key="key")
        >>> tts = PiperTTS(config)
        >>> tts.speak("Hello, I am BrainBot!")
        >>> # Or save to file
        >>> result = tts.synthesize("Hello world", "output.wav")
    """

    def __init__(self, config: VoiceConfig) -> None:
        """
        Initialize PiperTTS wrapper.

        Args:
            config: VoiceConfig with Piper binary and voice model paths

        Raises:
            FileNotFoundError: If Piper binary or voice model doesn't exist
        """
        self.config = config

        # Validate paths exist
        if not self.config.piper_bin.exists():
            raise FileNotFoundError(f"Piper binary not found: {self.config.piper_bin}")
        if not self.config.piper_voice.exists():
            raise FileNotFoundError(f"Piper voice model not found: {self.config.piper_voice}")

    def synthesize(
        self,
        text: str,
        output_path: Optional[Path] = None
    ) -> TTSResult:
        """
        Synthesize speech from text and save to file.

        Args:
            text: Text to synthesize
            output_path: Output WAV file path (auto-generated if None)

        Returns:
            TTSResult with audio path or error
        """
        if not text or not text.strip():
            return TTSResult(
                success=False,
                error="Empty text provided"
            )

        # Generate output path if not provided
        if output_path is None:
            timestamp = int(time.time())
            output_path = self.config.tmp_dir / f"tts_{timestamp}.wav"

        logger.info(f"Synthesizing: {text[:50]}...")

        try:
            # Build Piper command
            cmd = [
                str(self.config.piper_bin),
                "-m", str(self.config.piper_voice),
                "-f", str(output_path)
            ]

            logger.debug(f"Running: {' '.join(cmd)}")

            # Execute subprocess with text as stdin
            result = subprocess.run(
                cmd,
                input=text,
                text=True,
                capture_output=True,
                check=True,
                timeout=30
            )

            if output_path.exists():
                logger.info(f"TTS saved to {output_path}")
                return TTSResult(
                    audio_path=output_path,
                    duration_sec=self.estimate_audio_duration(text),
                    success=True
                )
            else:
                return TTSResult(
                    success=False,
                    error="Output file not created"
                )

        except subprocess.TimeoutExpired:
            return TTSResult(
                success=False,
                error="TTS synthesis timed out after 30 seconds"
            )
        except subprocess.CalledProcessError as e:
            return TTSResult(
                success=False,
                error=f"TTS synthesis failed: {e.stderr}"
            )
        except Exception as e:
            return TTSResult(
                success=False,
                error=f"Unexpected error: {str(e)}"
            )

    def speak(self, text: str, blocking: bool = True) -> bool:
        """
        Synthesize and play speech immediately.

        Args:
            text: Text to speak
            blocking: Wait for playback to complete (default: True)

        Returns:
            True if successful, False otherwise
        """
        result = self.synthesize(text)

        if not result.success or result.audio_path is None:
            logger.error(f"Synthesis failed: {result.error}")
            return False

        try:
            # Play audio file using aplay
            cmd = self.config.aplay_cmd.split() + [str(result.audio_path)]

            if blocking:
                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                # Clean up temp file after playback
                result.audio_path.unlink(missing_ok=True)
            else:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            logger.info("Audio playback started")
            return True

        except Exception as e:
            logger.error(f"Error playing audio: {e}")
            return False

    def speak_streaming(self, text: str) -> bool:
        """
        Synthesize and stream audio for lower latency.

        Args:
            text: Text to speak

        Returns:
            True if successful, False otherwise
        """
        try:
            # Build Piper and aplay commands
            piper_cmd = [
                str(self.config.piper_bin),
                "-m", str(self.config.piper_voice),
                "--output_raw"  # Output raw PCM for streaming
            ]
            aplay_cmd = self.config.aplay_cmd.split()

            logger.debug(f"Streaming: {text[:50]}...")

            # Pipe Piper stdout to aplay stdin
            piper_proc = subprocess.Popen(
                piper_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL
            )
            aplay_proc = subprocess.Popen(
                aplay_cmd,
                stdin=piper_proc.stdout,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            # Write text to Piper
            if piper_proc.stdin:
                piper_proc.stdin.write(text.encode())
                piper_proc.stdin.close()

            # Wait for completion
            aplay_proc.wait()
            piper_proc.wait()

            logger.info("Streaming TTS completed")
            return True

        except Exception as e:
            logger.error(f"Error in streaming TTS: {e}")
            return False

    @staticmethod
    def estimate_audio_duration(text: str, words_per_minute: int = 150) -> float:
        """
        Estimate audio duration from text length.

        Args:
            text: Text to estimate
            words_per_minute: Average speaking rate

        Returns:
            Estimated duration in seconds
        """
        word_count = len(text.split())
        minutes = word_count / words_per_minute
        return minutes * 60.0

    @staticmethod
    def list_available_voices(piper_bin: Path) -> list[str]:
        """
        List available Piper voice models.

        Args:
            piper_bin: Path to Piper executable

        Returns:
            List of available voice model names
        """
        # Search for .onnx files in Piper directory
        if not piper_bin.exists():
            return []

        piper_dir = piper_bin.parent
        voices = []

        for onnx_file in piper_dir.rglob("*.onnx"):
            voices.append(onnx_file.stem)

        return voices