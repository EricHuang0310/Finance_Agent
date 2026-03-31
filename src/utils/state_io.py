"""Atomic JSON I/O utilities for shared_state files."""

import json
import os
import tempfile
from pathlib import Path


def save_state_atomic(filepath: Path, data: dict | list) -> None:
    """Write data to a JSON file atomically using temp file + os.replace.

    Args:
        filepath: Target path for the JSON file.
        data: Dict or list to serialize as JSON.

    Raises:
        Any exception from json.dump or os.replace is re-raised after cleanup.
    """
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=filepath.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str, ensure_ascii=False)
        os.replace(tmp_path, filepath)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
