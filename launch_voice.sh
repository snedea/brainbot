#!/bin/bash
# launch_voice.sh - Quick setup and launch script for BrainBot Voice Mode
# ========================================================================

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}🎙️  BrainBot Voice Mode Quick Launch${NC}"
echo "======================================"
echo ""

# 1. Activate virtual environment
echo -e "${YELLOW}Step 1: Activating virtual environment...${NC}"
cd /home/brainbot/homelab/brainbot

if [ -f "/home/brainbot/brainbot/venv/bin/activate" ]; then
    source /home/brainbot/brainbot/venv/bin/activate
    echo -e "${GREEN}✅ Virtual environment activated${NC}"
else
    echo -e "${RED}❌ Virtual environment not found at /home/brainbot/brainbot/venv/${NC}"
    echo "Creating new virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
fi

# 2. Install Python packages
echo -e "\n${YELLOW}Step 2: Installing Python voice packages...${NC}"
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
echo -e "${GREEN}✅ Python packages installed${NC}"

# 3. Download Piper voice model if missing
echo -e "\n${YELLOW}Step 3: Checking Piper voice model...${NC}"
VOICE_FILE="$HOME/piper/en_US-lessac-medium.onnx"

if [ ! -f "$VOICE_FILE" ]; then
    echo "Downloading voice model (~60MB)..."
    cd ~/piper
    wget -q --show-progress https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
    wget -q --show-progress https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json
    echo -e "${GREEN}✅ Voice model downloaded${NC}"
else
    echo -e "${GREEN}✅ Voice model already exists${NC}"
fi

# 4. Test Piper
echo -e "\n${YELLOW}Step 4: Testing TTS...${NC}"
cd ~/piper
echo "BrainBot voice test" | ./piper/piper -m en_US-lessac-medium.onnx -f - | aplay 2>/dev/null
echo -e "${GREEN}✅ TTS working${NC}"

# 5. Check .env configuration
echo -e "\n${YELLOW}Step 5: Checking configuration...${NC}"
cd /home/brainbot/homelab/brainbot

if [ ! -f ".env" ]; then
    echo "Creating .env from template..."
    cp .env.example .env
    echo -e "${RED}⚠️  IMPORTANT: You need to add your PORCUPINE_ACCESS_KEY to .env${NC}"
    echo -e "   1. Get free key from: ${CYAN}https://console.picovoice.ai/${NC}"
    echo -e "   2. Edit .env: ${CYAN}nano .env${NC}"
    echo -e "   3. Add your key and save"
    echo ""
    read -p "Press Enter after you've added your key to .env..."
fi

# Check if key is set
if grep -q "YOUR_ACCESS_KEY_HERE" .env; then
    echo -e "${RED}❌ Porcupine key not configured in .env${NC}"
    echo "Please edit .env and add your access key, then run this script again."
    exit 1
fi

echo -e "${GREEN}✅ Configuration ready${NC}"

# 6. Test audio
echo -e "\n${YELLOW}Step 6: Testing audio devices...${NC}"
python3 -c "
import pyaudio
p = pyaudio.PyAudio()
count = p.get_device_count()
print(f'✅ Found {count} audio devices')

# Show input devices
for i in range(count):
    info = p.get_device_info_by_index(i)
    if info['maxInputChannels'] > 0:
        print(f\"  Input: [{i}] {info['name']}\")
p.terminate()
"

echo ""
read -p "Do you want to test audio recording? [Y/n]: " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    python3 brain_bot.py --test-audio
fi

# 7. Launch voice mode!
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ All checks passed! Launching voice mode...${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${CYAN}Say 'Computer' to activate voice interaction!${NC}"
echo -e "${CYAN}You can also type normally in the chat interface.${NC}"
echo -e "${CYAN}Press Ctrl+C to exit.${NC}"
echo ""
sleep 2

python3 brain_bot.py --voice