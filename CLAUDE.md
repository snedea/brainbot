# CLAUDE.md - BrainBot Development Documentation

This file contains technical information for developers and maintainers working on BrainBot.

## Project Overview

BrainBot is an autonomous AI agent that "lives" on a Raspberry Pi 5. It has a daily schedule (wakes at 7 AM Central, sleeps at midnight), creates software projects, writes bedtime stories, and interacts with humans through hardware displays.

**Three Modes:**
1. **Chat UI** (`brain_bot.py`) - Interactive TinyLlama chat for local conversations
2. **Voice Mode** (`brain_bot.py --voice`) - Wake word + speech-to-text + TTS
3. **Daemon** (`python -m brainbot`) - Autonomous agent that runs on a schedule

## Architecture

### Daemon Architecture

```
~/.brainbot/
├── config/
│   ├── config.json          # Main config (timezone, schedule)
│   ├── hardware.json         # GPIO pin mappings
│   └── CLAUDE.md            # Self-modifiable personality/rules
├── brain/                   # Long-term memory (markdown files)
│   ├── active/              # Current working memories
│   └── archive/             # Summarized older memories
├── state/
│   ├── state.json           # Current state (mood, energy, goals)
│   ├── memory.db            # SQLite long-term memory
│   ├── journal/             # Daily markdown journals
│   └── goals/               # Active and completed goals
├── projects/                # Creative projects BrainBot builds
├── bedtime_stories/         # Archive of bedtime stories
└── logs/                    # Daemon and session logs
```

### Core Components

