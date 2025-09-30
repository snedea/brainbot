"""
Voice agent state machine orchestrator.

This module coordinates all voice assistant components in a unified
state machine that handles the complete interaction flow.
"""

import threading
import logging
from enum import Enum, auto
from typing import Optional, Callable
from pathlib import Path

from config.voice_config import VoiceConfig
from voice.wake_listener import WakeWordListener
from voice.recorder import VoiceRecorder
from stt.whisper_cli import WhisperSTT
from llm.llama_local import LocalLLM
from tts.piper_cli import PiperTTS

logger = logging.getLogger(__name__)


class VoiceAgentState(Enum):
    """
    Voice agent state machine states.

    States:
        IDLE: Waiting for wake word
        LISTENING: Recording user speech
        TRANSCRIBING: Converting speech to text
        THINKING: Generating LLM response
        SPEAKING: Playing TTS output
        ERROR: Error state with recovery
        STOPPED: Agent has been stopped
    """
    IDLE = auto()
    LISTENING = auto()
    TRANSCRIBING = auto()
    THINKING = auto()
    SPEAKING = auto()
    ERROR = auto()
    STOPPED = auto()


class VoiceAgent(threading.Thread):
    """
    Main orchestrator for offline voice assistant interactions.

    Coordinates the complete voice interaction pipeline:
    1. IDLE: Wait for wake word
    2. LISTENING: Record user speech with VAD
    3. TRANSCRIBING: Convert speech to text
    4. THINKING: Generate LLM response
    5. SPEAKING: Synthesize and play response
    6. Return to IDLE

    Attributes:
        config: Voice configuration
        state: Current agent state
        wake_listener: Wake word detection thread
        recorder: Speech recorder
        stt: Speech-to-text engine
        llm: Language model
        tts: Text-to-speech engine
        on_state_change: Optional callback for state transitions
        on_transcript: Optional callback for user transcripts
        on_response: Optional callback for LLM responses

    Example:
        >>> config = VoiceConfig(access_key="your-key", wake_keywords=["porcupine"])
        >>> agent = VoiceAgent(config)
        >>> agent.start()
        >>> # Agent now runs continuously
        >>> agent.stop()
    """

    def __init__(
        self,
        config: VoiceConfig,
        on_state_change: Optional[Callable[[VoiceAgentState], None]] = None,
        on_transcript: Optional[Callable[[str], None]] = None,
        on_response: Optional[Callable[[str], None]] = None
    ) -> None:
        """
        Initialize voice agent.

        Args:
            config: VoiceConfig with all component settings
            on_state_change: Callback for state transitions
            on_transcript: Callback when user speech is transcribed
            on_response: Callback when LLM response is generated
        """
        super().__init__(daemon=True)
        self.config = config
        self.state = VoiceAgentState.IDLE
        self.running = False

        # Callbacks
        self.on_state_change = on_state_change
        self.on_transcript = on_transcript
        self.on_response = on_response

        # Component initialization (lazy loading)
        self.wake_listener: Optional[WakeWordListener] = None
        self.recorder: Optional[VoiceRecorder] = None
        self.stt: Optional[WhisperSTT] = None
        self.llm: Optional[LocalLLM] = None
        self.tts: Optional[PiperTTS] = None

        # State tracking
        self._wake_detected = threading.Event()
        self._initialization_complete = threading.Event()
        self._error_message: Optional[str] = None
        self._current_audio_path: Optional[Path] = None
        self._current_transcript: str = ""
        self._current_response: str = ""

    def run(self) -> None:
        """Main agent loop implementing the voice assistant state machine."""
        self.running = True
        self._transition_to(VoiceAgentState.IDLE)

        try:
            # Initialize all components
            self._initialize_components()

            # Main state machine loop
            while self.running:
                if self.state == VoiceAgentState.IDLE:
                    self._handle_idle()
                elif self.state == VoiceAgentState.LISTENING:
                    self._handle_listening()
                elif self.state == VoiceAgentState.TRANSCRIBING:
                    self._handle_transcribing()
                elif self.state == VoiceAgentState.THINKING:
                    self._handle_thinking()
                elif self.state == VoiceAgentState.SPEAKING:
                    self._handle_speaking()
                elif self.state == VoiceAgentState.ERROR:
                    self._handle_error()

        except Exception as e:
            logger.error(f"Fatal error in voice agent: {e}", exc_info=True)
            self._transition_to(VoiceAgentState.ERROR)
            self._error_message = str(e)

        finally:
            self._cleanup()
            self._transition_to(VoiceAgentState.STOPPED)

    def stop(self) -> None:
        """
        Stop the voice agent.

        Sets running flag to False, which will cause the main loop to
        exit and trigger cleanup.
        """
        self.running = False
        if self.wake_listener:
            self.wake_listener.stop()

    def _initialize_components(self) -> None:
        """Initialize all voice assistant components."""
        logger.info("Initializing voice agent components...")

        # Initialize STT
        self.stt = WhisperSTT(self.config)
        logger.info("✓ WhisperSTT initialized")

        # Initialize and load LLM
        self.llm = LocalLLM.get_instance(self.config)
        self.llm.load_model()
        logger.info("✓ LocalLLM initialized and loaded")

        # Initialize TTS
        self.tts = PiperTTS(self.config)
        logger.info("✓ PiperTTS initialized")

        # Initialize recorder
        self.recorder = VoiceRecorder(self.config)
        logger.info("✓ VoiceRecorder initialized")

        # Initialize and start wake word listener
        self.wake_listener = WakeWordListener(
            self.config,
            self._on_wake_detected
        )
        self.wake_listener.start()
        logger.info("✓ WakeWordListener started")

        logger.info("All components initialized successfully")

        # Signal that initialization is complete
        self._initialization_complete.set()

    def _handle_idle(self) -> None:
        """Handle IDLE state - wait for wake word."""
        logger.debug("Waiting for wake word...")
        self._wake_detected.wait()
        self._wake_detected.clear()
        self._transition_to(VoiceAgentState.LISTENING)

    def _handle_listening(self) -> None:
        """Handle LISTENING state - record user speech."""
        logger.info("Listening for user speech...")
        try:
            audio_path = self.recorder.record_utterance()
            self._current_audio_path = audio_path
            self._transition_to(VoiceAgentState.TRANSCRIBING)
        except Exception as e:
            logger.error(f"Recording failed: {e}")
            self._error_message = f"Recording error: {e}"
            self._transition_to(VoiceAgentState.ERROR)

    def _handle_transcribing(self) -> None:
        """Handle TRANSCRIBING state - convert speech to text."""
        logger.info("Transcribing speech...")
        try:
            result = self.stt.transcribe(self._current_audio_path)

            if not result.success:
                logger.error(f"Transcription failed: {result.error}")
                self._error_message = result.error
                self._transition_to(VoiceAgentState.ERROR)
                return

            self._current_transcript = result.text
            logger.info(f"Transcript: {result.text}")

            if self.on_transcript:
                self.on_transcript(result.text)

            self._transition_to(VoiceAgentState.THINKING)

        except Exception as e:
            logger.error(f"Transcription error: {e}")
            self._error_message = f"Transcription error: {e}"
            self._transition_to(VoiceAgentState.ERROR)

    def _handle_thinking(self) -> None:
        """Handle THINKING state - generate LLM response."""
        logger.info("Generating response...")
        try:
            response = self.llm.generate(self._current_transcript)
            self._current_response = response
            logger.info(f"Response: {response}")

            if self.on_response:
                self.on_response(response)

            self._transition_to(VoiceAgentState.SPEAKING)

        except Exception as e:
            logger.error(f"LLM generation error: {e}")
            self._error_message = f"LLM error: {e}"
            self._transition_to(VoiceAgentState.ERROR)

    def _handle_speaking(self) -> None:
        """Handle SPEAKING state - synthesize and play response."""
        logger.info("Speaking response...")
        try:
            success = self.tts.speak(self._current_response, blocking=True)

            if not success:
                logger.error("TTS playback failed")
                self._error_message = "TTS playback failed"
                self._transition_to(VoiceAgentState.ERROR)
                return

            # Clean up temp audio files
            if self._current_audio_path and self._current_audio_path.exists():
                self._current_audio_path.unlink(missing_ok=True)

            self._transition_to(VoiceAgentState.IDLE)

        except Exception as e:
            logger.error(f"TTS error: {e}")
            self._error_message = f"TTS error: {e}"
            self._transition_to(VoiceAgentState.ERROR)

    def _handle_error(self) -> None:
        """Handle ERROR state - log error and attempt recovery."""
        logger.error(f"Voice agent error: {self._error_message}")

        # Keep audio file for debugging if transcription failed
        if self._current_audio_path and self._current_audio_path.exists():
            if "Transcription" in str(self._error_message):
                logger.error(f"Audio file saved for debugging: {self._current_audio_path}")
                logger.error(f"Test manually with: {self.config.whisper_bin} -m {self.config.whisper_model} -f {self._current_audio_path}")
            else:
                # Clean up for other errors
                self._current_audio_path.unlink(missing_ok=True)

        # Try to recover by returning to IDLE
        self._error_message = None
        self._transition_to(VoiceAgentState.IDLE)

    def _on_wake_detected(self) -> None:
        """
        Callback for wake word detection.

        Signals the main loop that wake word was detected.
        """
        self._wake_detected.set()

    def _transition_to(self, new_state: VoiceAgentState) -> None:
        """
        Transition to new state with callback notification.

        Args:
            new_state: Target state to transition to
        """
        old_state = self.state
        self.state = new_state

        logger.info(f"State transition: {old_state.name} → {new_state.name}")

        if self.on_state_change:
            self.on_state_change(new_state)

    def _cleanup(self) -> None:
        """Clean up all resources."""
        logger.info("Cleaning up voice agent...")

        # Stop wake listener
        if self.wake_listener:
            self.wake_listener.stop()
            logger.info("✓ Wake listener stopped")

        # Close recorder
        if self.recorder:
            self.recorder.close()
            logger.info("✓ Recorder closed")

        # Clean up temp directory
        try:
            for temp_file in self.config.tmp_dir.glob("*.wav"):
                temp_file.unlink(missing_ok=True)
            logger.info("✓ Temp files cleaned up")
        except Exception as e:
            logger.warning(f"Error cleaning temp files: {e}")

        logger.info("Voice agent cleanup complete")

    def get_state(self) -> VoiceAgentState:
        """
        Get current agent state.

        Returns:
            Current VoiceAgentState
        """
        return self.state

    def is_running(self) -> bool:
        """
        Check if agent is running.

        Returns:
            True if agent is running, False otherwise
        """
        return self.running and self.state != VoiceAgentState.STOPPED

    def wait_for_initialization(self, timeout: float = 30.0) -> bool:
        """
        Wait for voice agent initialization to complete.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            True if initialization completed, False if timeout
        """
        return self._initialization_complete.wait(timeout=timeout)