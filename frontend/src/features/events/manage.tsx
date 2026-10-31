"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState, type FormEvent, type ReactNode } from "react";
import { buttonClass } from "@/components/ui/button";
import { serverNow } from "@/components/ui/countdown";
import { EVENT_STATUS, type EventStatus } from "@/components/ui/event-status-badge";
import { Field } from "@/components/ui/field";
import { LocalTime } from "@/components/ui/local-time";
import { Pager } from "@/components/ui/pager";
import { FormError } from "@/features/auth/auth-card";
import { api, errorMessage } from "@/lib/api";
import { fromLocalInput, toLocalInput } from "@/lib/datetime";
import type { Event, Page, Registration, RoleItem, Team, Track } from "./types";

// ---------- Form theo danh sách trường ----------

export interface FieldDef {
  key: string;
  label: string;
  type?: "text" | "textarea" | "url" | "email" | "datetime" | "number" | "decimal";
  required?: boolean;
  min?: number;
  hint?: string;
}

type Values = Record<string, unknown>;

const toInput = (f: FieldDef, v: unknown) => (v == null ? "" : f.type === "datetime" ? toLocalInput(String(v)) : String(v));
function fromInput(f: FieldDef, s: string): unknown {
  if (f.type === "datetime") return fromLocalInput(s);
  if (f.type === "number") return s === "" ? null : Number(s);
  return s.trim() === "" ? null : s.trim();
}

/**
 * Form sinh từ danh sách trường. `initial` có = sửa: chỉ gửi trường đã đổi (PATCH);
 * không có = tạo: gửi mọi trường có giá trị.
 */
export function FieldsForm({ fields, initial, submitLabel, onSubmit, busy, error, extra }: { fields: FieldDef[]; initial?: Values; submitLabel: string; onSubmit: (body: Values, form: HTMLFormElement) => void; busy?: boolean; error?: unknown; extra?: ReactNode }) {
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const fd = new FormData(form);
    const body: Values = {};
    for (const f of fields) {
      const raw = String(fd.get(f.key) ?? "");
      if (initial ? raw !== toInput(f, initial[f.key]) : raw.trim() !== "") body[f.key] = fromInput(f, raw);
    }
    if (Object.keys(body).length) onSubmit(body, form);
  }
  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        {fields.map((f) => {
          const common = { name: f.key, required: f.required, defaultValue: toInput(f, initial?.[f.key]) };
          const wide = f.type === "textarea" || f.key === "name";
          return (
            <div key={f.key} className={wide ? "sm:col-span-2" : ""}>
              {f.type === "textarea" ? (
                <label className="block">
                  <span className="text-sm font-bold">{f.label}</span>
                  <textarea {...common} rows={4} maxLength={20000} className="mt-1.5 block w-full rounded-xl border-2 border-ink bg-paper px-3.5 py-2.5 text-[15px]" />
                </label>
              ) : (
                <Field
                  {...common}
                  label={f.label}
                  type={f.type === "datetime" ? "datetime-local" : f.type === "decimal" ? "text" : (f.type ?? "text")}
                  inputMode={f.type === "decimal" ? "decimal" : undefined}
                  min={f.min}
                />
              )}
              {f.hint && <p className="mt-1 text-xs text-muted">{f.hint}</p>}
            </div>
          );
        })}
      </div>
      {extra}
      {error != null && <FormError>{errorMessage(error)}</FormError>}
      <button type="submit" className={buttonClass("primary")} disabled={busy}>
        {submitLabel}
      </button>
    </form>
  );
}

export const EVENT_FIELDS: Record<string, FieldDef> = {
  name: { key: "name", label: "Tên cuộc thi", required: true },
  slug: { key: "slug", label: "Đường dẫn (slug)", required: true, hint: "Chữ thường, số và dấu gạch ngang; không đổi được sau bản nháp." },
  description: { key: "description", label: "Mô tả", type: "textarea" },
  rules: { key: "rules", label: "Thể lệ", type: "textarea" },
  banner_url: { key: "banner_url", label: "Ảnh bìa (URL)", type: "url" },
  registration_opens_at: { key: "registration_opens_at", label: "Mở đăng ký", type: "datetime", required: true },
  registration_closes_at: { key: "registration_closes_at", label: "Đóng đăng ký", type: "datetime", required: true },
  starts_at: { key: "starts_at", label: "Bắt đầu thi", type: "datetime", required: true },
  ends_at: { key: "ends_at", label: "Kết thúc", type: "datetime", required: true },
  min_team_size: { key: "min_team_size", label: "Số người tối thiểu/đội", type: "number", min: 1 },
  max_team_size: { key: "max_team_size", label: "Số người tối đa/đội", type: "number", min: 1 },
};
export const pick = (...keys: string[]) => keys.map((k) => EVENT_FIELDS[k]);

