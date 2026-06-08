# Task Card: Fix md2video Pipeline Consistency

## Metadata
- Task ID: `TC-2026-06-08-pipeline-consistency`
- Status: `open`
- Created: `2026-06-08`
- Owner: `unassigned`
- Repo: `md2video`
- Primary layer: `code`
- Secondary layers: `docs`, `ci`, `runtime-validation`

## Objective
Make the repository's documented article-to-video pipeline runnable enough for local development by fixing import/runtime blockers, aligning examples with current APIs, removing animation-router ambiguity, and tightening CI so these regressions are caught automatically.

## Background
A read-only repository review found that the current architecture is coherent, but several implementation seams are inconsistent:

- `core.segment_tts` cannot import in the project venv because `Tuple` is used without being imported.
- `examples/example_pipeline.py` calls `generate_all()` with a two-argument callback, while `SegmentedTTSGenerator.generate_all()` invokes callbacks with three arguments.
- The repo has two animation template entrypoints. `examples/example_pipeline.py` imports `extensions.animation_templates.base.render_animation`, which only supports `price_contrast` and `table`, while `rules/storyboard_rules.json` routes common segment types to `bar_chart`, `bullet_list`, `calendar_highlight`, and `quote_card` implemented under `extensions/animations/animation_templates.py`.
- `.github/workflows/ci.yml` only installs `pillow numpy`, so it does not exercise the declared runtime dependencies from `requirements.txt`.

## Scope
In scope:
- Fix direct import/runtime blockers in core pipeline modules.
- Align `examples/example_pipeline.py` with current function signatures and animation routing.
- Consolidate or clearly route animation rendering so rule-generated `animation_type` values work.
- Add lightweight checks that import all core modules and validate the example path without generating paid external assets.
- Update docs only where they describe changed commands or entrypoints.

Out of scope:
- Running real `jimeng` generation or requiring external paid APIs in CI.
- Producing a final video as part of this task.
- Reworking the full architecture, replacing `ffmpeg`, or redesigning the harness.
- Changing existing dirty worktree edits unrelated to this task unless they directly block these fixes.

## Evidence
- Import blocker: `core/segment_tts.py` uses `Tuple` in `SemanticTypeAnalyzer.analyze()` but imports only `List`, `Optional`, and `Dict`.
- Callback mismatch: `core/segment_tts.py` calls `progress_callback(seg.id, seg.duration, seg.segment_type)`; `examples/example_pipeline.py` passes `lambda sid, dur: ...`.
- Animation mismatch: `extensions/animation_templates/base.py` registry contains only `price_contrast` and `table`; `extensions/animations/animation_templates.py` exposes the broader `render_animation(animation_type, vars_dict, duration, output_path)` router.
- CI gap: `.github/workflows/ci.yml` installs only `pillow numpy`, not `requirements.txt`, and does not run import smoke tests.

## Implementation Plan
1. Add the missing `Tuple` import in `core/segment_tts.py`.
2. Update `examples/example_pipeline.py` so the TTS progress callback accepts `segment_type`.
3. Change the example pipeline animation import to the broader router in `extensions/animations/animation_templates.py`, or add a compatibility wrapper so both entrypoints support the same rule-generated animation types.
4. Make `step3_generate_scenes()` pass each segment duration into animation rendering where available, instead of relying on a fixed default duration.
5. Add a local smoke-test script or CI inline command that imports core modules, extension routers, and harness modules.
6. Update CI to install from `requirements.txt` or a minimal explicit dependency set that includes import-time dependencies such as `edge-tts`, `Pillow`, `imageio`, `numpy`, `scipy`, and `qrcode[pil]`.
7. Keep external services out of CI: do not call `edge-tts` network synthesis, `jimeng`, or full `ffmpeg` video generation unless test fixtures are introduced.
8. Update README/SKILL snippets only if entrypoint names or commands change.

## Acceptance Criteria
- `.venv/bin/python - <<'PY'` import smoke test succeeds for:
  - `core.segment_tts`
  - `core.timeline_mapper`
  - `core.concat_engine`
  - `core.frame_extractor`
  - `core.cta_resource`
  - `extensions.storyboard.storyboard_ai`
  - `extensions.animations.animation_templates`
  - `harness.harness`
  - `harness.memory_loader`
  - `harness.self_report`
- `python -m py_compile` succeeds for all tracked `.py` files.
- The example pipeline no longer has an obvious callback arity mismatch.
- Rule-generated animation types from `rules/storyboard_rules.json` can resolve to a renderer or produce a deliberate, documented fallback.
- CI installs enough dependencies to catch the import blocker that currently slips through syntax-only checks.

## Validation Commands
```bash
python -m py_compile $(git ls-files '*.py')

.venv/bin/python - <<'PY'
mods = [
    'core.segment_tts',
    'core.timeline_mapper',
    'core.concat_engine',
    'core.frame_extractor',
    'core.cta_resource',
    'extensions.storyboard.storyboard_ai',
    'extensions.animations.animation_templates',
    'harness.harness',
    'harness.memory_loader',
    'harness.self_report',
]
for mod in mods:
    __import__(mod)
    print(f'IMPORT_OK {mod}')
PY
```

## Risks And Guards
- Avoid invoking paid or network-dependent generation during validation.
- Preserve the existing dirty worktree; inspect diffs before editing files that already contain user changes.
- If unifying animation entrypoints touches public imports, keep a compatibility shim to avoid breaking existing users.
- Treat `docs/LESSONS_LEARNED.md` as generated or semi-generated memory; do not rewrite it unless the fix requires a new friction record.

## Handoff Notes
The smallest safe repair is to fix `core.segment_tts`, align `examples/example_pipeline.py`, and add import smoke coverage to CI. Animation routing is the main design choice: prefer one canonical router and leave the older import path as a compatibility layer if practical.
