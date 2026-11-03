"use client";

import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import { isAxiosError } from "axios";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { buttonClass } from "@/components/ui/button";
import { LocalTime } from "@/components/ui/local-time";
import { Pager } from "@/components/ui/pager";
import { JOB_STATUS, VERDICT } from "@/features/ai-reviews/ai-reviews";
import { FormError } from "@/features/auth/auth-card";
import { TEAM_STATUS, useEvent, useTracks } from "@/features/events/manage";
import type { Page } from "@/features/events/types";
import { ASSIGNMENT_STATUS } from "@/features/judging/organizer";
import { PROGRESS } from "@/features/mentor/team-support";
import { useRounds } from "@/features/submissions/submissions";
import { api, codeMessage, errorMessage } from "@/lib/api";
import type { components, operations } from "@/lib/api-types";

type Dashboard = components["schemas"]["Dashboard"];
type Delivery = components["schemas"]["DeliveryOutput"];
type ExportQuery = operations["export_api_v1_events__event_id__reports_export_get"]["parameters"]["query"];
type Labels = Record<string, string | readonly [string, string]>;

const SELECT = "mt-1.5 block min-h-11 w-full rounded-xl border-2 border-ink bg-paper px-3 text-[15px]";
const DELIVERY_STATUS: Labels = { queued: ["Đang chờ", "bg-sun"], sent: ["Đã chuyển đi", "bg-mint"], failed: ["Lỗi", "bg-rose"], unknown: ["Không rõ", "bg-warm"] };
const CHANNEL: Record<Delivery["channel"], string> = { in_app: "Trong ứng dụng", email: "Email" };
// Theo nhóm của mã sự kiện (`team.reviewed` → team); mã mới chưa có nhãn thì hiện nguyên mã
const KIND: Record<string, string> = { announcement: "Thông báo BTC", team: "Đội", mentor: "Mentor", mentors: "Phân công mentor", assignments: "Phân công chấm", sync: "Đồng bộ repo", round: "Lịch vòng", event: "Lịch cuộc thi", results: "Kết quả", submission: "Nhắc hạn nộp", reminder: "Nhắc hạn nộp" };
const LIMIT = 20;

const label = (labels: Labels | undefined, key: string) => {
  const v = labels?.[key];
  return typeof v === "string" ? [v, "bg-sky"] : (v ?? [key, "bg-sky"]);
};

