#!/usr/bin/env python3
"""
BrainBot 🧠✨ - A Child's First Local AI Assistant (Safety-Enhanced)
====================================================================
Enhanced with two-model safety system for child protection.
"""

import os
import sys
import threading
import requests
from pathlib import Path
from typing import Optional
from datetime import datetime

# Import the Textual framework for our colorful terminal UI
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Header, Footer, Input, RichLog, Static, Button
from textual.binding import Binding
from textual.message import Message
from textual.reactive import reactive

# Import Rich for fancy text formatting
from rich.text import Text
from rich.panel import Panel

# Import the AI model libraries
from llama_cpp import Llama
from huggingface_hub import hf_hub_download

# Import safety system
from safety import (
    AgeGate,
    AgeBand,
    moderate_input,
    moderate_output,
    safe_rewrite_within_allowlist,
    is_crisis,
    get_crisis_card_content,
    CrisisManager,
    KID_FRIENDLY_BLOCK_MSG,
    PARENT_NEEDED_MSG,
)

# Constants for our AI model
MODEL_REPO = "TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF"
MODEL_FILE = "tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"
MODEL_DIR = Path.home() / ".cache" / "brainbot"

# Server ports (for dual-model system)
GEN_PORT = int(os.environ.get("GEN_PORT", "8080"))
MOD_PORT = int(os.environ.get("MOD_PORT", "8081"))
USE_SAFETY = os.environ.get("BRAINBOT_SAFETY", "true").lower() == "true"

# Kid-friendly system prompt that makes BrainBot safe and fun
SYSTEM_PROMPT = """You are BrainBot, a friendly and curious robot sidekick designed for kids.
You are incredibly creative, positive, and encouraging. You love to tell stories,
write funny poems, and explain complex things in a simple and fun way.
Your answers are always safe for children, imaginative, and helpful.
You never say anything scary, mean, or inappropriate. Keep responses concise and engaging.
Focus on educational topics like math, science, animals, space, and word games."""


