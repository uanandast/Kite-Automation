import asyncio
from unittest.mock import MagicMock

from webapp.runtime import DOCKER_WEBSITE_URL, TradingRuntime
from webapp.settings import Settings
from webapp.state import RuntimeState


def _make_runtime(environment: str) -> TradingRuntime:
    settings = Settings(
        environment=environment,
        dashboard_username="",
        dashboard_password="",
        session_secret="",
    )
    state = RuntimeState()
    return TradingRuntime(settings, state)


def test_lifespan_telegram_docker_notification(monkeypatch):
    runtime = _make_runtime("docker")
    mock_send = MagicMock()
    monkeypatch.setattr("webapp.runtime.send_telegram", mock_send)
    monkeypatch.setattr(runtime, "initialize", MagicMock())
    monkeypatch.setattr(runtime, "start_workers", MagicMock())

    async def _test():
        async with runtime.lifespan():
            pass

    asyncio.run(_test())

    mock_send.assert_called_once()
    message = mock_send.call_args[0][0]
    assert "🚀 Trading bot started successfully on Docker" in message
    assert DOCKER_WEBSITE_URL in message
    assert "https://uanandast.duckdns.org" in message


def test_lifespan_telegram_docker_notification_custom_url(monkeypatch):
    runtime = _make_runtime("production")
    mock_send = MagicMock()
    monkeypatch.setattr("webapp.runtime.send_telegram", mock_send)
    monkeypatch.setattr(runtime, "initialize", MagicMock())
    monkeypatch.setattr(runtime, "start_workers", MagicMock())
    monkeypatch.setenv("DASHBOARD_URL", "https://custom.duckdns.org")

    async def _test():
        async with runtime.lifespan():
            pass

    asyncio.run(_test())

    mock_send.assert_called_once()
    message = mock_send.call_args[0][0]
    assert "🚀 Trading bot started successfully on Docker" in message
    assert "https://custom.duckdns.org" in message


def test_lifespan_telegram_local_notification(monkeypatch):
    runtime = _make_runtime("local")
    mock_send = MagicMock()
    monkeypatch.setattr("webapp.runtime.send_telegram", mock_send)
    monkeypatch.setattr(runtime, "initialize", MagicMock())
    monkeypatch.setattr(runtime, "start_workers", MagicMock())

    async def _test():
        async with runtime.lifespan():
            pass

    asyncio.run(_test())

    mock_send.assert_called_once()
    message = mock_send.call_args[0][0]
    assert "🚀 Trading bot started successfully on MacBook" in message
    assert "duckdns" not in message