/** Ghi đè cache cuộc thi sau khi sửa, để mọi khối trên trang thấy bản mới. */
export function useEventCache(eventId: string) {
  const queryClient = useQueryClient();
  return (e: Event) => {
    queryClient.setQueryData(["event", eventId], e);
    return queryClient.invalidateQueries({ queryKey: ["events"] });
  };
}

export function useEvent(eventId: string) {
  return useQuery({ queryKey: ["event", eventId], queryFn: async () => (await api.get<Event>(`/events/${eventId}`)).data, enabled: !!eventId });
}

export function useTracks(eventId: string) {
  return useQuery({ queryKey: ["tracks", eventId], queryFn: async () => (await api.get<Page<Track>>(`/events/${eventId}/tracks`, { params: { limit: 100 } })).data.items, enabled: !!eventId });
}

/** Sửa thông tin cuộc thi; `keys` giới hạn trường theo quyền (admin chỉ name/description/banner). */
export function EventEditor({ event, keys }: { event: Event; keys: string[] }) {
  const setEvent = useEventCache(event.id);
  const [saved, setSaved] = useState(false);
  const save = useMutation({
    mutationFn: async (body: Values) => (await api.patch<Event>(`/events/${event.id}`, body)).data,
    onSuccess: (e) => {
      setSaved(true);
      return setEvent(e);
    },
  });
  return (
    <FieldsForm
      key={event.id + event.status}
      fields={pick(...keys)}
      initial={event as unknown as Values}
      submitLabel={save.isPending ? "Đang lưu…" : "Lưu"}
      busy={save.isPending}
      error={save.error}
      onSubmit={(body) => {
        setSaved(false);
        save.mutate(body);
      }}
      extra={saved && !save.isPending && <p role="status" className="text-sm font-semibold">Đã lưu.</p>}
    />
  );
}

// ---------- Trạng thái cuộc thi ----------

const ORDER: EventStatus[] = ["draft", "open", "ongoing", "judging", "closed"];
const WARN: Partial<Record<EventStatus, string>> = {
  open: "Thí sinh bắt đầu đăng ký và lập đội được. Cần có ít nhất một vòng thi hợp lệ.",
  ongoing: "Chỉ chuyển được từ giờ bắt đầu thi; đội chưa duyệt sẽ không được nộp bài.",
  judging: "Ngừng nhận bài, giám khảo bắt đầu chấm.",
  closed: "Cuộc thi kết thúc; mọi vòng phải có kết quả đã công bố. Sau đó chỉ tra cứu, không sửa điểm.",
};

/** Thanh trạng thái một chiều; chỉ BTC chuyển (admin không vận hành thay). */
export function StatusStepper({ event, canTransition }: { event: Event; canTransition: boolean }) {
  const setEvent = useEventCache(event.id);
  const idx = ORDER.indexOf(event.status);
  const next = ORDER[idx + 1];
  const move = useMutation({ mutationFn: async () => (await api.post<Event>(`/events/${event.id}/transition`, { to_status: next })).data, onSuccess: setEvent });
  return (
    <section aria-label="Trạng thái cuộc thi" className="sketch p-5">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-4">
        <ol className="flex flex-[1_1_480px] flex-wrap items-center gap-1.5">
          {ORDER.map((s, i) => (
            <li key={s} className="flex items-center gap-1.5">
              <span aria-current={i === idx ? "step" : undefined} className={`chip min-h-9 px-3.5 text-[13px] ${i === idx ? "bg-orange" : i < idx ? "bg-ink text-paper" : "bg-paper"}`}>
                {EVENT_STATUS[s].label}
              </span>
              {i < ORDER.length - 1 && <span aria-hidden className="font-black text-muted">→</span>}
            </li>
          ))}
        </ol>
        {canTransition && next && (
          <button
            type="button"
            className={buttonClass("primary")}
            disabled={move.isPending}
            onClick={() => {
              if (window.confirm(`Chuyển sang “${EVENT_STATUS[next].label}”? Trạng thái chỉ đi một chiều. ${WARN[next] ?? ""}`)) move.mutate();
            }}
          >
            Chuyển sang “{EVENT_STATUS[next].label}”
          </button>
        )}
      </div>
      {move.isError && <div className="mt-4"><FormError>{errorMessage(move.error)}</FormError></div>}
    </section>
  );
}

