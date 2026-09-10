from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ConfigDict, Field

from core.artifacts.models import (
    ARTIFACT_MODELS,
    ArtifactBase,
    AttackReport,
    DefenseReport,
    Verdict,
)
from core.state.machine import WorkflowState

A = TypeVar("A", bound=ArtifactBase)


class AdversarialRound(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gate: str
    round: int = Field(ge=1, le=3)
    attack_report: AttackReport
    defense_report: DefenseReport | None = None
    verdict: Verdict


class Checkpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    intent: str = ""
    state: WorkflowState = WorkflowState.INIT
    theme: str = "default"
    account: str = "default"
    artifacts: dict[str, str] = Field(
        default_factory=dict,
        description="Artifact name -> filename inside the run directory.",
    )
    adversarial_history: list[AdversarialRound] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CheckpointStore:
    def __init__(self, base_dir: Path | str = Path("outputs")) -> None:
        self.base_dir = Path(base_dir)

    def run_dir(self, run_id: str) -> Path:
        return self.base_dir / run_id

    def _ensure_run_dir(self, run_id: str) -> Path:
        run_dir = self.run_dir(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    def save_artifact(self, run_id: str, name: str, artifact: A) -> Path:
        if name not in ARTIFACT_MODELS:
            raise ValueError(f"unknown artifact name: {name}")
        run_dir = self._ensure_run_dir(run_id)
        path = run_dir / f"{name}.json"
        _atomic_write_json(path, artifact.model_dump(mode="json"))
        return path

    def load_artifact(self, run_id: str, name: str, model_cls: type[A]) -> A:
        path = self.run_dir(run_id) / f"{name}.json"
        if not path.exists():
            raise FileNotFoundError(f"artifact not found: {path}")
        return model_cls.model_validate_json(path.read_text(encoding="utf-8"))

    def load_artifact_by_name(self, run_id: str, name: str) -> ArtifactBase:
        model_cls = ARTIFACT_MODELS.get(name)
        if model_cls is None:
            raise ValueError(f"unknown artifact name: {name}")
        return self.load_artifact(run_id, name, model_cls)

    def save_checkpoint(self, checkpoint: Checkpoint) -> Path:
        checkpoint.updated_at = datetime.now(UTC)
        run_dir = self._ensure_run_dir(checkpoint.run_id)
        path = run_dir / "checkpoint.json"
        _atomic_write_json(path, checkpoint.model_dump(mode="json"))
        return path

    def load_checkpoint(self, run_id: str) -> Checkpoint:
        path = self.run_dir(run_id) / "checkpoint.json"
        if not path.exists():
            raise FileNotFoundError(f"checkpoint not found: {path}")
        return Checkpoint.model_validate_json(path.read_text(encoding="utf-8"))


def _atomic_write_json(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


__all__ = ["AdversarialRound", "Checkpoint", "CheckpointStore"]
