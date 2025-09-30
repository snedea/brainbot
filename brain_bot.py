#!/usr/bin/env python3
"""
BrainBot 🧠✨ - Your Local AI Assistant
=====================================

SETUP INSTRUCTIONS:
-------------------------------
1. Install Python (3.8 or newer):
   - Windows: Download from python.org
   - Mac: Install via Homebrew: `brew install python3`
   - Linux/Raspberry Pi: `sudo apt update && sudo apt install python3 python3-pip`

2. Create a project folder and virtual environment:
   ```
   mkdir brainbot
   cd brainbot
   python3 -m venv venv
   ```

3. Activate the virtual environment:
   - Windows: `venv\Scripts\activate`
   - Mac/Linux/Pi: `source venv/bin/activate`

4. Install required packages:
   ```
   pip install -r requirements.txt
   ```

5. Run BrainBot:
   ```
   python brain_bot.py
   ```

The first run will download the AI model (~670MB). After that, it works offline!

REQUIRED PACKAGES:
-----------------
# textual==0.82.0
# llama-cpp-python==0.3.1
# huggingface-hub==0.25.2
# rich==13.9.4
"""

import os
import sys
import threading
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

# Import the Textual framework for our colorful terminal UI
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Header, Footer, Input, RichLog, Static
from textual.binding import Binding
from textual.message import Message

# Import Rich for fancy text formatting
from rich.text import Text
from rich.panel import Panel

# Import the AI model libraries
from llama_cpp import Llama
from huggingface_hub import hf_hub_download

# Constants for our AI model
MODEL_REPO = "TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF"
MODEL_FILE = "tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"
MODEL_DIR = Path.home() / ".cache" / "brainbot"

# Friendly system prompt that makes BrainBot helpful and fun
SYSTEM_PROMPT = """You are BrainBot, a friendly and curious AI assistant.
You are incredibly creative, positive, and encouraging. You love to tell stories,
write funny poems, and explain complex things in a simple and fun way.
Your answers are always helpful, imaginative, and appropriate.
You never say anything scary, mean, or inappropriate. Keep responses concise and engaging."""


