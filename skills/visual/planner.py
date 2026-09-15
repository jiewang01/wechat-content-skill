"""Visual Planner：为 ContentPackage 自动生成配图计划。

功能：
- 分析 semantic_markdown 内容
- 识别适合插入图片的章节/概念点
- 为每个配图点生成 LLM 提示词
- 输出 ImageSpec 列表到 VisualPlan

使用方式：
    from core.artifacts.models import ContentPackage
    from renderer.ast import parse
    from skills.visual.planner import VisualPlanner
    
    ast = parse(package.semantic_markdown, title=package.title, digest=package.digest)
    planner = VisualPlanner(ast, package.title)
    images = planner.generate_specs(num_images=3)
"""

import re
from typing import Optional


class VisualPlanner:
    """基于 AST 的图文匹配规划器。"""

    def __init__(self, ast, title: str):
        self.ast = ast
        self.title = title
        self.sections: list[dict] = []

    def extract_sections(self) -> list[dict]:
        """提取文档结构（标题、段落、关键概念）。"""
        sections = []
        current_heading = "引言"
        bullet_count = 0

        for node in self.ast.nodes:
            kind = node.type
            text = node.text.strip() if hasattr(node, 'text') and node.text else ""

            if kind == "heading":
                current_heading = text
                sections.append({
                    "position": len(sections) + 1,
                    "type": "heading",
                    "title": text,
                    "content": "",
                })
            elif kind == "paragraph" and text:
                # 检测关键概念（包含术语、数字、对比等）
                concepts = self._extract_concepts(text)
                if concepts or not text.endswith("。"):
                    sections[-1]["content"] += text + "\n"
                    if concepts:
                        sections.append({
                            "position": len(sections) + 1,
                            "type": "concept",
                            "parent_heading": current_heading,
                            "concepts": concepts,
                            "content": text[:80] + "...",
                        })
            elif kind == "card":
                sections.append({
                    "position": len(sections) + 1,
                    "type": "comparison",
                    "title": node.title or "对比表",
                    "items": node.items if hasattr(node, 'items') else [],
                    "content": str(node.items)[:100],
                })
            elif kind == "list":
                bullet_count += len(node.items) if hasattr(node, 'items') else 0
                if bullet_count >= 3:
                    sections.append({
                        "position": len(sections) + 1,
                        "type": "checklist",
                        "item_count": bullet_count,
                        "content": "要点清单（{} 项）".format(bullet_count),
                    })
                    bullet_count = 0

        return sections

    def _extract_concepts(self, text: str) -> list[str]:
        """从段落中提取视觉化概念（专业术语、数字指标、对比关系）。"""
        concepts = []
        # 中文术语（4-10 字的专有名词模式）
        terms = re.findall(r'[\u4e00-\u9fff]{4,10}', text)
        # 英文术语
        terms.extend(re.findall(r'[A-Za-z][a-zA-Z0-9_-]{2,}', text))
        # 数字指标
        numbers = re.findall(r'\d+[%\s]?|\d+\.?\d*[kM]?', text)
        
        for t in terms[:3]:  # 最多取 3 个概念
            if len(t) >= 4 and t not in ['因此', '所以', '而且', '然而']:
                concepts.append(t)
        for n in numbers[:2]:
            concepts.append(n)
            
        return list(set(concepts))[:5]

    def generate_prompt(self, section: dict, idx: int) -> str:
        """为单个配图点生成 AI 绘画提示词（中文 SDXL 风格）。"""
        section_type = section.get("type", "concept")
        
        # 封面图
        if idx == 0:
            return (
                f"【封面】专业文章封面，{self.title}，扁平化设计，科技风格，"
                f"深蓝色背景配金色点缀，留白用于文字排版，2.35:1 横版构图"
            )
        
        # 根据类型生成不同提示词
        prompts = {
            "concept": self._prompt_for_concept(section),
            "heading": self._prompt_for_heading(section),
            "comparison": self._prompt_for_comparison(section),
            "checklist": self._prompt_for_checklist(section),
        }
        
        return prompts.get(section_type, self._default_prompt(section))

    def _prompt_for_concept(self, section: dict) -> str:
        """概念类配图：图标化展示核心术语。"""
        concepts = section.get("concepts", [])
        parent = section.get("parent_heading", "")
        
        if not concepts:
            return f"{parent}概念示意图，简约线条风格，单色渐变，留白充足"
        
        key_term = concepts[0] if isinstance(concepts, list) else concepts
        
        style = [
            "图标化设计",
            "扁平化插画",
            "浅灰色背景配品牌色高亮",
            "适合公众号阅读",
            "2:3 竖版构图",
        ]
        
        return f"{key_term}概念示意，{', '.join(style)}"

    def _prompt_for_heading(self, section: dict) -> str:
        """章节配图：抽象概念可视化。"""
        title = section.get("title", "")
        content = section.get("content", "")[:100]
        
        keywords = re.findall(r'[\u4e00-\u9fff]{2,}|[A-Za-z]{3,}', content)
        key_words = keywords[:3] if keywords else [title[:5]]
        
        styles = {
            "问题": "困惑/疑问，迷雾中的探照灯，冷暖对比",
            "解法": "解决方案，清晰的光路，明亮通透",
            "原理": "机制示意，齿轮/箭头/流程，科技感",
            "总结": "要点归纳，列表/金字塔，结构化",
        }
        
        mood = ""
        for keyword in key_words:
            for k, v in styles.items():
                if k in keyword:
                    mood = v
                    break
        
        mood_style = f"，{mood}" if mood else "，抽象几何，现代简约"
        
        return f"{title}配图，{mood_style}，柔和配色，信息图表风格"

    def _prompt_for_comparison(self, section: dict) -> str:
        """对比类配图：表格或分屏对比。"""
        items = section.get("items", [])
        title = section.get("title", "对比")
        
        item_names = []
        for item in items:
            if isinstance(item, str):
                parts = item.split(":")
                if parts:
                    item_names.append(parts[0].strip())
        
        left = item_names[0] if item_names else "方案 A"
        right = item_names[1] if len(item_names) > 1 else "方案 B"
        
        return (
            f"左右分屏对比图，左侧{left}右侧{right}，"
            f"中间分割线，对称构图，色块区分，数据可视化风格"
        )

    def _prompt_for_checklist(self, section: dict) -> str:
        """清单类配图：步骤图或对勾列表。"""
        count = section.get("item_count", 3)
        
        return (
            f"{count}步流程图或检查清单，对勾标记，进度指示，"
            f"模块化设计，适合长图传播，浅色底深色字"
        )

    def _default_prompt(self, section: dict) -> str:
        """默认提示词模板。"""
        title = section.get("title", "")
        content_preview = section.get("content", "")[:30]
        
        return f"{title}相关插图，简洁明快，{content_preview}，信息可视化，白色背景"

    def generate_specs(self, num_images: Optional[int] = None) -> list[dict]:
        """生成配图规格列表。"""
        sections = self.extract_sections()
        
        # 过滤出需要配图的位置（排除纯 heading 类型）
        target_sections = [
            s for s in sections 
            if s.get("type") in ["concept", "heading", "comparison", "checklist"]
        ]
        
        # 如果用户指定数量，按优先级选取
        if num_images:
            # 优先选择 concept 和 comparison 类型
            sorted_sections = sorted(
                target_sections,
                key=lambda s: (0 if s["type"] in ["concept", "comparison"] else 1, s["position"])
            )
            selected = sorted_sections[:num_images]
        else:
            selected = target_sections
        
        specs = []
        for idx, section in enumerate(selected):
            specs.append({
                "position": section["position"],
                "purpose": section.get("title", section.get("parent_heading", "配图")),
                "prompt": self.generate_prompt(section, idx),
                "asset_path": "",  # 留空，待生图 API 填充
            })
        
        # 确保至少有一张封面图
        if not any(s.get("purpose") == "封面" for s in specs):
            specs.insert(0, {
                "position": 1,
                "purpose": "封面",
                "prompt": self.generate_prompt({"title": self.title}, 0),
                "asset_path": "",
            })
        
        return specs
