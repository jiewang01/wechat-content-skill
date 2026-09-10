import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json

from core.artifacts.models import ARTIFACT_MODELS


def main() -> int:
    out_dir = Path(__file__).resolve().parent.parent / "schemas"
    out_dir.mkdir(exist_ok=True)
    for name, model in ARTIFACT_MODELS.items():
        schema = model.model_json_schema()
        path = out_dir / f"{name}.schema.json"
        path.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
