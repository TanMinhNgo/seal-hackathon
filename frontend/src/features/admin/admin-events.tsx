"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { buttonClass } from "@/components/ui/button";
import { EVENT_STATUS, EventStatusBadge, type EventStatus } from "@/components/ui/event-status-badge";
import { LocalTime } from "@/components/ui/local-time";
import { Pager } from "@/components/ui/pager";
import { FormError } from "@/features/auth/auth-card";
import { FieldsForm, pick, type FieldDef } from "@/features/events/manage";
import type { Event, EventPage } from "@/features/events/types";
import { api, errorMessage } from "@/lib/api";
import { useLeaveOnForbidden } from "./use-leave-on-forbidden";

const LIMIT = 20;
const CREATE_FIELDS: FieldDef[] = [
  ...pick("name", "slug", "registration_opens_at", "registration_closes_at", "starts_at", "ends_at", "min_team_size", "max_team_size", "description"),
  { key: "organizer_email", label: "Email ban tổ chức phụ trách", type: "email", required: true, hint: "Tài khoản đã có, đã xác thực, không phải admin." },
];

export function AdminEvents() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState({ q: "", status: "" });
  const [offset, setOffset] = useState(0);
  const [creating, setCreating] = useState(false);
  const events = useQuery({
    queryKey: ["events", "admin", filter, offset],
    queryFn: async () => (await api.get<EventPage>("/events", { params: { q: filter.q || undefined, status: filter.status || undefined, include_archived: true, limit: LIMIT, offset } })).data,
    placeholderData: keepPreviousData,
  });
  const create = useMutation({
    mutationFn: async (body: Record<string, unknown>) => (await api.post<Event>("/events", body)).data,
    onSuccess: (e) => {
      queryClient.invalidateQueries({ queryKey: ["events"] });
      router.push(`/admin/events/${e.id}`);
    },
  });
  useLeaveOnForbidden(events.error);

  function search(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    setFilter({ q: String(fd.get("q")).trim(), status: String(fd.get("status")) });
    setOffset(0);
  }

  return (
    <section>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <p className="max-w-xl text-sm text-muted">Admin tạo cuộc thi ở trạng thái bản nháp và chỉ định ban tổ chức. Lịch chi tiết, vòng thi, duyệt đội do ban tổ chức vận hành.</p>
        <button type="button" className={buttonClass("accent")} onClick={() => setCreating(!creating)}>
          {creating ? "Đóng form" : "+ Tạo cuộc thi"}
        </button>
      </div>

      {creating && (
        <div className="sketch mt-6 bg-cream p-6">
          <h2 className="mb-4 text-xl font-black">Tạo cuộc thi</h2>
          <FieldsForm fields={CREATE_FIELDS} submitLabel={create.isPending ? "Đang tạo…" : "Tạo bản nháp"} busy={create.isPending} error={create.error} onSubmit={(body) => create.mutate(body)} />
        </div>
      )}

      <form role="search" onSubmit={search} className="mt-7 flex flex-wrap items-end gap-2">
        <label className="min-w-0 flex-[1_1_280px]">
          <span className="text-sm font-bold">Tìm cuộc thi</span>
          <input name="q" type="search" maxLength={100} className="mt-1.5 block min-h-11 w-full rounded-xl border-2 border-ink bg-paper px-3.5" />
        </label>
        <label>
          <span className="text-sm font-bold">Trạng thái</span>
          <select name="status" className="mt-1.5 block min-h-11 rounded-xl border-2 border-ink bg-paper px-3">
            <option value="">Tất cả</option>
            {(Object.keys(EVENT_STATUS) as EventStatus[]).map((s) => (
              <option key={s} value={s}>
                {EVENT_STATUS[s].label}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" className="btn bg-ink text-paper">
          Lọc
        </button>
      </form>

      {events.isError && <div className="mt-4"><FormError>{errorMessage(events.error)}</FormError></div>}
      <div className="sketch mt-5 overflow-x-auto p-0">
        <table className="w-full min-w-[860px] text-left text-sm">
          <thead className="border-b-2 border-ink bg-cream">
            <tr>
              <th className="px-4 py-3">Cuộc thi</th>
              <th className="px-4 py-3">Trạng thái</th>
              <th className="px-4 py-3 text-right">Đội</th>
              <th className="px-4 py-3 text-right">Thí sinh</th>
              <th className="px-4 py-3">Thời gian thi</th>
              <th className="px-4 py-3"><span className="sr-only">Hồ sơ</span></th>
            </tr>
          </thead>
          <tbody>
            {events.data?.items.map((e) => (
              <tr key={e.id} className={`border-t border-line ${e.archived_at ? "bg-warm" : ""}`}>
                <td className="px-4 py-3">
                  <b className="break-words">{e.name}</b>
                  <div className="font-mono text-xs text-muted">/{e.slug}</div>
                </td>
                <td className="space-x-1 px-4 py-3">
                  <EventStatusBadge status={e.status} />
                  {e.archived_at && <span className="chip border-dashed bg-paper">Đã lưu trữ</span>}
                </td>
                <td className="px-4 py-3 text-right font-mono">{e.team_count ?? "—"}</td>
                <td className="px-4 py-3 text-right font-mono">{e.participant_count ?? "—"}</td>
                <td className="px-4 py-3 font-mono text-xs">
                  <LocalTime iso={e.starts_at} dateOnly /> → <LocalTime iso={e.ends_at} dateOnly />
                </td>
                <td className="px-4 py-3 text-right">
                  <Link href={`/admin/events/${e.id}`} className="btn bg-paper text-sm">
                    Hồ sơ
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {events.isPending && <p role="status" className="p-4">Đang tải…</p>}
        {events.data?.total === 0 && <p className="p-4">Chưa có cuộc thi nào khớp.</p>}
      </div>
      {events.data && <Pager offset={offset} limit={LIMIT} total={events.data.total} onChange={setOffset} />}
    </section>
  );
}
