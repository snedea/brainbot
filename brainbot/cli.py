"""BrainBot CLI - Command line interface for the daemon."""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

from .config.settings import Settings
from .daemon.server import (
    BrainBotDaemon,
    get_running_daemon_pid,
    stop_running_daemon,
)
from .version import get_version_full


def cmd_start(args: argparse.Namespace) -> int:
    """Start the daemon."""
    config_path = Path(args.config) if args.config else None
    settings = Settings.load(config_path)

    # Check if already running
    pid = get_running_daemon_pid(settings)
    if pid:
        print(f"BrainBot daemon is already running (PID {pid})")
        return 1

    daemon = BrainBotDaemon(settings=settings, config_path=config_path)
    success = daemon.start(foreground=args.foreground)

    return 0 if success else 1


def cmd_stop(args: argparse.Namespace) -> int:
    """Stop the daemon."""
    config_path = Path(args.config) if args.config else None
    settings = Settings.load(config_path)

    pid = get_running_daemon_pid(settings)
    if not pid:
        print("BrainBot daemon is not running")
        return 1

    print(f"Stopping BrainBot daemon (PID {pid})...")
    if stop_running_daemon(settings, timeout=args.timeout):
        print("BrainBot daemon stopped")
        return 0
    else:
        print("Failed to stop daemon")
        return 1


def cmd_restart(args: argparse.Namespace) -> int:
    """Restart the daemon."""
    config_path = Path(args.config) if args.config else None
    settings = Settings.load(config_path)

    # Stop if running
    pid = get_running_daemon_pid(settings)
    if pid:
        print(f"Stopping BrainBot daemon (PID {pid})...")
        stop_running_daemon(settings, timeout=args.timeout)

    # Start
    daemon = BrainBotDaemon(settings=settings, config_path=config_path)
    success = daemon.start(foreground=args.foreground)

    return 0 if success else 1


def cmd_status(args: argparse.Namespace) -> int:
    """Show daemon status."""
    config_path = Path(args.config) if args.config else None
    settings = Settings.load(config_path)

    pid = get_running_daemon_pid(settings)

    if not pid:
        print("BrainBot daemon is not running")
        return 1

    # Read state file for more info
    status = {
        "running": True,
        "pid": pid,
        "data_dir": str(settings.data_dir),
        "timezone": settings.timezone,
    }

    if settings.state_file.exists():
        try:
            state_data = json.loads(settings.state_file.read_text())
            status["state"] = {
                "status": state_data.get("status", "unknown"),
                "mood": state_data.get("mood", "unknown"),
                "energy": state_data.get("energy", 0),
                "current_activity": state_data.get("current_activity"),
            }
        except Exception:
            pass

    # Add version info
    status["version"] = get_version_full()

    if args.json:
        print(json.dumps(status, indent=2))
    else:
        print(f"BrainBot Daemon Status")
        print(f"=" * 40)
        print(f"Version:     {status['version']}")
        print(f"Running:     Yes (PID {pid})")
        print(f"Data Dir:    {status['data_dir']}")
        print(f"Timezone:    {status['timezone']}")

        if "state" in status:
            print(f"\nCurrent State:")
            print(f"  Status:    {status['state']['status']}")
            print(f"  Mood:      {status['state']['mood']}")
            print(f"  Energy:    {status['state']['energy']:.1%}")
            if status['state']['current_activity']:
                print(f"  Activity:  {status['state']['current_activity']}")

    return 0


def cmd_init(args: argparse.Namespace) -> int:
    """Initialize BrainBot configuration."""
    config_path = Path(args.config) if args.config else None
    settings = Settings.load(config_path)

    print(f"Initializing BrainBot at {settings.data_dir}")

    # Create directories
    settings.ensure_directories()

    # Save default config
    settings.save()

    print(f"\nCreated directories:")
    print(f"  Config:    {settings.config_dir}")
    print(f"  State:     {settings.state_dir}")
    print(f"  Logs:      {settings.log_dir}")
    print(f"  Projects:  {settings.projects_dir}")
    print(f"  Stories:   {settings.stories_dir}")

    print(f"\nConfiguration saved to: {settings.config_file}")
    print(f"CLAUDE.md created at:   {settings.claude_md_file}")

    # Initialize network identity
    try:
        from .network import NodeIdManager, HardwareScanner, PersonaGenerator

        print("\n--- Network Identity ---")

        # Generate node ID
        node_id_mgr = NodeIdManager(settings.config_dir)
        identity = node_id_mgr.get_identity()
        print(f"Node ID:     {identity.node_id}")

        # Scan hardware
        hw_config = settings.hardware.model_dump() if settings.hardware else {}
        scanner = HardwareScanner(hw_config)
        manifest = scanner.scan()

        caps = manifest.get_available_capabilities()
        print(f"Detected:    {len(caps)} hardware capabilities")

        # Generate persona
        persona_gen = PersonaGenerator(settings.config_dir)
        persona = persona_gen.generate(manifest, identity.hostname)
        print(f"Persona:     {persona.display_name} ({persona.role})")

    except ImportError as e:
        print(f"\nNetwork features not available: {e}")

    print(f"\nBrainBot initialized! Start with: brainbot start")

    return 0


