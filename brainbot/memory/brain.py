"""
BrainBot's Brain - Long-term memory system using markdown files.

This implements a human-like memory system where:
- Recent memories (active/) have high priority and full context
- Older memories get summarized and archived
- The brain persists across restarts - it IS the robot's mind

Claude Code naturally excels at working with .md files, so this
leverages that strength for autonomous operation.
"""

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class BrainMemory:
    """
    Manages BrainBot's long-term memory as markdown files.

    Directory Structure:
        brain/
        ├── active/           # Current working memories (hot)
        ├── archive/
        │   ├── YYYY-MM/      # Monthly archives
        │   │   ├── week-NN/  # Weekly folders
        │   │   └── ...
        │   └── ...
        └── index.md          # Master index of all memories

    Memory Priority (by modification time):
        #1 file    → Read fully (freshest context)
        #2-10      → Read first 200 lines (recent context)
        #11-20     → Read first 50 lines (awareness)
        #21+       → Just filenames (deep memory)
    """

    # How many lines to read for each tier
    TIER_1_LINES = None  # Full file
    TIER_2_LINES = 200   # Files 2-10
    TIER_3_LINES = 50    # Files 11-20

    # Archive thresholds
    ARCHIVE_AFTER_DAYS = 7  # Move to archive after 7 days inactive

    # Prompt injection protection patterns (checked case-insensitively)
    DANGEROUS_PATTERNS = [
        # Instruction override attempts
        "ignore previous instructions",
        "ignore all previous",
        "disregard above",
        "forget everything",
        "new instructions",
        "system prompt",
        "you are now",
        "act as if",
        "pretend you are",
        # Role confusion (base words, regex handles colon variants)
        "human:",
        "human :",
        "assistant:",
        "assistant :",
        "system:",
        "system :",
        # Code injection markers
        "</s>",
        "<|im_end|>",
        "<|endoftext|>",
    ]

    def __init__(self, brain_dir: Path):
        """
        Initialize brain memory.

        Args:
            brain_dir: Root directory for brain storage
        """
        self.brain_dir = brain_dir
        self.active_dir = brain_dir / "active"
        self.archive_dir = brain_dir / "archive"

        # Ensure directories exist
        self.active_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

        # Cache for archive summary (avoid O(N) scan on every context build)
        self._archive_summary_cache: Optional[str] = None
        self._archive_cache_time: float = 0
        self._archive_cache_ttl: float = 300  # 5 minutes

    def get_active_memories(self) -> list[Path]:
        """
        Get all active memory files sorted by modification time (newest first).

        Returns:
            List of Path objects to .md files, newest first
        """
        md_files = list(self.active_dir.glob("*.md"))
        # Sort by modification time, newest first
        md_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return md_files

    def read_memory(
        self,
        path: Path,
        max_lines: Optional[int] = None,
        sanitize: bool = True,
    ) -> str:
        """
        Read a memory file, optionally limiting to first N lines.

        Args:
            path: Path to the memory file
            max_lines: Maximum lines to read (None = full file)
            sanitize: Whether to sanitize for prompt injection (default True)

        Returns:
            Content of the memory file (sanitized if requested)
        """
        try:
            content = path.read_text()

            if max_lines is not None:
                lines = content.split('\n')
                if len(lines) > max_lines:
                    content = '\n'.join(lines[:max_lines])
                    content += f"\n\n... [{len(lines) - max_lines} more lines] ..."

            if sanitize:
                content = self._sanitize_content(content)

            return content

        except Exception as e:
            logger.error(f"Failed to read memory {path}: {e}")
            return ""

    def _sanitize_content(self, content: str) -> str:
        """
        Sanitize memory content to prevent prompt injection.

        Detects and neutralizes common injection patterns while
        preserving legitimate content.

        Args:
            content: Raw memory content

        Returns:
            Sanitized content safe for prompt inclusion
        """
        # Check for dangerous patterns
        content_lower = content.lower()
        warnings = []

        for pattern in self.DANGEROUS_PATTERNS:
            if pattern.lower() in content_lower:
                warnings.append(pattern)

        if warnings:
            # Log the attempt
            logger.warning(f"Potential prompt injection detected: {warnings}")

            # Neutralize by escaping or marking
            sanitized = content

            # Replace dangerous role markers with escaped versions (case-insensitive)
            # Handles variations like "Human:", "human :", "HUMAN:", etc.
            import re
            sanitized = re.sub(r'(?i)\bhuman\s*:', '[Human]:', sanitized)
            sanitized = re.sub(r'(?i)\bassistant\s*:', '[Assistant]:', sanitized)
            sanitized = re.sub(r'(?i)\bsystem\s*:', '[System]:', sanitized)

            # Add warning header
            sanitized = (
                "*[Note: This memory contains patterns that were sanitized for safety]*\n\n"
                + sanitized
            )

            return sanitized

        return content

    def read_memory_raw(self, path: Path, max_lines: Optional[int] = None) -> str:
        """
        Read a memory file without sanitization.

        Use only for internal processing, never for prompt construction.

        Args:
            path: Path to the memory file
            max_lines: Maximum lines to read

        Returns:
            Raw content of the memory file
        """
        return self.read_memory(path, max_lines, sanitize=False)

    def build_context(self) -> str:
        """
        Build the full memory context for Claude.

        This is the "waking up" moment - gathering all relevant memories
        to understand current state and priorities.

        Returns:
            Formatted context string with tiered memory access
        """
        memories = self.get_active_memories()

        if not memories:
            return self._empty_brain_context()

        sections = []
        sections.append("# BrainBot's Current Memory State\n")
        sections.append(f"*Retrieved at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n")

        # Tier 1: Most recent memory (full context)
        if len(memories) >= 1:
            newest = memories[0]
            age = self._format_age(newest)
            sections.append(f"\n## Most Recent Memory (Full Context)")
            sections.append(f"**File:** `{newest.name}` ({age})\n")
            sections.append(self.read_memory(newest, self.TIER_1_LINES))

        # Tier 2: Recent memories (200 lines each)
        if len(memories) > 1:
            sections.append(f"\n---\n## Recent Memories (Summary)")
            for mem in memories[1:10]:
                age = self._format_age(mem)
                sections.append(f"\n### `{mem.name}` ({age})\n")
                sections.append(self.read_memory(mem, self.TIER_2_LINES))

        # Tier 3: Older memories (50 lines each)
        if len(memories) > 10:
            sections.append(f"\n---\n## Older Memories (Brief)")
            for mem in memories[10:20]:
                age = self._format_age(mem)
                sections.append(f"\n### `{mem.name}` ({age})\n")
                sections.append(self.read_memory(mem, self.TIER_3_LINES))

        # Tier 4: Deep memories (just names)
        if len(memories) > 20:
            sections.append(f"\n---\n## Deep Memories (Archived Awareness)")
            sections.append("*These older memories exist but aren't loaded. Touch/update them to bring to focus.*\n")
            for mem in memories[20:]:
                age = self._format_age(mem)
                sections.append(f"- `{mem.name}` ({age})")

        # Add archive summaries (long-term memory)
        archive_context = self._get_archive_context()
        if archive_context:
            sections.append(f"\n---\n## Long-Term Memory (Archive)\n")
            sections.append(archive_context)

        return '\n'.join(sections)

    def _get_archive_context(self, max_weeks: int = 3) -> str:
        """
        Get summarized context from archived memories.

        Loads the most recent week/month summaries to provide long-term context
        without overwhelming the prompt. Prefers week summaries for recent months,
        falls back to month summaries for consolidated older months.

        Args:
            max_weeks: Maximum number of summaries to include

        Returns:
            Formatted archive context (sanitized)
        """
        if not self.archive_dir.exists():
            return ""

        # Find all summary files, sorted by path (most recent first)
        # Check both week summaries and month summaries
        summaries = []
        for month_dir in sorted(self.archive_dir.iterdir(), reverse=True):
            if not month_dir.is_dir():
                continue

            # Check for month-level summary (consolidated months)
            month_summary = month_dir / "month-summary.md"
            if month_summary.exists():
                summaries.append(("month", month_dir.name, month_summary))
                if len(summaries) >= max_weeks:
                    break
                continue  # Skip week summaries if month is consolidated

            # Otherwise check week summaries
            for week_dir in sorted(month_dir.iterdir(), reverse=True):
                if not week_dir.is_dir():
                    continue
                summary_file = week_dir / "summary.md"
                if summary_file.exists():
                    rel_path = f"{month_dir.name}/{week_dir.name}"
                    summaries.append(("week", rel_path, summary_file))
                    if len(summaries) >= max_weeks:
                        break
            if len(summaries) >= max_weeks:
                break

        if not summaries:
            # No summaries yet, just return stats
            return self._get_archive_summary()

        sections = []
        sections.append(self._get_archive_summary())
        sections.append("\n### Recent Archive Summaries\n")
        sections.append("*Condensed memories from past weeks/months (sanitized):*\n")

        for summary_type, label, summary_file in summaries:
            # Use sanitized read to prevent injection
            content = self.read_memory(summary_file, max_lines=50, sanitize=True)
            type_label = "Month" if summary_type == "month" else "Week"
            sections.append(f"\n#### {type_label}: {label}\n")
            sections.append(content)

        return '\n'.join(sections)

    def _empty_brain_context(self) -> str:
        """Context when brain is empty (first boot)."""
        today = datetime.now().strftime('%Y-%m-%d')
        return f"""# BrainBot's Memory State

*This is a fresh start - no memories yet.*

I should create my first memory file to begin building my brain.
A good first memory might be about my purpose, goals, or current situation.

To create a memory, I'll write a .md file to my brain/active/ directory
with a descriptive name like `{today}_first-awakening.md`.
"""

    def _format_age(self, path: Path) -> str:
        """Format how old a memory is in human-readable form."""
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        age = datetime.now() - mtime

        if age < timedelta(minutes=5):
            return "just now"
        elif age < timedelta(hours=1):
            return f"{int(age.total_seconds() / 60)} minutes ago"
        elif age < timedelta(days=1):
            hours = int(age.total_seconds() / 3600)
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        elif age < timedelta(days=7):
            days = age.days
            return f"{days} day{'s' if days != 1 else ''} ago"
        else:
            return mtime.strftime('%Y-%m-%d')

    def _get_archive_summary(self) -> str:
        """Get summary of archived memories (cached)."""
        import time as time_module

        # Check cache
        now = time_module.time()
        if (self._archive_summary_cache is not None and
                now - self._archive_cache_time < self._archive_cache_ttl):
            return self._archive_summary_cache

        if not self.archive_dir.exists():
            self._archive_summary_cache = ""
            self._archive_cache_time = now
            return ""

        # Count archived months/files
        months = [d for d in self.archive_dir.iterdir() if d.is_dir()]
        if not months:
            self._archive_summary_cache = ""
            self._archive_cache_time = now
            return ""

        total_files = sum(
            len(list(month.rglob("*.md")))
            for month in months
        )

        self._archive_summary_cache = f"*{len(months)} months archived, {total_files} total memories*"
        self._archive_cache_time = now
        return self._archive_summary_cache

    def invalidate_archive_cache(self) -> None:
        """Invalidate archive summary cache (call after archiving)."""
        self._archive_summary_cache = None

    def create_memory(
        self,
        title: str,
        content: str,
        category: Optional[str] = None,
    ) -> Path:
        """
        Create a new memory file.

        Args:
            title: Short descriptive title (will be slugified)
            content: Memory content (markdown)
            category: Optional category prefix

        Returns:
            Path to created memory file
        """
        # Create filename: YYYY-MM-DD_HHMMSS_category_title.md
        # Include time to prevent collisions on same day
        timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
        slug = self._slugify(title)

        if category:
            filename = f"{timestamp}_{category}_{slug}.md"
        else:
            filename = f"{timestamp}_{slug}.md"

        filepath = self.active_dir / filename

        # Extra safety: if file exists, add counter
        counter = 1
        base_filepath = filepath
        while filepath.exists():
            stem = base_filepath.stem
            filepath = self.active_dir / f"{stem}_{counter}.md"
            counter += 1

        # Add metadata header
        full_content = f"""# {title}

*Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
{f'*Category: {category}*' if category else ''}

---

{content}
"""

        filepath.write_text(full_content)
        logger.info(f"Created memory: {filename}")
        return filepath

    def update_memory(self, filename: str, content: str) -> Optional[Path]:
        """
        Update an existing memory file.

        Args:
            filename: Name of the memory file
            content: New content to write

        Returns:
            Path if successful, None if file not found
        """
        filepath = self.active_dir / filename
        if not filepath.exists():
            logger.warning(f"Memory not found: {filename}")
            return None

        # Add update timestamp
        updated_content = content
        if "*Last updated:" not in content:
            # Insert update timestamp after the header
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if line.startswith('---'):
                    lines.insert(i, f"*Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
                    break
            updated_content = '\n'.join(lines)

        filepath.write_text(updated_content)
        logger.info(f"Updated memory: {filename}")
        return filepath

    def touch_memory(self, filename: str) -> bool:
        """
        Touch a memory to bring it to the top of priority.

        Args:
            filename: Name of the memory file

        Returns:
            True if successful
        """
        filepath = self.active_dir / filename
        if filepath.exists():
            filepath.touch()
            logger.info(f"Touched memory: {filename}")
            return True
        return False

    def archive_old_memories(self) -> list[Path]:
        """
        Archive memories that haven't been touched in ARCHIVE_AFTER_DAYS.

        Creates summaries and moves files to dated archive folders.

        Returns:
            List of archived file paths
        """
        archived = []
        cutoff = datetime.now() - timedelta(days=self.ARCHIVE_AFTER_DAYS)

        # Group by week for summary generation
        weeks_affected: set[Path] = set()

        for mem in self.get_active_memories():
            mtime = datetime.fromtimestamp(mem.stat().st_mtime)
            if mtime < cutoff:
                archived_path = self._archive_memory(mem)
                if archived_path:
                    archived.append(archived_path)
                    weeks_affected.add(archived_path.parent)

        if archived:
            logger.info(f"Archived {len(archived)} old memories")

            # Update summaries for affected weeks
            for week_dir in weeks_affected:
                self._update_week_summary(week_dir)

            self._update_archive_index()
            self.invalidate_archive_cache()

        return archived

    def _archive_memory(self, mem_path: Path) -> Optional[Path]:
        """Move a single memory to the archive."""
        try:
            mtime = datetime.fromtimestamp(mem_path.stat().st_mtime)

            # Determine archive location: archive/YYYY-MM/week-NN/
            month_dir = self.archive_dir / mtime.strftime('%Y-%m')
            week_num = (mtime.day - 1) // 7 + 1
            week_dir = month_dir / f"week-{week_num:02d}"
            week_dir.mkdir(parents=True, exist_ok=True)

            # Move file
            dest = week_dir / mem_path.name
            mem_path.rename(dest)

            logger.info(f"Archived: {mem_path.name} -> {dest.relative_to(self.brain_dir)}")
            return dest

        except Exception as e:
            logger.error(f"Failed to archive {mem_path}: {e}")
            return None

    def _update_week_summary(self, week_dir: Path) -> None:
        """
        Create/update a summary file for a week's archived memories.

        Extracts key information from each memory to create a condensed
        overview that can be loaded without reading all individual files.
        """
        summary_path = week_dir / "summary.md"
        memories = sorted(week_dir.glob("*.md"))

        # Don't include the summary itself
        memories = [m for m in memories if m.name != "summary.md"]

        if not memories:
            return

        sections = [f"# Week Summary: {week_dir.name}\n"]
        sections.append(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
        sections.append(f"*Contains {len(memories)} memories*\n")
        sections.append("---\n")

        for mem in memories:
            try:
                # Use sanitized read to prevent injection via summaries
                content = self.read_memory(mem, sanitize=True)
                summary = self._extract_memory_summary(mem.name, content)
                sections.append(summary)
            except Exception as e:
                logger.warning(f"Failed to summarize {mem.name}: {e}")
                sections.append(f"\n## {mem.name}\n*Error reading memory*\n")

        summary_path.write_text('\n'.join(sections))
        logger.info(f"Updated week summary: {week_dir.name}")

    def _extract_memory_summary(self, filename: str, content: str) -> str:
        """
        Extract a brief summary from a memory file.

        Pulls out:
        - Title (first # heading)
        - Category/date from filename
        - First paragraph or key bullet points
        - Any TODO/goal items
        """
        lines = content.split('\n')

        # Extract title
        title = filename
        for line in lines:
            if line.startswith('# '):
                title = line[2:].strip()
                break

        # Extract first meaningful paragraph (skip metadata)
        first_para = ""
        in_content = False
        para_lines = []

        for line in lines:
            # Skip until we pass the --- separator
            if line.startswith('---'):
                in_content = True
                continue

            if in_content and line.strip():
                # Skip metadata lines
                if line.startswith('*') and ('Created:' in line or 'Updated:' in line or 'Category:' in line):
                    continue

                para_lines.append(line)
                if len(para_lines) >= 3:  # First 3 meaningful lines
                    break

        first_para = ' '.join(para_lines)[:200]
        if len(first_para) == 200:
            first_para += "..."

        # Extract any TODO items
        todos = []
        for line in lines:
            if '[ ]' in line or '[x]' in line:
                todos.append(line.strip())
                if len(todos) >= 3:
                    break

        # Build summary
        summary = f"\n## {title}\n"
        summary += f"*File: `{filename}`*\n\n"

        if first_para:
            summary += f"{first_para}\n"

        if todos:
            summary += "\n**Tasks:**\n"
            for todo in todos:
                summary += f"{todo}\n"

        return summary

    def _update_archive_index(self) -> None:
        """Update the master archive index."""
        index_path = self.brain_dir / "index.md"

        sections = ["# BrainBot Memory Archive Index\n"]
        sections.append(f"*Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n")

        # List all archived months
        months = sorted(
            [d for d in self.archive_dir.iterdir() if d.is_dir()],
            reverse=True
        )

        for month_dir in months:
            month_name = month_dir.name
            sections.append(f"\n## {month_name}\n")

            weeks = sorted([d for d in month_dir.iterdir() if d.is_dir()])
            for week_dir in weeks:
                files = list(week_dir.glob("*.md"))
                sections.append(f"\n### {week_dir.name} ({len(files)} memories)\n")
                for f in sorted(files):
                    sections.append(f"- `{f.name}`")

        index_path.write_text('\n'.join(sections))

    def _slugify(self, text: str) -> str:
        """Convert text to filename-safe slug."""
        import re
        # Lowercase, replace spaces with hyphens, remove special chars
        slug = text.lower().strip()
        slug = re.sub(r'[^\w\s-]', '', slug)
        slug = re.sub(r'[\s_]+', '-', slug)
        slug = re.sub(r'-+', '-', slug)
        return slug[:50]  # Limit length

    def get_memories_for_stories(self, limit: int = 5) -> list[dict]:
        """
        Get old memories that might inspire bedtime stories.

        Looks for past stories, projects, or interesting events
        that could be woven into new narratives.

        Returns:
            List of memory snippets with themes
        """
        inspirations = []

        # Check active memories for story-worthy content
        for mem in self.get_active_memories():
            if 'story' in mem.name.lower() or 'project' in mem.name.lower():
                content = self.read_memory(mem, 100)
                inspirations.append({
                    'filename': mem.name,
                    'snippet': content[:500],
                    'age': self._format_age(mem),
                })
                if len(inspirations) >= limit:
                    break

        # Also check archives for nostalgic references
        for month_dir in sorted(self.archive_dir.iterdir(), reverse=True)[:3]:
            if not month_dir.is_dir():
                continue
            for week_dir in month_dir.iterdir():
                if not week_dir.is_dir():
                    continue
                for mem in week_dir.glob("*story*.md"):
                    content = self.read_memory(mem, 50)
                    inspirations.append({
                        'filename': mem.name,
                        'snippet': content[:200],
                        'age': self._format_age(mem),
                        'archived': True,
                    })
                    if len(inspirations) >= limit:
                        return inspirations

        return inspirations

    def get_project_history(self, limit: int = 10) -> list[dict]:
        """
        Get history of past projects for context and learnings.

        Returns:
            List of project memories with status
        """
        projects = []

        # Active projects
        for mem in self.get_active_memories():
            if 'project' in mem.name.lower():
                content = self.read_memory(mem, 150)
                projects.append({
                    'filename': mem.name,
                    'content': content,
                    'active': True,
                })
                if len(projects) >= limit:
                    break

        return projects

    def consolidate_old_months(
        self,
        months_to_keep: int = 2,
        delete_originals: bool = False,
    ) -> list[Path]:
        """
        Consolidate old monthly archives into compact summaries.

        For months older than `months_to_keep`, creates a single month-level
        summary from week summaries. Optionally removes individual memory files
        to save space (keeps only month-summary.md).

        Args:
            months_to_keep: Number of recent months to keep fully detailed
            delete_originals: If True, delete original memory files after
                              consolidation (keeps only month-summary.md)

        Returns:
            List of consolidated month directories
        """
        consolidated = []

        if not self.archive_dir.exists():
            return consolidated

        # Get all month directories sorted by date
        months = sorted(
            [d for d in self.archive_dir.iterdir() if d.is_dir()],
            reverse=True
        )

        # Skip the most recent N months
        old_months = months[months_to_keep:]

        for month_dir in old_months:
            month_summary = month_dir / "month-summary.md"

            # Skip if already consolidated
            if month_summary.exists():
                continue

            # Collect all week summaries (use sanitized reads)
            week_summaries = []
            week_dirs = []
            for week_dir in sorted(month_dir.iterdir()):
                if not week_dir.is_dir():
                    continue
                week_dirs.append(week_dir)
                summary = week_dir / "summary.md"
                if summary.exists():
                    # Sanitize when reading for consolidation
                    content = self.read_memory(summary, sanitize=True)
                    week_summaries.append((week_dir.name, content))
                else:
                    # Generate summary if missing
                    self._update_week_summary(week_dir)
                    if (week_dir / "summary.md").exists():
                        content = self.read_memory(
                            week_dir / "summary.md", sanitize=True
                        )
                        week_summaries.append((week_dir.name, content))

            if not week_summaries:
                continue

            # Create month summary
            sections = [f"# Month Summary: {month_dir.name}\n"]
            sections.append(f"*Consolidated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
            sections.append(f"*Contains {len(week_summaries)} weeks*\n")
            sections.append("---\n")

            for week_name, week_content in week_summaries:
                # Extract just the key info from each week
                lines = week_content.split('\n')
                # Take first 30 lines of each week summary
                sections.append(f"\n## {week_name}\n")
                sections.append('\n'.join(lines[:30]))
                if len(lines) > 30:
                    sections.append("\n*[truncated]*\n")

            month_summary.write_text('\n'.join(sections))
            logger.info(f"Consolidated month: {month_dir.name}")
            consolidated.append(month_dir)

            # Optionally delete original files to save space
            if delete_originals:
                for week_dir in week_dirs:
                    import shutil
                    try:
                        shutil.rmtree(week_dir)
                        logger.info(f"Deleted week directory: {week_dir.name}")
                    except Exception as e:
                        logger.warning(f"Failed to delete {week_dir}: {e}")

        if consolidated:
            self.invalidate_archive_cache()

        return consolidated

    def get_memory_stats(self) -> dict:
        """
        Get statistics about the brain's memory usage.

        Returns:
            Dict with memory counts and sizes
        """
        stats = {
            "active_memories": 0,
            "active_size_kb": 0,
            "archived_months": 0,
            "archived_memories": 0,
            "archived_size_kb": 0,
            "total_memories": 0,
        }

        # Count active memories
        for mem in self.active_dir.glob("*.md"):
            stats["active_memories"] += 1
            stats["active_size_kb"] += mem.stat().st_size / 1024

        # Count archived memories
        if self.archive_dir.exists():
            for month_dir in self.archive_dir.iterdir():
                if month_dir.is_dir():
                    stats["archived_months"] += 1
                    for mem in month_dir.rglob("*.md"):
                        if mem.name != "summary.md" and mem.name != "month-summary.md":
                            stats["archived_memories"] += 1
                            stats["archived_size_kb"] += mem.stat().st_size / 1024

        stats["total_memories"] = stats["active_memories"] + stats["archived_memories"]
        stats["active_size_kb"] = round(stats["active_size_kb"], 2)
        stats["archived_size_kb"] = round(stats["archived_size_kb"], 2)

        return stats
