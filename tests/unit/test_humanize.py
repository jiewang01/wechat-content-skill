"""Humanize 检测器单测（M2-T7）：黑名单命中、评分区间、pass/fail 阈值。"""

from pathlib import Path

import yaml

from skills.content.humanize import analyze_text, load_rules


def test_clean_text_passes_with_full_score():
    report = analyze_text("今天跑了测试。全部通过。没踩坑。")
    assert report.humanize_score == 100
    assert report.passed is True
    assert report.issues == []


def test_blacklist_phrase_hits_and_scores():
    report = analyze_text("首先，我们来看。这个工具真的能赋能开发者。")
    assert report.humanize_score == 84
    assert report.passed is True
    phrase_issues = [i for i in report.issues if i["type"] == "blacklist_phrase"]
    assert {i["evidence"] for i in phrase_issues} == {"首先，", "赋能"}
    assert all(i["severity"] == "error" for i in phrase_issues)
    assert all("message" in i for i in phrase_issues)


def test_fail_below_pass_score():
    report = analyze_text("首先，其次，最后，再者，众所周知，毫无疑问。")
    assert report.humanize_score == 52
    assert report.passed is False


def test_paired_phrase_in_same_sentence():
    report = analyze_text("随着大模型的发展，写作方式也在变化。")
    assert report.humanize_score == 92
    issue = next(i for i in report.issues if i["type"] == "paired_phrase")
    assert issue["severity"] == "error"
    assert "随着" in issue["message"] and "的发展" in issue["message"]


def test_long_sentence_warning():
    report = analyze_text("abcdefghij" * 7)
    assert report.humanize_score == 97
    issue = next(i for i in report.issues if i["type"] == "long_sentence")
    assert issue["severity"] == "warning"
    assert "60" in issue["message"] and "70" in issue["message"]


def test_avg_sentence_length_warning():
    report = analyze_text("。".join(["abcdefghij" * 4] * 3) + "。")
    types = {i["type"] for i in report.issues}
    assert types == {"avg_sentence_length"}
    assert report.humanize_score == 95


def test_avg_skipped_below_min_sentences():
    report = analyze_text("。".join(["abcdefghij" * 4] * 2) + "。")
    assert report.issues == []
    assert report.humanize_score == 100


def test_long_paragraph_without_avg_trigger():
    report = analyze_text("。".join(["abcdefghij" * 3] * 7) + "。")
    types = {i["type"] for i in report.issues}
    assert types == {"long_paragraph"}
    assert report.humanize_score == 97


def test_repetition_ngram():
    report = analyze_text("数据导入失败。数据导入失败。数据导入失败。")
    rep = [i for i in report.issues if i["type"] == "repetition"]
    assert rep, "重复片段应被标记"
    assert all(len(i["evidence"]) == 5 for i in rep)
    assert all(i["severity"] == "warning" for i in rep)


def test_score_clamped_to_zero():
    report = analyze_text("众所周知。" * 13)
    assert report.humanize_score == 0
    assert report.passed is False


def test_code_fence_and_image_excluded():
    markdown = (
        "正文第一句，干净利落。\n\n"
        "```python\n"
        'print("首先，赋能")\n'
        "```\n\n"
        "![](https://example.com/赋能.png)\n"
    )
    report = analyze_text(markdown)
    assert report.issues == []
    assert report.humanize_score == 100


def test_custom_rules_without_code_change(tmp_path: Path):
    rules_file = tmp_path / "rules.yaml"
    rules_file.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "pass_score": 95,
                "limits": {"max_sentence_chars": 10},
                "phrases": ["黑名单词"],
                "pairs": [],
            }
        ),
        encoding="utf-8",
    )
    rules = load_rules(rules_file)
    assert rules.pass_score == 95
    assert rules.limits.max_sentence_chars == 10

    hit = analyze_text("这句话里有黑名单词。", rules)
    assert any(i["type"] == "blacklist_phrase" for i in hit.issues)
    assert hit.humanize_score == 92
    assert hit.passed is False

    over_limit = analyze_text("abcdefghijk", rules)
    assert any(i["type"] == "long_sentence" for i in over_limit.issues)
    assert over_limit.humanize_score == 97

    default_rules = analyze_text("这句话里有黑名单词。")
    assert default_rules.humanize_score == 100


