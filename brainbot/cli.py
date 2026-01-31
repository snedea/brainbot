"""BrainBot CLI - Command line interface for the daemon."""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from .config.settings import Settings
from .daemon.server import (
    BrainBotDaemon,
    get_running_daemon_pid,
    stop_running_daemon,
)


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

    if args.json:
        print(json.dumps(status, indent=2))
    else:
        print(f"BrainBot Daemon Status")
        print(f"=" * 40)
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


def main(argv: Optional[list] = None) -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="brainbot",
        description="BrainBot - Autonomous Living Agent for Raspberry Pi 5",
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

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
