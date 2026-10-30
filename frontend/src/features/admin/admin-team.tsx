"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { LocalTime } from "@/components/ui/local-time";
import { FormError } from "@/features/auth/auth-card";
import { useEvent, useTracks } from "@/features/events/manage";
import type { Team } from "@/features/events/types";
import { TeamSubmissions } from "@/features/submissions/submissions";
import { api, errorMessage } from "@/lib/api";
import { useLeaveOnForbidden } from "./use-leave-on-forbidden";

const STATUS: Record<Team["status"], [string, string]> = { pending: ["Chờ duyệt", "bg-sun"], approved: ["Đã duyệt", "bg-mint"], rejected: ["Bị từ chối", "bg-rose"] };

/** Hồ sơ đội chỉ đọc cho admin; BE không trả mã mời cho admin. */
export function AdminTeam({ teamId }: { teamId: string }) {
  const team = useQuery({ queryKey: ["team", teamId], queryFn: async () => (await api.get<Team>(`/teams/${teamId}`)).data });
  const eventId = team.data?.event_id ?? "";
  const event = useEvent(eventId);
  const tracks = useTracks(eventId);
  useLeaveOnForbidden(team.error);

  if (team.isError) return <FormError>{errorMessage(team.error)}</FormError>;
  if (!team.data) return <p role="status">Đang tải…</p>;
  const t = team.data;
  const track = tracks.data?.find((x) => x.id === t.track_id);

  return (
    <div className="space-y-7">
      <nav aria-label="Đường dẫn" className="text-sm font-bold">
        <Link href="/admin/events">Cuộc thi</Link> / <Link href={`/admin/events/${t.event_id}`}>{event.data?.name ?? "…"}</Link> / {t.name}
      </nav>
      <div className="flex flex-wrap items-end gap-3">
        <h1 className="break-words text-[clamp(36px,5vw,56px)] font-black leading-none tracking-[-0.045em]">{t.name}.</h1>
        <span className={`chip ${STATUS[t.status][1]}`}>{STATUS[t.status][0]}</span>
        {track && <span className="chip bg-sky">{track.name}</span>}
        {t.disbanded_at && <span className="chip bg-warm">Đã giải tán</span>}
      </div>
      <p className="text-sm text-muted">Hồ sơ chỉ đọc: admin không sửa, duyệt hay chấm đội. Commit, góp ý và AI review sẽ hiện ở đây từ Phase 4–6.</p>

      <div className="flex flex-wrap gap-7">
        <section className="sketch min-w-0 flex-[999_1_460px] p-6">
          <h2 className="text-xl font-black">Thành viên</h2>
          <ul className="mt-4 space-y-2.5">
            {t.members.map((m) => (
              <li key={m.user.id} className="flex flex-wrap items-center gap-x-3.5 gap-y-1.5 rounded-2xl border-2 border-dashed border-ink px-3.5 py-3">
                <span className="min-w-0 flex-[1_1_200px]">
                  <b className="break-words">{m.user.full_name}</b>
                  <span className="block break-all text-sm text-muted">{m.user.email}</span>
                </span>
                <span className={`chip ${m.user.id === t.leader_id ? "bg-orange" : m.status === "pending" ? "bg-sun" : "bg-mint"}`}>
                  {m.user.id === t.leader_id ? "Trưởng nhóm" : m.status === "pending" ? "Chờ duyệt" : "Thành viên"}
                </span>
                <span className="font-mono text-xs text-muted">
                  vào <LocalTime iso={m.joined_at} dateOnly />
                </span>
              </li>
            ))}
          </ul>
        </section>
        <div className="min-w-0 flex-[1_1_320px] space-y-5">
          <section className="rounded-2xl border-2 border-ink bg-cream p-4">
            <p className="text-sm font-bold">Repo</p>
            {t.repo_url ? (
              <a href={t.repo_url} target="_blank" rel="noreferrer" className="mt-1.5 block break-all font-mono text-sm font-extrabold underline">
                {t.repo_url}
              </a>
            ) : (
              <p className="mt-1.5 text-sm text-muted">Chưa khai báo.</p>
            )}
          </section>
          <section className="rounded-2xl border-2 border-ink p-4 text-sm">
            <p className="font-bold">Duyệt đội</p>
            <p className="mt-1.5">
              {t.reviewed_at ? (
                <>
                  {STATUS[t.status][0]} lúc <LocalTime iso={t.reviewed_at} />
                </>
              ) : (
                "Chưa được xét."
              )}
            </p>
            {t.review_note && <p className="mt-1.5 text-muted">Ghi chú: “{t.review_note}”</p>}
            <p className="mt-1.5 text-muted">
              Tạo đội <LocalTime iso={t.created_at} />
            </p>
          </section>
        </div>
      </div>

      <section className="sketch p-6">
        <h2 className="mb-4 text-xl font-black">Bài nộp</h2>
        <TeamSubmissions eventId={t.event_id} teamId={t.id} />
      </section>
    </div>
  );
}
