from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from core.artifacts.models import ArtifactBase, AttackReport, DefenseReport, Verdict
from core.state.checkpoint import (
    AdversarialRound,
    Checkpoint,
    CheckpointStore,
    RunPreferences,
)
from core.state.machine import (
    TERMINAL_STATES,
    PublishGateError,
    StateMachine,
    WorkflowState,
)


def new_run_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return f"run_{stamp}_{uuid.uuid4().hex[:6]}"


@dataclass(frozen=True)
class Stage:
    entry: WorkflowState
    func: Callable[[WorkflowRun], None]


class WorkflowRun:
    def __init__(
        self,
        run_id: str,
        intent: str,
        store: CheckpointStore,
        theme: str = "default",
        account: str = "default",
        preferences: RunPreferences | None = None,
    ) -> None:
        self.run_id = run_id
        self.intent = intent
        self.store = store
        self.machine = StateMachine(WorkflowState.INIT)
        self.checkpoint = Checkpoint(
            run_id=run_id,
            intent=intent,
            state=WorkflowState.INIT,
            theme=theme,
            account=account,
            preferences=preferences or RunPreferences(),
        )
        self._artifacts: dict[str, ArtifactBase] = {}

    @property
    def state(self) -> WorkflowState:
        return self.machine.state

    def advance(self, target: WorkflowState, *, publish_verdict_pass: bool | None = None) -> None:
        self.machine.transition(target, publish_verdict_pass=publish_verdict_pass)
        self.checkpoint.state = self.machine.state
        self.store.save_checkpoint(self.checkpoint)

    def save(self, name: str, artifact: ArtifactBase) -> Path:
        artifact.run_id = self.run_id
        self._artifacts[name] = artifact
        path = self.store.save_artifact(self.run_id, name, artifact)
        self.checkpoint.artifacts[name] = path.name
        self.store.save_checkpoint(self.checkpoint)
        return path

    def artifact(self, name: str) -> ArtifactBase:
        if name not in self._artifacts:
            if name not in self.checkpoint.artifacts:
                raise KeyError(f"artifact '{name}' has not been produced in run {self.run_id}")
            self._artifacts[name] = self.store.load_artifact_by_name(self.run_id, name)
        return self._artifacts[name]

    def artifact_typed(self, name: str, model_cls: type) -> object:
        return model_cls.model_validate(self.artifact(name).model_dump())

    def record_round(
        self, attack: AttackReport, defense: DefenseReport | None, verdict: Verdict
    ) -> None:
        self.checkpoint.adversarial_history.append(
            AdversarialRound(
                gate=attack.gate,
                round=attack.round,
                attack_report=attack,
                defense_report=defense,
                verdict=verdict,
            )
        )
        self.store.save_checkpoint(self.checkpoint)

    @property
    def publish_gate_passed(self) -> bool:
        return any(
            r.gate == "publish" and r.verdict.decision == "PASS"
            for r in self.checkpoint.adversarial_history
        )

    @classmethod
    def resume(cls, run_id: str, store: CheckpointStore) -> WorkflowRun:
        checkpoint = store.load_checkpoint(run_id)
        run = cls(
            run_id=run_id,
            intent=checkpoint.intent,
            store=store,
            theme=checkpoint.theme,
            account=checkpoint.account,
            preferences=checkpoint.preferences,
        )
        run.machine = StateMachine(checkpoint.state)
        run.checkpoint = checkpoint
        return run


class Orchestrator:
    def __init__(self, store: CheckpointStore, stages: Sequence[Stage]) -> None:
        self.store = store
        self._stages = {stage.entry: stage for stage in stages}

    def start(
        self,
        intent: str,
        run_id: str | None = None,
        theme: str = "default",
        account: str = "default",
        preferences: RunPreferences | None = None,
    ) -> WorkflowRun:
        run = WorkflowRun(
            run_id=run_id or new_run_id(),
            intent=intent,
            store=self.store,
            theme=theme,
            account=account,
            preferences=preferences,
        )
        self.store.save_checkpoint(run.checkpoint)
        return self._drive(run)

    def resume(self, run_id: str) -> WorkflowRun:
        run = WorkflowRun.resume(run_id, self.store)
        return self._drive(run)

    def _drive(self, run: WorkflowRun) -> WorkflowRun:
        while run.state not in TERMINAL_STATES:
            stage = self._stages.get(run.state)
            if stage is None:
                break
            stage.func(run)
        return run


__all__ = ["Orchestrator", "PublishGateError", "Stage", "WorkflowRun", "new_run_id"]
