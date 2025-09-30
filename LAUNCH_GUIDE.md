# 🚀 BrainBot Voice Mode - Launch Guide

**Quick start guide to get your voice assistant running in 5 minutes!**

---

## Quick Launch (Easiest Method)

```bash
cd /home/brainbot/homelab/brainbot
./launch_voice.sh
```

This automated script will:
1. ✅ Activate virtual environment
2. ✅ Install all Python packages
3. ✅ Download voice model
4. ✅ Test TTS
5. ✅ Check configuration
6. ✅ Test audio devices
7. ✅ Launch voice mode!

**First time only**: You'll need to add your Porcupine API key when prompted.

---

## Manual Setup (Step-by-Step)

### Step 1: Install Python Packages

```bash
cd /home/brainbot/homelab/brainbot
source /home/brainbot/brainbot/venv/bin/activate
pip install -r requirements.txt
```

### Step 2: Download Voice Model

```bash
cd ~/piper
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json
```

### Step 3: Test TTS Works

```bash
cd ~/piper
echo "Hello, I am BrainBot" | ./piper/piper -m en_US-lessac-medium.onnx -f - | aplay
```

You should hear BrainBot speak!

### Step 4: Get Porcupine API Key

1. Visit https://console.picovoice.ai/
2. Sign up (free for personal use)
3. Create an "Access Key"
4. Copy the key

### Step 5: Configure .env

```bash
cd /home/brainbot/homelab/brainbot
cp .env.example .env
nano .env
```

Add your API key:
```bash
PORCUPINE_ACCESS_KEY=your_key_here
```

Save and exit (Ctrl+O, Enter, Ctrl+X)

### Step 6: Test Audio

```bash
python3 brain_bot.py --test-audio
```

This will:
- List your microphones
- Record a 3-second test
- Save to `/tmp/brainbot_audio_test.wav`

Play it back:
```bash
aplay /tmp/brainbot_audio_test.wav
```

### Step 7: Launch Voice Mode! 🎉

```bash
python3 brain_bot.py --voice
```

Say **"Computer"** and start chatting!

---

## Troubleshooting

### "No module named 'pvporcupine'"

**Solution**:
```bash
source /home/brainbot/brainbot/venv/bin/activate
pip install -r requirements.txt
```

### "Piper binary not found"

**Check path**:
```bash
ls -la ~/piper/piper/piper
```

Should show the executable. If not, re-run `setup_voice.sh`.

### "Voice model not found"

**Download manually**:
```bash
cd ~/piper
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json
```

### Wake word not detecting

**Check**:
1. Microphone works: `arecord -d 3 test.wav && aplay test.wav`
2. API key is correct in `.env`
3. Speak clearly: "Computer" (not "hey computer")
4. Check logs in terminal for wake word detection messages

### No audio output

**Check ALSA**:
```bash
aplay -l  # List playback devices
alsamixer # Check volume levels
```

---

## Usage Tips

### Wake Word

Say **"Computer"** clearly and wait for the listening indicator.

### Voice Commands

After wake word:
- "What's 2 plus 2?"
- "Tell me a joke"
- "Explain how computers work"
- "Write a short poem about robots"

### Text Mode

You can still type normally in the chat interface while voice mode is active!

### Exit

Press `Ctrl+C` to exit cleanly.

---

## File Locations Reference

```
/home/brainbot/homelab/brainbot/          # Project directory
├── .env                                    # Your configuration
├── brain_bot.py                           # Main application
├── launch_voice.sh                        # Quick launcher
├── setup_voice.sh                         # Full installation
└── requirements.txt                       # Python packages

/home/brainbot/brainbot/venv/              # Virtual environment

/home/brainbot/piper/                      # Piper TTS
├── piper/piper                            # Binary
├── en_US-lessac-medium.onnx              # Voice model
└── en_US-lessac-medium.onnx.json         # Voice config

/home/brainbot/homelab/whisper.cpp/        # Speech-to-text
├── build/bin/main                         # Whisper binary
└── models/ggml-base.en.bin               # Whisper model

/home/brainbot/.cache/brainbot/            # AI model
└── tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf  # LLM model

/tmp/brainbot/                             # Temporary audio files
```

---

## Performance Expectations

On **Raspberry Pi 4 (4GB)**:

| Component | Time |
|-----------|------|
| Wake word detection | <100ms |
| Record speech (5s) | ~5s |
| Speech-to-text | 2-4s |
| LLM response | 3-5s |
| Text-to-speech | 1-2s |
| **Total** | **6-11s** |

First run is slower as models load into memory.

---

## Configuration Options

Edit `.env` to customize:

```bash
# Wake word
PORCUPINE_KEYWORD=computer  # or jarvis, alexa, etc.

# Audio device (from --test-audio)
MIC_INDEX=-1  # -1 = default

# Performance
LLAMA_THREADS=4  # Match your CPU cores

# Recording sensitivity
SILENCE_THRESHOLD=500  # Lower = more sensitive
SILENCE_DURATION_SEC=2.0  # Pause to stop recording
```

---

## Advanced: Different Voice Models

Browse voices: https://github.com/rhasspy/piper/blob/master/VOICES.md

Example - British voice:
```bash
cd ~/piper
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alba/medium/en_GB-alba-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alba/medium/en_GB-alba-medium.onnx.json

# Update .env
nano .env
# Change: PIPER_VOICE=/home/brainbot/piper/en_GB-alba-medium.onnx
```

---

## Getting Help

- **Documentation**: See `VOICE_MODE.md` for detailed info
- **Audio issues**: Run `python3 brain_bot.py --test-audio`
- **Check logs**: Terminal output shows detailed state transitions
- **GitHub Issues**: Report bugs or request features

---

## What's Next?

Once voice mode is working:

1. **Customize personality**: Edit `llm/llama_local.py` VOICE_SYSTEM_PROMPT
2. **Add custom wake words**: Train at https://console.picovoice.ai/
3. **Try different voices**: Download from Piper voices repository
4. **Optimize performance**: Adjust LLAMA_THREADS and models

---

**Enjoy your offline AI voice assistant! 🎙️🤖**