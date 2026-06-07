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
autopoiesis: true
memory_type: "living"
last_updated: "2026-06-07"
evolution_count: 0
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
