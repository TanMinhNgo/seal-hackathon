"use client";

import Link from "next/link";
import { buttonClass } from "@/components/ui/button";
import { EventStatusBadge } from "@/components/ui/event-status-badge";
import { FormError } from "@/features/auth/auth-card";
import { useMyEvents } from "@/features/auth/use-event-roles";
import { errorMessage } from "@/lib/api";
import type { MyEvent } from "./types";

const ROLE: Record<string, [string, string]> = {
  organizer: ["Ban tổ chức", "bg-orange"],
  judge: ["Giám khảo", "bg-sun"],
  mentor: ["Mentor", "bg-mint"],
  participant: ["Thí sinh", "bg-sky"],
};
const TEAM_STATUS: Record<string, string> = { pending: "chờ duyệt", approved: "đã duyệt", rejected: "bị từ chối" };

/** Việc chính của người dùng trong một cuộc thi, theo vai trò quan trọng nhất ở cuộc thi đó. */
function action({ event, roles, team }: MyEvent): [string, string] {
  if (roles.includes("organizer")) return [`/manage/events/${event.id}`, "Vận hành cuộc thi"];
  if (roles.includes("judge")) return [`/judge?event=${event.id}`, "Vào chấm điểm"];
  if (roles.includes("mentor")) return ["/mentor", "Khu mentor"];
  return [`/events/${event.slug}/my-team`, team ? "Đội của tôi" : "Lập đội / vào đội"];
}

export function MyEvents() {
  const mine = useMyEvents();
  return (
    <main className="mx-auto max-w-[1200px] px-4 pb-24 pt-12 sm:px-6">
      <p className="font-serif text-xl italic">Mọi cuộc thi bạn có vai trò</p>
      <h1 className="mt-2 text-[clamp(40px,6vw,72px)] font-black leading-[0.95] tracking-[-0.05em]">Cuộc thi của tôi.</h1>

      {mine.isPending && <p role="status" className="mt-10">Đang tải…</p>}
      {mine.isError && <div className="mt-10"><FormError>{errorMessage(mine.error)}</FormError></div>}
      {mine.data?.total === 0 && (
        <p className="mt-10 font-serif text-lg italic text-muted">
          Bạn chưa tham gia cuộc thi nào.{" "}
          <Link href="/events" className="font-sans font-bold not-italic text-ink underline">
            Xem các cuộc thi đang mở
          </Link>
        </p>
      )}

      <ul className="mt-9 space-y-4">
        {mine.data?.items.map((m) => {
          const [href, label] = action(m);
          const past = m.event.status === "closed" || !!m.event.archived_at;
          return (
            <li key={m.event.id} className={`sketch flex flex-wrap items-center gap-x-6 gap-y-4 p-5 ${past ? "bg-warm" : ""}`}>
              <div className="min-w-0 flex-[1_1_320px]">
                <div className="flex flex-wrap gap-1.5">
                  <EventStatusBadge status={m.event.status} />
                  {m.roles.map((r) => (
                    <span key={r} className={`chip ${ROLE[r]?.[1] ?? "bg-paper"}`}>
                      {ROLE[r]?.[0] ?? r}
                    </span>
                  ))}
                </div>
                <p className="mt-2.5 break-words text-2xl font-black tracking-tight">{m.event.name}</p>
                {m.team && (
                  <p className="mt-1 text-sm text-muted">
                    Đội {m.team.name} · {TEAM_STATUS[m.team.status] ?? m.team.status}
                    {m.team.member_status === "pending" && " · bạn đang chờ trưởng nhóm duyệt"}
                  </p>
                )}
              </div>
              <Link href={href} className={buttonClass(past ? "secondary" : "primary")}>
                {label}
              </Link>
            </li>
          );
        })}
      </ul>
    </main>
  );
}
