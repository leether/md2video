# md2video Assets

## CTA 二维码

`qr.png` — 真实微信群二维码（从 md2wechat 仓库复用）

### 用途

作为视频结尾 CTA 卡片的二维码素材，供 `cta_resource.py` / `generate_qr_cta()` 引用。

### 如何更新

如果二维码过期或需要更换：

1. 替换 `assets/qr.png` 为新图片（保持 300×300 以上分辨率）
2. 更新 `cta_resources.json` 中的 `target_url` 为新的群链接
3. 重新运行 harness 校验二维码完整性

### 预注册配置

已在 `cta_resources.json` 中注册为 `cta_qrcode_main`：

```json
{
  "id": "cta_qrcode_main",
  "resource_type": "qrcode",
  "target_url": "wechat://group", 
  "target_platform": "wechat",
  "target_account": "md2video交流群",
  "media_path": "assets/qr.png"
}
```

> **注意**：`target_url` 当前为占位符。如需指向具体链接，请替换后更新 checksum。
