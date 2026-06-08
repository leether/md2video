#!/usr/bin/env python3
"""Lint md2video narration scripts for report-like AI phrasing."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RULES = REPO_ROOT / "rules" / "narration_style_rules.json"


def load_rules(rules_path: Path = DEFAULT_RULES) -> dict[str, Any]:
    with rules_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def strip_markdown_noise(markdown: str) -> str:
    lines: list[str] = []
    in_code = False
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if stripped.startswith("|") and stripped.endswith("|"):
            continue
        if re.match(r"^\|[-:\s|]+\|$", stripped):
            continue
        lines.append(line)
    return "\n".join(lines)


def line_for_index(text: str, index: int) -> int:
    return text[:index].count("\n") + 1


def scan_literal_list(text: str, items: list[str], key: str, replacements: dict[str, str] | None = None) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for item in items:
        start = 0
        while True:
            idx = text.find(item, start)
            if idx < 0:
                break
            hit = {key: item, "line": line_for_index(text, idx)}
            if replacements and item in replacements:
                hit["replacement"] = replacements[item]
            hits.append(hit)
            start = idx + len(item)
    return hits


def scan_regex_list(text: str, patterns: list[str]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for pattern in patterns:
        regex = re.compile(pattern)
        for match in regex.finditer(text):
            line = line_for_index(text, match.start())
            excerpt = text.splitlines()[line - 1].strip()[:100] if text.splitlines() else ""
            hits.append({"pattern": pattern, "line": line, "excerpt": excerpt})
    return hits


def scan_punctuation(text: str, rules: list[dict[str, str]]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for rule in rules:
        char = rule["char"]
        start = 0
        while True:
            idx = text.find(char, start)
            if idx < 0:
                break
            hits.append({
                "char": char,
                "line": line_for_index(text, idx),
                "reason": rule.get("reason", ""),
                "replacement": rule.get("replacement", ""),
            })
            start = idx + len(char)
    return hits


def scan_long_paragraphs(text: str, max_chars: int) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    current_line = 1
    for para in re.split(r"\n\s*\n", text):
        plain = re.sub(r"[#*>`\[\]!|()_-]", "", para).strip()
        if len(plain) > max_chars:
            hits.append({
                "start_line": current_line,
                "char_count": len(plain),
                "max_chars": max_chars,
                "excerpt": plain[:80],
            })
        current_line += para.count("\n") + 2
    return hits


def scan_colloquial(text: str, rules: dict[str, Any]) -> dict[str, Any]:
    found = []
    for pattern in rules.get("l2_colloquial_expressions", []):
        if re.search(pattern, text):
            found.append(pattern)
    minimum = int(rules.get("l2_min_colloquial_expressions", 0))
    return {"found": found, "count": len(found), "minimum": minimum, "passed": len(found) >= minimum}


def scan_concrete_anchors(text: str, rules: dict[str, Any]) -> dict[str, Any]:
    found = []
    for pattern in rules.get("l2_concrete_anchor_patterns", []):
        if re.search(pattern, text):
            found.append(pattern)
    minimum = int(rules.get("l2_min_concrete_anchors", 0))
    return {"found": found, "count": len(found), "minimum": minimum, "passed": len(found) >= minimum}


def scan_sentence_rhythm(text: str, rules: dict[str, Any]) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    parts = [p.strip() for p in re.split(r"[。！？?!\n]+", text) if p.strip()]
    threshold = int(rules.get("l2_sentence_variance_threshold", 6))
    max_similar = int(rules.get("l2_max_consecutive_similar_length", 3))
    consecutive = 0
    prev_len = 0
    for part in parts:
        clean = re.sub(r"[#*>`\[\]!|()_-]", "", part).strip()
        if not clean:
            continue
        if re.match(r"^(第一|第二|第三|第四|第五|第六|第七|第八|第九|第十)[，,、]", clean):
            continue
        length = len(clean)
        if prev_len and abs(length - prev_len) < threshold:
            consecutive += 1
            if consecutive >= max_similar:
                warnings.append({
                    "type": "sentence_rhythm",
                    "detail": f"连续 {consecutive + 1} 句长度接近，口播节奏可能偏平",
                })
                break
        else:
            consecutive = 0
        prev_len = length
    return warnings


def lint_narration_style(markdown: str, rules_path: Path = DEFAULT_RULES, strict: bool = False) -> dict[str, Any]:
    rules = load_rules(rules_path)
    prose = strip_markdown_noise(markdown)
    replacements = rules.get("l1_banned_words_replacements", {})

    l1 = {
        "banned_words": scan_literal_list(prose, rules.get("l1_banned_words", []), "word", replacements),
        "banned_punctuation": scan_punctuation(prose, rules.get("l1_banned_punctuation", [])),
        "banned_structures": scan_regex_list(prose, rules.get("l1_banned_structures", [])),
        "vague_tools": scan_literal_list(prose, rules.get("l1_banned_vague_tools", []), "phrase"),
        "long_paragraphs": scan_long_paragraphs(prose, int(rules.get("l1_max_paragraph_chars", 9999))),
    }
    l1_total = sum(len(v) for v in l1.values())

    l2_punctuation = scan_punctuation(prose, rules.get("l2_banned_punctuation", []))
    colloquial = scan_colloquial(prose, rules)
    anchors = scan_concrete_anchors(prose, rules)
    questions = prose.count("？") + prose.count("?")
    min_questions = int(rules.get("l2_min_question_marks", 0))
    l2_warnings = [
        *scan_regex_list(prose.split("\n\n", 1)[0] if prose.strip() else "", rules.get("l2_no_go_openings", [])),
        *scan_sentence_rhythm(prose, rules),
    ]
    l2_warnings.extend({"type": "punctuation", "detail": f"第{h['line']}行 {h['reason']}"} for h in l2_punctuation)
    if not colloquial["passed"]:
        l2_warnings.append({"type": "colloquial", "detail": f"口语化表达 {colloquial['count']}/{colloquial['minimum']}"})
    if not anchors["passed"]:
        l2_warnings.append({"type": "concrete_anchor", "detail": f"具体锚点 {anchors['count']}/{anchors['minimum']}"})
    if questions < min_questions:
        l2_warnings.append({"type": "question", "detail": f"疑问句 {questions}/{min_questions}，少了口播转向"})

    l1_passed = l1_total == 0
    l2_passed = len(l2_warnings) == 0
    return {
        "passed": l1_passed and (l2_passed if strict else True),
        "strict": strict,
        "l1": {**l1, "passed": l1_passed, "total_hits": l1_total},
        "l2": {
            "passed": l2_passed,
            "warnings": l2_warnings,
            "colloquial": colloquial,
            "concrete_anchors": anchors,
            "question_count": questions,
            "minimum_questions": min_questions,
        },
        "manual_checks": rules.get("l3_manual_checks", []),
        "rules_version": rules.get("version", ""),
    }


def format_report(report: dict[str, Any]) -> str:
    lines = ["md2video Narration Style Lint", ""]
    lines.append(f"L1 hard rules: {'PASS' if report['l1']['passed'] else 'FAIL'}")
    for key, label in [
        ("banned_words", "banned word"),
        ("banned_punctuation", "banned punctuation"),
        ("banned_structures", "banned structure"),
        ("vague_tools", "vague tool"),
        ("long_paragraphs", "long paragraph"),
    ]:
        for hit in report["l1"][key]:
            lines.append(f"- {label}: {hit}")
    if report["l1"]["passed"]:
        lines.append("- no hard-rule hits")

    lines.append("")
    lines.append(f"L2 voice warnings: {'PASS' if report['l2']['passed'] else 'WARN'}")
    for warning in report["l2"]["warnings"]:
        lines.append(f"- {warning.get('type', 'warning')}: {warning.get('detail', warning)}")
    lines.append(
        f"- colloquial expressions: {report['l2']['colloquial']['count']}/{report['l2']['colloquial']['minimum']}"
    )
    lines.append(
        f"- concrete anchors: {report['l2']['concrete_anchors']['count']}/{report['l2']['concrete_anchors']['minimum']}"
    )
    lines.append(f"- questions: {report['l2']['question_count']}/{report['l2']['minimum_questions']}")

    lines.append("")
    lines.append("Manual review prompts:")
    for item in report["manual_checks"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append(f"Result: {'PASS' if report['passed'] else 'FAIL'}")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lint narration scripts for human voice and anti-AI phrasing")
    parser.add_argument("--input", required=True, help="Markdown narration script")
    parser.add_argument("--rules", default=str(DEFAULT_RULES), help="Rules JSON path")
    parser.add_argument("--strict", action="store_true", help="Treat L2 warnings as failures")
    parser.add_argument("--json", action="store_true", help="Print JSON report")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Input file not found: {input_path}", file=sys.stderr)
        return 2
    report = lint_narration_style(input_path.read_text(encoding="utf-8"), Path(args.rules), strict=args.strict)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_report(report))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
