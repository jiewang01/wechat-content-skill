"""eval 汇总 CLI（v0.2 计划 N3-T5）：一键运行四类 eval，输出 JSON 报告。

用法：
    python scripts/run_evals.py
    python scripts/run_evals.py -o outputs/evals/report.json
    python scripts/run_evals.py --no-write

四类 eval（判分逻辑全部集中在本文件，tests/evals/ 下三个测试文件直接复用）：
    1. humanize      好文得分 ≥ GOOD_CASE_MIN_SCORE 且 passed；
                     AI 味文得分 ≤ AI_FLAVOR_MAX_SCORE 且检出 error 级问题；
    2. content_gate  结构缺失文必须被 lint_content 检出 structure_incomplete；
                     好文走正向路径，零 error；
    3. render        全组件样张 + 嵌套样张（card 内嵌 note/quote/callout）
                     各在 5 个内置主题下渲染，
                     组件门 + HTML 门 + 公众号门全部零 error；
    4. framework     7 个写作框架语料各配 research / brief / draft 样例，
                     走 content → component → render/publish 全链路三层门禁，零 error。

判分阈值集中在 tests/evals/thresholds.py（N3 风险缓解：阈值有争议时只改那里），
及格线本身（60 分）以 skills/content/humanize/rules.yaml 的 pass_score 为准。

stdout 输出完整 JSON 报告；stderr 输出一行人类可读摘要。
退出码：0 = 全部通过；1 = 存在回归（任何用例失败）；2 = 语料 / 环境错误。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse
import json
import re

from core.artifacts.models import (
    ArticleDraft,
    BriefSection,
    ContentBrief,
    Fact,
    ResearchResult,
    Source,
    ValidationIssue,
)
from core.utils import estimate_word_count
from core.workflow.repair import repair_rendered
from renderer.ast import parse
from renderer.html import HtmlRenderer
from renderer.themes import load_theme
from skills.content.humanize.detector import analyze_text
from tests.evals.thresholds import (
    AI_FLAVOR_MAX_SCORE,
    GOOD_CASE_MIN_SCORE,
    MIN_CASES_PER_CLASS,
)
from validators import lint_components, lint_content, lint_gzh


class EvalsError(Exception):
    """语料缺失 / 数量不足 / 元数据不匹配等环境错误（对应退出码 2）。"""


ROOT = Path(__file__).resolve().parent.parent
CASES_DIR = ROOT / "tests" / "evals" / "cases"
FRAMEWORKS_DIR = CASES_DIR / "frameworks"
REPORT_PATH = ROOT / "outputs" / "evals" / "evals-report.json"

BUILTIN_THEMES = ("default", "editorial", "minimal", "tech", "magazine", "orange-heart")
FRAMEWORK_IDS = (
    "tutorial",
    "news-analysis",
    "opinion",
    "case-study",
    "listicle",
    "deep-dive",
    "narrative",
)

# 结构缺失语料的正文没有 `#` 标题行，标题在这里补齐，使用例只聚焦 markdown 属性
STRUCTURE_MISSING_TITLES = {
    "structure_missing_01": "晚间阅读",
    "structure_missing_02": "怎么记录失败",
}

# 全组件样张：组件种类与 tests/unit/test_theme_pack.py 的 DOC 保持一致，仅文字不同
RENDER_DOC = """# 渲染评估：全组件样张

