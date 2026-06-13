from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings


settings = get_settings()

# Where Linux auto-mounts removable drives. /media/<user>/<label> for desktop
# auto-mount, /mnt/* and /media/* for manual/legacy mounts, /run/media/<user>/*
# on some distros.
_MOUNT_GLOBS = ("/media/*/*", "/media/*", "/run/media/*/*", "/mnt/*")


@dataclass
class StorageTarget:
    path: str
    label: str
    is_mount: bool
    writable: bool
    total_bytes: int | None
    free_bytes: int | None

    def to_dict(self) -> dict:
        # camelCase to match the frontend convention.
        return {
            "path": self.path,
            "label": self.label,
            "isMount": self.is_mount,
            "writable": self.writable,
            "totalBytes": self.total_bytes,
            "freeBytes": self.free_bytes,
        }


def _disk_info(path: Path) -> tuple[int | None, int | None]:
    try:
        usage = shutil.disk_usage(str(path))
        return usage.total, usage.free
    except OSError:
        return None, None


def _is_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".pipesight_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def describe_target(path: Path, *, label: str | None = None) -> StorageTarget:
    total, free = _disk_info(path)
    return StorageTarget(
        path=str(path),
        label=label or path.name or str(path),
        is_mount=os.path.ismount(str(path)),
        writable=_is_writable(path),
        total_bytes=total,
        free_bytes=free,
    )


def scan_removable() -> list[StorageTarget]:
    """List currently mounted removable/external storage locations."""
    seen: set[str] = set()
    targets: list[StorageTarget] = []
    for pattern in _MOUNT_GLOBS:
        for entry in Path("/").glob(pattern.lstrip("/")):
            resolved = str(entry)
            if resolved in seen or not entry.is_dir():
                continue
            # Only surface real mount points (an actual external/removable FS),
            # not arbitrary empty dirs under /mnt.
            if not os.path.ismount(resolved):
                continue
            seen.add(resolved)
            targets.append(describe_target(entry))
    return targets


def options() -> dict:
    """Everything the settings UI needs to render the storage picker."""
    default = describe_target(settings.storage_dir, label="内部存储")
    current_path = settings.active_storage_dir
    return {
        "currentPath": str(current_path),
        "defaultPath": str(settings.storage_dir),
        "usingDefault": str(current_path) == str(settings.storage_dir),
        "internal": default.to_dict(),
        "removable": [t.to_dict() for t in scan_removable()],
    }


def validate_path(raw: str) -> StorageTarget:
    """Validate a user-chosen path; raises ValueError if unusable."""
    if not raw or not raw.strip():
        raise ValueError("路径不能为空")
    path = Path(raw.strip())
    if not _is_writable(path):
        raise ValueError(f"路径不可写或无法创建：{path}")
    return describe_target(path)
