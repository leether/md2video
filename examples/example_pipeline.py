#!/usr/bin/env python3
"""
完整 Pipeline 示例：从文章到最终视频

数据流：
    1. article.md → storyboard_ai → shots.json + segments_hint.json + prompts.json
    2. segments_hint.json → segment_tts → segments.json（含精确时长）
    3. prompts.json → 即梦 CLI / 动画模板 → scenes/ 目录
    4. segments.json + prompts.json + scenes/ → timeline_mapper → timeline.json
    5. timeline.json + scenes/ + narration_segments/ → concat_engine → final.mp4
    6. final.mp4 → frame_extractor → 抽帧报告
    7. final.mp4 + 所有产物 → harness → 合规报告

运行前准备：
    - 安装依赖: uv pip install edge-tts Pillow imageio numpy
    - 安装 ffmpeg: brew install ffmpeg
    - 安装即梦 CLI: pip install jimeng
    - 确保中文字体存在: /System/Library/Fonts/Hiragino Sans GB.ttc
"""

import asyncio
import sys
from pathlib import Path

# 将仓库根目录加入路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.segment_tts import SegmentedTTSGenerator
from core.timeline_mapper import TimelineMapper
from core.concat_engine import ConcatEngine
from core.frame_extractor import FrameExtractor
from core.cta_resource import generate_qr_cta, CTAResourceManager
from harness.harness import VideoComplianceHarness
from extensions.storyboard.storyboard_ai import storyboard_from_article
from extensions.animation_templates.base import render_animation
from extensions.prompt_templates.base import PromptTemplateLibrary


def step1_storyboard(article_path: str = "examples/example_article.md"):
    """步骤1：文章 → 分镜"""
    print("=" * 60)
    print("Step 1: 文章 → 分镜")
    print("=" * 60)

    with open(article_path, "r", encoding="utf-8") as f:
        article = f.read()

    shots_path = storyboard_from_article(article, output_dir=".")
    print(f"✅ 分镜已保存: {shots_path}")
    print(f"   segments_hint.json 和 prompts.json 已生成")
    return shots_path


def step2_generate_tts():
    """步骤2：生成分段TTS"""
    print("\n" + "=" * 60)
    print("Step 2: 生成分段 TTS")
    print("=" * 60)

    import json
    with open("segments_hint.json", "r", encoding="utf-8") as f:
        hints = json.load(f)

    gen = SegmentedTTSGenerator(output_dir="output")
    gen.split_by_semantic("", scene_hints=hints)
    asyncio.run(gen.generate_all(progress_callback=lambda sid, dur: print(f"  {sid}: {dur:.2f}s")))
    manifest = gen.save_manifest()
    print(f"✅ TTS 已保存: {manifest}")
    return manifest


def step3_generate_scenes(budget_limit: int = 500):
    """步骤3：生成素材（即梦 + Python动画 + CTA二维码）"""
    print("\n" + "=" * 60)
    print("Step 3: 生成素材")
    print("=" * 60)

    import json
    from pathlib import Path

    Path("scenes").mkdir(exist_ok=True)
    Path("rebuild_animations").mkdir(exist_ok=True)

    with open("prompts.json", "r", encoding="utf-8") as f:
        prompts = json.load(f)

    lib = PromptTemplateLibrary(budget_limit=budget_limit)

    for p in prompts:
        if p.get("source") == "python_animation":
            # Python 动画
            anim_type = p.get("animation_type", "price_contrast")
            output_path = f"rebuild_animations/{p['id']}.mp4"
            print(f"  生成动画: {p['id']} -> {output_path}")
            try:
                render_animation(anim_type, p.get("vars", {}), output_path)
            except Exception as e:
                print(f"  ⚠️ 动画生成失败: {e}")
        else:
            # 即梦素材（这里只是生成 prompt，实际调用需要 jimeng CLI）
            print(f"  即梦 prompt: {p['id']}")
            lib.add_custom(type('obj', (object,), {
                'id': p['id'],
                'text': p.get('text', p.get('prompt', '')),
                'model': 'seedance2.0fast_vip',
                'aspect_ratio': '9:16',
                'duration': 5,
                'negative_prompt': '',
                'notes': p.get('notes', ''),
                'retry_budget': 3,
            })())

    # 生成 CTA 二维码结尾卡片
    print("\n  生成 CTA 二维码...")
    try:
        cta_path = generate_qr_cta(
            target_url="https://www.douyin.com/user/xxx",  # 替换为实际 URL
            target_platform="douyin",
            target_account="即梦省钱攻略",
            output_video="rebuild_animations/cta_endcard.mp4",
        )
        print(f"  ✅ CTA 二维码已生成: {cta_path}")
    except Exception as e:
        print(f"  ⚠️ CTA 二维码生成失败: {e}")
        print("     请安装依赖: uv pip install qrcode[pil]")

    print("✅ 素材生成完成")
    print("   即梦素材请手动运行: jimeng video generate --prompt '...' --output scenes/")
    return True


