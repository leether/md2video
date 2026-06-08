# md2video Assets

## CTA 二维码

`qr.png` — 真实微信群二维码（从 `leether/md2wechat:assets/qr.png` 复用）

当前文件为了兼容 README 和旧调用路径保留历史文件名 `qr.png`，但文件内容是
Pillow 识别的 `JPEG` 图片，尺寸为 `396×396`。治理时以
`cta_resources.json` 中的 `media_sha256` 为准，不以扩展名判断真实性。

### 用途

作为视频结尾 CTA 卡片的二维码素材，供 `cta_resource.py` / `generate_qr_cta()` 引用。

### 如何更新

如果二维码过期或需要更换：

1. 从可信来源复制新图片到 `assets/qr.png`（保持 300×300 以上分辨率）
2. 更新 `cta_resources.json` 中的 `checksum`、`media_sha256`、来源路径和图片元数据
3. 运行 `python scripts/verify_cta_resources.py`
4. 再运行 harness 校验二维码完整性

### 预注册配置

已在 `cta_resources.json` 中注册为 `cta_qrcode_main`。注册表记录公开治理元数据：

```json
{
  "id": "cta_qrcode_main",
  "resource_type": "qrcode",
  "target_url": "wechat://group",
  "target_platform": "wechat",
  "target_account": "md2video交流群",
  "media_path": "assets/qr.png",
  "source_repo": "leether/md2wechat",
  "source_path": "assets/qr.png"
}
```

> **隐私边界**：`target_url` 只表达平台语义，不把二维码实际 payload 写入仓库文本。
