# BrainBot Voice Mode - Dependencies Reference

## ✅ Required Python Packages

These are in `requirements.txt` and will be installed automatically:

```
pvporcupine==3.0.0       # Wake word detection
pyaudio==0.2.14          # Audio input/output
python-dotenv==1.0.0     # Environment configuration
```

**Install with**:
```bash
source /home/brainbot/brainbot/venv/bin/activate
pip install -r requirements.txt
```

---

## ❌ NOT Required (Common Confusion)

These packages are **NOT** used in our implementation:

- ❌ `pvrecorder` - We use PyAudio instead
- ❌ `webrtcvad` or `webrtcvad-wheels` - We use amplitude-based silence detection
- ❌ `whisper` (OpenAI Python package) - We use whisper.cpp binary
- ❌ `piper-tts` (Python package) - We use Piper binary

**Do not install these!** They will add unnecessary dependencies.

---

## 🔧 System Dependencies (Already Installed)

These should be installed via `setup_voice.sh`:

```bash
# Build tools
build-essential cmake git

# Audio libraries
portaudio19-dev libsndfile1 alsa-utils

# Media tools
ffmpeg sox
```

---

## 📦 External Tools (Binaries)

### 1. whisper.cpp
**Location**: `~/homelab/whisper.cpp/build/bin/main`
**Purpose**: Speech-to-text
**Installation**: Built from source by `setup_voice.sh`

### 2. Piper TTS
**Location**: `~/piper/piper/piper`
**Purpose**: Text-to-speech
**Installation**: Downloaded binary by `setup_voice.sh`

### 3. Voice Model
**Location**: `~/piper/en_US-lessac-medium.onnx`
**Purpose**: Piper voice data
**Installation**: Downloaded separately (60MB)

```bash
cd ~/piper
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json
```

---

## 🎯 Why This Architecture?

### We Use PyAudio Instead of pvrecorder

**Reasons**:
- ✅ More widely supported
- ✅ Easier to install on Raspberry Pi
- ✅ Direct ALSA integration
- ✅ Works with both recording and playback

### We Use Amplitude Detection Instead of WebRTC VAD

**Reasons**:
- ✅ No compilation required
- ✅ Simpler implementation
- ✅ Works well in quiet environments (typical use case)
- ✅ Lower latency
- ✅ Fewer dependencies

**Implementation**: `voice/recorder.py` uses `audioop.rms()` to detect silence.

### We Use CLI Tools Instead of Python Packages

**Whisper.cpp over OpenAI Whisper**:
- ✅ Much faster on CPU (optimized C++)
- ✅ Lower memory usage
- ✅ Better for Raspberry Pi

**Piper binary over Python TTS**:
- ✅ Faster inference
- ✅ Better voice quality
- ✅ Lower resource usage
- ✅ Easy to swap voice models

---

## 📋 Dependency Check Script

Test if all dependencies are correctly installed:

```bash
#!/bin/bash
echo "Checking BrainBot voice dependencies..."

# Python packages
python3 -c "import pvporcupine" && echo "✅ pvporcupine" || echo "❌ pvporcupine"
python3 -c "import pyaudio" && echo "✅ pyaudio" || echo "❌ pyaudio"
python3 -c "from dotenv import load_dotenv" && echo "✅ python-dotenv" || echo "❌ python-dotenv"

# Binaries
[ -f ~/homelab/whisper.cpp/build/bin/main ] && echo "✅ whisper.cpp" || echo "❌ whisper.cpp"
[ -f ~/piper/piper/piper ] && echo "✅ piper" || echo "❌ piper"

# Models
[ -f ~/piper/en_US-lessac-medium.onnx ] && echo "✅ voice model" || echo "❌ voice model"
[ -f ~/.cache/brainbot/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf ] && echo "✅ LLM model" || echo "❌ LLM model"

echo "✅ = installed, ❌ = missing"
```

---

## 🐛 Common Installation Issues

### PyAudio Installation Fails

**Error**: `fatal error: portaudio.h: No such file or directory`

**Fix**:
```bash
sudo apt-get install portaudio19-dev
pip install --force-reinstall pyaudio
```

### pvporcupine Installation Fails

**Error**: `error: externally-managed-environment`

**Fix**: Use virtual environment
```bash
source /home/brainbot/brainbot/venv/bin/activate
pip install pvporcupine
```

### Import Error After Installation

**Error**: `ModuleNotFoundError: No module named 'pvporcupine'`

**Fix**: Verify virtual environment is activated
```bash
which python3  # Should show path in venv/
pip list | grep pvporcupine  # Should show installed
```

---

## 📚 Version Compatibility

Tested on:
- **Python**: 3.8 - 3.11
- **Raspberry Pi OS**: Bullseye (Debian 11)
- **Architecture**: ARM64 (aarch64)

Also works on:
- Ubuntu 20.04+
- macOS 11+ (Intel & Apple Silicon)
- Windows 10/11 (via WSL2)

---

## 🔄 Updating Dependencies

```bash
# Update Python packages
source venv/bin/activate
pip install --upgrade -r requirements.txt

# Update whisper.cpp
cd ~/homelab/whisper.cpp
git pull
cmake --build build -j$(nproc)

# Update Piper (download new release)
cd ~/piper
wget <new_piper_release_url>
tar -xzf piper_*.tar.gz
```

---

## 📊 Memory Usage

Expected RAM usage with all components loaded:

- **Base BrainBot**: ~100 MB
- **TinyLlama model**: ~1.5 GB
- **Porcupine**: ~10 MB
- **Audio buffers**: ~50 MB
- **Whisper (during transcription)**: ~300 MB
- **Total**: ~2 GB (minimum), 3-4 GB recommended

---

**This document clarifies the actual dependencies used in the implemented voice mode.**

If you see conflicting information elsewhere, refer to this file as the authoritative source.