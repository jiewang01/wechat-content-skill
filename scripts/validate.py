"""发布门禁 CLI：ContentPackage JSON → 渲染 + 修复循环 + 三层校验 → 结构化 ErrorReport。

用法：
    python scripts/validate.py pkg.json
    python scripts/validate.py pkg.json -o report.json --html-output wechat.html
    python scripts/validate.py pkg.json --theme default --max-html-bytes 1048576

管线（蓝图九章 / 十章）：
    1. 组件 lint（gate=content）：语义标记层，错误即止——标记问题无法靠渲染修复；
    2. 渲染 + 定向修复循环 ≤3 轮（gate=render）：HTML 层，段级节点归属（H3/H4）；
    3. 发布门禁（gate=publish）：平台层文档级检查（图片 / 外部资源 / 体积），
       与渲染层残留合并为最终 ErrorReport（H5：无 PASS 不发布）。

stdout 始终输出 ValidationReport JSON（Judge 消费的结构化 ErrorReport），
stderr 输出一行人类可读摘要。
退出码：0 = 通过；1 = 校验失败；2 = 输入 / 环境错误。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse
import json

from core.artifacts.models import ContentPackage, ValidationIssue, ValidationReport
from core.workflow.repair import repair_rendered
from renderer.ast import ParseError, parse
from renderer.html import HtmlRenderer
from renderer.themes import ThemeError, load_theme
from validators.component import lint_components
from validators.wechat import lint_gzh


def _split(issues: list[ValidationIssue]) -> tuple[list[ValidationIssue], list[ValidationIssue]]:
    errors = [issue for issue in issues if issue.severity == "error"]
    warnings = [issue for issue in issues if issue.severity == "warning"]
    return errors, warnings


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


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="validate.py",
        description="ContentPackage → 渲染 + 修复循环 + 发布门禁，输出结构化 ErrorReport",
    )
    parser.add_argument("input", help="ContentPackage JSON 文件路径")
    parser.add_argument("-o", "--output", default=None, help="ErrorReport JSON 输出路径（可选）")
    parser.add_argument(
        "--html-output",
        default=None,
        help="修复后的完整 HTML 输出路径（可选；无论成败均写出，便于排查）",
    )
    parser.add_argument("--theme", default=None, help="主题名（默认：取包内 theme 字段）")
    parser.add_argument(
        "--max-html-bytes", type=int, default=None, help="HTML 体积上限字节（默认 1MB）"
    )
    args = parser.parse_args()

    in_path = Path(args.input)
    if not in_path.is_file():
        print(f"错误：输入文件不存在：{in_path}", file=sys.stderr)
        return 2
    try:
        package = ContentPackage.model_validate(json.loads(in_path.read_text(encoding="utf-8")))
    except Exception as exc:
        print(f"错误：ContentPackage 校验失败：{exc}", file=sys.stderr)
        return 2

    try:
        theme = load_theme(args.theme or package.theme or "default")
    except ThemeError as exc:
        print(f"错误：主题加载失败：{exc}", file=sys.stderr)
        return 2

    component_errors, component_warnings = _split(lint_components(package.semantic_markdown, theme))
    if component_errors:
        report = ValidationReport(
            status="failed",
            gate="content",
            errors=component_errors,
            warnings=component_warnings,
        )
        return _emit(report, args.output)

    try:
        ast = parse(package.semantic_markdown, title=package.title, digest=package.digest)
    except ParseError as exc:
        print(f"错误：语义 Markdown 解析失败：{exc}", file=sys.stderr)
        return 2
    renderer = HtmlRenderer(theme)
    outcome = repair_rendered(ast, renderer)

    full_html = renderer.wrap_document(outcome.html)
    gzh_errors, gzh_warnings = _split(lint_gzh(full_html, max_bytes=args.max_html_bytes))
    errors = list(outcome.report.errors) + gzh_errors
    warnings = component_warnings + list(outcome.report.warnings) + gzh_warnings
    report = ValidationReport(
        status="failed" if errors else "passed",
        gate="publish",
        errors=errors,
        warnings=warnings,
    )
    if args.html_output:
        html_path = Path(args.html_output)
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(full_html, encoding="utf-8")
        print(f"wrote {html_path}", file=sys.stderr)
    return _emit(report, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
