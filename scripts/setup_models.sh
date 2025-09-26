#!/usr/bin/env bash
# Setup script for BrainBot dual-model system
set -euo pipefail

echo "==================================="
echo "BrainBot Model Setup"
echo "==================================="

# Create model directories
mkdir -p models/generation models/moderation

echo ""
echo "📦 Model Setup Instructions:"
echo ""

# Generation model (existing TinyLlama)
echo "1. Generation Model (TinyLlama GGUF)"
echo "   Location: models/generation/model.gguf"
echo ""
echo "   Download from:"
echo "   https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF"
echo "   Recommended: tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf (~670MB)"
echo ""

# Guard model for moderation
echo "2. Moderation Model (Guard GGUF)"
echo "   Location: models/moderation/guard.gguf"
echo ""
echo "   Recommended options (choose one):"
echo "   - Llama-Guard-3-8B-GGUF (Q4_K_M): ~4.9GB"
echo "     https://huggingface.co/bartowski/Llama-Guard-3-8B-GGUF"
echo ""
echo "   - Smaller alternative: Llama-Guard-7B (Q4_K_M): ~3.8GB"
echo "     https://huggingface.co/TheBloke/Llama-Guard-7B-GGUF"
echo ""

echo "==================================="
echo "Download Instructions:"
echo "==================================="
echo ""
echo "Option 1: Using wget"
echo "  wget -O models/generation/model.gguf [URL]"
echo "  wget -O models/moderation/guard.gguf [URL]"
echo ""
echo "Option 2: Using curl"
echo "  curl -L -o models/generation/model.gguf [URL]"
echo "  curl -L -o models/moderation/guard.gguf [URL]"
echo ""
echo "Option 3: Manual download"
echo "  Download files and place in respective directories"
echo ""

# Check if llama.cpp is available
if command -v llama-server &> /dev/null; then
    echo "✅ llama-server found: $(which llama-server)"
elif command -v ./llama-server &> /dev/null; then
    echo "✅ llama-server found in current directory"
else
    echo "⚠️  llama-server not found"
    echo ""
    echo "Install llama.cpp:"
    echo "  git clone https://github.com/ggerganov/llama.cpp"
    echo "  cd llama.cpp && make"
    echo ""
fi

echo "==================================="
echo "After placing models, run:"
echo "  python scripts/run_dual_models.py"
echo "==================================="