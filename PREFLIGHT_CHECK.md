# 🚀 BrainBot Voice Mode - Pre-Flight Checklist

**Complete this checklist before launching voice mode for the first time.**

---

## ✅ Pre-Flight Checklist

### 1. Python Environment

```bash
# Check Python version (need 3.8+)
python3 --version

# Check virtual environment exists
ls -la /home/brainbot/brainbot/venv/bin/activate

# Activate virtual environment
source /home/brainbot/brainbot/venv/bin/activate

# Verify it's activated (should show venv path)
which python3
```

**Expected**: Python 3.8+ and venv activated

---

### 2. Python Dependencies

```bash
# Install from requirements.txt
cd /home/brainbot/homelab/brainbot
pip install -r requirements.txt

# Verify installations
python3 << EOF
import sys
try:
    import pvporcupine
    print("✅ pvporcupine installed")
except ImportError:
    print("❌ pvporcupine MISSING")
    sys.exit(1)

try:
    import pyaudio
    print("✅ pyaudio installed")
except ImportError:
    print("❌ pyaudio MISSING")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    print("✅ python-dotenv installed")
except ImportError:
    print("❌ python-dotenv MISSING")
    sys.exit(1)

print("\n✅ All Python packages installed correctly!")
EOF
```

**Expected**: All three packages show ✅

---

### 3. External Tools

```bash
# Check whisper.cpp
ls -lh ~/homelab/whisper.cpp/build/bin/main
~/homelab/whisper.cpp/build/bin/main -h 2>&1 | head -3

# Check Piper
ls -lh ~/piper/piper/piper
~/piper/piper/piper --version

# Check whisper model
ls -lh ~/homelab/whisper.cpp/models/ggml-base.en.bin

# Check TinyLlama model
ls -lh ~/.cache/brainbot/*.gguf
```

**Expected**: All files exist and binaries show version info

---

### 4. Voice Model

```bash
# Check if voice model exists
ls -lh ~/piper/en_US-lessac-medium.onnx 2>/dev/null

# If missing, download it:
cd ~/piper
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json

# Verify download
ls -lh ~/piper/en_US-lessac-medium.onnx
```

**Expected**: ~60MB .onnx file and .json config

---

### 5. Test Piper TTS

```bash
cd ~/piper
echo "BrainBot is ready for voice mode" | ./piper/piper -m en_US-lessac-medium.onnx -f - | aplay
```

**Expected**: You should hear the spoken message

---

### 6. Environment Configuration

```bash
cd /home/brainbot/homelab/brainbot

# Create .env if it doesn't exist
if [ ! -f .env ]; then
    cp .env.example .env
    echo "✅ Created .env from template"
else
    echo "✅ .env already exists"
fi

# Check Porcupine key is set
if grep -q "YOUR_ACCESS_KEY_HERE" .env; then
    echo "❌ PORCUPINE_ACCESS_KEY not configured"
    echo "   1. Get key from https://console.picovoice.ai/"
    echo "   2. Edit .env: nano .env"
    echo "   3. Replace YOUR_ACCESS_KEY_HERE with your actual key"
    exit 1
else
    echo "✅ Porcupine key configured"
fi

# Verify paths
grep "PIPER_BIN" .env
grep "PIPER_VOICE" .env
grep "WHISPER_BIN" .env
```

**Expected**:
- .env exists
- Porcupine key is set
- All paths point to correct locations

---

### 7. Audio Devices

```bash
# List available devices
python3 << EOF
import pyaudio
p = pyaudio.PyAudio()
print(f"Found {p.get_device_count()} audio devices:\n")

for i in range(p.get_device_count()):
    info = p.get_device_info_by_index(i)
    if info['maxInputChannels'] > 0:
        print(f"  Input  [{i}]: {info['name']}")
    if info['maxOutputChannels'] > 0:
        print(f"  Output [{i}]: {info['name']}")

p.terminate()
EOF

# Test audio recording
arecord -d 3 -f S16_LE -r 16000 /tmp/test.wav
echo "Recording 3 seconds... speak now!"
aplay /tmp/test.wav
echo "Did you hear your voice?"
```

**Expected**:
- At least one input device found
- Recording and playback work

---

### 8. Full Audio Test

```bash
cd /home/brainbot/homelab/brainbot
python3 brain_bot.py --test-audio
```

**Expected**:
- Lists devices
- Records 3-second clip
- Saves to `/tmp/brainbot_audio_test.wav`

---

## 🎯 Launch Command

If all checks pass:

```bash
cd /home/brainbot/homelab/brainbot
source /home/brainbot/brainbot/venv/bin/activate
python3 brain_bot.py --voice
```

Or use the automated launcher:

```bash
./launch_voice.sh
```

---

## 🔍 Expected Launch Output

```
🎙️  Initializing voice mode...
✅ Voice configuration loaded
Initializing voice agent components...
✓ WhisperSTT initialized
✓ LocalLLM initialized and loaded
✓ PiperTTS initialized
✓ VoiceRecorder initialized
✓ WakeWordListener started
All components initialized successfully
✅ Voice mode active! Say 'computer' to interact
   Text mode still works - just type normally

[BrainBot TUI interface appears]
```

---

## 🐛 If Launch Fails

### Error: "ModuleNotFoundError: No module named 'X'"

**Fix**: Virtual environment not activated
```bash
source /home/brainbot/brainbot/venv/bin/activate
python3 brain_bot.py --voice
```

### Error: "PORCUPINE_ACCESS_KEY is required"

**Fix**: Add API key to .env
```bash
nano .env
# Add your key, save and exit
python3 brain_bot.py --voice
```

### Error: "Piper binary not found"

**Fix**: Check path in .env
```bash
# Should be: PIPER_BIN=/home/brainbot/piper/piper/piper
ls -la ~/piper/piper/piper  # Verify it exists
nano .env  # Fix path if needed
```

### Error: "Voice model not found"

**Fix**: Download voice model
```bash
cd ~/piper
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json
```

### Error: Audio device errors

**Fix**: Check permissions
```bash
sudo usermod -a -G audio $USER
# Log out and back in
groups  # Verify 'audio' is listed
```

---

## ✅ Success Indicators

Once running, you should:

1. See "Voice mode active!" message
2. See state transitions in terminal (IDLE → LISTENING → etc.)
3. Hear confirmation beep/tone when wake word detected (optional)
4. Be able to say "Computer" and see "LISTENING" state
5. Hear spoken responses after questions

---

## 🎤 First Test Interaction

1. Say: **"Computer"**
2. Wait for listening indicator
3. Say: **"What is two plus two?"**
4. Wait 7-10 seconds
5. Hear BrainBot respond: "Two plus two equals four!"

**If this works, your voice assistant is fully operational! 🎉**

---

## 📊 Performance Metrics

On Raspberry Pi 4 (4GB), expect:

- Wake word latency: <100ms
- Recording: Real-time (stops 2s after silence)
- Transcription: 2-4 seconds
- LLM generation: 3-5 seconds
- TTS synthesis: 1-2 seconds
- **Total response time: 7-11 seconds**

First interaction may be slower as models load into RAM.

---

**Complete this checklist methodically to ensure smooth launch!**