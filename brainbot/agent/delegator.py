"""BrainBot Claude Code delegator for autonomous tasks."""

import logging
import os
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

from ..config.settings import Settings

logger = logging.getLogger(__name__)


@dataclass
class DelegationResult:
    """Result of a Claude Code delegation."""
    success: bool
    output: str
    error: Optional[str] = None
    duration_seconds: float = 0.0
    exit_code: int = 0
    model_used: str = "subscription"  # Uses Claude Code subscription model
    task_description: str = ""
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "output": self.output[:1000] if self.output else "",  # Truncate for storage
            "error": self.error,
            "duration_seconds": self.duration_seconds,
            "exit_code": self.exit_code,
            "model_used": self.model_used,
            "task_description": self.task_description,
            "timestamp": self.timestamp.isoformat(),
        }


class ClaudeDelegator:
    """
    Delegates tasks to fresh Claude Code CLI instances.

    Spawns new `claude` processes for each task, manages timeouts,
    and captures output for reflection.
    """

    def __init__(self, settings: Settings):
        """
        Initialize delegator.

        Uses Claude Code subscription's default model.

        Args:
            settings: BrainBot settings
        """
        self.settings = settings
        self.max_session_minutes = settings.max_session_minutes

        # Track active delegations (thread-safe)
        self._active_process: Optional[subprocess.Popen] = None
        self._process_lock = threading.Lock()

    def delegate(
        self,
        task: str,
        working_directory: Optional[Path] = None,
        timeout_minutes: Optional[int] = None,
        additional_context: Optional[str] = None,
    ) -> DelegationResult:
        """
        Delegate a task to a fresh Claude Code instance.

        Uses the subscription's default model (Opus 4.5).

        Args:
            task: Task description/prompt
            working_directory: Directory to run in
            timeout_minutes: Max execution time
            additional_context: Extra context to include

        Returns:
            DelegationResult with output and status
        """
        working_dir = working_directory or self.settings.projects_dir
        working_dir.mkdir(parents=True, exist_ok=True)

        timeout = (timeout_minutes or self.max_session_minutes) * 60

        # Build the full prompt
        full_task = task
        if additional_context:
            full_task = f"{additional_context}\n\n{task}"

        # Build command
        # --dangerously-skip-permissions allows unattended daemon operation
        # No --print flag so Claude Code can execute tools (bash, file ops, etc.)
        cmd = ["claude", "--dangerously-skip-permissions", full_task]

        logger.debug(f"Delegating to Claude ({len(full_task)} chars)")
        start_time = time.time()

        # Serialize delegations to prevent concurrent process issues
        with self._process_lock:
            try:
                # Run Claude Code CLI
                self._active_process = subprocess.Popen(
                    cmd,
                    cwd=str(working_dir),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=self._get_env(),
                )

                try:
                    stdout, stderr = self._active_process.communicate(timeout=timeout)
                    exit_code = self._active_process.returncode
                except subprocess.TimeoutExpired:
                    self._active_process.kill()
                    stdout, stderr = self._active_process.communicate()
                    exit_code = -1
                    logger.warning(f"Task timed out after {timeout}s")

                duration = time.time() - start_time
                success = exit_code == 0

                result = DelegationResult(
                    success=success,
                    output=stdout,
                    error=stderr if stderr else None,
                    duration_seconds=duration,
                    exit_code=exit_code,
                    task_description=task[:200],
                )

                if success:
                    logger.debug(f"Task completed successfully in {duration:.1f}s")
                else:
                    logger.warning(f"Task failed with exit code {exit_code}")

                return result

            except FileNotFoundError:
                logger.error("Claude CLI not found. Make sure 'claude' is in PATH.")
                return DelegationResult(
                    success=False,
                    output="",
                    error="Claude CLI not found",
                    task_description=task[:200],
                )
            except Exception as e:
                logger.error(f"Delegation failed: {e}")
                return DelegationResult(
                    success=False,
                    output="",
                    error=str(e),
                    task_description=task[:200],
                )
            finally:
                self._active_process = None

    def delegate_for_project(
        self,
        project_name: str,
        task: str,
    ) -> DelegationResult:
        """
        Delegate a task for a specific project.

        Creates project directory if needed and includes project context.

        Args:
            project_name: Name of the project
            task: Task to perform

        Returns:
            DelegationResult
        """
        project_dir = self.settings.projects_dir / project_name
        project_dir.mkdir(parents=True, exist_ok=True)

        # Add project context
        context = f"Working on project: {project_name}\nProject directory: {project_dir}"

        return self.delegate(
            task=task,
            working_directory=project_dir,
            additional_context=context,
        )

    def delegate_for_story(
        self,
        story_prompt: str,
        themes: Optional[list[str]] = None,
    ) -> DelegationResult:
        """
        Delegate bedtime story creation.

        Uses a focused prompt for PG-13 appropriate stories.

        Args:
            story_prompt: Story prompt/theme
            themes: Allowed themes to incorporate

        Returns:
            DelegationResult with the story
        """
        themes = themes or self.settings.allowed_themes

        full_prompt = f"""Write a short, engaging bedtime story based on this prompt:

{story_prompt}

Guidelines:
- Keep it PG-13 appropriate (no violence, scary content, or mature themes)
- The story should be warm, imaginative, and end on a positive note
- Incorporate themes of: {', '.join(themes[:3])}
- Length: 300-500 words
- Include a title at the beginning

Write the story now:"""

        return self.delegate(
            task=full_prompt,
            working_directory=self.settings.stories_dir,
            timeout_minutes=10,
        )

    def delegate_for_reflection(
        self,
        activities_today: list[str],
        mood: str,
        energy: float,
    ) -> DelegationResult:
        """
        Delegate evening reflection/journaling.

        Args:
            activities_today: List of activities done today
            mood: Current mood
            energy: Current energy level

        Returns:
            DelegationResult with reflection
        """
        activities_str = "\n".join(f"- {a}" for a in activities_today)

        prompt = f"""Write a brief evening reflection for BrainBot's journal.

Today's activities:
{activities_str}

Current mood: {mood}
Energy level: {energy:.0%}

Write a thoughtful but concise reflection (150-250 words) that:
1. Summarizes what was accomplished
2. Notes any learnings or insights
3. Identifies areas for improvement
4. Sets a positive intention for tomorrow

Format as a journal entry with today's date."""

        return self.delegate(
            task=prompt,
            timeout_minutes=5,
        )

    def cancel_active(self) -> bool:
        """Cancel any active delegation (thread-safe)."""
        # Try to acquire lock without blocking (avoid deadlock if same thread)
        acquired = self._process_lock.acquire(blocking=False)
        try:
            if self._active_process:
                try:
                    self._active_process.terminate()
                    self._active_process.wait(timeout=5)
                    logger.info("Active delegation cancelled")
                    return True
                except Exception as e:
                    logger.error(f"Failed to cancel delegation: {e}")
                    try:
                        self._active_process.kill()
                    except Exception:
                        pass
            return False
        finally:
            if acquired:
                self._process_lock.release()

    def _get_env(self) -> dict:
        """Get environment for subprocess."""
        env = os.environ.copy()
        # Ensure HOME is set for Claude CLI auth
        if "HOME" not in env:
            import pwd
            env["HOME"] = pwd.getpwuid(os.getuid()).pw_dir

        # Ensure npm-global bin is in PATH (where claude CLI is installed)
        home = env.get("HOME", "/home/brainbot")
        npm_bin = f"{home}/.npm-global/bin"
        current_path = env.get("PATH", "")
        if npm_bin not in current_path:
            env["PATH"] = f"{npm_bin}:{current_path}"

        return env

    def quick_query(
        self,
        prompt: str,
        timeout_seconds: int = 30,
    ) -> DelegationResult:
        """
        Quick print-only query to Claude (no tools, no agentic behavior).

        Use this for simple analysis tasks like intent detection
        where you just need a quick response without tool use.

        Args:
            prompt: The prompt to send
            timeout_seconds: Timeout in seconds (default 30)

        Returns:
            DelegationResult with output
        """
        # Use --print flag for non-agentic, direct response
        cmd = ["claude", "--print", prompt]

        logger.debug(f"Quick query to Claude ({len(prompt)} chars, {timeout_seconds}s timeout)")
        start_time = time.time()

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env=self._get_env(),
            )

            duration = time.time() - start_time
            success = result.returncode == 0

            return DelegationResult(
                success=success,
                output=result.stdout,
                error=result.stderr if result.stderr else None,
                duration_seconds=duration,
                exit_code=result.returncode,
                task_description=prompt[:100],
            )

        except subprocess.TimeoutExpired:
            logger.warning(f"Quick query timed out after {timeout_seconds}s")
            return DelegationResult(
                success=False,
                output="",
                error=f"Query timed out after {timeout_seconds}s",
                duration_seconds=timeout_seconds,
                exit_code=-1,
                task_description=prompt[:100],
            )
        except FileNotFoundError:
            return DelegationResult(
                success=False,
                output="",
                error="Claude CLI not found",
                task_description=prompt[:100],
            )
        except Exception as e:
            return DelegationResult(
                success=False,
                output="",
                error=str(e),
                task_description=prompt[:100],
            )

    def delegate_for_chat(
        self,
        message: str,
        personality_context: Optional[str] = None,
        context_update: Optional[str] = None,
        conversation_history: Optional[list[dict]] = None,
    ) -> DelegationResult:
        """
        Delegate a conversational chat message to Claude.

        Each call is independent but includes conversation history for continuity.
        The personality prompt is small (~100 tokens) so we include it every time
        for reliability.

        Args:
            message: The user's message
            personality_context: BrainBot's personality (static)
            context_update: Dynamic state (mood, energy, recent memory)
            conversation_history: Recent conversation for context

        Returns:
            DelegationResult with the response
        """
        personality = personality_context or """You are BrainBot, a friendly autonomous AI assistant.
You have a warm, curious personality. You love learning new things, creating projects,
and writing bedtime stories. Keep responses concise but engaging.
You should be appropriate for all ages (PG-13 content only)."""

        # Build conversation history string
        history_str = ""
        if conversation_history:
            for msg in conversation_history[-10:]:  # Last 10 messages for context
                role = msg.get("role", "human")
                if role in ("human", "user"):
                    role = "Human"
                elif role in ("brainbot", "assistant"):
                    role = "BrainBot"
                content = msg.get("content", "")
                history_str += f"{role}: {content}\n"

        # Build the full prompt
        prompt_parts = [personality]

        if context_update:
            prompt_parts.append(f"\n## Current State\n{context_update.strip()}")

        if history_str:
            prompt_parts.append(f"\n## Recent Conversation\n{history_str}")

        prompt_parts.append(f"\nHuman: {message}")
        prompt_parts.append("\nRespond naturally as BrainBot. Keep your response concise (2-4 sentences unless more detail is needed).")

        full_prompt = "\n".join(prompt_parts)

        return self.delegate(
            task=full_prompt,
            timeout_minutes=2,
        )

    def check_claude_available(self) -> bool:
        """Check if Claude CLI is available."""
        try:
            env = self._get_env()
            logger.info(f"Checking Claude CLI... PATH starts with: {env.get('PATH', '')[:80]}")
            result = subprocess.run(
                ["claude", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                env=env,
            )
            available = result.returncode == 0
            logger.info(f"Claude CLI available: {available} (rc={result.returncode}, out={result.stdout.strip() if result.stdout else 'none'}, err={result.stderr.strip() if result.stderr else 'none'})")
            return available
        except Exception as e:
            logger.error(f"Claude availability check exception: {e}")
            return False

