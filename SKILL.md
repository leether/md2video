# md2video — Markdown/文章 → 短视频生成 SKILL

将 Markdown 文章或纯文本自动转换为带旁白的短视频。支持即梦 AI 素材 + Python 数据动画，内置分段 TTS、精确时轴拼接、分层级质检体系。

## 触发条件

当用户意图为以下任一形式时触发：
- "把这篇文章转成视频"
- "生成短视频"
- "Markdown 转视频"
- "给这篇文章做分镜"
- "文章→视频"
- 提供一段文字/文章并要求"做成视频"

## 架构

```
md2video/
├── core/                    # 核心引擎层（必须）
│   ├── segment_tts.py       # 分段 TTS + 语义类型推断 + 精确测时长
│   ├── timeline_mapper.py   # 程序化 timeline + Clip模型(fade/transition自动推断)
│   ├── concat_engine.py     # 精确时轴拼接（快速路径 + filter_complex特效路径）
│   ├── frame_extractor.py   # 抽帧检查（黑帧/方块/重叠）
│   └── cta_resource.py      # CTA 二维码资源治理
├── harness/                 # 质检体系 + 自创生免疫系统（必须）
│   ├── harness.py           # L1/L2/L3 分层合规检查
│   ├── self_report.py       # Autopoiesis 自检自报告 + 规则演化
│   └── video-rules.json     # 规则定义（可被 self_report 自动扩展）
├── rules/                   # 规则层（可被运行时加载和演化）
│   ├── segment_types.json   # 语义段落类型规则
│   └── storyboard_rules.json # 分镜拆解 + 转场推断规则
├── extensions/              # 扩展模板层（可选）
│   ├── animations/          # Python 动画模板（9种，纯代码无API依赖）
│   ├── prompt_templates/    # 即梦 prompt 模板 + 预算控制
│   └── storyboard/          # 文章→分镜 AI 拆解器（规则驱动）
├── examples/                # 示例
│   ├── example_article.md
│   └── example_pipeline.py
└── docs/
    └── LESSONS_LEARNED.md   # 活记忆器官（YAML frontmatter + 机器可读）
```

## 快速开始

### 1. 安装依赖

```bash
# Python 依赖
uv pip install edge-tts Pillow imageio numpy scipy

# 系统依赖
brew install ffmpeg

# 即梦 CLI（用于生成 AI 素材）
pip install jimeng
```

### 2. 准备文章

创建 `article.md`：

```markdown
价格翻倍！即梦新用户成本暴涨，老用户笑了

去年2月19日，我用即梦生成一个5秒视频只需要3.59积分。现在新用户同样的视频要花10积分以上。

我把我的老用户特权梳理了一下...
```

### 3. 一键生成

```python
from extensions.storyboard.storyboard_ai import storyboard_from_article
from core.segment_tts import SegmentedTTSGenerator
from core.timeline_mapper import TimelineMapper
from core.concat_engine import ConcatEngine
from core.cta_resource import generate_qr_cta
from harness.harness import VideoComplianceHarness
import asyncio

# Step 1: 文章 → 分镜 + pipeline 输入
storyboard_from_article(open("article.md").read())

# Step 2: 分段 TTS（精确测时长）
gen = SegmentedTTSGenerator()
gen.split_by_semantic("", scene_hints=...)  # 从 segments_hint.json 加载
asyncio.run(gen.generate_all())
gen.save_manifest()

# Step 3: 生成素材（即梦 CLI + Python 动画）
# 手动运行: jimeng video generate ... --output scenes/

# Step 3b: 生成 CTA 二维码结尾卡片
generate_qr_cta(
    target_url="https://www.douyin.com/user/xxx",
    target_platform="douyin",
    target_account="即梦省钱攻略",
    output_video="rebuild_animations/cta_endcard.mp4",
)

# Step 4: 构建 timeline（自动三方对齐）
mapper = TimelineMapper()
mapper.run()

# Step 5: 拼接最终视频
engine = ConcatEngine()
engine.concat()

# Step 5b: 追加 CTA 结尾
engine.append_endcard(
    input_video="output/final.mp4",
    endcard_path="rebuild_animations/cta_endcard.mp4",
    output_video="output/final_with_cta.mp4",
    endcard_duration=8.0,
)

# Step 6: 抽帧检查
from core.frame_extractor import FrameExtractor
extractor = FrameExtractor()
extractor.extract_and_check("output/final_with_cta.mp4")
extractor.generate_report()

# Step 7: 合规检查
harness = VideoComplianceHarness()
harness.run("output/final_with_cta.mp4")
```

