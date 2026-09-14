"""预览 CLI：把公众号 HTML 片段（或 ContentPackage JSON）包进手机框本地预览。

用法：
    python scripts/preview.py <wechat.html>
    python scripts/preview.py <content_package.json> --theme default

注意：预览页里的 <style> 仅用于浏览器本地展示，绝不进入发布产物。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse
import html as html_mod
import json

_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · 公众号预览</title>
<style>
body {{ margin:0; padding:24px 12px; background:#f2f3f5; display:flex; justify-content:center; }}
.phone {{ width:375px; max-width:100%; background:#ffffff; border-radius:16px;
         box-shadow:0 4px 24px rgba(0,0,0,0.12); overflow:hidden; }}
.phone-status {{ height:28px; background:#ffffff; border-bottom:1px solid #f0f0f0; }}
.phone-title {{ padding:20px 16px 4px; font-size:20px; font-weight:600; color:#333333;
               line-height:1.4;
               font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif; }}
.phone-meta {{ padding:4px 16px 12px; font-size:13px; color:#888888;
              font-family:-apple-system,'PingFang SC',sans-serif; }}
.phone-body {{ padding:0 16px 32px; }}
</style>
</head>
<body>
<div class="phone">
  <div class="phone-status"></div>
  <div class="phone-title">{title}</div>
  <div class="phone-meta">{meta}</div>
  <div class="phone-body">
{fragment}
  </div>
</div>
</body>
</html>
"""


def _render_package(path: Path, theme_name: str | None) -> tuple[str, str, str]:
    from core.artifacts.models import ContentPackage
    from renderer.html import HtmlRenderer
    from renderer.themes import load_theme

    package = ContentPackage.model_validate(json.loads(path.read_text(encoding="utf-8")))
    from renderer.ast import parse

    ast = parse(package.semantic_markdown, title=package.title, digest=package.digest)
    renderer = HtmlRenderer(load_theme(theme_name or package.theme or "default"))
    fragment = renderer.render(ast)
    meta = package.digest or f"主题：{package.theme or 'default'}"
    return fragment, package.title, meta


def _title_from_sibling_doc(html_path: Path) -> tuple[str, str]:
    """HTML 片段不携带标题；若同目录存在 wechat_document.json 则恢复标题与摘要。"""
    doc_path = html_path.parent / "wechat_document.json"
    if not doc_path.is_file():
        return "", ""
    try:
        doc = json.loads(doc_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "", ""
    return str(doc.get("title", "")), str(doc.get("digest", ""))


def main() -> int:
    parser = argparse.ArgumentParser(prog="preview.py", description="生成带手机框的本地预览页")
    parser.add_argument("input", help="公众号 HTML 片段或 ContentPackage JSON")
    parser.add_argument(
        "-o", "--output", default=None, help="输出路径（默认 <输入名>.preview.html）"
    )
    parser.add_argument("--theme", default=None, help="主题名（仅 JSON 输入时生效）")
    parser.add_argument("--title", default=None, help="覆盖预览页标题")
    args = parser.parse_args()

    in_path = Path(args.input)
    if not in_path.is_file():
        print(f"错误：输入文件不存在：{in_path}", file=sys.stderr)
        return 1

    if in_path.suffix.lower() == ".json":
        try:
            fragment, title, meta = _render_package(in_path, args.theme)
        except Exception as exc:
            print(f"错误：预览渲染失败：{exc}", file=sys.stderr)
            return 1
    else:
        fragment = in_path.read_text(encoding="utf-8-sig")
        title, meta = _title_from_sibling_doc(in_path)
        if not title:
            title = in_path.stem
        if not meta:
            meta = "本地 HTML 片段预览"

    if args.title:
        title = args.title

    page = _PAGE_TEMPLATE.format(
        title=html_mod.escape(title), meta=html_mod.escape(meta), fragment=fragment
    )
    out_path = (
        Path(args.output) if args.output else in_path.with_name(in_path.stem + ".preview.html")
    )
    out_path.write_text(page, encoding="utf-8")
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
