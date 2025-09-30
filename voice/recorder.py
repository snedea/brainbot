"""
Voice activity detection and speech recording.

This module provides simple recording that captures user speech after
wake word detection, automatically stopping when silence is detected.
"""

import wave
import time
import logging
from pathlib import Path
from typing import Optional
import struct
import audioop

import pyaudio

from config.voice_config import VoiceConfig

logger = logging.getLogger(__name__)


class VoiceRecorder:
    """
    Simple speech recorder with automatic silence detection.

    Uses amplitude-based silence detection to automatically stop recording
    after silence is detected. Outputs 16kHz mono WAV files compatible
    with whisper.cpp.

    Attributes:
        config: Voice configuration with audio settings
        audio: PyAudio instance for audio capture
        stream: Active audio input stream

    Example:
        >>> config = VoiceConfig(access_key="key")
        >>> recorder = VoiceRecorder(config)
        >>> wav_path = recorder.record_utterance()
        >>> print(f"Recorded to: {wav_path}")
        >>> recorder.close()
    """

    def __init__(self, config: VoiceConfig) -> None:
        """
        Initialize voice recorder.

        Args:
            config: VoiceConfig with audio device settings
        """
        self.config = config

        # Audio capture (initialized in _open_stream())
        self.audio: Optional[pyaudio.PyAudio] = None
        self.stream: Optional[pyaudio.Stream] = None

        # Recording state
        self._is_recording = False

    def _open_stream(self) -> None:
        """Open audio input stream for 16kHz mono recording."""
        self.audio = pyaudio.PyAudio()

        # Build audio stream parameters
        stream_params = {
            'format': pyaudio.paInt16,
            'channels': 1,
            'rate': self.config.sample_rate,
            'input': True,
            'frames_per_buffer': self.config.chunk_size
        }

        # Add device index if specified
        if self.config.audio_device_index is not None:
            stream_params['input_device_index'] = self.config.audio_device_index
            logger.info(f"Using audio device index: {self.config.audio_device_index}")

        self.stream = self.audio.open(**stream_params)
        logger.info(f"Opened audio stream at {self.config.sample_rate}Hz")

    def record_utterance(self, output_path: Optional[Path] = None) -> Path:
        """
        Record a single user utterance with automatic silence detection.

        Captures audio until either:
        1. Silence detected for config.silence_duration_sec
        2. Maximum duration (config.max_recording_sec) reached

        Args:
            output_path: Optional output file path (auto-generated if None)

        Returns:
            Path to recorded WAV file (16kHz mono)
        """
        if output_path is None:
            # Generate timestamped filename
            timestamp = int(time.time())
            output_path = self.config.tmp_dir / f"utterance_{timestamp}.wav"

        # Ensure stream is open
        if self.stream is None:
            self._open_stream()

        logger.info("Recording started...")
        frames = []
        silent_chunks = 0
        start_time = time.time()
        last_log_time = start_time

        # Minimum recording duration before silence detection activates (seconds)
        MIN_RECORDING_SEC = 1.5

        # Calculate how many silent chunks = silence threshold
        chunks_per_second = self.config.sample_rate / self.config.chunk_size
        silence_threshold_chunks = int(self.config.silence_duration_sec * chunks_per_second)

        # Track RMS values for debugging
        rms_values = []

        try:
            while True:
                # Read audio chunk
                data = self.stream.read(self.config.chunk_size, exception_on_overflow=False)
                frames.append(data)

                # Calculate RMS (root mean square) to detect silence
                rms = audioop.rms(data, 2)  # 2 bytes per sample (16-bit)
                rms_values.append(rms)

                # Log RMS values periodically (every second)
                elapsed = time.time() - start_time
                if elapsed - (last_log_time - start_time) >= 1.0:
                    avg_rms = sum(rms_values[-int(chunks_per_second):]) / min(len(rms_values), int(chunks_per_second))
                    logger.info(f"Recording... {elapsed:.1f}s (RMS: {int(avg_rms)}, threshold: {self.config.silence_threshold})")
                    last_log_time = time.time()

                # Only check for silence after minimum recording duration
                if elapsed >= MIN_RECORDING_SEC:
                    # Check if chunk is silent
                    if rms < self.config.silence_threshold:
                        silent_chunks += 1
                    else:
                        silent_chunks = 0

                    # Stop if silence detected
                    if silent_chunks > silence_threshold_chunks:
                        logger.info(f"Silence detected after {elapsed:.1f}s")
                        break

                # Stop if max duration reached
                if elapsed > self.config.max_recording_sec:
                    logger.info(f"Max recording duration reached ({self.config.max_recording_sec}s)")
                    break

        except Exception as e:
            logger.error(f"Recording error: {e}")
            raise

        # Save to WAV file
        self._save_wav(frames, output_path)
        logger.info(f"Recording saved to {output_path}")

        return output_path

    def _save_wav(self, frames: list[bytes], output_path: Path) -> None:
        """
        Save recorded frames to WAV file.

        Args:
            frames: List of PCM audio frames
            output_path: Output WAV file path
        """
        with wave.open(str(output_path), 'wb') as wf:
            wf.setnchannels(1)  # Mono
            wf.setsampwidth(2)  # 16-bit = 2 bytes
            wf.setframerate(self.config.sample_rate)
            wf.writeframes(b''.join(frames))

    def close(self) -> None:
        """Close audio stream and cleanup resources."""
        if self.stream is not None:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None

        if self.audio is not None:
            self.audio.terminate()
            self.audio = None

        logger.info("Voice recorder closed")

    def __enter__(self) -> "VoiceRecorder":
        """Context manager entry."""
        self._open_stream()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit with cleanup."""
        self.close()