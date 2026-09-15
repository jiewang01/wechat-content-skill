from __future__ import annotations

from enum import StrEnum


class WorkflowState(StrEnum):
    INIT = "INIT"
    RESEARCHING = "RESEARCHING"
    RESEARCHED = "RESEARCHED"
    DRAFTING = "DRAFTING"
    DRAFTED = "DRAFTED"
    ANNOTATING = "ANNOTATING"
    ANNOTATED = "ANNOTATED"
    STYLING = "STYLING"
    STYLED = "STYLED"
    IMAGERY = "IMAGERY"
    RENDERING = "RENDERING"
    VALIDATING = "VALIDATING"
    REPAIRING = "REPAIRING"
    VALIDATED = "VALIDATED"
    READY_TO_PUBLISH = "READY_TO_PUBLISH"
    UPLOADING = "UPLOADING"
    DRAFT_CREATED = "DRAFT_CREATED"
    PUBLISHED = "PUBLISHED"
    REJECTED = "REJECTED"


TRANSITIONS: dict[WorkflowState, frozenset[WorkflowState]] = {
    WorkflowState.INIT: frozenset({WorkflowState.RESEARCHING}),
    WorkflowState.RESEARCHING: frozenset({WorkflowState.RESEARCHED}),
    WorkflowState.RESEARCHED: frozenset({WorkflowState.DRAFTING}),
    WorkflowState.DRAFTING: frozenset({WorkflowState.DRAFTED}),
    WorkflowState.DRAFTED: frozenset({WorkflowState.ANNOTATING}),
    WorkflowState.ANNOTATING: frozenset({WorkflowState.ANNOTATED}),
    WorkflowState.ANNOTATED: frozenset({WorkflowState.STYLING}),
    WorkflowState.STYLING: frozenset({WorkflowState.STYLED}),
    WorkflowState.STYLED: frozenset({WorkflowState.IMAGERY}),
    WorkflowState.IMAGERY: frozenset({WorkflowState.RENDERING}),
    WorkflowState.RENDERING: frozenset({WorkflowState.VALIDATING}),
    WorkflowState.VALIDATING: frozenset({WorkflowState.REPAIRING, WorkflowState.VALIDATED}),
    WorkflowState.REPAIRING: frozenset(
        {WorkflowState.VALIDATING, WorkflowState.VALIDATED, WorkflowState.REJECTED}
    ),
    WorkflowState.VALIDATED: frozenset({WorkflowState.READY_TO_PUBLISH}),
    WorkflowState.READY_TO_PUBLISH: frozenset({WorkflowState.UPLOADING}),
    WorkflowState.UPLOADING: frozenset({WorkflowState.DRAFT_CREATED}),
    WorkflowState.DRAFT_CREATED: frozenset({WorkflowState.PUBLISHED}),
    WorkflowState.PUBLISHED: frozenset(),
    WorkflowState.REJECTED: frozenset(),
}

TERMINAL_STATES = frozenset(
    {WorkflowState.PUBLISHED, WorkflowState.REJECTED, WorkflowState.DRAFT_CREATED}
)


STATE_MIGRATIONS: dict[str, str] = {
    "DESIGNING": "ANNOTATING",
}
"""Legacy checkpoint state names mapped to their successor states.

Old runs persisted before the style/imagery split resume at the earliest
affected state so that annotation -> style -> imagery are re-executed.
"""


class IllegalTransitionError(Exception):
    pass


class PublishGateError(IllegalTransitionError):
    pass


class StateMachine:
    def __init__(self, state: WorkflowState = WorkflowState.INIT) -> None:
        if isinstance(state, str):
            state = STATE_MIGRATIONS.get(state, state)
        self._state = WorkflowState(state)

    @property
    def state(self) -> WorkflowState:
        return self._state

    def can(self, target: WorkflowState) -> bool:
        return target in TRANSITIONS[self._state]

    def allowed(self) -> frozenset[WorkflowState]:
        return TRANSITIONS[self._state]

    def transition(
        self,
        target: WorkflowState,
        *,
        publish_verdict_pass: bool | None = None,
    ) -> WorkflowState:
        target = WorkflowState(target)
        if not self.can(target):
            raise IllegalTransitionError(
                f"illegal workflow transition: {self._state.value} -> {target.value} "
                f"(allowed: {sorted(s.value for s in self.allowed())})"
            )
        if self._state is WorkflowState.VALIDATED and target is WorkflowState.READY_TO_PUBLISH:
            if publish_verdict_pass is not True:
                raise PublishGateError(
                    "VALIDATED -> READY_TO_PUBLISH requires a PASS verdict on the publish gate "
                    "(hard constraint H5: never publish without Judge PASS)"
                )
        self._state = target
        return self._state


__all__ = [
    "IllegalTransitionError",
    "PublishGateError",
    "STATE_MIGRATIONS",
    "TERMINAL_STATES",
    "TRANSITIONS",
    "StateMachine",
    "WorkflowState",
]
