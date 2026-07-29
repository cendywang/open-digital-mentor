"use client";

import { useEffect, useRef, useState } from "react";

import { VrmRenderer, type RenderPreset } from "@/avatar/VrmRenderer";
import type { AvatarRuntime, AvatarState } from "@/avatar/types";

const STATE_LABEL: Record<AvatarState, string> = {
  loading: "载入中",
  idle: "待机",
  thinking: "思考中",
  speaking: "讲解中",
  error: "形象不可用",
};

const STATE_DOT: Record<AvatarState, string> = {
  loading: "bg-slate-500",
  idle: "bg-emerald-500",
  thinking: "bg-amber-400 animate-pulse",
  speaking: "bg-accent animate-pulse",
  error: "bg-rose-500",
};

interface Props {
  modelUrl: string;
  renderPreset: RenderPreset;
  subtitle: string;
  onReady: (runtime: AvatarRuntime) => void;
}

export function AvatarStage({ modelUrl, renderPreset, subtitle, onReady }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [state, setState] = useState<AvatarState>("loading");
  const [attribution, setAttribution] = useState<string | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const renderer = new VrmRenderer({ renderPreset });
    const unsubscribe = renderer.onStateChange(setState);

    renderer.mount(canvas);
    onReady(renderer);

    renderer
      .load(modelUrl)
      .then(() => {
        const meta = renderer.getAttribution();
        if (meta?.author) {
          setAttribution(
            [meta.title, meta.author, meta.license].filter(Boolean).join(" · "),
          );
        }
      })
      .catch(() => {
        // Already surfaced through the error state; the app keeps working.
      });

    return () => {
      unsubscribe();
      renderer.dispose();
    };
  }, [modelUrl, renderPreset, onReady]);

  return (
    <div
      data-avatar-state={state}
      className="stage-backdrop relative h-full w-full overflow-hidden"
    >
      <canvas ref={canvasRef} className="block h-full w-full" />

      <div className="pointer-events-none absolute left-4 top-4 flex items-center gap-2 rounded-full border border-ink-line/70 bg-ink/70 px-3 py-1.5 text-xs backdrop-blur">
        <span className={`h-2 w-2 rounded-full ${STATE_DOT[state]}`} />
        <span className="text-slate-300">{STATE_LABEL[state]}</span>
      </div>

      {state === "error" && (
        <div className="absolute inset-x-4 top-1/2 -translate-y-1/2 rounded-xl border border-rose-500/40 bg-rose-950/60 p-5 text-center backdrop-blur">
          <p className="text-sm font-medium text-rose-200">数字人形象加载失败</p>
          <p className="mt-2 text-xs leading-relaxed text-rose-200/70">
            右侧的问答、引用与来源溯源功能不受影响，可以正常使用。
          </p>
        </div>
      )}

      {subtitle && (
        <div className="pointer-events-none absolute inset-x-4 bottom-8 flex justify-center">
          <p
            data-mentor-subtitle
            aria-live="polite"
            className="max-w-2xl bg-black/70 px-4 py-2 text-center text-sm leading-6 text-white shadow-lg backdrop-blur-sm"
          >
            {subtitle}
          </p>
        </div>
      )}

      {attribution && (
        <p className="pointer-events-none absolute bottom-3 left-4 right-4 truncate text-[10px] text-slate-500">
          形象：{attribution}
        </p>
      )}
    </div>
  );
}
