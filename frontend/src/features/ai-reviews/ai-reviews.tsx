"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { LocalTime } from "@/components/ui/local-time";
import { Pager } from "@/components/ui/pager";
import { FormError } from "@/features/auth/auth-card";
import { useForgetTeamOnForbidden } from "@/features/commits/commits";
import type { Event, Page } from "@/features/events/types";
import { useRounds } from "@/features/submissions/submissions";
import { api, errorCode, errorMessage } from "@/lib/api";
import type { components } from "@/lib/api-types";
import { useRealtime } from "@/lib/realtime";
import { useAuth } from "@/stores/auth";

type S = components["schemas"];
type Review = S["ReviewOutput"];
type Summary = S["AiSummary"];
type Flag = S["FlagOutput"];
/** organizer: retry + xử lý flag; judge: gửi flag; readonly: admin/mentor/thí sinh. */
export type AiMode = "organizer" | "judge" | "readonly";

const LIMIT = 10;
const INPUT = "mt-1.5 block w-full rounded-xl border-2 border-ink bg-paper px-3 text-[15px]";

export const VERDICT: Record<Review["verdict"], [string, string]> = {
  good: ["Tốt", "bg-mint"],
  pass: ["Đạt", "bg-sun"],
  needs_improvement: ["Cần cải thiện", "bg-rose"],
};
const SEVERITY: Record<S["Issue"]["severity"], [string, string]> = {
  high: ["Cao", "bg-rose"],
  medium: ["Vừa", "bg-sun"],
  low: ["Thấp", "bg-paper"],
};
const SCORE_LABEL: Record<keyof S["Scores"], string> = {
  correctness: "Đúng đắn",
  security: "Bảo mật",
  clean_code: "Code sạch",
  structure: "Cấu trúc",
  error_handling: "Xử lý lỗi",
  testing: "Kiểm thử",
  commit_hygiene: "Commit",
};
const FLAG_STATUS: Record<Review["flag_status"], string> = {
  none: "",
  open: "Giám khảo báo sai · chờ BTC",
  acknowledged: "BTC xác nhận AI sai",
  dismissed: "BTC giữ nguyên đánh giá",
};
export const JOB_STATUS: Record<S["LastJob"]["status"], string> = {
  queued: "Đang chờ",
  running: "Đang chạy",
  completed: "Xong",
  skipped: "Bỏ qua",
  failed: "Lỗi",
};
// Mã lỗi/skip an toàn từ BE; mã lạ thì hiện nguyên mã
const AI_CODE: Record<string, string> = {
  AI_NOT_CONFIGURED: "Máy chủ chưa cấu hình nhà cung cấp AI.",
  AI_SCHEMA_INVALID: "AI trả kết quả sai định dạng.",
  AI_OUTPUT_TRUNCATED: "Kết quả AI bị cắt vì quá dài so với giới hạn output.",
  AI_PROVIDER_UNAVAILABLE: "Nhà cung cấp AI không phản hồi.",
  AI_RATE_LIMITED: "Nhà cung cấp AI đang giới hạn tần suất.",
  AI_PROVIDER_TIMEOUT: "AI phản hồi quá thời gian (khoản token đã giữ không hoàn lại).",
  AI_PROVIDER_REJECTED: "Nhà cung cấp AI từ chối yêu cầu.",
  AI_WORKER_TIMEOUT: "Worker AI quá giờ (khoản token đã giữ không hoàn lại).",
  AI_DISABLED: "AI review đang tắt cho vòng này.",
  AI_NO_CODE_CHANGES: "Không có thay đổi code để đánh giá (chỉ tài liệu, file sinh tự động hoặc merge).",
  AI_INCOMPLETE_COMPARE: "Không lấy đủ diff (force push hoặc lịch sử thiếu).",
  AI_ROUND_BOUNDARY: "Lượt đồng bộ vắt qua hai vòng nên không đánh giá.",
  AI_EVENT_STOPPED: "Cuộc thi đã dừng nhận đánh giá.",
  AI_BUDGET_EXHAUSTED: "Hết ngân sách token của đội cho vòng này.",
  AI_LEASE_LOST: "Worker AI mất quyền xử lý job giữa chừng.",
  GITHUB_UNAVAILABLE: "GitHub không phản hồi khi lấy diff.",
  REPO_NOT_ACCESSIBLE: "Không đọc được repo hoặc commit trên GitHub (private, bị xóa hoặc lịch sử đã đổi).",
  GITHUB_RATE_LIMITED: "Đã chạm giới hạn gọi GitHub khi lấy diff.",
  SYNC_COORDINATION_UNAVAILABLE: "Bộ điều phối tạm thời không truy cập được.",
};
const aiCode = (c: string | null | undefined) => (c ? (AI_CODE[c] ?? c) : "");
const fmt = (n: number) => n.toLocaleString("vi-VN", { maximumFractionDigits: 1 });

