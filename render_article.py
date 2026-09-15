"""简单脚本：将 skill_article.md 渲染为 HTML"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from renderer.ast import parse
from renderer.html import HtmlRenderer
from renderer.themes import load_theme

# 读取 MD 文件
md_path = Path("/workspace/skill_article.md")
markdown_content = md_path.read_text(encoding="utf-8")

# 提取标题和正文
lines = markdown_content.strip().split("\n")
title = lines[0].lstrip("# ").strip() if lines else "公众号文章"
body = "\n".join(lines[1:]).strip()

print(f"标题：{title}")
print(f"\n正文预览（前 200 字符）：\n{body[:200]}...")

# 解析并渲染
try:
    ast = parse(body, title=title)
    theme = load_theme("default")
    renderer = HtmlRenderer(theme)
    html = renderer.render(ast, include_title=False)
    
    # 输出 HTML
    output_path = Path("/workspace/skill_article_rendered.html")
    output_path.write_text(html, encoding="utf-8-sig")
    
    print(f"\n✓ HTML 已生成：{output_path.absolute()}")
    print(f"文件大小：{output_path.stat().st_size} bytes")
    
except Exception as e:
    print(f"\n✗ 渲染失败：{e}", file=sys.stderr)
    sys.exit(1)
