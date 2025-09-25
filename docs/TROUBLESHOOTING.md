# 🔧 BrainBot Troubleshooting Guide

This guide covers common issues and their solutions. If you can't find your problem here, please open an issue on GitHub.

## 🚨 Common Issues

### 1. BrainBot Won't Start

#### Symptom: "ModuleNotFoundError" or import errors

**Solution 1: Check Virtual Environment**
```bash
# Make sure you're in the BrainBot directory
cd brainbot

# Activate virtual environment
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate     # Windows

# Verify installation
python -c "import textual; print('✅ Textual OK')"
python -c "import llama_cpp; print('✅ Llama-cpp OK')"
```

**Solution 2: Reinstall Dependencies**
```bash
# Activate virtual environment first
source venv/bin/activate

# Reinstall everything
pip install --force-reinstall -r requirements.txt
```

**Solution 3: Python Version Issue**
```bash
# Check Python version (needs 3.8+)
python --version

# If too old, install newer Python or try python3
python3 brain_bot.py
```

### 2. Model Download Issues

#### Symptom: "Failed to download model" or connection errors

**Solution 1: Check Internet Connection**
```bash
# Test connection to Hugging Face
ping huggingface.co

# If behind firewall, try different DNS
echo 'nameserver 8.8.8.8' | sudo tee -a /etc/resolv.conf
```

**Solution 2: Clear Cache and Retry**
```bash
# Remove existing cache
rm -rf ~/.cache/brainbot

# Try download again
python brain_bot.py
```

**Solution 3: Manual Download**
```bash
# Create cache directory
mkdir -p ~/.cache/brainbot

# Download manually using curl
curl -L "https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf" \
     -o ~/.cache/brainbot/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf
```

### 3. Memory Issues

#### Symptom: "Out of memory" or system freezing

**Solution 1: Check Available Memory**
```bash
# Check memory usage
free -h

# Check if swap is available
swapon --show
```

**Solution 2: Close Other Applications**
```bash
# Stop unnecessary services
sudo systemctl stop bluetooth  # On Pi
sudo systemctl stop cups       # Print service

# Close browser and other apps
```

**Solution 3: Adjust Model Settings**
Edit `brain_bot.py` and reduce memory usage:
```python
# Find this section and reduce values:
self.llm = await self.run_in_thread(
    lambda: Llama(
        model_path=str(self.model_path),
        n_ctx=1024,        # Reduced from 2048
        n_threads=2,       # Reduced from 4
        n_batch=128,       # Add this line
        # ... other settings
    )
)
```

### 4. Slow Performance

#### Symptom: BrainBot takes very long to respond

**Solution 1: Check CPU Usage**
```bash
# Monitor while BrainBot is thinking
htop
# or
top
```

**Solution 2: Optimize for Your Hardware**

**For Raspberry Pi:**
```python
# Edit brain_bot.py - use fewer threads
n_threads=2,  # or even 1 for Pi Zero
```

**For Older Computers:**
```python
# Reduce context window
n_ctx=1024,   # Instead of 2048
temperature=0.5,  # Less creative but faster
```

**Solution 3: Check Temperature (Raspberry Pi)**
```bash
# Check if CPU is throttling due to heat
vcgencmd measure_temp

# If over 80°C, improve cooling or reduce clock speed
echo 'arm_freq=1200' | sudo tee -a /boot/config.txt
```

### 5. Display/UI Issues

#### Symptom: Weird characters or broken layout

**Solution 1: Terminal Compatibility**
```bash
# Try different terminal
export TERM=xterm-256color

# Or use different terminal application
# Linux: gnome-terminal, xterm, konsole
# Mac: iTerm2, Terminal
# Windows: Windows Terminal, PowerShell
```

**Solution 2: Font Issues**
```bash
# Install better fonts (Linux)
sudo apt install fonts-dejavu-core fonts-liberation

# Check terminal font settings
# Use monospace fonts like "DejaVu Sans Mono"
```

**Solution 3: Screen Size Issues**
```bash
# For very small screens, try
export COLUMNS=80
export LINES=24
python brain_bot.py
```

### 6. Network/Firewall Issues

#### Symptom: Can't download model due to corporate firewall

**Solution 1: Configure Proxy**
```bash
# Set proxy environment variables
export HTTP_PROXY=http://your-proxy:8080
export HTTPS_PROXY=http://your-proxy:8080

# Then run setup
python brain_bot.py
```

**Solution 2: Download on Different Network**
1. Download the model file on a network without restrictions
2. Copy `~/.cache/brainbot/` folder to the restricted computer
3. BrainBot will use the existing model

