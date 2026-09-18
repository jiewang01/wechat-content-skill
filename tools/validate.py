#!/usr/bin/env python3
"""广告 Skill 数据校验脚本：校验 tests/cases 下的用例及其内嵌 AdTask/Evidence/Decision 是否符合 Schema。

用法:
    python3 tools/validate.py              # 校验全部用例
    python3 tools/validate.py task-003     # 校验单个或名称前缀

仅做顶层 required 校验（完整 JSON Schema 校验可后续引入 ajv/jsonschema 库）。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASE_DIR = ROOT / "tests" / "cases"
SCHEMA_DIR = ROOT / "schemas"


def load_schema(name: str) -> dict | None:
    p = SCHEMA_DIR / f"{name}.schema.json"
    return json.load(open(p)) if p.exists() else None


def check_required(data, schema, label) -> list[str]:
    if schema is None:
        return []
    errors = []
    for key in schema.get("required", []):
        if key not in data:
            errors.append(f"{label}: missing required '{key}'")
    return errors


def validate_case(path: Path) -> list[str]:
    errors = []
    try:
        case = json.load(open(path))
    except json.JSONDecodeError as e:
        return [f"{path.name}: INVALID JSON: {e}"]

    errors += check_required(case, load_schema("test-case"), path.name)

    adtask = case.get("expected_adtask")
    if adtask:
        errors += check_required(adtask, load_schema("ad-task"), f"{path.name} adtask")

    for ev in case.get("expected_evidence", []):
        errors += check_required(ev, load_schema("evidence"), f"{path.name} evidence")

    decision = case.get("expected_decision")
    if decision:
        errors += check_required(decision, load_schema("decision"), f"{path.name} decision")
        for r in decision.get("reasons", []):
            if not r.get("evidence_refs"):
                errors.append(f"{path.name}: reason without evidence_refs")
        conf = decision.get("confidence", {})
        if conf.get("value") is not None and not conf.get("evidence_refs"):
            errors.append(f"{path.name}: confidence without evidence_refs")

    return errors


def main() -> int:
    pattern = sys.argv[1] if len(sys.argv) > 1 else "task-"
    paths = sorted(CASE_DIR.glob("task-*.json"))
    selected = [p for p in paths if pattern in p.name] or paths

    all_errors = []
    for p in selected:
        all_errors += validate_case(p)

    print(f"checked: {len(selected)} case(s)")
    for e in all_errors:
        print("ERROR:", e)
    result = "PASS" if not all_errors else "FAIL"
    print("RESULT:", result)
    return 0 if result == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())