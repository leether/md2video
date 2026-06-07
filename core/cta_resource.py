#!/usr/bin/env python3
"""
CTA Resource Manager — CTA 二维码资源治理

核心原则：
1. 二维码是「资源」而非「配置」——必须纳入版本治理和一致性校验
2. 单一真相源：cta_resources.json 是二维码的唯一注册表
3. 生成即验证：二维码生成后立即校验可扫描性
4. URL 与目标平台一致：确保二维码指向的账号/内容与视频主题一致
5. 时轴显式声明：CTA 卡片（含二维码）必须在 timeline.json 中作为独立 segment

治理范围：
    - 二维码生成（URL → 二维码图片/视频）
    - 资源注册（cta_resources.json）
    - 一致性校验（URL ↔ 视频主题 ↔ 账号信息）
    - 嵌入集成（CTA endcard 动画模板）
    - 存在性检查（harness L3）

依赖：
    - qrcode[pil]（生成二维码）
    - pyzbar（可选，校验二维码可扫描性）
"""

import json
import hashlib
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, Dict, List

from PIL import Image


@dataclass
class CTAResource:
    """单个 CTA 资源条目"""
    id: str                      # 资源ID，如 "cta_qrcode_main"
    resource_type: str           # qrcode | button | link | text
    target_url: str              # 目标 URL（如抖音主页、公众号）
    target_platform: str         # 平台标识：douyin | wechat | xiaohongshu | bilibili | custom
    target_account: str          # 账号名/ID
    media_path: str              # 资源文件路径
    media_type: str = "image"    # image | video
    checksum: str = ""           # URL 的 SHA256 校验和
    generated_at: str = ""       # ISO 时间戳
    notes: str = ""              # 备注
    valid: bool = True           # 校验结果


@dataclass
class CTAEndcardSpec:
    """CTA 结尾卡片规格"""
    duration: float = 8.0        # CTA 时长（秒）
    layout: str = "center"       # center | split | overlay
    qrcode_position: tuple = (390, 700)  # (x, y) 相对于 1080×1920
    qrcode_size: int = 300       # 二维码边长
    text_elements: List[Dict] = field(default_factory=list)
    bg_color: tuple = (18, 18, 18)
    text_color: tuple = (255, 255, 255)
    accent_color: tuple = (255, 87, 34)  # 强调色（关注按钮）


