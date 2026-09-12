"""Tests for the pluggable deploy-notification backends (design doc §4)."""

from __future__ import annotations

import json

import httpx
import pytest

from mattstack.config_file import BoardConfig, MattstackConfig, NotifyConfig
from mattstack.notify import (
    DeployEnvelope,
    HermesNotifier,
    NullNotifier,
    TelegramNotifier,
    WebhookNotifier,
    build_notifier,
    send_deploy_notification,
)


def test_envelope_to_dict() -> None:
    envelope = DeployEnvelope(app="myapp", commit="abc123", env="staging")

    assert envelope.to_dict() == {
        "event": "deploy_complete",
        "app": "myapp",
        "commit": "abc123",
        "env": "staging",
        "frontend_url": "",
        "backend_url": "",
    }


def test_build_notifier_none() -> None:
    config = MattstackConfig(notify=NotifyConfig(backend="none"))
    assert isinstance(build_notifier(config), NullNotifier)


def test_build_notifier_webhook(monkeypatch) -> None:
    monkeypatch.setenv("MY_HOOK", "https://example.com/hook")
    config = MattstackConfig(notify=NotifyConfig(backend="webhook", webhook_url_env="MY_HOOK"))

    notifier = build_notifier(config)

    assert isinstance(notifier, WebhookNotifier)
    assert notifier.url == "https://example.com/hook"  # type: ignore[attr-defined]


def test_build_notifier_webhook_missing_url(monkeypatch) -> None:
    monkeypatch.delenv("MISSING_HOOK", raising=False)
    config = MattstackConfig(notify=NotifyConfig(backend="webhook", webhook_url_env="MISSING_HOOK"))

    with pytest.raises(ValueError, match="MISSING_HOOK"):
        build_notifier(config)


def test_build_notifier_telegram(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("MY_CHAT", "chat-1")
    config = MattstackConfig(notify=NotifyConfig(backend="telegram", chat_id_env="MY_CHAT"))

    assert isinstance(build_notifier(config), TelegramNotifier)


def test_build_notifier_hermes() -> None:
    config = MattstackConfig(
        notify=NotifyConfig(backend="hermes"),
        board=BoardConfig(url="https://axis.example.com/api/v1"),
    )

    notifier = build_notifier(config)

    assert isinstance(notifier, HermesNotifier)
    assert notifier.url == "https://axis.example.com/api/v1/deploy_webhook"  # type: ignore[attr-defined]


def test_build_notifier_unknown() -> None:
    config = MattstackConfig(notify=NotifyConfig(backend="bogus"))
    with pytest.raises(ValueError, match="Unknown notify backend"):
        build_notifier(config)


def test_webhook_notifier_posts_envelope() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    notifier = WebhookNotifier("https://example.com/hook", client=client)

    notifier.send(DeployEnvelope(app="myapp", commit="abc123"))

    assert str(calls[0].url) == "https://example.com/hook"
    body = json.loads(calls[0].content)
    assert body["event"] == "deploy_complete"
    assert body["app"] == "myapp"
    assert body["commit"] == "abc123"


def test_telegram_notifier_sends_message() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"ok": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    notifier = TelegramNotifier("token123", "chat456", client=client)

    notifier.send(DeployEnvelope(app="myapp", commit="abc123", env="prod"))

    assert str(calls[0].url) == "https://api.telegram.org/bottoken123/sendMessage"
    body = json.loads(calls[0].content)
    assert body["chat_id"] == "chat456"
    assert "myapp" in body["text"]
    assert "abc123" in body["text"]


def test_send_deploy_notification_none_is_noop() -> None:
    config = MattstackConfig(notify=NotifyConfig(backend="none"))
    send_deploy_notification(config, DeployEnvelope(app="myapp"))
