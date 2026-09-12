"""Pluggable deploy notifications (design doc §4)."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any, Protocol

import httpx

from mattstack.config_file import MattstackConfig


@dataclass
class DeployEnvelope:
    """The JSON envelope POSTed on deploy completion."""

    event: str = "deploy_complete"
    app: str = ""
    commit: str = ""
    env: str = "production"
    frontend_url: str = ""
    backend_url: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class Notifier(Protocol):
    """Interface every notify backend implements."""

    def send(self, envelope: DeployEnvelope) -> None: ...


class NullNotifier:
    """No-op notifier for notify.backend: none."""

    def send(self, envelope: DeployEnvelope) -> None:
        return None


class WebhookNotifier:
    """POSTs the raw envelope to a generic webhook URL."""

    def __init__(self, url: str, client: httpx.Client | None = None) -> None:
        self.url = url
        self._client = client or httpx.Client(timeout=30.0)
        self._owns_client = client is None

    def send(self, envelope: DeployEnvelope) -> None:
        response = self._client.post(self.url, json=envelope.to_dict())
        response.raise_for_status()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


class HermesNotifier(WebhookNotifier):
    """Posts the envelope to Axis's deploy_webhook; Hermes relays to Telegram."""


class TelegramNotifier:
    """Sends a formatted message directly to Telegram."""

    def __init__(self, token: str, chat_id: str, client: httpx.Client | None = None) -> None:
        self.token = token
        self.chat_id = chat_id
        self._client = client or httpx.Client(timeout=30.0)
        self._owns_client = client is None

    def send(self, envelope: DeployEnvelope) -> None:
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        response = self._client.post(
            url,
            json={"chat_id": self.chat_id, "text": _format_message(envelope)},
        )
        response.raise_for_status()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


def _format_message(envelope: DeployEnvelope) -> str:
    lines = [
        f"{envelope.event}: {envelope.app}",
        f"commit: {envelope.commit}",
        f"env: {envelope.env}",
    ]
    if envelope.frontend_url:
        lines.append(f"frontend: {envelope.frontend_url}")
    if envelope.backend_url:
        lines.append(f"backend: {envelope.backend_url}")
    return "\n".join(lines)


def build_notifier(config: MattstackConfig) -> Notifier:
    """Build the configured notify backend from a :class:`MattstackConfig`."""
    backend = (config.notify.backend or "none").strip().lower()

    if backend == "none":
        return NullNotifier()

    if backend == "webhook":
        url = os.environ.get(config.notify.webhook_url_env or "DEPLOY_WEBHOOK_URL", "")
        if not url:
            raise ValueError(
                f"notify.backend is 'webhook' but {config.notify.webhook_url_env} is unset"
            )
        return WebhookNotifier(url)

    if backend == "telegram":
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.environ.get(config.notify.chat_id_env or "TELEGRAM_CHAT_ID", "")
        if not token or not chat_id:
            raise ValueError(
                "notify.backend is 'telegram' but TELEGRAM_BOT_TOKEN or "
                f"{config.notify.chat_id_env} is unset"
            )
        return TelegramNotifier(token, chat_id)

    if backend == "hermes":
        base = (config.board.url or "").rstrip("/")
        if not base:
            raise ValueError("notify.backend is 'hermes' but board.url is unset")
        return HermesNotifier(f"{base}/deploy_webhook")

    raise ValueError(f"Unknown notify backend: {config.notify.backend!r}")


def send_deploy_notification(config: MattstackConfig, envelope: DeployEnvelope) -> None:
    """Build the configured notifier and send ``envelope``."""
    notifier: Any = build_notifier(config)
    try:
        notifier.send(envelope)
    finally:
        close = getattr(notifier, "close", None)
        if callable(close):
            close()
