# 🎙️ Piper Voice Samples for BrainBot

**Listen before you download! Choose the perfect voice for your AI assistant.**

---

## 🎧 How to Listen to Samples

Visit the official Piper samples page:
👉 **https://rhasspy.github.io/piper-samples/**

Or test individual voices below using the download links + aplay.

---

## 🇺🇸 English (US) Voices - Recommended

### 1. **lessac** (Currently Configured) ⭐

**Quality**: low, medium, high
**Style**: Professional, clear, neutral
**Best for**: General assistant, educational content

**Sample Test**:
```bash
cd ~/piper
# Download if you haven't already
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json

# Test it
echo "Hello, I am BrainBot, your friendly AI assistant" | ./piper/piper -m en_US-lessac-medium.onnx -f - | aplay
```

**Download sizes**:
- Low: ~5MB
- Medium: ~15MB (~63MB on disk)
- High: ~32MB

---

### 2. **amy** (Female, Friendly)

**Quality**: low, medium
**Style**: Warm, friendly, conversational
**Best for**: Kid-friendly interactions, casual chat

**Download**:
```bash
cd ~/piper
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx.json

echo "Hi there! I love helping with homework and answering questions" | ./piper/piper -m en_US-amy-medium.onnx -f - | aplay
```

---

### 3. **ryan** (Male, Natural)

**Quality**: low, medium, high
**Style**: Natural, expressive, modern
**Best for**: Storytelling, engaging conversations

**Download**:
```bash
cd ~/piper
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/medium/en_US-ryan-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/medium/en_US-ryan-medium.onnx.json

echo "Let me tell you an interesting story about robots and artificial intelligence" | ./piper/piper -m en_US-ryan-medium.onnx -f - | aplay
```

---

### 4. **ljspeech** (Female, Classic)

**Quality**: medium, high
**Style**: Clear, professional, audiobook quality
**Best for**: Reading text, explanations

**Download**:
```bash
cd ~/piper
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ljspeech/medium/en_US-ljspeech-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ljspeech/medium/en_US-ljspeech-medium.onnx.json

echo "In the world of artificial intelligence, neural networks process information in fascinating ways" | ./piper/piper -m en_US-ljspeech-medium.onnx -f - | aplay
```

---

### 5. **joe** (Male, Casual)

**Quality**: medium
**Style**: Relaxed, casual, friendly
**Best for**: Informal conversations, jokes

**Download**:
```bash
cd ~/piper
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/joe/medium/en_US-joe-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/joe/medium/en_US-joe-medium.onnx.json

echo "Hey! Want to hear a joke? Why did the robot go to school? To improve its AI-Q!" | ./piper/piper -m en_US-joe-medium.onnx -f - | aplay
```

---

## 🇬🇧 English (British) Voices

### 6. **alba** (Female, Scottish)

**Quality**: medium
**Style**: Clear Scottish accent, friendly
**Best for**: Distinctive character, educational

**Download**:
```bash
cd ~/piper
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alba/medium/en_GB-alba-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alba/medium/en_GB-alba-medium.onnx.json

echo "Hello there! I'm here to help you learn and explore the fascinating world of science" | ./piper/piper -m en_GB-alba-medium.onnx -f - | aplay
```

---

### 7. **alan** (Male, British RP)

**Quality**: low, medium
**Style**: Received Pronunciation, professional
**Best for**: Formal assistant, educational content

**Download**:
```bash
cd ~/piper
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alan/medium/en_GB-alan-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alan/medium/en_GB-alan-medium.onnx.json

echo "Good day. I shall endeavour to provide you with accurate and helpful information" | ./piper/piper -m en_GB-alan-medium.onnx -f - | aplay
```

---

### 8. **jenny_dioco** (Female, British)

**Quality**: medium
**Style**: Modern British, clear
**Best for**: Conversational assistant

**Download**:
```bash
cd ~/piper
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/jenny_dioco/medium/en_GB-jenny_dioco-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/jenny_dioco/medium/en_GB-jenny_dioco-medium.onnx.json

echo "Hi! I'm BrainBot, and I'm excited to chat with you about anything you'd like to learn" | ./piper/piper -m en_GB-jenny_dioco-medium.onnx -f - | aplay
```

---

## 📊 Quality Level Guide

| Quality | Sample Rate | Parameters | File Size | Pi 4 Performance | Use Case |
|---------|-------------|------------|-----------|------------------|----------|
| **low** | 16kHz | 5-7M | ~5MB | ⚡ Very fast | Quick responses, testing |
| **medium** | 22kHz | 15-20M | ~15MB | ✅ Balanced | **Recommended** for Pi 4 |
| **high** | 22kHz | 28-32M | ~32MB | 🐌 Slower | Best quality, patience needed |

**Recommendation**: Use **medium** quality for the best balance on Raspberry Pi 4.