完整 pipeline 示例见 `examples/example_pipeline.py`。

## Pipeline 详解

### 数据流

```
article.md
    ↓
storyboard_ai → shots.json + segments_hint.json + prompts.json
    ↓
segment_tts → segments.json（精确时长）
    ↓
jimeng CLI / animation_templates → scenes/ + rebuild_animations/
    ↓
timeline_mapper → timeline.json（三方一致性校验）
    ↓
concat_engine → final.mp4
    ↓
frame_extractor → 抽帧报告
    ↓
harness → compliance_report.json
```

### 关键设计

| 组件 | 核心原则 |
|------|---------|
| `segment_tts` | 按语义切分，独立生成，ffprobe 精确测时长 |
| `timeline_mapper` | Single Source of Truth，程序化对齐，L1 硬阻塞校验，Clip 模型支持 fade/transition |
| `concat_engine` | **双路径策略**：无特效→`-c copy` 快速路径；有特效→filter_complex (xfade+acrossfade) |
| `frame_extractor` | "不要在脑子里检查"，必须回读 PNG 帧 |
| `harness` | 自动触发，逐项核查，L1 失败阻断 |
| `bg_audio_mixer` | 即梦素材提取背景音→loudnorm标准化→循环填充→amix混入（旁白立体声化，背景≤35%） |
| `animation_timing` | 动画文字必须在视频开始后5%时间内出现，禁止长 fade-in 让观众干等 |

## 质检体系（三层）

直接继承并适配 `skill-compliance-harness` 机制：

### L1 硬阻塞（必须全部通过）

任何一项失败 → `final.mp4` 不得标记为完成

| 检查项 | 说明 |
|--------|------|
| 三方一致性 | segments/prompts/scenes 完全对齐 |
| Placeholder 检测 | 无黑帧/纯色帧/渲染失败 |
| 计算一致性 | 所有数值已与数据源核对 |
| 音频存在性 | final.mp4 包含音频流 |
| Timeline 完整性 | 每个 segment 素材+音频均存在 |
| 无遗漏场景 | prompts 中所有 scene 都出现在 final.mp4 |
| 无重复场景 | timeline 中无重复 segment_id |

### L2 警告（失败输出警告，不阻断）

| 检查项 | 阈值 |
|--------|------|
| 音画时长差值 | ≤ 2.0s |
| 分辨率匹配 | 1080×1920 |
| 帧率方差 | 30fps ± 1 |
| 段落时长合理性 | 2-15s |
| 背景音频音量 | 与旁白差距 ≤ 10dB（mean_volume 对比） |
| 动画文字延迟 | 文字在开始后 ≤ 5% 时间内必须可见 |
| 即梦背景音频混入 | 提取即梦原音 → loudnorm → 循环填充 → amix（≤35%） |

### L3 模式检查（人工确认清单）

| 检查项 | 方式 |
|--------|------|
| 箭头方向语义 | 人工 |
| 颜色语义 | 人工 |
| Emoji 兼容性 | 自动 + 人工 |
| CTA 卡片存在性 | 人工 |
| 二维码完整性 | 自动 |
| 二维码 URL 一致性 | 人工 |
| 文字对比度 | 自动 |
| 运动一致性 | 人工 |
| 转场有效性 | 自动 |
| 淡入淡出时长有效性 | 自动 |
| TTS 文本预处理 | 自动（--- 替换为 —，~ 替换为 约） |
| 即梦素材超时降级 | 人工（querying>5min 自动切 animation） |
| 内容事实准确性 | 人工（日期/数字回源核对） |

## 扩展模板

### 动画模板

内置模板（`extensions/animation_templates/base.py`）：
- `price_contrast`: 价格对比（左右对比 + 箭头）
- `table`: 表格数据展示（逐行淡入）

