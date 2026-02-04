# BrainBot Docker Container - Isolated Autonomous Agent
FROM python:3.12-slim

# Security: Run as non-root user
RUN useradd -m -s /bin/bash brainbot

# Install minimal dependencies + Node.js for Claude CLI
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install Claude CLI globally
RUN npm install -g @anthropic-ai/claude-code

# Set working directory
WORKDIR /app

# Copy only what's needed (no sensitive files)
COPY requirements.txt .

# Install Python dependencies (skip voice/hardware deps that won't work)
RUN pip install --no-cache-dir \
    pydantic \
    pydantic-settings \
    apscheduler \
    psutil \
    slack-bolt \
    slack-sdk \
    boto3 \
    rich \
    python-dotenv

# Copy application code
COPY brainbot/ ./brainbot/

# Copy entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Create data directory owned by brainbot user
RUN mkdir -p /home/brainbot/.brainbot && \
    chown -R brainbot:brainbot /home/brainbot/.brainbot /app

# Switch to non-root user
USER brainbot

# Set environment
ENV HOME=/home/brainbot
ENV BRAINBOT_DATA_DIR=/home/brainbot/.brainbot

# Health check
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s \
    CMD python -m brainbot status || exit 1

# Entrypoint sets up config from env vars
ENTRYPOINT ["docker-entrypoint.sh"]

# Run daemon in foreground
CMD ["python", "-m", "brainbot", "start", "--foreground"]