---

## 🔄 How to Change Voice

### Method 1: Edit .env

```bash
cd /home/brainbot/homelab/brainbot
nano .env

# Change the voice path:
PIPER_VOICE=/home/brainbot/piper/en_US-amy-medium.onnx

# Save and restart voice mode
```

### Method 2: Test Multiple Voices

```bash
cd ~/piper

# Download several voices you like
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/medium/en_US-ryan-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alba/medium/en_GB-alba-medium.onnx

# Download corresponding .json files
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx.json
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/medium/en_US-ryan-medium.onnx.json
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alba/medium/en_GB-alba-medium.onnx.json

# Test each one
echo "Testing Amy" | ./piper/piper -m en_US-amy-medium.onnx -f - | aplay
echo "Testing Ryan" | ./piper/piper -m en_US-ryan-medium.onnx -f - | aplay
echo "Testing Alba" | ./piper/piper -m en_GB-alba-medium.onnx -f - | aplay

# Choose your favorite and update .env!
```

---

## 🎭 Voice Personality Guide

| Voice | Gender | Accent | Best For | Personality |
|-------|--------|--------|----------|-------------|
| **lessac** | M | Neutral US | General use | Professional, clear |
| **amy** | F | US | Kids, casual | Warm, friendly |
| **ryan** | M | US | Stories | Expressive, natural |
| **ljspeech** | F | US | Reading | Clear, audiobook |
| **joe** | M | US | Casual chat | Relaxed, fun |
| **alba** | F | Scottish | Education | Distinctive, engaging |
| **alan** | M | British RP | Formal | Professional, proper |
| **jenny_dioco** | F | British | Conversation | Modern, clear |

---

## 🎪 Fun Test Phrases

Try these with different voices to hear personality:

```bash
# Storytelling test
echo "Once upon a time, in a land of circuits and code, lived a friendly robot named BrainBot" | ./piper/piper -m VOICE.onnx -f - | aplay

# Educational test
echo "The human brain contains approximately 86 billion neurons, each forming thousands of connections" | ./piper/piper -m VOICE.onnx -f - | aplay

# Joke test
echo "Why don't robots ever get tired? Because they have plenty of RAM to rest their memory!" | ./piper/piper -m VOICE.onnx -f - | aplay

# Friendly greeting
echo "Hello friend! I'm so excited to help you learn something amazing today!" | ./piper/piper -m VOICE.onnx -f - | aplay
```

---

## 📦 Complete Voice List by Language

For **all** available voices in 50+ languages:
👉 https://github.com/rhasspy/piper/blob/master/VOICES.md

**Available Languages**:
- Arabic, Catalan, Czech, Danish, Dutch, English, Finnish, French, German, Greek
- Hindi, Hungarian, Icelandic, Italian, Japanese, Kazakh, Korean, Nepali, Norwegian
- Polish, Portuguese, Romanian, Russian, Serbian, Spanish, Swedish, Turkish, Ukrainian
- Vietnamese, and more!

---

## 🔊 Quality Comparison Script

Create a script to test multiple voices quickly:

```bash
#!/bin/bash
# voice_compare.sh - Compare different Piper voices

cd ~/piper

VOICES=(
    "en_US-lessac-medium"
    "en_US-amy-medium"
    "en_US-ryan-medium"
    "en_GB-alba-medium"
)

TEXT="Hello, I am BrainBot, your offline AI assistant"

for voice in "${VOICES[@]}"; do
    echo "Playing: $voice"
    echo "$TEXT" | ./piper/piper -m ${voice}.onnx -f - | aplay
    sleep 1
done
```

---

## 💡 Pro Tips

1. **Download .json with .onnx**: Both files are needed!
2. **Start with medium**: Best balance for Pi 4
3. **Test before deciding**: Download 2-3, compare them
4. **Storage**: Each medium voice ~60-80MB on disk
5. **Switch anytime**: Just edit .env and restart

---

## 🎯 Quick Recommendation

**For BrainBot (kid-friendly AI assistant)**:

🥇 **First choice**: `en_US-amy-medium` (warm, friendly)
🥈 **Second choice**: `en_US-lessac-medium` (clear, professional)
🥉 **Third choice**: `en_GB-alba-medium` (distinctive, engaging)

**Download command**:
```bash
cd ~/piper
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx.json

# Test it
echo "Hi! I'm BrainBot and I'm excited to help you!" | ./piper/piper -m en_US-amy-medium.onnx -f - | aplay

# If you like it, update .env
nano /home/brainbot/homelab/brainbot/.env
# Change: PIPER_VOICE=/home/brainbot/piper/en_US-amy-medium.onnx
```

---

**Listen to samples at: https://rhasspy.github.io/piper-samples/**

**Choose your voice, download it, and make BrainBot sound perfect! 🎤**