/** Nhãn bắt buộc ở mọi nơi có điểm AI. */
export function AiBadge() {
  return <span className="chip bg-sky text-xs">AI – chỉ tham khảo</span>;
}

function useAiSummary(teamId: string, roundId?: string) {
  return useQuery({
    queryKey: ["ai-summary", teamId, roundId ?? ""],
    queryFn: async () =>
      (
        await api.get<Summary>(`/teams/${teamId}/ai-summary`, {
          params: { round_id: roundId },
        })
      ).data,
    // Chỉ BTC/admin nhận `jobs`; còn job chờ/chạy thì đọc lại để thấy review mới
    refetchInterval: (q) => (q.state.data?.jobs && q.state.data.jobs.queued + q.state.data.jobs.running > 0 ? 10_000 : false),
  });
}

/** Biểu đồ điểm theo thời gian bằng SVG thuần, thang 0–10. */
function ScoreChart({ points }: { points: Summary["timeline"] }) {
  if (points.length < 2) return null;
  const W = 300;
  const H = 80;
  const t = points.map((p) => Date.parse(p.at));
  const [t0, t1] = [Math.min(...t), Math.max(...t)];
  const xy = points.map((p, i) => [t1 === t0 ? (i / (points.length - 1)) * W : ((t[i] - t0) / (t1 - t0)) * W, H - (p.score / 10) * H] as const);
  return (
    <figure className="max-w-md">
      <figcaption className="text-xs font-bold text-muted">Điểm AI theo thời gian (thang 0–10, vạch đứt là 5)</figcaption>
      <svg viewBox={`-6 -6 ${W + 12} ${H + 12}`} className="h-24 w-full" role="img" aria-label={`Điểm AI theo thời gian: ${points.map((p) => fmt(p.score)).join(", ")}`}>
        <line x1={0} x2={W} y1={H / 2} y2={H / 2} className="stroke-ink/20" strokeDasharray="4 4" />
        <polyline points={xy.map((p) => p.join(",")).join(" ")} fill="none" className="stroke-orange" strokeWidth={3} strokeLinejoin="round" />
        {xy.map(([x, y], i) => (
          <circle key={i} cx={x} cy={y} r={4} className="fill-paper stroke-ink" strokeWidth={2} />
        ))}
      </svg>
    </figure>
  );
}

