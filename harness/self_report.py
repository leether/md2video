#!/usr/bin/env python3
"""
Self Report — Autopoiesis 自检自报告模块

SKILL 的免疫系统。负责：
1. 自我观察：加载系统状态（cta_resources.json, video-rules.json, timeline.json）
2. 摩擦点捕获：记录 pipeline 运行中的异常和修复
3. 规则演化：自动将新摩擦点编码进 video-rules.json（L3 自动检测项）
4. 活记忆写入：更新 LESSONS_LEARNED.md（YAML frontmatter + Markdown）
5. 自检报告输出：生成 human-readable 和 machine-readable 双格式报告

Autopoiesis 原则：
    - 边界由自我生产定义：self_report.py 只观察和记录系统内部状态
    - 结构耦合：从环境刺激（摩擦点）中学习，更新规则
    - 升级是自我分化的自然结果：新的检查项自然长出，无需外部干预
    - 演化度量：环境变化时，系统维持自身结构的能力

使用方式：
    python harness/self_report.py
    # 或在 pipeline 中调用：
    from harness.self_report import SelfReport
    report = SelfReport()
    report.capture_friction("素材遗漏", "s22 场景缺失", "补充生成 s22 素材")
    report.run()
"""

import json
import os
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Tuple


@dataclass
class FrictionPoint:
    """单个摩擦点记录"""
    id: str
    category: str
    description: str
    resolution: str = ""
    rule_id: Optional[str] = None
    auto_encode: bool = True
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