def cmd_logs(args: argparse.Namespace) -> int:
    """View daemon logs."""
    config_path = Path(args.config) if args.config else None
    settings = Settings.load(config_path)

    log_file = settings.log_dir / "brainbot.log"

    if not log_file.exists():
        print(f"No log file found at {log_file}")
        return 1

    if args.follow:
        import subprocess
        subprocess.run(["tail", "-f", str(log_file)])
    else:
        lines = args.lines
        with open(log_file) as f:
            all_lines = f.readlines()
            for line in all_lines[-lines:]:
                print(line, end="")

    return 0


def cmd_slack(args: argparse.Namespace) -> int:
    """Run Slack bot integration."""
    try:
        from .integrations.slack_bot import SlackBot, SLACK_AVAILABLE
    except ImportError as e:
        print(f"Error importing slack integration: {e}")
        print("Try: pip install slack-bolt")
        return 1

    if not SLACK_AVAILABLE:
        print("Error: slack-bolt not installed. Run: pip install slack-bolt")
        return 1

    import os
    if not os.environ.get("SLACK_BOT_TOKEN"):
        print("Error: SLACK_BOT_TOKEN environment variable not set")
        print("  export SLACK_BOT_TOKEN=xoxb-...")
        return 1
    if not os.environ.get("SLACK_APP_TOKEN"):
        print("Error: SLACK_APP_TOKEN environment variable not set")
        print("  export SLACK_APP_TOKEN=xapp-...")
        return 1

    config_path = Path(args.config) if args.config else None
    settings = Settings.load(config_path)

    from .agent.delegator import ClaudeDelegator

    delegator = ClaudeDelegator(settings)

    def handle_chat(message: str) -> str:
        """Handle chat message via Claude."""
        result = delegator.delegate_for_chat(message)
        return result.output if result.success else f"Error: {result.error}"

    print("Starting BrainBot Slack integration...")
    print("Send me a DM or @mention me in a channel!")
    print("Press Ctrl+C to stop")

    bot = SlackBot(on_message=handle_chat)

    try:
        bot.start(blocking=True)
    except KeyboardInterrupt:
        print("\nStopping...")
        bot.stop()

    return 0


# ============ Node Commands ============


def cmd_node_scan(args: argparse.Namespace) -> int:
    """Scan and display hardware capabilities."""
    config_path = Path(args.config) if args.config else None
    settings = Settings.load(config_path)

    try:
        from .network import HardwareScanner
    except ImportError as e:
        print(f"Network features not available: {e}")
        return 1

    hw_config = settings.hardware.model_dump() if settings.hardware else {}
    scanner = HardwareScanner(hw_config)
    manifest = scanner.scan()

    if args.json:
        print(json.dumps(manifest.model_dump(mode="json"), indent=2, default=str))
    else:
        print("Hardware Scan Results")
        print("=" * 50)
        print(f"\nPlatform:    {manifest.platform} {manifest.platform_version}")
        print(f"Hostname:    {manifest.hostname}")
        print(f"CPU Cores:   {manifest.cpu_cores}")
        print(f"RAM:         {manifest.ram_gb:.1f} GB")
        print(f"Disk:        {manifest.disk_gb:.1f} GB")

        if manifest.is_raspberry_pi:
            print(f"Pi Model:    {manifest.pi_model or 'Unknown'}")

        print("\nCapabilities:")
        for spec in manifest.capabilities:
            if spec.available:
                icon = "+"
                if spec.requires_confirmation:
                    icon = "?"
            else:
                icon = "-"
            print(f"  {icon} {spec.capability}")
            if spec.details:
                for key, value in spec.details.items():
                    print(f"      {key}: {value}")

        available = [c for c in manifest.capabilities if c.available]
        print(f"\nTotal: {len(available)} available capabilities")

    return 0


def cmd_node_persona(args: argparse.Namespace) -> int:
    """View or edit node persona."""
    config_path = Path(args.config) if args.config else None
    settings = Settings.load(config_path)

    try:
        from .network import PersonaGenerator, HardwareScanner, NodeIdManager
        from .network.persona import format_persona_display
    except ImportError as e:
        print(f"Network features not available: {e}")
        return 1

    persona_gen = PersonaGenerator(settings.config_dir)

    if args.reset:
        # Regenerate persona from hardware
        persona_gen.reset()
        node_id_mgr = NodeIdManager(settings.config_dir)
        identity = node_id_mgr.get_identity()
        hw_config = settings.hardware.model_dump() if settings.hardware else {}
        scanner = HardwareScanner(hw_config)
        manifest = scanner.scan()
        persona = persona_gen.generate(manifest, identity.hostname, force_regenerate=True)
        print("Persona regenerated from hardware")
        print()
        print(format_persona_display(persona))
        return 0

    if args.name:
        # Update name
        persona = persona_gen.update(name=args.name)
        if persona:
            print(f"Updated persona name to: {args.name}")
        else:
            print("No persona exists yet. Run: brainbot init")
            return 1
        return 0

    if args.edit:
        # Open in editor
        persona_file = settings.config_dir / "persona.json"
        if not persona_file.exists():
            print("No persona exists yet. Run: brainbot init")
            return 1
        editor = os.environ.get("EDITOR", "nano")
        os.system(f'{editor} "{persona_file}"')
        return 0

    # Display current persona
    persona = persona_gen.load()
    if persona is None:
        print("No persona exists yet. Run: brainbot init")
        return 1

    if args.json:
        print(json.dumps(persona.model_dump(mode="json"), indent=2, default=str))
    else:
        print(format_persona_display(persona))

    return 0


