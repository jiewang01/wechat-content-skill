"""eval 判分阈值集中定义（v0.2 计划 N3 风险缓解：阈值有争议时只改这里）。

判分逻辑见 scripts/run_evals.py，本模块只放数字、不放逻辑；
及格线本身（60 分）以 skills/content/humanize/rules.yaml 的 pass_score 为准，
此处只定义 eval 语料专用的高线 / 低线与语料规模下限。
"""

# 好文基线：必须 passed 且分数不低于此值（满分 100，留出规则微调余量）
GOOD_CASE_MIN_SCORE = 90

# AI 味文判定：分数不高于此值，且存在 error 级问题（黑名单短语 / 成对句式）
AI_FLAVOR_MAX_SCORE = 50

# 每类语料最少例数（N3-T1 DoD：好文 / AI 味文 / 结构缺失文每类 ≥ 2 例）
MIN_CASES_PER_CLASS = 2
