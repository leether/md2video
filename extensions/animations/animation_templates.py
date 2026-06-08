#!/usr/bin/env python3
"""
Animation Templates — 程序化动画素材模板库（v1.1 扩充版）

目标：将不依赖 AI 的「结构性动画」抽离为可复用模板，
      降低对外部 API（如即梦）的依赖，增强 SKILL 的自创生能力。

v1.1 新增模板：
    - bullet_list：要点列表动画（逐行出现 + 高亮）
    - calendar_highlight：日期标注动画（日历网格 + 高亮某天）
    - quote_card：引用卡片动画（居中排版 + 引号装饰）

核心原则：
    1. 纯 Python + Pillow + numpy，无需外部 API
    2. 模板参数化（vars），实现「一份模板，千次复用」
    3. 输出为透明背景 PNG 序列或带 alpha 的 MP4，直接融入 video pipeline
    4. 每个模板支持 duration 参数（默认 5s），与 segment 时长对齐
    5. 通过 animation_type 字段在 pipeline 中自动路由

当前模板列表：
    - animated_text：逐字/词打字机效果
    - bar_chart：柱状图生长动画
    - pie_chart：饼图旋转展开
    - trend_line：折线趋势动画
    - comparison_split：左右对比画面
    - table_scroll：表格滚动展示
    - bullet_list：要点列表逐行出现
    - calendar_highlight：日历高亮动画
    - quote_card：引用卡片动画
"""

import math
import os
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Callable

from PIL import Image, ImageDraw, ImageFont
import numpy as np


SUPPORTED_ANIMATION_TYPES = {
    "animated_text",
    "bar_chart",
    "pie_chart",
    "trend_line",
    "comparison_split",
    "table_scroll",
    "bullet_list",
    "calendar_highlight",
    "quote_card",
}


def available_animation_types() -> List[str]:
    """Return animation_type values accepted by AnimationRenderer.render_by_type."""
    return sorted(SUPPORTED_ANIMATION_TYPES)


@dataclass
class AnimationTemplate:
    """模板定义"""
    name: str
    description: str
    required_vars: List[str]
    optional_vars: Dict[str, any] = field(default_factory=dict)
    duration: float = 5.0
    fps: int = 30


