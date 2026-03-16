"""
Enterprise automation package.

Snapshot pipeline, health tracking, trend analysis.
"""
from .snapshot import (
    capture_snapshot,
    list_snapshots,
    compare_snapshots,
    prune_old_snapshots,
    get_trend,
    SNAPSHOTS_DIR,
    RETENTION_DAYS,
)

__all__ = [
    "capture_snapshot",
    "list_snapshots",
    "compare_snapshots",
    "prune_old_snapshots",
    "get_trend",
    "SNAPSHOTS_DIR",
    "RETENTION_DAYS",
]
