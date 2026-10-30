"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { buttonClass } from "@/components/ui/button";
import { EventStatusBadge } from "@/components/ui/event-status-badge";
import { LocalTime } from "@/components/ui/local-time";
import { FormError } from "@/features/auth/auth-card";
import { EventEditor, RegistrationsPanel, RolesPanel, Tabs, TeamsPanel, useEvent, useEventCache } from "@/features/events/manage";
import type { Event, Page, Round } from "@/features/events/types";
import { api, errorMessage } from "@/lib/api";
import { useLeaveOnForbidden } from "./use-leave-on-forbidden";

type Tab = "info" | "organizers" | "teams" | "registrations";

export function AdminEventDetail({ eventId }: { eventId: string }) {
  const event = useEvent(eventId);
  const [tab, setTab] = useState<Tab>("info");
  useLeaveOnForbidden(event.error);

  if (event.isError) return <FormError>{errorMessage(event.error)}</FormError>;
  if (!event.data) return <p role="status">Đang tải…</p>;
  const e = event.data;

  return (
    <div className="space-y-7">
      <div>
        <Link href="/admin/events" className="text-sm font-bold">
          ← Tất cả cuộc thi
        </Link>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <EventStatusBadge status={e.status} />
          <span className="chip border-dashed bg-paper font-mono">/{e.slug}</span>
          {e.archived_at && <span className="chip bg-warm">Đã lưu trữ</span>}
        </div>
        <h1 className="mt-3 break-words text-[clamp(36px,5vw,56px)] font-black leading-none tracking-[-0.045em]">{e.name}.</h1>
        <p className="mt-3 text-sm text-muted">Admin sửa tên, mô tả, ảnh bìa, chỉ định ban tổ chức và lưu trữ cuộc thi đã kết thúc. Lịch, vòng thi, duyệt đội do ban tổ chức vận hành. Mọi thay đổi ghi nhật ký.</p>
      </div>

      <Tabs<Tab>
        label="Hồ sơ cuộc thi"
        value={tab}
        onChange={setTab}
        tabs={[
          ["info", "Tổng quan"],
          ["organizers", "Ban tổ chức"],
          ["teams", "Đội thi"],
          ["registrations", "Người đăng ký"],
        ]}
      />

      <section className="sketch p-6">
        {tab === "info" && <Info event={e} />}
        {tab === "organizers" && <RolesPanel eventId={e.id} roles={["organizer"]} />}
        {tab === "teams" && <TeamsPanel eventId={e.id} review={false} />}
        {tab === "registrations" && <RegistrationsPanel eventId={e.id} />}
      </section>
    </div>
  );
}

function Info({ event }: { event: Event }) {
  const setEvent = useEventCache(event.id);
  const rounds = useQuery({ queryKey: ["rounds", event.id], queryFn: async () => (await api.get<Page<Round>>(`/events/${event.id}/rounds`, { params: { limit: 100 } })).data.items });
  const archive = useMutation({ mutationFn: async () => (await api.post<Event>(`/events/${event.id}/archive`, { archived: !event.archived_at })).data, onSuccess: setEvent });

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-xl font-black">Lịch (ban tổ chức đặt)</h2>
        <ol className="mt-3 divide-y divide-dashed divide-line">
          {[
            ["Mở đăng ký", event.registration_opens_at],
            ["Đóng đăng ký", event.registration_closes_at],
            ["Bắt đầu thi", event.starts_at],
            ["Kết thúc", event.ends_at],
          ].map(([label, iso]) => (
            <li key={label} className="flex flex-wrap gap-x-4 py-2.5">
              <span className="min-w-44 font-mono font-extrabold">
                <LocalTime iso={iso} />
              </span>
              <span className="font-bold">{label}</span>
            </li>
          ))}
          {rounds.data?.map((r) => (
            <li key={r.id} className="flex flex-wrap gap-x-4 py-2.5">
              <span className="min-w-44 font-mono font-extrabold">
                <LocalTime iso={r.submission_deadline} />
              </span>
              <span className="font-bold">Hạn nộp vòng {r.order} · {r.name}</span>
            </li>
          ))}
        </ol>
        <p className="mt-3 text-sm">
          Đội {event.min_team_size}–{event.max_team_size} người.
        </p>
      </div>

      <div className="border-t-2 border-dashed border-line pt-6">
        <h2 className="mb-4 text-xl font-black">Tên, mô tả, ảnh bìa</h2>
        <EventEditor event={event} keys={["name", "description", "banner_url"]} />
      </div>

      <div className="border-t-2 border-dashed border-line pt-6">
        <h2 className="text-xl font-black">Lưu trữ</h2>
        <p className="mt-1 text-sm text-muted">Ẩn cuộc thi đã kết thúc khỏi trang công khai; dữ liệu đội, commit, đánh giá giữ nguyên để tra cứu.</p>
        {archive.isError && <div className="mt-3"><FormError>{errorMessage(archive.error)}</FormError></div>}
        <button
          type="button"
          className={buttonClass("secondary", "mt-3")}
          disabled={event.status !== "closed" || archive.isPending}
          title={event.status !== "closed" ? "Chỉ lưu trữ được khi cuộc thi đã kết thúc" : undefined}
          onClick={() => {
            if (window.confirm(event.archived_at ? "Bỏ lưu trữ, hiện lại cuộc thi ở trang công khai?" : "Lưu trữ cuộc thi này?")) archive.mutate();
          }}
        >
          {event.archived_at ? "Bỏ lưu trữ" : "Lưu trữ"}
        </button>
      </div>
    </div>
  );
}