def step4_build_timeline():
    """步骤4：构建 timeline"""
    print("\n" + "=" * 60)
    print("Step 4: 构建 Timeline")
    print("=" * 60)

    mapper = TimelineMapper(output_dir="output", scenes_dir="scenes", prompts_file="prompts.json")
    timeline_path, errors, warnings = mapper.run()

    if errors:
        print(f"❌ L1 错误: {errors}")
        return None

    if warnings:
        print(f"⚠️ 警告: {warnings}")

    print(f"✅ Timeline 已保存: {timeline_path}")
    return timeline_path


def step5_concat():
    """步骤5：拼接最终视频"""
    print("\n" + "=" * 60)
    print("Step 5: 拼接最终视频")
    print("=" * 60)

    engine = ConcatEngine()
    output = engine.concat(
        timeline_path="output/timeline.json",
        segments_audio_dir="output/narration_segments",
        output_video="output/final.mp4",
    )

    # 追加 CTA（如果存在）
    cta_candidates = [
        "rebuild_animations/cta_endcard.mp4",
        "rebuild_animations/a_endcard.mp4",
    ]
    cta_path = None
    for c in cta_candidates:
        if Path(c).exists():
            cta_path = c
            break

    if cta_path:
        print(f"  追加 CTA 结尾: {cta_path}")
        output = engine.append_endcard(
            input_video=str(output),
            endcard_path=cta_path,
            output_video="output/final_with_cta.mp4",
            endcard_duration=8.0,
        )
    else:
        print("  ⚠️ 未找到 CTA 结尾卡片")

    print(f"✅ 最终视频: {output}")
    return output


def step6_frame_check():
    """步骤6：抽帧检查"""
    print("\n" + "=" * 60)
    print("Step 6: 抽帧检查")
    print("=" * 60)

    extractor = FrameExtractor()
    extractor.extract_and_check("output/final.mp4", "output/timeline.json")
    report = extractor.generate_report()
    print(f"✅ 抽帧报告: {report}")
    return report


def step7_compliance():
    """步骤7：合规检查"""
    print("\n" + "=" * 60)
    print("Step 7: 合规检查")
    print("=" * 60)

    harness = VideoComplianceHarness()
    results = harness.run("output/final.mp4")

    if harness.has_l1_failures():
        print("❌ L1 检查失败，流程阻断")
        return False

    if harness.has_l2_warnings():
        print("⚠️ L2 警告存在，请检查")

    print("✅ 合规检查通过")
    return True


def run_full_pipeline():
    """执行完整 pipeline"""
    step1_storyboard()
    step2_generate_tts()
    step3_generate_scenes()
    step4_build_timeline()
    step5_concat()
    step6_frame_check()
    step7_compliance()
    print("\n" + "=" * 60)
    print("Pipeline 完成！")
    print("=" * 60)


if __name__ == "__main__":
    run_full_pipeline()
