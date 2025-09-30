# 🎙️ BrainBot Voice Mode

**Offline voice assistant with wake word detection, speech-to-text, and natural voice responses**

---

## Overview

BrainBot Voice Mode transforms your Raspberry Pi into a completely offline voice assistant. Say "Computer" to activate voice interaction, ask questions naturally, and receive spoken AI responses - all without internet connection or cloud services.

### Key Features

- ✅ **Completely Offline** - No data leaves your device
- 🎤 **Wake Word Detection** - "Computer" activates listening
- 🗣️ **Natural Speech** - High-quality voice synthesis with Piper
- 🧠 **Smart Responses** - Powered by local TinyLlama model
- 🔒 **Private & Secure** - All processing happens locally
- 🆓 **Free to Use** - No subscriptions or API costs

---

## Quick Start

### 1. Run Setup Script

```bash
cd /home/brainbot/homelab/brainbot
./setup_voice.sh
```

This installs:
- whisper.cpp for speech-to-text
- Piper for text-to-speech
- Required system packages

### 2. Get Porcupine API Key

1. Visit https://console.picovoice.ai/
2. Sign up (free for personal use)
3. Create an access key

### 3. Configure Environment

```bash
# Copy example configuration
cp .env.example .env

# Edit with your API key
nano .env
```

Add your Porcupine key:
```
PORCUPINE_ACCESS_KEY=your_key_here
```

### 4. Test Audio

```bash
python3 brain_bot.py --test-audio
```

This will:
- List available microphones
- Record a 3-second test clip
- Verify audio setup

### 5. Run Voice Mode

```bash
python3 brain_bot.py --voice
```

Say **"Computer"** to activate, then ask your question!

---

## Hardware Requirements

### Minimum (Raspberry Pi 4, 2GB RAM)
- ✅ Microphone (USB or 3.5mm)
- ✅ Speaker or headphones
- ✅ 8GB+ microSD card
- ⏱️ ~5-10 seconds response time

### Recommended (Raspberry Pi 4, 4GB+ RAM)
- ✅ USB microphone with good quality
- ✅ External speaker for better audio
- ✅ 16GB+ microSD card
- ⚡ ~3-5 seconds response time

### Also Works On
- 🍎 macOS (Intel & Apple Silicon)
- 🐧 Linux (x86_64 & ARM64)
- 🪟 Windows (with WSL)

---

## Configuration Guide

### Environment Variables

Edit `.env` to customize your setup:

```bash
# Wake Word Settings
PORCUPINE_ACCESS_KEY=your_key_here
PORCUPINE_KEYWORD=computer  # or: jarvis, alexa, americano, etc.

# Audio Device (from --test-audio)
MIC_INDEX=-1  # -1 = default, or specific device number

# Model Paths (auto-configured by setup_voice.sh)
WHISPER_BIN=/home/brainbot/homelab/whisper.cpp/build/bin/main
WHISPER_MODEL=/home/brainbot/homelab/whisper.cpp/models/ggml-base.en.bin
PIPER_BIN=/home/brainbot/piper/piper
PIPER_VOICE=/home/brainbot/piper/en_US-lessac-medium.onnx

# Performance Tuning
LLAMA_THREADS=4  # Match your Pi's CPU cores
SILENCE_THRESHOLD=500  # Lower = more sensitive
MAX_RECORDING_SEC=30
SILENCE_DURATION_SEC=2.0  # Stop after 2s of silence
```

### Available Wake Words

**Built-in keywords** (free, no training needed):
- `computer` ⭐ Recommended
- `jarvis`
- `alexa`
- `americano`
- `blueberry`
- `bumblebee`
- `grapefruit`
- `grasshopper`
- `picovoice`
- `porcupine`
- `terminator`

**Custom wake words**: Train your own at https://console.picovoice.ai/

---

## Architecture

### Voice Pipeline Flow

```
┌──────────────┐
│ Wake Word    │  "Computer" detected
│ (Porcupine)  │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Record Audio │  VAD-based silence detection
│ (PyAudio)    │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Speech→Text  │  whisper.cpp (base.en model)
│ (Whisper)    │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Generate AI  │  TinyLlama 1.1B
│ Response     │
│ (llama.cpp)  │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Text→Speech  │  Piper TTS
│ (Piper)      │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Play Audio   │  aplay
│ (ALSA)       │
└──────────────┘
```

### State Machine

```
IDLE ──wake──> LISTENING ──silence──> TRANSCRIBING
  ▲                                        │
  │                                        ▼
  │                                   THINKING
  │                                        │
  │                                        ▼
  └────────────────────────────────── SPEAKING
```

---

## Troubleshooting

### No Audio Devices Found

**Problem**: `pyaudio` can't find microphone

**Solutions**:
```bash
# Check ALSA devices
arecord -l

# Add user to audio group
sudo usermod -a -G audio $USER
# Then log out and back in

# Install audio drivers
sudo apt-get install alsa-utils pulseaudio

# Test recording
arecord -d 3 test.wav
aplay test.wav
```

### Wake Word Not Detecting

**Problem**: Says "Computer" but nothing happens

**Solutions**:

1. **Check API key**: Verify `PORCUPINE_ACCESS_KEY` in `.env`
2. **Test microphone**: Run `python3 brain_bot.py --test-audio`
3. **Adjust sensitivity**: In `.env`, lower threshold:
   ```bash
   SILENCE_THRESHOLD=300  # More sensitive
   ```
4. **Speak clearly**: Say "Computer" clearly, wait for response
5. **Check logs**: Voice agent prints state changes

### Slow Response Time

**Problem**: Takes 10+ seconds to respond

**Solutions**:

1. **Optimize threads**:
   ```bash
   # In .env, match your Pi's cores
   LLAMA_THREADS=4
   ```

