from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Annotation, Marker, MediaAsset


settings = get_settings()

MEDIA_ROLLING_LIMIT_BYTES = 32 * 1024 * 1024 * 1024
_ROLLING_MEDIA_TYPES = ("photo", "video")
_ROLLING_MEDIA_SUFFIXES = {".jpg", ".jpeg", ".json", ".mp4", ".png"}

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


def _path_in_active_storage(path: str | Path | None) -> Path | None:
    if not path:
        return None
    candidate = Path(path)
    try:
        candidate.resolve().relative_to(settings.active_storage_dir.resolve())
    except (OSError, ValueError):
        return None
    return candidate


def _file_size(path: Path | None) -> int:
    if path is None:
        return 0
    try:
        return path.stat().st_size if path.is_file() else 0
    except OSError:
        return 0


def _managed_media_roots() -> list[Path]:
    root = settings.active_storage_dir
    return [
        root / "snapshots",
        root / "recordings",
        root / "annotations" / "rendered",
    ]


def _managed_media_usage() -> int:
    total = 0
    for root in _managed_media_roots():
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.suffix.lower() not in _ROLLING_MEDIA_SUFFIXES:
                continue
            total += _file_size(path)
    return total


def _asset_paths(asset: MediaAsset, rendered_paths: list[str]) -> list[Path]:
    paths: list[Path] = []
    media_path = _path_in_active_storage(asset.file_path)
    if media_path is not None:
        paths.append(media_path)
        if asset.type == "video":
            paths.append(media_path.with_suffix(".json"))

    thumbnail_path = _path_in_active_storage(asset.thumbnail_path)
    if thumbnail_path is not None:
        paths.append(thumbnail_path)

    for rendered_path in rendered_paths:
        path = _path_in_active_storage(rendered_path)
        if path is not None:
            paths.append(path)

    unique: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        try:
            key = path.resolve()
        except OSError:
            key = path
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def _unlink_managed(path: Path) -> None:
    if _path_in_active_storage(path) is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _delete_media_asset(db: Session, asset: MediaAsset, paths: list[Path]) -> None:
    for path in paths:
        _unlink_managed(path)

    annotations = db.scalars(
        select(Annotation).where(Annotation.media_asset_id == asset.id)
    ).all()
    for annotation in annotations:
        db.delete(annotation)

    markers = db.scalars(select(Marker).where(Marker.media_asset_id == asset.id)).all()
    for marker in markers:
        db.delete(marker)

    db.delete(asset)


def enforce_media_quota(
    db: Session | None = None,
    *,
    max_bytes: int = MEDIA_ROLLING_LIMIT_BYTES,
    protected_asset_ids: set[int] | None = None,
) -> int:
    """Keep photo/video files under the rolling media quota."""
    if db is None:
        from app.db import SessionLocal

        with SessionLocal() as owned_db:
            return enforce_media_quota(
                owned_db,
                max_bytes=max_bytes,
                protected_asset_ids=protected_asset_ids,
            )

    protected = protected_asset_ids or set()
    assets = db.scalars(
        select(MediaAsset)
        .where(MediaAsset.type.in_(_ROLLING_MEDIA_TYPES))
        .order_by(MediaAsset.captured_at.asc(), MediaAsset.id.asc())
    ).all()

    rendered_by_asset: dict[int, list[str]] = {}
    if assets:
        asset_ids = [asset.id for asset in assets]
        annotations = db.scalars(
            select(Annotation).where(Annotation.media_asset_id.in_(asset_ids))
        ).all()
        for annotation in annotations:
            if annotation.rendered_path:
                rendered_by_asset.setdefault(annotation.media_asset_id, []).append(annotation.rendered_path)

    entries: list[tuple[MediaAsset, list[Path], int]] = []
    db_total = 0
    for asset in assets:
        paths = _asset_paths(asset, rendered_by_asset.get(asset.id, []))
        size = sum(_file_size(path) for path in paths)
        if size > 0:
            entries.append((asset, paths, size))
            db_total += size

    total = max(db_total, _managed_media_usage())

    if total <= max_bytes:
        return total

    for asset, paths, size in entries:
        if total <= max_bytes:
            break
        if asset.id in protected:
            continue
        _delete_media_asset(db, asset, paths)
        total -= size

    db.commit()
    return max(total, 0)