### 7. Permission Issues

#### Symptom: "Permission denied" errors

**Solution 1: File Permissions**
```bash
# Make scripts executable
chmod +x setup.sh
chmod +x run.sh

# Fix directory permissions
chmod -R 755 brainbot/
```

**Solution 2: Virtual Environment Permissions**
```bash
# Recreate virtual environment
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 🐛 Platform-Specific Issues

### Windows Issues

#### Issue: "Microsoft Visual C++ 14.0 is required"
**Solution:**
1. Download Visual Studio Build Tools
2. Or install via chocolatey: `choco install visualstudio2022buildtools`
3. Or use pre-compiled wheels: `pip install --only-binary=all llama-cpp-python`

#### Issue: PowerShell execution policy
**Solution:**
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### macOS Issues

#### Issue: "clang: error" during compilation
**Solution:**
```bash
# Install Xcode command line tools
xcode-select --install

# Or install via Homebrew
brew install cmake
```

#### Issue: Python not found
**Solution:**
```bash
# Install Python via Homebrew
brew install python@3.11

# Use specific Python version
python3.11 -m venv venv
```

### Linux Issues

#### Issue: Missing system libraries
**Solution:**
```bash
# Ubuntu/Debian
sudo apt install build-essential cmake pkg-config
sudo apt install python3-dev libopenblas-dev

# CentOS/RHEL/Fedora
sudo yum groupinstall "Development Tools"
sudo yum install cmake python3-devel openblas-devel
```

## 🔍 Debugging Steps

### 1. Enable Verbose Logging

Edit `brain_bot.py` and change:
```python
# Find this line:
verbose=False,

# Change to:
verbose=True,
```

### 2. Test Individual Components

```python
# Test imports
python -c "
import textual
import llama_cpp
import huggingface_hub
import rich
print('✅ All imports successful')
"

# Test model loading
python -c "
from llama_cpp import Llama
import os
model_path = os.path.expanduser('~/.cache/brainbot/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf')
if os.path.exists(model_path):
    print('✅ Model file exists')
    # Test loading (this will take a while)
    llm = Llama(model_path=model_path, n_ctx=512, verbose=True)
    print('✅ Model loads successfully')
else:
    print('❌ Model file not found')
"
```

### 3. Check System Resources

```bash
# Monitor resources while running
htop  # or top

# Check disk space
df -h

# Check memory details
cat /proc/meminfo

# For Raspberry Pi, check throttling
vcgencmd get_throttled
```

## 🆘 Getting Help

### Before Reporting Issues

1. **Try the basic solutions** listed above
2. **Check your system meets requirements**:
   - Python 3.8+
   - 2GB RAM minimum
   - 1GB free disk space
3. **Gather system information**:
   ```bash
   python --version
   pip list | grep -E "(textual|llama|rich|huggingface)"
   uname -a  # Linux/Mac
   systeminfo  # Windows
   ```

### What to Include in Bug Reports

1. **Error message** (full text)
2. **System information** (OS, Python version, hardware)
3. **Steps to reproduce** the issue
4. **What you expected** vs. what happened
5. **Log output** (if available)

### Example Bug Report

```
Title: BrainBot crashes with "Out of memory" on Raspberry Pi 4

Environment:
- OS: Raspberry Pi OS Bullseye
- Hardware: Pi 4 Model B, 4GB RAM
- Python: 3.9.2
- BrainBot version: main branch

Steps to reproduce:
1. Run ./setup.sh
2. Start BrainBot with python brain_bot.py
3. Model downloads successfully
4. Ask any question
5. System freezes after "BrainBot is thinking..."

Error message:
[paste exact error here]

Expected: BrainBot should respond to questions
Actual: System becomes unresponsive

Additional info:
- free -h shows 3.2GB available before crash
- dmesg shows "Out of memory: Kill process..."
```

## ✅ Prevention Tips

1. **Keep system updated**:
   ```bash
   sudo apt update && sudo apt upgrade  # Linux
   brew update && brew upgrade          # Mac
   ```

2. **Monitor disk space** - BrainBot needs ~1GB
3. **Close unnecessary applications** before running BrainBot
4. **Use stable internet** for initial model download
5. **Regular cleanup**:
   ```bash
   # Clean pip cache
   pip cache purge

   # Clean system logs (Linux)
   sudo journalctl --vacuum-size=100M
   ```

---

**Still need help?**
- 📖 Check the [main README](../README.md)
- 🍓 See [Raspberry Pi specific guide](SETUP_PI.md)
- 🐛 [Open an issue on GitHub](https://github.com/yourusername/brainbot/issues)
- 💬 Join our discussions for questions