"""BrainBot watchdog thread for monitoring daemon health."""

import io
import logging
import os
import signal
import threading
import time
from typing import Callable, Optional

try:
    import faulthandler
    FAULTHANDLER_AVAILABLE = True
except ImportError:
    FAULTHANDLER_AVAILABLE = False

logger = logging.getLogger(__name__)


class Watchdog:
    """
    External watchdog thread that monitors daemon health.

    Runs in a separate thread to detect if the main loop hangs.
    Can trigger recovery actions if the daemon becomes unresponsive.
    """

    def __init__(
        self,
        heartbeat_getter: Callable[[], float],
        log_dir: Optional[str] = None,
        warning_threshold: float = 60.0,
        critical_threshold: float = 120.0,
        check_interval: float = 10.0,
        on_critical: Optional[Callable[[], None]] = None,
    ):
        """
        Initialize watchdog.

        Args:
            heartbeat_getter: Callable that returns the timestamp of the last heartbeat
            log_dir: Directory for thread dump files
            warning_threshold: Seconds without heartbeat before warning
            critical_threshold: Seconds without heartbeat before critical action
            check_interval: How often to check heartbeat (seconds)
            on_critical: Callback when critical threshold reached
        """
        self.heartbeat_getter = heartbeat_getter
        self.log_dir = log_dir
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
        self.check_interval = check_interval
        self.on_critical = on_critical

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._consecutive_warnings = 0

    def start(self) -> None:
        """Start the watchdog thread."""
        if self._thread and self._thread.is_alive():
            logger.warning("Watchdog already running")
            return

        self._stop_event.clear()
        self._consecutive_warnings = 0
        self._thread = threading.Thread(
            target=self._run,
            name="BrainBotWatchdog",
            daemon=False,
        )
        self._thread.start()
        logger.info("Watchdog thread started")

    def stop(self, timeout: float = 5.0) -> None:
        """
        Stop the watchdog thread.

        Args:
            timeout: How long to wait for thread to stop
        """
        if not self._thread:
            return

        self._stop_event.set()
        self._thread.join(timeout=timeout)

        if self._thread.is_alive():
            logger.warning("Watchdog thread did not stop gracefully")
        else:
            logger.info("Watchdog thread stopped")

        self._thread = None

    def is_running(self) -> bool:
        """Check if watchdog is running."""
        return self._thread is not None and self._thread.is_alive()

    def _run(self) -> None:
        """Watchdog main loop."""
        logger.info("[WATCHDOG] Starting watchdog loop")

        while not self._stop_event.is_set():
            try:
                # Wait for check interval or stop signal
                if self._stop_event.wait(self.check_interval):
                    break

                # Check heartbeat age
                last_heartbeat = self.heartbeat_getter()
                age = time.time() - last_heartbeat

                if age > self.critical_threshold:
                    self._consecutive_warnings += 1
                    logger.critical(
                        f"[WATCHDOG] MAIN LOOP HUNG! No heartbeat for {int(age)}s "
                        f"(warning {self._consecutive_warnings}/3)"
                    )

                    # Capture thread dump on first critical warning
                    if self._consecutive_warnings == 1:
                        self._capture_thread_dump()

                    # Trigger recovery after 3 consecutive critical warnings
                    if self._consecutive_warnings >= 3:
                        logger.critical(
                            "[WATCHDOG] Main loop confirmed hung. Initiating recovery..."
                        )
                        if self.on_critical:
                            self.on_critical()
                        break

                elif age > self.warning_threshold:
                    logger.warning(
                        f"[WATCHDOG] Main loop slow: no heartbeat for {int(age)}s"
                    )
                    self._consecutive_warnings = 0

                else:
                    # Heartbeat is fresh
                    if self._consecutive_warnings > 0:
                        logger.info(
                            f"[WATCHDOG] Main loop recovered (heartbeat age: {int(age)}s)"
                        )
                    self._consecutive_warnings = 0

            except Exception as e:
                logger.error(f"[WATCHDOG] Error in watchdog loop: {e}", exc_info=True)
                time.sleep(self.check_interval)

        logger.info("[WATCHDOG] Watchdog loop ended")

    def _capture_thread_dump(self) -> None:
        """Capture thread stack traces for debugging."""
        if not FAULTHANDLER_AVAILABLE:
            logger.warning("[WATCHDOG] faulthandler not available, cannot capture thread dump")
            return

        logger.critical("[WATCHDOG] Capturing thread dump for hang diagnosis...")

        try:
            # Capture to string buffer
            buffer = io.StringIO()
            faulthandler.dump_traceback(file=buffer, all_threads=True)
            stack_trace = buffer.getvalue()

            # Log it
            logger.critical(f"[WATCHDOG] Thread dump:\n{stack_trace}")

            # Save to file if log_dir specified
            if self.log_dir:
                from pathlib import Path
                dump_file = Path(self.log_dir) / f"thread_dump_{int(time.time())}.txt"
                dump_file.write_text(stack_trace)
                logger.critical(f"[WATCHDOG] Thread dump saved to {dump_file}")

        except Exception as e:
            logger.error(f"[WATCHDOG] Failed to capture thread dump: {e}")


class ProcessWatchdog:
    """
    Watches a process and can force-kill it if unresponsive.

    Used as a last resort when the daemon won't stop gracefully.
    """

    @staticmethod
    def force_stop(pid: int, grace_period: float = 20.0) -> None:
        """
        Send SIGTERM, then SIGKILL if process doesn't exit.

        Args:
            pid: Process ID to stop
            grace_period: Seconds to wait before SIGKILL
        """
        logger.info(f"Force stopping PID {pid}")

        try:
            # Send SIGTERM
            os.kill(pid, signal.SIGTERM)
        except OSError as e:
            logger.error(f"Failed to send SIGTERM to {pid}: {e}")
            try:
                os.kill(pid, signal.SIGKILL)
            except Exception:
                pass
            return

        # Wait for graceful exit
        start = time.time()
        while time.time() - start < grace_period:
            try:
                os.kill(pid, 0)  # Check if alive
                time.sleep(0.5)
            except OSError:
                # Process exited
                logger.info(f"Process {pid} exited after SIGTERM")
                return

        # Still alive, send SIGKILL
        logger.warning(f"Process {pid} did not exit after SIGTERM, sending SIGKILL")
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception as e:
            logger.error(f"Failed to SIGKILL {pid}: {e}")
