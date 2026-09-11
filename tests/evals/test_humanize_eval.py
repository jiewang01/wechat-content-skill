"""humanize eval 回归测试（v0.2 计划 N3-T2 / N3-T5）：语料判分 + eval CLI 报告。

对应 DoD：
- 好文 humanize_score ≥ GOOD_CASE_MIN_SCORE 且 passed；
- AI 味文被检出（分数 ≤ AI_FLAVOR_MAX_SCORE 且存在 error 级问题）；
- 结构缺失文被 lint_content 检出 structure_incomplete，好文走正向路径零 error；
- CLI 一键运行输出 JSON 报告（默认路径 outputs/evals/），退出码语义正确。

判分逻辑全部集中在 scripts/run_evals.py，本文件只做断言、不重复实现。
"""

import json

import scripts.run_evals as evals
from tests.evals.thresholds import AI_FLAVOR_MAX_SCORE, GOOD_CASE_MIN_SCORE


def test_good_cases_score_high_and_pass():
    results = evals.run_humanize_eval()
    good = [case for case in results if case["kind"] == "good"]
    assert len(good) == 2
    for case in good:
        assert case["ok"], case
        assert case["score"] >= GOOD_CASE_MIN_SCORE
        assert case["passed"] is True


def test_ai_flavor_cases_detected():
    results = evals.run_humanize_eval()
    flagged = [case for case in results if case["kind"] == "ai_flavor"]
    assert len(flagged) == 2
    for case in flagged:
        assert case["ok"], case
        assert case["score"] <= AI_FLAVOR_MAX_SCORE
        assert case["error_count"] > 0


def test_content_gate_structure_missing_detected():
    results = evals.run_content_gate_eval()
    missing = [case for case in results if case["kind"] == "structure_missing"]
    assert len(missing) == 2
    for case in missing:
        assert case["ok"], case
        assert "structure_incomplete" in case["error_types"]


def test_content_gate_good_cases_clean():
    results = evals.run_content_gate_eval()
    good = [case for case in results if case["kind"] == "good"]
    assert len(good) == 2
    for case in good:
        assert case["ok"], case
        assert case["error_types"] == []


def test_default_report_path_under_outputs():
    assert evals.REPORT_PATH == evals.ROOT / "outputs" / "evals" / "evals-report.json"


def test_main_writes_full_json_report(tmp_path):
    report_path = tmp_path / "evals-report.json"
    assert evals.main(["-o", str(report_path)]) == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["summary"] == {
        "total": 20,
        "failed": 0,
        "failed_cases": [],
        "passed": True,
    }
    assert {suite: len(cases) for suite, cases in report["suites"].items()} == {
        "humanize": 4,
        "content_gate": 4,
        "render": 5,
        "framework": 7,
    }


def test_main_no_write_keeps_report_off_disk(tmp_path):
    report_path = tmp_path / "evals-report.json"
    assert evals.main(["-o", str(report_path), "--no-write"]) == 0
    assert not report_path.exists()


def test_main_exit_one_on_regression(monkeypatch):
    monkeypatch.setattr(evals, "run_render_eval", lambda: [{"case": "render/broken", "ok": False}])
    assert evals.main(["--no-write"]) == 1


def test_main_exit_two_on_env_error(monkeypatch):
    def _missing_corpus():
        raise evals.EvalsError("框架语料缺失")

    monkeypatch.setattr(evals, "run_framework_eval", _missing_corpus)
    assert evals.main(["--no-write"]) == 2