class BrainBotApp(App):
    """The main BrainBot application using Textual framework."""

    # CSS styling for our colorful interface
    CSS = """
    Screen {
        background: $primary-background;
    }

    Header {
        background: $accent;
        color: $text;
        text-style: bold;
    }

    RichLog {
        background: $panel;
        border: thick $accent;
        border-title-color: $accent;
        border-title-style: bold;
        scrollbar-size: 1 1;
        padding: 1 2;
        margin: 1 2;
    }

    Input {
        dock: bottom;
        margin: 1 2 2 2;
        background: $panel;
        border: thick $accent;
        border-title-color: $accent;
        padding: 0 1;
    }

    Footer {
        background: $primary-background-lighten-2;
    }

    .thinking {
        color: $warning;
        text-style: italic;
    }

    .user-message {
        color: $success;
        text-style: bold;
    }

    .bot-message {
        color: $text;
    }
    """

    # Keybindings for the app
    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", priority=True),
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+space", "trigger_wake", "Wake"),
    ]

    # Set the app title
    TITLE = "BrainBot 🧠✨"

    # Use a fun color theme
    THEME = "nord"

    def __init__(self):
        """Initialize the BrainBot app."""
        super().__init__()
        self.llm: Optional[Llama] = None
        self.model_path: Optional[Path] = None
        self.is_processing = False
        self.voice_agent = None  # Will be set when voice mode is enabled

    def compose(self) -> ComposeResult:
        """Build the UI layout."""
        # Create the header with our title
        yield Header(show_clock=True, time_format='%I:%M %p')

        # Create the main chat display area with word wrapping
        chat_log = RichLog(highlight=True, markup=True, wrap=True, auto_scroll=True)
        chat_log.border_title = "💬 Chat with BrainBot"
        yield chat_log

        # Create the input box for user messages
        input_box = Input(placeholder="Ask me anything! What shall we explore today?")
        input_box.border_title = "✏️ Your Message"
        yield input_box

        # Create voice status indicator (shown only in voice mode)
        voice_status = Static("", id="voice_status")
        voice_status.styles.dock = "top"
        voice_status.styles.align = ("right", "top")
        voice_status.styles.padding = (0, 2)
        voice_status.styles.color = "#808080"
        yield voice_status

        # Add footer with instructions
        yield Footer()

    def on_mount(self) -> None:
        """Called when the app starts up."""
        # Get references to our widgets
        self.chat_log = self.query_one(RichLog)
        self.input_box = self.query_one(Input)
        self.voice_status = self.query_one("#voice_status", Static)

        # Show welcome message
        welcome_text = Text()
        welcome_text.append("🎉 ", style="bold yellow")
        welcome_text.append("Welcome to BrainBot!\n\n", style="bold cyan")
        welcome_text.append("I'm BrainBot, your friendly AI companion! ", style="white")
        welcome_text.append("I love to:\n", style="white")
        welcome_text.append("  • 📚 Answer your curious questions\n", style="green")
        welcome_text.append("  • 📝 Help you write stories and poems\n", style="green")
        welcome_text.append("  • 🎨 Create fun word games\n", style="green")
        welcome_text.append("  • 🔬 Explain how things work\n", style="green")
        welcome_text.append("\n", style="white")
        welcome_text.append("\nWhat would you like to talk about today?", style="italic cyan")

        self.chat_log.write(welcome_text)
        self.chat_log.write("")  # Add some spacing

        # Focus on the input box
        self.input_box.focus()

        # Initialize the AI model in the background
        self.init_model_async()

    def init_model_async(self) -> None:
        """Initialize the AI model in a background thread."""
        self.initialize_model()

    @work(exclusive=True)
    async def initialize_model(self) -> None:
        """Download (if needed) and load the AI model."""
        self.chat_log.write(Text("🤖 Loading BrainBot's brain...", style="dim italic"))

        try:
            # Ensure model directory exists
            MODEL_DIR.mkdir(parents=True, exist_ok=True)
            self.model_path = MODEL_DIR / MODEL_FILE

            # Check if model exists, download if not
            if not self.model_path.exists():
                self.chat_log.write(Text("📥 Downloading AI model (this only happens once)...",
                                       style="yellow italic"))
                self.chat_log.write(Text("   This might take a few minutes (~670MB)",
                                       style="dim italic"))

                # Download the model using Hugging Face Hub
                try:
                    import urllib.request
                    model_url = f"https://huggingface.co/{MODEL_REPO}/resolve/main/{MODEL_FILE}"

                    # Download with progress indication
                    def download_with_progress():
                        urllib.request.urlretrieve(model_url, str(self.model_path))
                        return str(self.model_path)

                    downloaded_path = await self.run_in_thread(download_with_progress)
                except Exception as download_error:
                    # Fallback to hf_hub_download without threading
                    downloaded_path = hf_hub_download(
                        repo_id=MODEL_REPO,
                        filename=MODEL_FILE,
                        cache_dir=MODEL_DIR,
                        local_dir=MODEL_DIR,
                        local_dir_use_symlinks=False
                    )

                self.chat_log.write(Text("✅ Model downloaded successfully!", style="green"))

            # Load the model
            self.chat_log.write(Text("🧠 Initializing neural pathways...", style="cyan italic"))

            # Create the LLM instance with optimized settings
            self.llm = await self.run_in_thread(
                lambda: Llama(
                    model_path=str(self.model_path),
                    n_ctx=2048,  # Context window size
                    n_threads=4,  # Number of CPU threads to use
                    n_gpu_layers=0,  # CPU only for compatibility
                    verbose=False,  # Quiet mode
                    seed=42,  # For reproducibility
                    temperature=0.7,  # Creativity level (0.7 is balanced)
                )
            )

            self.chat_log.write(Text("🎊 BrainBot is ready to chat!", style="bold green"))
            self.chat_log.write("")  # Add spacing

        except Exception as e:
            error_msg = f"❌ Oops! Couldn't load BrainBot: {str(e)}"
            self.chat_log.write(Text(error_msg, style="bold red"))
            self.chat_log.write(Text("Please check your internet connection and try again.",
                                    style="italic"))

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle when user presses Enter in the input box."""
        # Get the user's message
        user_message = event.value.strip()

        # Ignore empty messages
        if not user_message:
            return

        # Check if we're already processing or model isn't ready
        if self.is_processing or self.llm is None:
            self.chat_log.write(Text("⏳ Please wait, I'm still thinking...",
                                    style="yellow italic"))
            return

        # Clear the input box for the next message
        self.input_box.clear()

        # Show the user's message in the chat
        user_text = Text()
        user_text.append("👤 You: ", style="bold green")
        user_text.append(user_message, style="green")
        self.chat_log.write(user_text)
        self.chat_log.write("")  # Add spacing

        # Process the message with the AI
        self.generate_response(user_message)

    @work(exclusive=True)
    async def generate_response(self, user_message: str) -> None:
        """Generate AI response in a background worker."""
        self.is_processing = True

        # Show thinking message
        thinking_msg = Text("🤔 BrainBot is thinking...", style="cyan italic")
        self.chat_log.write(thinking_msg)

        try:
            # Create the prompt with system message and user input
            prompt = f"""<|system|>
{SYSTEM_PROMPT}
</s>
<|user|>
{user_message}
</s>
<|assistant|>"""

            # Generate response from the AI model
            response = await self.run_in_thread(
                lambda: self.llm(
                    prompt,
                    max_tokens=256,  # Maximum response length
                    stop=["</s>", "<|user|>"],  # Stop tokens
                    echo=False,  # Don't repeat the prompt
                    temperature=0.7,  # Creativity level
                    top_p=0.9,  # Nucleus sampling
                    repeat_penalty=1.1,  # Avoid repetition
                )
            )

            # Extract the generated text
            bot_response = response['choices'][0]['text'].strip()

            # Simply add the bot's response (no need to clear)
            # The thinking message will remain visible but that's ok
            bot_text = Text()
            bot_text.append("🤖 BrainBot: ", style="bold cyan")
            bot_text.append(bot_response, style="white")
            self.chat_log.write(bot_text)
            self.chat_log.write("")  # Add spacing

            # Speak the response if TTS is enabled
            if self.tts_enabled and self.tts_engine and bot_response:
                self.speak_text(bot_response)

        except Exception as e:
            # Handle any errors
            error_text = Text()
            error_text.append("❌ Oops! ", style="bold red")
            error_text.append(f"Something went wrong: {str(e)}", style="red")
            self.chat_log.write(error_text)

        finally:
            self.is_processing = False

    async def run_in_thread(self, func):
        """Run a blocking function in a thread to avoid freezing the UI."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, func)

    def action_trigger_wake(self) -> None:
        """Manually trigger wake word detection (simulates saying 'Computer')."""
        if not self.voice_agent or not hasattr(self.voice_agent, '_on_wake_detected'):
            self.chat_log.write(Text("⚠️ Voice mode is not active.",
                                    style="yellow italic"))
            return

        # Trigger the wake word callback manually
        self.voice_agent._on_wake_detected()
        self.chat_log.write(Text("🎤 Wake word triggered! Listening...",
                                 style="cyan italic"))
        self.chat_log.write("")  # Add spacing


