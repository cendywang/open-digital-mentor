"use client";

import type { ConnectionStatus } from "@/transport/useMentorSession";
import type { HelloEvent } from "@/transport/protocol";

const STATUS: Record<ConnectionStatus, { label: string; dot: string }> = {
  connecting: { label: "连接中", dot: "bg-amber-400 animate-pulse" },
  ready: { label: "已连接", dot: "bg-emerald-500" },
  disconnected: { label: "未连接", dot: "bg-rose-500" },
};

export function SessionHeader({
  status,
  server,
}: {
  status: ConnectionStatus;
  server: HelloEvent | null;
}) {
  const badge = STATUS[status];

  return (
    <header className="space-y-3 border-b border-ink-line pb-4">
      <div className="flex items-baseline justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-slate-100">Open Digital Mentor</h1>
          <p className="text-xs text-slate-500">Knowledge-driven VRM digital mentor</p>
        </div>
        <span className="flex shrink-0 items-center gap-1.5 text-xs text-slate-400">
          <span className={`h-2 w-2 rounded-full ${badge.dot}`} />
          {badge.label}
        </span>
      </div>

      {server && (
        <div className="flex flex-wrap gap-1.5 text-[11px]">
          <Tag
            label={server.mode === "mock" ? "Mock 模式 · 不联网" : "Live 模式"}
            tone={server.mode === "mock" ? "amber" : "accent"}
          />
          <Tag label={`LLM: ${server.providers.llm}`} />
          <Tag label={`TTS: ${server.providers.tts}`} />
          <Tag label={`检索: ${server.providers.retriever}`} />
          {server.knowledge_entries > 0 && (
            <Tag label={`知识条目: ${server.knowledge_entries}`} />
          )}
        </div>
      )}
    </header>
  );
}

function Tag({ label, tone = "slate" }: { label: string; tone?: "slate" | "amber" | "accent" }) {
  const styles = {
    slate: "border-ink-line text-slate-400",
    amber: "border-amber-700/60 text-amber-300",
    accent: "border-accent/50 text-accent-soft",
  } as const;
  return (
    <span className={`rounded border px-1.5 py-0.5 ${styles[tone]}`}>{label}</span>
  );
}