def cmd_node_id(args: argparse.Namespace) -> int:
    """Show node identity."""
    config_path = Path(args.config) if args.config else None
    settings = Settings.load(config_path)

    try:
        from .network import NodeIdManager
    except ImportError as e:
        print(f"Network features not available: {e}")
        return 1

    node_id_mgr = NodeIdManager(settings.config_dir)
    identity = node_id_mgr.get_identity()

    if args.json:
        print(json.dumps(identity.model_dump(mode="json"), indent=2, default=str))
    else:
        print("Node Identity")
        print("=" * 50)
        print(f"Node ID:      {identity.node_id}")
        print(f"Hostname:     {identity.hostname}")
        print(f"Fingerprint:  {identity.machine_fingerprint[:16]}...")
        print(f"Created:      {identity.created_at}")
        print(f"Last Boot:    {identity.last_boot}")

    return 0


# ============ Network Commands ============


def cmd_network_status(args: argparse.Namespace) -> int:
    """Show network status and online nodes."""
    config_path = Path(args.config) if args.config else None
    settings = Settings.load(config_path)

    try:
        from .network.storage import StorageClient, CloudStorageConfig
        from .network.registry import NodeRegistry, format_registry_display
    except ImportError as e:
        print(f"Network features not available: {e}")
        return 1

    # Check if network is configured
    if not hasattr(settings, 'network') or not settings.network.enabled:
        print("Network is not enabled. Configure R2 credentials first.")
        print("Run: brainbot network config")
        return 1

    storage_config = CloudStorageConfig(
        r2_account_id=settings.network.r2_account_id,
        r2_access_key_id=settings.network.r2_access_key_id,
        r2_secret_access_key=settings.network.r2_secret_access_key,
        r2_bucket=settings.network.r2_bucket,
    )

    if not storage_config.is_configured:
        print("R2 credentials not configured. Run: brainbot network config")
        return 1

    storage = StorageClient(storage_config)
    registry = NodeRegistry(storage)

    # Test connection
    conn = storage.test_connection()
    if not conn["r2"]["connected"]:
        print(f"Failed to connect to R2: {conn['r2']['error']}")
        return 1

    nodes = registry.get_all_nodes(include_offline=True)

    if args.json:
        nodes_data = [n.model_dump(mode="json") for n in nodes]
        print(json.dumps(nodes_data, indent=2, default=str))
    else:
        print(format_registry_display(nodes))

    return 0


def _push_only_sync(memory_sync) -> dict:
    """Push local memories to cloud (upload only, no download)."""
    from pathlib import Path

    stats = {"uploaded": 0, "errors": 0}

    # Push all local active memories
    for path in memory_sync.active_dir.glob("*.md"):
        cloud_key = f"brain/active/{path.name}"
        if memory_sync._upload_file(path, cloud_key):
            stats["uploaded"] += 1
        else:
            stats["errors"] += 1

    return stats


def _pull_only_sync(memory_sync) -> dict:
    """Pull cloud memories to local (download only, no upload)."""
    stats = {"downloaded": 0, "errors": 0}

    # Get cloud files
    cloud_keys = memory_sync.storage.list_keys("brain/active/")
    for key in cloud_keys:
        if not key.endswith(".md"):
            continue

        filename = key.split("/")[-1]
        local_path = memory_sync.active_dir / filename

        if memory_sync._download_file(key, local_path):
            stats["downloaded"] += 1
        else:
            stats["errors"] += 1

    return stats


