"""
Centralized shared_state directory resolver.

Returns shared_state/YYYY-MM-DD/ for daily organization.
The orchestrator freezes the date in SHARED_STATE_DIR env var at startup
so all modules and agent subprocesses use the same directory.
"""

import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path


def get_state_dir() -> Path:
    """Return today's shared_state directory, creating it if needed."""
    env_dir = os.environ.get("SHARED_STATE_DIR")
    if env_dir:
        p = Path(env_dir)
    else:
        today = datetime.now().strftime("%Y-%m-%d")
        p = Path("shared_state") / today
    p.mkdir(parents=True, exist_ok=True)
    return p


def cleanup_old_state(keep_days: int = 7):
    """Remove shared_state daily directories older than keep_days."""
    base = Path("shared_state")
    if not base.exists():
        return
    cutoff = datetime.now() - timedelta(days=keep_days)
    for child in base.iterdir():
        if not child.is_dir():
            continue
        try:
            dir_date = datetime.strptime(child.name, "%Y-%m-%d")
            if dir_date < cutoff:
                shutil.rmtree(child)
                print(f"  🗑️  Cleaned up old state: {child}")
        except ValueError:
            pass  # skip non-date directories
