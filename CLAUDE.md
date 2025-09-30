# CLAUDE.md - BrainBot Development Documentation

This file contains technical information for developers and maintainers working on BrainBot.

## Project Overview

BrainBot is a user-friendly, offline-first AI chat assistant built with Python and Textual. It targets Raspberry Pi deployment and prioritizes safety, simplicity, and educational value.

## Architecture

### Core Components

**Frontend: Textual TUI Framework**
- `brain_bot.py` - Main application with colorful terminal interface
- CSS styling for user-friendly visual design
- Async event handling for responsive UI

**AI Backend: llama-cpp-python**
- TinyLlama 1.1B Chat model (Q4_K_M quantization)
- Local inference only - no cloud dependencies
- Memory optimized for 2GB+ RAM systems

**Safety Layer**
- Built-in system prompt with safety guardrails
- No external content filtering (everything local)
- Appropriate response constraints

## Technical Specifications

### Model Details
- **Model**: TinyLlama-1.1B-Chat-v1.0
- **Format**: GGUF (Q4_K_M quantization)
- **Size**: ~670MB download
- **Context Window**: 2048 tokens
- **Memory Usage**: ~1.5GB when loaded

### System Requirements
- **Python**: 3.8+
- **RAM**: 2GB minimum, 4GB recommended
- **Storage**: 1GB for model + dependencies
- **CPU**: ARM64 or x86_64 (no GPU required)

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

**External Tools** (voice mode):
- whisper.cpp (compiled from source)
- Piper TTS (binary download)
- ALSA utilities (system package)

## Development Setup

### Local Development
```bash
git clone https://github.com/snedea/brainbot.git
cd brainbot

# Create development environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run in development mode
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
├── .env.example         # Voice configuration template
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
├── scripts/
│   ├── audio_check.py   # Audio device testing utility
│   ├── install.sh       # Advanced installation tools
│   └── brainbot.service # Systemd service definition
└── docs/
    ├── SETUP_PI.md        # Raspberry Pi specific guide
    ├── TROUBLESHOOTING.md # Common issues
    ├── VOICE_MODE.md      # Voice mode comprehensive guide
    ├── LAUNCH_GUIDE.md    # Voice quick start
    ├── DEPENDENCIES.md    # Voice dependencies reference
    ├── PREFLIGHT_CHECK.md # Voice setup checklist
    └── VOICE_SAMPLES.md   # Available voice models
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

#### State Machine Flow

```
     ┌────────────────────────────────────┐
     │          IDLE                      │
     │  • Wake word listener active       │
     │  • Waiting for "Computer"          │
     └───────────────┬────────────────────┘
                     │ wake word detected
                     ▼
     ┌────────────────────────────────────┐
     │        LISTENING                   │
     │  • Recording audio                 │
     │  • VAD-based silence detection     │
     └───────────────┬────────────────────┘
                     │ silence detected
                     ▼
     ┌────────────────────────────────────┐
     │      TRANSCRIBING                  │
     │  • Converting speech to text       │
     │  • whisper.cpp processing          │
     └───────────────┬────────────────────┘
                     │ text ready
                     ▼
     ┌────────────────────────────────────┐
     │        THINKING                    │
     │  • LLM generating response         │
     │  • TinyLlama inference             │
     └───────────────┬────────────────────┘
                     │ response ready
                     ▼
     ┌────────────────────────────────────┐
     │        SPEAKING                    │
     │  • Synthesizing speech             │
     │  • Playing audio output            │
     └───────────────┬────────────────────┘
                     │ playback complete
                     ▼
            [Return to IDLE]
