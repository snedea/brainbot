# 🍓 BrainBot Raspberry Pi Setup Guide

This guide will help you set up BrainBot on your Raspberry Pi for the best experience possible.

## 📋 Prerequisites

### Hardware Requirements
- **Raspberry Pi 4** (4GB RAM recommended, 2GB minimum)
- **MicroSD Card**: 32GB or larger (Class 10 or better)
- **Power Supply**: Official Pi power adapter recommended
- **Monitor/Display**: Any HDMI-compatible display
- **Keyboard**: USB or wireless keyboard
- **Internet Connection**: Required for initial setup only

### Software Requirements
- **Raspberry Pi OS**: Latest version (Bullseye or newer)
- **SSH Access**: Optional but recommended for remote setup

## 🚀 Quick Setup

### Method 1: Automated Setup (Recommended)

1. **Flash Raspberry Pi OS**:
   - Use [Raspberry Pi Imager](https://www.raspberrypi.org/software/)
   - Enable SSH and set username/password during imaging

2. **Connect and Update**:
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```

3. **Clone and Setup BrainBot**:
   ```bash
   git clone https://github.com/yourusername/brainbot.git
   cd brainbot
   ./setup.sh
   ```

4. **Run BrainBot**:
   ```bash
   ./run.sh
   ```

### Method 2: Manual Setup

If you prefer to install step by step:

1. **Install Dependencies**:
   ```bash
   sudo apt update
   sudo apt install -y python3 python3-pip python3-venv git build-essential cmake
   ```

2. **Clone Repository**:
   ```bash
   git clone https://github.com/yourusername/brainbot.git
   cd brainbot
   ```

3. **Create Virtual Environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

4. **Install Python Packages**:
   ```bash
   # Install numpy first to avoid compilation issues
   pip install numpy

   # Install llama-cpp-python with optimizations
   CMAKE_ARGS="-DLLAMA_BLAS=ON -DLLAMA_BLAS_VENDOR=OpenBLAS" pip install llama-cpp-python==0.3.1

   # Install other dependencies
   pip install textual==0.82.0 huggingface-hub==0.25.2 rich==13.9.4
   ```

## ⚡ Performance Optimization

### 1. Memory Configuration

Add these lines to `/boot/config.txt`:
```bash
# Increase GPU memory split (helps with overall performance)
gpu_mem=64

# Disable unused interfaces to save memory
dtparam=audio=off
```

### 2. CPU Governor
Set the CPU to performance mode:
```bash
echo 'performance' | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor
```

### 3. Swap Configuration
Increase swap size for better memory management:
```bash
sudo dphys-swapfile swapoff
sudo nano /etc/dphys-swapfile
# Change CONF_SWAPSIZE=100 to CONF_SWAPSIZE=1024
sudo dphys-swapfile setup
sudo dphys-swapfile swapon
```

### 4. System Optimization
```bash
# Disable unnecessary services
sudo systemctl disable bluetooth
sudo systemctl disable wifi-powersave@wlan0

# Enable memory overcommit
echo 'vm.overcommit_memory=1' | sudo tee -a /etc/sysctl.conf
```

## 🖥️ Display Configuration

### For Small Screens (7" displays and smaller)

1. **Increase Console Font Size**:
   ```bash
   sudo dpkg-reconfigure console-setup
   # Choose UTF-8, Latin1, Terminus, 16x32
   ```

2. **Optimize Terminal Settings**:
   ```bash
   # Add to ~/.bashrc
   export TERM=xterm-256color
   ```

### For Touchscreen Displays

1. **Install Virtual Keyboard** (optional):
   ```bash
   sudo apt install matchbox-keyboard
   ```

2. **Auto-rotate Configuration**:
   ```bash
   # Add to /boot/config.txt for 90-degree rotation
   display_rotate=1
   ```

## 🔄 Auto-Start on Boot

### Method 1: Desktop Auto-start

Create `~/.config/autostart/brainbot.desktop`:
```ini
[Desktop Entry]
Type=Application
Name=BrainBot
Exec=/home/pi/brainbot/run.sh
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
```

### Method 2: System Service (Background)

Install as a system service:
```bash
cd brainbot
sudo scripts/install.sh service-install
```

Control the service:
```bash
sudo systemctl start brainbot     # Start
sudo systemctl stop brainbot      # Stop
sudo systemctl status brainbot    # Check status
journalctl -u brainbot -f         # View logs
```

### Method 3: Console Auto-login + Auto-run

1. **Enable Auto-login**:
   ```bash
   sudo raspi-config
   # System Options > Boot / Auto Login > Console Autologin
   ```

2. **Add to ~/.bashrc**:
   ```bash
   # Auto-start BrainBot on login
   if [ -z "$SSH_CLIENT" ] && [ -z "$SSH_TTY" ]; then
       cd ~/brainbot && ./run.sh
   fi
   ```

## 🐛 Raspberry Pi Troubleshooting

### Common Issues and Solutions

#### 1. Model Download Fails
```bash
# Clear cache and retry
rm -rf ~/.cache/brainbot
cd brainbot && ./setup.sh
```

#### 2. Out of Memory Errors
```bash
# Check memory usage
free -h
# Increase swap or close other applications
sudo systemctl stop bluetooth
sudo systemctl stop cups
```

#### 3. Slow Performance
```bash
# Check CPU temperature
vcgencmd measure_temp

# If overheating (>80°C), improve cooling or reduce clock speed
echo 'arm_freq=1200' | sudo tee -a /boot/config.txt
```

#### 4. Compilation Errors
```bash
# Install missing build tools
sudo apt install -y build-essential cmake pkg-config
sudo apt install -y libopenblas-dev liblapack-dev gfortran
```

#### 5. Display Issues
```bash
# Force HDMI output
echo 'hdmi_force_hotplug=1' | sudo tee -a /boot/config.txt
echo 'hdmi_drive=2' | sudo tee -a /boot/config.txt
```

#### 6. Network Issues During Setup
```bash
# Configure DNS
echo 'nameserver 8.8.8.8' | sudo tee -a /etc/resolv.conf

# Test connection
ping -c 3 huggingface.co
```

### Performance Monitoring

Monitor BrainBot's performance:
```bash
# Check CPU usage
htop

# Monitor temperature
watch -n 2 vcgencmd measure_temp

# Check memory usage
free -h

# Monitor disk I/O
iotop
```

## 🎯 User-Friendly Setup Tips

### 1. Create Desktop Shortcut
The setup script automatically creates a desktop shortcut, but you can customize it:

```ini
[Desktop Entry]
Version=1.0
Type=Application
Name=🧠 BrainBot
Comment=Chat with your AI friend!
Exec=/home/pi/brainbot/run.sh
Icon=/home/pi/brainbot/icon.png
Terminal=true
Categories=Education;Science;
StartupWMClass=brainbot
```

### 2. Quick Start Guide

Create a file `START_BRAINBOT.txt` on the desktop:
```
🧠✨ How to Start BrainBot:

1. Double-click the BrainBot icon on desktop
2. Or open terminal and type: ./run.sh
3. Wait for BrainBot to say "ready to chat!"
4. Start asking questions!

🎮 Fun things to try:
- "Tell me a story about robots"
- "What's 25 + 17?"
- "How do airplanes fly?"
- "Write a funny poem"
```

### 3. Usage Monitoring

Add basic conversation logging:
```bash
# Log all conversations (optional)
mkdir -p ~/brainbot_logs
echo "BRAINBOT_LOG=~/brainbot_logs/chat.log" >> ~/.bashrc
```

## 🔧 Advanced Configuration

### Custom Model Settings

Edit `brain_bot.py` to adjust for your Pi's capabilities:

```python
# For Pi 4 with 8GB RAM
self.llm = await self.run_in_thread(
    lambda: Llama(
        model_path=str(self.model_path),
        n_ctx=4096,        # Larger context window
        n_threads=4,       # Use all CPU cores
        n_gpu_layers=0,    # CPU only
        verbose=False,
        seed=42,
        temperature=0.7,
        n_batch=512,       # Larger batch size
    )
)

# For Pi 4 with 4GB RAM (default settings)
# Use the existing configuration

# For Pi 4 with 2GB RAM
self.llm = await self.run_in_thread(
    lambda: Llama(
        model_path=str(self.model_path),
        n_ctx=1024,        # Smaller context window
        n_threads=2,       # Use fewer threads
        n_gpu_layers=0,    # CPU only
        verbose=False,
        seed=42,
        temperature=0.7,
        n_batch=128,       # Smaller batch size
    )
)
```

### Storage Optimization

Move model cache to USB drive (if needed):
```bash
# Mount USB drive
sudo mkdir /mnt/usb
sudo mount /dev/sda1 /mnt/usb

# Move cache
mv ~/.cache/brainbot /mnt/usb/brainbot
ln -s /mnt/usb/brainbot ~/.cache/brainbot
```

## 🎉 You're All Set!

Your BrainBot should now be running smoothly on your Raspberry Pi. The first model download will take about 10-15 minutes, but after that, everything runs offline and fast!

**Need help?** Check the main [troubleshooting guide](TROUBLESHOOTING.md) or open an issue on GitHub.