**文字出现时序硬规约（避免观众干等）：**
- `quote_card`: `fade_in_end ≤ total_frames × 0.05`，`quote_end ≤ total_frames × 0.25`
- `bullet_list`: 全部文字在 `total_frames × 0.15` 内出现完毕
- `bar_chart`/`trend_line`: 数据标签第1帧即显示，柱子/折线快速生长
- 通用原则：文字内容必须在解说开始后 0.5s 内可见

自定义模板：继承 `AnimationTemplate`，实现 `render()` 方法。

### Prompt 模板

内置模板（`extensions/prompt_templates/base.py`）：
- `hook_text`: 3D 文字 hook
- `person_talking`: 人物讲述
- `product_showcase`: 产品展示
- `data_visualization`: 数据可视化
- `calendar_highlight`: 日历高亮
- `before_after_split`: 前后对比
- `cta_endcard`: CTA 结尾卡片

支持预算控制：`PromptTemplateLibrary(budget_limit=500)`

### 分镜拆解

```python
from extensions.storyboard.storyboard_ai import storyboard_from_article

storyboard_from_article(
    article_text="...",
    chars_per_second=4.5,  # 中文字符/秒
)
# 输出: shots.json + segments_hint.json + prompts.json
```

自动识别：
- 第一段 → hook
- 含 CTA 关键词的最后一段 → endcard
- 含数据/价格/日期关键词 → animation / 对应模板

## 关键原则

1. **Single Source of Truth**：segments.json 是时长唯一源，timeline.json 是映射唯一源，cta_resources.json 是二维码唯一注册表
2. **不要在脑子里检查**：所有检查必须回读真实文件，输出逐条勾选报告
3. **音频拼接唯一可靠路径**：mp3 → wav → concat → m4a
4. **禁止使用 emoji**：使用 ASCII 替代（! / X / √）或 Pillow 矢量图形
5. **预算控制**：即梦素材消耗积分，内置 `budget_limit` 和重试限制
6. **二维码资源治理**：CTA 二维码必须注册到 cta_resources.json，生成即校验，URL 与主题一致
7. **双路径拼接**：concat_engine 自动选择 `-c copy` 快速路径或 `filter_complex` 特效路径，确保质量与性能的平衡

## 文件规范

### segments.json

```json
{
  "generator": "md2video.segment_tts",
  "voice": "zh-CN-XiaoxiaoNeural",
  "segments": [
    {"id": "s01_hook", "text": "...", "duration": 4.01, "audio_path": "..."}
  ],
  "total_duration": 118.2
}
```

### timeline.json

```json
{
  "generator": "md2video.timeline_mapper",
  "entries": [
    {
      "segment_id": "s01_hook",
      "duration": 4.01,
      "media_path": "scenes/s01_hook.mp4",
      "start_time": 0.0,
      "end_time": 4.01
    }
  ],
  "validation": {"errors": [], "warnings": []}
}
```

### prompts.json

```json
[
  {
    "id": "s01_hook",
    "text": "Cinematic shot, bold Chinese text...",
    "model": "seedance2.0fast_vip",
    "aspect_ratio": "9:16",
    "duration": 5
  }
]
```

## 依赖

- Python 3.10+
- ffmpeg（Homebrew: `brew install ffmpeg`）
- edge-tts
- Pillow
- imageio
- numpy
- scipy（可选，用于 frame_extractor 边缘检测）
- jimeng CLI（可选，用于 AI 素材生成）

## 活记忆运行时加载

`harness/memory_loader.py` 是系统的「免疫系统记忆」。pipeline 启动时自动加载 `docs/LESSONS_LEARNED.md`，打印历史摩擦风险提示：

```
━━━ 🧠 活记忆风险提示 ━━━
已加载 13 条历史摩擦点，最近高摩擦类别：TTS、内容质量、动画时序

  ⚡ [f007] TTS: 49段TTS批次间 voice 不一致...
     → 全部49段串行重生成，voice=zh-CN-XiaoxiaoNeural
━━━━━━━━━━━━━━━━━━━━━━━━
```

- 同样的坑不反复踩：运行时感知历史教训
- 高摩擦类别自动附加到 L3 人工确认清单
- 纯 Python 实现，无 PyYAML 依赖

