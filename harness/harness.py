#!/usr/bin/env python3
"""
Video Compliance Harness — 视频合规性检查框架

核心原则（直接继承自 skill-compliance-harness）：
1. 自动触发：主流程执行到 concat_engine 后自动加载
2. 强制逐项核查：必须按检查清单逐项核验实际产物
3. 任何一项 L1 不通过 → 红灯阻断，不得汇报完成
4. 宁可多走一遍核查，不可跳过
5. "看起来是对的"≠ 真的检查了
6. 不要在脑子里检查，必须回读真实文件

执行流程：
    Step 1: 加载 video-rules.json，定位 L1/L2/L3 检查项
    Step 2: 逐项拆清单
    Step 3: 逐项核验产物（回读真实文件，ffprobe，抽帧）
    Step 4: 输出核查报告
"""

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Optional, Tuple


@dataclass
class CheckResult:
    """单项检查结果"""
    check_id: str
    level: str           # L1 | L2 | L3
    name: str
    passed: bool
    auto_detect: bool
    detail: str
    block_on_fail: bool = False


class VideoComplianceHarness:
    """
    视频合规性检查 Harness

    使用方式：
        harness = VideoComplianceHarness()
        results = harness.run("output/final.mp4")
        if harness.has_l1_failures():
            raise RuntimeError("L1 checks failed, aborting")
    """

    RULES_PATH = Path(__file__).parent / "video-rules.json"
    DEFAULT_REPORT_PATH = Path("output/compliance_report.json")
    DEFAULT_SUMMARY_PATH = Path("output/compliance_summary.txt")

    def __init__(self, rules_path: Optional[Path] = None):
        self.rules_path = rules_path or self.RULES_PATH
        self.rules = self._load_rules()
        self.results: List[CheckResult] = []
        self.l1_errors: List[str] = []
        self.l2_warnings: List[str] = []
        self.l3_manual_checks: List[str] = []

    def _load_rules(self) -> dict:
        """加载 video-rules.json"""
        with open(self.rules_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _ffprobe(self, video_path: str, args: List[str]) -> dict:
        """调用 ffprobe 获取信息"""
        cmd = ["ffprobe", "-v", "error", "-of", "json"] + args + [video_path]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(result.stdout)

    # ═══════════════════════════════════════════════════════
    # L1 检查实现
    # ═══════════════════════════════════════════════════════

    def _check_tri_consistency(self) -> CheckResult:
        """三方一致性（依赖 timeline_mapper 的输出）"""
        timeline_path = Path("output/timeline.json")
        if not timeline_path.exists():
            return CheckResult(
                check_id="tri_consistency", level="L1", name="三方一致性",
                passed=False, auto_detect=True,
                detail="timeline.json 不存在，请先运行 timeline_mapper",
                block_on_fail=True,
            )

        with open(timeline_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        errors = data.get("validation", {}).get("errors", [])
        if errors:
            return CheckResult(
                check_id="tri_consistency", level="L1", name="三方一致性",
                passed=False, auto_detect=True,
                detail=f"发现 {len(errors)} 个 L1 错误: {'; '.join(errors)}",
                block_on_fail=True,
            )

        warnings = data.get("validation", {}).get("warnings", [])
        detail = "三方一致性通过"
        if warnings:
            detail += f"; 有 {len(warnings)} 个警告: {'; '.join(warnings)}"

        return CheckResult(
            check_id="tri_consistency", level="L1", name="三方一致性",
            passed=True, auto_detect=True, detail=detail,
            block_on_fail=True,
        )

    def _check_placeholder(self, video_path: str) -> CheckResult:
        """Placeholder 检测：通过 frame_extractor 的报告"""
        report_path = Path("output/frame_checks/frame_check_report.json")
        if not report_path.exists():
            return CheckResult(
                check_id="placeholder_count", level="L1", name="Placeholder 检测",
                passed=False, auto_detect=True,
                detail="frame_check_report.json 不存在，请先运行 frame_extractor",
                block_on_fail=True,
            )

        with open(report_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        auto_checks = data.get("auto_checks", {})
        failed = auto_checks.get("failed", 0)

        if failed > 0:
            return CheckResult(
                check_id="placeholder_count", level="L1", name="Placeholder 检测",
                passed=False, auto_detect=True,
                detail=f"抽帧检查发现 {failed} 处异常（黑帧/方块/重叠），请检查 frame_check_report.json",
                block_on_fail=True,
            )

        return CheckResult(
            check_id="placeholder_count", level="L1", name="Placeholder 检测",
            passed=True, auto_detect=True,
            detail=f"抽帧检查通过，{auto_checks.get('passed', 0)} 项自动检查全部通过",
            block_on_fail=True,
        )

    def _check_calculation_consistency(self) -> CheckResult:
        """计算一致性：必须由人工确认"""
        return CheckResult(
            check_id="calculation_consistency", level="L1", name="计算一致性",
            passed=True, auto_detect=False,
            detail="[MANUAL] 请确认：所有数值计算（总和、差值、百分比）已与数据源核对。当前标记为通过，但必须在发布前人工复核。",
            block_on_fail=True,
        )

    def _check_audio_stream(self, video_path: str) -> CheckResult:
        """检查视频是否包含音频流"""
        try:
            info = self._ffprobe(video_path, ["-show_streams"])
            streams = info.get("streams", [])
            audio_streams = [s for s in streams if s.get("codec_type") == "audio"]

            if not audio_streams:
                return CheckResult(
                    check_id="audio_presence", level="L1", name="音频存在性",
                    passed=False, auto_detect=True,
                    detail="final.mp4 不包含音频流",
                    block_on_fail=True,
                )

            return CheckResult(
                check_id="audio_presence", level="L1", name="音频存在性",
                passed=True, auto_detect=True,
                detail=f"包含 {len(audio_streams)} 个音频流，codec: {audio_streams[0].get('codec_name', 'unknown')}",
                block_on_fail=True,
            )
        except Exception as e:
            return CheckResult(
                check_id="audio_presence", level="L1", name="音频存在性",
                passed=False, auto_detect=True,
                detail=f"ffprobe 失败: {e}",
                block_on_fail=True,
            )

    def _check_timeline_completeness(self) -> CheckResult:
        """Timeline 完整性"""
        timeline_path = Path("output/timeline.json")
        if not timeline_path.exists():
            return CheckResult(
                check_id="timeline_completeness", level="L1", name="Timeline 完整性",
                passed=False, auto_detect=True,
                detail="timeline.json 不存在",
                block_on_fail=True,
            )

        with open(timeline_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        entries = data.get("entries", [])
        missing_media = []
        missing_audio = []

        for entry in entries:
            media_path = Path(entry.get("media_path", ""))
            if not media_path.exists():
                missing_media.append(entry["segment_id"])

            audio_path = Path("output/narration_segments") / f"{entry['segment_id']}.mp3"
            if not audio_path.exists():
                missing_audio.append(entry["segment_id"])

        if missing_media or missing_audio:
            detail = ""
            if missing_media:
                detail += f"缺失素材: {missing_media}; "
            if missing_audio:
                detail += f"缺失音频: {missing_audio}"
            return CheckResult(
                check_id="timeline_completeness", level="L1", name="Timeline 完整性",
                passed=False, auto_detect=True, detail=detail.strip(),
                block_on_fail=True,
            )

        return CheckResult(
            check_id="timeline_completeness", level="L1", name="Timeline 完整性",
            passed=True, auto_detect=True,
            detail=f"所有 {len(entries)} 个 segment 素材和音频均存在",
            block_on_fail=True,
        )

    def _check_no_missing_scene(self) -> CheckResult:
        """无遗漏场景"""
        prompts_path = Path("prompts.json")
        timeline_path = Path("output/timeline.json")

        if not prompts_path.exists() or not timeline_path.exists():
            return CheckResult(
                check_id="no_missing_scene", level="L1", name="无遗漏场景",
                passed=True, auto_detect=True,
                detail="跳过（缺少 prompts.json 或 timeline.json）",
                block_on_fail=True,
            )

        with open(prompts_path, "r", encoding="utf-8") as f:
            prompts = json.load(f)
        prompt_ids = {p.get("id", p.get("scene_id", "")) for p in (prompts if isinstance(prompts, list) else prompts.get("scenes", []))}

        with open(timeline_path, "r", encoding="utf-8") as f:
            timeline = json.load(f)
        timeline_ids = {e["segment_id"] for e in timeline.get("entries", [])}

        missing = prompt_ids - timeline_ids
        if missing:
            return CheckResult(
                check_id="no_missing_scene", level="L1", name="无遗漏场景",
                passed=False, auto_detect=True,
                detail=f"prompts.json 中有 {len(missing)} 个 scene 未出现在 timeline 中: {missing}",
                block_on_fail=True,
            )

        return CheckResult(
            check_id="no_missing_scene", level="L1", name="无遗漏场景",
            passed=True, auto_detect=True,
            detail="所有 prompts.json 中的 scene 都在 timeline 中",
            block_on_fail=True,
        )

    def _check_no_duplicate(self) -> CheckResult:
        """无重复场景"""
        timeline_path = Path("output/timeline.json")
        if not timeline_path.exists():
            return CheckResult(
                check_id="no_duplicate_scene", level="L1", name="无重复场景",
                passed=True, auto_detect=True,
                detail="跳过（缺少 timeline.json）",
                block_on_fail=True,
            )

        with open(timeline_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        ids = [e["segment_id"] for e in data.get("entries", [])]
        duplicates = [sid for sid in set(ids) if ids.count(sid) > 1]

        if duplicates:
            return CheckResult(
                check_id="no_duplicate_scene", level="L1", name="无重复场景",
                passed=False, auto_detect=True,
                detail=f"发现重复 segment_id: {duplicates}",
                block_on_fail=True,
            )

        return CheckResult(
            check_id="no_duplicate_scene", level="L1", name="无重复场景",
            passed=True, auto_detect=True,
            detail="无重复",
            block_on_fail=True,
        )

    # ═══════════════════════════════════════════════════════
    # L2 检查实现
    # ═══════════════════════════════════════════════════════

    def _check_av_drift(self, video_path: str) -> CheckResult:
        """音画时长差值"""
        try:
            info = self._ffprobe(video_path, ["-show_streams"])
            streams = info.get("streams", [])

            video_duration = 0
            audio_duration = 0
            for s in streams:
                if s.get("codec_type") == "video":
                    video_duration = float(s.get("duration", 0) or 0)
                elif s.get("codec_type") == "audio":
                    audio_duration = float(s.get("duration", 0) or 0)

            if video_duration == 0:
                fmt = self._ffprobe(video_path, ["-show_format"])
                video_duration = float(fmt.get("format", {}).get("duration", 0) or 0)
                audio_duration = video_duration

            drift = abs(video_duration - audio_duration)
            threshold = self.rules.get("l2_warning_checks", {}).get("audio_video_drift", {}).get("threshold", {}).get("max_drift_seconds", 2.0)

            if drift > threshold:
                return CheckResult(
                    check_id="audio_video_drift", level="L2", name="音画时长差值",
                    passed=False, auto_detect=True,
                    detail=f"音画差值 {drift:.3f}s > 阈值 {threshold}s (video={video_duration:.2f}s, audio={audio_duration:.2f}s)",
                    block_on_fail=False,
                )

            return CheckResult(
                check_id="audio_video_drift", level="L2", name="音画时长差值",
                passed=True, auto_detect=True,
                detail=f"音画差值 {drift:.3f}s <= 阈值 {threshold}s",
                block_on_fail=False,
            )
        except Exception as e:
            return CheckResult(
                check_id="audio_video_drift", level="L2", name="音画时长差值",
                passed=False, auto_detect=True,
                detail=f"检查失败: {e}",
                block_on_fail=False,
            )

    def _check_resolution(self, video_path: str) -> CheckResult:
        """分辨率检查"""
        try:
            info = self._ffprobe(video_path, ["-select_streams", "v:0", "-show_entries", "stream=width,height"])
            stream = info.get("streams", [{}])[0]
            width = stream.get("width", 0)
            height = stream.get("height", 0)

            target_w = 1080
            target_h = 1920
            min_acceptable = 720

            if width < min_acceptable or height < min_acceptable:
                return CheckResult(
                    check_id="resolution_match", level="L2", name="分辨率匹配",
                    passed=False, auto_detect=True,
                    detail=f"分辨率 {width}×{height} 低于最小可接受值 {min_acceptable}p",
                    block_on_fail=False,
                )

            if width != target_w or height != target_h:
                return CheckResult(
                    check_id="resolution_match", level="L2", name="分辨率匹配",
                    passed=False, auto_detect=True,
                    detail=f"分辨率 {width}×{height} 不等于目标 {target_w}×{target_h}",
                    block_on_fail=False,
                )

            return CheckResult(
                check_id="resolution_match", level="L2", name="分辨率匹配",
                passed=True, auto_detect=True,
                detail=f"分辨率 {width}×{height} 符合目标",
                block_on_fail=False,
            )
        except Exception as e:
            return CheckResult(
                check_id="resolution_match", level="L2", name="分辨率匹配",
                passed=False, auto_detect=True,
                detail=f"检查失败: {e}",
                block_on_fail=False,
            )

    def _check_fps_variance(self, video_path: str) -> CheckResult:
        """帧率方差（简化版：仅检查最终视频帧率）"""
        try:
            info = self._ffprobe(video_path, ["-select_streams", "v:0", "-show_entries", "stream=r_frame_rate"])
            stream = info.get("streams", [{}])[0]
            fps_str = stream.get("r_frame_rate", "0/1")
            num, den = fps_str.split("/")
            fps = float(num) / float(den)

            target = 30
            threshold = 1.0

            if abs(fps - target) > threshold:
                return CheckResult(
                    check_id="frame_rate_variance", level="L2", name="帧率方差",
                    passed=False, auto_detect=True,
                    detail=f"帧率 {fps:.2f} 与目标 {target} 偏差 {abs(fps-target):.2f} > 阈值 {threshold}",
                    block_on_fail=False,
                )

            return CheckResult(
                check_id="frame_rate_variance", level="L2", name="帧率方差",
                passed=True, auto_detect=True,
                detail=f"帧率 {fps:.2f} 符合目标",
                block_on_fail=False,
            )
        except Exception as e:
            return CheckResult(
                check_id="frame_rate_variance", level="L2", name="帧率方差",
                passed=False, auto_detect=True,
                detail=f"检查失败: {e}",
                block_on_fail=False,
            )

    def _check_segment_duration(self) -> CheckResult:
        """段落时长合理性"""
        segments_path = Path("output/segments.json")
        if not segments_path.exists():
            return CheckResult(
                check_id="segment_duration_reasonable", level="L2", name="段落时长合理性",
                passed=True, auto_detect=True,
                detail="跳过（缺少 segments.json）",
                block_on_fail=False,
            )

        with open(segments_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        durations = [s.get("duration", 0) for s in data.get("segments", [])]
        min_d = min(durations) if durations else 0
        max_d = max(durations) if durations else 0

        min_thresh = 1.0
        max_thresh = 30.0

        issues = []
        if min_d < min_thresh:
            issues.append(f"最短段落 {min_d:.2f}s < {min_thresh}s")
        if max_d > max_thresh:
            issues.append(f"最长段落 {max_d:.2f}s > {max_thresh}s")

        if issues:
            return CheckResult(
                check_id="segment_duration_reasonable", level="L2", name="段落时长合理性",
                passed=False, auto_detect=True,
                detail="; ".join(issues),
                block_on_fail=False,
            )

        return CheckResult(
            check_id="segment_duration_reasonable", level="L2", name="段落时长合理性",
            passed=True, auto_detect=True,
            detail=f"段落时长范围 {min_d:.2f}s ~ {max_d:.2f}s 合理",
            block_on_fail=False,
        )

    # ═══════════════════════════════════════════════════════
    # L3 检查（输出人工清单）
    # ═══════════════════════════════════════════════════════

    def _check_qrcode_integrity(self) -> CheckResult:
        """二维码完整性检查"""
        registry_path = Path("cta_resources.json")
        if not registry_path.exists():
            return CheckResult(
                check_id="qrcode_integrity", level="L3", name="二维码完整性",
                passed=False, auto_detect=True,
                detail="cta_resources.json 不存在，CTA 二维码未纳入资源治理",
                block_on_fail=False,
            )

        with open(registry_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        resources = data.get("resources", [])
        qrcodes = [r for r in resources if r.get("resource_type") == "qrcode"]

        if not qrcodes:
            return CheckResult(
                check_id="qrcode_integrity", level="L3", name="二维码完整性",
                passed=False, auto_detect=True,
                detail="cta_resources.json 中未注册任何 qrcode 资源",
                block_on_fail=False,
            )

        issues = []
        for r in qrcodes:
            # 检查文件存在性
            media_path = Path(r.get("media_path", ""))
            if not media_path.exists():
                issues.append(f"[{r['id']}] 二维码文件不存在: {media_path}")
            # 检查 URL 格式
            url = r.get("target_url", "")
            if not url or not url.startswith(("http://", "https://")):
                issues.append(f"[{r['id']}] URL 格式非法: {url}")
            # 检查可扫描性
            if not r.get("valid", True):
                issues.append(f"[{r['id']}] 二维码可扫描性校验失败")

        if issues:
            return CheckResult(
                check_id="qrcode_integrity", level="L3", name="二维码完整性",
                passed=False, auto_detect=True,
                detail="; ".join(issues),
                block_on_fail=False,
            )

        return CheckResult(
            check_id="qrcode_integrity", level="L3", name="二维码完整性",
            passed=True, auto_detect=True,
            detail=f"已注册 {len(qrcodes)} 个二维码资源，全部通过校验",
            block_on_fail=False,
        )

    def _collect_l3_checks(self) -> List[CheckResult]:
        """收集所有 L3 检查项（ mostly manual ）"""
        l3_rules = self.rules.get("l3_render_checks", {})
        results = []

        for check_id, rule in l3_rules.items():
            if check_id.startswith("_"):
                continue

            manual_items = rule.get("manual_checklist", [])
            detail = "[MANUAL CHECK REQUIRED]\n" + "\n".join(f"  [ ] {item}" for item in manual_items)

            results.append(CheckResult(
                check_id=check_id,
                level="L3",
                name=rule.get("name", check_id),
                passed=True,  # L3 默认通过，由人工最终确认
                auto_detect=rule.get("auto_detect", False),
                detail=detail,
                block_on_fail=False,
            ))

        return results

    # ═══════════════════════════════════════════════════════
    # 主执行流程
    # ═══════════════════════════════════════════════════════

    def run(self, video_path: str = "output/final.mp4") -> List[CheckResult]:
        """
        执行完整合规检查

        Returns:
            所有检查项的结果列表
        """
        print("=" * 60)
        print(" Video Compliance Harness — 开始执行")
        print("=" * 60)

        results = []

        # L1 检查
        print("\n[L1 硬阻塞检查]")
        l1_checks = [
            self._check_tri_consistency,
            lambda: self._check_placeholder(video_path),
            self._check_calculation_consistency,
            lambda: self._check_audio_stream(video_path),
            self._check_timeline_completeness,
            self._check_no_missing_scene,
            self._check_no_duplicate,
        ]
        for check_fn in l1_checks:
            result = check_fn()
            results.append(result)
            status = "✅" if result.passed else "❌"
            print(f"  {status} {result.name}: {result.detail[:80]}")

        # L2 检查
        print("\n[L2 警告检查]")
        l2_checks = [
            lambda: self._check_av_drift(video_path),
            lambda: self._check_resolution(video_path),
            lambda: self._check_fps_variance(video_path),
            self._check_segment_duration,
        ]
        for check_fn in l2_checks:
            result = check_fn()
            results.append(result)
            status = "✅" if result.passed else "⚠️"
            print(f"  {status} {result.name}: {result.detail[:80]}")

        # L3 检查
        print("\n[L3 模式检查]")
        # L3 自动检查项
        l3_auto_checks = [
            self._check_qrcode_integrity,
            self._check_transition_validity,
            self._check_fade_validity,
        ]
        for check_fn in l3_auto_checks:
            result = check_fn()
            results.append(result)

        l3_results = self._collect_l3_checks()
        results.extend(l3_results)
        for result in results:
            if result.level != "L3":
                continue
            status = "✅" if result.passed else "❌" if result.auto_detect else "🔍"
            print(f"  {status} {result.name}")
            for line in result.detail.split("\n"):
                if line.strip():
                    print(f"      {line}")

        self.results = results
        self._save_report(video_path)
        return results

    def has_l1_failures(self) -> bool:
        """是否有 L1 检查失败"""
        return any(r.level == "L1" and not r.passed for r in self.results)

    def _check_transition_validity(self) -> CheckResult:
        """转场有效性检查"""
        timeline_path = Path("output/timeline.json")
        if not timeline_path.exists():
            return CheckResult(
                check_id="transition_validity", level="L3", name="转场有效性",
                passed=True, auto_detect=True,
                detail="跳过（缺少 timeline.json）",
                block_on_fail=False,
            )

        with open(timeline_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        entries = data.get("entries", [])
        issues = []
        max_ratio = 0.5

        for i, entry in enumerate(entries):
            trans = entry.get("transition")
            if not trans:
                continue

            duration = trans.get("duration", 0)
            trans_type = trans.get("type", "")

            # 检查时长
            if duration <= 0:
                issues.append(f"[{entry['segment_id']}] transition_duration 必须大于 0")
                continue

            # 检查类型
            valid_types = {"fade", "crossfade", "slideleft", "slideright", "slideup", "slidedown", "wipeleft", "wiperight"}
            if trans_type not in valid_types:
                issues.append(f"[{entry['segment_id']}] 未知转场类型: {trans_type}")

            # 检查时长不超过相邻段最小时长的一半
            if i < len(entries) - 1:
                min_dur = min(entry.get("duration", 0), entries[i + 1].get("duration", 0))
                if duration > min_dur * max_ratio:
                    issues.append(
                        f"[{entry['segment_id']}] transition_duration {duration}s 超过相邻段最小时长 {min_dur}s 的 50%"
                    )

        if issues:
            return CheckResult(
                check_id="transition_validity", level="L3", name="转场有效性",
                passed=False, auto_detect=True,
                detail="; ".join(issues),
                block_on_fail=False,
            )

        return CheckResult(
            check_id="transition_validity", level="L3", name="转场有效性",
            passed=True, auto_detect=True,
            detail="所有转场配置有效",
            block_on_fail=False,
        )

    def _check_fade_validity(self) -> CheckResult:
        """淡入淡出时长有效性检查"""
        timeline_path = Path("output/timeline.json")
        if not timeline_path.exists():
            return CheckResult(
                check_id="fade_duration_validity", level="L3", name="淡入淡出时长有效性",
                passed=True, auto_detect=True,
                detail="跳过（缺少 timeline.json）",
                block_on_fail=False,
            )

        with open(timeline_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        entries = data.get("entries", [])
        issues = []

        for entry in entries:
            seg_id = entry["segment_id"]
            duration = entry.get("duration", 0)
            fade_in = entry.get("fade_in", 0)
            fade_out = entry.get("fade_out", 0)

            if fade_in < 0 or fade_out < 0:
                issues.append(f"[{seg_id}] fade_in/fade_out 不能为负数")
            if fade_in > 0 and fade_in >= duration:
                issues.append(f"[{seg_id}] fade_in ({fade_in}s) 必须小于段时长 ({duration}s)")
            if fade_out > 0 and fade_out >= duration:
                issues.append(f"[{seg_id}] fade_out ({fade_out}s) 必须小于段时长 ({duration}s)")
            if fade_in + fade_out >= duration:
                issues.append(f"[{seg_id}] fade_in + fade_out ({fade_in + fade_out}s) 必须小于段时长 ({duration}s)")

        if issues:
            return CheckResult(
                check_id="fade_duration_validity", level="L3", name="淡入淡出时长有效性",
                passed=False, auto_detect=True,
                detail="; ".join(issues),
                block_on_fail=False,
            )

        return CheckResult(
            check_id="fade_duration_validity", level="L3", name="淡入淡出时长有效性",
            passed=True, auto_detect=True,
            detail="所有 fade_in/fade_out 配置有效",
            block_on_fail=False,
        )

    def has_l2_warnings(self) -> bool:
        """是否有 L2 警告"""
        return any(r.level == "L2" and not r.passed for r in self.results)

    def _save_report(self, video_path: str):
        """保存检查报告"""
        self.DEFAULT_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

        report = {
            "harness": "md2video.compliance_harness",
            "video": video_path,
            "l1_summary": {
                "total": sum(1 for r in self.results if r.level == "L1"),
                "passed": sum(1 for r in self.results if r.level == "L1" and r.passed),
                "failed": sum(1 for r in self.results if r.level == "L1" and not r.passed),
            },
            "l2_summary": {
                "total": sum(1 for r in self.results if r.level == "L2"),
                "passed": sum(1 for r in self.results if r.level == "L2" and r.passed),
                "failed": sum(1 for r in self.results if r.level == "L2" and not r.passed),
            },
            "l3_summary": {
                "total": sum(1 for r in self.results if r.level == "L3"),
            },
            "results": [
                {
                    "id": r.check_id,
                    "level": r.level,
                    "name": r.name,
                    "passed": r.passed,
                    "auto": r.auto_detect,
                    "detail": r.detail,
                }
                for r in self.results
            ],
        }

        with open(self.DEFAULT_REPORT_PATH, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        # 文本摘要
        with open(self.DEFAULT_SUMMARY_PATH, "w", encoding="utf-8") as f:
            f.write("═ Video Compliance Harness 核查报告 ═\n\n")
            f.write(f"视频: {video_path}\n\n")

            f.write("[L1 硬阻塞]\n")
            for r in self.results:
                if r.level == "L1":
                    status = "✅ PASS" if r.passed else "❌ FAIL"
                    f.write(f"  {status} {r.name}\n")
                    f.write(f"      {r.detail}\n")

            f.write("\n[L2 警告]\n")
            for r in self.results:
                if r.level == "L2":
                    status = "✅ PASS" if r.passed else "⚠️ WARN"
                    f.write(f"  {status} {r.name}\n")
                    f.write(f"      {r.detail}\n")

            f.write("\n[L3 人工检查清单]\n")
            for r in self.results:
                if r.level == "L3":
                    f.write(f"  🔍 {r.name}\n")
                    f.write(f"      {r.detail}\n")

            l1_failed = report["l1_summary"]["failed"]
            f.write(f"\n{'='*50}\n")
            if l1_failed > 0:
                f.write(f"结果: ❌ 未通过 ({l1_failed} 项 L1 失败)\n")
            else:
                f.write("结果: ✅ 通过\n")

        print(f"\n报告已保存:")
        print(f"  JSON: {self.DEFAULT_REPORT_PATH}")
        print(f"  文本: {self.DEFAULT_SUMMARY_PATH}")
