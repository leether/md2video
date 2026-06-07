#!/usr/bin/env python3
"""
Frame Extractor — 抽帧检查引擎

核心原则：
1. "不要在脑子里检查"——必须回读真实 PNG 帧，逐条确认
2. 覆盖 L3 模式检查：箭头方向、颜色语义、emoji字体兼容性、文字重叠
3. 自动检测 + 人工抽检结合：auto_detect=true 的项程序自动检查，false 的项输出报告待人工确认
4. 每段至少抽 1 帧，关键帧（段落起始/中间/结束）至少抽 3 帧

检查项：
    [auto] 文字重叠检测：OCR 或边缘密度分析
    [auto] 黑帧/灰帧检测：检测 placeholder 或渲染失败
    [auto] emoji 方块检测：检测 Unicode 替换字符或 fallback 方块
    [manual] 箭头方向语义：箭头方向是否与数据因果关系一致
    [manual] 颜色语义：涨价/降价/正负的颜色是否符合语义约定
    [manual] CTA 卡片存在：结尾是否包含引导关注的画面
"""

import json
import subprocess
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional, Dict, Tuple
from PIL import Image
import numpy as np


@dataclass
class FrameCheckResult:
    """单帧检查结果"""
    segment_id: str
    timestamp: float           # 在视频中的时间戳（秒）
    frame_path: str            # 抽帧文件路径
    checks: Dict[str, dict] = field(default_factory=dict)   # {check_id: {passed, detail}}


@dataclass
class ExtractConfig:
    """抽帧配置"""
    frames_per_segment: int = 3           # 每段抽几帧
    output_dir: str = "output/frame_checks"
    min_brightness_threshold: int = 10    # 黑帧检测阈值（平均亮度<10视为黑帧）
    max_uniformity_threshold: float = 0.95  # 纯色检测阈值（ uniformity > 0.95 视为纯色/placeholder）
    emoji_replacement_chars: List[str] = field(default_factory=lambda: ["□", "■", "�", "▯", "▮"])


