"""FastAPI entrypoint.

Endpoints: `GET /health` and `WS /ws` are the entire external surface. The
service has no tool, browser, filesystem, or code-execution interface.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.pipeline import MentorPipeline
from app.protocol import (
    PROTOCOL_VERSION,
    AskMessage,
    ErrorCode,
    ErrorEvent,
    HelloEvent,
    InterruptedEvent,
    StopMessage,
)
from app.providers import build_llm, build_retriever, build_tts

log = logging.getLogger("odm")

MAX_WS_MESSAGE_BYTES = 64 * 1024


def _configure_logging(settings: Settings) -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        stream=sys.stdout,
    )


def _startup_banner(settings: Settings, app: FastAPI) -> None:
    retriever = app.state.retriever
    size = getattr(retriever, "size", None)
    entries = size if size is not None else "built-in"

    log.info("=" * 68)
    log.info("Open Digital Mentor — backend (protocol v%d)", PROTOCOL_VERSION)
    if settings.is_mock:
        log.info("MODE: MOCK — no outbound network requests will be made")
    else:
        log.info("MODE: LIVE — real providers are configured")
    log.info(
        "providers: llm=%s  tts=%s  retriever=%s  (knowledge entries: %s)",
        app.state.llm.name,
        app.state.tts.name,
        retriever.name,
        entries,
    )
    log.info("listening on %s:%s   cors allowlist: %s", settings.host, settings.port,
             ", ".join(settings.origins))

    if settings.binds_publicly():
        log.warning("!" * 68)
        log.warning("ODM_HOST=%s exposes this service beyond localhost.", settings.host)
        log.warning("This service has no authentication. Put it behind a reverse")
        log.warning("proxy with auth before letting anything untrusted reach it.")
        log.warning("!" * 68)

    for problem in settings.validation_errors():
        log.error("config: %s", problem)
    log.info("=" * 68)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    _configure_logging(settings)

    app.state.settings = settings
    app.state.retriever = build_retriever(settings)
    app.state.llm = build_llm(settings)
    app.state.tts = build_tts(settings)
    app.state.connections_by_ip = defaultdict(int)

    _startup_banner(settings, app)
    try:
        yield
    finally:
        for provider in (app.state.retriever, app.state.llm, app.state.tts):
            try:
                await provider.aclose()
            except Exception:  # noqa: BLE001
                log.debug("provider close failed", exc_info=True)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Open Digital Mentor",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if not settings.is_mock else "/docs",
    )

    # Explicit allowlist. Never use "*" for a credential-bearing deployment.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.get("/health")
    async def health() -> dict[str, object]:
        return {
            "status": "ok",
            "protocol_version": PROTOCOL_VERSION,
            "mode": app.state.settings.mode.value,
            "providers": {
                "llm": app.state.llm.name,
                "tts": app.state.tts.name,
                "retriever": app.state.retriever.name,
            },
        }

    @app.websocket("/ws")
    async def ws(websocket: WebSocket) -> None:
        await _handle_socket(app, websocket)

    return app


async def _handle_socket(app: FastAPI, websocket: WebSocket) -> None:
    settings: Settings = app.state.settings
    client_ip = websocket.client.host if websocket.client else "unknown"
    counts: defaultdict[str, int] = app.state.connections_by_ip
    origin = websocket.headers.get("origin")

    # CORSMiddleware does not police WebSocket handshakes. Browsers always
    # send Origin, so enforce the same allowlist here; non-browser clients
    # without an Origin header remain usable for local automation.
    if origin and origin not in settings.origins:
        await websocket.close(code=1008, reason="origin not allowed")
        log.warning("rejected websocket origin from %s", client_ip)
        return

    if counts[client_ip] >= settings.max_connections_per_ip:
        await websocket.close(code=1008, reason="too many connections")
        log.warning("rejected connection from %s: per-IP limit reached", client_ip)
        return

    # Increment before the first await so concurrent handshakes cannot all
    # observe the old count and bypass the per-IP limit.
    counts[client_ip] += 1
    current: asyncio.Task[None] | None = None

    async def cancel_current() -> None:
        nonlocal current
        if current and not current.done():
            current.cancel()
            await asyncio.gather(current, return_exceptions=True)
        current = None

    try:
        await websocket.accept()

        pipeline = MentorPipeline(
            retriever=app.state.retriever,
            llm=app.state.llm,
            tts=app.state.tts,
            settings=settings,
        )

        retriever_size = getattr(app.state.retriever, "size", None)
        await websocket.send_json(
            HelloEvent(
                mode=settings.mode.value,
                providers={
                    "llm": app.state.llm.name,
                    "tts": app.state.tts.name,
                    "retriever": app.state.retriever.name,
                },
                knowledge_entries=retriever_size if retriever_size is not None else 0,
                sample_data_only=getattr(app.state.retriever, "sample_data_only", True),
            ).model_dump()
        )

        while True:
            raw = await websocket.receive_text()
            if len(raw.encode("utf-8")) > MAX_WS_MESSAGE_BYTES:
                await _send_error(websocket, "", ErrorCode.MESSAGE_TOO_LONG, "message too large")
                continue

            try:
                payload = _parse(raw)
            except ValueError as exc:
                await _send_error(websocket, "", ErrorCode.BAD_REQUEST, str(exc))
                continue

            if isinstance(payload, StopMessage):
                await cancel_current()
                await websocket.send_json(
                    InterruptedEvent(turn_id=payload.turn_id).model_dump()
                )
                continue

            question = payload.question.strip()
            if not question:
                await _send_error(
                    websocket, payload.turn_id, ErrorCode.BAD_REQUEST, "empty question"
                )
                continue
            if len(question) > settings.max_message_chars:
                await _send_error(
                    websocket,
                    payload.turn_id,
                    ErrorCode.MESSAGE_TOO_LONG,
                    f"question exceeds {settings.max_message_chars} characters",
                )
                continue

            # A new question implicitly interrupts the previous turn.
            await cancel_current()

            if settings.log_message_body:
                log.info("turn %s: %s", payload.turn_id, question)
            else:
                log.info("turn %s: question received (%d chars)", payload.turn_id, len(question))

            current = asyncio.create_task(
                _drive_turn(pipeline, websocket, payload.turn_id, question)
            )

    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        log.exception("websocket handler error")
    finally:
        await cancel_current()
        counts[client_ip] = max(0, counts[client_ip] - 1)


async def _drive_turn(
    pipeline: MentorPipeline, websocket: WebSocket, turn_id: str, question: str
) -> None:
    try:
        async for event in pipeline.run(turn_id, question):
            await websocket.send_json(event.model_dump())
    except asyncio.CancelledError:
        log.info("turn %s cancelled", turn_id)
        raise
    except (WebSocketDisconnect, RuntimeError):
        # Client vanished mid-turn; nothing to report to.
        pass
    except Exception:  # noqa: BLE001
        log.exception("turn %s failed to stream", turn_id)


def _parse(raw: str) -> AskMessage | StopMessage:
    import json

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")

    kind = data.get("type")
    try:
        if kind == "ask":
            return AskMessage.model_validate(data)
        if kind == "stop":
            return StopMessage.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"invalid {kind} message: {exc.error_count()} problem(s)") from exc
    raise ValueError(f"unknown message type: {kind!r}")


async def _send_error(
    websocket: WebSocket, turn_id: str, code: ErrorCode, message: str
) -> None:
    await websocket.send_json(
        ErrorEvent(turn_id=turn_id, code=code, message=message).model_dump()
    )


app = create_app()


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)


if __name__ == "__main__":
    main()
