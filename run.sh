#!/bin/bash
# BrainBot Run Script

# Colors for output
RED='\033[0;31m'
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