普通段落，含 **加粗强调**、*斜体补充*、`行内代码` 与 [外部链接](https://example.com/eval)。

:::note
评估说明：note 组件在各主题下都应渲染为带样式的提示块。
:::

:::quote cite="评估引用人"
评估引用：语义标记的渲染结果不应依赖具体主题。
:::

:::callout type="info" title="评估信息"
info 类型提示内容。
:::

:::callout type="warning" title="评估注意"
warning 类型提示内容。
:::

:::callout type="tip" title="评估提示"
tip 类型提示内容。
:::

:::callout type="danger" title="评估危险"
danger 类型提示内容。
:::

:::card title="评估要点卡" footer="评估完"
- 要点甲：语义标记完整
- 要点乙：内联样式合规
:::

![评估配图](https://example.com/eval.png)

```python
score = 100
threshold = 90
```

- 渲染清单甲
- 渲染清单乙

1. 评估步骤甲
2. 评估步骤乙

---

> 评估用引用块：这是一段普通 Markdown 引用。
"""

# 框架 eval 的 research / brief 元数据，与语料正文中的（见 fact_NNN）标记一一对应
_FRAMEWORK_META: dict[str, dict] = {
    "tutorial": {
        "topic": "给仓库加一条自动测试流水线",
        "goal": "带读者用四步给 Python 仓库接入 GitHub Actions",
        "note": "yml 配置里的缩进必须用空格，不能用 Tab。",
        "sources": [
            ("src_001", "支付模块线上故障复盘（内部）", ""),
        ],
        "facts": [
            ("fact_001", "合码前未强制跑测试，退款接口故障两小时", ["src_001"]),
        ],
    },
    "news-analysis": {
        "topic": "HashiCorp 商业版涨价 40%，社区怎么看",
        "goal": "拆解事件的事实、背景与影响，给出观察清单",
        "note": "文中比例与日期均以官方公告为准。",
        "sources": [
            ("src_001", "HashiCorp 官方涨价公告", "https://example.com/hashicorp-announcement"),
            ("src_002", "HashiCorp 最近一季财报", "https://example.com/hashicorp-earnings"),
        ],
        "facts": [
            ("fact_001", "商业版订阅全线涨价 40%，4 月 1 日生效", ["src_001"]),
            ("fact_002", "上一轮协议变更后，付费客户数不降反升", ["src_002"]),
        ],
    },
    "opinion": {
        "topic": "多数团队不需要微服务，先把单体写明白",
        "goal": "给出可检验的架构判断，而不是站队",
        "note": "本文立场系作者个人偏好，论据见正文。",
        "sources": [
            (
                "src_001",
                "某电商团队技术分享：单体架构支撑日活百万",
                "https://example.com/monolith-talk",
            ),
        ],
        "facts": [
            ("fact_001", "模块化单体配合读写分离，在日活百万级业务下稳定运行", ["src_001"]),
        ],
    },
    "case-study": {
        "topic": "一次失败的会员拉新：我们如何三周烧掉三十万",
        "goal": "复盘失败动作，提炼下次可执行的教训",
        "note": "复盘数据已脱敏，金额做了取整处理。",
        "sources": [("src_001", "活动复盘内部文档（脱敏）", "")],
        "facts": [
            ("fact_001", "活动期间平台风控收紧，分享链路被限流两次", ["src_001"]),
        ],
    },
    "listicle": {
        "topic": "独立开发者的五个低成本获客渠道",
        "goal": "给出可对照执行的获客渠道清单",
        "note": "各渠道数据为该团队实测，行业不同会有差异。",
        "sources": [("src_001", "Product Hunt 官方数据看板", "https://example.com/ph-stats")],
        "facts": [
            ("fact_001", "Product Hunt 单次提交带来 87 个注册", ["src_001"]),
        ],
    },
    "deep-dive": {
        "topic": "排队还是拒绝：四种限流算法拆到底",
        "goal": "把四种限流算法拆到可做选型判断的深度",
        "note": "文中参数为示意值，生产环境需按容量压测调参。",
        "sources": [("src_001", "限流算法压测报告（内部）", "")],
        "facts": [
            ("fact_001", "固定窗口限流在窗口交界处可放行双倍请求", ["src_001"]),
        ],
    },
    "narrative": {
        "topic": "上线前夜",
        "goal": "用叙事还原一次上线救火的真实过程",
        "note": "文中人物均为化名。",
        "sources": [("src_001", "上线值班记录（内部）", "")],
        "facts": [
            ("fact_001", "上线首小时注册 1400 人，支付零失败", ["src_001"]),
        ],
    },
}

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_SECTION_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$")
_FACT_MARKER_RE = re.compile(r"fact_\d{3}")
_DIGEST_MAX_CHARS = 54


def _extract_title(markdown: str) -> str:
    for line in markdown.splitlines():
        matched = _HEADING_RE.match(line.strip())
        if matched and matched.group(1) == "#":
            return matched.group(2).strip()
    for line in markdown.splitlines():
        if line.strip():
            return line.strip().lstrip("#").strip()
    return "未命名文章"


def _make_digest(markdown: str) -> str:
    for line in markdown.splitlines():
        text = line.strip()
        if not text or _HEADING_RE.match(text) or text.startswith("!["):
            continue
        cleaned = re.sub(r"[*_`>\-#]+", "", text).strip()
        if cleaned:
            return cleaned[:_DIGEST_MAX_CHARS]
    return ""


def _brief_section(heading: str, body_lines: list[str], claims: dict[str, str]) -> BriefSection:
    text = "\n".join(body_lines)
    fact_ids = list(dict.fromkeys(_FACT_MARKER_RE.findall(text)))
    return BriefSection(
        heading=heading,
        key_points=[claims[fact_id] for fact_id in fact_ids if fact_id in claims],
        fact_ids=fact_ids,
    )


def _sections_from_markdown(markdown: str, claims: dict[str, str]) -> list[BriefSection]:
    """按 `##` 二级标题切分语料正文生成大纲小节；`###` 子标题归入父节正文。"""
    sections: list[BriefSection] = []
    heading: str | None = None
    body: list[str] = []
    for line in markdown.splitlines():
        matched = _SECTION_HEADING_RE.match(line)
        if matched:
            if heading is not None:
                sections.append(_brief_section(heading, body, claims))
            heading, body = matched.group(1), []
        elif heading is not None:
            body.append(line)
    if heading is not None:
        sections.append(_brief_section(heading, body, claims))
    return sections


def _require_cases(kind: str, paths: list[Path]) -> None:
    if len(paths) < MIN_CASES_PER_CLASS:
        raise EvalsError(
            f"{kind} 类语料仅 {len(paths)} 例，需 ≥ {MIN_CASES_PER_CLASS}（{CASES_DIR}）"
        )


def _case_result(
    case_id: str,
    issues: list[ValidationIssue],
    **extra: object,
) -> dict[str, object]:
    errors = [issue for issue in issues if issue.severity == "error"]
    error_types = sorted({issue.type for issue in errors})
    result: dict[str, object] = {
        "case": case_id,
        "ok": not errors,
        "error_types": error_types,
    }
    if error_types:
        result["reason"] = "存在 error：" + "、".join(error_types)
    result.update(extra)
    return result


def _render_theme(
    semantic_markdown: str,
    *,
    title: str,
    digest: str,
    theme_name: str,
) -> tuple[list[ValidationIssue], int, int]:
    """组件门 → 渲染 + 定向修复（内含 HTML 门）→ 公众号门；返回 (issues, 字节数, 轮数)。"""
    theme = load_theme(theme_name)
    issues: list[ValidationIssue] = list(lint_components(semantic_markdown, theme))
    if any(issue.severity == "error" for issue in issues):
        return issues, 0, 0
    ast = parse(semantic_markdown, title=title, digest=digest)
    renderer = HtmlRenderer(theme)
    outcome = repair_rendered(ast, renderer)
    issues.extend(outcome.report.errors)
    issues.extend(outcome.report.warnings)
    full_html = renderer.wrap_document(outcome.html)
    issues.extend(lint_gzh(full_html))
    return issues, len(full_html.encode("utf-8")), outcome.rounds


def _framework_artifacts(
    text: str,
    fw_id: str,
    meta: dict,
) -> tuple[ResearchResult, ContentBrief, ArticleDraft]:
    claims = {fact_id: claim for fact_id, claim, _ in meta["facts"]}
    sources = [
        Source(source_id=source_id, title=title, url=url)
        for source_id, title, url in meta["sources"]
    ]
    facts = [
        Fact(fact_id=fact_id, claim=claim, source_ids=source_ids)
        for fact_id, claim, source_ids in meta["facts"]
    ]
    research = ResearchResult(topic=meta["topic"], sources=sources, facts=facts)
    sections = _sections_from_markdown(text, claims)
    if not sections:
        raise EvalsError(f"框架语料 {fw_id} 缺少 ## 二级标题，无法生成大纲小节")
    word_count = estimate_word_count(text)
    brief = ContentBrief(
        topic=meta["topic"],
        goal=meta["goal"],
        framework=fw_id,
        word_target=min(10000, max(200, word_count)),
        sections=sections,
    )
    draft = ArticleDraft(
        title=_extract_title(text),
        digest=_make_digest(text),
        framework=fw_id,
        markdown=text,
        word_count=word_count,
        fact_ids=sorted({fid for section in sections for fid in section.fact_ids}),
        humanize=analyze_text(text),
    )
    return research, brief, draft


def run_humanize_eval() -> list[dict]:
    results: list[dict] = []
    for kind in ("good", "ai_flavor"):
        paths = sorted(CASES_DIR.glob(f"{kind}_*.md"))
        _require_cases(f"humanize/{kind}", paths)
        for path in paths:
            report = analyze_text(path.read_text(encoding="utf-8"))
            error_count = sum(1 for item in report.issues if item["severity"] == "error")
            if kind == "good":
                ok = report.humanize_score >= GOOD_CASE_MIN_SCORE and report.passed
                reason = (
                    ""
                    if ok
                    else f"好文得分 {report.humanize_score}，需 ≥ {GOOD_CASE_MIN_SCORE} 且通过"
                    f"（passed={report.passed}）"
                )
            else:
                ok = report.humanize_score <= AI_FLAVOR_MAX_SCORE and error_count > 0
                reason = (
                    ""
                    if ok
                    else f"AI 味文得分 {report.humanize_score}，需 ≤ {AI_FLAVOR_MAX_SCORE} "
                    f"且检出 error 级问题（实际 {error_count} 条）"
                )
            case: dict = {
                "case": path.stem,
                "kind": kind,
                "score": report.humanize_score,
                "passed": report.passed,
                "error_count": error_count,
                "ok": ok,
            }
            if reason:
                case["reason"] = reason
            results.append(case)
    return results


def run_content_gate_eval() -> list[dict]:
    results: list[dict] = []
    for kind in ("structure_missing", "good"):
        paths = sorted(CASES_DIR.glob(f"{kind}_*.md"))
        _require_cases(f"content_gate/{kind}", paths)
        for path in paths:
            text = path.read_text(encoding="utf-8")
            draft = ArticleDraft(
                title=STRUCTURE_MISSING_TITLES.get(path.stem) or _extract_title(text),
                digest=_make_digest(text),
                markdown=text,
                word_count=estimate_word_count(text),
            )
            errors = [issue for issue in lint_content(draft) if issue.severity == "error"]
            error_types = sorted({issue.type for issue in errors})
            if kind == "structure_missing":
                hit = any(
                    issue.type == "structure_incomplete" and issue.property == "markdown"
                    for issue in errors
                )
                ok = hit
                reason = "" if hit else "未检出 structure_incomplete（markdown）错误"
            else:
                ok = not errors
                reason = "" if ok else "正向样例存在 error：" + "、".join(error_types)
            case: dict = {
                "case": path.stem,
                "kind": kind,
                "error_types": error_types,
                "ok": ok,
            }
            if reason:
                case["reason"] = reason
            results.append(case)
    return results


def run_render_eval() -> list[dict]:
    nested_path = CASES_DIR / "render_nested.md"
    if not nested_path.is_file():
        raise EvalsError(f"嵌套渲染语料缺失：{nested_path}")
    nested_doc = nested_path.read_text(encoding="utf-8")
    nested_title = _extract_title(nested_doc)
    nested_digest = _make_digest(nested_doc)
    results = []
    for doc, title, digest, prefix in (
        (RENDER_DOC, _extract_title(RENDER_DOC), _make_digest(RENDER_DOC), "render"),
        (nested_doc, nested_title, nested_digest, "render_nested"),
    ):
        for theme_name in BUILTIN_THEMES:
            issues, html_bytes, rounds = _render_theme(
                doc, title=title, digest=digest, theme_name=theme_name
            )
            results.append(
                _case_result(
                    f"{prefix}/{theme_name}",
                    issues,
                    theme=theme_name,
                    html_bytes=html_bytes,
                    repair_rounds=rounds,
                )
            )
    return results


def run_framework_eval() -> list[dict]:
    results: list[dict] = []
    for index, fw_id in enumerate(FRAMEWORK_IDS):
        path = FRAMEWORKS_DIR / f"{fw_id}.md"
        if not path.is_file():
            raise EvalsError(f"框架语料缺失：{path}")
        meta = _FRAMEWORK_META.get(fw_id)
        if meta is None:
            raise EvalsError(f"框架 {fw_id} 缺少元数据（_FRAMEWORK_META）")
        text = path.read_text(encoding="utf-8")
        research, brief, draft = _framework_artifacts(text, fw_id, meta)
        content_issues = lint_content(draft, research=research, brief=brief)
        semantic_markdown = f"{text.rstrip()}\n\n:::note\n{meta['note']}\n:::\n"
        theme_name = BUILTIN_THEMES[index % len(BUILTIN_THEMES)]
        render_issues, html_bytes, rounds = _render_theme(
            semantic_markdown,
            title=draft.title,
            digest=draft.digest,
            theme_name=theme_name,
        )
        results.append(
            _case_result(
                f"framework/{fw_id}",
                content_issues + render_issues,
                framework=fw_id,
                theme=theme_name,
                html_bytes=html_bytes,
                repair_rounds=rounds,
            )
        )
    return results


def run_all_evals() -> dict[str, object]:
    suites = {
        "humanize": run_humanize_eval(),
        "content_gate": run_content_gate_eval(),
        "render": run_render_eval(),
        "framework": run_framework_eval(),
    }
    total = sum(len(cases) for cases in suites.values())
    failed = [str(case["case"]) for cases in suites.values() for case in cases if not case["ok"]]
    return {
        "version": "0.3",
        "suites": suites,
        "summary": {
            "total": total,
            "failed": len(failed),
            "failed_cases": failed,
            "passed": not failed,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="run_evals.py",
        description="运行四类 eval（humanize / content_gate / render / framework），输出 JSON 报告",
    )
    parser.add_argument("-o", "--output", type=Path, default=REPORT_PATH, help="JSON 报告写出路径")
    parser.add_argument("--no-write", action="store_true", help="只在 stdout 输出报告，不写文件")
    args = parser.parse_args(argv)

    try:
        report = run_all_evals()
    except EvalsError as exc:
        print(f"evals: 语料 / 环境错误 - {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(
            f"evals: 运行异常（按语料 / 环境错误处理）- {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2

    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if not args.no_write:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")

    summary = report["summary"]
    if summary["passed"]:
        verdict = f"evals: PASS - {summary['total']}/{summary['total']} 用例通过"
    else:
        verdict = (
            f"evals: FAIL - {summary['total'] - summary['failed']}/{summary['total']} 用例通过；"
            f"失败：{'、'.join(summary['failed_cases'])}"
        )
    print(verdict, file=sys.stderr)
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