class VoiceHooks:
    """
    Integration hooks for voice mode.

    This class bridges the voice agent with the BrainBot TUI,
    allowing voice interactions to appear in the chat interface.
    """

    def __init__(self, brain_bot_app: BrainBotApp):
        """
        Initialize voice hooks.

        Args:
            brain_bot_app: Reference to the BrainBotApp instance
        """
        self.app = brain_bot_app
        self.current_state = "IDLE"

    def on_state_change(self, state):
        """
        Update UI based on voice agent state.

        Args:
            state: VoiceAgentState enum value
        """
        from agent.voice_agent import VoiceAgentState

        state_indicators = {
            VoiceAgentState.IDLE: "🎤 Ready",
            VoiceAgentState.LISTENING: "🔴 Recording...",
            VoiceAgentState.TRANSCRIBING: "⚙️  Transcribing...",
            VoiceAgentState.THINKING: "🧠 Thinking...",
            VoiceAgentState.SPEAKING: "🔊 Speaking...",
            VoiceAgentState.ERROR: "❌ Error"
        }

        status_text = state_indicators.get(state, "🎤 Ready")
        self.current_state = status_text

        # Update voice status widget (thread-safe)
        if hasattr(self.app, 'voice_status'):
            self.app.call_from_thread(
                self._update_voice_status,
                status_text
            )

    def _update_voice_status(self, text: str):
        """Helper method to update voice status (runs on main thread)."""
        self.app.voice_status.update(text)

    def on_transcript(self, text: str):
        """
        Handle transcribed user speech.

        Args:
            text: Transcribed user text
        """
        if text and text.strip():
            # Add user message to chat (thread-safe)
            self.app.call_from_thread(
                self.app.chat_log.write,
                Text(f"👤 You: {text}", style="bold cyan")
            )

    def on_response(self, text: str):
        """
        Handle LLM response.

        Args:
            text: Generated response text
        """
        if text and text.strip():
            # Add AI response to chat (thread-safe)
            self.app.call_from_thread(
                self.app.chat_log.write,
                Text(f"🤖 BrainBot: {text}", style="bold green")
            )
            self.app.call_from_thread(
                self.app.chat_log.write,
                ""  # Add spacing
            )


