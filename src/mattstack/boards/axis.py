"""Axis board backend (HTTP, design doc §2 endpoint map)."""

from __future__ import annotations

from typing import Any, cast

import httpx

from mattstack.boards.base import BoardBackend


class AxisBackend(BoardBackend):
    """Board backend wrapping the Axis REST API."""

    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        project_slug: str = "default",
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.project_slug = project_slug
        self._client = client or httpx.Client(timeout=30.0)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _post(self, path: str, payload: dict[str, Any]) -> Any:
        response = self._client.post(
            f"{self.base_url}{path}", json=payload, headers=self._headers()
        )
        response.raise_for_status()
        return response.json()

    def _patch(self, path: str, payload: dict[str, Any]) -> Any:
        response = self._client.patch(
            f"{self.base_url}{path}", json=payload, headers=self._headers()
        )
        response.raise_for_status()
        return response.json()

    def create_task(self, title: str, project: str | None = None, **fields: Any) -> dict[str, Any]:
        task: dict[str, Any] = {"title": title, "project": project or self.project_slug}
        task.update(fields)
        return cast(dict[str, Any], self._post("/tasks/batch", {"tasks": [task]}))

    def list_tasks(self, **filters: Any) -> list[dict[str, Any]]:
        result = self._post("/tasks/search", dict(filters))
        if isinstance(result, list):
            return cast(list[dict[str, Any]], result)
        if isinstance(result, dict) and "tasks" in result:
            tasks = result["tasks"]
            return cast(list[dict[str, Any]], tasks) if isinstance(tasks, list) else []
        return []

    def update_task(self, task_id: str, **updates: Any) -> dict[str, Any]:
        task: dict[str, Any] = {"id": task_id}
        task.update(updates)
        return cast(dict[str, Any], self._patch("/tasks/bulk-update", {"tasks": [task]}))

    def transition_task(
        self, task_id: str, target_status: str, comment: str = ""
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._post(
                f"/tasks/{task_id}/transition",
                {"status": target_status, "comment": comment},
            ),
        )

    def claim_task(self, task_id: str, agent_name: str) -> dict[str, Any]:
        return cast(dict[str, Any], self._post(f"/tasks/{task_id}/claim", {"agent": agent_name}))

    def get_next_task(self, agent_name: str, project: str | None = None) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._post(
                "/tasks/next", {"agent": agent_name, "project": project or self.project_slug}
            ),
        )

    def link_pr(self, task_id: str, pr_url: str, pr_number: int | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"pr_url": pr_url}
        if pr_number is not None:
            payload["pr_number"] = pr_number
        return cast(dict[str, Any], self._post(f"/tasks/{task_id}/link-pr", payload))
