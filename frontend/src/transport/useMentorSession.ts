"use client";

/**
 * Owns the WebSocket, the turn lifecycle and the audio queue.
 *
 * Keeping transport separate makes the Stop path reviewable: tell the server,
 * stop the audio device, then drop the queue.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { AvatarExpression, AvatarRuntime } from "@/avatar/types";
import { AudioQueue } from "./AudioQueue";
import type { Citation, ClientMessage, HelloEvent, ServerEvent } from "./protocol";

export type ConnectionStatus = "connecting" | "ready" | "disconnected";

export interface Turn {
  id: string;
  question: string;
  answer: string;
  citations: Citation[];
  refused: boolean;
}

export interface MentorSession {
  status: ConnectionStatus;
  server: HelloEvent | null;
  busy: boolean;
  current: Turn | null;
  history: Turn[];
  error: string | null;
  subtitle: string;
  ask: (question: string) => void;
  stop: () => void;
}

const EXPRESSIONS: ReadonlySet<string> = new Set([
  "neutral",
  "happy",
  "angry",
  "sad",
  "relaxed",
  "surprised",
]);

export function useMentorSession(
  url: string,
  avatar: AvatarRuntime | null,
): MentorSession {
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const [server, setServer] = useState<HelloEvent | null>(null);
  const [current, setCurrent] = useState<Turn | null>(null);
  const [history, setHistory] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [subtitle, setSubtitle] = useState("");

  const socketRef = useRef<WebSocket | null>(null);
  const turnRef = useRef<string | null>(null);
  const avatarRef = useRef<AvatarRuntime | null>(avatar);
  avatarRef.current = avatar;

  const queue = useMemo(
    () =>
      new AudioQueue(async (request) => {
        await avatarRef.current?.speak(request);
      }, setSubtitle, (turnId) => {
        if (turnRef.current !== turnId) return;
        turnRef.current = null;
        setBusy(false);
      }),
    [],
  );

  useEffect(() => {
    let disposed = false;
    let retry: ReturnType<typeof setTimeout> | undefined;

    const connect = () => {
      if (disposed) return;
      setStatus("connecting");

      const socket = new WebSocket(url);
      socketRef.current = socket;

      socket.onopen = () => setStatus("ready");

      socket.onmessage = (message) => {
        let event: ServerEvent;
        try {
          event = JSON.parse(message.data as string) as ServerEvent;
        } catch {
          return;
        }
        handleEvent(event);
      };

      socket.onclose = () => {
        if (disposed) return;
        turnRef.current = null;
        queue.clear();
        avatarRef.current?.stop();
        if (avatarRef.current?.state === "thinking") avatarRef.current.setState("idle");
        setStatus("disconnected");
        setBusy(false);
        retry = setTimeout(connect, 2000);
      };

      socket.onerror = () => socket.close();
    };

    const handleEvent = (event: ServerEvent) => {
      // Late packets from a superseded turn are dropped here, once, so no
      // downstream consumer has to think about it.
      if (
        event.type !== "hello" &&
        event.turn_id &&
        event.turn_id !== turnRef.current
      ) {
        return;
      }

      switch (event.type) {
        case "hello":
          setServer(event);
          break;

        case "turn.start":
          avatarRef.current?.setState("thinking");
          break;

        case "retrieval":
          setCurrent((turn) =>
            turn ? { ...turn, citations: event.citations, refused: event.refused } : turn,
          );
          break;

        case "text.delta":
          setCurrent((turn) => (turn ? { ...turn, answer: turn.answer + event.text } : turn));
          break;

        case "expression":
          if (EXPRESSIONS.has(event.expression)) {
            avatarRef.current?.setExpression(event.expression as AvatarExpression);
          }
          break;

        case "audio":
          queue.enqueue(event);
          break;

        case "turn.end":
          queue.complete(event.turn_id, event.total_segments);
          if (avatarRef.current?.state === "thinking") {
            avatarRef.current.setState("idle");
          }
          setCurrent((turn) => {
            if (turn) setHistory((past) => [...past, turn]);
            return turn;
          });
          break;

        case "interrupted":
          setBusy(false);
          break;

        case "error":
          setBusy(false);
          setError(event.message || "服务端返回了一个错误");
          avatarRef.current?.setState("error");
          break;
      }
    };

    connect();

    return () => {
      disposed = true;
      if (retry) clearTimeout(retry);
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [url, queue]);

  const send = useCallback((message: ClientMessage) => {
    const socket = socketRef.current;
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify(message));
      return true;
    }
    return false;
  }, []);

  const stop = useCallback(() => {
    const turnId = turnRef.current;
    // Order matters: cut the source first so nothing keeps playing while the
    // stop message is in flight, then drop everything already buffered.
    turnRef.current = null;
    avatarRef.current?.stop();
    if (avatarRef.current?.state === "thinking") avatarRef.current.setState("idle");
    queue.clear();
    if (turnId) send({ type: "stop", turn_id: turnId });
    setBusy(false);
  }, [queue, send]);

  const ask = useCallback(
    (question: string) => {
      const trimmed = question.trim();
      if (!trimmed) return;

      // A new question implicitly interrupts the previous answer.
      avatarRef.current?.stop();
      queue.clear();

      const turnId = `t-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
      if (!send({ type: "ask", turn_id: turnId, question: trimmed })) {
        setError("尚未连接到后端服务");
        return;
      }

      turnRef.current = turnId;
      queue.beginTurn(turnId);
      setError(null);
      setBusy(true);
      setCurrent({ id: turnId, question: trimmed, answer: "", citations: [], refused: false });
    },
    [queue, send],
  );

  return { status, server, busy, current, history, error, subtitle, ask, stop };
}