2. **Use faster models**:
   ```bash
   # Smaller Whisper model (faster, less accurate)
   cd ~/homelab/whisper.cpp
   bash ./models/download-ggml-model.sh tiny.en
   # Update .env: WHISPER_MODEL=ggml-tiny.en.bin
   ```

3. **Monitor resources**:
   ```bash
   htop  # Check CPU/RAM usage
   ```

### Poor Speech Recognition

**Problem**: Whisper transcribes incorrectly

**Solutions**:

1. **Better microphone**: USB mic > built-in mic
2. **Reduce background noise**: Quiet environment
3. **Larger model**:
   ```bash
   cd ~/homelab/whisper.cpp
   bash ./models/download-ggml-model.sh small.en
   # Update .env: WHISPER_MODEL=ggml-small.en.bin
   ```

### TTS Sounds Robotic

**Problem**: Voice synthesis sounds unnatural

**Solutions**:

1. **Try different voice**:
   ```bash
   cd ~/piper
   # Download alternative voices from:
   # https://github.com/rhasspy/piper/blob/master/VOICES.md

   # Example: British English
   wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alba/medium/en_GB-alba-medium.onnx

   # Update .env:
   PIPER_VOICE=/home/brainbot/piper/en_GB-alba-medium.onnx
   ```

2. **Higher quality model**: Use `high` instead of `medium` voices

---

## Performance Benchmarks

Tested on **Raspberry Pi 4 (4GB RAM)**:

| Component | Model | Time | Notes |
|-----------|-------|------|-------|
| Wake Word | Porcupine | <100ms | Always listening |
| Speech→Text | Whisper base.en | 2-4s | For 5s audio |
| LLM | TinyLlama 1.1B | 3-5s | ~30 tokens |
| Text→Speech | Piper medium | 1-2s | Per sentence |
| **Total** | **Full pipeline** | **6-11s** | End-to-end |

### Optimization Tips

**Faster (less quality)**:
- Whisper: tiny.en model
- LLM: Reduce max_tokens
- Piper: low quality voice

**Slower (better quality)**:
- Whisper: small.en model
- LLM: More context
- Piper: high quality voice

---

## Example Interactions

```
You: "Computer"
🎤 [Wake word detected]

You: "What's the weather like?"
👂 [Recording... silence detected]
🔄 [Transcribing speech...]
🧠 [Generating response...]
🗣️ BrainBot: "I'm a local AI without internet access, so I can't check
    the current weather. But I can help you with many other things like
    answering questions, writing stories, or solving problems!"

You: "Tell me a joke"
👂 [Recording...]
🔄 [Transcribing...]
🧠 [Generating...]
🗣️ BrainBot: "Why did the robot go to school? To improve its
    AI-Q! Get it? Like IQ but for AI!"
```

---

## Development

### Module Structure

```
brainbot/
├── config/
│   ├── voice_config.py      # Configuration dataclass
│   └── env_loader.py         # .env file loader
├── voice/
│   ├── wake_listener.py      # Porcupine wake word
│   └── recorder.py           # VAD-based recording
├── stt/
│   └── whisper_cli.py        # whisper.cpp wrapper
├── llm/
│   └── llama_local.py        # llama.cpp wrapper
├── tts/
│   └── piper_cli.py          # Piper TTS wrapper
└── agent/
    └── voice_agent.py        # State machine orchestrator
```

### Adding Custom Voices

1. Browse available voices: https://github.com/rhasspy/piper/blob/master/VOICES.md
2. Download `.onnx` and `.onnx.json` files
3. Update `.env` with new path
4. Restart BrainBot

### Testing Components

```python
# Test wake word detection
from config import load_voice_config
from voice.wake_listener import WakeWordListener

config = load_voice_config()
listener = WakeWordListener(config, lambda: print("Wake!"))
listener.start()

# Test speech recognition
from stt.whisper_cli import WhisperSTT
stt = WhisperSTT(config)
result = stt.transcribe("audio.wav")
print(result.text)

# Test text-to-speech
from tts.piper_cli import PiperTTS
tts = PiperTTS(config)
tts.speak("Hello world!")
```

---

## FAQ

**Q: Does it work offline?**
A: Yes! After initial setup, everything runs locally.

**Q: Can I change the wake word?**
A: Yes, edit `PORCUPINE_KEYWORD` in `.env` or train a custom one.

**Q: How much RAM does it need?**
A: Minimum 2GB, recommended 4GB+

**Q: Can I use it while typing?**
A: Yes! Voice and text modes work simultaneously.

**Q: Is it always listening?**
A: Only for the wake word. Audio is processed locally.

**Q: Can I run it 24/7?**
A: Yes, it's designed for continuous operation.

**Q: What languages are supported?**
A: English by default. Whisper supports 90+ languages (download other models).

**Q: Can I customize the AI personality?**
A: Yes, edit `VOICE_SYSTEM_PROMPT` in `llm/llama_local.py`

---

## Resources

- **Porcupine Console**: https://console.picovoice.ai/
- **Whisper.cpp**: https://github.com/ggerganov/whisper.cpp
- **Piper TTS**: https://github.com/rhasspy/piper
- **Piper Voices**: https://github.com/rhasspy/piper/blob/master/VOICES.md
- **TinyLlama**: https://github.com/jzhang38/TinyLlama

---

## Contributing

Found a bug or have a feature request? Please open an issue on GitHub!

Want to add support for a new language or voice? PRs welcome!

---

## License

BrainBot Voice Mode follows the same MIT license as the main project.

External dependencies have their own licenses:
- Porcupine: Free for personal use (Apache 2.0 for evaluation)
- Whisper.cpp: MIT
- Piper: MIT
- TinyLlama: Apache 2.0

---

**Made with ❤️ for the Raspberry Pi community**