```

#### Component Details

**1. Wake Word Detection** (`voice/wake_listener.py`)
- **Technology**: Porcupine by Picovoice
- **Always Listening**: Runs continuously with minimal CPU usage
- **Keyword**: "Computer" (default), customizable to 10+ built-in keywords
- **Latency**: <100ms detection time
- **Privacy**: Processing happens locally, API key only for SDK activation

**2. Audio Recording** (`voice/recorder.py`)
- **Technology**: PyAudio for ALSA integration
- **VAD**: Amplitude-based silence detection using `audioop.rms()`
- **Smart Stop**: Automatically stops after 2 seconds of silence
- **Format**: 16kHz, 16-bit PCM, mono
- **Max Duration**: 30 seconds (configurable)

**3. Speech-to-Text** (`stt/whisper_cli.py`)
- **Technology**: whisper.cpp (C++ implementation)
- **Model**: base.en (150MB, English-optimized)
- **Performance**: 2-4 seconds for 5 seconds of audio on Pi 4
- **Why whisper.cpp**: 5-10x faster than Python Whisper on CPU
- **Process**: Subprocess call to compiled binary

**4. LLM Integration** (`llm/llama_local.py`)
- **Model**: TinyLlama 1.1B Q4_K_M (shared with text mode)
- **Voice Prompt**: Optimized for concise spoken responses
- **Context**: Uses conversation history when available
- **Performance**: 3-5 seconds for 30-token response

**5. Text-to-Speech** (`tts/piper_cli.py`)
- **Technology**: Piper TTS by Rhasspy
- **Voice**: en_US-lessac-medium (60MB)
- **Quality**: Natural-sounding neural TTS
- **Performance**: 1-2 seconds synthesis time
- **Playback**: Pipes to ALSA's `aplay` utility

**6. Voice Agent** (`agent/voice_agent.py`)
- **Design**: State machine running as daemon thread
- **Callbacks**: Integrates with Textual TUI via VoiceHooks
- **Error Handling**: Transitions to ERROR state, recovers automatically
- **Lifecycle**: Starts with app, stops cleanly on exit

#### Integration with Main Application

The voice mode integrates into `brain_bot.py` through:

```python
# Command line flag
python brain_bot.py --voice

# Voice agent initialization
voice_agent = VoiceAgent(
    config=config,
    on_state_change=hooks.on_state_change,
    on_transcript=hooks.on_transcript,
    on_response=hooks.on_response
)

# Background operation
voice_agent.start()  # Non-blocking

# UI integration
class VoiceHooks:
    """Bridge between voice agent and Textual UI"""
    def on_state_change(state):
        # Update status display
    def on_transcript(text):
        # Add to chat log
    def on_response(text):
        # Display and speak
```

#### Configuration System

Voice mode uses environment-based configuration (`.env`):

```bash
# Wake word
PORCUPINE_ACCESS_KEY=your_key_here
PORCUPINE_KEYWORD=computer

# Model paths
WHISPER_BIN=/home/brainbot/homelab/whisper.cpp/build/bin/main
WHISPER_MODEL=/home/brainbot/homelab/whisper.cpp/models/ggml-base.en.bin
PIPER_BIN=/home/brainbot/piper/piper
PIPER_VOICE=/home/brainbot/piper/en_US-lessac-medium.onnx

# Performance tuning
LLAMA_THREADS=4
SILENCE_THRESHOLD=500
SILENCE_DURATION_SEC=2.0
```

Configuration is loaded via `config/env_loader.py` and validated through `config/voice_config.py` dataclass.

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

**Memory Usage**:
- Base BrainBot: ~100MB
- TinyLlama loaded: +1.5GB
- Porcupine: +10MB
- Audio buffers: +50MB
- Whisper (during STT): +300MB (temporary)
- **Total**: ~2GB active, 4GB recommended

#### Why This Architecture?

**PyAudio over pvrecorder**:
- More widely supported on Raspberry Pi
- Direct ALSA integration
- Handles both recording and playback

**Amplitude VAD over WebRTC VAD**:
- No compilation required
- Simpler implementation
- Lower latency
- Fewer dependencies
- Sufficient for quiet home environments

**whisper.cpp over OpenAI Whisper (Python)**:
- 5-10x faster on CPU
- Lower memory footprint
- Optimized for edge devices
- Better for real-time use

**Piper over festival/espeak**:
- Superior voice quality
- Neural TTS model
- Easy voice model swapping
- Faster than cloud APIs

**External binaries over Python packages**:
- Better performance on constrained hardware
- Lower memory usage
- Easier to optimize per-platform
- Simpler dependency management

#### Testing Voice Mode

```bash
# Test audio devices
python brain_bot.py --test-audio

# Test individual components
python -c "from voice.wake_listener import WakeWordListener; ..."

