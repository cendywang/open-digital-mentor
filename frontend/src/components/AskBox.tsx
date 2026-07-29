"use client";

import { useState } from "react";

const SAMPLES = [
  "自贸区主体和关境内主体应该怎么选？",
  "设立完成后有哪些必须限时办的事？",
  "企业银行开户为什么会被拒？",
  "帮我写一段 Python 快速排序", // deliberately off-corpus: demonstrates refusal
];

interface Props {
  busy: boolean;
  disabled: boolean;
  onAsk: (question: string) => void;
  onStop: () => void;
}

export function AskBox({ busy, disabled, onAsk, onStop }: Props) {
  const [value, setValue] = useState("");

  const submit = () => {
    if (!value.trim() || disabled) return;
    onAsk(value);
    setValue("");
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {SAMPLES.map((sample) => (
          <button
            key={sample}
            type="button"
            disabled={disabled}
            onClick={() => onAsk(sample)}
            className="rounded-full border border-ink-line bg-ink-soft/60 px-3 py-1.5 text-xs text-slate-300 transition hover:border-accent/50 hover:text-accent-soft disabled:opacity-40"
          >
            {sample}
          </button>
        ))}
      </div>

      <div className="flex gap-2">
        <input
          value={value}
          disabled={disabled}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.nativeEvent.isComposing) submit();
          }}
          placeholder="输入你的问题…"
          maxLength={2000}
          className="min-w-0 flex-1 rounded-lg border border-ink-line bg-ink-soft/60 px-4 py-2.5 text-sm text-slate-200 outline-none transition placeholder:text-slate-600 focus:border-accent/60 disabled:opacity-40"
        />

        {busy ? (
          <button
            type="button"
            onClick={onStop}
            className="shrink-0 rounded-lg border border-rose-600/60 bg-rose-950/40 px-5 py-2.5 text-sm text-rose-200 transition hover:bg-rose-900/50"
          >
            停止
          </button>
        ) : (
          <button
            type="button"
            onClick={submit}
            disabled={disabled || !value.trim()}
            className="shrink-0 rounded-lg bg-accent px-5 py-2.5 text-sm font-medium text-white transition hover:bg-accent-soft disabled:opacity-30"
          >
            提问
          </button>
        )}
      </div>
    </div>
  );
}