## Harness 自动运行

`ConcatEngine` 支持拼接完成后自动运行 harness 质检：

```python
engine = ConcatEngine()
engine.concat(
    timeline_path="output/timeline.json",
    auto_harness=True,  # ← 启用自动质检
)
```

或通过环境变量启用：

```bash
export MD2VIDEO_AUTO_HARNESS=1
python your_pipeline.py
```

自动 harness 在拼接完成后立即运行，L1 失败会在控制台打印 ❌，但不阻断返回（报告保存到 `output/compliance_report.json`）。

## 已知限制

1. 即梦素材需要手动调用 `jimeng` CLI 生成（当前未封装自动调用）
2. frame_extractor 的文字重叠检测依赖 pytesseract（可选）
3. L3 模式检查中的箭头方向、颜色语义、内容事实准确性需要人工确认
4. 中文字体硬编码为 Hiragino Sans GB（macOS），其他平台需修改
5. **背景音频提取**：即梦素材标准化时须保留原音频流，单独提取后混入，禁止 `-an` 直接丢弃
6. **TTS voice 一致性**：全部 segment 必须用同一 voice 生成，禁止混用不同 session 的音频
7. **TTS 文本预处理**：Markdown 分隔符 `---` 和 `~` 会导致 edge-tts 失败，必须在生成前替换

## Autopoiesis Governance

md2video 是一个**自创生系统（autopoietic system）**。它的边界不是由外部定义的「功能清单」划定，而是由自我生产的操作网络划定：

```
storyboard_ai → segment_tts → timeline_mapper → concat_engine → harness
                                                     ↑________________________|
                                                              (feedback loop)
```

### 自创生的四个特征

1. **边界由自我生产定义**
   - 系统的存在不依赖外部指令。即使没有用户输入，SelfReport 也能通过 `--dry-run` 观察自身状态并输出报告。
   - `segment_tts.py` 的语义类型推断、timeline_mapper 的自动转场、storyboard_ai 的规则驱动——这些都是系统内部操作自然长出的能力，不是外部强加的功能。

2. **结构耦合（从环境刺激中学习）**
   - 环境 = Markdown 文章的语义模式、ffmpeg 的行为、即梦 API 的响应。
   - 当环境产生「摩擦」（如素材遗漏、音画错位），SelfReport 捕获摩擦点并编码进 `video-rules.json`。
   - 规则不是静态的：每次运行都可能产生新的 L3 检查项。

3. **升级是自我分化的自然结果**
   - v1.0 → v1.1 的升级不是「需求文档驱动的重构」，而是系统在使用中自我分化的产物：
     - Clip-based Timeline 从 concat_engine 的双路径策略中自然长出
     - 规则驱动的 storyboard 从「发现新的语义模式时不想改代码」的需求中长出
     - 9 个 animation_templates 从「降低外部 API 依赖」的自维持需求中长出

4. **演化度量：环境变化时的自我维持能力**
   - 指标 1：新增一种语义段落类型时，需要改几行代码？（目标：0 行，只改 JSON 规则）
   - 指标 2：发现新摩擦点时，规则自动演化的延迟？（目标：1 次 `self_report.py` 运行）
   - 指标 3：外部 API（即梦）不可用时，系统能否继续产出视频？（目标：能，通过 animation_templates）

### 自检命令

```bash
# 完整自检 + 规则演化 + 活记忆更新
python harness/self_report.py

# 捕获一个摩擦点并触发演化
python harness/self_report.py --capture "素材遗漏" "s22 场景缺失" "补充生成 s22 素材"
```

### 活记忆器官

`docs/LESSONS_LEARNED.md` 不是静态文档。它包含：
- **YAML frontmatter**：机器可读的摩擦点列表、evolution_count、时间戳
- **Markdown 正文**：人类可读的复盘和架构启示
- **闭环**：每个摩擦点的 `rule_id` 指向 `video-rules.json` 中的对应项

## 版本

v1.2.0 — 自创生系统完整迁移：活记忆运行时加载（memory_loader）、摩擦点→规则演化闭环（self_report）、L3 规则扩展（v5 实战教训编码）、Harness 自动运行