# Full integration test
python brain_bot.py --voice
# Say "Computer"
# Say "What is two plus two?"
# Verify response
```

## Platform-Specific Optimizations

### Raspberry Pi 4
- **Memory Management**: Configured for 2GB models
- **CPU Threading**: Optimized for 4-core ARM Cortex-A72
- **Storage**: Model cached to ~/.cache/brainbot
- **Service Integration**: Systemd service for background operation

### macOS/Linux/Windows
- **Cross-platform compatibility** via Python
- **Virtual environment isolation**
- **Automatic platform detection** in setup.sh

## Performance Tuning

### Model Parameters
```python
# Configurable in brain_bot.py
Llama(
    model_path=str(self.model_path),
    n_ctx=2048,        # Context window - reduce for less RAM usage
    n_threads=4,       # CPU threads - match your core count
    n_gpu_layers=0,    # CPU only for compatibility
    temperature=0.7,   # Creativity vs consistency
    verbose=False      # Quiet mode
)
```

### Memory Optimization
- **Swap configuration** recommended for Pi deployments
- **Model quantization** reduces memory footprint by 70%
- **Async processing** prevents UI blocking

## Security Considerations

### Input Validation
- No arbitrary code execution
- Text-only interface limits attack surface
- Local processing only

### Model Safety
- Pre-configured safety prompt
- No internet access after initial download
- User-controlled environment

### File System Security
- Models cached in user directory only
- No system-level file access required
- Sandboxed execution environment

## Testing

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

### Platform Testing
- [ ] Raspberry Pi 4 (2GB/4GB/8GB models)
- [ ] Ubuntu 20.04+
- [ ] macOS 11+
- [ ] Windows 10/11 (WSL for voice mode)

## Deployment

### Raspberry Pi Production
1. Use setup.sh for automated installation
2. Configure systemd service for auto-start
3. Optimize memory settings for hardware
4. Set up desktop shortcuts for easy access

### Container Deployment (Future)
- Docker support could be added
- Would simplify cross-platform deployment
- Consider resource constraints for Pi deployment

## Contributing Guidelines

### Code Style
- Follow PEP 8 Python style guide
- Use type hints where appropriate
- Include docstrings for all functions
- Add inline comments for complex logic

### Pull Request Process
1. Fork the repository
2. Create feature branch
3. Test on Raspberry Pi if possible
4. Update documentation as needed
5. Submit PR with clear description

### Issue Reporting
- Include system information (OS, Python version, hardware)
- Provide full error messages
- Steps to reproduce
- Expected vs actual behavior

## Future Enhancements

### Completed Features ✅
- ~~**Voice Interface**~~: Speech-to-text and text-to-speech - **DONE in v2.0!**
  - Wake word detection with Porcupine
  - whisper.cpp STT
  - Piper TTS
  - Full offline operation

### Planned Features
- **Web UI Option**: Browser-based interface for touch devices
- **Model Options**: Support for different model sizes (7B, 13B variants)
- **Learning Analytics**: Track topics explored
- **Usage Controls**: Time limits, content filtering
- **Multi-language Voice**: Additional language models for voice mode
- **Custom Wake Words**: Easy training and integration of custom wake phrases
- **Voice Activity Visualization**: Real-time waveform display during recording
- **Conversation Persistence**: Save and resume voice conversations

### Technical Debt
- Better error handling for model download failures
- Improved chat history management
- Automated testing suite
- Performance monitoring
- Voice mode integration testing
- Documentation for custom voice model training

## Troubleshooting

### Common Development Issues

**Import Errors**
- Ensure virtual environment is activated
- Check Python version compatibility
- Verify all dependencies installed

**Model Download Failures**
- Check internet connection
- Clear model cache and retry
- Manual download fallback implemented

**Performance Issues**
- Monitor memory usage with htop
- Adjust model parameters for hardware
- Check CPU temperature on Pi

### Debugging Tools

**Enable Verbose Logging**
```python
# In brain_bot.py, change:
verbose=False
# to:
verbose=True
```

**Monitor Resources**
```bash
# Memory usage
free -h

# CPU usage
htop

# Disk space
df -h
```

## License and Attribution

- **License**: MIT License
- **Model**: TinyLlama (Apache 2.0)
- **Dependencies**: Various open-source licenses
- **Framework**: Textual (MIT)

This project demonstrates how modern AI can be made accessible, safe, and educational while maintaining complete privacy and user control.