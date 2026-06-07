# 贡献指南

感谢你对 md2video 的关注！以下是如何参与贡献的说明。

## 快速开始

```bash
git clone https://github.com/leether/md2video.git
cd md2video
uv pip install -r requirements.txt
brew install ffmpeg
```

## 如何贡献

### 报告问题

- 在 [Issues](../../issues) 中搜索是否已有相同问题
- 新建 Issue，包含：复现步骤、期望行为、实际行为、Python 版本、ffmpeg 版本
- 渲染相关的问题，请附上 **原始 Markdown** 和 **最终视频截图**

### 提交代码

1. Fork 本仓库
2. 创建分支：`git checkout -b feat/your-feature` 或 `fix/your-fix`
3. 提交变更：`git commit -m "feat: 简短描述"`
4. 推送分支：`git push origin feat/your-feature`
5. 创建 Pull Request

### 提交规范

使用 [Conventional Commits](https://www.conventionalcommits.org/) 格式：

```
feat: 新增 bullet_list 动画模板
fix: 修复 filter_complex 音频流缺失导致拼接失败
refactor: 将 timeline_mapper 升级为 Clip-based 模型
docs: 补充 Autopoiesis Governance 说明
chore: 更新 requirements.txt
ci: 新增 GitHub Actions 工作流
```

## 开发须知

### 新增动画模板

在 `extensions/animations/animation_templates.py` 中：

1. 添加 `render_xxx()` 方法（纯 Python + Pillow，零外部 API）
2. 在 `render_by_type()` 路由表中注册
3. 更新 `SKILL.md` 和 `README.md` 的模板列表
4. 确保 `py_compile` 通过

### 新增语义类型

**不需要改代码！** 只需更新规则文件：

1. `rules/segment_types.json`：添加 keyword_rules 或 pattern_rules
2. `rules/storyboard_rules.json`：添加 segment_type_mapping 和 transition_rules
3. 运行 `python harness/self_report.py` 验证规则加载正常

### 新增质检规则

1. 在 `harness/video-rules.json` 的对应层级（l1/l2/l3）添加规则定义
2. 如需要自动检测，在 `harness/harness.py` 中实现 check_fn
3. 运行 `python harness/self_report.py --capture "类别" "描述" "解决"` 将摩擦点编码为规则

### 测试

本地验证：

```bash
# Python 语法检查
python -m py_compile core/*.py extensions/*/*.py harness/*.py

# JSON 格式验证
python -c "import json; json.load(open('harness/video-rules.json'))"
python -c "import json; json.load(open('rules/segment_types.json'))"
python -c "import json; json.load(open('rules/storyboard_rules.json'))"

# Self report 干运行
python harness/self_report.py

# 运行 CI 全量检查
python -m py_compile core/segment_tts.py core/timeline_mapper.py \
  core/concat_engine.py core/cta_resource.py core/frame_extractor.py \
  harness/self_report.py harness/harness.py \
  extensions/storyboard/storyboard_ai.py \
  extensions/animations/animation_templates.py
```

### 隐私门禁（硬门禁，提交前必过）

项目有两道防线：

| 防线 | 触发点 | 方式 |
|------|--------|------|
| **GitHub Actions** | push/PR 到 main | 服务端硬门禁，无法绕过 |
| **本地检查** | `git push` 前手动运行 | 开发者自律 |

**P0 阻断**（命中即拒绝推送）：
- API 密钥（OpenAI/即梦/腾讯云等已知格式）
- 私钥（PEM 头/SSH 私钥）
- JWT Token
- 通用凭据赋值（非占位值的 `SECRET=`/`TOKEN=`/`PASSWORD=` 等）
- 内网 IP（192.168 / 10.x / 172.16-31）

提交前请手动扫描：
```bash
grep -rn "sk-" . --include="*.py" --include="*.json" | grep -v "__pycache__"
grep -rn "ghp_\|gho_" . --include="*.py" --include="*.json" | grep -v "__pycache__"
```

## 目录结构

```
core/
├── segment_tts.py             # 分段 TTS + 语义类型推断
├── timeline_mapper.py         # 程序化 timeline
├── concat_engine.py           # 精确时轴拼接
├── frame_extractor.py         # 抽帧检查
└── cta_resource.py            # 二维码资源治理

harness/
├── harness.py                 # L1/L2/L3 质检
├── self_report.py             # Autopoiesis 自检
└── video-rules.json           # 规则定义

extensions/
├── animations/
│   └── animation_templates.py # 9 种 Python 动画模板
├── storyboard/
│   └── storyboard_ai.py       # 规则驱动分镜拆解
└── prompt_templates/          # 即梦 prompt 模板

rules/
├── segment_types.json         # 语义类型规则
└── storyboard_rules.json      # 分镜 + 转场规则
```

## 许可证

提交代码即表示你同意以 MIT License 授权你的贡献。