def main():
    """Main entry point for BrainBot."""
    import argparse

    # Check Python version
    if sys.version_info < (3, 8):
        print("❌ BrainBot requires Python 3.8 or newer!")
        print("Please upgrade Python and try again.")
        sys.exit(1)

    # Configure logging to file (keeps TUI clean)
    log_dir = Path.home() / ".cache" / "brainbot"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "brainbot.log"

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        filename=str(log_file),
        filemode='a'  # Append mode
    )

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='BrainBot - Your friendly local AI assistant',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python brain_bot.py              Run in text mode (default)
  python brain_bot.py --voice      Enable voice mode with wake word
  python brain_bot.py --test-audio Test microphone and audio devices
        """
    )

    parser.add_argument(
        '--voice',
        action='store_true',
        help='Enable voice mode with wake word detection'
    )

    parser.add_argument(
        '--test-audio',
        action='store_true',
        help='Test audio devices and exit (no chat interface)'
    )

    args = parser.parse_args()

    # Test audio if requested
    if args.test_audio:
        print("🎤 Running audio device test...\n")
        try:
            from scripts.audio_check import main as audio_main
            audio_main()
        except ImportError as e:
            print(f"❌ Could not import audio_check: {e}")
            print("Make sure all voice dependencies are installed.")
        return

    # Initialize voice mode if requested
    voice_agent = None
    if args.voice:
        try:
            print("🎙️  Initializing voice mode...")

            # Import voice components
            from config import load_voice_config, ENV_LOADER_AVAILABLE
            from agent.voice_agent import VoiceAgent

            if not ENV_LOADER_AVAILABLE:
                print("❌ Voice mode requires python-dotenv")
                print("Install it with: pip install python-dotenv")
                sys.exit(1)

            # Load voice configuration
            config = load_voice_config()
            print("✅ Voice configuration loaded")

            # Note: Voice agent will be started after the app is created
            # so we can hook into the app's UI

        except ValueError as e:
            print(f"❌ Configuration error: {e}")
            print("\nPlease edit your .env file and add required settings.")
            print("Copy .env.example to .env if you haven't already.")
            sys.exit(1)

        except FileNotFoundError as e:
            print(f"❌ Missing files: {e}")
            print("\nRun ./setup_voice.sh to install voice mode dependencies.")
            sys.exit(1)

        except Exception as e:
            print(f"❌ Failed to initialize voice mode: {e}")
            import traceback
            traceback.print_exc()
            print("\nContinuing in text-only mode...")
            args.voice = False

    # Create and run the app
    app = BrainBotApp()

    # Start voice agent if enabled
    if args.voice and 'config' in locals():
        try:
            # Create hooks to bridge voice agent with UI
            hooks = VoiceHooks(app)

            # Create voice agent
            voice_agent = VoiceAgent(
                config=config,
                on_state_change=hooks.on_state_change,
                on_transcript=hooks.on_transcript,
                on_response=hooks.on_response
            )

            # Start voice agent in background thread
            # Note: VoiceAgent is already a Thread, so just call start() directly
            print("🔄 Starting voice agent components...")
            voice_agent.start()

            # Wait for initialization to complete before starting TUI
            # This ensures all ALSA messages appear before the TUI takes over
            print("⏳ Waiting for components to initialize...")
            if voice_agent.wait_for_initialization(timeout=30.0):
                # Store voice agent in app for manual wake trigger
                app.voice_agent = voice_agent

                # Show voice mode indicator
                keywords = config.wake_keywords or ["wake word"]
                print(f"✅ Voice mode active! Say '{keywords[0]}' to interact")
                print("   Text mode still works - just type normally")
                print(f"   Press Ctrl+Space to manually trigger wake")
                print(f"   Logs saved to: {log_file}\n")
            else:
                print("⚠️  Voice agent initialization timed out")
                print("Continuing in text-only mode...\n")
                voice_agent = None

        except Exception as e:
            print(f"⚠️  Could not start voice agent: {e}")
            print("Continuing in text-only mode...\n")
            voice_agent = None

    try:
        # Run the Textual app
        app.run()
    except KeyboardInterrupt:
        print("\n👋 Shutting down BrainBot...")
    finally:
        # Stop voice agent if running
        if voice_agent:
            try:
                voice_agent.stop()
                print("✅ Voice agent stopped")
            except:
                pass


if __name__ == "__main__":
    main()