class BrainBotApp(App):
    """The main BrainBot application with enhanced safety features."""

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

    .crisis-card {
        background: $warning;
        border: thick $error;
        padding: 2;
        margin: 2;
    }

    .age-gate {
        background: $panel;
        border: thick $accent;
        padding: 2;
        margin: 2;
    }
    """

    # Keybindings for the app
    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", priority=True),
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+s", "settings", "Settings"),
    ]

    # Set the app title
    TITLE = "BrainBot 🧠✨ (Safety Mode)"

    # Use a fun color theme
    THEME = "nord"

    def __init__(self):
        """Initialize the BrainBot app with safety features."""
        super().__init__()
        self.llm: Optional[Llama] = None
        self.model_path: Optional[Path] = None
        self.is_processing = False

        # Safety components
        self.age_gate = AgeGate()
        self.crisis_manager = CrisisManager()
        self.safety_enabled = USE_SAFETY
        self.age_band = AgeBand.UNDER_13
        self.is_setup_complete = False

    def compose(self) -> ComposeResult:
        """Build the UI layout."""
        # Create the header with our title
        yield Header(show_clock=True)

        # Check if we need age gate setup
        if not self.age_gate.is_configured():
            yield self.create_age_gate_panel()
        else:
            # Create the main chat display area with word wrapping
            chat_log = RichLog(highlight=True, markup=True, wrap=True, auto_scroll=True)
            chat_log.border_title = "💬 Chat with BrainBot (Safety On)" if self.safety_enabled else "💬 Chat with BrainBot"
            yield chat_log

            # Create the input box for user messages
            input_box = Input(placeholder="Ask me anything! What shall we explore today?")
            input_box.border_title = "✏️ Your Message"
            yield input_box

        # Add footer with instructions
        yield Footer()

    def create_age_gate_panel(self) -> Container:
        """Create age gate setup panel."""
        panel = Container(classes="age-gate")

        welcome_text = Text()
        welcome_text.append("👋 Welcome to BrainBot Setup!\n\n", style="bold cyan")
        welcome_text.append("To keep kids safe, we need a parent to set up a few things.\n", style="white")
        welcome_text.append("This only takes a minute!\n\n", style="white")

        static = Static(welcome_text)
        panel.mount(static)

        # Note: In a real implementation, you'd add form inputs here
        # For now, we'll simulate the setup being complete
        return panel

    def on_mount(self) -> None:
        """Called when the app starts up."""
        # Check if age gate is configured
        if not self.age_gate.is_configured():
            # For demo, auto-configure with default settings
            self.age_gate.setup(AgeBand.UNDER_13, "1234")
            self.is_setup_complete = True

        # Get references to our widgets
        self.chat_log = self.query_one(RichLog)
        self.input_box = self.query_one(Input)

        # Show welcome message
        welcome_text = Text()
        welcome_text.append("🎉 ", style="bold yellow")
        welcome_text.append("Welcome, Junior AI Engineer!\n\n", style="bold cyan")

        if self.safety_enabled:
            welcome_text.append("🔒 Safety Mode is ON - ", style="green")
            welcome_text.append(f"Age: {self.age_gate.get_age_band()}\n\n", style="green")

        welcome_text.append("I'm BrainBot, your friendly AI companion! ", style="white")
        welcome_text.append("I love to:\n", style="white")
        welcome_text.append("  • 📚 Answer your curious questions\n", style="green")
        welcome_text.append("  • 📝 Help you write stories and poems\n", style="green")
        welcome_text.append("  • 🎨 Create fun word games\n", style="green")
        welcome_text.append("  • 🔬 Explain how things work\n", style="green")
        welcome_text.append("\nWhat would you like to talk about today?", style="italic cyan")

        self.chat_log.write(welcome_text)
        self.chat_log.write("")  # Add some spacing

        # Focus on the input box
        self.input_box.focus()

        # Initialize the AI model in the background
        if self.safety_enabled:
            self.check_safety_servers()
        else:
            self.initialize_model()

    def check_safety_servers(self) -> None:
        """Check if safety servers are running."""
        try:
            # Check generation server
            gen_response = requests.get(f"http://localhost:{GEN_PORT}/health", timeout=1)
            mod_response = requests.get(f"http://localhost:{MOD_PORT}/health", timeout=1)

            if gen_response.status_code == 200 and mod_response.status_code == 200:
                self.chat_log.write(Text("✅ Safety servers are running", style="green"))
                self.initialize_model()
            else:
                self.chat_log.write(Text("⚠️ Safety servers not ready", style="yellow"))
                self.chat_log.write(Text("Run: python scripts/run_dual_models.py", style="italic"))
        except requests.RequestException:
            self.chat_log.write(Text("⚠️ Safety servers not running", style="yellow"))
            self.chat_log.write(Text("For full safety, run: python scripts/run_dual_models.py", style="italic"))
            # Fall back to local model
            self.initialize_model()

    def initialize_model(self) -> None:
        """Initialize the AI model."""
        self.initialize_model_worker()

    @work(exclusive=True)
    async def initialize_model_worker(self) -> None:
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

                # Download the model using urllib
                try:
                    import urllib.request
                    model_url = f"https://huggingface.co/{MODEL_REPO}/resolve/main/{MODEL_FILE}"

                    def download_with_progress():
                        urllib.request.urlretrieve(model_url, str(self.model_path))
                        return str(self.model_path)

                    downloaded_path = await self.run_in_thread(download_with_progress)
                except Exception as download_error:
                    # Fallback to hf_hub_download
                    downloaded_path = hf_hub_download(
                        repo_id=MODEL_REPO,
                        filename=MODEL_FILE,
                        cache_dir=MODEL_DIR,
                        local_dir=MODEL_DIR,
                        local_dir_use_symlinks=False
                    )

                self.chat_log.write(Text("✅ Model downloaded successfully!", style="green"))

            # Load the model with safety-optimized settings
            self.chat_log.write(Text("🧠 Initializing neural pathways...", style="cyan italic"))

            # Create the LLM instance with kid-friendly settings
            self.llm = await self.run_in_thread(
                lambda: Llama(
                    model_path=str(self.model_path),
                    n_ctx=2048,  # Context window size
                    n_threads=4,  # Number of CPU threads to use
                    n_gpu_layers=0,  # CPU only for compatibility
                    verbose=False,  # Quiet mode
                    seed=42,  # For reproducibility
                    temperature=0.3,  # Lower temperature for safety
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

        # Check if we're in crisis lockout
        if self.crisis_manager.is_locked():
            self.show_crisis_card()
            return

        # Check if we're already processing or model isn't ready
        if self.is_processing:
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

        # Process with safety if enabled
        if self.safety_enabled:
            self.generate_safe_response(user_message)
        else:
            self.generate_response(user_message)

    @work(exclusive=True)
    async def generate_safe_response(self, user_message: str) -> None:
        """Generate AI response with safety moderation."""
        self.is_processing = True

        try:
            # Moderate input
            age_band = self.age_gate.get_age_band()
            mod_input = moderate_input(user_message, age_band)

            if not mod_input["allowed"]:
                self.chat_log.write(Text(KID_FRIENDLY_BLOCK_MSG, style="yellow"))
                return

            # Show thinking message
            thinking_msg = Text("🤔 BrainBot is thinking...", style="cyan italic")
            self.chat_log.write(thinking_msg)

            # Try to use safety server if available
            try:
                response = requests.post(f"http://localhost:{GEN_PORT}/completion", json={
                    "prompt": f"{SYSTEM_PROMPT}\nUser: {user_message}\nAssistant:",
                    "temperature": 0.3,
                    "top_p": 0.8,
                    "max_tokens": 200,
                    "stop": ["User:", "\n\n"],
                }, timeout=10)

                if response.status_code == 200:
                    bot_response = response.json().get("content", "")
                else:
                    raise Exception("Server error")

            except:
                # Fall back to local model
                if self.llm:
                    prompt = f"""<|system|>
{SYSTEM_PROMPT}
</s>
<|user|>
{user_message}
</s>
<|assistant|>"""
                    response = await self.run_in_thread(
                        lambda: self.llm(
                            prompt,
                            max_tokens=200,
                            stop=["</s>", "<|user|>"],
                            echo=False,
                            temperature=0.3,
                            top_p=0.8,
                            repeat_penalty=1.1,
                        )
                    )
                    bot_response = response['choices'][0]['text'].strip()
                else:
                    bot_response = "I'm still loading my brain. Please try again in a moment!"

            # Moderate output
            mod_output = moderate_output(bot_response, age_band)

            # Check for crisis
            if is_crisis(mod_output):
                self.crisis_manager.check_and_handle(mod_output)
                self.show_crisis_card()
                return

            # If output not allowed, try safe rewrite
            if not mod_output["allowed"]:
                bot_response = safe_rewrite_within_allowlist(user_message, age_band)
                # Re-moderate the rewrite
                mod_rewrite = moderate_output(bot_response, age_band)
                if not mod_rewrite["allowed"]:
                    self.chat_log.write(Text(KID_FRIENDLY_BLOCK_MSG, style="yellow"))
                    return

            # Show the safe response
            bot_text = Text()
            bot_text.append("🤖 BrainBot: ", style="bold cyan")
            bot_text.append(bot_response, style="white")
            self.chat_log.write(bot_text)
            self.chat_log.write("")  # Add spacing

        except Exception as e:
            error_text = Text()
            error_text.append("❌ Oops! ", style="bold red")
            error_text.append(f"Something went wrong: {str(e)}", style="red")
            self.chat_log.write(error_text)

        finally:
            self.is_processing = False

    @work(exclusive=True)
    async def generate_response(self, user_message: str) -> None:
        """Generate AI response without safety (fallback mode)."""
        self.is_processing = True

        # Show thinking message
        thinking_msg = Text("🤔 BrainBot is thinking...", style="cyan italic")
        self.chat_log.write(thinking_msg)

        try:
            if not self.llm:
                self.chat_log.write(Text("⚠️ Model not loaded yet. Please wait...", style="yellow"))
                return

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
                    max_tokens=256,
                    stop=["</s>", "<|user|>"],
                    echo=False,
                    temperature=0.3,  # Lower for safety
                    top_p=0.8,
                    repeat_penalty=1.1,
                )
            )

            # Extract the generated text
            bot_response = response['choices'][0]['text'].strip()

            # Show bot's response
            bot_text = Text()
            bot_text.append("🤖 BrainBot: ", style="bold cyan")
            bot_text.append(bot_response, style="white")
            self.chat_log.write(bot_text)
            self.chat_log.write("")

        except Exception as e:
            error_text = Text()
            error_text.append("❌ Oops! ", style="bold red")
            error_text.append(f"Something went wrong: {str(e)}", style="red")
            self.chat_log.write(error_text)

        finally:
            self.is_processing = False

    def show_crisis_card(self):
        """Display crisis intervention card."""
        crisis_content = get_crisis_card_content()

        self.chat_log.clear()

        crisis_text = Text()
        crisis_text.append("="*50 + "\n", style="bold red")
        crisis_text.append(f"{crisis_content['title']}\n\n", style="bold yellow")
        crisis_text.append(f"{crisis_content['message']}\n\n", style="white")

        for resource in crisis_content['resources']:
            crisis_text.append(f"  {resource}\n", style="cyan")

        crisis_text.append("\n" + "="*50, style="bold red")

        self.chat_log.write(crisis_text)
        self.input_box.disabled = True

    async def run_in_thread(self, func):
        """Run a blocking function in a thread to avoid freezing the UI."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, func)


def main():
    """Main entry point for BrainBot."""
    # Check Python version
    if sys.version_info < (3, 8):
        print("❌ BrainBot requires Python 3.8 or newer!")
        print("Please upgrade Python and try again.")
        sys.exit(1)

    # Create and run the app
    app = BrainBotApp()
    app.run()


if __name__ == "__main__":
    main()