/**
 * Amplitude-driven mouth movement.
 *
 * This is NOT phoneme-accurate lip sync and the README says so. It reads the
 * RMS of the playing buffer, smooths it, and maps it onto the aa/ih/ou
 * expressions. Two details are what keep it from looking broken:
 *
 *   - asymmetric smoothing: the mouth opens fast and closes slowly, which
 *     reads as speech rather than as a twitch;
 *   - viseme gating: outside a reported speech window the mouth is forced
 *     shut, so background noise and trailing silence don't leave it hanging
 *     open.
 *
 * When a provider reports only one sentence-level window (`durationS === 0`),
 * gating is disabled for the whole clip — the declared degradation path.
 * The approach is adapted from pixiv/ChatVRM (MIT); the implementation here
 * is new.
 */

import type { Viseme } from "./types";

const FFT_SIZE = 1024;

/** Opening is nearly instant; closing takes ~5x longer. */
const ATTACK = 0.55;
const RELEASE = 0.12;

/** Below this the mouth is considered closed. Avoids idle jitter. */
const NOISE_FLOOR = 0.015;

/** RMS is small even for loud speech; expand it into a usable 0..1 range. */
const GAIN = 2.6;
const CURVE = 0.62;

export interface MouthWeights {
  aa: number;
  ih: number;
  ou: number;
}

export class LipSyncDriver {
  private readonly analyser: AnalyserNode;
  // Explicitly backed by ArrayBuffer (not SharedArrayBuffer) so it satisfies
  // getFloatTimeDomainData's signature under TS 5.7's stricter typed arrays.
  private readonly buffer: Float32Array<ArrayBuffer>;
  private smoothed = 0;
  private visemes: Viseme[] = [];
  private gatingEnabled = false;
  private startedAt = 0;

  constructor(context: AudioContext) {
    this.analyser = context.createAnalyser();
    this.analyser.fftSize = FFT_SIZE;
    this.buffer = new Float32Array(this.analyser.fftSize);
  }

  get node(): AnalyserNode {
    return this.analyser;
  }

  /** Called when a clip starts playing. */
  begin(visemes: Viseme[], currentTime: number): void {
    this.visemes = visemes;
    this.startedAt = currentTime;
    // A single zero-length window means "no real timing data" — gate off
    // rather than silence the entire clip.
    this.gatingEnabled =
      visemes.length > 0 && !(visemes.length === 1 && visemes[0].durationS === 0);
  }

  end(): void {
    this.visemes = [];
    this.gatingEnabled = false;
    this.smoothed = 0;
  }

  /** Sample the analyser and return mouth weights for this frame. */
  sample(currentTime: number): MouthWeights {
    this.analyser.getFloatTimeDomainData(this.buffer);

    let sum = 0;
    for (let i = 0; i < this.buffer.length; i++) {
      sum += this.buffer[i] * this.buffer[i];
    }
    const rms = Math.sqrt(sum / this.buffer.length);

    let level = rms < NOISE_FLOOR ? 0 : Math.min(1, Math.pow(rms * GAIN, CURVE));

    if (this.gatingEnabled && !this.isInsideSpeechWindow(currentTime - this.startedAt)) {
      level = 0;
    }

    const coefficient = level > this.smoothed ? ATTACK : RELEASE;
    this.smoothed += (level - this.smoothed) * coefficient;
    if (this.smoothed < 0.001) this.smoothed = 0;

    return distribute(this.smoothed);
  }

  private isInsideSpeechWindow(elapsed: number): boolean {
    for (const viseme of this.visemes) {
      if (elapsed >= viseme.offsetS && elapsed <= viseme.offsetS + viseme.durationS) {
        return true;
      }
    }
    return false;
  }
}

/**
 * Spread one openness value across three vowel shapes.
 *
 * A single `aa` at full weight looks like a fish. Mixing in `ih` and `ou`
 * at low amplitude gives the jaw somewhere to travel through.
 */
function distribute(level: number): MouthWeights {
  if (level <= 0) return { aa: 0, ih: 0, ou: 0 };
  return {
    aa: level * 0.85,
    ih: level < 0.35 ? level * 0.5 : 0,
    ou: level > 0.65 ? (level - 0.65) * 0.6 : 0,
  };
}
