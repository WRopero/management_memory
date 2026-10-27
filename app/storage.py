"""Tamaños en disco del volumen de Cognee (solo lectura: os.stat, nunca se abren los .lbug)."""
from __future__ import annotations

import os
from pathlib import Path

from . import config


def _size(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.stat(os.path.join(root, f)).st_size
            except OSError:
                pass
    return total


def graph_files() -> dict[str, dict]:
    """dataset_id -> {bytes, wal_bytes, path}. Los archivos se llaman <dataset_id>.lbug[.wal]."""
    out: dict[str, dict] = {}
    base = Path(config.STORAGE_DIR) / "system" / "databases"
    if not base.exists():
        return out
    for p in base.rglob("*.lbug*"):
        name = p.name
        wal = name.endswith(".wal")
        ds = name[: -len(".lbug.wal")] if wal else name[: -len(".lbug")] if name.endswith(".lbug") else None
        if not ds:
            continue
        try:
            sz = p.stat().st_size
        except OSError:
            continue
        e = out.setdefault(ds, {"bytes": 0, "wal_bytes": 0, "file": str(p.relative_to(config.STORAGE_DIR))})
        e["wal_bytes" if wal else "bytes"] += sz
    return out


def totals() -> dict:
    root = Path(config.STORAGE_DIR)
    if not root.exists():
        return {"available": False}
    return {"available": True, "data_bytes": _size(root / "data"), "system_bytes": _size(root / "system"),
            "total_bytes": _size(root), "raw_files": sum(1 for _ in (root / "data").rglob("*.txt"))}