// ---------- Danh sách con: vòng / track / giải ----------

export const CRUD = {
  rounds: {
    title: "Vòng thi",
    fields: [
      { key: "name", label: "Tên vòng", required: true },
      { key: "order", label: "Thứ tự", type: "number", min: 1, required: true },
      { key: "required_judges", label: "Số giám khảo mỗi đội", type: "number", min: 1 },
      { key: "starts_at", label: "Bắt đầu", type: "datetime", required: true },
      { key: "submission_deadline", label: "Hạn nộp", type: "datetime", required: true },
      { key: "ends_at", label: "Kết thúc", type: "datetime", required: true },
    ],
    summary: (r: Values) => (
      <>
        Vòng {String(r.order)} · bắt đầu <LocalTime iso={String(r.starts_at)} /> · hạn nộp <LocalTime iso={String(r.submission_deadline)} /> · {String(r.required_judges)} giám khảo/đội
      </>
    ),
  },
  tracks: {
    title: "Track",
    fields: [
      { key: "name", label: "Tên track", required: true },
      { key: "description", label: "Mô tả", type: "textarea", required: true },
    ],
    summary: (t: Values) => <>{String(t.description ?? "")}</>,
  },
  prizes: {
    title: "Giải thưởng",
    fields: [
      { key: "name", label: "Tên giải", required: true },
      { key: "rank", label: "Hạng", type: "number", min: 1, required: true },
      { key: "value", label: "Giá trị (đồng)", type: "decimal", required: true },
      { key: "description", label: "Mô tả", type: "textarea", required: true },
    ],
    summary: (p: Values) => (
      <>
        Hạng {String(p.rank)} · {Number(p.value).toLocaleString("vi-VN")} đ
      </>
    ),
  },
} satisfies Record<string, { title: string; fields: FieldDef[]; summary: (v: Values) => ReactNode }>;

