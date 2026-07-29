/**
 * Reorders concurrently-synthesised audio segments back into sentence order.
 *
 * The backend synthesises every sentence in parallel, so segments genuinely
 * may arrive out of order. Playing them as they land would scramble the
 * answer.
 *
 * Two invariants:
 *   - segments play strictly in `seq` order, gaps waited for;
 *   - anything belonging to a superseded turn is dropped on arrival. After a
 *     Stop, packets are still in flight; discarding by turn id is the only
 *     reliable way to stop them being played under the next question.
 */

import type { SpeakRequest, Viseme } from "@/avatar/types";
import { decodeBase64Audio, type AudioEvent } from "./protocol";

interface QueuedSegment {
  seq: number;
  request: SpeakRequest;
  text: string;
}

export class AudioQueue {
  private pending: QueuedSegment[] = [];
  private nextSeq = 0;
  private draining = false;
  private turnId: string | null = null;
  private totalSegments: number | null = null;
  private retainSubtitle = false;
  private drained = false;

  constructor(
    private readonly play: (request: SpeakRequest) => Promise<void>,
    private readonly showSubtitle: (text: string) => void = () => undefined,
    private readonly onDrained: (turnId: string) => void = () => undefined,
  ) {}

  /** Begin a new turn. Anything from the previous one is discarded. */
  beginTurn(turnId: string): void {
    this.turnId = turnId;
    this.pending = [];
    this.nextSeq = 0;
    this.totalSegments = null;
    this.retainSubtitle = false;
    this.drained = false;
    this.showSubtitle("");
  }

  /** Drop everything and stop accepting segments until the next turn. */
  clear(): void {
    this.turnId = null;
    this.pending = [];
    this.nextSeq = 0;
    this.totalSegments = null;
    this.retainSubtitle = false;
    this.drained = false;
    this.showSubtitle("");
  }

  enqueue(event: AudioEvent): void {
    if (this.turnId === null || event.turn_id !== this.turnId) return;
    if (event.seq < this.nextSeq || this.pending.some((segment) => segment.seq === event.seq)) {
      return;
    }

    this.pending.push({
      seq: event.seq,
      text: event.text,
      request: {
        audio: event.ok && event.audio ? decodeBase64Audio(event.audio) : new ArrayBuffer(0),
        mimeType: event.mime_type,
        visemes: event.ok ? event.visemes.map(toViseme) : [],
      },
    });
    void this.drain();
  }

  /** Tell the queue no more segments will arrive for this turn. */
  complete(turnId: string, totalSegments: number): void {
    if (this.turnId !== turnId) return;
    this.totalSegments = totalSegments;
    void this.drain();
  }

  private async drain(): Promise<void> {
    if (this.draining) return;
    this.draining = true;
    const turnAtStart = this.turnId;

    try {
      for (;;) {
        if (this.turnId !== turnAtStart) return; // superseded mid-drain
        const index = this.pending.findIndex((s) => s.seq === this.nextSeq);
        if (index === -1) return; // waiting on a gap

        const [segment] = this.pending.splice(index, 1);
        this.nextSeq += 1;
        this.showSubtitle(segment.text);
        this.retainSubtitle = segment.request.audio.byteLength === 0;

        if (segment.request.audio.byteLength > 0) {
          await this.play(segment.request);
        }
      }
    } finally {
      this.draining = false;
      if (this.turnId === turnAtStart) {
        const finished =
          this.totalSegments !== null && this.nextSeq >= this.totalSegments;
        if (finished) {
          if (!this.retainSubtitle) this.showSubtitle("");
          if (!this.drained && this.turnId !== null) {
            this.drained = true;
            this.onDrained(this.turnId);
          }
        }
        // A new segment may have landed while an old turn's playback promise
        // was resolving. Always give the current generation another chance.
        if (this.pending.some((segment) => segment.seq === this.nextSeq)) {
          void this.drain();
        }
      } else if (this.turnId !== null) {
        void this.drain();
      }
    }
  }
}

function toViseme(wire: { offset_s: number; duration_s: number; text: string }): Viseme {
  return { offsetS: wire.offset_s, durationS: wire.duration_s, text: wire.text };
}
