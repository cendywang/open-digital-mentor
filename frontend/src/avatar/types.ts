/**
 * The avatar boundary.
 *
 * Nothing behind this interface knows what a retriever, a citation or a
 * mentor is — swapping VRM for Live2D, a sprite sheet or a static portrait
 * does not change the transport or knowledge pipeline.
 */

/** Emotion presets the backend may emit as `expression` events. */
export type AvatarExpression =
  | "neutral"
  | "happy"
  | "angry"
  | "sad"
  | "relaxed"
  | "surprised";

/**
 * Lifecycle of a turn, as the avatar sees it.
 *
 * `error` is reachable from anywhere — critically, a failed model load lands
 * here without taking the rest of the app down. Text Q&A must keep working
 * with no avatar at all.
 */
export type AvatarState = "loading" | "idle" | "thinking" | "speaking" | "error";

/**
 * A mouth-shape window aligned to the audio timeline.
 *
 * A provider that only reports sentence boundaries returns a single entry
 * with `durationS === 0`, meaning "the whole clip". That is a declared
 * degradation, not phoneme-accurate lip sync, and the UI says so.
 */
export interface Viseme {
  offsetS: number;
  durationS: number;
  text: string;
}

export interface SpeakRequest {
  audio: ArrayBuffer;
  mimeType: string;
  visemes: Viseme[];
}

export interface AvatarRuntime {
  readonly state: AvatarState;

  mount(canvas: HTMLCanvasElement): void;
  load(url: string): Promise<void>;

  setState(state: AvatarState): void;
  setExpression(expression: AvatarExpression): void;

  /** Resolves when playback finishes, or immediately if interrupted. */
  speak(request: SpeakRequest): Promise<void>;

  /** Halt playback now and release any queued audio node. */
  stop(): void;

  dispose(): void;

  onStateChange(listener: (state: AvatarState) => void): () => void;

  /** VRM metadata, surfaced so the UI can display required attribution. */
  getAttribution(): AvatarAttribution | null;
}

export interface AvatarAttribution {
  title?: string;
  author?: string;
  license?: string;
  otherLicenseUrl?: string;
}
