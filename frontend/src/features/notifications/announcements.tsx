"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { buttonClass } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { LocalTime } from "@/components/ui/local-time";
import { Pager } from "@/components/ui/pager";
import { FormError } from "@/features/auth/auth-card";
import type { Page } from "@/features/events/types";
import { api, errorMessage } from "@/lib/api";
import type { components } from "@/lib/api-types";
import { useAuth } from "@/stores/auth";

type Announcement = components["schemas"]["AnnouncementOutput"];
type AnnouncementInput = components["schemas"]["AnnouncementInput"];
type Audience = AnnouncementInput["audience"];

const LIMIT = 10;
export const AUDIENCES: Record<Audience, string> = {
  public: "Công khai (cả khách)",
  all: "Mọi người trong cuộc thi",
  participants: "Thí sinh",
  judges: "Giám khảo",
  mentors: "Mentor",
};

/** Lịch sử thông báo; server tự lọc theo audience của người xem (khách chỉ thấy public). */
export function AnnouncementList({ eventId, title, showAudience }: { eventId: string; title?: string; showAudience?: boolean }) {
  const [offset, setOffset] = useState(0);
  const userId = useAuth((s) => s.user?.id);
  const authLoading = useAuth((s) => s.status === "loading");
  const list = useQuery({
    queryKey: ["announcements", eventId, userId, offset],
    queryFn: async () => (await api.get<Page<Announcement>>(`/events/${eventId}/announcements`, { params: { limit: LIMIT, offset } })).data,
    // Đợi khôi phục phiên để không tải bản của khách rồi tải lại
    enabled: !authLoading,
    placeholderData: keepPreviousData,
  });

  if (list.isError) return <FormError>{errorMessage(list.error)}</FormError>;
  if (!list.data?.total && !showAudience) return null;
  return (
    <section>
      {title && <h2 className="text-[clamp(32px,4vw,48px)] font-black tracking-[-0.045em]">{title}</h2>}
      {list.data?.total === 0 && <p className="text-sm text-muted">Chưa gửi thông báo nào.</p>}
      <ul className={`space-y-3 ${title ? "mt-6" : ""}`}>
        {list.data?.items.map((a) => (
          <li key={a.id} className="rounded-2xl border-2 border-dashed border-ink p-4">
            <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
              <b className="text-[17px]">{a.title}</b>
              <span className="font-mono text-xs text-muted">
                <LocalTime iso={a.created_at} />
              </span>
            </div>
            {showAudience && (
              <p className="mt-1.5 flex flex-wrap gap-1.5">
                <span className="chip bg-cream">{AUDIENCES[a.audience]}</span>
                {a.send_email && <span className="chip bg-sky">Có gửi email</span>}
              </p>
            )}
            <p className="mt-2 whitespace-pre-line text-[15px] leading-relaxed">{a.body}</p>
          </li>
        ))}
      </ul>
      {list.data && list.data.total > LIMIT && <Pager offset={offset} limit={LIMIT} total={list.data.total} onChange={setOffset} />}
    </section>
  );
}

/** BTC gửi thông báo hàng loạt; email do worker gửi sau, chỉ tới tài khoản đã xác thực trong cuộc thi. */
export function AnnouncementForm({ eventId, closed }: { eventId: string; closed: boolean }) {
  const queryClient = useQueryClient();
  const [sent, setSent] = useState(false);
  const send = useMutation({
    mutationFn: async (body: AnnouncementInput) => (await api.post<Announcement>(`/events/${eventId}/announcements`, body)).data,
    onSuccess: () => {
      setSent(true);
      queryClient.invalidateQueries({ queryKey: ["announcements", eventId] });
    },
  });

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const f = new FormData(form);
    const body: AnnouncementInput = {
      title: (f.get("title") as string).trim(),
      body: (f.get("body") as string).trim(),
      audience: f.get("audience") as Audience,
      send_email: f.get("send_email") === "on",
    };
    if (!window.confirm(`Gửi thông báo tới: ${AUDIENCES[body.audience]}${body.send_email ? " (kèm email)" : ""}? Không thu hồi được.`)) return;
    send.mutate(body, { onSuccess: () => form.reset() });
  }

  if (closed) return <p className="text-sm text-muted">Cuộc thi đã kết thúc, không gửi thêm thông báo.</p>;
  return (
    <form onSubmit={submit} onChange={() => setSent(false)} className="max-w-2xl space-y-4">
      <Field label="Tiêu đề" name="title" required maxLength={150} />
      <label className="block">
        <span className="text-sm font-bold">Nội dung (văn bản thuần)</span>
        <textarea name="body" required rows={5} maxLength={5000} className="mt-1.5 block w-full resize-y rounded-xl border-2 border-ink bg-paper px-3.5 py-2.5 text-[15px]" />
      </label>
      <label className="block">
        <span className="text-sm font-bold">Người nhận</span>
        <select name="audience" defaultValue="all" className="mt-1.5 block min-h-11 w-full rounded-xl border-2 border-ink bg-paper px-3 text-[15px]">
          {Object.entries(AUDIENCES).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
      </label>
      <label className="flex min-h-11 items-center gap-2 text-sm font-bold">
        <input type="checkbox" name="send_email" className="size-4 accent-ink" />
        Gửi kèm email (chỉ tài khoản đã xác thực trong cuộc thi; khách không nhận email)
      </label>
      {send.isError && <FormError>{errorMessage(send.error)}</FormError>}
      {sent && (
        <p role="status" className="text-sm font-bold">
          Đã lưu thông báo. Email (nếu chọn) được gửi dần, xem trạng thái ở dashboard.
        </p>
      )}
      <button type="submit" className={buttonClass()} disabled={send.isPending}>
        {send.isPending ? "Đang gửi…" : "Gửi thông báo"}
      </button>
    </form>
  );
}
