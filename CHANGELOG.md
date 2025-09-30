# Changelog

All notable changes to BrainBot will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.0.0] - 2024-09-29

### 🎤 Major Feature: Offline Voice Assistant Mode

BrainBot now includes a complete offline voice assistant with wake word detection, speech recognition, and natural voice synthesis. Say "Computer" to activate your personal AI assistant!

### Added

#### Voice Mode Core Features
- **Complete Voice Pipeline**: End-to-end voice interaction with 100% offline processing
  - Wake word detection using Porcupine ("Computer" or custom keywords)
  - Speech-to-text via whisper.cpp (base.en model, 150MB)
  - Local LLM integration with TinyLlama 1.1B
  - Text-to-speech using Piper TTS (en_US-lessac-medium voice, 60MB)
  - Automatic silence detection for natural conversation flow

#### New Modules (11 Files)
- `voice/wake_listener.py` - Porcupine wake word detection thread
- `voice/recorder.py` - VAD-based audio recording with silence detection
- `stt/whisper_cli.py` - whisper.cpp subprocess wrapper
- `llm/llama_local.py` - TinyLlama wrapper optimized for voice responses
- `tts/piper_cli.py` - Piper TTS subprocess wrapper
- `agent/voice_agent.py` - State machine orchestrating complete voice pipeline
- `config/voice_config.py` - Configuration dataclass for voice settings
- `config/env_loader.py` - Environment variable loader with validation
- `scripts/audio_check.py` - Audio device testing utility

#### Setup & Launch Scripts
- `setup_voice.sh` - Automated installation of all voice dependencies
  - Compiles whisper.cpp from source
  - Downloads Piper TTS binary (architecture-specific)
  - Installs system packages (ALSA, PortAudio, FFmpeg, Sox)
  - Downloads voice models
  - Creates configuration template
  - Tests audio setup
- `launch_voice.sh` - Quick launcher with preflight checks
  - Activates virtual environment
  - Verifies all dependencies
  - Tests TTS and microphone
  - Launches voice mode

#### Configuration
- `.env.example` - Template for voice configuration
  - Porcupine API key setup
  - Wake word customization
  - Model path configuration
  - Performance tuning parameters
  - Audio device selection

#### Documentation (5 New Files)
- `VOICE_MODE.md` - Comprehensive voice mode guide
  - Architecture overview
  - Setup instructions
  - Configuration reference
  - Troubleshooting guide
  - Performance benchmarks
  - FAQ section
- `LAUNCH_GUIDE.md` - Quick start guide for voice mode
  - Step-by-step setup
  - Common issues and fixes
  - Usage tips
  - File locations reference
- `DEPENDENCIES.md` - Voice dependencies reference
  - Required Python packages
  - External tools explanation
  - Architecture rationale
  - Installation troubleshooting
- `PREFLIGHT_CHECK.md` - Pre-launch checklist
  - Systematic verification steps
  - Expected outputs
  - Error resolution
- `VOICE_SAMPLES.md` - Available voice models guide
  - Voice model samples
  - Download instructions
  - Quality comparisons

#### Integration with Main Application
- Added `--voice` flag to `brain_bot.py` for voice mode
- Added `--test-audio` flag for audio device testing
- Implemented `VoiceHooks` class for TUI integration
- Thread-safe voice agent running as daemon
- Real-time state display in status bar
- Graceful fallback to text-only mode on errors
- Clean shutdown handling for all voice threads

#### Dependencies
- **New Python packages**:
  - `pvporcupine==3.0.0` - Wake word detection SDK
  - `pyaudio==0.2.14` - Audio input/output
  - `python-dotenv==1.0.0` - Environment configuration
