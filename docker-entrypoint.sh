#!/bin/bash
set -e

# Create config directory
mkdir -p /home/brainbot/.brainbot/config

# Create network.json from environment variables
cat > /home/brainbot/.brainbot/config/network.json << EOF
{
  "enabled": true,
  "r2_account_id": "${R2_ACCOUNT_ID}",
  "r2_access_key_id": "${R2_ACCESS_KEY_ID}",
  "r2_secret_access_key": "${R2_SECRET_ACCESS_KEY}",
  "r2_bucket": "${R2_BUCKET:-brainbot-network}",
  "heartbeat_interval_seconds": 60,
  "sync_interval_seconds": 300,
  "slack": {
    "bot_token": "${SLACK_BOT_TOKEN}",
    "app_token": "${SLACK_APP_TOKEN}",
    "network_channel": "${SLACK_NETWORK_CHANNEL}",
    "post_boot_announcements": true,
    "post_task_updates": true
  }
}
EOF

echo "BrainBot config initialized"
echo "Starting BrainBot daemon..."

# Execute the main command
exec "$@"
