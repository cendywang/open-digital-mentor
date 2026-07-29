import assert from "node:assert/strict";
import { describe, it } from "node:test";

import type { SpeakRequest } from "@/avatar/types";
import { AudioQueue } from "./AudioQueue";
import type { AudioEvent } from "./protocol";

function event(
  seq: number,
  options: { turnId?: string; ok?: boolean; audio?: boolean; text?: string } = {},
): AudioEvent {
  const hasAudio = options.audio ?? true;
  return {
    type: "audio",
    turn_id: options.turnId ?? "turn-1",
    seq,
    audio: hasAudio ? btoa(String.fromCharCode(seq + 1)) : "",
    mime_type: "audio/wav",
    text: options.text ?? `subtitle-${seq}`,
    visemes: [],
    ok: options.ok ?? hasAudio,
  };
}

function byte(request: SpeakRequest): number {
  return new Uint8Array(request.audio)[0];
}

async function waitFor(predicate: () => boolean, message: string): Promise<void> {
  const deadline = Date.now() + 1_000;
  while (Date.now() < deadline) {
    if (predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
  assert.fail(message);
}

describe("AudioQueue", () => {
  it("plays 2 -> 0 -> 1 arrivals strictly as 0 -> 1 -> 2", async () => {
    const played: number[] = [];
    const subtitles: string[] = [];
    const queue = new AudioQueue(
      async (request) => {
        played.push(byte(request) - 1);
      },
      (text) => subtitles.push(text),
    );

    queue.beginTurn("turn-1");
    queue.enqueue(event(2));
    queue.enqueue(event(0));
    queue.enqueue(event(1));
    queue.complete("turn-1", 3);

    await waitFor(() => played.length === 3, "all three segments should play");
    assert.deepEqual(played, [0, 1, 2]);
    assert.deepEqual(subtitles.filter(Boolean), ["subtitle-0", "subtitle-1", "subtitle-2"]);
    assert.equal(subtitles.at(-1), "");
  });

  it("clear drops buffered and late packets from a stopped turn", async () => {
    const played: number[] = [];
    const subtitles: string[] = [];
    let finishPlaying: (() => void) | undefined;
    const queue = new AudioQueue(
      (request) => {
        played.push(byte(request) - 1);
        return new Promise<void>((resolve) => {
          finishPlaying = resolve;
        });
      },
      (text) => subtitles.push(text),
    );

    queue.beginTurn("turn-1");
    queue.enqueue(event(0));
    queue.enqueue(event(1));
    await waitFor(() => typeof finishPlaying === "function", "first segment should start");

    queue.clear();
    queue.enqueue(event(2));
    finishPlaying?.();

    await waitFor(() => subtitles.at(-1) === "", "clear should hide the subtitle");
    assert.deepEqual(played, [0]);
  });

  it("restarts draining for a new turn after old playback settles", async () => {
    const played: number[] = [];
    let releaseOld: (() => void) | undefined;
    const queue = new AudioQueue(async (request) => {
      const value = byte(request) - 1;
      played.push(value);
      if (played.length === 1) {
        await new Promise<void>((resolve) => {
          releaseOld = resolve;
        });
      }
    });

    queue.beginTurn("turn-1");
    queue.enqueue(event(0));
    await waitFor(() => typeof releaseOld === "function", "old turn should start playing");

    queue.clear();
    queue.beginTurn("turn-2");
    queue.enqueue(event(1, { turnId: "turn-1" }));
    queue.enqueue(event(0, { turnId: "turn-2" }));
    queue.complete("turn-2", 1);
    releaseOld?.();

    await waitFor(() => played.length === 2, "new turn should drain after old playback settles");
    assert.deepEqual(played, [0, 0]);
  });

  it("advances across a failed segment without stalling later audio", async () => {
    const played: number[] = [];
    const subtitles: string[] = [];
    const queue = new AudioQueue(
      async (request) => {
        played.push(byte(request) - 1);
      },
      (text) => subtitles.push(text),
    );

    queue.beginTurn("turn-1");
    queue.enqueue(event(2));
    queue.enqueue(event(0, { ok: false, audio: false, text: "text-only" }));
    queue.enqueue(event(1));
    queue.complete("turn-1", 3);

    await waitFor(() => played.length === 2, "later audio should play after a failed segment");
    assert.deepEqual(played, [1, 2]);
    assert.ok(subtitles.includes("text-only"));
    assert.equal(subtitles.at(-1), "");
  });

  it("keeps the final subtitle visible when TTS is unavailable", async () => {
    const subtitles: string[] = [];
    const drained: string[] = [];
    const queue = new AudioQueue(
      async () => undefined,
      (text) => subtitles.push(text),
      (turnId) => drained.push(turnId),
    );

    queue.beginTurn("turn-1");
    queue.enqueue(event(0, { ok: false, audio: false, text: "仍然显示文字" }));
    queue.complete("turn-1", 1);

    await waitFor(
      () => subtitles.at(-1) === "仍然显示文字",
      "text-only subtitle should remain visible",
    );
    assert.deepEqual(drained, ["turn-1"]);
  });

  it("reports drained only after the final playback settles", async () => {
    let finishPlaying: (() => void) | undefined;
    const drained: string[] = [];
    const queue = new AudioQueue(
      () =>
        new Promise<void>((resolve) => {
          finishPlaying = resolve;
        }),
      undefined,
      (turnId) => drained.push(turnId),
    );

    queue.beginTurn("turn-1");
    queue.enqueue(event(0));
    queue.complete("turn-1", 1);
    await waitFor(() => typeof finishPlaying === "function", "playback should start");
    assert.deepEqual(drained, []);

    finishPlaying?.();
    await waitFor(() => drained.length === 1, "drained should follow playback completion");
    queue.complete("turn-1", 1);
    await new Promise((resolve) => setTimeout(resolve, 10));
    assert.deepEqual(drained, ["turn-1"]);
  });
});