class AnimationRenderer:
    """
    动画渲染器：将模板定义 + 参数 vars 渲染为帧序列
    """

    def __init__(
        self,
        width: int = 1080,
        height: int = 1920,
        fps: int = 30,
        font_path: str = "/System/Library/Fonts/Hiragino Sans GB.ttc",
    ):
        self.width = width
        self.height = height
        self.fps = fps
        self.font_path = font_path
        self.frames: List[np.ndarray] = []

    def _get_font(self, size: int) -> ImageFont.FreeTypeFont:
        try:
            return ImageFont.truetype(self.font_path, size)
        except:
            return ImageFont.load_default()

    def _create_base_frame(self, bg_color: Tuple[int, int, int] = (255, 255, 255)) -> Image.Image:
        img = Image.new("RGBA", (self.width, self.height), bg_color + (255,))
        return img

    def _save_sequence(
        self,
        frames: List[np.ndarray],
        output_path: str,
        audio_path: Optional[str] = None,
    ) -> str:
        """将帧序列保存为带 alpha 的 MP4（ffmpeg）"""
        output_path = str(output_path)
        temp_dir = Path(output_path).parent / f"_frames_{Path(output_path).stem}"
        temp_dir.mkdir(exist_ok=True)

        for i, frame in enumerate(frames):
            img = Image.fromarray(frame, "RGBA")
            img.save(temp_dir / f"frame_{i:04d}.png")

        ffmpeg_cmd = (
            f"ffmpeg -y -framerate {self.fps} -i '{temp_dir}/frame_%04d.png' "
            f"-c:v libx264 -pix_fmt yuva420p -preset medium -crf 23 '{output_path}'"
        )
        os.system(ffmpeg_cmd)

        if audio_path and Path(audio_path).exists():
            tmp_path = str(output_path).replace(".mp4", "_tmp.mp4")
            os.system(
                f"ffmpeg -y -i '{output_path}' -i '{audio_path}' "
                f"-c:v copy -c:a aac -shortest '{tmp_path}' && mv '{tmp_path}' '{output_path}'"
            )

        for f in temp_dir.glob("*.png"):
            f.unlink()
        temp_dir.rmdir()

        return output_path

    # ═══════════════════════════════════════
    # 模板渲染方法
    # ═══════════════════════════════════════

    def render_animated_text(
        self,
        text: str,
        duration: float = 5.0,
        chars_per_second: float = 6.0,
        font_size: int = 48,
        text_color: Tuple[int, int, int] = (40, 40, 40),
        bg_color: Tuple[int, int, int] = (255, 255, 255),
        cursor_blink: bool = True,
        output_path: str = "output/animated_text.mp4",
    ) -> str:
        """打字机效果：逐字出现，带闪烁光标"""
        total_frames = int(duration * self.fps)
        char_interval = self.fps / chars_per_second
        font = self._get_font(font_size)

        frames = []
        for frame_idx in range(total_frames):
            img = self._create_base_frame(bg_color)
            draw = ImageDraw.Draw(img)

            visible_chars = min(len(text), int(frame_idx / char_interval))
            display_text = text[:visible_chars]

            cursor = "|" if cursor_blink and (frame_idx % 10 < 5) and visible_chars < len(text) else ""
            display_text += cursor

            bbox = draw.textbbox((0, 0), display_text, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            x = (self.width - text_w) // 2
            y = (self.height - text_h) // 2
            draw.text((x, y), display_text, fill=text_color + (255,), font=font)

            frames.append(np.array(img))

        return self._save_sequence(frames, output_path)

    def render_bar_chart(
        self,
        data: List[Tuple[str, float]],
        duration: float = 5.0,
        font_size: int = 36,
        bar_color: Tuple[int, int, int] = (66, 133, 244),
        bg_color: Tuple[int, int, int] = (255, 255, 255),
        output_path: str = "output/bar_chart.mp4",
    ) -> str:
        """柱状图生长动画"""
        total_frames = int(duration * self.fps)
        font = self._get_font(font_size)
        frames = []

        max_val = max(v for _, v in data)
        bar_count = len(data)
        bar_width = (self.width - 200) // bar_count
        bar_gap = 40
        chart_bottom = self.height - 300
        chart_top = 400
        chart_height = chart_bottom - chart_top

        for frame_idx in range(total_frames):
            img = self._create_base_frame(bg_color)
            draw = ImageDraw.Draw(img)
            progress = min(1.0, frame_idx / (total_frames * 0.7))

            for i, (label, value) in enumerate(data):
                bar_h = (value / max_val) * chart_height * progress
                x = 100 + i * (bar_width + bar_gap)
                y = chart_bottom - bar_h
                draw.rectangle(
                    [x, y, x + bar_width, chart_bottom],
                    fill=bar_color + (255,),
                )
                bbox = draw.textbbox((0, 0), label, font=font)
                lw = bbox[2] - bbox[0]
                draw.text((x + (bar_width - lw) // 2, chart_bottom + 20), label, fill=(0, 0, 0, 255), font=font)
                value_text = str(int(value))
                vb = draw.textbbox((0, 0), value_text, font=font)
                vw = vb[2] - vb[0]
                draw.text((x + (bar_width - vw) // 2, y - 40), value_text, fill=(0, 0, 0, 255), font=font)

            frames.append(np.array(img))

        return self._save_sequence(frames, output_path)

    def render_pie_chart(
        self,
        data: List[Tuple[str, float]],
        colors: Optional[List[Tuple[int, int, int]]] = None,
        duration: float = 5.0,
        bg_color: Tuple[int, int, int] = (255, 255, 255),
        output_path: str = "output/pie_chart.mp4",
    ) -> str:
        """饼图旋转展开动画"""
        if colors is None:
            colors = [
                (66, 133, 244), (219, 68, 55), (244, 160, 0),
                (15, 157, 88), (171, 71, 188), (0, 172, 193),
            ]
        total_frames = int(duration * self.fps)
        frames = []

        total = sum(v for _, v in data)
        cx, cy = self.width // 2, self.height // 2
        radius = min(cx, cy) - 200

        for frame_idx in range(total_frames):
            img = self._create_base_frame(bg_color)
            draw = ImageDraw.Draw(img)
            sweep = (frame_idx / total_frames) * 360

            start_angle = -90
            for i, (label, value) in enumerate(data):
                angle = (value / total) * sweep
                end_angle = start_angle + angle
                if angle > 0:
                    color = colors[i % len(colors)]
                    draw.pieslice(
                        [cx - radius, cy - radius, cx + radius, cy + radius],
                        start=start_angle, end=end_angle,
                        fill=color + (255,),
                    )
                start_angle = end_angle

            frames.append(np.array(img))

        return self._save_sequence(frames, output_path)

    def render_trend_line(
        self,
        points: List[float],
        duration: float = 5.0,
        line_color: Tuple[int, int, int] = (66, 133, 244),
        bg_color: Tuple[int, int, int] = (255, 255, 255),
        output_path: str = "output/trend_line.mp4",
    ) -> str:
        """折线趋势动画"""
        total_frames = int(duration * self.fps)
        frames = []

        margin = 150
        chart_w = self.width - 2 * margin
        chart_h = self.height - 2 * margin
        max_val = max(points)
        min_val = min(points)
        val_range = max_val - min_val or 1

        step_x = chart_w / max(1, len(points) - 1)

        for frame_idx in range(total_frames):
            img = self._create_base_frame(bg_color)
            draw = ImageDraw.Draw(img)
            progress = min(1.0, frame_idx / (total_frames * 0.8))
            visible_points = int(len(points) * progress)

            if visible_points >= 2:
                pts = []
                for i in range(visible_points):
                    x = margin + i * step_x
                    y = margin + chart_h - ((points[i] - min_val) / val_range) * chart_h
                    pts.append((int(x), int(y)))
                for i in range(len(pts) - 1):
                    draw.line([pts[i], pts[i+1]], fill=line_color + (255,), width=4)
                for p in pts:
                    draw.ellipse([p[0]-6, p[1]-6, p[0]+6, p[1]+6], fill=line_color + (255,))

            frames.append(np.array(img))

        return self._save_sequence(frames, output_path)

    def render_comparison_split(
        self,
        left_text: str,
        right_text: str,
        duration: float = 5.0,
        split_progress: float = 0.5,
        left_bg: Tuple[int, int, int] = (232, 240, 254),
        right_bg: Tuple[int, int, int] = (252, 232, 232),
        font_size: int = 40,
        output_path: str = "output/comparison_split.mp4",
    ) -> str:
        """左右对比画面"""
        total_frames = int(duration * self.fps)
        font = self._get_font(font_size)
        frames = []

        for frame_idx in range(total_frames):
            img = self._create_base_frame((255, 255, 255))
            draw = ImageDraw.Draw(img)

            img.paste(left_bg + (255,), (0, 0, int(self.width * split_progress), self.height))
            img.paste(right_bg + (255,), (int(self.width * split_progress), 0, self.width, self.height))

            draw = ImageDraw.Draw(img)
            draw.line([(int(self.width * split_progress), 0), (int(self.width * split_progress), self.height)], fill=(200, 200, 200, 255), width=2)

            for text, x_start, x_end in [(left_text, 50, int(self.width * split_progress) - 50), (right_text, int(self.width * split_progress) + 50, self.width - 50)]:
                bbox = draw.textbbox((0, 0), text, font=font)
                tw = bbox[2] - bbox[0]
                th = bbox[3] - bbox[1]
                x = x_start + (x_end - x_start - tw) // 2
                y = (self.height - th) // 2
                draw.text((x, y), text, fill=(40, 40, 40, 255), font=font)

            frames.append(np.array(img))

        return self._save_sequence(frames, output_path)

    def render_table_scroll(
        self,
        headers: List[str],
        rows: List[List[str]],
        duration: float = 5.0,
        font_size: int = 32,
        header_bg: Tuple[int, int, int] = (66, 133, 244),
        row_colors: List[Tuple[int, int, int]] = None,
        output_path: str = "output/table_scroll.mp4",
    ) -> str:
        """表格滚动展示"""
        if row_colors is None:
            row_colors = [(250, 250, 250), (255, 255, 255)]
        total_frames = int(duration * self.fps)
        font = self._get_font(font_size)
        frames = []

        row_h = font_size + 30
        col_w = (self.width - 100) // len(headers)
        total_table_h = (len(rows) + 1) * row_h
        visible_h = self.height - 300
        max_scroll = max(0, total_table_h - visible_h)

        for frame_idx in range(total_frames):
            img = self._create_base_frame()
            draw = ImageDraw.Draw(img)

            progress = frame_idx / total_frames
            scroll_y = int(progress * max_scroll)

            # Header
            for j, h in enumerate(headers):
                x = 50 + j * col_w
                draw.rectangle([x, 100 - scroll_y, x + col_w, 100 + row_h - scroll_y], fill=header_bg + (255,))
                draw.text((x + 10, 110 - scroll_y), h, fill=(255, 255, 255, 255), font=font)

            # Rows
            for i, row in enumerate(rows):
                y = 100 + (i + 1) * row_h - scroll_y
                if y < 100 or y > self.height - 100:
                    continue
                bg = row_colors[i % len(row_colors)]
                for j, cell in enumerate(row):
                    x = 50 + j * col_w
                    draw.rectangle([x, y, x + col_w, y + row_h], fill=bg + (255,))
                    draw.text((x + 10, y + 10), str(cell), fill=(40, 40, 40, 255), font=font)

            frames.append(np.array(img))

        return self._save_sequence(frames, output_path)

    # ═══════════════════════════════════════
    # v1.1 新增模板
    # ═══════════════════════════════════════

    def render_bullet_list(
        self,
        items: List[str],
        title: str = "",
        duration: float = 5.0,
        font_size: int = 44,
        title_size: int = 56,
        bullet: str = "•",
        text_color: Tuple[int, int, int] = (40, 40, 40),
        accent_color: Tuple[int, int, int] = (66, 133, 244),
        bg_color: Tuple[int, int, int] = (255, 255, 255),
        output_path: str = "output/bullet_list.mp4",
    ) -> str:
        """
        要点列表动画：逐行出现 + 高亮当前行

        适用于：总结要点、核心结论、行动建议等段落
        """
        total_frames = int(duration * self.fps)
        font = self._get_font(font_size)
        title_font = self._get_font(title_size)
        frames = []

        line_h = font_size + 40
        title_y = 200 if title else 150
        start_y = title_y + (120 if title else 0)
        # 文字在前15%时间内全部出现，不让观众等
        items_per_frame = total_frames * 0.15 / max(len(items), 1)

        for frame_idx in range(total_frames):
            img = self._create_base_frame(bg_color)
            draw = ImageDraw.Draw(img)

            # 绘制标题
            if title:
                tb = draw.textbbox((0, 0), title, font=title_font)
                tw = tb[2] - tb[0]
                draw.text(((self.width - tw) // 2, title_y), title, fill=text_color + (255,), font=title_font)

            # 逐行出现
            visible_items = min(len(items), int(frame_idx / items_per_frame) + 1)

            for i, item in enumerate(items[:visible_items]):
                y = start_y + i * line_h
                alpha = 255
                # 当前高亮行
                if i == visible_items - 1:
                    # 渐入 alpha
                    item_progress = (frame_idx % items_per_frame) / items_per_frame
                    alpha = int(128 + 127 * min(1.0, item_progress * 2))
                    # 背景高亮条
                    draw.rounded_rectangle(
                        [80, y - 10, self.width - 80, y + line_h + 10],
                        radius=12,
                        fill=accent_color + (30,),
                    )

                draw.text((120, y), bullet, fill=accent_color + (alpha,), font=font)
                draw.text((170, y), item, fill=text_color + (alpha,), font=font)

            frames.append(np.array(img))

        return self._save_sequence(frames, output_path)

    def render_calendar_highlight(
        self,
        year: int,
        month: int,
        highlight_day: int,
        duration: float = 5.0,
        font_size: int = 36,
        day_size: int = 80,
        header_color: Tuple[int, int, int] = (66, 133, 244),
        highlight_color: Tuple[int, int, int] = (234, 67, 53),
        bg_color: Tuple[int, int, int] = (255, 255, 255),
        output_path: str = "output/calendar_highlight.mp4",
    ) -> str:
        """
        日历高亮动画：展示月历网格，高亮指定日期

        适用于：事件预告、里程碑、截止日期、重要日期等
        """
        import calendar
        total_frames = int(duration * self.fps)
        font = self._get_font(font_size)
        header_font = self._get_font(font_size + 8)
        frames = []

        cal = calendar.Calendar()
        month_days = cal.monthdayscalendar(year, month)
        month_name = calendar.month_name[month]
        title = f"{year}年{month}月"

        # 计算布局
        cols = 7
        rows = len(month_days)
        cell_w = min(day_size, (self.width - 200) // cols)
        cell_h = cell_w
        grid_w = cols * cell_w
        grid_h = rows * cell_h
        start_x = (self.width - grid_w) // 2
        start_y = 350

        # 动画参数
        grid_appear_frame = max(1, int(total_frames * 0.3))
        highlight_start = int(total_frames * 0.5)
        highlight_end = max(highlight_start + 1, int(total_frames * 0.85))

        for frame_idx in range(total_frames):
            img = self._create_base_frame(bg_color)
            draw = ImageDraw.Draw(img)

            # 标题
            tb = draw.textbbox((0, 0), title, font=header_font)
            tw = tb[2] - tb[0]
            draw.text(((self.width - tw) // 2, 120), title, fill=(40, 40, 40, 255), font=header_font)

            # 星期标题
            weekdays = ["一", "二", "三", "四", "五", "六", "日"]
            for j, wd in enumerate(weekdays):
                x = start_x + j * cell_w + cell_w // 2
                wb = draw.textbbox((0, 0), wd, font=font)
                ww = wb[2] - wb[0]
                draw.text((x - ww // 2, start_y - 50), wd, fill=(100, 100, 100, 255), font=font)

            # 网格和日期
            grid_progress = min(1.0, frame_idx / grid_appear_frame)
            visible_rows = int(rows * grid_progress) + 1

            for row_idx, week in enumerate(month_days[:visible_rows]):
                for col_idx, day in enumerate(week):
                    if day == 0:
                        continue

                    x = start_x + col_idx * cell_w
                    y = start_y + row_idx * cell_h
                    cx = x + cell_w // 2
                    cy = y + cell_h // 2

                    is_highlight = (day == highlight_day)

                    # 高亮动画
                    if is_highlight and frame_idx >= highlight_start:
                        hl_progress = min(1.0, (frame_idx - highlight_start) / (highlight_end - highlight_start))
                        pulse = 1.0 + 0.15 * math.sin(hl_progress * math.pi * 4)
                        r = int(day_size * 0.4 * pulse)
                        draw.ellipse(
                            [cx - r, cy - r, cx + r, cy + r],
                            fill=highlight_color + (int(200 * hl_progress),),
                        )
                        # 脉冲环
                        ring_r = r + int(10 * pulse)
                        draw.ellipse(
                            [cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r],
                            outline=highlight_color + (int(100 * hl_progress),),
                            width=2,
                        )

                    # 日期数字
                    day_str = str(day)
                    db = draw.textbbox((0, 0), day_str, font=font)
                    dw = db[2] - db[0]
                    dh = db[3] - db[1]
                    text_color = (255, 255, 255) if is_highlight and frame_idx >= highlight_end else (40, 40, 40)
                    draw.text((cx - dw // 2, cy - dh // 2), day_str, fill=text_color + (255,), font=font)

                    # 网格线
                    draw.rectangle([x, y, x + cell_w, y + cell_h], outline=(220, 220, 220, 255), width=1)

            frames.append(np.array(img))

        return self._save_sequence(frames, output_path)

    def render_quote_card(
        self,
        quote: str,
        author: str = "",
        duration: float = 5.0,
        font_size: int = 48,
        author_size: int = 36,
        quote_color: Tuple[int, int, int] = (40, 40, 40),
        accent_color: Tuple[int, int, int] = (66, 133, 244),
        bg_color: Tuple[int, int, int] = (255, 255, 255),
        output_path: str = "output/quote_card.mp4",
    ) -> str:
        """
        引用卡片动画：居中排版 + 引号装饰 + 渐入效果

        适用于：金句、核心观点、名人名言、用户证言等
        """
        total_frames = int(duration * self.fps)
        font = self._get_font(font_size)
        author_font = self._get_font(author_size)
        frames = []

        # 文字换行处理
        def wrap_text(text: str, max_width: int, font) -> List[str]:
            lines = []
            current = ""
            for char in text:
                test = current + char
                bbox = font.getbbox(test)
                if bbox and bbox[2] > max_width:
                    lines.append(current)
                    current = char
                else:
                    current = test
            if current:
                lines.append(current)
            return lines

        max_text_w = self.width - 200
        quote_lines = wrap_text(quote, max_text_w, font)

        line_h = font_size + 20
        total_text_h = len(quote_lines) * line_h
        author_h = author_size + 30 if author else 0
        card_h = total_text_h + author_h + 200
        card_w = self.width - 120

        # 动画参数：文字尽快出现，不让观众等
        fade_in_end = max(1, int(total_frames * 0.03))  # 3%时间完成卡片渐入
        quote_end = max(fade_in_end + 1, int(total_frames * 0.20))    # 20%时间完成文字显示
        hold_end = total_frames

        for frame_idx in range(total_frames):
            img = self._create_base_frame(bg_color)
            draw = ImageDraw.Draw(img)

            # 卡片背景渐入
            if frame_idx < fade_in_end:
                card_alpha = int(255 * (frame_idx / fade_in_end))
                scale = 0.9 + 0.1 * (frame_idx / fade_in_end)
            else:
                card_alpha = 255
                scale = 1.0

            # 绘制卡片背景
            card_x = int((self.width - card_w * scale) // 2)
            card_y = int((self.height - card_h * scale) // 2)
            cw = int(card_w * scale)
            ch = int(card_h * scale)

            draw.rounded_rectangle(
                [card_x, card_y, card_x + cw, card_y + ch],
                radius=20,
                fill=(250, 250, 250, card_alpha),
                outline=accent_color + (int(100 * (card_alpha / 255)),),
                width=2,
            )

            # 左引号装饰
            if frame_idx >= fade_in_end:
                quote_font = self._get_font(80)
                qa = min(255, int(255 * (frame_idx - fade_in_end) / (fade_in_end * 0.5)))
                draw.text((card_x + 30, card_y + 20), '"', fill=accent_color + (qa,), font=quote_font)

            # 引用文字逐行渐入
            text_start_y = card_y + 80
            for li, line in enumerate(quote_lines):
                line_start = fade_in_end + li * int((quote_end - fade_in_end) / max(len(quote_lines), 1))
                if frame_idx >= line_start:
                    la = min(255, int(255 * (frame_idx - line_start) / 10))
                    lb = draw.textbbox((0, 0), line, font=font)
                    lw = lb[2] - lb[0]
                    draw.text((card_x + (cw - lw) // 2, text_start_y + li * line_h), line, fill=quote_color + (la,), font=font)

            # 作者
            if author and frame_idx >= quote_end:
                aa = min(255, int(255 * (frame_idx - quote_end) / 15))
                ab = draw.textbbox((0, 0), f"— {author}", font=author_font)
                aw = ab[2] - ab[0]
                ay = text_start_y + len(quote_lines) * line_h + 30
                draw.text((card_x + (cw - aw) // 2, ay), f"— {author}", fill=(100, 100, 100, aa), font=author_font)

            frames.append(np.array(img))

        return self._save_sequence(frames, output_path)

    # ═══════════════════════════════════════
    # 统一路由入口
    # ═══════════════════════════════════════

    def render_by_type(
        self,
        animation_type: str,
        vars_dict: Dict,
        duration: float = 5.0,
        output_path: str = "output/animation.mp4",
    ) -> str:
        """
        根据 animation_type 路由到对应渲染方法

        这是 pipeline 中的统一入口。
        """
        renderers = {
            "animated_text": lambda: self.render_animated_text(
                text=vars_dict.get("text", ""),
                duration=duration,
                output_path=output_path,
            ),
            "bar_chart": lambda: self.render_bar_chart(
                data=vars_dict.get("data", []),
                duration=duration,
                output_path=output_path,
            ),
            "pie_chart": lambda: self.render_pie_chart(
                data=vars_dict.get("data", []),
                duration=duration,
                output_path=output_path,
            ),
            "trend_line": lambda: self.render_trend_line(
                points=vars_dict.get("points", []),
                duration=duration,
                output_path=output_path,
            ),
            "comparison_split": lambda: self.render_comparison_split(
                left_text=vars_dict.get("left", ""),
                right_text=vars_dict.get("right", ""),
                duration=duration,
                output_path=output_path,
            ),
            "table_scroll": lambda: self.render_table_scroll(
                headers=vars_dict.get("headers", []),
                rows=vars_dict.get("rows", []),
                duration=duration,
                output_path=output_path,
            ),
            "bullet_list": lambda: self.render_bullet_list(
                items=vars_dict.get("items", []),
                title=vars_dict.get("title", ""),
                duration=duration,
                output_path=output_path,
            ),
            "calendar_highlight": lambda: self.render_calendar_highlight(
                year=vars_dict.get("year", 2026),
                month=vars_dict.get("month", 1),
                highlight_day=vars_dict.get("highlight_day", 1),
                duration=duration,
                output_path=output_path,
            ),
            "quote_card": lambda: self.render_quote_card(
                quote=vars_dict.get("quote", ""),
                author=vars_dict.get("author", ""),
                duration=duration,
                output_path=output_path,
            ),
        }

        if animation_type not in renderers:
            raise ValueError(f"Unknown animation_type: {animation_type}. Available: {available_animation_types()}")

        return renderers[animation_type]()


# 便捷入口
def render_animation(
    animation_type: str,
    vars_dict: Dict,
    duration: float = 5.0,
    output_path: str = "output/animation.mp4",
) -> str:
    """一键渲染指定类型的动画"""
    renderer = AnimationRenderer()
    return renderer.render_by_type(animation_type, vars_dict, duration, output_path)
