#!/bin/bash

# BrainBot Setup Script
# ===================
# One-command setup for BrainBot on Raspberry Pi and other Linux systems

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Fun banner
echo -e "${PURPLE}"
cat << "EOF"
    ____            _       ____        _
   | __ ) _ __ __ _(_)_ __ | __ )  ___ | |_
   |  _ \| '__/ _` | | '_ \|  _ \ / _ \| __|
   | |_) | | | (_| | | | | | |_) | (_) | |_
   |____/|_|  \__,_|_|_| |_|____/ \___/ \__|

   🧠✨ Your Child's First Local AI Assistant
EOF
echo -e "${NC}"

echo -e "${CYAN}Starting BrainBot setup...${NC}\n"

# Check if we're running on Raspberry Pi
PI_MODEL=""
if [ -f /proc/device-tree/model ]; then
    PI_MODEL=$(cat /proc/device-tree/model)
    echo -e "${GREEN}🍓 Detected: $PI_MODEL${NC}"
fi

# Function to print section headers
print_section() {
    echo -e "\n${BLUE}==== $1 ====${NC}"
}

# Function to check command success
check_success() {
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ $1 successful${NC}"
    else
        echo -e "${RED}❌ $1 failed${NC}"
        exit 1
    fi
}

# Check Python version
print_section "Checking Python Installation"
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    echo -e "${GREEN}🐍 Python $PYTHON_VERSION found${NC}"

    # Check if version is at least 3.8
    if python3 -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)"; then
        echo -e "${GREEN}✅ Python version is compatible${NC}"
    else
        echo -e "${RED}❌ Python 3.8+ required. Found: $PYTHON_VERSION${NC}"
        echo -e "${YELLOW}Please upgrade Python and try again${NC}"
        exit 1
    fi
else
    echo -e "${RED}❌ Python3 not found${NC}"
    echo -e "${YELLOW}Installing Python3...${NC}"

    # Try to install Python3 based on the system
    if command -v apt &> /dev/null; then
        sudo apt update
        sudo apt install -y python3 python3-pip python3-venv
        check_success "Python3 installation"
    elif command -v yum &> /dev/null; then
        sudo yum install -y python3 python3-pip
        check_success "Python3 installation"
    else
        echo -e "${RED}❌ Cannot auto-install Python. Please install Python 3.8+ manually${NC}"
        exit 1
    fi
fi

# Check for pip
print_section "Checking pip"
if python3 -m pip --version &> /dev/null; then
    echo -e "${GREEN}✅ pip is available${NC}"
else
    echo -e "${YELLOW}Installing pip...${NC}"
    if command -v apt &> /dev/null; then
        sudo apt install -y python3-pip
        check_success "pip installation"
    else
        python3 -m ensurepip --default-pip
        check_success "pip installation"
    fi
fi

# Install system dependencies for Raspberry Pi
if [[ "$PI_MODEL" == *"Raspberry Pi"* ]]; then
    print_section "Installing Raspberry Pi Dependencies"
    sudo apt update
    sudo apt install -y build-essential cmake pkg-config
    check_success "System dependencies installation"
fi

# Create virtual environment
print_section "Setting Up Virtual Environment"
if [ ! -d "venv" ]; then
    echo -e "${CYAN}Creating virtual environment...${NC}"
    python3 -m venv venv
    check_success "Virtual environment creation"
else
    echo -e "${YELLOW}Virtual environment already exists${NC}"
fi

# Activate virtual environment
echo -e "${CYAN}Activating virtual environment...${NC}"
source venv/bin/activate
check_success "Virtual environment activation"

# Upgrade pip in virtual environment
echo -e "${CYAN}Upgrading pip...${NC}"
python -m pip install --upgrade pip
check_success "pip upgrade"

# Install dependencies
print_section "Installing BrainBot Dependencies"
echo -e "${CYAN}Installing Python packages...${NC}"
echo -e "${YELLOW}This may take several minutes, especially on Raspberry Pi...${NC}"

# For Raspberry Pi, we might need to use different installation options
if [[ "$PI_MODEL" == *"Raspberry Pi"* ]]; then
    echo -e "${YELLOW}Raspberry Pi detected - using optimized installation...${NC}"

    # Install numpy first to avoid compilation issues
    pip install numpy

    # Install llama-cpp-python with specific options for Pi
    CMAKE_ARGS="-DLLAMA_BLAS=ON -DLLAMA_BLAS_VENDOR=OpenBLAS" pip install llama-cpp-python==0.3.1

    # Install other dependencies
    pip install textual==0.82.0 huggingface-hub==0.25.2 rich==13.9.4
else
    # Standard installation for other systems
    pip install -r requirements.txt
fi

check_success "Dependencies installation"

# Create run script
print_section "Creating Run Script"
cat > run.sh << 'EOF'
#!/bin/bash
# BrainBot Run Script

# Colors for output
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}🧠✨ Starting BrainBot...${NC}"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo -e "${RED}❌ Virtual environment not found. Please run setup.sh first.${NC}"
    exit 1
fi

# Activate virtual environment
source venv/bin/activate

# Run BrainBot
python brain_bot.py
EOF

chmod +x run.sh
echo -e "${GREEN}✅ Run script created${NC}"

# Create desktop shortcut for Raspberry Pi Desktop
if [[ "$PI_MODEL" == *"Raspberry Pi"* ]] && [ -d "$HOME/Desktop" ]; then
    print_section "Creating Desktop Shortcut"

    CURRENT_DIR=$(pwd)
    cat > "$HOME/Desktop/BrainBot.desktop" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=BrainBot
Comment=Your Child's First Local AI Assistant
Exec=$CURRENT_DIR/run.sh
Icon=utilities-terminal
Terminal=true
Categories=Education;Science;
StartupWMClass=brainbot
EOF

    chmod +x "$HOME/Desktop/BrainBot.desktop"
    echo -e "${GREEN}✅ Desktop shortcut created${NC}"
fi

# Test installation
print_section "Testing Installation"
echo -e "${CYAN}Testing BrainBot installation...${NC}"

# Quick test to see if all imports work
python -c "
import sys
sys.path.insert(0, '.')

try:
    from textual.app import App
    from llama_cpp import Llama
    from huggingface_hub import hf_hub_download
    from rich.text import Text
    print('✅ All dependencies imported successfully!')
except ImportError as e:
    print(f'❌ Import error: {e}')
    sys.exit(1)
"

check_success "Dependency test"

# Final instructions
print_section "Setup Complete!"
echo -e "${GREEN}🎉 BrainBot is ready to use!${NC}\n"

echo -e "${CYAN}To start BrainBot:${NC}"
echo -e "${YELLOW}  ./run.sh${NC}\n"

echo -e "${CYAN}First run will download the AI model (~670MB)${NC}"
echo -e "${CYAN}After that, BrainBot works completely offline!${NC}\n"

if [[ "$PI_MODEL" == *"Raspberry Pi"* ]]; then
    echo -e "${PURPLE}🍓 Raspberry Pi Tips:${NC}"
    echo -e "${YELLOW}  • Desktop shortcut created on Desktop${NC}"
    echo -e "${YELLOW}  • For best performance, close other applications${NC}"
    echo -e "${YELLOW}  • First model download may take 10-15 minutes${NC}\n"
fi

echo -e "${GREEN}Happy learning with BrainBot! 🚀${NC}"

# Deactivate virtual environment
deactivate