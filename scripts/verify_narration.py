#!/usr/bin/env python3
"""
旁白音频质检脚本 —— 验证最终视频中每个 segment 的音频是否与原始 TTS 一致

原理：从最终视频中提取每个 segment 对应时间段的音频，与原始 TTS mp3 计算
小延迟窗口内的最大绝对皮尔逊相关系数。如果相关系数 > 0.3，认为是同一音频（旁白正确混入）。

用法：
    python scripts/verify_narration.py output/final.mp4 output/timeline.json output/narration_segments
"""

import json
import sys
import subprocess
import tempfile
from pathlib import Path
import numpy as np


def extract_audio(video_path: str, start: float, duration: float, output_wav: str):
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-ss", str(start), "-t", str(duration),
        "-i", video_path,
        "-vn", "-ar", "48000", "-ac", "1",
        "-c:a", "pcm_s16le",
        output_wav,
    ]
    subprocess.run(cmd, capture_output=True, check=True)


def load_mono_wav(path: str) -> np.ndarray:
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-i", path,
        "-ar", "48000", "-ac", "1",
        "-c:a", "pcm_s16le",
        "-f", "s16le", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, check=True)
    return np.frombuffer(result.stdout, dtype=np.int16).astype(np.float32)


def _pearson_corr_aligned(a: np.ndarray, b: np.ndarray) -> float:
    min_len = min(len(a), len(b))
    a = a[:min_len]
    b = b[:min_len]
    a = a - np.mean(a)
    b = b - np.mean(b)
    denom = np.sqrt(np.sum(a**2)) * np.sqrt(np.sum(b**2))
    if denom == 0:
        return 0.0
    return float(np.sum(a * b) / denom)


def pearson_corr(a: np.ndarray, b: np.ndarray, max_lag_seconds: float = 0.08, sample_rate: int = 48000) -> float:
    """Return max absolute correlation, allowing small codec delay offsets."""
    max_lag = int(max_lag_seconds * sample_rate)
    step = max(1, sample_rate // 200)  # 5ms
    best = 0.0

    for lag in range(-max_lag, max_lag + 1, step):
        if lag < 0:
            corr = _pearson_corr_aligned(a[:lag], b[-lag:])
        elif lag > 0:
            corr = _pearson_corr_aligned(a[lag:], b[:-lag])
        else:
            corr = _pearson_corr_aligned(a, b)
        best = max(best, abs(corr))

    return best


def verify(video_path: str, timeline_path: str, audio_dir: str, threshold: float = 0.30):
    with open(timeline_path, "r", encoding="utf-8") as f:
        timeline = json.load(f).get("entries", [])

    # 同步 concat_engine 的 CTA 去重逻辑
    cta_indices = [i for i, e in enumerate(timeline) if "cta" in e.get("segment_id", "").lower() or e.get("segment_type") == "cta"]
    if len(cta_indices) > 1:
        print(f"[质检] 检测到 {len(cta_indices)} 个 CTA，同步去重...")
        for i in cta_indices[:-1]:
            timeline[i]["segment_type"] = "narrative"
    if cta_indices:
        last = timeline[-1]
        last_is_cta = "cta" in last.get("segment_id", "").lower() or last.get("segment_type") == "cta"
        if not last_is_cta:
            last_cta_idx = cta_indices[-1]
            cta_entry = timeline.pop(last_cta_idx)
            timeline.append(cta_entry)
            print(f"[质检] 将 {cta_entry['segment_id']} 移到末尾")

    # 同步 concat_engine 的 start_time 计算（与 filter_complex offset 一致）
    cum_time = 0.0
    for entry in timeline:
        entry["start_time"] = cum_time
        trans = entry.get("transition")
        if trans:
            cum_time += entry["duration"] - trans.get("duration", 0.0)
        else:
            cum_time += entry["duration"]
        entry["end_time"] = cum_time

    passed = 0
    failed = 0
    fail_details = []

    print(f"[质检] 视频: {video_path}")
    print(f"[质检] 共 {len(timeline)} 个 segment，阈值: {threshold}")
    print()

    for entry in timeline:
        seg_id = entry["segment_id"]
        start = entry.get("start_time", 0.0)
        duration = entry["duration"]

        mp3_path = Path(audio_dir) / f"{seg_id}.mp3"
        if not mp3_path.exists():
            print(f"⚠️  {seg_id}: 找不到音频 {mp3_path}")
            continue

        with tempfile.TemporaryDirectory() as tmpdir:
            video_wav = Path(tmpdir) / "v.wav"
            extract_audio(video_path, start, duration, str(video_wav))
            v_samples = load_mono_wav(str(video_wav))
            tts_samples = load_mono_wav(str(mp3_path))

            corr = pearson_corr(v_samples, tts_samples)
            status = "PASS" if corr > threshold else "FAIL"

            if status == "PASS":
                passed += 1
            else:
                failed += 1
                fail_details.append((seg_id, corr))

            marker = "✅" if status == "PASS" else "❌"
            print(f"{marker} {seg_id}: corr={corr:.3f} ({status})")

    total = passed + failed
    print()
    print(f"{'='*50}")
    print(f"通过: {passed}/{total}")
    print(f"失败: {failed}/{total}")
    if fail_details:
        print("\n失败项:")
        for seg_id, corr in fail_details:
            print(f"  ❌ {seg_id}: corr={corr:.3f}")
    print(f"{'='*50}")

    if failed > 0:
        print("\n[质检] ❌ 未通过 —— 旁白音频混入存在问题")
        sys.exit(1)
    else:
        print("\n[质检] ✅ 全部通过 —— 旁白音频正确混入")
        sys.exit(0)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python verify_narration.py <final.mp4> <timeline.json> <audio_dir>")
        sys.exit(1)
    verify(sys.argv[1], sys.argv[2], sys.argv[3])
