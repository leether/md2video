#!/usr/bin/env python3
"""
memory_loader.py — 活记忆加载器

读取 docs/LESSONS_LEARNED.md 的 YAML frontmatter，提取有实质内容的摩擦点，
供 pipeline 运行时自动感知历史教训。

设计对标 md2wechat 的 memory-loader.mjs：
- 纯 Python 实现，无 PyYAML 依赖
- mtime 缓存，避免重复读取
- 启动时打印风险提示
- 高摩擦类别自动附加到 L3 检查清单

Autopoiesis 原则：
    - 活记忆是系统的「免疫系统记忆」：同样的坑不反复踩
    - 运行时加载 = 将历史教训从「静态文档」变成「运行时感知」
    - 风险提示在控制台打印，不阻断流程，但提高警觉
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Any

# ── 模块级缓存 ──
_cache: Optional[Dict] = None
_cache_mtime: Optional[float] = None


def _strip_quotes(s: str) -> str:
    """去除字符串首尾引号"""
    s = s.strip()
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    return s


def _parse_yaml_frontmatter(content: str) -> Optional[Dict[str, Any]]:
    """
    轻量 YAML frontmatter 解析器

    只处理 LESSONS_LEARNED.md 的实际格式：
    ---
    key: value
    key: "value"
    array:
      - key: value
        key: value
    ---
    """
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return None

    # 找第二个 ---
    end_idx = -1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break

    if end_idx == -1:
        return None

    yaml_lines = lines[1:end_idx]
    result: Dict[str, Any] = {"friction_points": []}

    i = 0
    while i < len(yaml_lines):
        line = yaml_lines[i]
        trimmed = line.strip()

        # 跳过空行和注释
        if not trimmed or trimmed.startswith("#"):
            i += 1
            continue

        # 数组项开始：- key: value
        if trimmed.startswith("- "):
            after_dash = trimmed[2:].strip()
            kv_match = _match_kv(after_dash)
            if kv_match:
                # 对象数组项的开始
                key, val = kv_match
                obj: Dict[str, Any] = {key: _strip_quotes(val)}
                i += 1
                # 继续读取同对象的后续字段（缩进更大）
                while i < len(yaml_lines):
                    next_line = yaml_lines[i]
                    next_trimmed = next_line.strip()
                    # 遇到新的数组项或分隔线则停止
                    if next_trimmed.startswith("- "):
                        break
                    if next_trimmed == "---":
                        break
                    if not next_trimmed:
                        # 空行：检查下一行是否是新数组项
                        if i + 1 < len(yaml_lines) and yaml_lines[i + 1].strip().startswith("- "):
                            i += 1
                            break
                        i += 1
                        continue
                    next_kv = _match_kv(next_trimmed)
                    if next_kv:
                        k, v = next_kv
                        obj[k] = _strip_quotes(v)
                    i += 1
                result["friction_points"].append(obj)
                continue
            else:
                i += 1
                continue

        # 顶层键值对
        top_kv = _match_kv(trimmed)
        if top_kv:
            k, v = top_kv
            if k != "friction_points":
                result[k] = _strip_quotes(v)
            i += 1
            continue

        i += 1

    return result


def _match_kv(text: str) -> Optional[tuple]:
    """匹配 key: value 格式，返回 (key, value) 或 None"""
    # 支持 key: value, key:"value", key: 'value', key: 123, key: true
    import re
    m = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*):\s*(.*)$', text)
    if m:
        return m.group(1), m.group(2).strip()
    return None


def _parse_value(v: str) -> Any:
    """尝试将字符串解析为 bool/int/float/str"""
    v = v.strip()
    if v == "true":
        return True
    if v == "false":
        return False
    if v == "null" or v == "~":
        return None
    # 整数
    if v.isdigit() or (v.startswith("-") and v[1:].isdigit()):
        return int(v)
    # 浮点数
    try:
        return float(v)
    except ValueError:
        pass
    return _strip_quotes(v)


def load_living_memory(lessons_path: Optional[str] = None) -> Dict[str, Any]:
    """
    加载活记忆（带 mtime 缓存）

    Returns:
        {
            "loaded": bool,
            "evolution_count": int,
            "last_updated": str,
            "total_friction_points": int,
            "recent_friction_points": List[Dict],  # 最近5条
            "high_friction_points": List[Dict],    # 高摩擦类别前3条
            "all_categories": List[str],           # 所有类别
            "reason": str,  # 加载失败原因
        }
    """
    global _cache, _cache_mtime

    if lessons_path is None:
        lessons_path = str(Path(__file__).parent.parent / "docs" / "LESSONS_LEARNED.md")

    lessons_path = Path(lessons_path)

    if not lessons_path.exists():
        return {"loaded": False, "reason": "file_not_found", "friction_points": []}

    try:
        stat = lessons_path.stat()
        if _cache is not None and _cache_mtime == stat.st_mtime:
            return _cache

        with open(lessons_path, "r", encoding="utf-8") as f:
            content = f.read()

        frontmatter = _parse_yaml_frontmatter(content)

        if frontmatter is None:
            return {"loaded": False, "reason": "no_yaml_frontmatter", "friction_points": []}

        # 过滤出有实质内容的摩擦点
        valid_fps = [
            fp for fp in frontmatter.get("friction_points", [])
            if isinstance(fp, dict)
            and fp.get("description")
            and str(fp.get("description")).strip()
            and str(fp.get("description")).strip().lower() != "undefined"
        ]

        # 按 timestamp 降序
        def _ts_key(fp: Dict) -> float:
            ts = fp.get("timestamp", "")
            try:
                from datetime import datetime
                return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
            except Exception:
                return 0.0

        sorted_fps = sorted(valid_fps, key=_ts_key, reverse=True)
        recent = sorted_fps[:5]

        # 高摩擦类别：按类别出现频率取 top 3
        from collections import Counter
        cat_counts = Counter(fp.get("category", "未分类") for fp in valid_fps)
        high_cats = [cat for cat, _ in cat_counts.most_common(3)]
        high_friction = [fp for fp in sorted_fps if fp.get("category") in high_cats][:3]

        result = {
            "loaded": True,
            "evolution_count": frontmatter.get("evolution_count", len(valid_fps)),
            "last_updated": frontmatter.get("last_updated", ""),
            "total_friction_points": len(valid_fps),
            "recent_friction_points": recent,
            "high_friction_points": high_friction,
            "all_categories": sorted(list(set(fp.get("category", "未分类") for fp in valid_fps if fp.get("category")))),
            "friction_points": valid_fps,
        }

        _cache = result
        _cache_mtime = stat.st_mtime
        return result

    except Exception as e:
        return {"loaded": False, "reason": str(e), "friction_points": []}


def format_risk_warnings(memory: Dict[str, Any]) -> str:
    """
    格式化风险提示（供渲染器/拼接引擎启动时打印）

    Returns: 人类可读的警告字符串，可直接 print()
    """
    if not memory.get("loaded") or not memory.get("high_friction_points"):
        return ""

    lines = []
    lines.append("")
    lines.append("━━━ 🧠 活记忆风险提示 ━━━")
    lines.append(
        f"已加载 {memory['total_friction_points']} 条历史摩擦点，"
        f"最近高摩擦类别：{'、'.join(memory['all_categories'][:3]) or '无'}"
    )
    lines.append("")

    for fp in memory["high_friction_points"]:
        desc = fp.get("description", "")[:80]
        resolution = fp.get("resolution", "")
        lines.append(f"  ⚡ [{fp.get('id', '?')}] {fp.get('category', '未分类')}: {desc}")
        if resolution:
            lines.append(f"     → {resolution[:80]}")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


def format_l3_memory_items(memory: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    格式化 L3 人工确认附加项（供 harness 附加到 L3 检查清单）

    Returns: List[Dict] 每个元素可附加到 harness 的 L3 needsReview 列表
    """
    if not memory.get("loaded") or not memory.get("recent_friction_points"):
        return []

    items = []
    for fp in memory["recent_friction_points"]:
        desc = fp.get("description", "")
        resolution = fp.get("resolution", "")
        msg = f"[活记忆] {desc}"
        if resolution:
            msg += f" → {resolution}"
        items.append({
            "level": "L3",
            "id": f"memory_{fp.get('id', '?')}",
            "message": msg,
            "source": "living_memory",
            "friction_id": fp.get("id"),
            "category": fp.get("category"),
            "auto_detect": False,
        })
    return items


# ── CLI 测试入口 ──
def main():
    import json
    memory = load_living_memory()
    print(format_risk_warnings(memory))
    l3_items = format_l3_memory_items(memory)
    if l3_items:
        print("\nL3 附加项:")
        for item in l3_items:
            print(f"  {item['id']}: {item['message']}")
    print("\n" + json.dumps({
        "loaded": memory["loaded"],
        "evolution_count": memory.get("evolution_count", 0),
        "last_updated": memory.get("last_updated", ""),
        "total_friction_points": memory.get("total_friction_points", 0),
        "recent_count": len(memory.get("recent_friction_points", [])),
        "high_count": len(memory.get("high_friction_points", [])),
        "categories": memory.get("all_categories", []),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
