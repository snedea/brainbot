"""
Wake word detection using Porcupine and PyAudio.

This module provides a thread-based wake word listener that continuously
monitors audio input for the configured wake word (e.g., "Hey Computer").
"""

import threading
import logging
from typing import Callable, Optional
import struct

import pvporcupine
import pyaudio

from config.voice_config import VoiceConfig

logger = logging.getLogger(__name__)


class WakeWordListener(threading.Thread):
    """
    Background thread for continuous wake word detection.

    Uses Porcupine for efficient wake word detection with PyAudio for
    cross-platform audio capture. Runs until explicitly stopped.

    Attributes:
        config: Voice configuration with Porcupine settings
        on_wake: Callback function invoked when wake word is detected
        running: Thread running state flag
        porcupine: Porcupine wake word engine instance
        audio_stream: PyAudio stream instance
        pyaudio: PyAudio instance

    Example:
        >>> config = VoiceConfig(access_key="your-key")
        >>> def handle_wake():
        ...     print("Wake word detected!")
        >>> listener = WakeWordListener(config, handle_wake)
        >>> listener.start()
        >>> # ... do other work ...
        >>> listener.stop()
    """

    def __init__(self, config: VoiceConfig, on_wake: Callable[[], None]) -> None:
        """
        Initialize wake word listener thread.

        Args:
            config: VoiceConfig with Porcupine settings and audio device
            on_wake: Callback function to invoke when wake word is detected
        """
        super().__init__(daemon=True)
        self.config = config
        self.on_wake = on_wake
        self.running = False

        # Porcupine engine and audio (initialized in run())
        self.porcupine: Optional[pvporcupine.Porcupine] = None
        self.audio_stream: Optional[pyaudio.Stream] = None
        self.pyaudio_instance: Optional[pyaudio.PyAudio] = None

    def run(self) -> None:
        """
        Main thread loop for wake word detection.

        Initializes Porcupine and PyAudio, then continuously reads audio
        frames and processes them for wake word detection. Runs until stop()
        is called.
        """
        self.running = True

        try:
            # Initialize Porcupine with "computer" keyword
            self.porcupine = pvporcupine.create(
                access_key=self.config.access_key,
                keywords=self.config.wake_keywords,
                sensitivities=self.config.porcupine_sensitivities
            )

            # Initialize PyAudio
            self.pyaudio_instance = pyaudio.PyAudio()

            # Build audio stream parameters
            stream_params = {
                'rate': self.porcupine.sample_rate,
                'channels': 1,
                'format': pyaudio.paInt16,
                'input': True,
                'frames_per_buffer': self.porcupine.frame_length
            }

            # Add device index if specified
            if self.config.audio_device_index is not None:
                stream_params['input_device_index'] = self.config.audio_device_index
                logger.info(f"Using audio device index: {self.config.audio_device_index}")

            # Open audio stream
            self.audio_stream = self.pyaudio_instance.open(**stream_params)

            logger.info(f"Listening for wake words: {self.config.wake_keywords}")

            # Main detection loop
            while self.running:
                # Read audio frame
                pcm_data = self.audio_stream.read(
                    self.porcupine.frame_length,
                    exception_on_overflow=False
                )

                # Convert to PCM array
                pcm = struct.unpack_from("h" * self.porcupine.frame_length, pcm_data)

                # Process with Porcupine
                keyword_index = self.porcupine.process(pcm)

                if keyword_index >= 0:
                    detected_keyword = self.config.wake_keywords[keyword_index]
                    logger.info(f"Wake word detected: '{detected_keyword}'")
                    self.on_wake()

        except Exception as e:
            logger.error(f"Error in wake word listener: {e}")
            raise

        finally:
            self._cleanup()

    def stop(self) -> None:
        """
        Stop the wake word listener thread.

        Sets the running flag to False, which will cause the main loop to
        exit and trigger cleanup.
        """
        self.running = False

    def _cleanup(self) -> None:
        """Clean up Porcupine and PyAudio resources."""
        if self.audio_stream is not None:
            self.audio_stream.stop_stream()
            self.audio_stream.close()
            self.audio_stream = None

        if self.pyaudio_instance is not None:
            self.pyaudio_instance.terminate()
            self.pyaudio_instance = None

        if self.porcupine is not None:
            self.porcupine.delete()
            self.porcupine = None

        logger.info("Wake word listener cleaned up")

    @staticmethod
    def list_audio_devices() -> list[tuple[int, str]]:
        """
        List available audio input devices.

        Returns:
            List of (device_index, device_name) tuples
        """
        pa = pyaudio.PyAudio()
        devices = []

        try:
            for i in range(pa.get_device_count()):
                info = pa.get_device_info_by_index(i)
                if info['maxInputChannels'] > 0:
                    devices.append((i, info['name']))
        finally:
            pa.terminate()

        return devices