"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { FormError } from "@/features/auth/auth-card";
import { useMyEvents } from "@/features/auth/use-event-roles";
import { Tabs } from "@/features/events/manage";
import type { Page, Team } from "@/features/events/types";
import { TeamProgress } from "@/features/commits/commits";
import { TeamSubmissions } from "@/features/submissions/submissions";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/stores/auth";
import { MentorNotes, TeamQuestions } from "./team-support";

type Tab = "questions" | "notes" | "progress" | "submissions";

export function MentorView() {
  const user = useAuth((s) => s.user);
  const mine = useMyEvents();
  const teams = useQuery({
    queryKey: ["mentoring"],
    // shortcut: 100 đội đầu; một mentor hiếm khi được giao nhiều hơn
    queryFn: async () => (await api.get<Page<Team>>("/me/mentoring", { params: { limit: 100 } })).data.items,
  });
  const [picked, setPicked] = useState("");
  const [tab, setTab] = useState<Tab>("questions");
  const eventName = new Map(mine.data?.items.map((m) => [m.event.id, m.event.name]));
  const t = teams.data?.find((x) => x.id === picked) ?? teams.data?.[0];

  return (
    <main className="mx-auto max-w-[1360px] px-4 pb-24 pt-8 sm:px-6">
      <p className="font-serif text-lg italic">Xin chào, {user?.full_name}</p>
      <h1 className="mt-1 text-[clamp(38px,4.6vw,58px)] font-black leading-none tracking-[-0.045em]">Đồng hành cùng các đội.</h1>
      {teams.isError && <div className="mt-6"><FormError>{errorMessage(teams.error)}</FormError></div>}
      {teams.data?.length === 0 && <p className="mt-8 font-serif text-lg italic text-muted">Bạn chưa được BTC phân công đội nào.</p>}

      {t && (
        <div className="mt-7 flex flex-wrap items-start gap-6">
          <section aria-labelledby="teams" className="flex min-w-0 flex-[1_1_260px] flex-col gap-3">
            <h2 id="teams" className="text-lg font-black">
              Đội được phân công · {teams.data!.length}
            </h2>
            {teams.data!.map((x) => (
              <button
                key={x.id}
                type="button"
                aria-pressed={x.id === t.id}
                onClick={() => setPicked(x.id)}
                className={`flex flex-col gap-1 rounded-[20px] border-2 border-ink p-4 text-left transition-colors hover:bg-cream ${x.id === t.id ? "bg-cream shadow-sketch-sm" : "bg-paper"}`}
              >
                <span className="break-words text-[19px] font-black">{x.name}</span>
                <span className="text-[13px] font-semibold text-muted">{eventName.get(x.event_id) ?? ""}</span>
              </button>
            ))}
          </section>

          <section aria-labelledby="team-name" className="flex min-w-0 flex-[3_1_600px] flex-col gap-[22px]">
            <div className="sketch p-[22px]">
              <h2 id="team-name" className="break-words text-[32px] font-black tracking-tight">
                {t.name}
              </h2>
              {t.repo_url && (
                <a href={t.repo_url} target="_blank" rel="noreferrer" className="mt-1 inline-block break-all font-mono text-[13px] underline">
                  {t.repo_url}
                </a>
              )}
              <ul className="mt-3 flex flex-wrap gap-1.5">
                {t.members
                  .filter((m) => m.status === "active")
                  .map((m) => (
                    <li key={m.user.id} className="rounded-full border-[1.5px] border-ink px-2.5 py-0.5 text-[13px] font-semibold">
                      {m.user.full_name}
                      {m.user.id === t.leader_id && " · trưởng nhóm"}
                    </li>
                  ))}
              </ul>
            </div>

            <Tabs<Tab>
              label="Hỗ trợ đội"
              value={tab}
              onChange={setTab}
              tabs={[
                ["questions", "Câu hỏi từ đội"],
                ["notes", "Góp ý & tiến độ"],
                ["progress", "Tiến độ commit"],
                ["submissions", "Bài nộp"],
              ]}
            />
            <div className="sketch p-[22px]">
              {tab === "questions" && <TeamQuestions key={t.id} teamId={t.id} mode="mentor" />}
              {tab === "notes" && <MentorNotes key={t.id} teamId={t.id} canPost />}
              {tab === "progress" && <TeamProgress key={t.id} teamId={t.id} />}
              {tab === "submissions" && <TeamSubmissions key={t.id} eventId={t.event_id} teamId={t.id} />}
            </div>
          </section>
        </div>
      )}
    </main>
  );
}
