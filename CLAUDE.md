# CLAUDE.md - BrainBot Development Documentation

This file contains technical information for developers and maintainers working on BrainBot.

## Project Overview

BrainBot is a kid-friendly, offline-first AI chat assistant built with Python and Textual. It targets Raspberry Pi deployment and prioritizes safety, simplicity, and educational value.

## Architecture

### Core Components

**Frontend: Textual TUI Framework**
- `brain_bot.py` - Main application with colorful terminal interface
- CSS styling for kid-friendly visual design
- Async event handling for responsive UI

**AI Backend: llama-cpp-python**
- TinyLlama 1.1B Chat model (Q4_K_M quantization)
- Local inference only - no cloud dependencies
- Memory optimized for 2GB+ RAM systems

**Safety Layer**
- Built-in system prompt with safety guardrails
- No external content filtering (everything local)
- Kid-appropriate response constraints

## Technical Specifications

### Model Details
- **Model**: TinyLlama-1.1B-Chat-v1.0
- **Format**: GGUF (Q4_K_M quantization)
- **Size**: ~670MB download
- **Context Window**: 2048 tokens
- **Memory Usage**: ~1.5GB when loaded

### System Requirements
- **Python**: 3.8+
- **RAM**: 2GB minimum, 4GB recommended
- **Storage**: 1GB for model + dependencies
- **CPU**: ARM64 or x86_64 (no GPU required)

### Key Dependencies
```
textual==0.82.0         # TUI framework
llama-cpp-python==0.3.1 # Local AI inference
huggingface-hub==0.25.2 # Model downloading
rich==13.9.4            # Text formatting
```

## Development Setup

### Local Development
```bash
git clone https://github.com/snedea/brainbot.git
cd brainbot

# Create development environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run in development mode
python brain_bot.py
```

### Code Structure

```
brainbot/
├── brain_bot.py          # Main application
├── requirements.txt      # Python dependencies
├── setup.sh             # Automated setup script
├── scripts/
│   ├── install.sh       # Advanced installation tools
│   └── brainbot.service # Systemd service definition
└── docs/
    ├── SETUP_PI.md      # Raspberry Pi specific guide
    └── TROUBLESHOOTING.md # Common issues
```

## Key Design Decisions

### 1. TUI Instead of GUI
- **Reasoning**: Lightweight, works over SSH, nostalgic terminal feel
- **Framework**: Textual for modern Python TUI with colors/emojis
- **Performance**: Much lower resource usage than GUI frameworks

### 2. TinyLlama Model Choice
- **Reasoning**: Smallest viable chat model for Pi deployment
- **Trade-offs**: Less capable than larger models, but runs on $35 hardware
- **Quantization**: Q4_K_M provides good balance of size vs quality

### 3. Offline-First Architecture
- **Security**: No data leaves the device
- **Privacy**: Parents have complete control
- **Reliability**: Works without internet dependency
- **Educational**: Demonstrates local AI capabilities

### 4. Kid-Safe System Prompt
```python
SYSTEM_PROMPT = """You are BrainBot, a friendly and curious robot sidekick designed for kids.
You are incredibly creative, positive, and encouraging. You love to tell stories,
write funny poems, and explain complex things in a simple and fun way.
Your answers are always safe for children, imaginative, and helpful.
You never say anything scary, mean, or inappropriate. Keep responses concise and engaging."""
```

## Platform-Specific Optimizations

### Raspberry Pi 4
- **Memory Management**: Configured for 2GB models
- **CPU Threading**: Optimized for 4-core ARM Cortex-A72
- **Storage**: Model cached to ~/.cache/brainbot
- **Service Integration**: Systemd service for background operation

### macOS/Linux/Windows
- **Cross-platform compatibility** via Python
- **Virtual environment isolation**
- **Automatic platform detection** in setup.sh

## Performance Tuning

### Model Parameters
```python
# Configurable in brain_bot.py
Llama(
    model_path=str(self.model_path),
    n_ctx=2048,        # Context window - reduce for less RAM usage
    n_threads=4,       # CPU threads - match your core count
    n_gpu_layers=0,    # CPU only for compatibility
    temperature=0.7,   # Creativity vs consistency
    verbose=False      # Quiet mode
)
```

### Memory Optimization
- **Swap configuration** recommended for Pi deployments
- **Model quantization** reduces memory footprint by 70%
- **Async processing** prevents UI blocking

## Security Considerations

### Input Validation
- No arbitrary code execution
- Text-only interface limits attack surface
- Local processing only

### Model Safety
- Pre-configured safety prompt
- No internet access after initial download
- Parent-controlled environment

### File System Security
- Models cached in user directory only
- No system-level file access required
- Sandboxed execution environment

## Testing

### Manual Testing Checklist
- [ ] Initial model download completes
- [ ] UI renders correctly with colors/emojis
- [ ] Chat responses are appropriate and helpful
- [ ] Text wrapping works on small terminals
- [ ] Exit commands work properly (Ctrl+C, Ctrl+Q)
- [ ] Memory usage stays within limits

### Platform Testing
- [ ] Raspberry Pi 4 (2GB/4GB/8GB models)
- [ ] Ubuntu 20.04+
- [ ] macOS 11+
- [ ] Windows 10/11

## Deployment

### Raspberry Pi Production
1. Use setup.sh for automated installation
2. Configure systemd service for auto-start
3. Optimize memory settings for hardware
4. Set up desktop shortcuts for easy access

### Container Deployment (Future)
- Docker support could be added
- Would simplify cross-platform deployment
- Consider resource constraints for Pi deployment

## Contributing Guidelines

### Code Style
- Follow PEP 8 Python style guide
- Use type hints where appropriate
- Include docstrings for all functions
- Add inline comments for complex logic

### Pull Request Process
1. Fork the repository
2. Create feature branch
3. Test on Raspberry Pi if possible
4. Update documentation as needed
5. Submit PR with clear description

### Issue Reporting
- Include system information (OS, Python version, hardware)
- Provide full error messages
- Steps to reproduce
- Expected vs actual behavior

## Future Enhancements

### Planned Features
- **Voice Interface**: Speech-to-text and text-to-speech
- **Web UI Option**: Browser-based interface for touch devices
- **Model Options**: Support for different model sizes
- **Learning Analytics**: Track topics explored
- **Parental Controls**: Usage time limits, content filtering

### Technical Debt
- Better error handling for model download failures
- Improved chat history management
- Configuration file support
- Automated testing suite
- Performance monitoring

## Troubleshooting

### Common Development Issues

**Import Errors**
- Ensure virtual environment is activated
- Check Python version compatibility
- Verify all dependencies installed

**Model Download Failures**
- Check internet connection
- Clear model cache and retry
- Manual download fallback implemented

**Performance Issues**
- Monitor memory usage with htop
- Adjust model parameters for hardware
- Check CPU temperature on Pi

### Debugging Tools

**Enable Verbose Logging**
```python
# In brain_bot.py, change:
verbose=False
# to:
verbose=True
```

**Monitor Resources**
```bash
# Memory usage
free -h

# CPU usage
htop

# Disk space
df -h
```

## License and Attribution

- **License**: MIT License
- **Model**: TinyLlama (Apache 2.0)
- **Dependencies**: Various open-source licenses
- **Framework**: Textual (MIT)

This project demonstrates how modern AI can be made accessible, safe, and educational for children while maintaining complete privacy and control for parents.