def cmd_network_sync(args: argparse.Namespace) -> int:
    """Sync brain memories with cloud."""
    config_path = Path(args.config) if args.config else None
    settings = Settings.load(config_path)

    try:
        from .network.storage import StorageClient, CloudStorageConfig
        from .network.event_log import EventLog
        from .network.memory_sync import MemorySyncManager
        from .network import NodeIdManager
    except ImportError as e:
        print(f"Network features not available: {e}")
        return 1

    if not hasattr(settings, 'network') or not settings.network.enabled:
        print("Network is not enabled. Run: brainbot network config")
        return 1

    storage_config = CloudStorageConfig(
        r2_account_id=settings.network.r2_account_id,
        r2_access_key_id=settings.network.r2_access_key_id,
        r2_secret_access_key=settings.network.r2_secret_access_key,
        r2_bucket=settings.network.r2_bucket,
    )

    if not storage_config.is_configured:
        print("R2 credentials not configured. Run: brainbot network config")
        return 1

    node_id_mgr = NodeIdManager(settings.config_dir)
    node_id = node_id_mgr.node_id

    storage = StorageClient(storage_config)
    event_log = EventLog(storage, node_id)
    memory_sync = MemorySyncManager(
        storage=storage,
        event_log=event_log,
        brain_dir=settings.brain_dir,
        node_id=node_id,
    )

    # Determine sync mode: push, pull, or bidirectional
    push_only = getattr(args, 'push', False)
    pull_only = getattr(args, 'pull', False)

    if push_only and pull_only:
        print("Cannot use both --push and --pull. Use one or neither for bidirectional sync.")
        return 1

    if push_only:
        print("Pushing local memories to cloud...")
        stats = _push_only_sync(memory_sync)
        print(f"\nPush Complete:")
        print(f"  Uploaded: {stats['uploaded']}")
        print(f"  Errors:   {stats['errors']}")
    elif pull_only:
        print("Pulling cloud memories to local...")
        stats = _pull_only_sync(memory_sync)
        print(f"\nPull Complete:")
        print(f"  Downloaded: {stats['downloaded']}")
        print(f"  Errors:     {stats['errors']}")
    else:
        print("Syncing brain memories (bidirectional)...")
        stats = memory_sync.sync()
        print(f"\nSync Complete:")
        print(f"  Uploaded:   {stats['uploaded']}")
        print(f"  Downloaded: {stats['downloaded']}")
        print(f"  Conflicts:  {stats['conflicts']}")
        print(f"  Unchanged:  {stats['unchanged']}")
        print(f"  Errors:     {stats['errors']}")

    return 0


def cmd_network_config(args: argparse.Namespace) -> int:
    """Configure network credentials."""
    config_path = Path(args.config) if args.config else None
    settings = Settings.load(config_path)

    print("Configure BrainBot Network (R2/S3)")
    print("=" * 50)
    print()

    # R2 Configuration (Primary storage)
    print("=== Cloudflare R2 (Primary Storage) ===")
    print("You'll need Cloudflare R2 credentials:")
    print("  1. Go to Cloudflare Dashboard > R2")
    print("  2. Create a bucket named 'brainbot-network'")
    print("  3. Create an API token with read/write access")
    print()

    r2_account_id = input("R2 Account ID: ").strip()
    r2_access_key_id = input("R2 Access Key ID: ").strip()
    r2_secret_access_key = input("R2 Secret Access Key: ").strip()
    r2_bucket = input("R2 Bucket Name [brainbot-network]: ").strip() or "brainbot-network"

    # S3 Configuration (Backup storage - optional)
    print()
    print("=== AWS S3 (Backup Storage - Optional) ===")
    print("S3 is used for cold storage backups.")
    print("Press Enter to skip S3 configuration.")
    print()

    s3_bucket = input("S3 Bucket Name [brainbot-backup]: ").strip() or "brainbot-backup"
    s3_region = input("S3 Region [us-east-1]: ").strip() or "us-east-1"

    # Check if S3 credentials differ from R2
    s3_access_key_id = ""
    s3_secret_access_key = ""
    use_different_s3_creds = input("Use different credentials for S3? [y/N]: ").strip().lower()
    if use_different_s3_creds == "y":
        s3_access_key_id = input("S3 Access Key ID: ").strip()
        s3_secret_access_key = input("S3 Secret Access Key: ").strip()

    # Save to network config file
    network_config = {
        "enabled": True,
        # R2 config
        "r2_account_id": r2_account_id,
        "r2_access_key_id": r2_access_key_id,
        "r2_secret_access_key": r2_secret_access_key,
        "r2_bucket": r2_bucket,
        # S3 config
        "s3_bucket": s3_bucket,
        "s3_region": s3_region,
        "s3_access_key_id": s3_access_key_id if s3_access_key_id else r2_access_key_id,
        "s3_secret_access_key": s3_secret_access_key if s3_secret_access_key else r2_secret_access_key,
        # Intervals
        "heartbeat_interval_seconds": 60,
        "sync_interval_seconds": 300,
    }

    network_file = settings.config_dir / "network.json"
    network_file.write_text(json.dumps(network_config, indent=2))

    print(f"\nNetwork config saved to: {network_file}")
    print("\nTest connection with: brainbot network status")

    return 0


