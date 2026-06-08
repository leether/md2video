import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PipelineGovernanceTests(unittest.TestCase):
    def test_preflight_reports_missing_required_command(self):
        preflight = load_module("preflight_script", REPO_ROOT / "scripts" / "preflight.py")

        result = preflight.check_required_commands(["definitely-not-md2video-command"])

        self.assertEqual(result["id"], "required_commands")
        self.assertFalse(result["passed"])
        self.assertIn("definitely-not-md2video-command", result["missing"])
        self.assertEqual(result["level"], "L1")

    def test_orchestrator_writes_jsonl_log_and_run_manifest_in_dry_run(self):
        orchestrator = load_module("orchestrator_script", REPO_ROOT / "scripts" / "orchestrator.py")

        with tempfile.TemporaryDirectory(prefix="md2video-orchestrator-test-") as tmp:
            output_dir = Path(tmp) / "output"
            log_path = Path(tmp) / ".md2video-pipeline.jsonl"
            article_path = Path(tmp) / "article.md"
            article_path.write_text("# Test\n\nA governed dry run.", encoding="utf-8")

            code = orchestrator.main([
                "--input", str(article_path),
                "--output-dir", str(output_dir),
                "--log", str(log_path),
                "--dry-run",
                "--skip-command-checks",
            ])

            self.assertEqual(code, 0)
            self.assertTrue(log_path.exists())
            log_entries = [
                json.loads(line)
                for line in log_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertGreaterEqual(len(log_entries), 2)
            self.assertTrue(all("step" in entry and "status" in entry for entry in log_entries))

            manifest_path = output_dir / "run-manifest.json"
            self.assertTrue(manifest_path.exists())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["mode"], "dry-run")
            self.assertEqual(manifest["input"]["path"], str(article_path))
            self.assertEqual(manifest["input"]["sha256"], orchestrator.sha256_file(article_path))
            self.assertIn("steps", manifest)

    def test_self_report_no_write_preserves_governance_files(self):
        from harness.self_report import SelfReport

        with tempfile.TemporaryDirectory(prefix="md2video-self-report-test-") as tmp:
            project = Path(tmp)
            (project / "harness").mkdir()
            (project / "docs").mkdir()
            (project / "output").mkdir()
            rules_path = project / "harness" / "video-rules.json"
            lessons_path = project / "docs" / "LESSONS_LEARNED.md"

            rules_before = {
                "version": "test",
                "l3_render_checks": {},
                "autopoiesis": {"self_report_enabled": True, "evolution_count": 0},
            }
            lessons_before = """---
autopoiesis: true
memory_type: "living"
last_updated: "2026-06-08"
evolution_count: 0
friction_points:
---

# LESSONS
"""
            rules_path.write_text(json.dumps(rules_before, ensure_ascii=False, indent=2), encoding="utf-8")
            lessons_path.write_text(lessons_before, encoding="utf-8")

            report = SelfReport(project_dir=str(project))
            report.capture_friction("测试", "no-write should not persist", "keep files unchanged")
            report_path, data = report.run(no_write=True, print_human=False)

            self.assertIsNone(report_path)
            self.assertEqual(json.loads(rules_path.read_text(encoding="utf-8")), rules_before)
            self.assertEqual(lessons_path.read_text(encoding="utf-8"), lessons_before)
            self.assertFalse((project / "output" / "self_report.json").exists())
            self.assertEqual(data["friction_summary"]["total"], 1)

    def test_narration_style_lint_blocks_report_voice(self):
        lint = load_module("lint_narration_style", REPO_ROOT / "scripts" / "lint_narration_style.py")

        bad_script = "在当今AI快速发展的时代，首先让我们来看看AI工具。这意味着什么？"
        bad_report = lint.lint_narration_style(bad_script)
        self.assertFalse(bad_report["passed"])
        self.assertGreater(bad_report["l1"]["total_hits"], 0)

        good_script = (
            "事情是这样的。昨天我让 Codex 帮我收尾，十分钟后发现自己漏了检查报告。\n\n"
            "说真的，我当时就在想，我到底漏了什么？\n\n"
            "后来我只留四行，输入、输出、失败检查、运行证据。这玩意很笨，但有效。"
        )
        good_report = lint.lint_narration_style(good_script, strict=True)
        self.assertTrue(good_report["passed"])


if __name__ == "__main__":
    unittest.main()
