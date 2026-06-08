---
friction_points:
  - id: "f001"
    category: "素材遗漏"
    description: "s22 场景缺失，timeline 中声明了但 scenes/ 目录没有对应文件"
    resolution: "补充生成 s22 素材，或改为 animation_templates 替代方案"
    rule_id: "no_missing_scene"
    timestamp: "2026-06-06T10:00:00+08:00"
  - id: "f002"
    category: "TTS"
    description: "混用不同 session 的 edge-tts 导致 NoAudioReceived 错误"
    resolution: "全部 segment 统一 voice，禁止混用 session，串行生成"
    rule_id: "tts_voice_consistency"
    timestamp: "2026-06-06T11:00:00+08:00"
  - id: "f003"
    category: "TTS"
    description: "Markdown 分隔符 --- 被 edge-tts 误解析，导致语音合成失败"
    resolution: "文本预处理：replace('---', '—').replace('~', '约')"
    rule_id: "tts_text_sanitization"
    timestamp: "2026-06-06T11:30:00+08:00"
  - id: "f004"
    category: "音画同步"
    description: "即梦默认5s视频 vs 中文TTS 15-37s旁白，视频严重不足"
    resolution: "-stream_loop -1 循环填充 + audio_durations.json 更新 timeline duration"
    rule_id: "audio_video_sync"
    timestamp: "2026-06-06T14:00:00+08:00"
  - id: "f005"
    category: "视觉细节"
    description: "文字对比度不足、emoji 渲染为方块、字体回退到系统默认"
    resolution: "使用 Hiragino Sans GB，禁用不兼容 emoji，对比度 >= 4.5"
    rule_id: "text_contrast"
    timestamp: "2026-06-06T15:00:00+08:00"
  - id: "f006"
    category: "动画语义同步"
    description: "animation 模板视频只有5s且与语义无关，duration 参数未传入"
    resolution: "12个 animation shots 按语义重渲染，时长匹配音频"
    rule_id: "animation_semantic_sync"
    timestamp: "2026-06-06T16:00:00+08:00"
  - id: "f007"
    category: "TTS"
    description: "49段TTS批次间 voice 不一致，原始pipeline与手动补发使用不同 session"
    resolution: "全部49段串行重生成，voice=zh-CN-XiaoxiaoNeural"
    rule_id: "tts_voice_consistency"
    timestamp: "2026-06-06T17:00:00+08:00"
  - id: "f008"
    category: "即梦素材"
    description: "标准化阶段用 -an 去掉了即梦原始音频，丢失背景音"
    resolution: "即梦素材标准化禁止 -an，保留音频流，后续提取混入"
    rule_id: "jimeng_background_audio"
    timestamp: "2026-06-06T18:00:00+08:00"
  - id: "f009"
    category: "音频混音"
    description: "即梦背景音频几乎听不见，mean -43.7dB vs 旁白 -19.7dB"
    resolution: "仅 loudnorm 标准化，amix 旁白转立体声44100Hz，背景比例35%"
    rule_id: "bg_audio_level"
    timestamp: "2026-06-06T19:00:00+08:00"
  - id: "f010"
    category: "动画时序"
    description: "quote_card 前25%时间文字不可见，bullet_list 逐行出现太慢"
    resolution: "fade_in_end=3%, quote_end=20%; bullet_list 前15%时间全部出现"
    rule_id: "animation_text_timing"
    timestamp: "2026-06-06T20:00:00+08:00"
  - id: "f011"
    category: "内容质量"
    description: "13个 segment 文本为英文，TTS 读出英文解说"
    resolution: "基于原文手动翻译13个英文片段，重新生成 TTS"
    rule_id: "language_check"
    timestamp: "2026-06-06T21:00:00+08:00"
  - id: "f012"
    category: "内容质量"
    description: "s49 文本包含错误日期 2023 年，与原文时间线矛盾"
    resolution: "删除错误日期，替换为语义连贯的中文过渡句"
    rule_id: "content_accuracy"
    timestamp: "2026-06-06T22:00:00+08:00"
  - id: "f013"
    category: "素材积压"
    description: "s38/s48 即梦素材 querying >5min，pipeline 阻塞"
    resolution: "超时自动降级为 animation_templates 替代方案"
    rule_id: "jimeng_timeout_fallback"
    timestamp: "2026-06-06T23:00:00+08:00"
  - id: "f014"
    category: "音频混音"
    description: "ffmpeg acrossfade 滤镜没有 offset 参数，音频全部从0时刻混合，与视频 xfade offset 完全错位"
    resolution: "放弃 acrossfade 链式混合，改用 Python+numpy 按 start_time 精确叠加音频样本"
    rule_id: "acrossfade_no_offset"
    timestamp: "2026-06-07T19:00:00+08:00"
  - id: "f015"
    category: "音频混音"
    description: "amix=inputs=49 需要同时解码49个音频流，内存超3.9GB被系统 SIGKILL"
    resolution: "音频混合从 ffmpeg filter_complex 迁移到 Python numpy，逐段提取叠加，内存降至~70MB"
    rule_id: "amix_memory_limit"
    timestamp: "2026-06-07T19:30:00+08:00"
  - id: "f016"
    category: "音频归一化"
    description: "cmd_audio 使用 -shortest，ffmpeg 在原始音频 EOF 时立即停止，apad 来不及 pad 到目标时长"
    resolution: "移除 -shortest，用 -t 作为输出选项单独限制时长"
    rule_id: "apad_shortest_conflict"
    timestamp: "2026-06-07T18:00:00+08:00"
  - id: "f017"
    category: "时轴精度"
    description: "_normalize_video 阈值 abs(raw-target)<0.1 太宽，视频长度不精确导致 filter_complex offset 累积错位"
    resolution: "阈值收紧至 0.001s，确保所有 segment 视频/音频长度精确匹配 target_duration"
    rule_id: "duration_threshold"
    timestamp: "2026-06-07T18:30:00+08:00"
  - id: "f018"
    category: "音频混音"
    description: "TTS 混入使用 -map 1:a 完全替换原始音频，30/49 segment 的 AI 素材背景音乐丢失"
    resolution: "检测源素材音频流，有则 amix 混合（背景 volume=0.2 + TTS volume=1.0 + 总音量 0.8），无则直接替换"
    rule_id: "bg_audio_mix_logic"
    timestamp: "2026-06-07T20:00:00+08:00"
