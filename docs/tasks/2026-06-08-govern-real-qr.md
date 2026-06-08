# Task Card: Govern Real CTA QR Asset

Status: implemented
Created: 2026-06-08
Implemented: 2026-06-08

## Context

`md2video` uses a WeChat QR image in README and CTA endcard generation. The
real QR source is the sister repository `leether/md2wechat:assets/qr.png`.

Before this task, `assets/qr.png` already matched the source QR byte-for-byte,
but `cta_resources.json` still contained a placeholder-style checksum and did
not record the media fingerprint, image metadata, or source provenance.

## Scope

- Re-copy and verify the real QR from `leether/md2wechat:assets/qr.png`.
- Keep the existing public path `assets/qr.png` for README and runtime
  compatibility.
- Do not store the QR decoded payload in text files.
- Govern the public registry metadata through `cta_resources.json`.
- Add a CI-checkable validation script.

## Implementation Notes

- `assets/qr.png` content SHA256:
  `e41e839f2f1f83a39b9622b2dc22eaecba76319b4aca7f1d3b74dc2f10868f59`
- Source provenance:
  - `source_repo`: `leether/md2wechat`
  - `source_path`: `assets/qr.png`
  - source file commit observed locally: `20baad2 fix: include QR code image in repo for README display`
  - `source_sha256`: same as `media_sha256`
- Actual image metadata:
  - Format: `JPEG`
  - Dimensions: `396x396`
- Historical filename `qr.png` is retained intentionally; validation uses
  `media_sha256` and `media_format`, not the extension.
- `target_url` remains `wechat://group` as a platform semantic marker. The
  actual QR payload is not written into repository text for privacy.

## Validation

Run:

```bash
git diff --no-index --quiet ../md2wechat/assets/qr.png assets/qr.png
python scripts/verify_cta_resources.py
python -m py_compile $(git ls-files '*.py')
python scripts/smoke_imports.py
```

Expected:

- `CTA_RESOURCE_OK`
- QR source and local asset have no diff
- Python syntax check passes
- Import and routing smoke check passes

## CI

`.github/workflows/ci.yml` now runs `python scripts/verify_cta_resources.py`.