def cmd_network_task(args: argparse.Namespace) -> int:
    """Submit a task to the network."""
    config_path = Path(args.config) if args.config else None
    settings = Settings.load(config_path)

    try:
        from .network.storage import StorageClient, CloudStorageConfig
        from .network.registry import NodeRegistry
        from .network.event_log import EventLog
        from .network.task_queue import TaskQueue
        from .network.task_router import TaskRouter, TaskSubmitter
        from .network import NodeIdManager, HardwareScanner
    except ImportError as e:
        print(f"Network features not available: {e}")
        return 1

    if not settings.network.enabled:
        print("Network is not enabled. Run: brainbot network config")
        return 1

    # Parse payload
    payload = {}
    if args.payload:
        try:
            payload = json.loads(args.payload)
        except json.JSONDecodeError as e:
            print(f"Invalid JSON payload: {e}")
            return 1

    # Initialize network components
    storage_config = CloudStorageConfig(
        r2_account_id=settings.network.r2_account_id,
        r2_access_key_id=settings.network.r2_access_key_id,
        r2_secret_access_key=settings.network.r2_secret_access_key,
        r2_bucket=settings.network.r2_bucket,
    )

    if not storage_config.is_configured:
        print("R2 credentials not configured. Run: brainbot network config")
        return 1

    node_id_mgr = NodeIdManager(settings.config_dir)
    node_id = node_id_mgr.node_id

    hw_config = settings.hardware.model_dump() if settings.hardware else {}
    scanner = HardwareScanner(hw_config)
    manifest = scanner.scan()

    storage = StorageClient(storage_config)
    registry = NodeRegistry(storage)
    event_log = EventLog(storage, node_id)
    queue = TaskQueue(storage, event_log, node_id)
    router = TaskRouter(registry, node_id)
    submitter = TaskSubmitter(router, queue, manifest)

    # Submit task
    if args.node:
        # Submit to specific node
        success, message = submitter.submit_to_node(
            node_id=args.node,
            task_type=args.task_type,
            payload=payload,
            priority=args.priority,
        )
    else:
        # Route automatically
        success, message = submitter.submit(
            task_type=args.task_type,
            payload=payload,
            priority=args.priority,
            force_remote=args.force_remote,
        )

    if success:
        print(f"Success: {message}")
        return 0
    else:
        print(f"Failed: {message}")
        return 1


# ============ Safety Commands ============


def cmd_safety_show(args: argparse.Namespace) -> int:
    """Show all safety policies."""
    config_path = Path(args.config) if args.config else None
    settings = Settings.load(config_path)

    try:
        from .network.safety import PolicyEnforcer
        from .network.safety.policies import format_policies_display
    except ImportError as e:
        print(f"Safety features not available: {e}")
        return 1

    enforcer = PolicyEnforcer(settings.config_dir)
    policies = enforcer.get_all_policies()

    if args.json:
        print(json.dumps(policies.model_dump(mode="json"), indent=2, default=str))
    else:
        print(format_policies_display(policies))

    return 0


def cmd_safety_disable(args: argparse.Namespace) -> int:
    """Disable a capability."""
    config_path = Path(args.config) if args.config else None
    settings = Settings.load(config_path)

    try:
        from .network.safety import PolicyEnforcer
        from .network.models import HardwareCapability
    except ImportError as e:
        print(f"Safety features not available: {e}")
        return 1

    # Validate capability
    try:
        cap = HardwareCapability(args.capability)
    except ValueError:
        print(f"Unknown capability: {args.capability}")
        print("\nValid capabilities:")
        for c in HardwareCapability:
            print(f"  {c.value}")
        return 1

    enforcer = PolicyEnforcer(settings.config_dir)
    reason = args.reason or "Disabled by user"

    if enforcer.disable_capability(cap, reason):
        print(f"Disabled: {cap.value}")
        print(f"Reason: {reason}")
    else:
        print("Failed to update policy")
        return 1

    return 0


def cmd_safety_enable(args: argparse.Namespace) -> int:
    """Enable a capability."""
    config_path = Path(args.config) if args.config else None
    settings = Settings.load(config_path)

    try:
        from .network.safety import PolicyEnforcer
        from .network.models import HardwareCapability
    except ImportError as e:
        print(f"Safety features not available: {e}")
        return 1

    try:
        cap = HardwareCapability(args.capability)
    except ValueError:
        print(f"Unknown capability: {args.capability}")
        return 1

    enforcer = PolicyEnforcer(settings.config_dir)

    if enforcer.enable_capability(cap, require_confirmation=args.explicit):
        mode = "explicit confirmation required" if args.explicit else "always allowed"
        print(f"Enabled: {cap.value} ({mode})")
    else:
        print("Failed to update policy")
        return 1

    return 0


def cmd_safety_reset(args: argparse.Namespace) -> int:
    """Reset a capability to default policy."""
    config_path = Path(args.config) if args.config else None
    settings = Settings.load(config_path)

    try:
        from .network.safety import PolicyEnforcer
        from .network.models import HardwareCapability
    except ImportError as e:
        print(f"Safety features not available: {e}")
        return 1

    try:
        cap = HardwareCapability(args.capability)
    except ValueError:
        print(f"Unknown capability: {args.capability}")
        return 1

    enforcer = PolicyEnforcer(settings.config_dir)

    if enforcer.reset_capability(cap):
        print(f"Reset to default: {cap.value}")
    else:
        print("Failed to reset policy")
        return 1

    return 0


# ============ Integration Commands ============


