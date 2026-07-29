/** Mirror of backend/app/protocol.py (v0). Keep the two in step. */

export const PROTOCOL_VERSION = 0;

export type KnowledgeType = "fact" | "decision_framework" | "checklist" | "redline";

export interface Source {
  title: string;
  url: string;
  retrieved_at: string;
  license: string;
  is_sample_data: boolean;
}

export interface Citation {
  index: number;
  id: string;
  title: string;
  snippet: string;
  source: Source;
  type: KnowledgeType;
}

export interface WireViseme {
  offset_s: number;
  duration_s: number;
  text: string;
}

interface Base {
  turn_id: string;
}

export interface HelloEvent extends Base {
  type: "hello";
  protocol_version: number;
  mode: string;
  providers: Record<string, string>;
  knowledge_entries: number;
  sample_data_only: boolean;
}

export interface TurnStartEvent extends Base {
  type: "turn.start";
}

export interface RetrievalEvent extends Base {
  type: "retrieval";
  citations: Citation[];
  refused: boolean;
  top_score: number;
}

export interface TextDeltaEvent extends Base {
  type: "text.delta";
  seq: number;
  text: string;
}

export interface ExpressionEvent extends Base {
  type: "expression";
  expression: string;
}

export interface AudioEvent extends Base {
  type: "audio";
  seq: number;
  audio: string;
  mime_type: string;
  text: string;
  visemes: WireViseme[];
  ok: boolean;
}

export interface TurnEndEvent extends Base {
  type: "turn.end";
  text: string;
  total_segments: number;
}

export interface InterruptedEvent extends Base {
  type: "interrupted";
}

export interface ErrorEvent extends Base {
  type: "error";
  code: string;
  message: string;
}

export type ServerEvent =
  | HelloEvent
  | TurnStartEvent
  | RetrievalEvent
  | TextDeltaEvent
  | ExpressionEvent
  | AudioEvent
  | TurnEndEvent
  | InterruptedEvent
  | ErrorEvent;

export type ClientMessage =
  | { type: "ask"; turn_id: string; question: string }
  | { type: "stop"; turn_id: string };

export function decodeBase64Audio(base64: string): ArrayBuffer {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
}
