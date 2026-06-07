#!/usr/bin/env python3
"""
Concat Engine — 精确时轴拼接引擎（v1.1 Clip-based）

核心原则：
1. 以 timeline.json 为唯一数据源，消除手动硬编码映射表
2. 每段素材精确匹配旁白时长：scale+pad→1080×1920，trim/pad到目标时长
3. 音频拼接唯一可靠路径：mp3→wav 中间格式 → concat → m4a
4. 追加结尾元素（CTA卡片、无声过渡等）必须在 timeline 中显式声明
5. v1.1 升级：支持 per-clip fade_in/fade_out 和段间 crossfade transition

拼接策略（分支选择）：
    - 快速路径：所有 clip 无 fade/transition → concat demuxer + -c copy
    - 特效路径：任意 clip 有 fade/transition → filter_complex（xfade + acrossfade）

技术栈：
    - 视频处理：ffmpeg（scale, pad, fade, xfade, filter_complex）
    - 音频处理：ffmpeg（mp3→wav, afade, acrossfade, aac编码）
"""

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Dict


@dataclass
class ConcatConfig:
    """拼接配置"""
    target_width: int = 1080
    target_height: int = 1920
    target_fps: int = 30
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    audio_bitrate: str = "192k"
    crf: int = 23
    pixel_format: str = "yuv420p"
    silent_pad_color: str = "black"
    silent_pad_text: str = ""
    # 转场默认配置
    default_transition_duration: float = 0.5
    default_transition_type: str = "fade"