autopoiesis: true
memory_type: "living"
last_updated: "2026-06-08"
evolution_count: 5
---

# LESSONS_LEARNED — md2video 活记忆器官
> 本文档是 md2video SKILL 的「活记忆器官」。每次 pipeline 运行产生摩擦时，SelfReport 会自动更新此文档。摩擦点与 video-rules.json 中的规则通过 rule_id 形成闭环。

## 摩擦点类别：TTS

### f002
- **描述**：混用不同 session 的 edge-tts 导致 NoAudioReceived 错误
- **解决**：全部 segment 统一 voice，禁止混用 session，串行生成
- **关联规则**：`tts_voice_consistency`
- **时间**：2026-06-06T11:00:00+08:00

### f003
- **描述**：Markdown 分隔符 --- 被 edge-tts 误解析，导致语音合成失败
- **解决**：文本预处理：replace('---', '—').replace('~', '约')
- **关联规则**：`tts_text_sanitization`
- **时间**：2026-06-06T11:30:00+08:00

### f007
- **描述**：49段TTS批次间 voice 不一致，原始pipeline与手动补发使用不同 session
- **解决**：全部49段串行重生成，voice=zh-CN-XiaoxiaoNeural
- **关联规则**：`tts_voice_consistency`
- **时间**：2026-06-06T17:00:00+08:00

## 摩擦点类别：内容质量

### f011
- **描述**：13个 segment 文本为英文，TTS 读出英文解说
- **解决**：基于原文手动翻译13个英文片段，重新生成 TTS
- **关联规则**：`language_check`
- **时间**：2026-06-06T21:00:00+08:00

### f012
- **描述**：s49 文本包含错误日期 2023 年，与原文时间线矛盾
- **解决**：删除错误日期，替换为语义连贯的中文过渡句
- **关联规则**：`content_accuracy`
- **时间**：2026-06-06T22:00:00+08:00

## 摩擦点类别：动画时序

### f010
- **描述**：quote_card 前25%时间文字不可见，bullet_list 逐行出现太慢
- **解决**：fade_in_end=3%, quote_end=20%; bullet_list 前15%时间全部出现
- **关联规则**：`animation_text_timing`
- **时间**：2026-06-06T20:00:00+08:00

## 摩擦点类别：动画语义同步

### f006
- **描述**：animation 模板视频只有5s且与语义无关，duration 参数未传入
- **解决**：12个 animation shots 按语义重渲染，时长匹配音频
- **关联规则**：`animation_semantic_sync`
- **时间**：2026-06-06T16:00:00+08:00

## 摩擦点类别：即梦素材

### f008
- **描述**：标准化阶段用 -an 去掉了即梦原始音频，丢失背景音
- **解决**：即梦素材标准化禁止 -an，保留音频流，后续提取混入
- **关联规则**：`jimeng_background_audio`
- **时间**：2026-06-06T18:00:00+08:00

## 摩擦点类别：素材积压

### f013
- **描述**：s38/s48 即梦素材 querying >5min，pipeline 阻塞
- **解决**：超时自动降级为 animation_templates 替代方案
- **关联规则**：`jimeng_timeout_fallback`
- **时间**：2026-06-06T23:00:00+08:00

