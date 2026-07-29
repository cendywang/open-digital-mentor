from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.config import get_settings
from app.main import create_app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ODM_MODE", "mock")
    monkeypatch.setenv("ODM_MAX_CONNECTIONS_PER_IP", "5")
    monkeypatch.setenv(
        "ODM_ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    )
    monkeypatch.setenv("ODM_LOG_MESSAGE_BODY", "false")
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as test_client:
            yield test_client
    finally:
        get_settings.cache_clear()


def test_http_cors_allows_local_frontend_and_rejects_other_origins(client):
    allowed = client.get("/health", headers={"Origin": "http://localhost:3000"})
    denied = client.get("/health", headers={"Origin": "https://untrusted.example"})

    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "access-control-allow-origin" not in denied.headers


def test_websocket_rejects_browser_origin_outside_allowlist(client):
    with pytest.raises(WebSocketDisconnect) as rejected:
        with client.websocket_connect(
            "/ws", headers={"Origin": "https://untrusted.example"}
        ) as websocket:
            websocket.receive_json()

    assert rejected.value.code == 1008


def test_websocket_accepts_allowed_browser_origin(client):
    with client.websocket_connect(
        "/ws", headers={"Origin": "http://localhost:3000"}
    ) as websocket:
        assert websocket.receive_json()["type"] == "hello"


def test_100kb_websocket_message_is_rejected_without_reaching_pipeline(client):
    with client.websocket_connect("/ws") as websocket:
        websocket.receive_json()
        websocket.send_text("x" * (100 * 1024))
        error = websocket.receive_json()

    assert error["type"] == "error"
    assert error["code"] == "message_too_long"
    assert error["turn_id"] == ""


def test_sixth_connection_from_same_ip_is_rejected(client):
    with ExitStack() as stack:
        sockets = [stack.enter_context(client.websocket_connect("/ws")) for _ in range(5)]
        assert all(socket.receive_json()["type"] == "hello" for socket in sockets)

        with pytest.raises(WebSocketDisconnect) as rejected:
            with client.websocket_connect("/ws") as extra:
                extra.receive_json()

    assert rejected.value.code == 1008


def test_default_logs_record_length_but_not_question_body(client, caplog):
    question = "private-body-marker-should-not-be-logged"
    caplog.set_level("INFO", logger="odm")

    with client.websocket_connect("/ws") as websocket:
        websocket.receive_json()
        websocket.send_json(
            {"type": "ask", "turn_id": "security-log-test", "question": question}
        )
        for _ in range(200):
            if websocket.receive_json()["type"] == "turn.end":
                break

    assert question not in caplog.text
    assert f"question received ({len(question)} chars)" in caplog.text