class SelfReport:
    """
    Autopoiesis 自检自报告器
    """

    def __init__(self, project_dir: str = "."):
        self.project_dir = Path(project_dir)
        self.output_dir = self.project_dir / "output"
        self.rules_path = self.project_dir / "harness" / "video-rules.json"
        self.lessons_path = self.project_dir / "docs" / "LESSONS_LEARNED.md"
        self.cta_path = self.project_dir / "output" / "cta_resources.json"
        self.timeline_path = self.output_dir / "timeline.json"

        self.friction_points: List[FrictionPoint] = []
        self.system_state: Dict = {}
        self.rules: Dict = {}
        self.lessons: Dict = {}
        self.report: Dict = {}

    def _load_json(self, path: Path, default=None) -> Dict:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return default or {}

    def _save_json(self, path: Path, data: Dict):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_system_state(self):
        """加载系统当前状态"""
        self.system_state = {
            "rules_version": self._load_json(self.rules_path, {}).get("version", "unknown"),
            "timeline_exists": self.timeline_path.exists(),
            "cta_exists": self.cta_path.exists(),
            "output_dir_exists": self.output_dir.exists(),
            "segments_count": 0,
            "has_effects": False,
        }

        if self.timeline_path.exists():
            timeline = self._load_json(self.timeline_path)
            self.system_state["segments_count"] = timeline.get("segment_count", 0)
            self.system_state["has_effects"] = timeline.get("has_effects", False)
            self.system_state["total_duration"] = timeline.get("total_duration", 0.0)

        self.rules = self._load_json(self.rules_path, {})

    def capture_friction(
        self,
        category: str,
        description: str,
        resolution: str = "",
        rule_id: Optional[str] = None,
        auto_encode: bool = True,
    ) -> FrictionPoint:
        """
        捕获一个摩擦点

        Args:
            category: 摩擦点类别（如"素材遗漏"、"音画错位"、"计算不一致"）
            description: 详细描述
            resolution: 解决方案（可选）
            rule_id: 关联的 rule_id（可选，auto_encode 时会自动分配）
            auto_encode: 是否自动编码进 rules
        """
        fid = f"f{len(self.friction_points)+1:03d}"
        fp = FrictionPoint(
            id=fid,
            category=category,
            description=description,
            resolution=resolution,
            rule_id=rule_id,
            auto_encode=auto_encode,
        )
        self.friction_points.append(fp)
        return fp

    def _generate_rule_id(self, category: str) -> str:
        """从类别生成 rule_id — 扩展覆盖 v5 实战教训"""
        mapping = {
            "素材遗漏": "no_missing_scene",
            "素材积压": "jimeng_timeout_fallback",
            "音画错位": "audio_video_drift",
            "音画同步": "audio_video_sync",
            "计算不一致": "calculation_consistency",
            "视觉细节": "text_contrast",
            "ffmpeg": "audio_presence",
            "转场": "transition_validity",
            "淡入淡出": "fade_duration_validity",
            "TTS": "tts_voice_consistency",
            "动画语义同步": "animation_semantic_sync",
            "动画时序": "animation_text_timing",
            "即梦素材": "jimeng_background_audio",
            "音频混音": "bg_audio_level",
            "内容质量": "content_accuracy",
        }
        # 安全化 category 字符串
        safe_cat = category.lower().replace(" ", "_").replace("/", "_").replace("-", "_")
        return mapping.get(category, f"auto_{safe_cat}")

    def auto_encode(self, write: bool = True):
        """
        自动将未编码的摩擦点加入 video-rules.json

        策略：
        1. 如果 friction 已有 rule_id 且规则已存在 → 更新规则描述
        2. 如果 friction 没有 rule_id → 生成新 rule_id，在 L3 中创建新检查项
        3. 标记规则为 autopoiesis 演化产物
        """
        if not self.rules:
            return

        l3_checks = self.rules.get("l3_render_checks", {})
        if isinstance(l3_checks, dict):
            l3_checks = l3_checks
        else:
            l3_checks = {}

        new_rules_count = 0

        for fp in self.friction_points:
            if not fp.auto_encode:
                continue

            rule_id = fp.rule_id or self._generate_rule_id(fp.category)

            # 检查规则是否已存在
            existing = l3_checks.get(rule_id) if isinstance(l3_checks, dict) else None
            if not existing:
                # 创建新 L3 检查项
                new_rule = {
                    "id": rule_id,
                    "name": f"[AUTO] {fp.category}",
                    "description": fp.description,
                    "auto_detect": True,
                    "check_fn": "harness._auto_check",
                    "origin_friction": fp.id,
                    "autopoiesis": True,
                }
                if isinstance(l3_checks, dict):
                    l3_checks[rule_id] = new_rule
                new_rules_count += 1
                fp.rule_id = rule_id

        if new_rules_count > 0:
            self.rules["l3_render_checks"] = l3_checks
            self.rules["autopoiesis"] = {
                "self_report_enabled": True,
                "auto_encode": True,
                "last_evolution": datetime.now().isoformat(),
                "evolution_count": self.rules.get("autopoiesis", {}).get("evolution_count", 0) + new_rules_count,
            }
            if write:
                self._save_json(self.rules_path, self.rules)

        return new_rules_count

    def _load_lessons(self) -> Dict:
        """加载 LESSONS_LEARNED.md 的 YAML frontmatter 和正文"""
        if not self.lessons_path.exists():
            return {"frontmatter": {}, "body": ""}

        with open(self.lessons_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 解析 YAML frontmatter — 复用 memory_loader 的纯 Python 解析器
        # 使用 importlib 避免模块路径问题（直接运行 self_report.py 时 __package__ 为 None）
        import importlib.util
        memory_loader_path = Path(__file__).parent / "memory_loader.py"
        spec = importlib.util.spec_from_file_location("memory_loader", memory_loader_path)
        memory_loader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(memory_loader)
        frontmatter = memory_loader._parse_yaml_frontmatter(content) or {}
        body = content
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                body = parts[2].strip()

        return {"frontmatter": frontmatter, "body": body}

    def write_lessons(self):
        """
        更新 LESSONS_LEARNED.md（活记忆器官）

        结构：
        ---
        autopoiesis: true
        memory_type: living
        last_updated: "2026-06-07"
        evolution_count: N
        friction_points:
          - id: "f001"
            category: "素材遗漏"
            ...
        ---
        # 正文
        """
        lessons = self._load_lessons()
        fm = lessons.get("frontmatter", {})

        # 更新 frontmatter
        fm["autopoiesis"] = True
        fm["memory_type"] = "living"
        fm["last_updated"] = datetime.now().strftime("%Y-%m-%d")
        fm["evolution_count"] = int(fm.get("evolution_count", 0)) + len(self.friction_points)

        # 合并摩擦点（确保是列表）
        existing_fps = fm.get("friction_points", [])
        if isinstance(existing_fps, str):
            existing_fps = []
        if not isinstance(existing_fps, list):
            existing_fps = []
        existing_ids = {f.get("id") for f in existing_fps if isinstance(f, dict)}

        for fp in self.friction_points:
            if fp.id not in existing_ids:
                existing_fps.append({
                    "id": fp.id,
                    "category": fp.category,
                    "description": fp.description,
                    "resolution": fp.resolution,
                    "rule_id": fp.rule_id,
                    "timestamp": fp.timestamp,
                })

        fm["friction_points"] = existing_fps

        # 生成正文
        body_lines = ["# LESSONS_LEARNED — md2video 活记忆器官\n"]
        body_lines.append(
            "> 本文档是 md2video SKILL 的「活记忆器官」。每次 pipeline 运行产生摩擦时，"
            "SelfReport 会自动更新此文档。摩擦点与 video-rules.json 中的规则通过 rule_id 形成闭环。\n"
        )

        # 按类别分组
        by_category = {}
        for fp_data in existing_fps:
            cat = fp_data.get("category", "未分类")
            by_category.setdefault(cat, []).append(fp_data)

        for cat, fps in sorted(by_category.items()):
            body_lines.append(f"\n## 摩擦点类别：{cat}\n")
            for fp_data in fps:
                body_lines.append(f"\n### {fp_data['id']}\n")
                body_lines.append(f"- **描述**：{fp_data['description']}\n")
                if fp_data.get("resolution"):
                    body_lines.append(f"- **解决**：{fp_data['resolution']}\n")
                if fp_data.get("rule_id"):
                    body_lines.append(f"- **关联规则**：`{fp_data['rule_id']}`\n")
                body_lines.append(f"- **时间**：{fp_data.get('timestamp', 'unknown')}\n")

        body_lines.append("\n---\n")
        body_lines.append("\n*本文件由 harness/self_report.py 自动维护。手动修改请在 frontmatter 后添加自定义章节。*\n")

        body = "".join(body_lines)

        # YAML frontmatter 序列化 — 保留完整信息，不截断
        fm_lines = ["---"]
        for k, v in fm.items():
            if k == "friction_points":
                fm_lines.append(f"{k}:")
                for fp_data in v:
                    fm_lines.append(f"  - id: \"{fp_data['id']}\"")
                    fm_lines.append(f"    category: \"{fp_data['category']}\"")
                    # 保留完整描述，不截断
                    desc = str(fp_data.get("description", "")).replace('"', '\\"')
                    fm_lines.append(f'    description: "{desc}"')
                    if fp_data.get("resolution"):
                        res = str(fp_data["resolution"]).replace('"', '\\"')
                        fm_lines.append(f'    resolution: "{res}"')
                    if fp_data.get("rule_id"):
                        fm_lines.append(f'    rule_id: "{fp_data["rule_id"]}"')
                    if fp_data.get("timestamp"):
                        fm_lines.append(f'    timestamp: "{fp_data["timestamp"]}"')
            elif isinstance(v, bool):
                fm_lines.append(f"{k}: {str(v).lower()}")
            elif isinstance(v, int):
                fm_lines.append(f"{k}: {v}")
            elif isinstance(v, str):
                fm_lines.append(f'{k}: "{v}"')
            else:
                fm_lines.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
        fm_lines.append("---")

        full_content = "\n".join(fm_lines) + "\n\n" + body

        self.lessons_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.lessons_path, "w", encoding="utf-8") as f:
            f.write(full_content)

    def generate_report(self) -> Dict:
        """生成自检报告"""
        self.report = {
            "timestamp": datetime.now().isoformat(),
            "system_state": self.system_state,
            "friction_summary": {
                "total": len(self.friction_points),
                "by_category": {},
                "auto_encoded": sum(1 for fp in self.friction_points if fp.auto_encode and fp.rule_id),
            },
            "evolution": {
                "rules_version": self.rules.get("version", "unknown"),
                "autopoiesis_enabled": self.rules.get("autopoiesis", {}).get("self_report_enabled", False),
                "new_rules_this_run": sum(1 for fp in self.friction_points if fp.auto_encode),
            },
            "recommendations": [],
        }

        for fp in self.friction_points:
            cat = fp.category
            self.report["friction_summary"]["by_category"][cat] = (
                self.report["friction_summary"]["by_category"].get(cat, 0) + 1
            )

        # 生成建议
        if not self.system_state.get("timeline_exists"):
            self.report["recommendations"].append("timeline.json 不存在，请先运行 pipeline")
        if self.system_state.get("has_effects") and not self.rules.get("l3_render_checks", {}).get("transition_validity"):
            self.report["recommendations"].append("检测到转场效果，建议启用 transition_validity 检查")

        return self.report

    def save_report(self) -> Path:
        """保存报告到 output/self_report.json"""
        report_path = self.output_dir / "self_report.json"
        self._save_json(report_path, self.report)
        return report_path

    def print_report(self):
        """打印 human-readable 报告"""
        print("=" * 60)
        print("md2video Self Report — Autopoiesis 自检报告")
        print("=" * 60)
        print(f"\n📊 系统状态：")
        for k, v in self.system_state.items():
            print(f"  {k}: {v}")

        print(f"\n🔥 摩擦点（{len(self.friction_points)} 个）：")
        for fp in self.friction_points:
            status = "✅ 已编码" if fp.rule_id else "⏳ 待编码"
            print(f"  [{status}] {fp.id}: {fp.category} — {fp.description[:60]}")

        print(f"\n📈 演化状态：")
        print(f"  规则版本: {self.report['evolution']['rules_version']}")
        print(f"  自创生启用: {self.report['evolution']['autopoiesis_enabled']}")
        print(f"  本次新增规则: {self.report['evolution']['new_rules_this_run']}")

        if self.report["recommendations"]:
            print(f"\n💡 建议：")
            for rec in self.report["recommendations"]:
                print(f"  • {rec}")

        print("\n" + "=" * 60)

    def run(self, no_write: bool = False, print_human: bool = True) -> Tuple[Optional[Path], Dict]:
        """
        完整自检流程：
        1. 加载系统状态
        2. 自动编码摩擦点
        3. 写入活记忆（no_write=False 时）
        4. 生成并保存报告（no_write=False 时）
        5. 打印报告（print_human=True 时）
        """
        self.load_system_state()
        self.auto_encode(write=not no_write)
        if not no_write:
            self.write_lessons()
        self.generate_report()
        report_path = None if no_write else self.save_report()
        if print_human:
            self.print_report()
        return report_path, self.report


# CLI 入口
def main():
    import argparse

    parser = argparse.ArgumentParser(description="md2video Self Report — Autopoiesis 自检")
    parser.add_argument("--project-dir", default=".", help="项目根目录")
    parser.add_argument("--capture", nargs=3, metavar=("CATEGORY", "DESC", "RESOLUTION"),
                        help="捕获一个摩擦点：--capture '素材遗漏' 's22缺失' '补充生成'")
    parser.add_argument("--no-write", action="store_true",
                        help="只生成内存报告，不写 LESSONS_LEARNED.md、video-rules.json 或 output/self_report.json")
    parser.add_argument("--json", action="store_true", help="输出 machine-readable JSON")
    args = parser.parse_args()

    report = SelfReport(project_dir=args.project_dir)

    if args.capture:
        report.capture_friction(args.capture[0], args.capture[1], args.capture[2])

    _, data = report.run(no_write=args.no_write, print_human=not args.json)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