def cmd_integrations_pipedream(args: argparse.Namespace) -> int:
    """Configure Pipedream integration."""
    config_path = Path(args.config) if args.config else None
    settings = Settings.load(config_path)

    try:
        from .integrations.pipedream import PipedreamConfig, PipedreamConfigManager
    except ImportError as e:
        print(f"Integration features not available: {e}")
        return 1

    manager = PipedreamConfigManager(settings.config_dir)

    print("Configure Pipedream Integration")
    print("=" * 50)
    print()
    print("Pipedream connects BrainBot to 1000+ services via webhooks.")
    print("Create workflows at: https://pipedream.com")
    print()

    # Get webhook URLs interactively
    print("Enter webhook URLs (press Enter to skip):")
    print()

    webhook_digest = input("Daily Digest Webhook URL: ").strip()
    webhook_notif = input("Notification Webhook URL: ").strip()
    webhook_log = input("Event Log Webhook URL: ").strip()
    inbound_secret = input("Inbound Webhook Secret (for security): ").strip()

    config = PipedreamConfig(
        enabled=bool(webhook_digest or webhook_notif or webhook_log),
        webhook_daily_digest=webhook_digest,
        webhook_notification=webhook_notif,
        webhook_log_event=webhook_log,
        inbound_secret=inbound_secret,
    )

    if manager.save(config):
        print(f"\nPipedream config saved to: {manager.config_file}")
        if config.enabled:
            print("Status: ENABLED")
        else:
            print("Status: DISABLED (no webhooks configured)")
    else:
        print("Failed to save configuration")
        return 1

    return 0


def cmd_integrations_email(args: argparse.Namespace) -> int:
    """Configure email integration."""
    config_path = Path(args.config) if args.config else None
    settings = Settings.load(config_path)

    try:
        from .integrations.email import EmailConfig, EmailConfigManager
    except ImportError as e:
        print(f"Integration features not available: {e}")
        return 1

    manager = EmailConfigManager(settings.config_dir)

    print("Configure Email Integration (Fastmail SMTP/IMAP)")
    print("=" * 50)
    print()
    print("BrainBot will send you daily digest emails via Fastmail")
    print("and can receive your replies via IMAP.")
    print()
    print("First, create an app-specific password in Fastmail:")
    print("  Settings -> Privacy & Security -> Integrations -> New App Password")
    print()

    # SMTP credentials
    print("=== OUTBOUND (SMTP) ===")
    smtp_user = input("Fastmail Email: ").strip()
    smtp_password = input("App Password: ").strip()

    print()
    # Recipient (can be same or different)
    recipient_email = input(f"Send digest to [{smtp_user}]: ").strip() or smtp_user
    recipient_name = input("Your Name: ").strip()

    print()
    # IMAP credentials for receiving replies
    print("=== INBOUND (IMAP) - for receiving replies ===")
    use_same = input("Use same credentials for IMAP? [Y/n]: ").strip().lower()
    if use_same == "n":
        imap_user = input("IMAP Username: ").strip()
        imap_password = input("IMAP Password: ").strip()
    else:
        imap_user = smtp_user
        imap_password = smtp_password

    imap_folder = input("IMAP Folder to monitor [INBOX]: ").strip() or "INBOX"
    imap_interval = input("Check interval in seconds [300]: ").strip()
    imap_check_interval = int(imap_interval) if imap_interval else 300

    print()
    # Optional settings
    print("=== SETTINGS ===")
    sender_name = input("Bot Name [BrainBot]: ").strip() or "BrainBot"
    digest_time = input("Daily Digest Time (HH:MM) [19:00]: ").strip() or "19:00"

    config = EmailConfig(
        enabled=bool(smtp_user and smtp_password),
        # SMTP
        smtp_host="smtp.fastmail.com",
        smtp_port=465,
        smtp_user=smtp_user,
        smtp_password=smtp_password,
        sender_email=smtp_user,
        sender_name=sender_name,
        # IMAP
        imap_host="imap.fastmail.com",
        imap_port=993,
        imap_user=imap_user,
        imap_password=imap_password,
        imap_folder=imap_folder,
        imap_check_interval=imap_check_interval,
        # Recipient
        recipient_email=recipient_email,
        recipient_name=recipient_name,
        digest_time=digest_time,
    )

    if manager.save(config):
        print(f"\nEmail config saved to: {manager.config_file}")
        if config.is_configured:
            print(f"Status: ENABLED")
            print(f"SMTP: {smtp_user} @ smtp.fastmail.com:465")
            print(f"IMAP: {imap_user} @ imap.fastmail.com:993 ({imap_folder})")
            print(f"Recipient: {recipient_email}")
            print(f"Digest Time: {digest_time} ({settings.timezone})")
            print(f"Reply Check: every {imap_check_interval}s")
            print()
            print("Test with: brainbot integrations test")
            print("Preview:   brainbot digest send --preview")
            print("Send:      brainbot digest send")
            print()
            print("Note: Restart daemon for changes to take effect: brainbot restart")
        else:
            print("Status: DISABLED (missing credentials)")
    else:
        print("Failed to save configuration")
        return 1

    return 0


