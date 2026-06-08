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

        # ── 活记忆加载：启动时自动感知历史教训 ──
        try:
            from harness.memory_loader import load_living_memory, format_risk_warnings
            memory = load_living_memory()
            warning_text = format_risk_warnings(memory)
            if warning_text:
                print(warning_text)
        except Exception as e:
            # 活记忆加载失败不阻断拼接流程
            print(f"[ConcatEngine] 活记忆加载跳过: {e}")

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

    def _deduplicate_cta(self):
        """CTA 去重：只保留最后一个作为 endcard，其他降级为 narrative"""
        cta_indices = []
        for i, entry in enumerate(self.timeline):
            seg_id = entry.get("segment_id", "")
            seg_type = entry.get("segment_type", "")
            if "cta" in seg_id.lower() or seg_type == "cta":
                cta_indices.append(i)

        if len(cta_indices) > 1:
            print(f"[ConcatEngine] 检测到 {len(cta_indices)} 个 CTA，去重中...")
            for i in cta_indices[:-1]:
                old_type = self.timeline[i].get("segment_type", "?")
                self.timeline[i]["segment_type"] = "narrative"
                print(f"[ConcatEngine]   {self.timeline[i]['segment_id']}: {old_type} → narrative")

        # 确保最后一个是 CTA
        if not self.timeline:
            return

        last = self.timeline[-1]
        last_is_cta = "cta" in last.get("segment_id", "").lower() or last.get("segment_type") == "cta"

        if not last_is_cta and cta_indices:
            last_cta_idx = cta_indices[-1]
            cta_entry = self.timeline.pop(last_cta_idx)
            self.timeline.append(cta_entry)
            print(f"[ConcatEngine] 将 {cta_entry['segment_id']} 移到末尾作为 endcard")

    def _generate_cta_endcard(self, qr_path="assets/qr.png", duration=5.0):
        """生成 CTA endcard 视频（黑底+二维码居中+静音音轨）"""
        qr = Path(qr_path)
        if not qr.exists():
            print(f"[WARN] QR 图片不存在: {qr_path}")
            return None

        endcard_video = self.temp_dir / "cta_endcard.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", str(qr),
            "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
            "-vf",
            f"scale=400:400,pad={self.config.target_width}:{self.config.target_height}:(ow-iw)/2:(oh-ih)/2:black",
            "-shortest",
            "-t", str(duration),
            "-c:v", self.config.video_codec,
            "-c:a", self.config.audio_codec,
            "-b:a", self.config.audio_bitrate,
            "-pix_fmt", self.config.pixel_format,
            str(endcard_video),
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        return str(endcard_video)

    def _normalize_video(
        self,
        input_path: str,
        output_path: str,
        target_duration: float,
        ensure_audio: bool = True,
    ) -> float:
        """
        将单个视频归一化到目标时长和分辨率

        策略（v1.2 三步分离）：
        1. 生成无音频视频（scale/pad/trim/tpad/fps）
        2. 单独生成音频（原始音频提取+apad pad 到目标时长，或无音频时生成静音）
        3. 合并视频+音频

        三步分离彻底绕过 -vf 与 -af 同时存在时的 ffmpeg 行为不一致问题。
        """
        path = Path(input_path)
        is_image = path.suffix.lower() in (".jpg", ".jpeg", ".png", ".gif", ".webp")

        # ═══════════════════════════════════════
        # Step 1: 生成无音频视频
        # ═══════════════════════════════════════
        filters = []
        scale_pad = (
            f"scale={self.config.target_width}:{self.config.target_height}:force_original_aspect_ratio=decrease,"
            f"pad={self.config.target_width}:{self.config.target_height}:(ow-iw)/2:(oh-ih)/2:black"
        )
        filters.append(scale_pad)
        filters.append(f"fps={self.config.target_fps}")

        if is_image:
            filter_str = ",".join(filters)
            cmd_video = [
                "ffmpeg", "-y", "-v", "error",
                "-loop", "1",
                "-i", input_path,
                "-t", str(target_duration),
                "-vf", filter_str,
                "-c:v", self.config.video_codec,
                "-pix_fmt", self.config.pixel_format,
                "-crf", str(self.config.crf),
                "-an",
                output_path,
            ]
        else:
            info = self._probe_video_info(input_path)
            raw_duration = float(info.get("format", {}).get("duration", 0) or 0)
            if raw_duration == 0:
                raw_duration = self._probe_duration(input_path)

            # 必须精确匹配 target_duration，否则 filter_complex 的 acrossfade 会累积错位
            if abs(raw_duration - target_duration) < 0.001:
                filter_str = ",".join(filters)
            elif raw_duration > target_duration:
                filter_str = ",".join(filters + [f"trim=duration={target_duration}"])
            else:
                freeze_duration = target_duration - raw_duration
                filter_str = ",".join(filters + [f"tpad=stop_mode=clone:stop_duration={freeze_duration}"])

            cmd_video = [
                "ffmpeg", "-y", "-v", "error",
                "-i", input_path,
                "-vf", filter_str,
                "-t", str(target_duration),
                "-c:v", self.config.video_codec,
                "-pix_fmt", self.config.pixel_format,
                "-crf", str(self.config.crf),
                "-an",
                output_path,
            ]

        subprocess.run(cmd_video, capture_output=True, check=True)

        # ═══════════════════════════════════════
        # Step 2: 单独生成音频（精确到 target_duration）
        # ═══════════════════════════════════════
        has_audio = self._has_audio_stream(input_path) if not is_image else False
        temp_audio = str(self.temp_dir / f"{path.stem}_audio.m4a")

        if has_audio:
            # 提取原始音频，用 apad pad 到目标时长
            # 注意：不能加 -shortest，否则 ffmpeg 在原始音频 EOF 时立即停止，apad 来不及 pad
            cmd_audio = [
                "ffmpeg", "-y", "-v", "error",
                "-i", input_path,
                "-vn",
                "-af", f"apad=pad_dur={target_duration}",
                "-t", str(target_duration),
                "-c:a", self.config.audio_codec,
                "-b:a", self.config.audio_bitrate,
                temp_audio,
            ]
        else:
            # 生成静音音频
            cmd_audio = [
                "ffmpeg", "-y", "-v", "error",
                "-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo",
                "-t", str(target_duration),
                "-c:a", self.config.audio_codec,
                "-b:a", self.config.audio_bitrate,
                temp_audio,
            ]

        subprocess.run(cmd_audio, capture_output=True, check=True)

        # ═══════════════════════════════════════
        # Step 3: 合并视频和音频
        # ═══════════════════════════════════════
        temp_merged = str(self.temp_dir / f"{path.stem}_merged.mp4")
        cmd_merge = [
            "ffmpeg", "-y", "-v", "error",
            "-i", output_path,
            "-i", temp_audio,
            "-c:v", "copy",
            "-c:a", "copy",
            "-shortest",
            temp_merged,
        ]
        subprocess.run(cmd_merge, capture_output=True, check=True)
        os.replace(temp_merged, output_path)

        # 清理临时音频文件
        Path(temp_audio).unlink(missing_ok=True)

        # 验证：音视频时长必须一致
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=duration", "-of", "default=noprint_wrappers=1", output_path],
            capture_output=True, text=True
        )
        durations = [float(x.split("=")[1]) for x in probe.stdout.strip().split("\n") if x.startswith("duration=")]
        if len(durations) >= 2:
            vdur, adur = durations[0], durations[1]
            if abs(adur - target_duration) > 0.5 or abs(vdur - target_duration) > 0.5:
                print(f"[WARN] {path.stem}: 视频={vdur:.2f}s 音频={adur:.2f}s 目标={target_duration:.2f}s")

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
    ) -> Tuple[str, str]:
        """
        构建视频 filter_complex 滤镜链（音频用 Python 单独处理，避免 amix OOM）

        Returns:
            (filter_complex_string, final_video_label)
        """
        filter_parts = []

        # 计算每段的有效 fade（transition 覆盖相邻段的 fade）
        effective_fades = []
        for i, clip in enumerate(clips):
            fade_in = clip.get("fade_in", 0.0)
            fade_out = clip.get("fade_out", 0.0)

            if i > 0:
                prev_trans = clips[i - 1].get("transition")
                if prev_trans:
                    fade_in = 0.0

            trans = clip.get("transition")
            if trans:
                fade_out = 0.0

            effective_fades.append((fade_in, fade_out))

        # 为每个输入添加 fade 滤镜
        for i, (clip, (fade_in, fade_out)) in enumerate(zip(clips, effective_fades)):
            duration = clip["duration"]

            video_filters = ["setpts=PTS-STARTPTS"]
            if fade_in > 0:
                video_filters.append(f"fade=t=in:st=0:d={fade_in}")
            if fade_out > 0:
                video_filters.append(f"fade=t=out:st={duration - fade_out}:d={fade_out}")
            filter_parts.append(f"[{i}:v]{','.join(video_filters)}[v{i}]")

        # 链式应用 transition（视频）
        video_chain = "v0"

        for i in range(1, len(clips)):
            trans = clips[i - 1].get("transition")
            if not trans:
                filter_parts.append(
                    f"[{video_chain}][v{i}]concat=n=2:v=1:a=0[vt{i}]"
                )
                video_chain = f"vt{i}"
            else:
                trans_type = trans.get("type", self.config.default_transition_type)
                trans_duration = trans.get("duration", self.config.default_transition_duration)

                cum_duration = sum(c["duration"] for c in clips[:i])
                cum_trans_duration = sum(
                    clips[j].get("transition", {}).get("duration", 0.0)
                    for j in range(i)
                )
                offset = cum_duration - cum_trans_duration

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
                video_chain = f"vt{i}"

        filter_complex = ";".join(filter_parts)
        return filter_complex, video_chain

    def _concat_effect_path(
        self,
        normalized_videos: List[str],
        clips: List[dict],
        output_video: str,
    ) -> Path:
        """特效路径：filter_complex（仅视频，音频由 Python 单独处理）"""
        filter_complex, v_out = self._build_filter_complex(clips)

        inputs = []
        for path in normalized_videos:
            inputs.extend(["-i", path])

        cmd = [
            "ffmpeg", "-y",
            *inputs,
            "-filter_complex", filter_complex,
            "-map", f"[{v_out}]",
            "-an",  # 无音频，音频由 Python 单独混合
            "-c:v", self.config.video_codec,
            "-preset", "fast",
            "-crf", str(self.config.crf),
            "-movflags", "+faststart",
            "-pix_fmt", self.config.pixel_format,
            output_video,
        ]

        result = subprocess.run(cmd, capture_output=True, check=False)
        if result.returncode != 0:
            print(f"[ConcatEngine] ffmpeg failed with code {result.returncode}")
            print(f"[ConcatEngine] stderr: {result.stderr.decode('utf-8', errors='replace')[:2000]}")
            raise subprocess.CalledProcessError(
                result.returncode, cmd, output=result.stdout, stderr=result.stderr
            )
        return Path(output_video)

    def _mix_audio_python(
        self,
        normalized_videos: List[str],
        clips: List[dict],
    ) -> Path:
        """
        用 Python + numpy 混合音频，避免 ffmpeg amix 内存不足。
        每个音频流按 start_time 精确对齐，transition 期间自然叠加。
        """
        import numpy as np
        import wave

        sr = 48000
        last_clip = clips[-1]
        total_duration = last_clip["end_time"]
        total_samples = int(total_duration * sr) + sr  # 多留 1 秒缓冲

        mixed = np.zeros(total_samples, dtype=np.float64)

        for i, video_path in enumerate(normalized_videos):
            clip = clips[i]
            start_time = clip["start_time"]

            # 提取音频样本
            cmd = [
                "ffmpeg", "-y", "-v", "error",
                "-i", video_path,
                "-vn", "-ar", str(sr), "-ac", "1",
                "-c:a", "pcm_s16le", "-f", "s16le", "-",
            ]
            result = subprocess.run(cmd, capture_output=True, check=True)
            samples = np.frombuffer(result.stdout, dtype=np.int16).astype(np.float64)

            start_sample = int(start_time * sr)
            end_sample = min(start_sample + len(samples), total_samples)

            if start_sample < total_samples:
                seg_len = end_sample - start_sample
                mixed[start_sample:end_sample] += samples[:seg_len]

        # 归一化防止 clipping
        max_amp = np.max(np.abs(mixed))
        if max_amp > 32767:
            mixed = mixed * (32767.0 / max_amp)

        # 保存为 wav
        temp_audio = self.temp_dir / "mixed_audio.wav"
        mixed_int16 = mixed.astype(np.int16)
        with wave.open(str(temp_audio), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(mixed_int16.tobytes())

        return temp_audio

    # ═══════════════════════════════════════════════════════
    # 主入口
    # ═══════════════════════════════════════════════════════

    def concat(
        self,
        timeline_path: str = "output/timeline.json",
        segments_audio_dir: str = "output/narration_segments",
        output_video: str = "output/final.mp4",
        auto_harness: bool = False,
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

        # CTA 去重与结尾修正
        self._deduplicate_cta()

        # 重新计算 start_time / end_time（与 filter_complex offset 逻辑一致）
        cum_time = 0.0
        for entry in self.timeline:
            entry["start_time"] = cum_time
            trans = entry.get("transition")
            if trans:
                cum_time += entry["duration"] - trans.get("duration", 0.0)
            else:
                cum_time += entry["duration"]
            entry["end_time"] = cum_time

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

            # 2. 处理音频：TTS 旁白混入归一化视频
            mp3_path = Path(segments_audio_dir) / f"{seg_id}.mp3"
            if mp3_path.exists():
                wav_path = self.temp_dir / f"{seg_id}.wav"
                self._convert_audio_to_wav(str(mp3_path), str(wav_path))
                audio_wavs.append(str(wav_path))

                # 将 TTS 旁白混入归一化视频
                # 如果源素材有原始音频（如背景音乐），混合保留；否则直接替换
                temp_with_tts = str(self.temp_dir / f"{seg_id}_tts.mp4")
                has_original_audio = self._has_audio_stream(media_path)
                if has_original_audio:
                    # 混合模式：原始音频降音量 + TTS，避免 clipping
                    cmd_tts = [
                        "ffmpeg", "-y", "-v", "error",
                        "-i", str(norm_path),
                        "-i", str(wav_path),
                        "-filter_complex",
                        "[0:a]volume=0.2[orig];[1:a]volume=1.0[tts];"
                        "[orig][tts]amix=inputs=2:normalize=0[aout];"
                        "[aout]volume=0.8[final]",
                        "-map", "0:v",
                        "-map", "[final]",
                        "-c:v", "copy",
                        "-c:a", self.config.audio_codec,
                        "-b:a", self.config.audio_bitrate,
                        "-shortest",
                        temp_with_tts,
                    ]
                else:
                    # 替换模式：源素材无音频，直接用 TTS
                    cmd_tts = [
                        "ffmpeg", "-y", "-v", "error",
                        "-i", str(norm_path),
                        "-i", str(wav_path),
                        "-map", "0:v",
                        "-map", "1:a",
                        "-c:v", "copy",
                        "-c:a", self.config.audio_codec,
                        "-b:a", self.config.audio_bitrate,
                        "-shortest",
                        temp_with_tts,
                    ]
                subprocess.run(cmd_tts, capture_output=True, check=True)
                os.replace(temp_with_tts, norm_path)
            else:
                print(f"[WARN] {seg_id}: 找不到音频 {mp3_path}")

        # 选择拼接路径
        if has_effects:
            # 特效路径：视频用 filter_complex（无音频），音频用 Python numpy 混合，避免 ffmpeg amix OOM
            temp_video = str(self.temp_dir / "video_only.mp4")
            self._concat_effect_path(normalized_videos, self.timeline, temp_video)

            print("[ConcatEngine] 混合音频...")
            temp_audio = self._mix_audio_python(normalized_videos, self.timeline)

            print("[ConcatEngine] 合并视频与音频...")
            cmd_merge = [
                "ffmpeg", "-y", "-v", "error",
                "-i", temp_video,
                "-i", str(temp_audio),
                "-c:v", "copy",
                "-c:a", self.config.audio_codec,
                "-b:a", self.config.audio_bitrate,
                "-shortest",
                output_video,
            ]
            subprocess.run(cmd_merge, capture_output=True, check=True)
            output = Path(output_video)
        else:
            # 快速路径
            output = self._concat_fast_path(normalized_videos, audio_wavs, output_video)

        # 如果最后不是 CTA，追加 CTA endcard
        last_entry = self.timeline[-1] if self.timeline else None
        last_is_cta = last_entry and (
            "cta" in last_entry.get("segment_id", "").lower()
            or last_entry.get("segment_type") == "cta"
        )
        if not last_is_cta:
            endcard_path = self._generate_cta_endcard()
            if endcard_path:
                print(f"[ConcatEngine] 追加 CTA endcard...")
                temp_output = str(Path(output_video).with_suffix(".tmp.mp4"))
                self.append_endcard(output_video, endcard_path, temp_output, endcard_duration=5.0)
                os.replace(temp_output, output_video)

        # 验证输出
        output_duration = self._probe_duration(output_video)
        expected_duration = sum(e["duration"] for e in self.timeline)
        print(f"[ConcatEngine] 输出完成: {output_video}")
        print(f"[ConcatEngine] 预期时长: {expected_duration:.2f}s, 实际时长: {output_duration:.2f}s, 差值: {abs(output_duration - expected_duration):.3f}s")

        # ── 可选：自动运行 harness 质检 ──
        if auto_harness or os.environ.get("MD2VIDEO_AUTO_HARNESS", "").lower() in ("1", "true", "yes"):
            try:
                from harness.harness import VideoComplianceHarness
                print("\n[ConcatEngine] 自动运行 harness 质检...")
                harness = VideoComplianceHarness()
                results = harness.run(output_video)
                if harness.has_l1_failures():
                    print("[ConcatEngine] ❌ Harness L1 检查未通过，请查看报告")
                else:
                    print("[ConcatEngine] ✅ Harness 检查通过")
            except Exception as e:
                print(f"[ConcatEngine] Harness 自动运行失败（可手动运行）: {e}")

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