export function CrudPanel({ eventId, kind }: { eventId: string; kind: keyof typeof CRUD }) {
  const cfg = CRUD[kind];
  const queryClient = useQueryClient();
  const key = [kind, eventId];
  const list = useQuery({ queryKey: key, queryFn: async () => (await api.get<Page<Values & { id: string }>>(`/events/${eventId}/${kind}`, { params: { limit: 100 } })).data.items });
  const [editing, setEditing] = useState<string | null>(null);
  const done = () => {
    setEditing(null);
    return queryClient.invalidateQueries({ queryKey: key });
  };
  const save = useMutation({
    mutationFn: ({ id, body }: { id?: string; body: Values }) => (id ? api.patch(`/events/${eventId}/${kind}/${id}`, body) : api.post(`/events/${eventId}/${kind}`, body)),
    onSuccess: done,
  });
  const remove = useMutation({ mutationFn: (id: string) => api.delete(`/events/${eventId}/${kind}/${id}`), onSuccess: done });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-black">{cfg.title}</h2>
        <button type="button" className={buttonClass("accent")} onClick={() => setEditing(editing === "new" ? null : "new")}>
          {editing === "new" ? "Đóng" : "+ Thêm"}
        </button>
      </div>
      {editing === "new" && (
        <div className="rounded-2xl border-2 border-ink bg-cream p-4">
          <FieldsForm fields={cfg.fields as FieldDef[]} submitLabel="Thêm" busy={save.isPending} error={save.error} onSubmit={(body) => save.mutate({ body })} />
        </div>
      )}
      {list.isError && <FormError>{errorMessage(list.error)}</FormError>}
      {remove.isError && <FormError>{errorMessage(remove.error)}</FormError>}
      {list.data?.length === 0 && <p className="font-serif italic text-muted">Chưa có mục nào.</p>}
      <ul className="space-y-2.5">
        {list.data?.map((item) => (
          <li key={item.id} className="rounded-2xl border-2 border-dashed border-ink p-3.5">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
              <span className="min-w-0 flex-[1_1_260px]">
                <b className="break-words">{String(item.name)}</b>
                <span className="block text-sm text-muted">{cfg.summary(item)}</span>
              </span>
              <span className="flex gap-1.5">
                <button type="button" className="btn bg-paper text-sm" onClick={() => setEditing(editing === item.id ? null : item.id)}>
                  {editing === item.id ? "Đóng" : "Sửa"}
                </button>
                <button
                  type="button"
                  className="btn bg-paper text-sm"
                  disabled={remove.isPending}
                  onClick={() => {
                    if (window.confirm(`Xóa “${String(item.name)}”?`)) remove.mutate(item.id);
                  }}
                >
                  Xóa
                </button>
              </span>
            </div>
            {editing === item.id && (
              <div className="mt-3 border-t-2 border-dashed border-line pt-3">
                <FieldsForm fields={cfg.fields as FieldDef[]} initial={item} submitLabel="Lưu" busy={save.isPending} error={save.error} onSubmit={(body) => save.mutate({ id: item.id, body })} />
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

// ---------- Vai trò ----------

const ROLE_LABEL: Record<string, string> = { organizer: "Ban tổ chức", judge: "Giám khảo", mentor: "Mentor", participant: "Thí sinh" };

/** Danh sách và cấp vai trò; `roles` là các vai trò người đang xem được cấp (admin: organizer; BTC: judge, mentor). */
export function RolesPanel({ eventId, roles }: { eventId: string; roles: ("organizer" | "judge" | "mentor")[] }) {
  const queryClient = useQueryClient();
  const key = ["roles", eventId];
  const list = useQuery({ queryKey: key, queryFn: async () => (await api.get<Page<RoleItem>>(`/events/${eventId}/roles`, { params: { limit: 100 } })).data.items });
  const done = () => queryClient.invalidateQueries({ queryKey: key });
  const add = useMutation({ mutationFn: (body: { email: string; role: string }) => api.post(`/events/${eventId}/roles`, body), onSuccess: done });
  const remove = useMutation({ mutationFn: (id: string) => api.delete(`/events/${eventId}/roles/${id}`), onSuccess: done });
  const shown = list.data?.filter((r) => (roles as string[]).includes(r.role));

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const fd = new FormData(form);
    add.mutate({ email: String(fd.get("email")).trim(), role: String(fd.get("role") ?? roles[0]) }, { onSuccess: () => form.reset() });
  }

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-black">{roles.map((r) => ROLE_LABEL[r]).join(" & ")}</h2>
      {list.isError && <FormError>{errorMessage(list.error)}</FormError>}
      {shown?.length === 0 && <p className="font-serif italic text-muted">Chưa có ai.</p>}
      <ul className="space-y-2.5">
        {shown?.map((r) => (
          <li key={r.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-2xl border-2 border-dashed border-ink px-3.5 py-3">
            <span className="min-w-0 flex-[1_1_220px]">
              <b className="break-words">{r.user.full_name}</b>
              <span className="block break-all text-sm text-muted">{r.user.email}</span>
            </span>
            <span className="chip bg-paper">{ROLE_LABEL[r.role]}</span>
            <button
              type="button"
              className="btn bg-paper text-sm"
              disabled={remove.isPending}
              onClick={() => {
                if (window.confirm(`Gỡ vai trò ${ROLE_LABEL[r.role]} của ${r.user.full_name}?`)) remove.mutate(r.id);
              }}
            >
              Gỡ
            </button>
          </li>
        ))}
      </ul>
      {remove.isError && <FormError>{errorMessage(remove.error)}</FormError>}
      <form onSubmit={submit} className="flex flex-wrap items-end gap-2 border-t-2 border-dashed border-line pt-4">
        <div className="min-w-0 flex-[1_1_260px]">
          <Field label="Thêm bằng email (tài khoản đã có)" name="email" type="email" required maxLength={254} />
        </div>
        {roles.length > 1 && (
          <label>
            <span className="text-sm font-bold">Vai trò</span>
            <select name="role" className="mt-1.5 block min-h-11 rounded-xl border-2 border-ink bg-paper px-3">
              {roles.map((r) => (
                <option key={r} value={r}>
                  {ROLE_LABEL[r]}
                </option>
              ))}
            </select>
          </label>
        )}
        <button type="submit" className={buttonClass("primary")} disabled={add.isPending}>
          Thêm
        </button>
        {add.isError && <div className="w-full"><FormError>{errorMessage(add.error)}</FormError></div>}
      </form>
    </div>
  );
}

// ---------- Đội thi ----------

const TEAM_STATUS: Record<Team["status"], [string, string]> = { pending: ["Chờ duyệt", "bg-sun"], approved: ["Đã duyệt", "bg-mint"], rejected: ["Bị từ chối", "bg-rose"] };
const LIMIT = 20;

/** Danh sách đội; `review` = BTC duyệt/từ chối, ngược lại chỉ xem (admin) kèm link hồ sơ. */
export function TeamsPanel({ eventId, review }: { eventId: string; review: boolean }) {
  const queryClient = useQueryClient();
  const tracks = useTracks(eventId);
  const event = useEvent(eventId);
  // Server khóa duyệt đội (TEAM_FROZEN) khi không còn "open" hoặc đã tới giờ thi
  const canDecide = review && event.data?.status === "open" && Date.parse(event.data.starts_at) > serverNow();
  const [status, setStatus] = useState(review ? "pending" : "");
  const [trackId, setTrackId] = useState("");
  const [offset, setOffset] = useState(0);
  const [rejecting, setRejecting] = useState<Team | null>(null);
  const teams = useQuery({
    queryKey: ["event-teams", eventId, status, trackId, offset],
    queryFn: async () => (await api.get<Page<Team>>(`/events/${eventId}/teams`, { params: { status: status || undefined, track_id: trackId || undefined, limit: LIMIT, offset } })).data,
    placeholderData: keepPreviousData,
  });
  const decide = useMutation({
    mutationFn: ({ id, body }: { id: string; body: { status: "approved" | "rejected"; note?: string } }) => api.post(`/teams/${id}/review`, body),
    // Lỗi gửi mail (EMAIL_QUEUE_UNAVAILABLE) vẫn có thể đã lưu quyết định nên luôn tải lại
    onSettled: () => {
      setRejecting(null);
      return queryClient.invalidateQueries({ queryKey: ["event-teams", eventId] });
    },
  });
  const trackName = new Map(tracks.data?.map((t) => [t.id, t.name]));
  const select = "min-h-11 rounded-xl border-2 border-ink bg-paper px-3";

  function reject(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (rejecting) decide.mutate({ id: rejecting.id, body: { status: "rejected", note: String(new FormData(e.currentTarget).get("note")).trim() } });
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h2 className="text-xl font-black">{review ? "Duyệt đội" : "Đội thi"}</h2>
        <div className="flex flex-wrap gap-2">
          <select aria-label="Lọc trạng thái" value={status} onChange={(e) => {
              setStatus(e.target.value);
              setOffset(0);
            }} className={select}>
            <option value="">Mọi trạng thái</option>
            <option value="pending">Chờ duyệt</option>
            <option value="approved">Đã duyệt</option>
            <option value="rejected">Bị từ chối</option>
          </select>
          <select aria-label="Lọc track" value={trackId} onChange={(e) => {
              setTrackId(e.target.value);
              setOffset(0);
            }} className={select}>
            <option value="">Mọi track</option>
            {tracks.data?.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </div>
      </div>
      {teams.isError && <FormError>{errorMessage(teams.error)}</FormError>}
      {decide.isError && <FormError>{errorMessage(decide.error)}</FormError>}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[820px] text-left text-sm">
          <thead className="border-b-2 border-ink">
            <tr>
              <th className="px-3 py-2.5">Đội</th>
              <th className="px-3 py-2.5">Trạng thái</th>
              <th className="px-3 py-2.5">Track</th>
              <th className="px-3 py-2.5">Thành viên</th>
              <th className="px-3 py-2.5">Repo</th>
              <th className="px-3 py-2.5 text-right">{review ? "Quyết định" : <span className="sr-only">Hồ sơ</span>}</th>
            </tr>
          </thead>
          <tbody>
            {teams.data?.items.map((t) => {
              const active = t.members.filter((m) => m.status === "active").length;
              const pending = t.members.length - active;
              return (
                <tr key={t.id} className="border-t border-line align-top">
                  <td className="px-3 py-3 font-extrabold">{t.name}</td>
                  <td className="px-3 py-3">
                    <span className={`chip ${TEAM_STATUS[t.status][1]}`}>{TEAM_STATUS[t.status][0]}</span>
                    {t.review_note && <p className="mt-1 max-w-56 text-xs text-muted">“{t.review_note}”</p>}
                  </td>
                  <td className="px-3 py-3">{(t.track_id && trackName.get(t.track_id)) || "—"}</td>
                  <td className="px-3 py-3 font-mono">
                    {active}
                    {pending > 0 && <span className="text-muted"> + {pending} chờ</span>}
                  </td>
                  <td className="max-w-56 break-all px-3 py-3 font-mono text-xs">{t.repo_url ? <a href={t.repo_url} target="_blank" rel="noreferrer" className="underline">{t.repo_url.replace("https://github.com/", "")}</a> : "—"}</td>
                  <td className="px-3 py-3 text-right">
                    {review && !canDecide ? (
                      <span className="text-sm text-muted">Đã khóa</span>
                    ) : review ? (
                      <span className="inline-flex flex-wrap justify-end gap-1.5">
                        {t.status !== "approved" && (
                          <button type="button" className="btn bg-mint text-sm" disabled={decide.isPending} onClick={() => decide.mutate({ id: t.id, body: { status: "approved" } })}>
                            Duyệt
                          </button>
                        )}
                        {t.status !== "rejected" && (
                          <button type="button" className="btn bg-paper text-sm" onClick={() => setRejecting(t)}>
                            Từ chối…
                          </button>
                        )}
                      </span>
                    ) : (
                      <Link href={`/admin/teams/${t.id}`} className="font-bold underline">
                        Hồ sơ đội →
                      </Link>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {teams.data?.total === 0 && <p className="p-3 font-serif italic text-muted">Không có đội nào khớp.</p>}
      </div>
      {rejecting && canDecide && (
        <form onSubmit={reject} className="rounded-2xl border-2 border-ink bg-rose p-4">
          <label className="block">
            <span className="text-sm font-bold">Lý do từ chối đội {rejecting.name} (bắt buộc, đội sẽ thấy)</span>
            <textarea name="note" required rows={2} maxLength={2000} className="mt-1.5 block w-full rounded-xl border-2 border-ink bg-paper px-3 py-2 text-sm" />
          </label>
          <div className="mt-3 flex gap-2">
            <button type="submit" className={buttonClass("primary")} disabled={decide.isPending}>
              Gửi từ chối
            </button>
            <button type="button" className={buttonClass("secondary")} onClick={() => setRejecting(null)}>
              Hủy
            </button>
          </div>
        </form>
      )}
      {review && <p className="text-sm text-muted">Chỉ duyệt được đội đủ thành viên chính thức, không còn yêu cầu chờ và có repo hợp lệ, trước giờ bắt đầu thi.</p>}
      {teams.data && <Pager offset={offset} limit={LIMIT} total={teams.data.total} onChange={setOffset} />}
    </div>
  );
}

// ---------- Người đăng ký ----------

export function RegistrationsPanel({ eventId }: { eventId: string }) {
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const regs = useQuery({
    queryKey: ["registrations", eventId, q, offset],
    queryFn: async () => (await api.get<Page<Registration>>(`/events/${eventId}/registrations`, { params: { q: q || undefined, limit: LIMIT, offset } })).data,
    placeholderData: keepPreviousData,
  });
  function search(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setQ(String(new FormData(e.currentTarget).get("q")).trim());
    setOffset(0);
  }
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h2 className="text-xl font-black">Người đăng ký</h2>
        <form role="search" onSubmit={search} className="flex items-end gap-2">
          <Field label="Tìm email hoặc họ tên" name="q" type="search" maxLength={100} />
          <button type="submit" className="btn bg-ink text-paper">
            Tìm
          </button>
        </form>
      </div>
      {regs.isError && <FormError>{errorMessage(regs.error)}</FormError>}
      <ul className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
        {regs.data?.items.map((r) => (
          <li key={r.user.id} className={`rounded-2xl border-2 border-dashed border-ink px-3.5 py-3 ${r.team_id ? "" : "bg-cream"}`}>
            <b className="break-words">{r.user.full_name}</b>
            <span className="block break-all text-sm text-muted">{r.user.email}</span>
            <span className="mt-1 block text-xs text-muted">
              Đăng ký <LocalTime iso={r.registered_at} /> · {r.team_id ? (r.member_status === "pending" ? "đang chờ vào đội" : "đã có đội") : "chưa có đội"}
            </span>
          </li>
        ))}
      </ul>
      {regs.data?.total === 0 && <p className="font-serif italic text-muted">Chưa có ai đăng ký.</p>}
      {regs.data && <Pager offset={offset} limit={LIMIT} total={regs.data.total} onChange={setOffset} />}
    </div>
  );
}

// ---------- Khung tab ----------

export function Tabs<K extends string>({ tabs, value, onChange, label }: { tabs: [K, string][]; value: K; onChange: (k: K) => void; label: string }) {
  return (
    <div role="tablist" aria-label={label} className="flex flex-wrap gap-2">
      {tabs.map(([k, text]) => (
        <button key={k} type="button" role="tab" aria-selected={value === k} onClick={() => onChange(k)} className={`btn ${value === k ? "bg-ink text-paper" : "bg-paper"}`}>
          {text}
        </button>
      ))}
    </div>
  );
}