def test_default_rules_packaged():
    rules = load_rules()
    assert rules.pass_score == 60
    assert rules.limits.max_sentence_chars == 60
    assert "首先，" in rules.phrases
    assert rules.version == 2
    assert "不得不说" in rules.phrases
    assert ("一方面", "另一方面") in rules.pairs
    assert "但是" in rules.connectives
    assert rules.limits.max_connectives_per_kilo == 12
    assert rules.limits.min_chars_for_rhythm == 150
    assert rules.limits.min_sentences_for_rhythm == 6
    assert rules.limits.max_repeated_opening_run == 3
    assert rules.limits.min_sentence_length_std == 3.5
    assert rules.penalties.connective_density == 3
    assert rules.penalties.opening_monotony == 3
    assert rules.penalties.sentence_length_uniformity == 3


def _relaxed_rhythm_rules():
    """放宽节奏门限的默认规则副本：让短文本也能进入节奏维度（pydantic 模型可变）。"""
    rules = load_rules()
    rules.limits.min_chars_for_rhythm = 20
    rules.limits.min_sentences_for_rhythm = 3
    return rules


def test_connective_density_warning():
    text = (
        "先做梳理。但是工具确实很关键，选错了会拖慢整个团队。"
        "然而人才是胜负手。因此别急着下单采购。"
    )
    report = analyze_text(text, _relaxed_rhythm_rules())
    types = {i["type"] for i in report.issues}
    assert types == {"connective_density"}
    issue = report.issues[0]
    assert issue["severity"] == "warning"
    assert issue["evidence"].endswith("处/千字")
    assert report.humanize_score == 97


def test_opening_monotony_warning():
    text = "我们看数据。我们谈结论。我们给一份完整、可落地、经得起复盘检验的改造方案。"
    report = analyze_text(text, _relaxed_rhythm_rules())
    types = {i["type"] for i in report.issues}
    assert types == {"opening_monotony"}
    issue = report.issues[0]
    assert issue["severity"] == "warning"
    assert issue["evidence"] == "我们"
    assert "连续 3 句" in issue["message"]
    assert report.humanize_score == 97


def test_sentence_length_uniformity_warning():
    text = "今天跑了十公里。中午吃了两碗面。晚上看了三集剧。"
    report = analyze_text(text, _relaxed_rhythm_rules())
    types = {i["type"] for i in report.issues}
    assert types == {"sentence_length_uniformity"}
    issue = report.issues[0]
    assert issue["severity"] == "warning"
    assert issue["evidence"] == "0.0 字"
    assert report.humanize_score == 97


def test_rhythm_dimensions_skip_short_text():
    """默认门限（CJK≥150 且句数≥6）下，短文即使句首单调也不触发节奏维度。"""
    text = "我们先看数据。我们再谈结论。我们最后给方案。我们都要复盘。"
    report = analyze_text(text)
    assert report.issues == []
    assert report.humanize_score == 100


def test_opening_strips_inline_marks():
    """句首的加粗等行内标记不计入句首提取，**我们** 与 我们 视为同一开头。"""
    text = "**我们**认为流程重要，这事反复验证过。我们见过太多反例。我们建议先做梳理。"
    report = analyze_text(text, _relaxed_rhythm_rules())
    types = {i["type"] for i in report.issues}
    assert types == {"opening_monotony"}
    assert report.issues[0]["evidence"] == "我们"


def test_custom_rules_v2_fields(tmp_path: Path):
    rules_file = tmp_path / "rules.yaml"
    rules_file.write_text(
        yaml.safe_dump(
            {
                "version": 2,
                "limits": {
                    "min_chars_for_rhythm": 20,
                    "min_sentences_for_rhythm": 3,
                    "max_connectives_per_kilo": 10,
                },
                "connectives": ["因此"],
                "phrases": [],
                "pairs": [],
            }
        ),
        encoding="utf-8",
    )
    rules = load_rules(rules_file)
    assert rules.version == 2
    assert rules.limits.max_connectives_per_kilo == 10
    assert rules.connectives == ["因此"]
    assert rules.penalties.connective_density == 3

    text = "今天天气确实很好，适合出门走走。因此我们临时决定去公园。早上人少。"
    report = analyze_text(text, rules)
    types = {i["type"] for i in report.issues}
    assert types == {"connective_density"}
    assert report.humanize_score == 97