## 摩擦点类别：素材遗漏

### f001
- **描述**：s22 场景缺失，timeline 中声明了但 scenes/ 目录没有对应文件
- **解决**：补充生成 s22 素材，或改为 animation_templates 替代方案
- **关联规则**：`no_missing_scene`
- **时间**：2026-06-06T10:00:00+08:00

## 摩擦点类别：视觉细节

### f005
- **描述**：文字对比度不足、emoji 渲染为方块、字体回退到系统默认
- **解决**：使用 Hiragino Sans GB，禁用不兼容 emoji，对比度 >= 4.5
- **关联规则**：`text_contrast`
- **时间**：2026-06-06T15:00:00+08:00

## 摩擦点类别：音画同步

### f004
- **描述**：即梦默认5s视频 vs 中文TTS 15-37s旁白，视频严重不足
- **解决**：-stream_loop -1 循环填充 + audio_durations.json 更新 timeline duration
- **关联规则**：`audio_video_sync`
- **时间**：2026-06-06T14:00:00+08:00

## 摩擦点类别：音频混音

### f009
- **描述**：即梦背景音频几乎听不见，mean -43.7dB vs 旁白 -19.7dB
- **解决**：仅 loudnorm 标准化，amix 旁白转立体声44100Hz，背景比例35%
- **关联规则**：`bg_audio_level`
- **时间**：2026-06-06T19:00:00+08:00

---

*本文件由 harness/self_report.py 自动维护。手动修改请在 frontmatter 后添加自定义章节。*

## 摩擦点类别：音频混音（v11-v16 深度复盘）

### f014 — acrossfade 无 offset 参数
- **描述**：ffmpeg `acrossfade` 滤镜没有 `offset` 参数，链式混合时所有音频从 0 时刻开始叠加，与视频 `xfade` 的精确 offset 完全不同步。质检 48/49 失败，corr≈0
- **解决**：放弃 `acrossfade`，改用 `adelay`+`amix`，但 `amix=inputs=49` 导致 OOM。最终方案：Python+numpy 逐段提取音频样本，按 `start_time` 精确叠加到总音轨
- **关联规则**：`acrossfade_no_offset`
- **时间**：2026-06-07T19:00:00+08:00

### f015 — amix OOM
- **描述**：`amix=inputs=49:duration=longest` 需要 ffmpeg 同时解码 49 个音频流，内存峰值超 3.9GB，被系统 SIGKILL (exit code 9)
- **解决**：音频混合完全从 filter_complex 剥离，用 Python numpy 实现。每段单独 `ffmpeg -f s16le -` 提取 PCM，按 `start_time` 对齐后 `mixed[start:end] += samples`。49 段总数据量仅 ~70MB，内存安全
- **关联规则**：`amix_memory_limit`
- **时间**：2026-06-07T19:30:00+08:00

### f016 — apad 与 -shortest 冲突
- **描述**：`_normalize_video` 的 `cmd_audio` 同时用了 `apad=pad_dur={target}` 和 `-shortest`。`apad` 在音频 EOF 后开始 pad 静音，但 `-shortest` 让 ffmpeg 检测到"有效流结束"立即停止，`apad` 来不及完成
- **解决**：`cmd_audio` 移除 `-shortest`，让 `-t` 作为**输出选项**单独限制时长。`apad` pad 完成后，`-t` 在 target_duration 处截断
- **关联规则**：`apad_shortest_conflict`
- **时间**：2026-06-07T18:00:00+08:00

### f017 — 时长阈值过宽
- **描述**：`_normalize_video` 中 `abs(raw_duration - target_duration) < 0.1` 判定为"足够接近"，跳过 `trim`/`tpad`。s02 原始 15.10s vs target 15.12s，差 0.02s 被跳过，导致 filter_complex offset 累积错位
- **解决**：阈值收紧至 `0.001s`（1ms）。任何不等于 target_duration 的素材都强制 `trim` 或 `tpad` 到精确时长
- **关联规则**：`duration_threshold`
- **时间**：2026-06-07T18:30:00+08:00

### f018 — 背景音乐丢失
- **描述**：TTS 混入命令 `-map 0:v -map 1:a` 完全丢弃了原始音频。30/49 segment 的 AI 素材有背景音乐，全部被静默替换为纯 TTS
- **解决**：混入前检测源素材是否有音频流。有则 `amix` 混合（背景 `volume=0.2` + TTS `volume=1.0`，总输出 `volume=0.8` 防 clipping）；无则直接替换。质检 corr 从 1.0 降至 ~0.85，仍远高于 0.3 阈值
- **关联规则**：`bg_audio_mix_logic`
- **时间**：2026-06-07T20:00:00+08:00