def cmd_integrations_test(args: argparse.Namespace) -> int:
    """Test integrations."""
    config_path = Path(args.config) if args.config else None
    settings = Settings.load(config_path)

    try:
        from .integrations.email import EmailIntegration, EmailConfigManager
    except ImportError as e:
        print(f"Integration features not available: {e}")
        return 1

    email_manager = EmailConfigManager(settings.config_dir)
    email_config = email_manager.load()

    print("Testing Integrations")
    print("=" * 50)
    print()

    # Test email/SMTP
    print("Email Integration:")
    if email_config.is_configured:
        print(f"  SMTP User: {email_config.smtp_user}")
        print(f"  IMAP User: {email_config.imap_user}")
        print(f"  Recipient: {email_config.recipient_email}")
        print(f"  Digest Time: {email_config.digest_time}")
        print()

        email = EmailIntegration(email_config)
        result = email.test_connection()

        # SMTP test
        print("  SMTP (outbound)...", end=" ", flush=True)
        smtp_result = result.get("smtp", {})
        if smtp_result.get("success"):
            print("OK")
            print(f"    {smtp_result.get('message', 'Connected')}")
        else:
            print("FAILED")
            print(f"    Error: {smtp_result.get('error')}")

        # IMAP test
        print("  IMAP (inbound)...", end=" ", flush=True)
        imap_result = result.get("imap", {})
        if imap_result.get("success"):
            print("OK")
            print(f"    {imap_result.get('message', 'Connected')}")
        else:
            print("FAILED")
            print(f"    Error: {imap_result.get('error')}")

    else:
        print("  Not configured. Run: brainbot integrations email")

    return 0


def cmd_digest_send(args: argparse.Namespace) -> int:
    """Send daily digest now."""
    config_path = Path(args.config) if args.config else None
    settings = Settings.load(config_path)

    try:
        from .integrations.email import EmailIntegration, EmailConfigManager
    except ImportError as e:
        print(f"Integration features not available: {e}")
        return 1

    email_manager = EmailConfigManager(settings.config_dir)
    email_config = email_manager.load()

    if not email_config.is_configured:
        print("Email not configured. Run: brainbot integrations email")
        return 1

    # Try to load memory store for richer digest
    memory_store = None
    state_manager = None
    try:
        from .memory.store import MemoryStore
        memory_store = MemoryStore(settings.state_dir / "memory.db")
    except Exception:
        pass

    try:
        from .state.manager import StateManager
        state_manager = StateManager(settings.state_dir)
    except Exception:
        pass

    # Create integration and send
    email = EmailIntegration(email_config, memory_store, state_manager)

    print(f"Generating digest for {email_config.recipient_email}...")
    digest = email.generate_digest()

    if args.preview:
        print("\n" + "=" * 50)
        print("PREVIEW (not sent)")
        print("=" * 50)
        print(digest.to_text())
        return 0

    print("Sending via Fastmail SMTP...")
    result = email.send_digest(digest)

    if result["success"]:
        print(f"Digest sent successfully to {email_config.recipient_email}")
    else:
        print(f"Failed to send: {result.get('error')}")
        return 1

    return 0


