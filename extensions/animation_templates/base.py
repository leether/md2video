#!/usr/bin/env python3
"""
Animation Templates — Python 动画模板库

核心原则：
1. 每个模板是一个独立的 Python 函数，输出 mp4 文件
2. 模板参数通过 dataclass 定义，确保类型安全
3. 所有模板统一输出 1080×1920，30fps
4. 字体必须使用指定中文字体，无 fallback 风险
5. 禁止直接使用 emoji，使用 ASCII 替代或 Pillow 绘制的矢量图形

模板类型：
    - 数据对比：价格对比、前后对比
    - 时间线：日历、日期标注、倒计时
    - 列表/表格：多行数据、明细表
    - 引导过渡： quotes、CTA、章节标题
"""

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple, Optional

from PIL import Image, ImageDraw, ImageFont
import numpy as np


# 中文字体配置 —— 必须存在，否则报错
DEFAULT_FONT_PATH = "/System/Library/Fonts/Hiragino Sans GB.ttc"

def get_font(size: int) -> ImageFont.FreeTypeFont:
    """加载中文字体，失败则报错"""
    if not os.path.exists(DEFAULT_FONT_PATH):
        raise RuntimeError(
            f"中文字体不存在: {DEFAULT_FONT_PATH}\n"
            "请安装 Hiragino Sans GB 或修改 DEFAULT_FONT_PATH"
        )
    return ImageFont.truetype(DEFAULT_FONT_PATH, size)


@dataclass
class AnimationConfig:
    """动画全局配置"""
    width: int = 1080
    height: int = 1920
    fps: int = 30
    duration: float = 5.0
    bg_color: Tuple[int, int, int] = (18, 18, 18)
    text_color: Tuple[int, int, int] = (255, 255, 255)
    accent_color: Tuple[int, int, int] = (76, 175, 80)      # 绿色（默认正数/涨价）
    negative_color: Tuple[int, int, int] = (244, 67, 54)    # 红色（默认负数/降价）
    warning_color: Tuple[int, int, int] = (255, 193, 7)      # 黄色（警告/过期）
    font_path: str = DEFAULT_FONT_PATH


class AnimationTemplate(ABC):
    """动画模板基类"""

    def __init__(self, config: Optional[AnimationConfig] = None):
        self.config = config or AnimationConfig()
        self.frames: List[np.ndarray] = []

    @abstractmethod
    def render(self) -> List[np.ndarray]:
        """渲染所有帧，返回 RGB 数组列表"""
        pass

    def save(self, output_path: str):
        """使用 imageio + ffmpeg 保存为 mp4"""
        import imageio
        writer = imageio.get_writer(
            output_path,
            fps=self.config.fps,
            codec="libx264",
            pixelformat="yuv420p",
            quality=8,
        )
        frames = self.render()
        for frame in frames:
            writer.append_data(frame)
        writer.close()
        print(f"[AnimationTemplate] 已保存: {output_path} ({len(frames)} frames)")

    def _create_frame(self, draw_fn=None) -> Image.Image:
        """创建空白画布"""
        img = Image.new("RGB", (self.config.width, self.config.height), self.config.bg_color)
        if draw_fn:
            draw = ImageDraw.Draw(img)
            draw_fn(draw, img)
        return img

    def _text_to_array(self, img: Image.Image) -> np.ndarray:
        """PIL Image → numpy RGB array"""
        return np.array(img)


# ═══════════════════════════════════════════════════════
# 内置模板示例
# ═══════════════════════════════════════════════════════

@dataclass
class PriceContrastParams:
    """价格对比模板参数"""
    old_label: str = "老用户"
    old_price: str = "¥3.59"
    new_label: str = "新用户"
    new_price: str = "¥10.00+"
    subtitle: str = "价格翻了近3倍"
    duration: float = 5.0


