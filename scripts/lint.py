"""快速 lint CLI：对单个产物执行对应层检查，不渲染、不修复。

用法：
    python scripts/lint.py draft.json                       # ArticleDraft → Content QA
    python scripts/lint.py draft.json --research r.json --brief b.json
    python scripts/lint.py package.json                     # ContentPackage → 组件 + 视觉 lint
    python scripts/lint.py doc.md                           # 语义 Markdown → 组件 lint
    python scripts/lint.py page.html                        # HTML → html + gzh 双层

按扩展名分派；.json 先按 ArticleDraft 再按 ContentPackage 识别
（两类字段集不相交且均为 extra=forbid，不会误判）。
draft 模式显式加载 skills/content/humanize/rules.yaml 复检 AI 味（H8：不信任缓存）。
stdout 输出 ValidationReport JSON（结构化 ErrorReport），stderr 一行摘要。
退出码：0 = 通过；1 = 检出错误；2 = 输入 / 环境错误。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse
import json

from core.artifacts.models import (
    ArticleDraft,
    ContentBrief,
    ContentPackage,
    ResearchResult,
    ValidationIssue,
    ValidationReport,
)
from renderer.themes import Theme, ThemeError, load_theme
from skills.content.humanize.detector import load_rules
from validators import validate_wechat_html
from validators.component import lint_components
from validators.content import lint_content, lint_visual


def _split(issues: list[ValidationIssue]) -> tuple[list[ValidationIssue], list[ValidationIssue]]:
    errors = [issue for issue in issues if issue.severity == "error"]
    warnings = [issue for issue in issues if issue.severity == "warning"]
    return errors, warnings


def _report(gate: str, issues: list[ValidationIssue]) -> ValidationReport:
    errors, warnings = _split(issues)
    return ValidationReport(
        status="failed" if errors else "passed", gate=gate, errors=errors, warnings=warnings
    )


def _emit(report: ValidationReport, output: str | None) -> int:
    text = json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2)
    print(text)
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
    verdict = "PASS" if report.status == "passed" else "FAIL"
    print(
        f"{verdict}: {len(report.errors)} errors, {len(report.warnings)} warnings"
        f" (gate={report.gate})",
        file=sys.stderr,
    )
    return 0 if report.status == "passed" else 1


def _load_model(path: Path, model_cls, label: str):
    try:
        return model_cls.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except Exception as exc:
        raise ValueError(f"{label}校验失败：{exc}") from exc


def _load_theme(name: str | None) -> Theme:
    try:
        return load_theme(name or "default")
    except ThemeError as exc:
        raise ValueError(f"主题加载失败：{exc}") from exc


def _lint_draft(path: Path, args: argparse.Namespace) -> ValidationReport:
    draft = _load_model(path, ArticleDraft, "ArticleDraft ")
    research = (
        _load_model(Path(args.research), ResearchResult, "ResearchResult ")
        if args.research
        else None
    )
    brief = _load_model(Path(args.brief), ContentBrief, "ContentBrief ") if args.brief else None
    issues = lint_content(draft, research=research, brief=brief, rules=load_rules())
    return _report("content", issues)


def _lint_package(path: Path, args: argparse.Namespace) -> ValidationReport:
    package = _load_model(path, ContentPackage, "ContentPackage ")
    theme = _load_theme(args.theme or package.theme or "default")
    issues = lint_components(package.semantic_markdown, theme=theme) + lint_visual(package)
    return _report("content", issues)


def _lint_markdown(path: Path, args: argparse.Namespace) -> ValidationReport:
    theme = _load_theme(args.theme)
    return _report("content", lint_components(path.read_text(encoding="utf-8"), theme=theme))


def _lint_html(path: Path) -> ValidationReport:
    return _report("publish", validate_wechat_html(path.read_text(encoding="utf-8")))


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="lint.py", description="单产物快速 lint（不渲染、不修复）"
    )
    parser.add_argument("input", help="待检文件：draft.json / package.json / .md / .html")
    parser.add_argument("-o", "--output", default=None, help="ErrorReport JSON 输出路径（可选）")
    parser.add_argument(
        "--research", default=None, help="ResearchResult JSON（draft 模式：引用一致性）"
    )
    parser.add_argument("--brief", default=None, help="ContentBrief JSON（draft 模式：字数目标）")
    parser.add_argument(
        "--theme", default=None, help="组件 lint 主题（默认：包内 theme 字段 / default）"
    )
    args = parser.parse_args()

    in_path = Path(args.input)
    if not in_path.is_file():
        print(f"错误：输入文件不存在：{in_path}", file=sys.stderr)
        return 2
    suffix = in_path.suffix.lower()
    try:
        if suffix in {".md", ".markdown"}:
            report = _lint_markdown(in_path, args)
        elif suffix in {".html", ".htm"}:
            report = _lint_html(in_path)
        elif suffix == ".json":
            try:
                report = _lint_draft(in_path, args)
            except ValueError:
                report = _lint_package(in_path, args)
        else:
            print(
                f"错误：不支持的文件类型：{suffix}（支持 .json / .md / .html）",
                file=sys.stderr,
            )
            return 2
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    return _emit(report, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
