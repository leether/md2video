#!/usr/bin/env python3
"""Validate CTA resource registry and local media fingerprints."""

import hashlib
import json
import sys
from pathlib import Path

from PIL import Image, UnidentifiedImageError


REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = REPO_ROOT / "cta_resources.json"
ALLOWED_TARGET_PREFIXES = ("http://", "https://", "wechat://")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def short_target_checksum(target_url: str) -> str:
    return hashlib.sha256(target_url.encode("utf-8")).hexdigest()[:16]


def validate_registry() -> list[str]:
    errors: list[str] = []

    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        registry = json.load(f)

    resources = registry.get("resources", [])
    if registry.get("resource_count") != len(resources):
        errors.append("resource_count does not match resources length")

    for resource in resources:
        rid = resource.get("id", "<missing-id>")

        target_url = resource.get("target_url", "")
        if not target_url.startswith(ALLOWED_TARGET_PREFIXES):
            errors.append(f"[{rid}] unsupported target_url scheme")
        elif resource.get("checksum") != short_target_checksum(target_url):
            errors.append(f"[{rid}] target_url checksum mismatch")

        media_path_value = resource.get("media_path", "")
        media_path = Path(media_path_value)
        if not media_path_value or media_path.is_absolute():
            errors.append(f"[{rid}] media_path must be a repo-relative path")
            continue

        full_media_path = (REPO_ROOT / media_path).resolve()
        try:
            full_media_path.relative_to(REPO_ROOT)
        except ValueError:
            errors.append(f"[{rid}] media_path escapes the repository")
            continue

        if not full_media_path.exists():
            errors.append(f"[{rid}] media file is missing: {media_path_value}")
            continue

        media_sha256 = sha256_file(full_media_path)
        if resource.get("media_sha256") != media_sha256:
            errors.append(f"[{rid}] media_sha256 mismatch")
        if resource.get("source_sha256") and resource["source_sha256"] != media_sha256:
            errors.append(f"[{rid}] source_sha256 mismatch")

        try:
            with Image.open(full_media_path) as img:
                media_format = img.format or ""
                pixel_width = img.width
                pixel_height = img.height
        except UnidentifiedImageError:
            errors.append(f"[{rid}] media file is not a readable image")
            continue

        if resource.get("media_format") != media_format:
            errors.append(f"[{rid}] media_format mismatch")
        if resource.get("pixel_width") != pixel_width:
            errors.append(f"[{rid}] pixel_width mismatch")
        if resource.get("pixel_height") != pixel_height:
            errors.append(f"[{rid}] pixel_height mismatch")

        if not resource.get("source_repo") or not resource.get("source_path"):
            errors.append(f"[{rid}] source_repo/source_path must be recorded")

        if resource.get("valid") is not True:
            errors.append(f"[{rid}] valid must be true")

    return errors


def main() -> int:
    errors = validate_registry()
    if errors:
        for error in errors:
            print(f"CTA_RESOURCE_ERROR {error}", file=sys.stderr)
        return 1

    print("CTA_RESOURCE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