class PriceContrastAnimation(AnimationTemplate):
    """
    价格对比动画
    左：老用户低价（绿色） 右：新用户高价（红色）
    中间箭头：从低到高
    """

    def __init__(self, params: PriceContrastParams, config: Optional[AnimationConfig] = None):
        super().__init__(config)
        self.params = params
        self.config.duration = params.duration

    def render(self) -> List[np.ndarray]:
        total_frames = int(self.config.duration * self.config.fps)
        frames = []

        font_large = get_font(120)
        font_medium = get_font(60)
        font_small = get_font(40)

        for frame_idx in range(total_frames):
            progress = frame_idx / total_frames if total_frames > 1 else 1.0

            img = self._create_frame()
            draw = ImageDraw.Draw(img)
            W, H = self.config.width, self.config.height

            # 标题
            title = "价格对比"
            bbox = draw.textbbox((0, 0), title, font=font_medium)
            tw = bbox[2] - bbox[0]
            draw.text(((W - tw) // 2, 200), title, fill=self.config.text_color, font=font_medium)

            # 老用户价格（左，绿色 = 正面/低价优惠）
            # 注意：这里颜色语义需根据实际场景调整
            old_x = W // 4
            old_y = H // 2 - 50
            bbox = draw.textbbox((0, 0), self.params.old_label, font=font_small)
            lw = bbox[2] - bbox[0]
            draw.text((old_x - lw // 2, old_y - 100), self.params.old_label, fill=(150, 150, 150), font=font_small)
            bbox = draw.textbbox((0, 0), self.params.old_price, font=font_large)
            pw = bbox[2] - bbox[0]
            draw.text((old_x - pw // 2, old_y), self.params.old_price, fill=self.config.accent_color, font=font_large)

            # 箭头（中间）
            arrow_x = W // 2
            arrow_y = H // 2
            # 绘制简单箭头
            arrow_len = int(100 * progress)
            draw.line([(arrow_x - arrow_len, arrow_y), (arrow_x + arrow_len, arrow_y)], fill=self.config.text_color, width=8)
            # 箭头头部
            draw.polygon([(arrow_x + arrow_len + 20, arrow_y), (arrow_x + arrow_len, arrow_y - 15), (arrow_x + arrow_len, arrow_y + 15)], fill=self.config.text_color)

            # 新用户价格（右，红色 = 负面/涨价）
            new_x = W * 3 // 4
            bbox = draw.textbbox((0, 0), self.params.new_label, font=font_small)
            nw = bbox[2] - bbox[0]
            draw.text((new_x - nw // 2, old_y - 100), self.params.new_label, fill=(150, 150, 150), font=font_small)
            bbox = draw.textbbox((0, 0), self.params.new_price, font=font_large)
            pw = bbox[2] - bbox[0]
            draw.text((new_x - pw // 2, old_y), self.params.new_price, fill=self.config.negative_color, font=font_large)

            # 副标题
            bbox = draw.textbbox((0, 0), self.params.subtitle, font=font_small)
            sw = bbox[2] - bbox[0]
            draw.text(((W - sw) // 2, H - 300), self.params.subtitle, fill=self.config.warning_color, font=font_small)

            frames.append(self._text_to_array(img))

        return frames


@dataclass
class TableParams:
    """表格动画模板参数"""
    title: str = "积分明细"
    headers: List[str] = field(default_factory=lambda: ["来源", "积分"])
    rows: List[List[str]] = field(default_factory=lambda: [["签到", "+18"], ["任务", "+88"]])
    total_label: str = "合计"
    total_value: str = "249"
    duration: float = 5.0


class TableAnimation(AnimationTemplate):
    """
    表格数据展示动画
    逐行淡入，最后显示总计
    """

    def __init__(self, params: TableParams, config: Optional[AnimationConfig] = None):
        super().__init__(config)
        self.params = params
        self.config.duration = params.duration

    def render(self) -> List[np.ndarray]:
        total_frames = int(self.config.duration * self.config.fps)
        frames = []

        font_title = get_font(80)
        font_header = get_font(50)
        font_row = get_font(45)
        font_total = get_font(60)

        for frame_idx in range(total_frames):
            progress = frame_idx / total_frames if total_frames > 1 else 1.0

            img = self._create_frame()
            draw = ImageDraw.Draw(img)
            W, H = self.config.width, self.config.height

            # 标题
            bbox = draw.textbbox((0, 0), self.params.title, font=font_title)
            tw = bbox[2] - bbox[0]
            draw.text(((W - tw) // 2, 200), self.params.title, fill=self.config.text_color, font=font_title)

            # 表头
            y_start = 400
            col_widths = [W // 2, W // 2]
            x_positions = [100, W // 2 + 50]

            for i, h in enumerate(self.params.headers):
                draw.text((x_positions[i], y_start), h, fill=(150, 150, 150), font=font_header)

            # 行数据（逐行淡入）
            row_height = 100
            for row_idx, row in enumerate(self.params.rows):
                row_progress = max(0, min(1, (progress - row_idx * 0.15) / 0.2))
                if row_progress <= 0:
                    continue
                y = y_start + 100 + row_idx * row_height
                for col_idx, cell in enumerate(row):
                    alpha = int(255 * row_progress)
                    # 简化：直接绘制，不处理 alpha
                    color = self.config.accent_color if "+" in cell else self.config.text_color
                    draw.text((x_positions[col_idx], y), cell, fill=color, font=font_row)

            # 总计
            total_progress = max(0, min(1, (progress - 0.7) / 0.3))
            if total_progress > 0:
                y = y_start + 100 + len(self.params.rows) * row_height + 50
                draw.line([(100, y - 20), (W - 100, y - 20)], fill=(100, 100, 100), width=3)
                draw.text((x_positions[0], y), self.params.total_label, fill=self.config.text_color, font=font_total)
                draw.text((x_positions[1], y), self.params.total_value, fill=self.config.accent_color, font=font_total)

            frames.append(self._text_to_array(img))

        return frames


# 注册表
ANIMATION_REGISTRY = {
    "price_contrast": (PriceContrastAnimation, PriceContrastParams),
    "table": (TableAnimation, TableParams),
}


def render_animation(template_id: str, params_dict: dict, output_path: str, config: Optional[AnimationConfig] = None):
    """
    便捷入口：通过模板ID渲染动画

    Args:
        template_id: 模板ID，如 "price_contrast", "table"
        params_dict: 模板参数字典
        output_path: 输出 mp4 路径
        config: 可选的全局配置
    """
    if template_id not in ANIMATION_REGISTRY:
        raise ValueError(f"未知模板: {template_id}。可用: {list(ANIMATION_REGISTRY.keys())}")

    template_cls, params_cls = ANIMATION_REGISTRY[template_id]
    params = params_cls(**params_dict)
    anim = template_cls(params, config)
    anim.save(output_path)
    return output_path
