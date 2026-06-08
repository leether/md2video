# Task Card: Pipeline Orchestrator and Preflight Governance

Status: implemented
Created: 2026-06-08
Implemented: 2026-06-08

## Objective

Adopt the useful governance pattern from `md2wechat`: every pipeline run should
have a stable preflight envelope, structured JSONL execution log, run manifest,
no-write self-report validation, CI dry-run coverage, and a privacy gate.

## Boundary

In scope:

- Add `scripts/preflight.py` for machine-readable pipeline readiness checks.
- Add `scripts/orchestrator.py` as the governed dry-run entrypoint.
- Write `.md2video-pipeline.jsonl` and `output/run-manifest.json` style proof.
- Add `SelfReport.run(no_write=True)` and CLI `--no-write --json`.
- Add unit tests for the governance contracts.
- Add privacy scanning and CI coverage.

Out of scope:

- Paid or external video/material generation.
- Replacing `examples/example_pipeline.py` with a full production runner.
- Live E2E rendering with TTS or remote services.
- Automatic self-evolution rule generation beyond the existing `SelfReport`
  behavior.

## Implementation Notes

- `scripts/preflight.py` checks:
  - required command availability (`ffmpeg`, `ffprobe`) unless skipped
  - governance JSON parseability
  - storyboard animation routing
  - CTA registry consistency
  - TTS-sensitive input characters
  - stale output artifacts
- `scripts/orchestrator.py` runs the governance chain:
  - preflight
  - CTA registry verification
  - import/routing smoke
  - self-report no-write validation
  - run manifest write
- `harness/self_report.py --no-write --json` is safe for CI and local contract
  checks because it does not write `LESSONS_LEARNED.md`, `video-rules.json`, or
  `output/self_report.json`.
- `scripts/privacy-check.sh --full` is wired into CI to block common secret
  patterns and local user paths in tracked text.

## Validation

Run:

```bash
python -m unittest discover -s tests -p 'test_*.py'
python scripts/preflight.py --input examples/example_article.md --skip-command-checks --json
python scripts/orchestrator.py --input examples/example_article.md --output-dir /tmp/md2video-dry-run-output --log /tmp/md2video-pipeline.jsonl --dry-run --skip-command-checks --allow-dirty-output
python harness/self_report.py --no-write --json
bash scripts/privacy-check.sh --full
python -m py_compile $(git ls-files '*.py')
python scripts/smoke_imports.py
```

Expected:

- unit tests pass
- preflight JSON reports `ok: true`
- orchestrator exits `0` and writes a JSONL log plus `run-manifest.json`
- self-report no-write exits `0` without mutating governance files
- privacy gate has no blocking findings
- syntax and import smoke checks pass

## Residual Risks

- The orchestrator is currently a governance dry-run wrapper, not a full
  article-to-video runner.
- Full paid-service E2E remains outside this task and should stay explicit.
- Future self-evolution hardening should add observation-layer generated checks,
  companion tests, audit records, and rollback snapshots before any generated
  rule can be promoted.