- **External tools**:
  - whisper.cpp (compiled from https://github.com/ggerganov/whisper.cpp)
  - Piper TTS binary (from https://github.com/rhasspy/piper)
  - Whisper base.en model (~150MB)
  - Piper voice model (~60MB)

### Changed

- **README.md**: Added prominent voice mode section with quick start
- **README.md**: Updated future ideas to mark voice mode as completed
- **README.md**: Enhanced "How to Use" with voice mode instructions
- **CLAUDE.md**: Added comprehensive voice mode architecture documentation
- **CLAUDE.md**: Updated code structure to include 11 new voice modules
- **CLAUDE.md**: Enhanced testing checklist with voice mode tests
- **CLAUDE.md**: Updated dependencies section with voice packages
- **requirements.txt**: Added voice mode Python dependencies

### Technical Details

#### Voice Mode Architecture

**State Machine Flow**:
```
IDLE → LISTENING → TRANSCRIBING → THINKING → SPEAKING → [back to IDLE]
```

**Component Stack**:
- **Wake Word**: Porcupine (always listening, <100ms latency)
- **Audio Recording**: PyAudio + amplitude-based VAD
- **STT**: whisper.cpp (5-10x faster than Python implementation)
- **LLM**: TinyLlama 1.1B Q4_K_M (shared with text mode)
- **TTS**: Piper neural TTS (high-quality voice synthesis)
- **Audio Output**: ALSA via `aplay`

**Design Decisions**:
- PyAudio over pvrecorder (better Pi compatibility)
- Amplitude VAD over WebRTC VAD (simpler, fewer dependencies)
- whisper.cpp over OpenAI Whisper (CPU optimization)
- Piper over festival/espeak (superior voice quality)
- External binaries over Python packages (performance on constrained hardware)

#### Performance Benchmarks (Raspberry Pi 4, 4GB RAM)

| Component | Time | Notes |
|-----------|------|-------|
| Wake word detection | <100ms | Always listening |
| Audio recording | ~5s | User-dependent |
| Speech-to-text | 2-4s | For 5s audio |
| LLM generation | 3-5s | ~30 tokens |
| Text-to-speech | 1-2s | Per sentence |
| **Total latency** | **7-11s** | Complete interaction |

**Memory Usage**:
- Base BrainBot: ~100MB
- TinyLlama loaded: +1.5GB
- Porcupine: +10MB
- Audio buffers: +50MB
- Whisper (during STT): +300MB (temporary)
- **Total**: ~2GB minimum, 4GB recommended

#### File Count
- **20 new/modified files**
- **~2,000 lines of new code**
- **5 comprehensive documentation files**
- **11 new Python modules**

### Privacy & Security

Voice mode maintains BrainBot's privacy-first approach:
- ✅ **100% Offline**: All audio processing happens locally after initial setup
- ✅ **No Cloud APIs**: No audio data sent to external servers
- ✅ **Local Storage**: Audio files stored in `/tmp/brainbot` (temporary)
- ✅ **API Key Privacy**: Porcupine key only used for local SDK activation
- ✅ **User Control**: Complete control over all voice data

### Known Limitations

- Voice mode requires microphone and speaker hardware
- Porcupine API key needed (free for personal use)
- English only by default (other languages supported with different models)
- Best performance on Raspberry Pi 4 with 4GB+ RAM
- Wake word detection requires clear pronunciation in quiet environment

### Migration Notes

**For Existing Users**:
1. Voice mode is completely optional - text mode unchanged
2. Run `./setup_voice.sh` to install voice dependencies
3. Get free Porcupine key from https://console.picovoice.ai/
4. Configure `.env` file with your API key
5. Launch with `python brain_bot.py --voice` or `./launch_voice.sh`

**Storage Requirements**:
- Voice mode adds ~200MB of models (whisper + piper)
- External tools: ~50MB (whisper.cpp + piper binaries)
- Total additional space: ~250MB

---

## [1.0.1] - 2024-09-29

### Changed
- Updated branding and demo screenshot
- Enhanced README with better descriptions

### Fixed
- Minor documentation corrections

---

## [1.0.0] - 2024-09-29

### Added
- Initial BrainBot release
- Colorful Textual TUI interface
- Local TinyLlama 1.1B integration
- Offline-first operation
- Text-to-speech toggle (Ctrl+T)
- Raspberry Pi optimization
- Desktop shortcut support
- Automated setup script
- Comprehensive documentation

### Features
- Kid-friendly AI assistant
- No internet required after setup
- Privacy-preserving local processing
- Educational and fun conversations
- Low-resource requirements

---

## Future Releases

### [2.1.0] - Planned
- Multi-language voice support
- Custom wake word training guide
- Voice activity visualization
- Conversation history for voice mode
- Web UI option

### [3.0.0] - Ideas
- Multiple model size options (7B, 13B)
- Learning analytics dashboard
- Parental controls and time limits
- Built-in educational games
- ASCII art generation

---

**Made with ❤️ for curious minds everywhere!**