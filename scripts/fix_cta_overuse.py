#!/usr/bin/env python3
"""
修复 segments.json 中 CTA 过多的问题

用法：
    python scripts/fix_cta_overuse.py output/rsi_cn/segments.json

逻辑：
    - 只有最后一个 segment 允许类型为 "cta"
    - 其他被误标为 "cta" 的 segment 降级为 "narrative"
"""

import json
import sys
from pathlib import Path


def fix_cta_overuse(segments_path: str):
    path = Path(segments_path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    segments = data.get("segments", [])
    if not segments:
        print("No segments found")
        return

    total = len(segments)
    fixed = 0

    for i, seg in enumerate(segments):
        if seg.get("segment_type") == "cta" and i < total - 1:
            seg["segment_type"] = "narrative"
            seg["segment_type_confidence"] = 0.5
            fixed += 1
            print(f"  Fixed {seg['id']}: cta -> narrative")

    if fixed > 0:
        # 备份原文件
        backup_path = path.with_suffix(".json.bak")
        path.rename(backup_path)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"\nFixed {fixed} segment(s). Original backed up to {backup_path.name}")
    else:
        print("No overuse CTA segments found. All good!")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <segments.json>")
        sys.exit(1)
    fix_cta_overuse(sys.argv[1])