/** Biểu đồ thanh ngang: số liệu vẫn đọc được bằng chữ, thanh chỉ để nhìn nhanh. */
function Bars({ title, data, labels, empty = "Chưa có dữ liệu." }: { title: string; data: Record<string, number>; labels?: Labels; empty?: string }) {
  const entries = Object.entries(data);
  const max = Math.max(1, ...entries.map(([, n]) => n));
  return (
    <section className="rounded-2xl border-2 border-ink p-4">
      <h3 className="font-black">{title}</h3>
      {entries.length === 0 ? (
        <p className="mt-2 text-sm text-muted">{empty}</p>
      ) : (
        <ul className="mt-3 space-y-2">
          {entries.map(([k, n]) => {
            const [text, bg] = label(labels, k);
            return (
              <li key={k} className="grid grid-cols-[minmax(0,8rem)_1fr_auto] items-center gap-2 text-sm">
                <span className="truncate" title={text}>
                  {text}
                </span>
                <span aria-hidden className="h-4 rounded-full border-[1.5px] border-ink bg-paper">
                  <span className={`block h-full rounded-full ${bg}`} style={{ width: `${(n / max) * 100}%` }} />
                </span>
                <b className="font-mono">{n}</b>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function CommitsChart({ data }: { data: Record<string, number> }) {
  const days = Object.entries(data).sort(([a], [b]) => a.localeCompare(b));
  const total = days.reduce((s, [, n]) => s + n, 0);
  const max = Math.max(1, ...days.map(([, n]) => n));
  const w = 24;
  const H = 144;
  return (
    <section className="rounded-2xl border-2 border-ink p-4 lg:col-span-2">
      <h3 className="font-black">Commit theo ngày có commit (UTC)</h3>
      {days.length === 0 ? (
        <p className="mt-2 text-sm text-muted">Chưa có commit trong thời gian thi.</p>
      ) : (
        <>
          <div className="mt-3 overflow-x-auto">
            {/* Vẽ theo pixel thật: vài ngày thì cột vẫn hẹp, nhiều ngày thì cuộn ngang */}
            <svg role="img" aria-label={`${total} commit trong ${days.length} ngày có commit, nhiều nhất ${max} commit một ngày`} width={days.length * w} height={H} viewBox={`0 0 ${days.length * w} ${H}`}>
              {days.map(([day, n], i) => (
                <rect key={day} x={i * w + 3} y={H - 1 - (n / max) * (H - 4)} width={w - 6} height={(n / max) * (H - 4)} rx={3} className="fill-orange stroke-ink" strokeWidth={1.5}>
                  <title>{`${day}: ${n} commit`}</title>
                </rect>
              ))}
            </svg>
          </div>
          <p className="mt-1 flex flex-wrap justify-between gap-x-3 font-mono text-xs text-muted">
            <span>{days[0][0]}</span>
            <span>
              Tổng {total} · cao nhất {max}/ngày
            </span>
            <span>{days.at(-1)?.[0]}</span>
          </p>
        </>
      )}
    </section>
  );
}

function Stat({ label, value, warn }: { label: string; value: number; warn?: boolean }) {
  return (
    <div className={`rounded-[18px] border-2 border-ink p-4 ${warn && value > 0 ? "bg-rose" : "bg-cream"}`}>
      <dt className="text-sm font-semibold">{label}</dt>
      <dd className="mt-1 font-mono text-3xl font-extrabold">{value}</dd>
    </div>
  );
}

export function DashboardPanel({ eventId }: { eventId: string }) {
  const rounds = useRounds(eventId);
  const dash = useQuery({ queryKey: ["dashboard", eventId], queryFn: async () => (await api.get<Dashboard>(`/events/${eventId}/dashboard`)).data, refetchInterval: 60_000 });
  if (dash.isError) return <FormError>{errorMessage(dash.error)}</FormError>;
  const d = dash.data;
  if (!d) return <p role="status">Đang tải…</p>;
  const roundName: Labels = Object.fromEntries((rounds.data ?? []).map((r) => [r.id, `V${r.order} · ${r.name}`]));

  return (
    <div className="space-y-6">
      <dl className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Stat label="Người đăng ký" value={d.registrations} />
        <Stat label="Đội đã duyệt" value={d.teams_by_status.approved ?? 0} />
        <Stat label="Đội chưa phân công chấm" value={d.unassigned_teams} warn />
        <Stat label="Đội chưa nộp bài" value={d.unsubmitted_teams} warn />
        <Stat label="Câu hỏi chưa xong" value={d.unresolved_questions} warn />
        <Stat label="Lỗi đồng bộ repo" value={d.sync_errors} warn />
      </dl>
      <div className="grid gap-4 lg:grid-cols-2">
        <CommitsChart data={d.commits_per_day} />
        <Bars title="Đội theo trạng thái" data={d.teams_by_status} labels={TEAM_STATUS} />
        <Bars title="Bài nộp theo vòng" data={d.submissions_by_round} labels={roundName} empty="Chưa có bài nộp." />
        <Bars title="Tiến độ chấm (phân công)" data={d.judging_progress} labels={ASSIGNMENT_STATUS} empty="Chưa phân công chấm." />
        <Bars title="Ghi nhận mentor gần nhất" data={d.mentor_progress} labels={PROGRESS} empty="Mentor chưa ghi nhận tiến độ." />
        <Bars title="AI review theo kết luận (tham khảo)" data={d.ai_verdict_counts} labels={VERDICT} empty="Chưa có AI review." />
        <Bars title="Job AI" data={d.ai_job_counts} labels={JOB_STATUS} empty="Chưa có job AI." />
      </div>
    </div>
  );
}

/** Nhật ký gửi thông báo: không chứa email đích hay nội dung, chỉ trạng thái giao nhận. */
export function DeliveriesPanel({ eventId }: { eventId: string }) {
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const list = useQuery({
    queryKey: ["deliveries", eventId, status, offset],
    queryFn: async () => (await api.get<Page<Delivery>>(`/events/${eventId}/notification-deliveries`, { params: { status: status || undefined, limit: LIMIT, offset } })).data,
    placeholderData: keepPreviousData,
  });

  return (
    <div className="space-y-3">
      <label className="block max-w-56">
        <span className="text-sm font-bold">Trạng thái</span>
        <select
          className={SELECT}
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setOffset(0);
          }}
        >
          <option value="">Tất cả</option>
          {Object.entries(DELIVERY_STATUS).map(([k, v]) => (
            <option key={k} value={k}>
              {v[0]}
            </option>
          ))}
        </select>
      </label>
      <p className="text-sm text-muted">&quot;Đã chuyển đi&quot; nghĩa là máy chủ mail đã nhận, chưa chắc tới hộp thư. &quot;Không rõ&quot; không tự gửi lại để tránh trùng.</p>
      {list.isError && <FormError>{errorMessage(list.error)}</FormError>}
      {list.data?.items.length === 0 && <p className="text-sm text-muted">Chưa có lượt gửi.</p>}
      {!!list.data?.items.length && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead>
              <tr className="border-b-2 border-ink">
                <th className="py-2 pr-3">Cập nhật</th>
                <th className="py-2 pr-3">Loại</th>
                <th className="py-2 pr-3">Kênh</th>
                <th className="py-2 pr-3">Trạng thái</th>
                <th className="py-2">Ghi chú</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-dashed divide-line">
              {list.data.items.map((d) => {
                const [text, bg] = label(DELIVERY_STATUS, d.status);
                return (
                  <tr key={d.id}>
                    <td className="py-2 pr-3 font-mono text-xs">
                      <LocalTime iso={d.updated_at} />
                    </td>
                    <td className="py-2 pr-3" title={d.notification_type}>
                      {KIND[d.notification_type.split(".")[0]] ?? <span className="font-mono text-xs">{d.notification_type}</span>}
                    </td>
                    <td className="py-2 pr-3">{CHANNEL[d.channel]}</td>
                    <td className="py-2 pr-3">
                      <span className={`chip ${bg}`}>{text}</span>
                    </td>
                    <td className="py-2">{d.error_code ? codeMessage(d.error_code) : d.recipient_id ? "" : "Người được mời chưa có tài khoản"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {list.data && list.data.total > LIMIT && <Pager offset={offset} limit={LIMIT} total={list.data.total} onChange={setOffset} />}
    </div>
  );
}

const TYPES: Record<ExportQuery["type"], string> = { teams: "Danh sách đội", submissions: "Bài nộp (mọi phiên bản)", leaderboard: "Bảng xếp hạng (vòng đã khóa điểm)" };

async function download(eventId: string, query: ExportQuery) {
  try {
    const { data } = await api.get<Blob>(`/events/${eventId}/reports/export`, { params: query, responseType: "blob", timeout: 120_000 });
    const url = URL.createObjectURL(data);
    const a = document.createElement("a");
    a.href = url;
    a.download = `seal-${query.type}-${new Date().toISOString().slice(0, 10)}.${query.format}`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1_000);
  } catch (e) {
    // responseType blob làm body lỗi thành Blob; đọc lại JSON để hiện đúng mã lỗi
    if (isAxiosError(e) && e.response?.data instanceof Blob) e.response.data = await e.response.data.text().then(JSON.parse).catch(() => undefined);
    throw e;
  }
}

/** Xuất báo cáo xlsx/pdf; dùng chung cho BTC và admin (server kiểm quyền và chặn điểm chưa khóa). */
export function ExportForm({ eventId }: { eventId: string }) {
  const rounds = useRounds(eventId);
  const tracks = useTracks(eventId);
  const [type, setType] = useState<ExportQuery["type"]>("teams");
  const run = useMutation({ mutationFn: (q: ExportQuery) => download(eventId, q) });

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    run.mutate({ type, format: f.get("format") as ExportQuery["format"], round_id: (f.get("round_id") as string) || undefined, track_id: (f.get("track_id") as string) || undefined });
  }

  return (
    <form onSubmit={submit} onChange={() => run.reset()} className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <label className="block">
          <span className="text-sm font-bold">Loại báo cáo</span>
          <select className={SELECT} value={type} onChange={(e) => setType(e.target.value as ExportQuery["type"])}>
            {Object.entries(TYPES).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="text-sm font-bold">Định dạng</span>
          <select name="format" className={SELECT} defaultValue="xlsx">
            <option value="xlsx">Excel (.xlsx)</option>
            <option value="pdf">PDF</option>
          </select>
        </label>
        <label className="block">
          <span className="text-sm font-bold">Vòng{type === "leaderboard" ? "" : " (tuỳ chọn)"}</span>
          <select key={type} name="round_id" className={SELECT} required={type === "leaderboard"} defaultValue="">
            <option value="" disabled={type === "leaderboard"}>
              {type === "leaderboard" ? "Chọn vòng" : "Mọi vòng"}
            </option>
            {rounds.data?.map((r) => (
              <option key={r.id} value={r.id}>
                V{r.order} · {r.name}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="text-sm font-bold">Track (tuỳ chọn)</span>
          <select name="track_id" className={SELECT} defaultValue="">
            <option value="">Mọi track</option>
            {tracks.data?.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className="text-sm text-muted">Tối đa 10.000 dòng mỗi lần. Báo cáo không kèm mật khẩu, mã mời, URL file hay tên giám khảo.</p>
      {run.isError && <FormError>{errorMessage(run.error)}</FormError>}
      <button type="submit" className={buttonClass()} disabled={run.isPending}>
        {run.isPending ? "Đang tạo file…" : "Tải báo cáo"}
      </button>
    </form>
  );
}

/** Trang `/manage/events/[id]/dashboard` của BTC. */
export function EventDashboard({ eventId }: { eventId: string }) {
  const event = useEvent(eventId);
  return (
    <main className="mx-auto max-w-[1360px] space-y-8 px-4 pb-24 pt-8 sm:px-6">
      <div>
        <Link href={`/manage/events/${eventId}`} className="text-sm font-bold">
          ← Khu vận hành
        </Link>
        <p className="mt-3 font-serif text-lg italic">Dashboard</p>
        <h1 className="mt-1 break-words text-[clamp(36px,5vw,56px)] font-black leading-none tracking-[-0.045em]">{event.data?.name ?? "…"}.</h1>
      </div>
      <DashboardPanel eventId={eventId} />
      <section className="sketch p-6">
        <h2 className="mb-4 text-xl font-black">Xuất báo cáo</h2>
        <ExportForm eventId={eventId} />
      </section>
      <section className="sketch p-6">
        <h2 className="mb-4 text-xl font-black">Lịch sử gửi thông báo</h2>
        <DeliveriesPanel eventId={eventId} />
      </section>
    </main>
  );
}