def main(argv: Optional[list] = None) -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="brainbot",
        description="BrainBot - Autonomous AI Agent",
    )
    parser.add_argument(
        "--config", "-c",
        help="Path to config file",
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # start
    start_parser = subparsers.add_parser("start", help="Start the daemon")
    start_parser.add_argument(
        "--foreground", "-f",
        action="store_true",
        help="Run in foreground (don't daemonize)",
    )
    start_parser.set_defaults(func=cmd_start)

    # stop
    stop_parser = subparsers.add_parser("stop", help="Stop the daemon")
    stop_parser.add_argument(
        "--timeout", "-t",
        type=int,
        default=30,
        help="Shutdown timeout in seconds",
    )
    stop_parser.set_defaults(func=cmd_stop)

    # restart
    restart_parser = subparsers.add_parser("restart", help="Restart the daemon")
    restart_parser.add_argument(
        "--foreground", "-f",
        action="store_true",
        help="Run in foreground after restart",
    )
    restart_parser.add_argument(
        "--timeout", "-t",
        type=int,
        default=30,
        help="Shutdown timeout in seconds",
    )
    restart_parser.set_defaults(func=cmd_restart)

    # status
    status_parser = subparsers.add_parser("status", help="Show daemon status")
    status_parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output as JSON",
    )
    status_parser.set_defaults(func=cmd_status)

    # init
    init_parser = subparsers.add_parser("init", help="Initialize configuration")
    init_parser.set_defaults(func=cmd_init)

    # logs
    logs_parser = subparsers.add_parser("logs", help="View daemon logs")
    logs_parser.add_argument(
        "--follow", "-f",
        action="store_true",
        help="Follow log output (tail -f)",
    )
    logs_parser.add_argument(
        "--lines", "-n",
        type=int,
        default=50,
        help="Number of lines to show",
    )
    logs_parser.set_defaults(func=cmd_logs)

    # slack
    slack_parser = subparsers.add_parser("slack", help="Run Slack bot integration")
    slack_parser.set_defaults(func=cmd_slack)

    # === Node Commands ===
    node_parser = subparsers.add_parser("node", help="Node management commands")
    node_subparsers = node_parser.add_subparsers(dest="node_command", help="Node subcommands")

    # node scan
    node_scan_parser = node_subparsers.add_parser("scan", help="Scan hardware capabilities")
    node_scan_parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    node_scan_parser.set_defaults(func=cmd_node_scan)

    # node persona
    node_persona_parser = node_subparsers.add_parser("persona", help="View/edit node persona")
    node_persona_parser.add_argument("--edit", action="store_true", help="Open in $EDITOR")
    node_persona_parser.add_argument("--name", help="Set custom name")
    node_persona_parser.add_argument("--reset", action="store_true", help="Regenerate from hardware")
    node_persona_parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    node_persona_parser.set_defaults(func=cmd_node_persona)

    # node id
    node_id_parser = node_subparsers.add_parser("id", help="Show node identity")
    node_id_parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    node_id_parser.set_defaults(func=cmd_node_id)

    # === Network Commands ===
    network_parser = subparsers.add_parser("network", help="Network management commands")
    network_subparsers = network_parser.add_subparsers(dest="network_command", help="Network subcommands")

    # network status
    network_status_parser = network_subparsers.add_parser("status", help="Show online nodes")
    network_status_parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    network_status_parser.set_defaults(func=cmd_network_status)

    # network sync
    network_sync_parser = network_subparsers.add_parser("sync", help="Sync brain with cloud")
    network_sync_parser.add_argument("--push", action="store_true", help="Push local to cloud")
    network_sync_parser.add_argument("--pull", action="store_true", help="Pull cloud to local")
    network_sync_parser.set_defaults(func=cmd_network_sync)

    # network config
    network_config_parser = network_subparsers.add_parser("config", help="Configure R2/S3 credentials")
    network_config_parser.set_defaults(func=cmd_network_config)

    # network task
    network_task_parser = network_subparsers.add_parser("task", help="Submit a task to the network")
    network_task_parser.add_argument("task_type", help="Task type (e.g., led_mood, display_text)")
    network_task_parser.add_argument("--payload", "-p", help="JSON payload for task")
    network_task_parser.add_argument("--node", "-n", help="Target specific node ID")
    network_task_parser.add_argument("--priority", type=int, default=1, help="Task priority (1-10)")
    network_task_parser.add_argument("--force-remote", action="store_true", help="Force remote execution")
    network_task_parser.set_defaults(func=cmd_network_task)

    # === Safety Commands ===
    safety_parser = subparsers.add_parser("safety", help="Safety policy management")
    safety_subparsers = safety_parser.add_subparsers(dest="safety_command", help="Safety subcommands")

    # safety show
    safety_show_parser = safety_subparsers.add_parser("show", help="Show all policies")
    safety_show_parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    safety_show_parser.set_defaults(func=cmd_safety_show)

    # safety disable
    safety_disable_parser = safety_subparsers.add_parser("disable", help="Disable a capability")
    safety_disable_parser.add_argument("capability", help="Capability to disable")
    safety_disable_parser.add_argument("--reason", help="Reason for disabling")
    safety_disable_parser.set_defaults(func=cmd_safety_disable)

    # safety enable
    safety_enable_parser = safety_subparsers.add_parser("enable", help="Enable a capability")
    safety_enable_parser.add_argument("capability", help="Capability to enable")
    safety_enable_parser.add_argument("--explicit", action="store_true", help="Require explicit confirmation")
    safety_enable_parser.set_defaults(func=cmd_safety_enable)

    # safety reset
    safety_reset_parser = safety_subparsers.add_parser("reset", help="Reset capability to default")
    safety_reset_parser.add_argument("capability", help="Capability to reset")
    safety_reset_parser.set_defaults(func=cmd_safety_reset)

    # === Integration Commands ===
    integrations_parser = subparsers.add_parser("integrations", help="External service integrations")
    integrations_subparsers = integrations_parser.add_subparsers(dest="integrations_command", help="Integration subcommands")

    # integrations pipedream
    int_pd_parser = integrations_subparsers.add_parser("pipedream", help="Configure Pipedream webhooks")
    int_pd_parser.set_defaults(func=cmd_integrations_pipedream)

    # integrations email
    int_email_parser = integrations_subparsers.add_parser("email", help="Configure email integration")
    int_email_parser.set_defaults(func=cmd_integrations_email)

    # integrations test
    int_test_parser = integrations_subparsers.add_parser("test", help="Test all integrations")
    int_test_parser.set_defaults(func=cmd_integrations_test)

    # === Digest Command ===
    digest_parser = subparsers.add_parser("digest", help="Daily digest management")
    digest_subparsers = digest_parser.add_subparsers(dest="digest_command", help="Digest subcommands")

    # digest send
    digest_send_parser = digest_subparsers.add_parser("send", help="Send daily digest now")
    digest_send_parser.add_argument("--preview", action="store_true", help="Preview without sending")
    digest_send_parser.set_defaults(func=cmd_digest_send)

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
