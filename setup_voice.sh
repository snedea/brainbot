#!/bin/bash
# setup_voice.sh - Automated setup for BrainBot voice mode
# =========================================================
# This script installs all external dependencies for voice mode:
# - whisper.cpp for speech-to-text
# - Piper for text-to-speech
# - Required system packages

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}🎙️  BrainBot Voice Mode Setup${NC}"
echo "================================"
echo ""

# Function to check command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to print section headers
print_section() {
    echo -e "\n${BLUE}==== $1 ====${NC}"
}

# Function to check success
check_success() {
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ $1${NC}"
    else
        echo -e "${RED}❌ $1 failed${NC}"
        exit 1
    fi
}

# Detect architecture
ARCH=$(uname -m)
echo -e "${YELLOW}Detected architecture: $ARCH${NC}"

if [[ "$ARCH" != "aarch64" && "$ARCH" != "arm64" && "$ARCH" != "x86_64" ]]; then
    echo -e "${RED}⚠️  Unsupported architecture: $ARCH${NC}"
    echo "This script supports: aarch64 (Pi), arm64 (Mac), x86_64 (Intel/AMD)"
    exit 1
fi

# 1. Create necessary directories
print_section "Creating directories"
mkdir -p ~/homelab
mkdir -p ~/piper
mkdir -p /tmp/brainbot
check_success "Directory creation"

# 2. Install system dependencies
print_section "Installing system packages"
echo -e "${YELLOW}This will require sudo access...${NC}"

if command_exists apt-get; then
    sudo apt-get update
    sudo apt-get install -y \
        build-essential cmake git \
        python3-dev python3-venv \
        portaudio19-dev libsndfile1 \
        ffmpeg sox alsa-utils \
        wget curl
    check_success "System packages installed"
elif command_exists brew; then
    brew install cmake portaudio sox ffmpeg
    check_success "System packages installed (macOS)"
else
    echo -e "${RED}Package manager not found. Please install dependencies manually.${NC}"
    exit 1
fi

# 3. Install Python packages
print_section "Installing Python packages"
if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d ".venv" ]; then
    source .venv/bin/activate
else
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv venv
    source venv/bin/activate
fi

pip install --upgrade pip wheel setuptools
pip install -r requirements.txt
check_success "Python packages installed"

# 4. Build whisper.cpp
print_section "Setting up whisper.cpp"
WHISPER_DIR="$HOME/homelab/whisper.cpp"

if [ ! -d "$WHISPER_DIR" ]; then
    echo -e "${YELLOW}Cloning whisper.cpp...${NC}"
    cd ~/homelab
    git clone https://github.com/ggerganov/whisper.cpp.git
    cd whisper.cpp

    echo -e "${YELLOW}Building whisper.cpp...${NC}"
    mkdir -p build
    cd build
    cmake ..
    cmake --build . -j$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)
    check_success "whisper.cpp built"

    # Download base.en model (good balance for Pi)
    echo -e "${YELLOW}Downloading Whisper model (base.en ~150MB)...${NC}"
    cd "$WHISPER_DIR"
    bash ./models/download-ggml-model.sh base.en
    check_success "Whisper model downloaded"
else
    echo -e "${GREEN}✓ whisper.cpp already exists${NC}"
fi

# 5. Download Piper TTS
print_section "Setting up Piper TTS"
PIPER_DIR="$HOME/piper"
PIPER_BIN="$PIPER_DIR/piper"

