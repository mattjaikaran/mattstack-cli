"""Hermes board backend — NOT IMPLEMENTED (stub).

Hermes' kanban is unresolved (design doc open question 1), so this stays an
explicit not-implemented contract. Use ``board.backend: axis`` or ``none``.
``notify.backend: hermes`` does not use this module; it posts to ``HERMES_URL``.
"""

from __future__ import annotations

from mattstack.boards.base import StubBoardBackend


class HermesBackend(StubBoardBackend):
    """Stub: every method raises NotImplementedError."""

    backend_name = "hermes"