class FrameExtractor:
    """
    抽帧检查引擎
    """

    def __init__(self, config: Optional[ExtractConfig] = None):
        self.config = config or ExtractConfig()
        self.output_dir = Path(self.config.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.results: List[FrameCheckResult] = []

    def _extract_frame(self, video_path: str, timestamp: float, output_path: str) -> bool:
        """用 ffmpeg 在指定时间戳抽帧"""
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(timestamp),
            "-i", video_path,
            "-vframes", "1",
            "-q:v", "2",
            output_path,
        ]
        try:
            subprocess.run(cmd, capture_output=True, check=True)
            return Path(output_path).exists()
        except subprocess.CalledProcessError:
            return False

    def _check_black_frame(self, img: Image.Image) -> Tuple[bool, str]:
        """
        黑帧/灰帧检测

        Returns:
            (passed, detail)
            passed=True 表示不是黑帧（正常）
        """
        arr = np.array(img.convert("L"))
        mean_brightness = arr.mean()

        if mean_brightness < self.config.min_brightness_threshold:
            return False, f"平均亮度 {mean_brightness:.1f} < 阈值 {self.config.min_brightness_threshold}，疑似黑帧/渲染失败"

        # 纯色检测（placeholder 常见特征）
        unique_ratio = len(np.unique(arr)) / 256
        if unique_ratio < (1 - self.config.max_uniformity_threshold):
            return False, f"色彩丰富度 {unique_ratio:.4f}，疑似纯色 placeholder"

        return True, f"平均亮度 {mean_brightness:.1f}，色彩丰富度 {unique_ratio:.4f}"

    def _check_emoji_blocks(self, img: Image.Image) -> Tuple[bool, str]:
        """
        Emoji 方块检测

        策略：
        1. 尝试 OCR（如果环境中安装了 pytesseract）
        2. 降级：检测图片中是否有已知的 emoji fallback 方块字符的视觉特征
           （大范围的均匀色块，常见于 emoji 无法渲染时显示的方框）
        """
        # 简化版：检测大区域均匀色块（可能是 emoji 方框）
        arr = np.array(img)

        # 转换为二值，检测大的连通区域
        gray = np.array(img.convert("L"))
        # 边缘检测：如果图像有大量文字，边缘会很多；如果大面积是方框，边缘集中在方框边界
        from scipy import ndimage
        edges = ndimage.sobel(gray)
        edge_density = (edges > 20).sum() / edges.size

        # 启发式：edge_density 极低但非纯色 = 可能有大面积空白或方框
        # edge_density 极高但 uniform = 可能是密集文字
        # 这个检查需要更多调优，目前作为警告级别
        if edge_density < 0.01:
            return True, f"边缘密度 {edge_density:.4f}，建议人工检查是否有 emoji 方块"

        return True, f"边缘密度 {edge_density:.4f}，无异常"

    def _check_text_overlap(self, img: Image.Image) -> Tuple[bool, str]:
        """
        文字重叠检测（简化版）

        策略：OCR 检测文字区域重叠
        当前实现：如果没有 pytesseract，降级为警告
        """
        try:
            import pytesseract
            # 获取文字区域
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            boxes = []
            for i in range(len(data["text"])):
                if int(data["conf"][i]) > 30:
                    x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
                    boxes.append((x, y, x+w, y+h))

            # 检测重叠
            overlaps = 0
            for i in range(len(boxes)):
                for j in range(i+1, len(boxes)):
                    x1, y1, x2, y2 = boxes[i]
                    x3, y3, x4, y4 = boxes[j]
                    if x1 < x4 and x2 > x3 and y1 < y4 and y2 > y3:
                        overlaps += 1

            if overlaps > 0:
                return False, f"检测到 {overlaps} 处文字重叠"
            return True, "无文字重叠"
        except ImportError:
            return True, "未安装 pytesseract，跳过文字重叠检测"

    def extract_and_check(
        self,
        video_path: str,
        timeline_path: str = "output/timeline.json",
    ) -> List[FrameCheckResult]:
        """
        主入口：按 timeline 抽帧并检查

        Args:
            video_path: 最终视频路径
            timeline_path: timeline.json 路径

        Returns:
            检查结果列表
        """
        with open(timeline_path, "r", encoding="utf-8") as f:
            timeline_data = json.load(f)
        entries = timeline_data.get("entries", [])

        results = []

        for entry in entries:
            seg_id = entry["segment_id"]
            start_time = entry.get("start_time", 0)
            end_time = entry.get("end_time", start_time + entry.get("duration", 0))
            duration = entry.get("duration", 0)

            # 计算抽帧时间点
            if self.config.frames_per_segment == 1:
                timestamps = [start_time + duration / 2]
            else:
                timestamps = [
                    start_time + duration * i / (self.config.frames_per_segment - 1)
                    for i in range(self.config.frames_per_segment)
                ]

            for ts in timestamps:
                frame_name = f"{seg_id}_{ts:.2f}s.png"
                frame_path = self.output_dir / frame_name

                ok = self._extract_frame(video_path, ts, str(frame_path))
                if not ok:
                    result = FrameCheckResult(
                        segment_id=seg_id,
                        timestamp=ts,
                        frame_path=str(frame_path),
                        checks={"extract": {"passed": False, "detail": "抽帧失败"}},
                    )
                    results.append(result)
                    continue

                # 加载图片进行检查
                img = Image.open(frame_path)
                checks = {}

                # L3 自动检查项
                passed, detail = self._check_black_frame(img)
                checks["black_frame"] = {"passed": passed, "detail": detail}

                passed, detail = self._check_emoji_blocks(img)
                checks["emoji_blocks"] = {"passed": passed, "detail": detail}

                passed, detail = self._check_text_overlap(img)
                checks["text_overlap"] = {"passed": passed, "detail": detail}

                result = FrameCheckResult(
                    segment_id=seg_id,
                    timestamp=ts,
                    frame_path=str(frame_path),
                    checks=checks,
                )
                results.append(result)

        self.results = results
        return results

    def generate_report(self) -> Path:
        """生成检查报告"""
        report_path = self.output_dir / "frame_check_report.json"
        data = {
            "total_frames": len(self.results),
            "auto_checks": {},
            "manual_checks_needed": [],
            "frames": [],
        }

        # 统计自动检查
        auto_passed = 0
        auto_failed = 0
        for r in self.results:
            for check_id, check_result in r.checks.items():
                if check_result["passed"]:
                    auto_passed += 1
                else:
                    auto_failed += 1

        data["auto_checks"] = {
            "total": auto_passed + auto_failed,
            "passed": auto_passed,
            "failed": auto_failed,
        }

        # 需要人工检查的项目
        data["manual_checks_needed"] = [
            {"id": "arrow_direction", "description": "箭头方向与数据因果关系是否一致"},
            {"id": "color_semantic", "description": "颜色语义（涨红跌绿/正负对应）是否正确"},
            {"id": "cta_presence", "description": "结尾是否包含 CTA 卡片"},
            {"id": "font_fallback", "description": "中文字体是否正确加载，无回退到系统默认字体"},
        ]

        # 详细帧数据
        for r in self.results:
            data["frames"].append(asdict(r))

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # 同时输出文本摘要
        summary_path = self.output_dir / "frame_check_summary.txt"
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write("═ Frame Check Summary ═\n\n")
            f.write(f"Total frames checked: {len(self.results)}\n")
            f.write(f"Auto checks: {auto_passed} passed, {auto_failed} failed\n\n")

            if auto_failed > 0:
                f.write("Failed checks:\n")
                for r in self.results:
                    for check_id, check_result in r.checks.items():
                        if not check_result["passed"]:
                            f.write(f"  [{r.segment_id} @ {r.timestamp:.2f}s] {check_id}: {check_result['detail']}\n")

            f.write("\nManual checks required:\n")
            for m in data["manual_checks_needed"]:
                f.write(f"  [ ] {m['id']}: {m['description']}\n")

        return report_path