class ConcatEngine:
    """
    精确时轴拼接引擎（Clip-based）
    """

    def __init__(self, config: Optional[ConcatConfig] = None):
        self.config = config or ConcatConfig()
        self.output_dir = Path("output")
        self.temp_dir = Path(tempfile.gettempdir()) / "md2video_concat"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.timeline: List[dict] = []
        self.concat_list_file: Optional[Path] = None
        self.audio_concat_list_file: Optional[Path] = None

    def _probe_video_info(self, video_path: str) -> dict:
        """用 ffprobe 获取视频信息"""
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate,duration",
            "-show_entries", "format=duration",
            "-of", "json",
            video_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(result.stdout)

    def _probe_duration(self, media_path: str) -> float:
        """用 ffprobe 获取媒体精确时长"""
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            media_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())

    def _has_audio_stream(self, video_path: str) -> bool:
        """检查视频是否包含音频流"""
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=codec_type",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return "audio" in result.stdout.lower()

    def _normalize_video(
        self,
        input_path: str,
        output_path: str,
        target_duration: float,
        ensure_audio: bool = True,
    ) -> float:
        """
        将单个视频归一化到目标时长和分辨率

        策略：
        1. scale + pad 到 1080×1920（保持比例，不足处黑边填充）
        2. 如果视频时长 > 目标时长：trim 到目标时长
        3. 如果视频时长 < 目标时长：freeze 最后一帧 pad 到目标时长
        4. 如果是图片：loop 成目标时长的视频
        5. 确保有音频流（如果没有，添加静音音轨）
        6. 统一帧率、编码格式

        Returns:
            实际输出时长（应与 target_duration 一致）
        """
        path = Path(input_path)
        is_image = path.suffix.lower() in (".jpg", ".jpeg", ".png", ".gif", ".webp")

        # 构建视频滤镜链
        filters = []
        scale_pad = (
            f"scale={self.config.target_width}:{self.config.target_height}:force_original_aspect_ratio=decrease,"
            f"pad={self.config.target_width}:{self.config.target_height}:(ow-iw)/2:(oh-ih)/2:black"
        )
        filters.append(scale_pad)
        filters.append(f"fps={self.config.target_fps}")

        # 确定是否需要确保音频
        has_audio = self._has_audio_stream(input_path) if not is_image else False
        need_audio = ensure_audio and not has_audio

        if is_image:
            # 图片：loop 成目标时长的视频
            filter_str = ",".join(filters)
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1",
                "-i", input_path,
                "-t", str(target_duration),
                "-vf", filter_str,
                "-c:v", self.config.video_codec,
                "-pix_fmt", self.config.pixel_format,
                "-crf", str(self.config.crf),
                "-an",  # 先不处理音频
                output_path,
            ]
        else:
            # 视频：先获取时长
            info = self._probe_video_info(input_path)
            raw_duration = float(info.get("format", {}).get("duration", 0) or 0)
            if raw_duration == 0:
                raw_duration = self._probe_duration(input_path)

            # 时长调整策略
            if abs(raw_duration - target_duration) < 0.1:
                # 几乎相等，只做缩放
                filter_str = ",".join(filters)
            elif raw_duration > target_duration:
                # 太长：trim
                filter_str = ",".join(filters + [f"trim=duration={target_duration}"])
            else:
                # 太短：freeze 最后一帧 pad
                freeze_duration = target_duration - raw_duration
                filter_str = ",".join(filters + [f"tpad=stop_mode=clone:stop_duration={freeze_duration}"])

            cmd = [
                "ffmpeg", "-y",
                "-i", input_path,
                "-vf", filter_str,
                "-t", str(target_duration),
                "-c:v", self.config.video_codec,
                "-pix_fmt", self.config.pixel_format,
                "-crf", str(self.config.crf),
                "-an",  # 先不处理音频
                output_path,
            ]

        subprocess.run(cmd, capture_output=True, check=True)

        # 如果没有音频，添加静音音轨
        if need_audio or is_image:
            temp_with_audio = str(self.temp_dir / f"{path.stem}_with_audio.mp4")
            cmd_audio = [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", f"anullsrc=r=48000:cl=stereo",
                "-i", output_path,
                "-shortest",
                "-c:v", "copy",
                "-c:a", self.config.audio_codec,
                "-b:a", self.config.audio_bitrate,
                temp_with_audio,
            ]
            subprocess.run(cmd_audio, capture_output=True, check=True)
            # 替换原文件
            os.replace(temp_with_audio, output_path)

        return self._probe_duration(output_path)

    def _convert_audio_to_wav(self, mp3_path: str, output_wav: str) -> str:
        """mp3 → wav（无损中间格式，确保 concat 精确）"""
        cmd = [
            "ffmpeg", "-y",
            "-i", mp3_path,
            "-ar", "48000",
            "-ac", "2",
            "-c:a", "pcm_s16le",
            output_wav,
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        return output_wav

    def _build_video_concat_list(self, normalized_paths: List[str]) -> Path:
        """生成 concat demuxer 列表文件"""
        list_file = self.temp_dir / "video_concat_list.txt"
        with open(list_file, "w") as f:
            for p in normalized_paths:
                abs_path = str(Path(p).resolve())
                f.write(f"file '{abs_path}'\n")
        self.concat_list_file = list_file
        return list_file

    def _build_audio_concat_list(self, wav_paths: List[str]) -> Path:
        """生成音频 concat 列表文件"""
        list_file = self.temp_dir / "audio_concat_list.txt"
        with open(list_file, "w") as f:
            for p in wav_paths:
                abs_path = str(Path(p).resolve())
                f.write(f"file '{abs_path}'\n")
        self.audio_concat_list_file = list_file
        return list_file

    # ═══════════════════════════════════════════════════════
    # 快速路径：无特效，直接 concat
    # ═══════════════════════════════════════════════════════

    def _concat_fast_path(
        self,
        normalized_videos: List[str],
        audio_wavs: List[str],
        output_video: str,
    ) -> Path:
        """快速路径：concat demuxer + -c copy"""
        # 视频拼接
        video_list = self._build_video_concat_list(normalized_videos)
        temp_concat_video = self.temp_dir / "concat_video.mp4"

        cmd_video = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(video_list),
            "-c", "copy",
            str(temp_concat_video),
        ]
        subprocess.run(cmd_video, capture_output=True, check=True)

        # 音频拼接
        if audio_wavs:
            audio_list = self._build_audio_concat_list(audio_wavs)
            temp_concat_audio = self.temp_dir / "concat_audio.m4a"

            cmd_audio = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(audio_list),
                "-c:a", self.config.audio_codec,
                "-b:a", self.config.audio_bitrate,
                str(temp_concat_audio),
            ]
            subprocess.run(cmd_audio, capture_output=True, check=True)

            # 音视频合并
            cmd_mux = [
                "ffmpeg", "-y",
                "-i", str(temp_concat_video),
                "-i", str(temp_concat_audio),
                "-c:v", "copy",
                "-c:a", "copy",
                "-shortest",
                output_video,
            ]
        else:
            cmd_mux = [
                "ffmpeg", "-y",
                "-i", str(temp_concat_video),
                "-c:v", "copy",
                output_video,
            ]

        subprocess.run(cmd_mux, capture_output=True, check=True)
        return Path(output_video)

    # ═══════════════════════════════════════════════════════
    # 特效路径：filter_complex（fade + transition）
    # ═══════════════════════════════════════════════════════

    def _build_filter_complex(
        self,
        clips: List[dict],
    ) -> Tuple[List[str], str, str]:
        """
        构建 filter_complex 滤镜链

        Returns:
            (ffmpeg_args, final_video_label, final_audio_label)
        """
        filter_parts = []

        # 计算每段的有效 fade（transition 覆盖相邻段的 fade）
        effective_fades = []
        for i, clip in enumerate(clips):
            fade_in = clip.get("fade_in", 0.0)
            fade_out = clip.get("fade_out", 0.0)

            # 如果前一段有 transition，当前段的 fade_in 被覆盖
            if i > 0:
                prev_trans = clips[i - 1].get("transition")
                if prev_trans:
                    fade_in = 0.0

            # 如果当前段有 transition，当前段的 fade_out 被覆盖
            trans = clip.get("transition")
            if trans:
                fade_out = 0.0

            effective_fades.append((fade_in, fade_out))

        # 为每个输入添加 fade 滤镜
        for i, (clip, (fade_in, fade_out)) in enumerate(zip(clips, effective_fades)):
            duration = clip["duration"]

            # 视频 fade
            video_filters = [f"[{i}:v]setpts=PTS-STARTPTS"]
            if fade_in > 0:
                video_filters.append(f"fade=t=in:st=0:d={fade_in}")
            if fade_out > 0:
                video_filters.append(f"fade=t=out:st={duration - fade_out}:d={fade_out}")
            video_filters.append(f"[v{i}]")
            filter_parts.append(",".join(video_filters))

            # 音频 fade
            audio_filters = [f"[{i}:a]asetpts=PTS-STARTPTS"]
            if fade_in > 0:
                audio_filters.append(f"afade=t=in:st=0:d={fade_in}")
            if fade_out > 0:
                audio_filters.append(f"afade=t=out:st={duration - fade_out}:d={fade_out}")
            audio_filters.append(f"[a{i}]")
            filter_parts.append(",".join(audio_filters))

        # 链式应用 transition
        video_chain = "v0"
        audio_chain = "a0"

        for i in range(1, len(clips)):
            trans = clips[i - 1].get("transition")
            if not trans:
                # 没有 transition，简单拼接（用 concat filter）
                # 但这里我们已经在做 filter_complex 了，所以用 concat filter
                filter_parts.append(
                    f"[{video_chain}][v{i}]concat=n=2:v=1:a=0[vt{i}]"
                )
                filter_parts.append(
                    f"[{audio_chain}][a{i}]concat=n=2:v=0:a=1[at{i}]"
                )
                video_chain = f"vt{i}"
                audio_chain = f"at{i}"
            else:
                trans_type = trans.get("type", self.config.default_transition_type)
                trans_duration = trans.get("duration", self.config.default_transition_duration)

                # 计算 offset
                # offset = sum(clips[0:i].duration) - trans_duration * i
                cum_duration = sum(c["duration"] for c in clips[:i])
                offset = cum_duration - trans_duration * i

                # xfade 视频转场
                xfade_types = {
                    "fade": "fade",
                    "crossfade": "fade",
                    "slideleft": "slideleft",
                    "slideright": "slideright",
                    "slideup": "slideup",
                    "slidedown": "slidedown",
                    "wipeleft": "wipeleft",
                    "wiperight": "wiperight",
                }
                xfade_type = xfade_types.get(trans_type, "fade")

                filter_parts.append(
                    f"[{video_chain}][v{i}]xfade=transition={xfade_type}:"
                    f"duration={trans_duration}:offset={offset}[vt{i}]"
                )

                # acrossfade 音频交叉淡入淡出
                filter_parts.append(
                    f"[{audio_chain}][a{i}]acrossfade=d={trans_duration}:"
                    f"c1=tri:c2=tri[at{i}]"
                )

                video_chain = f"vt{i}"
                audio_chain = f"at{i}"

        filter_complex = ";".join(filter_parts)
        return filter_complex, video_chain, audio_chain

    def _concat_effect_path(
        self,
        normalized_videos: List[str],
        clips: List[dict],
        output_video: str,
    ) -> Path:
        """特效路径：filter_complex"""
        filter_complex, v_out, a_out = self._build_filter_complex(clips)

        # 构建输入参数
        inputs = []
        for path in normalized_videos:
            inputs.extend(["-i", path])

        cmd = [
            "ffmpeg", "-y",
            *inputs,
            "-filter_complex", filter_complex,
            "-map", f"[{v_out}]",
            "-map", f"[{a_out}]",
            "-c:v", self.config.video_codec,
            "-preset", "fast",
            "-crf", str(self.config.crf),
            "-c:a", self.config.audio_codec,
            "-b:a", self.config.audio_bitrate,
            "-movflags", "+faststart",
            "-pix_fmt", self.config.pixel_format,
            output_video,
        ]

        subprocess.run(cmd, capture_output=True, check=True)
        return Path(output_video)

    # ═══════════════════════════════════════════════════════
    # 主入口
    # ═══════════════════════════════════════════════════════

    def concat(
        self,
        timeline_path: str = "output/timeline.json",
        segments_audio_dir: str = "output/narration_segments",
        output_video: str = "output/final.mp4",
    ) -> Path:
        """
        主入口：按 timeline 拼接最终视频

        自动选择路径：
        - 所有 clip 无 fade/transition → 快速路径（-c copy）
        - 任意 clip 有 fade/transition → 特效路径（filter_complex）
        """
        # 加载 timeline
        with open(timeline_path, "r", encoding="utf-8") as f:
            timeline_data = json.load(f)
        self.timeline = timeline_data.get("entries", [])

        if not self.timeline:
            raise ValueError("Timeline is empty")

        # 判断是否需要走特效路径
        has_effects = any(
            e.get("fade_in", 0) > 0 or e.get("fade_out", 0) > 0 or e.get("transition") is not None
            for e in self.timeline
        )

        print(f"[ConcatEngine] 处理 {len(self.timeline)} 个片段...")
        print(f"[ConcatEngine] 特效路径: {'是' if has_effects else '否（快速路径）'}")

        normalized_videos = []
        audio_wavs = []

        for entry in self.timeline:
            seg_id = entry["segment_id"]
            media_path = entry["media_path"]
            target_duration = entry["duration"]

            # 1. 归一化视频
            norm_path = self.temp_dir / f"{seg_id}_norm.mp4"
            actual_duration = self._normalize_video(
                media_path, str(norm_path), target_duration, ensure_audio=True
            )
            normalized_videos.append(str(norm_path))

            # 校验
            if abs(actual_duration - target_duration) > 0.5:
                print(f"[WARN] {seg_id}: 归一化后时长 {actual_duration:.2f}s 与目标 {target_duration:.2f}s 偏差过大")

            # 2. 转换音频为 wav（快速路径需要）
            mp3_path = Path(segments_audio_dir) / f"{seg_id}.mp3"
            if mp3_path.exists():
                wav_path = self.temp_dir / f"{seg_id}.wav"
                self._convert_audio_to_wav(str(mp3_path), str(wav_path))
                audio_wavs.append(str(wav_path))
            else:
                print(f"[WARN] {seg_id}: 找不到音频 {mp3_path}")

        # 选择拼接路径
        if has_effects:
            # 特效路径：视频用 filter_complex，音频也包含在 filter_complex 中
            # 注意：特效路径下，normalized_videos 已经包含音频了，不需要单独处理音频
            output = self._concat_effect_path(normalized_videos, self.timeline, output_video)
        else:
            # 快速路径
            output = self._concat_fast_path(normalized_videos, audio_wavs, output_video)

        # 验证输出
        output_duration = self._probe_duration(output_video)
        expected_duration = sum(e["duration"] for e in self.timeline)
        print(f"[ConcatEngine] 输出完成: {output_video}")
        print(f"[ConcatEngine] 预期时长: {expected_duration:.2f}s, 实际时长: {output_duration:.2f}s, 差值: {abs(output_duration - expected_duration):.3f}s")

        return Path(output_video)

    def append_endcard(
        self,
        input_video: str,
        endcard_path: str,
        output_video: str,
        endcard_duration: Optional[float] = None,
    ) -> Path:
        """
        追加结尾卡片（CTA、关注引导等）

        必须在 timeline.json 中显式声明为最后一个 segment，
        或作为独立步骤调用。
        """
        if endcard_duration:
            # 归一化 endcard 时长
            norm_endcard = self.temp_dir / "endcard_norm.mp4"
            self._normalize_video(endcard_path, str(norm_endcard), endcard_duration)
            endcard_path = str(norm_endcard)

        # 两文件拼接
        list_file = self.temp_dir / "endcard_list.txt"
        with open(list_file, "w") as f:
            f.write(f"file '{Path(input_video).resolve()}'\n")
            f.write(f"file '{Path(endcard_path).resolve()}'\n")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_file),
            "-c", "copy",
            output_video,
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        return Path(output_video)
