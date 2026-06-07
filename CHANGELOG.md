# Changelog

所有 notable changes 都记录在此文件。

格式遵循 [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)，
本项目遵守 [Semantic Versioning](https://semver.org/)。

## [Unreleased]

## [1.1.0] - 2026-06-07

### Added

- **Autopoiesis 自创生免疫系统**：`harness/self_report.py`
  - 自我观察：加载 system state（rules / timeline / cta_resources）
  - 摩擦点捕获：`capture_friction()` 记录异常 + 解决方案
  - 规则演化：`auto_encode()` 自动将新摩擦点编码进 `video-rules.json`（L3 自动检测项）
  - 活记忆写入：`write_lessons()` 更新 `docs/LESSONS_LEARNED.md`（YAML frontmatter + Markdown）
- **活记忆器官**：`docs/LESSONS_LEARNED.md` 升级为机器可读格式
  - YAML frontmatter：`autopoiesis: true`, `memory_type: living`, `evolution_count`, `friction_points` 列表
  - 摩擦点 ↔ 规则通过 `rule_id` 形成闭环
- **规则驱动分镜拆解**：`extensions/storyboard/storyboard_ai.py` 从硬编码升级为规则驱动
  - 加载 `rules/storyboard_rules.json` 自动推断 visual_type 和 transition
  - 新增语义段落类型：hook / narrative / data_contrast / list / date / quote / cta / transition
- **语义段落类型推断**：`core/segment_tts.py` 新增 `SegmentTypeAnalyzer`
  - 三层推断：位置规则 → 关键词规则 → 正则规则
  - 类型信息写入 `segments.json`，供下游 timeline_mapper / storyboard_ai 使用
- **自动转场推断**：`core/timeline_mapper.py` + `storyboard_ai.py`
  - 根据相邻段 `segment_type` 组合自动匹配转场效果（fade / crossfade / slideleft / wipeleft 等）
  - 从 `transitions.json` 加载配置，无需手动注入
- **3 种新动画模板**（纯 Python，零外部 API）：
  - `bullet_list`：要点列表逐行出现 + 高亮当前行
  - `calendar_highlight`：月历网格 + 指定日期脉冲高亮
  - `quote_card`：引用卡片 + 引号装饰 + 渐入效果
- **规则层**（`rules/` 目录）：
  - `segment_types.json`：语义段落类型规则定义
  - `storyboard_rules.json`：分镜拆解 + 转场推断规则定义
- **GitHub Actions CI**：`.github/workflows/ci.yml`
  - Python 语法检查（全部核心模块）
  - JSON 格式验证（rules + harness config）
  - Self report 干运行
  - LESSONS_LEARNED frontmatter 完整性检查
- **项目治理文件**：`README.md`（含 badge、架构图、完整流程）、`CONTRIBUTING.md`、`CHANGELOG.md`

### Changed

- **SKILL.md 全面升级**：新增 Autopoiesis Governance 章节（自创生四特征、演化度量指标、自检命令）
- **架构图更新**：新增 `rules/` 目录、`self_report.py`、活记忆器官说明
- **版本升级**：v1.0.0 → v1.1.0

### Fixed

- `core/segment_tts.py`：修复 `"""` 在字符串字面量中被误解析为 docstring 的 SyntaxError
- `extensions/animations/animation_templates.py`：同上
- `.gitignore`：`animations/` 改为 `/animations/`，避免误忽略 `extensions/animations/` 源代码目录

## [1.0.0] - 2026-06-06

### Added

- **核心引擎层**：
  - `segment_tts.py`：按语义边界切分长文本，独立生成 TTS，`ffprobe` 精确测时长
  - `timeline_mapper.py`：程序化 timeline 生成，三方一致性校验（segments↔prompts↔scenes）
  - `concat_engine.py`：精确时轴拼接，支持 `-c copy` 快速路径和 `filter_complex` 特效路径
  - `frame_extractor.py`：抽帧检查（黑帧/文字重叠/emoji 方块）
  - `cta_resource.py`：二维码生成/注册/校验/合成
- **质检体系**：`harness.py` + `video-rules.json`
  - L1 硬阻塞（6 项）：三方一致性、placeholder=0、计算一致性、音频存在性、timeline 完整性、无遗漏场景
  - L2 警告（5 项）：音画差值、分辨率匹配、帧率方差、字体回退、段落时长合理性
  - L3 模式检查（8 项）：箭头方向、颜色语义、emoji 兼容性、CTA 卡片、二维码完整性、文字对比度、运动一致性、转场有效性
- **扩展模板层**：
  - `animation_templates.py`：6 种纯 Python 动画（animated_text、bar_chart、pie_chart、trend_line、comparison_split、table_scroll）
  - `storyboard_ai.py`：文章→分镜拆解器，输出 shots.json / prompts.json / segments_hint.json
  - `prompt_templates`：即梦 prompt 模板 + 预算控制
- **CTA 资源治理**：`cta_resources.json` 注册表，harness L3 检查 `qrcode_integrity`
- **文档**：`SKILL.md`（完整 Skill 文档）、`LESSONS_LEARNED.md`（初始复盘）

[Unreleased]: https://github.com/leether/md2video/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/leether/md2video/releases/tag/v1.1.0
[1.0.0]: https://github.com/leether/md2video/releases/tag/v1.0.0
