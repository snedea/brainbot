"""Version tracking for BrainBot.

Uses git commit hash to identify exact code version running on each node.
"""

import subprocess
from pathlib import Path
from typing import Optional

_cached_version: Optional[str] = None


def get_version() -> str:
    """
    Get the current version (git commit hash).

    Returns:
        Short git hash (e.g., "807f0a4") or "unknown" if not in a git repo
    """
    global _cached_version

    if _cached_version is not None:
        return _cached_version

    try:
        # Get the directory containing the brainbot package
        import brainbot
        package_dir = Path(brainbot.__file__).parent.parent

        # Get short commit hash
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=package_dir,
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0:
            _cached_version = result.stdout.strip()
        else:
            _cached_version = "unknown"

    except Exception:
        _cached_version = "unknown"

    return _cached_version


def get_version_full() -> str:
    """
    Get full version info including commit hash and dirty status.

    Returns:
        Version string like "807f0a4" or "807f0a4-dirty" if uncommitted changes
    """
    try:
        import brainbot
        package_dir = Path(brainbot.__file__).parent.parent

        # Get short commit hash
        hash_result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=package_dir,
            capture_output=True,
            text=True,
            timeout=5,
        )

        if hash_result.returncode != 0:
            return "unknown"

        version = hash_result.stdout.strip()

        # Check for uncommitted changes
        dirty_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=package_dir,
            capture_output=True,
            text=True,
            timeout=5,
        )

        if dirty_result.returncode == 0 and dirty_result.stdout.strip():
            version += "-dirty"

        return version

    except Exception:
        return "unknown"


def get_version_info() -> dict:
    """
    Get detailed version information.

    Returns:
        Dict with version details
    """
    try:
        import brainbot
        package_dir = Path(brainbot.__file__).parent.parent

        info = {
            "hash": get_version(),
            "full": get_version_full(),
            "branch": "unknown",
            "commit_date": "unknown",
        }

        # Get branch name
        branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=package_dir,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if branch_result.returncode == 0:
            info["branch"] = branch_result.stdout.strip()

        # Get commit date
        date_result = subprocess.run(
            ["git", "log", "-1", "--format=%ci"],
            cwd=package_dir,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if date_result.returncode == 0:
            info["commit_date"] = date_result.stdout.strip()

        return info

    except Exception:
        return {
            "hash": "unknown",
            "full": "unknown",
            "branch": "unknown",
            "commit_date": "unknown",
        }
