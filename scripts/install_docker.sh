#!/bin/bash
# Install Docker Engine in WSL2
# Run with: sudo bash scripts/install_docker.sh

set -e

echo "=== Installing Docker Engine in WSL2 ==="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run with sudo: sudo bash $0"
    exit 1
fi

# Get the actual user (not root)
ACTUAL_USER=${SUDO_USER:-$USER}

echo "[1/6] Updating package list..."
apt-get update

echo "[2/6] Installing prerequisites..."
apt-get install -y ca-certificates curl

echo "[3/6] Adding Docker GPG key..."
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

echo "[4/6] Adding Docker repository..."
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update

echo "[5/6] Installing Docker..."
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

echo "[6/6] Configuring Docker..."
# Add user to docker group
usermod -aG docker "$ACTUAL_USER"

# Start Docker service
service docker start

# Enable Docker to start on WSL launch
echo "# Start Docker daemon automatically" >> /etc/wsl.conf
echo "[boot]" >> /etc/wsl.conf
echo "command = service docker start" >> /etc/wsl.conf

echo ""
echo "=== Docker installed successfully! ==="
echo ""
echo "Next steps:"
echo "  1. Close this terminal and open a new one"
echo "  2. Run: docker run hello-world"
echo "  3. Then build BrainBot: cd /mnt/c/homelab/brainbot && docker compose up -d"
echo ""
