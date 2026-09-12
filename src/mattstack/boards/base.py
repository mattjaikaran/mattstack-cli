"""Pluggable kanban board backend protocol (design doc §2)."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class BoardBackend(Protocol):
    """Interface every board adapter implements."""

    def create_task(
        self, title: str, project: str | None = None, **fields: Any
    ) -> dict[str, Any]: ...

    def list_tasks(self, **filters: Any) -> list[dict[str, Any]]: ...

    def update_task(self, task_id: str, **updates: Any) -> dict[str, Any]: ...

    def transition_task(
        self, task_id: str, target_status: str, comment: str = ""
    ) -> dict[str, Any]: ...

    def claim_task(self, task_id: str, agent_name: str) -> dict[str, Any]: ...

    def get_next_task(self, agent_name: str, project: str | None = None) -> dict[str, Any]: ...

    def link_pr(
        self, task_id: str, pr_url: str, pr_number: int | None = None
    ) -> dict[str, Any]: ...


class StubBoardBackend:
    """Base for backends that exist as clearly-marked stubs.

    Every method raises :class:`NotImplementedError` until the real adapter is
    built (design doc §2 open questions). Subclasses set ``backend_name``.
    """

    backend_name = "stub"

    def create_task(self, title: str, project: str | None = None, **fields: Any) -> dict[str, Any]:
        raise self._error()

    def list_tasks(self, **filters: Any) -> list[dict[str, Any]]:
        raise self._error()

    def update_task(self, task_id: str, **updates: Any) -> dict[str, Any]:
        raise self._error()

    def transition_task(
        self, task_id: str, target_status: str, comment: str = ""
    ) -> dict[str, Any]:
        raise self._error()

    def claim_task(self, task_id: str, agent_name: str) -> dict[str, Any]:
        raise self._error()

    def get_next_task(self, agent_name: str, project: str | None = None) -> dict[str, Any]:
        raise self._error()

    def link_pr(self, task_id: str, pr_url: str, pr_number: int | None = None) -> dict[str, Any]:
        raise self._error()

    def _error(self) -> NotImplementedError:
        return NotImplementedError(
            f"{type(self).__name__} is not implemented yet. Use board.backend: 'axis' or 'none'."
        )