function SummaryPanel({ teamId, roundId, mode }: { teamId: string; roundId?: string; mode: AiMode }) {
  const summary = useAiSummary(teamId, roundId);
  const queryClient = useQueryClient();
  const retry = useMutation({
    mutationFn: (jobId: string) => api.post(`/teams/${teamId}/ai-reviews/retry`, { job_id: jobId }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["ai-summary", teamId] }),
  });
  useForgetTeamOnForbidden(teamId, summary.error);
  if (errorCode(summary.error) === "FORBIDDEN") return <p className="font-serif italic text-muted">Báo cáo AI chưa mở cho bạn ở vòng này.</p>;
  if (summary.isError) return <FormError>{errorMessage(summary.error)}</FormError>;
  if (!summary.data) return <p role="status">Đang tải…</p>;
  const s = summary.data;
  const cell = "rounded-2xl border-2 border-ink bg-paper px-4 py-3";
  const job = s.last_job;
  return (
    <div className="@container space-y-3">
      {s.score_spike && (
        <p className="rounded-xl border-2 border-ink bg-sun px-3.5 py-2.5 text-sm font-semibold">Điểm review gần nhất tăng đột biến (≥ 3 điểm so với trung bình trước). Chỉ là tín hiệu để xem kỹ, không phải kết luận gian lận.</p>
      )}
      <div className="grid gap-3 @md:grid-cols-2 @3xl:grid-cols-4">
        <div className={cell}>
          <p className="text-xs font-bold text-muted">Điểm trung bình (theo dòng thay đổi)</p>
          <p className="text-2xl font-black">
            {s.avg_score == null ? (
              <span className="text-base">Chưa có review</span>
            ) : (
              <>
                {fmt(s.avg_score)}
                <span className="text-sm text-muted">/10</span>
              </>
            )}
          </p>
        </div>
        <div className={cell}>
          <p className="text-xs font-bold text-muted">Phân loại</p>
          <p className="mt-1 flex flex-wrap gap-1.5">
            {(Object.keys(VERDICT) as Review["verdict"][]).map((v) => (
              <span key={v} className={`chip text-xs ${VERDICT[v][1]}`}>
                {VERDICT[v][0]} · {s.verdict_counts[v] ?? 0}
              </span>
            ))}
          </p>
        </div>
        <div className={cell}>
          <p className="text-xs font-bold text-muted">Review có lỗi nghiêm trọng</p>
          <p className="text-2xl font-black">{s.critical_count}</p>
        </div>
        <div className={cell}>
          <p className="text-xs font-bold text-muted">Lỗi hay gặp</p>
          {s.top_issues.length ? (
            <ul className="mt-1 text-sm">
              {s.top_issues.slice(0, 3).map((i) => (
                <li key={i.category}>
                  {i.category} · <b>{i.count}</b>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm">Chưa có</p>
          )}
        </div>
      </div>
      <ScoreChart points={s.timeline} />
      {s.jobs && (
        <div className="space-y-2 rounded-2xl border-2 border-dashed border-ink px-4 py-3 text-sm">
          <p>
            Job: chờ {s.jobs.queued} · chạy {s.jobs.running} · xong {s.jobs.completed} · bỏ qua {s.jobs.skipped} · lỗi {s.jobs.failed}
            {s.token_budget != null && (
              <>
                {" "}
                · token đã dùng/giữ <b>{(s.tokens_used ?? 0).toLocaleString("vi-VN")}</b> / {s.token_budget.toLocaleString("vi-VN")}
              </>
            )}
          </p>
          {s.budget_exhausted && <p className="font-semibold text-minus">Có job bị bỏ qua vì thiếu ngân sách token. Bài nộp và chấm điểm của giám khảo không bị ảnh hưởng.</p>}
          {job && (
            <p className="flex flex-wrap items-center gap-2">
              <span>
                Job gần nhất: <b>{JOB_STATUS[job.status]}</b> (lần thử {job.attempts}){job.error_code && ` · ${aiCode(job.error_code)}`}
              </span>
              {mode === "organizer" && job.can_retry && (
                <button type="button" className="btn min-h-9 bg-orange text-sm font-extrabold" disabled={retry.isPending} onClick={() => retry.mutate(job.id)}>
                  Thử lại job
                </button>
              )}
              {retry.isSuccess && (
                <span role="status" className="text-xs font-semibold">
                  Đã xếp lịch, review sẽ có sau khi worker chạy xong.
                </span>
              )}
              {retry.isError && (
                <span role="alert" className="text-xs font-semibold text-minus">
                  {errorMessage(retry.error)}
                </span>
              )}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

/** Phản hồi của giám khảo về một review. BTC/admin đọc danh tính và lý do; chỉ BTC xử lý. */
function FlagsPanel({ reviewId, canResolve }: { reviewId: string; canResolve: boolean }) {
  const queryClient = useQueryClient();
  const flags = useQuery({
    queryKey: ["ai-flags", reviewId],
    queryFn: async () =>
      (
        await api.get<Page<Flag>>(`/ai-reviews/${reviewId}/flags`, {
          params: { limit: 100 },
        })
      ).data,
  });
  const resolve = useMutation({
    mutationFn: (v: { id: string; decision: "acknowledged" | "dismissed"; note: string }) =>
      api.post(`/ai-review-flags/${v.id}/resolve`, {
        decision: v.decision,
        note: v.note,
      }),
    onSuccess: () => Promise.all([queryClient.invalidateQueries({ queryKey: ["ai-flags", reviewId] }), queryClient.invalidateQueries({ queryKey: ["ai-reviews"] })]),
  });
  if (flags.isError) return <FormError>{errorMessage(flags.error)}</FormError>;
  if (!flags.data) return <p role="status">Đang tải…</p>;
  if (!flags.data.total) return <p className="text-sm text-muted">Chưa có phản hồi.</p>;
  return (
    <ul className="space-y-2">
      {flags.data.items.map((f) => (
        <li key={f.id} className="rounded-xl border-2 border-ink bg-paper px-3 py-2 text-sm">
          <p>
            <b>{f.judge.full_name}</b> · <LocalTime iso={f.created_at} /> · {f.status === "open" ? "Chờ xử lý" : f.status === "acknowledged" ? "Đã xác nhận AI sai" : "Đã bác"}
          </p>
          <p className="mt-1 whitespace-pre-wrap break-words">{f.reason}</p>
          {f.resolution_note && <p className="mt-1 text-muted">BTC: {f.resolution_note}</p>}
          {canResolve && f.status === "open" && (
            <form
              className="mt-2 space-y-2"
              onSubmit={(e) => {
                e.preventDefault();
                const fd = new FormData(e.currentTarget);
                const submitter = (e.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null;
                resolve.mutate({
                  id: f.id,
                  decision: submitter?.value === "dismissed" ? "dismissed" : "acknowledged",
                  note: String(fd.get("note")).trim(),
                });
              }}
            >
              <label className="block text-xs font-bold">
                Ghi chú xử lý
                <textarea name="note" required maxLength={2000} rows={2} className={`${INPUT} py-2`} />
              </label>
              <div className="flex flex-wrap gap-2">
                <button type="submit" value="acknowledged" className="btn min-h-9 bg-mint text-sm" disabled={resolve.isPending}>
                  AI đánh giá sai
                </button>
                <button type="submit" value="dismissed" className="btn min-h-9 bg-paper text-sm" disabled={resolve.isPending}>
                  Giữ nguyên đánh giá AI
                </button>
              </div>
              {resolve.isError && <FormError>{errorMessage(resolve.error)}</FormError>}
            </form>
          )}
        </li>
      ))}
    </ul>
  );
}

function FlagForm({ reviewId }: { reviewId: string }) {
  const queryClient = useQueryClient();
  const flag = useMutation({
    mutationFn: (reason: string) => api.post(`/ai-reviews/${reviewId}/flag`, { reason }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["ai-reviews"] }),
  });
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    flag.mutate(String(new FormData(e.currentTarget).get("reason")).trim());
  }
  return (
    <form onSubmit={submit} className="space-y-2">
      <label className="block text-xs font-bold">
        AI đánh giá sai ở đâu? (gửi lại sẽ cập nhật phản hồi cũ)
        <textarea name="reason" required maxLength={2000} rows={2} className={`${INPUT} py-2`} />
      </label>
      <button type="submit" className="btn min-h-9 bg-paper text-sm" disabled={flag.isPending}>
        Đánh dấu đánh giá sai
      </button>
      {flag.isSuccess && (
        <span role="status" className="ml-2 text-xs font-semibold">
          Đã gửi phản hồi cho BTC.
        </span>
      )}
      {flag.isError && <FormError>{errorMessage(flag.error)}</FormError>}
    </form>
  );
}

function ReviewCard({ r, mode, canReadFlags }: { r: Review; mode: AiMode; canReadFlags: boolean }) {
  const [open, setOpen] = useState(false);
  const [showFlags, setShowFlags] = useState(false);
  return (
    <li className="rounded-[18px] border-2 border-ink bg-paper px-4 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xl font-black">
          {fmt(r.overall)}
          <span className="text-sm text-muted">/10</span>
        </span>
        <span className={`chip text-xs ${VERDICT[r.verdict][1]}`}>{VERDICT[r.verdict][0]}</span>
        {r.critical && <span className="chip bg-rose text-xs">Có lỗi nghiêm trọng</span>}
        {r.flag_status !== "none" && <span className="chip bg-warm text-xs">{FLAG_STATUS[r.flag_status]}</span>}
        <AiBadge />
        <span className="text-xs text-muted">
          <LocalTime iso={r.created_at} /> · {r.commit_shas.map((s) => s.slice(0, 7)).join(", ")}
        </span>
      </div>
      <p className="mt-1.5 whitespace-pre-wrap break-words text-[15px]">{r.summary}</p>
      <p className="mt-1 text-xs text-muted">
        Đã xem {r.coverage.reviewed_files} file
        {r.coverage.omitted_files > 0 && `, bỏ qua ${r.coverage.omitted_files} file`}
        {r.coverage.truncated && " · dữ liệu gửi AI đã bị cắt bớt (diff, README hoặc cây thư mục)"} · chỉ đánh giá phần diff được gửi, không kết luận toàn repo.
      </p>
      <button type="button" className="mt-2 text-sm font-bold underline" aria-expanded={open} onClick={() => setOpen(!open)}>
        {open ? "Ẩn chi tiết" : `Chi tiết (${r.issues.length} vấn đề)`}
      </button>
      {open && (
        <div className="mt-3 space-y-3">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-4">
            {(Object.keys(SCORE_LABEL) as (keyof S["Scores"])[]).map((k) => (
              <div key={k} className="flex justify-between gap-2 border-b border-dashed border-ink/40">
                <dt>{SCORE_LABEL[k]}</dt>
                <dd className="font-mono font-bold">{fmt(r.scores[k])}</dd>
              </div>
            ))}
          </dl>
          {r.issues.length > 0 && (
            <ul className="space-y-2">
              {r.issues.map((i, n) => (
                <li key={n} className="rounded-xl border-2 border-ink px-3 py-2 text-sm">
                  <p className="flex flex-wrap items-center gap-2">
                    <span className={`chip text-xs ${SEVERITY[i.severity][1]}`}>{SEVERITY[i.severity][0]}</span>
                    <span className="break-all font-mono text-xs font-semibold">
                      {i.file}
                      {i.line != null ? `:${i.line}` : " (không xác định được dòng)"}
                    </span>
                    <span className="text-xs text-muted">{i.category}</span>
                  </p>
                  <p className="mt-1 whitespace-pre-wrap break-words">{i.message}</p>
                  {i.suggestion && <p className="mt-1 whitespace-pre-wrap break-words text-muted">Gợi ý: {i.suggestion}</p>}
                </li>
              ))}
            </ul>
          )}
          <p className="text-xs text-muted">
            Model {r.model} · prompt {r.prompt_version}
          </p>
          {mode === "judge" && <FlagForm reviewId={r.id} />}
          {canReadFlags && r.flagged && (
            <div>
              <button type="button" className="text-sm font-bold underline" aria-expanded={showFlags} onClick={() => setShowFlags(!showFlags)}>
                {showFlags ? "Ẩn phản hồi giám khảo" : "Xem phản hồi giám khảo"}
              </button>
              {showFlags && (
                <div className="mt-2">
                  <FlagsPanel reviewId={r.id} canResolve={mode === "organizer"} />
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </li>
  );
}

/** Danh sách review; `commitSha` có thì chỉ lấy review gộp commit đó. `canReadFlags` cho BTC/admin. */
export function AiReviewList({ teamId, roundId, commitSha, mode, canReadFlags = false }: { teamId: string; roundId?: string; commitSha?: string; mode: AiMode; canReadFlags?: boolean }) {
  const [offset, setOffset] = useState(0);
  const [verdict, setVerdict] = useState("");
  const list = useQuery({
    queryKey: ["ai-reviews", teamId, roundId ?? "", commitSha ?? "", verdict, offset],
    queryFn: async () =>
      (
        await api.get<Page<Review>>(`/teams/${teamId}/ai-reviews`, {
          params: {
            round_id: roundId,
            commit_sha: commitSha,
            verdict: verdict || undefined,
            limit: LIMIT,
            offset,
          },
        })
      ).data,
    placeholderData: keepPreviousData,
  });
  useForgetTeamOnForbidden(teamId, list.error);
  if (list.isError) return errorCode(list.error) === "FORBIDDEN" ? null : <FormError>{errorMessage(list.error)}</FormError>;
  if (!list.data) return <p role="status">Đang tải…</p>;
  return (
    <div className="space-y-3">
      {!commitSha && (
        <label className="flex items-center gap-2 text-sm font-bold">
          Lọc
          <select
            value={verdict}
            onChange={(e) => {
              setVerdict(e.target.value);
              setOffset(0);
            }}
            className="min-h-9 rounded-xl border-2 border-ink bg-paper px-2 font-normal"
          >
            <option value="">Mọi phân loại</option>
            {(Object.keys(VERDICT) as Review["verdict"][]).map((v) => (
              <option key={v} value={v}>
                {VERDICT[v][0]}
              </option>
            ))}
          </select>
        </label>
      )}
      {list.data.total === 0 && <p className="font-serif italic text-muted">Chưa có review AI{commitSha ? " cho commit này" : ""}.</p>}
      <ol className="space-y-2.5">
        {list.data.items.map((r) => (
          <ReviewCard key={r.id} r={r} mode={mode} canReadFlags={canReadFlags} />
        ))}
      </ol>
      {list.data.total > LIMIT && <Pager offset={offset} limit={LIMIT} total={list.data.total} onChange={setOffset} />}
    </div>
  );
}

/** Khối "Chất lượng code" của một đội: tổng hợp + danh sách review. */
export function AiQuality({ teamId, roundId, mode, canReadFlags }: { teamId: string; roundId?: string; mode: AiMode; canReadFlags?: boolean }) {
  const queryClient = useQueryClient();
  const isAdmin = useAuth((s) => s.user?.is_admin);
  // BTC/admin không vào được room đội; BTC đã tự poll summary khi có job đang chạy
  useRealtime(mode === "organizer" || isAdmin ? null : `team:${teamId}`, {
    "ai_review:new": () => ["ai-reviews", "ai-summary"].forEach((k) => queryClient.invalidateQueries({ queryKey: [k, teamId] })),
  });
  return (
    <div className="space-y-5">
      <p className="flex flex-wrap items-center gap-2 text-sm text-muted">
        <AiBadge /> Điểm AI chỉ để tham khảo, không cộng vào điểm rubric. AI chỉ thấy phần diff được gửi, có thể sai.
      </p>
      <SummaryPanel teamId={teamId} roundId={roundId} mode={mode} />
      <AiReviewList teamId={teamId} roundId={roundId} mode={mode} canReadFlags={canReadFlags} />
    </div>
  );
}

const VISIBILITY: Record<Event["ai_visible_to_participants"], string> = {
  never: "Không bao giờ",
  during: "Trong lúc thi",
  after_round: "Sau khi vòng công bố kết quả",
};

/** Cấu hình AI mặc định của cuộc thi (áp cho vòng chưa bắt đầu) + snapshot thật từng vòng. */
export function AiConfigPanel({ event, onSaved }: { event: Event; onSaved: (e: Event) => void }) {
  const rounds = useRounds(event.id);
  const save = useMutation({
    mutationFn: async (body: Partial<Event>) => (await api.patch<Event>(`/events/${event.id}`, body)).data,
    onSuccess: onSaved,
  });
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const next = {
      ai_review_enabled: fd.get("ai_review_enabled") === "on",
      ai_visible_to_participants: String(fd.get("ai_visible_to_participants")) as Event["ai_visible_to_participants"],
      ai_pass_threshold: Number(fd.get("ai_pass_threshold")),
      ai_good_threshold: Number(fd.get("ai_good_threshold")),
      ai_token_budget_per_team_round: Number(fd.get("ai_token_budget_per_team_round")),
    };
    // Chỉ gửi trường đã đổi
    const body = Object.fromEntries(Object.entries(next).filter(([k, v]) => event[k as keyof typeof next] !== v));
    if (Object.keys(body).length) save.mutate(body);
  }
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-black">AI đánh giá code</h2>
        <p className="mt-1 text-sm text-muted">
          Cấu hình này là mặc định cho các vòng chưa bắt đầu; vòng đã bắt đầu giữ nguyên cấu hình đã chốt. Khi bật, diff code của đội (đã lọc file sinh tự động và credential thông dụng, không bảo đảm lọc hết) được gửi tới nhà cung cấp AI.
          Điểm AI chỉ tham khảo, không cộng vào rubric.
        </p>
      </div>
      <form key={[event.ai_review_enabled, event.ai_visible_to_participants, event.ai_pass_threshold, event.ai_good_threshold, event.ai_token_budget_per_team_round].join("|")} onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
        <label className="flex items-center gap-2 font-bold sm:col-span-2">
          <input type="checkbox" name="ai_review_enabled" defaultChecked={event.ai_review_enabled} className="size-5" />
          Bật AI review (tắt chỉ dừng nhận job mới, không xóa review đã có)
        </label>
        <label className="block">
          <span className="text-sm font-bold">Thí sinh xem báo cáo AI</span>
          <select name="ai_visible_to_participants" defaultValue={event.ai_visible_to_participants} className={`${INPUT} min-h-11`}>
            {(Object.keys(VISIBILITY) as Event["ai_visible_to_participants"][]).map((v) => (
              <option key={v} value={v}>
                {VISIBILITY[v]}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="text-sm font-bold">Ngân sách token/đội/vòng</span>
          <input type="number" name="ai_token_budget_per_team_round" required min={1} max={100000000} step={1} defaultValue={event.ai_token_budget_per_team_round} className={`${INPUT} min-h-11`} />
        </label>
        <label className="block">
          <span className="text-sm font-bold">Ngưỡng “Đạt” (từ)</span>
          <input type="number" name="ai_pass_threshold" required min={0} max={10} step={0.01} defaultValue={event.ai_pass_threshold} className={`${INPUT} min-h-11`} />
        </label>
        <label className="block">
          <span className="text-sm font-bold">Ngưỡng “Tốt” (từ)</span>
          <input type="number" name="ai_good_threshold" required min={0} max={10} step={0.01} defaultValue={event.ai_good_threshold} className={`${INPUT} min-h-11`} />
          <span className="mt-1 block text-xs text-muted">Cần 0 ≤ Đạt &lt; Tốt ≤ 10.</span>
        </label>
        <div className="sm:col-span-2">
          {save.isError && <FormError>{errorMessage(save.error)}</FormError>}
          {save.isSuccess && (
            <p role="status" className="mb-2 text-sm font-semibold">
              Đã lưu.
            </p>
          )}
          <button type="submit" className="btn bg-orange font-extrabold" disabled={save.isPending}>
            Lưu cấu hình AI
          </button>
        </div>
      </form>
      <div>
        <h3 className="mb-2 font-black">Cấu hình đã chốt theo vòng</h3>
        {rounds.isError && <FormError>{errorMessage(rounds.error)}</FormError>}
        {rounds.data?.length === 0 && <p className="text-sm text-muted">Chưa có vòng nào.</p>}
        {!!rounds.data?.length && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] border-collapse text-sm">
              <thead>
                <tr className="border-b-2 border-ink text-left">
                  <th className="px-2 py-2">Vòng</th>
                  <th className="px-2 py-2">AI</th>
                  <th className="px-2 py-2">Thí sinh xem</th>
                  <th className="px-2 py-2">Ngưỡng Đạt/Tốt</th>
                  <th className="px-2 py-2">Ngân sách</th>
                  <th className="px-2 py-2">Model · prompt</th>
                </tr>
              </thead>
              <tbody>
                {rounds.data.map((r) => (
                  <tr key={r.id} className="border-b border-dashed border-ink">
                    <td className="px-2 py-2 font-bold">{r.name}</td>
                    <td className="px-2 py-2">{r.ai_config.ai_review_enabled ? "Bật" : "Tắt"}</td>
                    <td className="px-2 py-2">{VISIBILITY[r.ai_config.ai_visible_to_participants]}</td>
                    <td className="px-2 py-2">
                      {fmt(r.ai_config.ai_pass_threshold)} / {fmt(r.ai_config.ai_good_threshold)}
                    </td>
                    <td className="px-2 py-2">{r.ai_config.ai_token_budget_per_team_round.toLocaleString("vi-VN")}</td>
                    <td className="px-2 py-2 font-mono text-xs">
                      {r.ai_config.model} · {r.ai_config.prompt_version}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
