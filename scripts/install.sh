#!/bin/bash

# BrainBot Installation Helper Script
# ==================================
# Additional installation utilities for BrainBot

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

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

# Install as systemd service
install_service() {
    print_section "Installing BrainBot as System Service"

    # Check if we're running as root or with sudo
    if [ "$EUID" -ne 0 ]; then
        echo -e "${RED}Please run this with sudo for service installation${NC}"
        exit 1
    fi

    # Get the actual user who ran sudo
    REAL_USER=${SUDO_USER:-$USER}
    REAL_HOME=$(getent passwd $REAL_USER | cut -d: -f6)
    BRAINBOT_DIR="$REAL_HOME/brainbot"

    echo -e "${CYAN}Installing for user: $REAL_USER${NC}"
    echo -e "${CYAN}BrainBot directory: $BRAINBOT_DIR${NC}"

    # Check if BrainBot directory exists
    if [ ! -d "$BRAINBOT_DIR" ]; then
        echo -e "${RED}❌ BrainBot directory not found at $BRAINBOT_DIR${NC}"
        echo -e "${YELLOW}Please run setup.sh first${NC}"
        exit 1
    fi

    # Create service file with correct paths
    SERVICE_FILE="/etc/systemd/system/brainbot.service"
    cat > "$SERVICE_FILE" << EOF
[Unit]
Description=BrainBot - Child's First Local AI Assistant
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$REAL_USER
Group=$REAL_USER
WorkingDirectory=$BRAINBOT_DIR
Environment=PATH=$BRAINBOT_DIR/venv/bin
ExecStartPre=/bin/sleep 10
ExecStart=$BRAINBOT_DIR/venv/bin/python $BRAINBOT_DIR/brain_bot.py
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=brainbot

# Resource limits to prevent system overload
MemoryMax=2G
CPUQuota=80%

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=$REAL_HOME/.cache

[Install]
WantedBy=multi-user.target
EOF

    check_success "Service file creation"

    # Reload systemd and enable service
    systemctl daemon-reload
    check_success "Systemd reload"

    systemctl enable brainbot.service
    check_success "Service enable"

    echo -e "${GREEN}🎉 BrainBot service installed successfully!${NC}"
    echo -e "${CYAN}Commands:${NC}"
    echo -e "${YELLOW}  sudo systemctl start brainbot    # Start BrainBot${NC}"
    echo -e "${YELLOW}  sudo systemctl stop brainbot     # Stop BrainBot${NC}"
    echo -e "${YELLOW}  sudo systemctl status brainbot   # Check status${NC}"
    echo -e "${YELLOW}  journalctl -u brainbot -f        # View logs${NC}"
}

# Remove systemd service
remove_service() {
    print_section "Removing BrainBot System Service"

    if [ "$EUID" -ne 0 ]; then
        echo -e "${RED}Please run this with sudo for service removal${NC}"
        exit 1
    fi

    # Stop and disable service
    systemctl stop brainbot.service 2>/dev/null || true
    systemctl disable brainbot.service 2>/dev/null || true

    # Remove service file
    rm -f /etc/systemd/system/brainbot.service

    # Reload systemd
    systemctl daemon-reload
    systemctl reset-failed

    echo -e "${GREEN}✅ BrainBot service removed${NC}"
}

# Update BrainBot
update_brainbot() {
    print_section "Updating BrainBot"

    # Check if we're in a git repository
    if [ -d ".git" ]; then
        echo -e "${CYAN}Pulling latest changes...${NC}"
        git pull origin main
        check_success "Git pull"

        # Activate virtual environment and update dependencies
        if [ -f "venv/bin/activate" ]; then
            source venv/bin/activate
            pip install --upgrade -r requirements.txt
            check_success "Dependencies update"
            deactivate
        fi

        echo -e "${GREEN}✅ BrainBot updated successfully!${NC}"
    else
        echo -e "${YELLOW}Not a git repository. Please download the latest version manually.${NC}"
    fi
}

# Check system compatibility
check_compatibility() {
    print_section "System Compatibility Check"

    echo -e "${CYAN}Checking system requirements...${NC}"

    # Check Python version
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
        echo -e "${GREEN}✅ Python $PYTHON_VERSION${NC}"
    else
        echo -e "${RED}❌ Python3 not found${NC}"
    fi

    # Check memory
    TOTAL_MEM=$(free -m | grep '^Mem:' | awk '{print $2}')
    if [ "$TOTAL_MEM" -ge 1024 ]; then
        echo -e "${GREEN}✅ Memory: ${TOTAL_MEM}MB${NC}"
    else
        echo -e "${YELLOW}⚠️  Low memory: ${TOTAL_MEM}MB (recommended: 2GB+)${NC}"
    fi

    # Check available space
    AVAILABLE_SPACE=$(df -BM . | tail -1 | awk '{print $4}' | sed 's/M//')
    if [ "$AVAILABLE_SPACE" -ge 1024 ]; then
        echo -e "${GREEN}✅ Storage: ${AVAILABLE_SPACE}MB available${NC}"
    else
        echo -e "${RED}❌ Insufficient storage: ${AVAILABLE_SPACE}MB (need 1GB+)${NC}"
    fi

    # Check CPU cores
    CPU_CORES=$(nproc)
    echo -e "${GREEN}✅ CPU cores: $CPU_CORES${NC}"

    # Check if this is a Raspberry Pi
    if [ -f /proc/device-tree/model ]; then
        PI_MODEL=$(cat /proc/device-tree/model)
        echo -e "${GREEN}🍓 Device: $PI_MODEL${NC}"
    fi
}

# Show help
show_help() {
    echo -e "${CYAN}BrainBot Installation Helper${NC}"
    echo -e "${YELLOW}Usage: $0 [command]${NC}\n"
    echo -e "${CYAN}Commands:${NC}"
    echo -e "${YELLOW}  service-install    Install BrainBot as systemd service (requires sudo)${NC}"
    echo -e "${YELLOW}  service-remove     Remove BrainBot systemd service (requires sudo)${NC}"
    echo -e "${YELLOW}  update            Update BrainBot to latest version${NC}"
    echo -e "${YELLOW}  check             Check system compatibility${NC}"
    echo -e "${YELLOW}  help              Show this help message${NC}"
}

# Main script logic
case "$1" in
    service-install)
        install_service
        ;;
    service-remove)
        remove_service
        ;;
    update)
        update_brainbot
        ;;
    check)
        check_compatibility
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo -e "${RED}Unknown command: $1${NC}"
        show_help
        exit 1
        ;;
esac