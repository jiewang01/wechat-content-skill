"""CLI 单测：scripts/validate.py / scripts/lint.py（蓝图十章，计划 M4-T5）。

子进程级黑盒测试，只锁对外契约（与冒烟矩阵一一对应）：
- 退出码：0 = 通过；1 = 检出错误；2 = 输入 / 环境错误；
- stdout：结构化 ErrorReport（ValidationReport JSON）；
- stderr：一行人类可读摘要；
- -o / --html-output 产物文件。

另补三路分支：--max-html-bytes 体积门禁、未知主题 exit 2、
lint.py 的 .json → ContentPackage 回退分派（H5：无 PASS 不发布）。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from core.utils import estimate_word_count

REPO = Path(__file__).resolve().parent.parent.parent

CLEAN_MARKDOWN = """# 手冲咖啡入门

## 冲煮步骤

把水烧到 92 度。
磨豆 20 克。
闷蒸 30 秒。

## 小结
"""

SEMANTIC_MARKDOWN = (
    "# 手冲咖啡入门\n\n"
    ":::note\n水温影响萃取率。\n:::\n\n"
    ':::quote cite="《冲煮手册》"\n闷蒸 30 秒，之后分两段注水。\n:::\n\n'
    ':::callout type="warning" title="注意"\n水温别超过 96 度。\n:::\n\n'
    ':::card title="参数速记" footer="共 3 条"\n- 水温 92 度\n- 粉水比 1 比 15\n- 闷蒸 30 秒\n:::'
)


def run_cli(script: str, *argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(REPO / "scripts" / script), *argv],
        capture_output=True,
        text=True,
        cwd=REPO,
        check=False,
    )


def write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def report_of(result: subprocess.CompletedProcess[str]) -> dict:
    return json.loads(result.stdout)


def error_types(report: dict) -> list[str]:
    return [issue["type"] for issue in report["errors"]]


def make_package(semantic_markdown: str) -> dict:
    return {"title": "手冲咖啡入门", "semantic_markdown": semantic_markdown, "theme": "default"}


def test_validate_good_package_passes_and_writes_artifacts(tmp_path):
    pkg = write_json(tmp_path / "good.json", make_package(SEMANTIC_MARKDOWN))
    report_file = tmp_path / "report.json"
    html_file = tmp_path / "out.html"
    result = run_cli(
        "validate.py", str(pkg), "-o", str(report_file), "--html-output", str(html_file)
    )
    assert result.returncode == 0
    assert "PASS" in result.stderr
    report = report_of(result)
    assert report["status"] == "passed"
    assert report["gate"] == "publish"
    assert report["errors"] == []
    assert json.loads(report_file.read_text(encoding="utf-8"))["status"] == "passed"
    html = html_file.read_text(encoding="utf-8-sig")
    assert html.startswith('<section style="')
    assert html.rstrip().endswith("</section>")


def test_validate_unknown_marker_fails_fast_at_content_gate(tmp_path):
    pkg = write_json(
        tmp_path / "bad_marker.json",
        make_package("# 手冲咖啡入门\n\n:::spoiler\n内容\n:::"),
    )
    result = run_cli("validate.py", str(pkg))
    assert result.returncode == 1
    assert "FAIL" in result.stderr
    report = report_of(result)
    assert report["status"] == "failed"
    assert report["gate"] == "content"
    assert error_types(report) == ["unknown_component"]


def test_validate_http_image_blocked_at_publish_gate(tmp_path):
    pkg = write_json(
        tmp_path / "bad_img.json",
        make_package("# 手冲咖啡入门\n\n![配图](http://example.com/i.png)"),
    )
    result = run_cli("validate.py", str(pkg))
    assert result.returncode == 1
    report = report_of(result)
    assert report["status"] == "failed"
    assert report["gate"] == "publish"
    assert error_types(report) == ["insecure_image_url"]


def test_validate_html_size_limit_flag(tmp_path):
    pkg = write_json(tmp_path / "good.json", make_package(SEMANTIC_MARKDOWN))
    result = run_cli("validate.py", str(pkg), "--max-html-bytes", "16")
    assert result.returncode == 1
    report = report_of(result)
    assert report["gate"] == "publish"
    assert error_types(report) == ["html_too_large"]


def test_validate_missing_input_exits_2(tmp_path):
    result = run_cli("validate.py", str(tmp_path / "nope.json"))
    assert result.returncode == 2
    assert "不存在" in result.stderr


def test_validate_invalid_package_json_exits_2(tmp_path):
    pkg = write_json(tmp_path / "broken.json", {"title": "缺语义正文"})
    result = run_cli("validate.py", str(pkg))
    assert result.returncode == 2
    assert "ContentPackage" in result.stderr


def test_validate_unknown_theme_exits_2(tmp_path):
    pkg = write_json(tmp_path / "good.json", make_package(SEMANTIC_MARKDOWN))
    result = run_cli("validate.py", str(pkg), "--theme", "nope")
    assert result.returncode == 2
    assert "主题加载失败" in result.stderr


def test_lint_clean_draft_passes(tmp_path):
    draft = write_json(
        tmp_path / "draft.json",
        {
            "title": "手冲咖啡入门",
            "markdown": CLEAN_MARKDOWN,
            "word_count": estimate_word_count(CLEAN_MARKDOWN),
        },
    )
    report_file = tmp_path / "report.json"
    result = run_cli("lint.py", str(draft), "-o", str(report_file))
    assert result.returncode == 0
    report = report_of(result)
    assert report["status"] == "passed"
    assert report["gate"] == "content"
    assert report["errors"] == []
    assert report_file.is_file()


def test_lint_empty_title_draft_fails(tmp_path):
    draft = write_json(
        tmp_path / "draft.json",
        {"title": "", "markdown": CLEAN_MARKDOWN, "word_count": 26},
    )
    result = run_cli("lint.py", str(draft))
    assert result.returncode == 1
    report = report_of(result)
    assert report["gate"] == "content"
    assert error_types(report) == ["structure_incomplete"]


def test_lint_package_json_falls_back_to_component_lint(tmp_path):
    pkg = write_json(
        tmp_path / "pkg.json",
        make_package("# 手冲咖啡入门\n\n:::spoiler\n内容\n:::"),
    )
    result = run_cli("lint.py", str(pkg))
    assert result.returncode == 1
    report = report_of(result)
    assert report["gate"] == "content"
    assert error_types(report) == ["unknown_component"]


def test_lint_html_file_checks_both_layers(tmp_path):
    page = tmp_path / "page.html"
    page.write_text("<div>x</div>", encoding="utf-8")
    result = run_cli("lint.py", str(page))
    assert result.returncode == 1
    report = report_of(result)
    assert report["gate"] == "publish"
    assert error_types(report) == ["forbidden_tag"]


def test_lint_markdown_file_unclosed_marker(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text("# 手冲咖啡入门\n\n:::note\n未闭合的说明", encoding="utf-8")
    result = run_cli("lint.py", str(doc))
    assert result.returncode == 1
    report = report_of(result)
    assert report["gate"] == "content"
    assert error_types(report) == ["unclosed_marker"]


def test_lint_unsupported_suffix_exits_2(tmp_path):
    note = tmp_path / "note.txt"
    note.write_text("普通文本", encoding="utf-8")
    result = run_cli("lint.py", str(note))
    assert result.returncode == 2
    assert "不支持的文件类型" in result.stderr