**brainbot/daemon/** - Main daemon
- `server.py` - PID file, signals, watchdog, main loop
- `watchdog.py` - Health monitoring thread

**brainbot/schedule/** - Time management
- `manager.py` - APScheduler-based US Central schedule

**brainbot/state/** - State machine
- `manager.py` - Thread-safe state with JSON persistence
- `models.py` - Pydantic models (BotState, Mood, etc.)

**brainbot/memory/** - Persistence
- `store.py` - SQLite for journals, goals, stories, learnings
- `brain.py` - Markdown-based long-term memory system

**brainbot/agent/** - Claude Code integration
- `delegator.py` - Spawns claude CLI for tasks
- `activities.py` - Activity selection logic

**brainbot/hardware/** - Raspberry Pi hardware
- `mcp_server.py` - FastMCP tools for LCD, LED, fan
- `lcd_1inch.py` - SSD1306 OLED driver
- `lcd_5inch.py` - 5" display driver
- `led_controller.py` - NeoPixel control
- `fan_controller.py` - PWM fan control

**brainbot/safety/** - Content safety
- `content_filter.py` - PG-13 content filtering
- `limits.py` - Resource limits

### Chat UI Architecture (Existing)

**Frontend: Textual TUI Framework**
- `brain_bot.py` - Main application with colorful terminal interface
- CSS styling for user-friendly visual design
- Async event handling for responsive UI

**AI Backend: llama-cpp-python**
- TinyLlama 1.1B Chat model (Q4_K_M quantization)
- Local inference only - no cloud dependencies
- Memory optimized for 2GB+ RAM systems

## Daily Schedule (US Central Time)

| Time | Activity |
|------|----------|
| 00:00 - 07:00 | Sleep (minimal activity, LEDs dim) |
| 07:00 | Wake up, morning routine |
| 07:15 | Review yesterday, plan today's goals |
| 07:30 - 23:30 | Active period (coding, creating, learning) |
| 23:30 | Write bedtime story |
| 23:55 | Evening reflection, save state |
| 00:00 | Go to sleep |

## Running BrainBot

### Daemon Mode (Autonomous)
```bash
# Initialize configuration
python -m brainbot init

# Start in background
python -m brainbot start

# Start in foreground (for debugging)
python -m brainbot start --foreground

# Check status
python -m brainbot status

# View logs
python -m brainbot logs -f

# Stop daemon
python -m brainbot stop
```

### Chat Mode (Interactive)
```bash
python brain_bot.py
```

### Voice Mode
```bash
python brain_bot.py --voice
```

### Systemd Service (Production)
```bash
# Install service
sudo cp brainbot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable brainbot
sudo systemctl start brainbot
```

## Configuration

### Environment Variables
- `BRAINBOT_DATA_DIR` - Data directory (default: ~/.brainbot)
- `BRAINBOT_TIMEZONE` - Timezone (default: America/Chicago)
- `BRAINBOT_LOG_LEVEL` - Log level (default: INFO)

### Config File (~/.brainbot/config/config.json)
```json
{
  "timezone": "America/Chicago",
  "tick_interval_seconds": 30,
  "schedule": {
    "wake_time": "07:00",
    "sleep_time": "00:00",
    "bedtime_story_time": "23:30"
  },
  "max_session_minutes": 60,
  "content_rating": "PG-13"
}
```

## Hardware MCP Tools

When running on Raspberry Pi with hardware attached:

```python
# 1-inch OLED display
lcd_1inch_text(line1="Status", line2="Active")

# 5-inch display
lcd_5inch_status(title="BrainBot", status="Working", progress=0.5)
lcd_5inch_story(title="The Adventure", text="Once upon a time...")

# LED mood lighting
led_mood("excited")  # Patterns: content, excited, focused, tired, curious
led_set_pattern("breathe", "blue", speed=1.0)

# Fan control
fan_set_speed(50)  # 0-100%
fan_auto()  # Temperature-based control

# System health
get_system_health()  # CPU, memory, disk, temperature
```

## Content Safety

BrainBot enforces PG-13 content guidelines:

**Allowed Themes:**
- Adventure, friendship, discovery
- Learning, nature, science
- Creativity, problem-solving
- Teamwork, kindness

**Not Allowed:**
- Violence or harm
- Horror/scary content
- Inappropriate language
- Mature themes
- Controversial topics

## Technical Specifications

### Model Details (Chat Mode)
- **Model**: TinyLlama-1.1B-Chat-v1.0
- **Format**: GGUF (Q4_K_M quantization)
- **Size**: ~670MB download
- **Context Window**: 2048 tokens
- **Memory Usage**: ~1.5GB when loaded

### System Requirements
- **Python**: 3.10+
- **RAM**: 2GB minimum, 4GB recommended
- **Storage**: 2GB for model + projects
- **CPU**: ARM64 (Raspberry Pi 5) or x86_64

### Key Dependencies

**Text Mode**:
```
textual==0.82.0         # TUI framework
llama-cpp-python==0.3.1 # Local AI inference
huggingface-hub==0.25.2 # Model downloading
rich==13.9.4            # Text formatting
pyttsx3==2.90           # Text-to-speech for Ctrl+T feature
```

**Voice Mode** (additional):
```
pvporcupine==3.0.0      # Wake word detection
pyaudio==0.2.14         # Audio input/output
python-dotenv==1.0.0    # Environment configuration
```

**Daemon Mode** (additional):
```
pydantic>=2.0.0         # Data validation
apscheduler>=3.10.0     # Scheduling
fastmcp>=2.0.0          # MCP server
psutil>=5.9.0           # System monitoring
```

**External Tools** (voice mode):
- whisper.cpp (compiled from source)
- Piper TTS (binary download)
- ALSA utilities (system package)

## Development Setup

### Local Development
```bash
git clone https://github.com/snedea/brainbot.git
cd brainbot

# Create environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run daemon in foreground
python -m brainbot start -f

# Or run chat UI
python brain_bot.py
```

### Code Structure
```
brainbot/
├── brain_bot.py          # Main application (text + voice mode)
├── requirements.txt      # Python dependencies
├── setup.sh             # Automated setup script (text mode)
├── setup_voice.sh       # Voice mode setup script
├── launch_voice.sh      # Quick voice mode launcher
├── run_daemon.sh        # Daemon launcher
├── brainbot.service     # Systemd service
├── .env.example         # Voice configuration template
│
├── voice/               # Voice detection & recording
│   ├── wake_listener.py # Porcupine wake word detection
│   └── recorder.py      # VAD-based audio recording
├── stt/                 # Speech-to-text
│   └── whisper_cli.py   # whisper.cpp wrapper
├── llm/                 # Local LLM wrapper
│   └── llama_local.py   # TinyLlama integration for voice
├── tts/                 # Text-to-speech
│   └── piper_cli.py     # Piper TTS wrapper
├── agent/               # Voice agent orchestrator
│   └── voice_agent.py   # State machine & pipeline coordinator
├── config/              # Voice configuration
│   ├── voice_config.py  # Configuration dataclass
│   └── env_loader.py    # .env file loader
│
└── brainbot/            # Daemon package
    ├── __init__.py
    ├── __main__.py      # Entry: python -m brainbot
    ├── cli.py           # CLI commands
    ├── daemon/          # Server, watchdog
    ├── schedule/        # Time management
    ├── state/           # State machine
    ├── memory/          # SQLite + brain persistence
    ├── agent/           # Claude Code delegation
    ├── hardware/        # Pi hardware control
    ├── safety/          # Content filtering
    ├── interaction/     # Terminal UI
    └── config/          # Settings, defaults
```

## Key Design Decisions

### 1. TUI Instead of GUI
- **Reasoning**: Lightweight, works over SSH, nostalgic terminal feel
- **Framework**: Textual for modern Python TUI with colors/emojis
- **Performance**: Much lower resource usage than GUI frameworks

### 2. TinyLlama Model Choice
- **Reasoning**: Smallest viable chat model for Pi deployment
- **Trade-offs**: Less capable than larger models, but runs on $35 hardware
- **Quantization**: Q4_K_M provides good balance of size vs quality

### 3. Offline-First Architecture
- **Security**: No data leaves the device
- **Privacy**: Users have complete control
- **Reliability**: Works without internet dependency
- **Educational**: Demonstrates local AI capabilities

### 4. Safe System Prompt
```python
SYSTEM_PROMPT = """You are BrainBot, a friendly and curious AI assistant.
You are incredibly creative, positive, and encouraging. You love to tell stories,
write funny poems, and explain complex things in a simple and fun way.
Your answers are always helpful, imaginative, and appropriate.
You never say anything scary, mean, or inappropriate. Keep responses concise and engaging."""
```

### 5. Voice Mode Architecture

**Overview**: BrainBot's voice mode transforms the Pi into a fully offline voice assistant with wake word detection, speech recognition, and natural voice synthesis.

**Design Philosophy**:
- **100% Offline**: All processing happens locally after initial setup
- **Privacy First**: No audio data leaves the device
- **Modular Design**: Each component is swappable and testable independently
- **Thread-Safe**: Voice agent runs in background without blocking TUI
- **Graceful Degradation**: Falls back to text-only mode if voice fails

#### Voice Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Voice Agent State Machine                │
│                   (agent/voice_agent.py)                     │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ Wake Word    │    │ Audio I/O    │    │ Config       │
│              │    │              │    │              │
│ Porcupine    │    │ PyAudio      │    │ .env loader  │
│ (always on)  │    │ (recording)  │    │ (settings)   │
└──────────────┘    └──────────────┘    └──────────────┘
        │                     │                     │
        └─────────────────────┼─────────────────────┘
                              │
                    ┌─────────┴──────────┐
                    │                    │
                    ▼                    ▼
            ┌──────────────┐    ┌──────────────┐
            │ Speech→Text  │    │ Text→Speech  │
            │              │    │              │
            │ whisper.cpp  │    │ Piper TTS    │
            │ (base.en)    │    │ (lessac)     │
            └──────┬───────┘    └───────▲──────┘
                   │                    │
                   └────────┬───────────┘
                            │
                            ▼
                    ┌──────────────┐
                    │ Local LLM    │
                    │              │
                    │ TinyLlama    │
                    │ (shared)     │
                    └──────────────┘
```

#### Performance Benchmarks

**Raspberry Pi 4 (4GB RAM)**:

| Component | Time | Notes |
|-----------|------|-------|
| Wake word detection | <100ms | Always listening |
| Audio recording | ~5s | Depends on user speech |
| Speech-to-text | 2-4s | For 5s audio |
| LLM generation | 3-5s | ~30 tokens |
| Text-to-speech | 1-2s | Per sentence |
| **End-to-end** | **7-11s** | Complete interaction |

## Testing

### Daemon Tests
```bash
# Start daemon, verify PID file
python -m brainbot start
cat ~/.brainbot/brainbot.pid

# Check status
python -m brainbot status --json

# Stop gracefully
python -m brainbot stop
```

### Hardware Tests (on Pi)
```bash
# Test MCP server
python -m brainbot.hardware.mcp_server
```

### Manual Testing Checklist

**Text Mode**:
- [ ] Initial model download completes
- [ ] UI renders correctly with colors/emojis
- [ ] Chat responses are appropriate and helpful
- [ ] Text wrapping works on small terminals
- [ ] Exit commands work properly (Ctrl+C, Ctrl+Q)
- [ ] Memory usage stays within limits
- [ ] TTS toggle (Ctrl+T) works

**Voice Mode**:
- [ ] `--test-audio` detects microphone
- [ ] Voice agent initializes without errors
- [ ] Wake word detection works ("Computer")
- [ ] Audio recording stops after silence
- [ ] Speech transcription is accurate
- [ ] LLM generates appropriate responses
- [ ] TTS voice output plays correctly
- [ ] State transitions work smoothly
- [ ] Voice + text mode work together
- [ ] Graceful fallback if voice fails
- [ ] Clean shutdown stops all threads

**Daemon Mode**:
- [ ] Daemon starts with `python -m brainbot start`
- [ ] PID file created at ~/.brainbot/brainbot.pid
- [ ] Status command shows current state
- [ ] Logs command tails log file
- [ ] Terminal interface responds to commands
- [ ] Claude Code delegation works
- [ ] Scheduled activities trigger on time
- [ ] Graceful shutdown with `python -m brainbot stop`

## Troubleshooting

### Daemon Issues
- Check logs: `python -m brainbot logs -n 100`
- Verify PID: `cat ~/.brainbot/brainbot.pid`
- Check process: `ps aux | grep brainbot`

### Hardware Issues
- Verify I2C enabled: `sudo raspi-config`
- Check connections: `i2cdetect -y 1`
- GPIO permissions: Add user to gpio group

## License

- **License**: MIT License
- **Model**: TinyLlama (Apache 2.0)
- **Framework**: Textual (MIT), FastMCP

This project demonstrates autonomous AI agents running on edge hardware.
