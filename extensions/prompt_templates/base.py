#!/usr/bin/env python3
"""
Prompt Templates — 即梦素材 Prompt 模板库

核心原则：
1. 每个模板定义一套即梦 prompt 的生成规则
2. 模板参数通过变量注入，避免手动拼接字符串
3. 内置平台参数（seedance2.0fast_vip 等）和预算控制
4. 输出结构化的 prompts.json，供 timeline_mapper 消费

即梦平台参数参考：
    - model: seedance2.0fast_vip (快速版) / seedance2.0_vip (质量版)
    - aspect_ratio: 9:16 (竖屏)
    - duration: 5s / 10s
    - negative_prompt: 通用负向词
"""

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional, Dict


@dataclass
class JimengPrompt:
    """单个即梦 prompt 条目"""
    id: str                      # scene_id，与 segments.json 对齐
    text: str                    # 即梦 prompt 文本
    model: str = "seedance2.0fast_vip"
    aspect_ratio: str = "9:16"
    duration: int = 5
    negative_prompt: str = ""
    notes: str = ""              # 画面描述备注
    retry_budget: int = 3        # 最大重试次数


@dataclass
class PromptTemplate:
    """Prompt 模板定义"""
    template_id: str
    base_prompt: str             # 基础 prompt，含 {var} 占位符
    variables: List[str] = field(default_factory=list)
    default_params: Dict = field(default_factory=dict)


class PromptTemplateLibrary:
    """
    Prompt 模板库
    """

    # 通用负向词
    DEFAULT_NEGATIVE = "blurry, low quality, watermark, text overlay, distorted face, bad anatomy"

    BUILT_IN_TEMPLATES = {
        "hook_text": PromptTemplate(
            template_id="hook_text",
            base_prompt="Cinematic shot, bold Chinese text '{text}' floating in 3D space, dramatic lighting, dark background with subtle particles, movie trailer style, high contrast",
            variables=["text"],
            default_params={"duration": 5},
        ),
        "person_talking": PromptTemplate(
            template_id="person_talking",
            base_prompt="Professional Chinese presenter speaking directly to camera, confident expression, clean studio background with subtle gradient, soft studio lighting, upper body shot, 4K quality",
            variables=[],
            default_params={"duration": 10},
        ),
        "product_showcase": PromptTemplate(
            template_id="product_showcase",
            base_prompt="Sleek product showcase, {product_name} on minimalist pedestal, soft rim lighting, shallow depth of field, clean background, premium commercial photography style",
            variables=["product_name"],
            default_params={"duration": 5},
        ),
        "data_visualization": PromptTemplate(
            template_id="data_visualization",
            base_prompt="Abstract data visualization, floating charts and numbers, {metric} trending upward, neon accents on dark background, futuristic UI style, cinematic motion graphics",
            variables=["metric"],
            default_params={"duration": 5},
        ),
        "calendar_highlight": PromptTemplate(
            template_id="calendar_highlight",
            base_prompt="3D calendar floating in space, {date} highlighted in glowing accent color, date zooms in dramatically, cinematic depth of field, dark elegant background",
            variables=["date"],
            default_params={"duration": 5},
        ),
        "before_after_split": PromptTemplate(
            template_id="before_after_split",
            base_prompt="Split screen comparison, left side labeled '{before_label}' in cool tones, right side labeled '{after_label}' in warm tones, smooth transition line in center, clean graphic design",
            variables=["before_label", "after_label"],
            default_params={"duration": 5},
        ),
        "cta_endcard": PromptTemplate(
            template_id="cta_endcard",
            base_prompt="End screen with '关注 + 点赞' call-to-action, bold Chinese text, subscribe button animation style, energetic background with subtle motion, portrait format",
            variables=[],
            default_params={"duration": 8},
        ),
    }

    def __init__(self, budget_limit: Optional[int] = None):
        """
        Args:
            budget_limit: 积分预算上限，超过则报错
        """
        self.budget_limit = budget_limit
        self.used_budget = 0
        self.prompts: List[JimengPrompt] = []

    def generate(
        self,
        template_id: str,
        scene_id: str,
        variables: Optional[Dict[str, str]] = None,
        overrides: Optional[Dict] = None,
    ) -> JimengPrompt:
        """
        基于模板生成单个 prompt

        Args:
            template_id: 模板ID
            scene_id: 场景ID（与 segments 对齐）
            variables: 模板变量值
            overrides: 覆盖默认参数

        Returns:
            JimengPrompt 对象
        """
        if template_id not in self.BUILT_IN_TEMPLATES:
            raise ValueError(f"未知模板: {template_id}。可用: {list(self.BUILT_IN_TEMPLATES.keys())}")

        tmpl = self.BUILT_IN_TEMPLATES[template_id]
        vars_dict = variables or {}

        # 变量注入
        prompt_text = tmpl.base_prompt
        for var_name in tmpl.variables:
            val = vars_dict.get(var_name, f"{{{var_name}}}")
            prompt_text = prompt_text.replace(f"{{{var_name}}}", val)

        # 合并参数
        params = {**tmpl.default_params, **(overrides or {})}

        # 成本估算（简化：按 duration 估算）
        cost = params.get("duration", 5)
        if self.budget_limit is not None:
            self.used_budget += cost
            if self.used_budget > self.budget_limit:
                raise RuntimeError(
                    f"预算超限: 已用 {self.used_budget} / 限额 {self.budget_limit}。"
                    f"当前 prompt '{scene_id}' 需要 {cost} 积分。"
                )

        prompt = JimengPrompt(
            id=scene_id,
            text=prompt_text,
            model=params.get("model", "seedance2.0fast_vip"),
            aspect_ratio=params.get("aspect_ratio", "9:16"),
            duration=params.get("duration", 5),
            negative_prompt=params.get("negative_prompt", self.DEFAULT_NEGATIVE),
            notes=params.get("notes", ""),
            retry_budget=params.get("retry_budget", 3),
        )

        self.prompts.append(prompt)
        return prompt

    def add_custom(self, prompt: JimengPrompt):
        """添加自定义 prompt"""
        self.prompts.append(prompt)

    def save(self, output_path: str = "prompts.json") -> Path:
        """保存为 prompts.json"""
        data = [asdict(p) for p in self.prompts]
        path = Path(output_path)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return path

    @classmethod
    def load(cls, path: str = "prompts.json") -> List[JimengPrompt]:
        """加载 prompts.json"""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [JimengPrompt(**p) for p in data]


# 便捷入口
def generate_prompts_from_scenes(
    scenes: List[dict],
    output_path: str = "prompts.json",
    budget_limit: Optional[int] = None,
) -> Path:
    """
    从场景描述列表批量生成 prompts.json

    scenes 格式：
        [
            {"id": "s01_hook", "template": "hook_text", "vars": {"text": "价格翻倍"}},
            {"id": "s02_person", "template": "person_talking"},
            ...
        ]
    """
    lib = PromptTemplateLibrary(budget_limit=budget_limit)
    for scene in scenes:
        lib.generate(
            template_id=scene["template"],
            scene_id=scene["id"],
            variables=scene.get("vars"),
            overrides=scene.get("overrides"),
        )
    return lib.save(output_path)
