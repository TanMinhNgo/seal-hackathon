"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import type { ReactNode } from "react";
import { buttonClass } from "@/components/ui/button";
import { FormError } from "@/features/auth/auth-card";
import { api, errorMessage } from "@/lib/api";
import type { components } from "@/lib/api-types";
import { useLeaveOnForbidden } from "./use-leave-on-forbidden";

type AuditLogPage = components["schemas"]["AuditLogPage"];
type SystemOverviewData = components["schemas"]["SystemOverview"];
type Status = components["schemas"]["ServiceStatus"]["status"];

const STATUS: Record<Status, [string, string]> = {
  ok: ["Hoạt động", "bg-mint"],
  degraded: ["Chậm", "bg-sun"],
  down: ["Ngừng", "bg-orange"],
  not_configured: ["Chưa cấu hình", "bg-warm"],
};
const SERVICE_NAMES: Record<string, string> = {
  api: "API",
  database: "Cơ sở dữ liệu",
  redis: "Redis",
  worker: "Worker (Celery)",
  beat: "Lịch chạy (Beat)",
  email_queue: "Hàng đợi email",
  storage: "Lưu trữ file",
};

const count = (n: number) => n.toLocaleString("vi-VN");
const bytes = (n: number | null | undefined) => {
  if (n == null) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = n > 0 ? Math.min(Math.floor(Math.log(n) / Math.log(1024)), units.length - 1) : 0;
  return `${(n / 1024 ** i).toFixed(i ? 1 : 0)} ${units[i]}`;
};
const time = (iso: string) => new Date(iso).toLocaleString("vi-VN");

function Card({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section className="sketch p-6">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-black tracking-tight">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

export function SystemOverview() {
  // API: đo trực tiếp từ trình duyệt nên luôn có, kể cả khi /admin/system chưa sẵn sàng
  const health = useQuery({
    queryKey: ["health"],
    queryFn: async () => {
      const start = performance.now();
      await api.get("/health");
      return Math.round(performance.now() - start);
    },
    refetchInterval: 30_000,
    retry: false,
  });
  const system = useQuery({
    queryKey: ["admin-system"],
    queryFn: async () => (await api.get<SystemOverviewData>("/admin/system")).data,
    refetchInterval: 30_000,
    retry: false,
  });
  const recent = useQuery({
    queryKey: ["audit-logs", "recent"],
    queryFn: async () => (await api.get<AuditLogPage>("/admin/audit-logs", { params: { limit: 5 } })).data,
  });
  useLeaveOnForbidden(system.error ?? recent.error);
  // CSDL ngừng thì BE trả số 0 giả; không được hiện như dữ liệu rỗng
  const dbDown = system.data?.services.some((s) => s.name === "database" && s.status === "down");
  const d = dbDown ? undefined : system.data?.data;

  return (
    <div className="space-y-7">
      <Card
        title="Tình trạng hệ thống"
        action={
          <span className="flex items-center gap-3 text-sm text-muted">
            {system.dataUpdatedAt > 0 && <span>Cập nhật {new Date(system.dataUpdatedAt).toLocaleTimeString("vi-VN")}</span>}
            <button type="button" className="btn bg-paper" onClick={() => { health.refetch(); system.refetch(); }} disabled={system.isFetching}>
              Làm mới
            </button>
          </span>
        }
      >
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <ServiceTile name="api" status={health.isError ? "down" : health.data !== undefined ? "ok" : null} latency={health.data ?? null} detail={health.isError ? errorMessage(health.error) : null} />
          {system.data?.services.map((s) => <ServiceTile key={s.name} name={s.name} status={s.status} latency={s.latency_ms ?? null} detail={s.detail ?? null} />)}
        </ul>
        {system.isError && (
          <div className="mt-4">
            <FormError>{errorMessage(system.error)}</FormError>
          </div>
        )}
      </Card>

      <Card title="Dữ liệu lưu trữ">
        {dbDown ? (
          <FormError>Cơ sở dữ liệu không phản hồi nên chưa có thống kê. Số liệu sẽ hiện lại khi cơ sở dữ liệu hoạt động.</FormError>
        ) : (
          <dl className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5">
            <Stat label="Tài khoản" value={d && count(d.users)} note={d && `${count(d.active_users)} hoạt động · ${count(d.admins)} admin`} bg="bg-cream" />
            <Stat label="Cuộc thi" value={d && count(d.events)} />
            <Stat label="Đội thi" value={d && count(d.teams)} />
            <Stat label="Bài nộp" value={d && count(d.submissions)} />
            <Stat label="Commit đã đồng bộ" value={d && count(d.commits)} bg="bg-sky" />
            <Stat label="Đánh giá AI" value={d && count(d.ai_reviews)} />
            <Stat label="Bản ghi nhật ký" value={d && count(d.audit_logs)} />
            <Stat label="Dung lượng CSDL" value={d && bytes(d.database_bytes)} bg="bg-mint" />
            <Stat label="Dung lượng file" value={d && bytes(d.storage_bytes)} bg="bg-mint" />
          </dl>
        )}
      </Card>

      <Card
        title="Hoạt động gần đây"
        action={
          <Link href="/admin/audit-logs" className={buttonClass("secondary")}>
            Xem toàn bộ nhật ký
          </Link>
        }
      >
        {recent.isError && <FormError>{errorMessage(recent.error)}</FormError>}
        {recent.data?.total === 0 && <p className="font-serif italic text-muted">Chưa có thao tác nào được ghi.</p>}
        <ol className="divide-y divide-dashed divide-line">
          {recent.data?.items.map((l) => (
            <li key={l.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-3 text-sm">
              <span className="font-mono text-muted">{time(l.created_at)}</span>
              <b className="break-all">{l.actor_email}</b>
              <span className="chip bg-paper font-mono">{l.action}</span>
              <span className="break-all font-mono text-xs text-muted">
                {l.target_type} {l.target_id}
              </span>
            </li>
          ))}
        </ol>
      </Card>
    </div>
  );
}

function ServiceTile({ name, status, latency, detail }: { name: string; status: Status | null; latency: number | null; detail: string | null }) {
  const [label, bg] = status ? STATUS[status] : ["Đang kiểm tra…", "bg-paper"];
  return (
    <li className="rounded-2xl border-2 border-ink p-4">
      <div className="flex items-start justify-between gap-2">
        <span className="font-bold">{SERVICE_NAMES[name] ?? name}</span>
        <span className={`chip ${bg}`}>{label}</span>
      </div>
      <p className="mt-2 font-mono text-sm tabular-nums text-muted">{latency !== null ? `${latency} ms` : "—"}</p>
      {detail && <p className="mt-1 break-words text-xs text-muted">{detail}</p>}
    </li>
  );
}

function Stat({ label, value, note, bg = "bg-paper" }: { label: string; value: string | undefined; note?: string; bg?: string }) {
  return (
    <div className={`rounded-2xl border-2 border-ink p-4 ${bg}`}>
      <dt className="text-sm font-semibold">{label}</dt>
      <dd className="mt-1 font-mono text-[28px] font-extrabold tabular-nums leading-none">{value ?? "…"}</dd>
      {note && <dd className="mt-1.5 text-xs text-muted">{note}</dd>}
    </div>
  );
}