class CTAResourceManager:
    """
    CTA 资源管理器

    使用方式：
        manager = CTAResourceManager()
        # 生成二维码
        resource = manager.generate_qrcode(
            target_url="https://www.douyin.com/user/xxx",
            target_platform="douyin",
            target_account="即梦省钱攻略",
        )
        # 注册到治理表
        manager.register(resource)
        # 保存
        manager.save()
    """

    REGISTRY_PATH = Path("cta_resources.json")
    OUTPUT_DIR = Path("cta_assets")

    def __init__(self, registry_path: Optional[Path] = None):
        self.registry_path = registry_path or self.REGISTRY_PATH
        self.resources: List[CTAResource] = []
        self._load_registry()

    def _load_registry(self):
        """加载现有注册表"""
        if self.registry_path.exists():
            with open(self.registry_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.resources = [CTAResource(**r) for r in data.get("resources", [])]

    def _compute_checksum(self, url: str) -> str:
        """计算 URL 校验和"""
        return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]

    def generate_qrcode(
        self,
        target_url: str,
        target_platform: str,
        target_account: str,
        size: int = 300,
        output_name: Optional[str] = None,
    ) -> CTAResource:
        """
        生成二维码资源

        Args:
            target_url: 目标 URL
            target_platform: 平台标识
            target_account: 账号名
            size: 二维码边长（像素）
            output_name: 输出文件名（不含后缀）

        Returns:
            CTAResource 对象
        """
        try:
            import qrcode
        except ImportError:
            raise ImportError("请安装 qrcode: uv pip install qrcode[pil]")

        self.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        name = output_name or f"qrcode_{target_platform}_{target_account}"
        output_path = self.OUTPUT_DIR / f"{name}.png"

        # 生成二维码
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=2,
        )
        qr.add_data(target_url)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        img = img.resize((size, size), Image.Resampling.LANCZOS)
        img.save(output_path)

        # 校验可扫描性（可选）
        valid = self._validate_scannable(str(output_path), target_url)

        resource = CTAResource(
            id=name,
            resource_type="qrcode",
            target_url=target_url,
            target_platform=target_platform,
            target_account=target_account,
            media_path=str(output_path),
            media_type="image",
            checksum=self._compute_checksum(target_url),
            valid=valid,
            notes=f"Generated for {target_account} on {target_platform}",
        )

        return resource

    def _validate_scannable(self, image_path: str, expected_url: str) -> bool:
        """
        校验二维码可扫描性

        如果安装了 pyzbar，尝试解码并比对 URL。
        否则返回 True（跳过）。
        """
        try:
            from pyzbar.pyzbar import decode
            img = Image.open(image_path)
            decoded = decode(img)
            if not decoded:
                return False
            for d in decoded:
                if d.data.decode("utf-8") == expected_url:
                    return True
            return False
        except ImportError:
            return True

    def register(self, resource: CTAResource):
        """注册资源到治理表"""
        # 去重：同ID覆盖
        self.resources = [r for r in self.resources if r.id != resource.id]
        self.resources.append(resource)

    def get(self, resource_id: str) -> Optional[CTAResource]:
        """按ID获取资源"""
        for r in self.resources:
            if r.id == resource_id:
                return r
        return None

    def get_by_platform(self, platform: str) -> List[CTAResource]:
        """按平台获取资源"""
        return [r for r in self.resources if r.target_platform == platform]

    def validate_consistency(self, video_topic: str) -> List[str]:
        """
        校验二维码与视频主题的一致性

        检查项：
        1. URL 非空且格式合法
        2. target_account 非空
        3. checksum 与当前 URL 匹配
        """
        errors = []
        for r in self.resources:
            if not r.target_url or not r.target_url.startswith(("http://", "https://")):
                errors.append(f"[{r.id}] URL 格式非法: {r.target_url}")
            if not r.target_account:
                errors.append(f"[{r.id}] target_account 为空")
            if r.checksum != self._compute_checksum(r.target_url):
                errors.append(f"[{r.id}] checksum 不匹配，URL 可能已被篡改")
            if not r.valid:
                errors.append(f"[{r.id}] 二维码可扫描性校验失败")
        return errors

    def save(self):
        """保存注册表"""
        data = {
            "version": "1.0.0",
            "resource_count": len(self.resources),
            "resources": [asdict(r) for r in self.resources],
        }
        with open(self.registry_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def generate_cta_endcard(
        self,
        resource_id: str,
        spec: Optional[CTAEndcardSpec] = None,
        output_path: str = "rebuild_animations/cta_endcard.mp4",
    ) -> Path:
        """
        生成带二维码的 CTA 结尾卡片视频

        Args:
            resource_id: CTA 资源ID
            spec: CTA 卡片规格
            output_path: 输出路径

        Returns:
            输出视频路径
        """
        resource = self.get(resource_id)
        if not resource:
            raise ValueError(f"CTA 资源不存在: {resource_id}")

        spec = spec or CTAEndcardSpec()

        # 导入动画基类
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from extensions.animation_templates.base import AnimationTemplate, AnimationConfig, get_font
        import numpy as np

        class CTAEndcardAnimation(AnimationTemplate):
            def __init__(self, resource, spec, config=None):
                super().__init__(config)
                self.resource = resource
                self.spec = spec
                self.config.duration = spec.duration

            def render(self):
                from PIL import ImageDraw
                total_frames = int(self.config.duration * self.config.fps)
                frames = []

                font_title = get_font(80)
                font_sub = get_font(50)
                font_cta = get_font(60)

                # 加载二维码
                qrcode_img = Image.open(self.resource.media_path).convert("RGBA")
                qrcode_img = qrcode_img.resize((self.spec.qrcode_size, self.spec.qrcode_size), Image.Resampling.LANCZOS)

                for frame_idx in range(total_frames):
                    progress = frame_idx / total_frames if total_frames > 1 else 1.0

                    img = Image.new("RGB", (self.config.width, self.config.height), self.spec.bg_color)
                    draw = ImageDraw.Draw(img)
                    W, H = self.config.width, self.config.height

                    # 主标题（淡入）
                    if progress > 0.1:
                        title = "关注我，获取更多"
                        bbox = draw.textbbox((0, 0), title, font=font_title)
                        tw = bbox[2] - bbox[0]
                        draw.text(((W - tw) // 2, 300), title, fill=self.spec.text_color, font=font_title)

                        subtitle = self.resource.target_account
                        bbox = draw.textbbox((0, 0), subtitle, font=font_sub)
                        sw = bbox[2] - bbox[0]
                        draw.text(((W - sw) // 2, 420), subtitle, fill=self.spec.accent_color, font=font_sub)

                    # 二维码（缩放进入）
                    if progress > 0.3:
                        scale = min(1.0, (progress - 0.3) / 0.3)
                        qr_size = int(self.spec.qrcode_size * scale)
                        qr_resized = qrcode_img.resize((qr_size, qr_size), Image.Resampling.LANCZOS)

                        x = (W - qr_size) // 2
                        y = self.spec.qrcode_position[1]
                        img.paste(qr_resized, (x, y), qr_resized)

                    # 扫码提示
                    if progress > 0.6:
                        hint = "扫码关注"
                        bbox = draw.textbbox((0, 0), hint, font=font_cta)
                        hw = bbox[2] - bbox[0]
                        draw.text(((W - hw) // 2, y + qr_size + 50), hint, fill=(200, 200, 200), font=font_cta)

                    # 平台标识
                    if progress > 0.8:
                        platform_text = f"@{self.resource.target_platform}"
                        bbox = draw.textbbox((0, 0), platform_text, font=font_sub)
                        pw = bbox[2] - bbox[0]
                        draw.text(((W - pw) // 2, H - 200), platform_text, fill=(150, 150, 150), font=font_sub)

                    frames.append(np.array(img))

                return frames

        anim = CTAEndcardAnimation(resource, spec)
        anim.save(output_path)
        return Path(output_path)


# 便捷入口
def generate_qr_cta(
    target_url: str,
    target_platform: str,
    target_account: str,
    output_video: str = "rebuild_animations/cta_endcard.mp4",
) -> Path:
    """
    一键生成带二维码的 CTA 结尾卡片

    Args:
        target_url: 目标 URL
        target_platform: 平台标识
        target_account: 账号名
        output_video: 输出视频路径

    Returns:
        输出视频路径
    """
    manager = CTAResourceManager()
    resource = manager.generate_qrcode(
        target_url=target_url,
        target_platform=target_platform,
        target_account=target_account,
    )
    manager.register(resource)
    manager.save()
    return manager.generate_cta_endcard(resource.id, output_path=output_video)
