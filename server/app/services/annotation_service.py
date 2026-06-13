from __future__ import annotations

import base64
import binascii
import json
from datetime import datetime
from pathlib import Path

from app.config import get_settings


settings = get_settings()


def _annotations_dir() -> Path:
    base = settings.active_storage_dir / "annotations"
    (base / "rendered").mkdir(parents=True, exist_ok=True)
    return base


def _decode_data_url(data_url: str) -> bytes:
    # Accept "data:image/png;base64,...." or a bare base64 string.
    payload = data_url.split(",", 1)[1] if data_url.startswith("data:") else data_url
    try:
        return base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("invalid base64 image data") from exc


def save_annotation(
    *,
    annotation_json: dict,
    rendered_png_data_url: str | None,
) -> tuple[Path | None, Path, dict]:
    """Persist a graphical annotation: rendered PNG + json sidecar.

    Returns (rendered_path, json_path, stored_json). Raises ValueError on bad
    image data.
    """
    base = _annotations_dir()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]

    rendered_path: Path | None = None
    if rendered_png_data_url:
        rendered_bytes = _decode_data_url(rendered_png_data_url)
        rendered_path = base / "rendered" / f"annotation_{stamp}.png"
        rendered_path.write_bytes(rendered_bytes)

    stored = dict(annotation_json)
    stored["renderedImage"] = str(rendered_path) if rendered_path else ""
    stored["savedAt"] = datetime.now().isoformat(timespec="seconds")

    json_path = base / f"annotation_{stamp}.json"
    json_path.write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")

    return rendered_path, json_path, stored
