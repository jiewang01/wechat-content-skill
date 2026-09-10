"""确定性 AI 味检测器（内容质量门的 Attacker 引擎）。"""

from skills.content.humanize.detector import HumanizeRules, analyze_text, load_rules

__all__ = ["HumanizeRules", "analyze_text", "load_rules"]
