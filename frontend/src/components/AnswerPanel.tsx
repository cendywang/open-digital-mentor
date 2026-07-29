"use client";

import { useEffect, useState } from "react";

import type { Citation, KnowledgeType } from "@/transport/protocol";
import type { Turn } from "@/transport/useMentorSession";

const TYPE_LABEL: Record<KnowledgeType, string> = {
  fact: "事实",
  decision_framework: "决策框架",
  checklist: "清单",
  redline: "红线",
};

const TYPE_STYLE: Record<KnowledgeType, string> = {
  fact: "border-slate-600 text-slate-300",
  decision_framework: "border-accent/60 text-accent-soft",
  checklist: "border-emerald-600/60 text-emerald-300",
  redline: "border-rose-600/60 text-rose-300",
};

export function AnswerPanel({ turn, busy }: { turn: Turn | null; busy: boolean }) {
  const [openCitation, setOpenCitation] = useState<number | null>(null);

  useEffect(() => setOpenCitation(null), [turn?.id]);

  if (!turn) {
    return (
      <div className="rounded-xl border border-ink-line bg-ink-soft/60 p-6 text-sm leading-relaxed text-slate-400">
        选一个下面的示例问题，或者直接提问。
        <br />
        回答会带来源角标，点击角标可以查看被引用的原文片段。
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-ink-line bg-ink-soft/60 p-5">
        <p className="text-xs text-slate-500">你的问题</p>
        <p className="mt-1 text-sm text-slate-200">{turn.question}</p>
      </div>

      <div
        className={`rounded-xl border p-5 ${
          turn.refused ? "border-amber-600/50 bg-amber-950/25" : "border-ink-line bg-ink-soft/60"
        }`}
      >
        {turn.refused && (
          <p className="mb-3 inline-flex rounded-full border border-amber-600/50 px-2.5 py-0.5 text-[11px] text-amber-300">
            知识库未覆盖 · 已拒答
          </p>
        )}
        <AnswerText
          text={turn.answer || (busy ? "…" : "")}
          citations={turn.citations}
          onCitation={(index) => {
            setOpenCitation(index);
            requestAnimationFrame(() => {
              document
                .getElementById(`citation-${index}`)
                ?.scrollIntoView({ behavior: "smooth", block: "nearest" });
            });
          }}
        />
      </div>

      {turn.citations.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-slate-500">引用来源（{turn.citations.length}）</p>
          {turn.citations.map((citation) => (
            <CitationCard
              key={citation.id}
              citation={citation}
              open={openCitation === citation.index}
              onToggle={() =>
                setOpenCitation((current) =>
                  current === citation.index ? null : citation.index,
                )
              }
            />
          ))}
        </div>
      )}
    </div>
  );
}

function AnswerText({
  text,
  citations,
  onCitation,
}: {
  text: string;
  citations: Citation[];
  onCitation: (index: number) => void;
}) {
  const known = new Set(citations.map((citation) => citation.index));

  return (
    <p className="whitespace-pre-wrap text-sm leading-7 text-slate-200">
      {text.split(/(\[\d{1,2}\])/g).map((part, index) => {
        const match = /^\[(\d{1,2})\]$/.exec(part);
        const citationIndex = match ? Number(match[1]) : null;
        if (citationIndex === null || !known.has(citationIndex)) {
          return <span key={`${index}-${part}`}>{part}</span>;
        }
        return (
          <button
            key={`${index}-${part}`}
            type="button"
            onClick={() => onCitation(citationIndex)}
            className="mx-0.5 inline font-medium text-accent-soft underline decoration-accent/40 underline-offset-2 hover:text-white"
            aria-label={`查看引用 ${citationIndex} 的原文`}
          >
            {part}
          </button>
        );
      })}
    </p>
  );
}

function CitationCard({
  citation,
  open,
  onToggle,
}: {
  citation: Citation;
  open: boolean;
  onToggle: () => void;
}) {

  return (
    <div
      id={`citation-${citation.index}`}
      className="scroll-mt-4 rounded-lg border border-ink-line bg-ink-soft/40"
    >
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full items-start gap-3 p-3 text-left transition hover:bg-ink-soft/80"
      >
        <span className="mt-0.5 shrink-0 rounded bg-accent/15 px-1.5 py-0.5 text-[11px] font-medium text-accent-soft">
          [{citation.index}]
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm text-slate-200">{citation.title}</span>
          <span className="mt-1 flex flex-wrap items-center gap-1.5">
            <span
              className={`rounded border px-1.5 py-px text-[10px] ${TYPE_STYLE[citation.type]}`}
            >
              {TYPE_LABEL[citation.type]}
            </span>
            {citation.source.is_sample_data && (
              <span className="rounded border border-amber-700/50 px-1.5 py-px text-[10px] text-amber-400/90">
                示例数据
              </span>
            )}
          </span>
        </span>
        <span className="shrink-0 text-xs text-slate-500">{open ? "收起" : "原文"}</span>
      </button>

      {open && (
        <div className="border-t border-ink-line px-3 py-3">
          <p className="whitespace-pre-wrap text-xs leading-6 text-slate-400">
            {citation.snippet}
          </p>
          <p className="mt-3 text-[11px] text-slate-500">
            来源：{citation.source.title}
            {citation.source.license && ` · ${citation.source.license}`}
          </p>
          {citation.source.url && (
            <a
              href={citation.source.url}
              target="_blank"
              rel="noreferrer noopener"
              className="mt-1 inline-block text-[11px] text-accent-soft hover:underline"
            >
              查看来源 ↗
            </a>
          )}
        </div>
      )}
    </div>
  );
}
