"use client";

import { useCallback, useState } from "react";

import type { AvatarRuntime } from "@/avatar/types";
import type { RenderPreset } from "@/avatar/VrmRenderer";
import { AnswerPanel } from "@/components/AnswerPanel";
import { AskBox } from "@/components/AskBox";
import { SessionHeader } from "@/components/SessionHeader";
import { AvatarStage } from "@/components/AvatarStage";
import { useMentorSession } from "@/transport/useMentorSession";

const WS_URL = process.env.NEXT_PUBLIC_ODM_WS_URL ?? "ws://127.0.0.1:8000/ws";
const AVATAR_URL = process.env.NEXT_PUBLIC_ODM_AVATAR_URL ?? "/avatars/default.vrm";
const RENDER_PRESET = (process.env.NEXT_PUBLIC_ODM_RENDER_PRESET ?? "stylized") as RenderPreset;

export default function Home() {
  const [avatar, setAvatar] = useState<AvatarRuntime | null>(null);
  const handleReady = useCallback((runtime: AvatarRuntime) => setAvatar(runtime), []);

  const session = useMentorSession(WS_URL, avatar);
  const disabled = session.status !== "ready";

  return (
    <main className="flex h-screen flex-col lg:flex-row">
      <section className="h-[42vh] shrink-0 lg:h-full lg:flex-1">
        <AvatarStage
          modelUrl={AVATAR_URL}
          renderPreset={RENDER_PRESET}
          subtitle={session.subtitle}
          onReady={handleReady}
        />
      </section>

      <section className="flex min-h-0 flex-1 flex-col gap-4 border-t border-ink-line p-5 lg:max-w-xl lg:border-l lg:border-t-0">
        <SessionHeader status={session.status} server={session.server} />

        <div className="scroll-thin min-h-0 flex-1 overflow-y-auto pr-1">
          <AnswerPanel turn={session.current} busy={session.busy} />
        </div>

        {session.error && (
          <p className="rounded-lg border border-rose-700/50 bg-rose-950/40 px-3 py-2 text-xs text-rose-200">
            {session.error}
          </p>
        )}

        <AskBox
          busy={session.busy}
          disabled={disabled}
          onAsk={session.ask}
          onStop={session.stop}
        />

        <p className="text-[11px] leading-relaxed text-slate-600">
          示例知识库为合成数据，不构成任何法律、税务或投资建议。口型为音量包络驱动的近似效果，
          非音素级同步。
        </p>
      </section>
    </main>
  );
}