if [ ! -f "$PIPER_BIN" ]; then
    echo -e "${YELLOW}Downloading Piper TTS...${NC}"
    cd "$PIPER_DIR"

    # Determine correct Piper binary
    if [[ "$ARCH" == "aarch64" || "$ARCH" == "arm64" ]]; then
        PIPER_ARCH="arm64"
    elif [[ "$ARCH" == "x86_64" ]]; then
        PIPER_ARCH="amd64"
    fi

    PIPER_VERSION="2023.11.14-2"
    PIPER_URL="https://github.com/rhasspy/piper/releases/download/${PIPER_VERSION}/piper_linux_${PIPER_ARCH}.tar.gz"

    wget -q --show-progress "$PIPER_URL" -O piper.tar.gz
    tar -xzf piper.tar.gz
    rm piper.tar.gz

    # Make binary executable
    chmod +x piper/piper
    mv piper/piper .
    mv piper/*.onnx . 2>/dev/null || true
    mv piper/*.json . 2>/dev/null || true
    rm -rf piper

    check_success "Piper binary installed"
else
    echo -e "${GREEN}✓ Piper already exists${NC}"
fi

# 6. Download Piper voice model
PIPER_VOICE="$PIPER_DIR/en_US-lessac-medium.onnx"
if [ ! -f "$PIPER_VOICE" ]; then
    echo -e "${YELLOW}Downloading Piper voice model (~60MB)...${NC}"
    cd "$PIPER_DIR"

    BASE_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium"
    wget -q --show-progress "${BASE_URL}/en_US-lessac-medium.onnx"
    wget -q --show-progress "${BASE_URL}/en_US-lessac-medium.onnx.json"

    check_success "Piper voice model downloaded"
else
    echo -e "${GREEN}✓ Piper voice model already exists${NC}"
fi

# 7. Check for TinyLlama model
print_section "Checking LLM model"
MODEL_PATH="$HOME/.cache/brainbot/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"

if [ ! -f "$MODEL_PATH" ]; then
    echo -e "${YELLOW}LLM model not found. It will be downloaded on first run of brain_bot.py${NC}"
else
    echo -e "${GREEN}✓ TinyLlama model exists${NC}"
fi

# 8. Create .env file if it doesn't exist
print_section "Creating configuration file"

if [ ! -f ".env" ]; then
    echo -e "${YELLOW}Creating .env from template...${NC}"
    cp .env.example .env
    echo -e "${GREEN}✓ Created .env${NC}"
    echo -e "${RED}⚠️  IMPORTANT: Edit .env and add your PORCUPINE_ACCESS_KEY${NC}"
    echo -e "   Get one free at: ${CYAN}https://console.picovoice.ai/${NC}"
else
    echo -e "${GREEN}✓ .env already exists${NC}"
fi

# 9. Test audio setup
print_section "Testing audio"

python3 << 'EOF'
try:
    import pyaudio
    p = pyaudio.PyAudio()
    device_count = p.get_device_count()
    print(f"✅ Found {device_count} audio devices")

    # Show input devices
    print("\nAvailable input devices:")
    for i in range(device_count):
        info = p.get_device_info_by_index(i)
        if info['maxInputChannels'] > 0:
            print(f"  [{i}] {info['name']}")

    p.terminate()
except Exception as e:
    print(f"⚠️  Audio test warning: {e}")
    print("You may need to configure audio devices manually")
EOF

# 10. Summary
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ Voice mode setup complete!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo ""
echo -e "1. ${CYAN}Get your Porcupine access key${NC}"
echo -e "   Visit: https://console.picovoice.ai/"
echo -e "   (Free for personal use)"
echo ""
echo -e "2. ${CYAN}Edit .env file${NC}"
echo -e "   nano .env"
echo -e "   Add your PORCUPINE_ACCESS_KEY"
echo ""
echo -e "3. ${CYAN}Test audio devices${NC}"
echo -e "   python3 brain_bot.py --test-audio"
echo ""
echo -e "4. ${CYAN}Run BrainBot with voice mode${NC}"
echo -e "   python3 brain_bot.py --voice"
echo ""
echo -e "5. ${CYAN}Say the wake word${NC}"
echo -e "   Say 'Computer' to activate voice interaction"
echo ""
echo -e "${YELLOW}Troubleshooting:${NC}"
echo -e "  • If audio doesn't work, check device permissions"
echo -e "  • For Pi: Add user to 'audio' group: sudo usermod -a -G audio \$USER"
echo -e "  • See VOICE_MODE.md for detailed documentation"
echo ""