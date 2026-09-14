"""渲染 CLI：ContentPackage JSON → 公众号 HTML + WechatDocument JSON。

用法：
    python scripts/render.py <content_package.json> -o wechat.html
    python scripts/render.py pkg.json -o out.html --doc-output doc.json --theme default
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse
import json

from core.artifacts.models import ContentPackage, WechatDocument
from renderer.ast import ParseError, parse
from renderer.html import HtmlRenderer
from renderer.themes import ThemeError, load_theme


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="render.py", description="ContentPackage JSON → 公众号 HTML"
    )
    parser.add_argument("input", help="ContentPackage JSON 文件路径")
    parser.add_argument(
        "-o", "--output", default=None, help="HTML 输出路径（默认 <输入目录>/wechat.html）"
    )
    parser.add_argument(
        "--doc-output",
        default=None,
        help="WechatDocument JSON 输出路径（默认：<输入目录>/wechat_document.json）",
    )
    parser.add_argument("--theme", default=None, help="主题名（默认：取包内 theme 字段）")
    parser.add_argument(
        "--include-title",
        action="store_true",
        help="把标题渲染进正文（默认不渲染：公众号标题栏单独展示）",
    )
    args = parser.parse_args()

    in_path = Path(args.input)
    if not in_path.is_file():
        print(f"错误：输入文件不存在：{in_path}", file=sys.stderr)
        return 1
    out_dir = in_path.parent
    html_path = Path(args.output) if args.output else out_dir / "wechat.html"
    doc_path = Path(args.doc_output) if args.doc_output else out_dir / "wechat_document.json"

    try:
        package = ContentPackage.model_validate(json.loads(in_path.read_text(encoding="utf-8")))
    except Exception as exc:
        print(f"错误：ContentPackage 校验失败：{exc}", file=sys.stderr)
        return 1

    try:
        ast = parse(package.semantic_markdown, title=package.title, digest=package.digest)
        theme = load_theme(args.theme or package.theme or "default")
        renderer = HtmlRenderer(theme)
        html = renderer.render(ast, include_title=args.include_title)
        plain_text = renderer.render_plain_text(ast)
    except (ParseError, ThemeError) as exc:
        print(f"错误：渲染失败：{exc}", file=sys.stderr)
        return 1

    cover_asset = package.visual.cover.asset_path if package.visual.cover else ""
    image_assets = [img.asset_path for img in package.visual.images if img.asset_path]
    document = WechatDocument(
        run_id=package.run_id,
        title=package.title,
        digest=package.digest,
        html=html,
        plain_text=plain_text,
        cover_asset=cover_asset,
        image_assets=image_assets,
        size_bytes=len(html.encode("utf-8")),
    )

    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html, encoding="utf-8-sig")
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    doc_path.write_text(
        json.dumps(document.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"wrote {html_path} ({document.size_bytes} bytes)")
    print(f"wrote {doc_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
