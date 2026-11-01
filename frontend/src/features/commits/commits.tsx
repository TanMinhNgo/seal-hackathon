"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useState } from "react";
import { LocalTime } from "@/components/ui/local-time";
import { Pager } from "@/components/ui/pager";
import { FormError } from "@/features/auth/auth-card";
import type { Page } from "@/features/events/types";
import { api, errorCode, errorMessage } from "@/lib/api";
import type { components } from "@/lib/api-types";

type S = components["schemas"];
export type Commit = S["CommitOutput"];
type Stats = S["CommitStats"];
type Overview = S["CommitOverview"];
type DiffPage = S["DiffPage"];

const LIMIT = 20;

// sync_error chỉ là mã an toàn từ BE; mỗi mã một câu tiếng Việt, không suy thành "không hoạt động"
const SYNC_ERROR: Record<string, string> = {
  GITHUB_NOT_CONFIGURED: "Máy chủ chưa cấu hình kết nối GitHub.",
  REPO_NOT_ACCESSIBLE: "Không đọc được repo (đã chuyển private, bị xóa hoặc đổi tên).",
  GITHUB_UNAVAILABLE: "GitHub không phản hồi, hệ thống sẽ thử lại.",
  GITHUB_INCOMPLETE_HISTORY: "Chưa lấy đủ lịch sử commit, hệ thống sẽ thử lại.",
  GITHUB_RATE_LIMITED: "Đã chạm giới hạn gọi GitHub, tạm dừng tới khi được phép.",
  SYNC_COORDINATION_UNAVAILABLE: "Bộ điều phối đồng bộ tạm thời không truy cập được.",
  SYNC_QUEUE_UNAVAILABLE: "Hàng đợi đồng bộ không nhận việc, có thể job đã vào hàng.",
  SYNC_WORKER_TIMEOUT: "Lượt đồng bộ trước bị quá giờ.",
};
const syncError = (code: string | null | undefined) => (code ? (SYNC_ERROR[code] ?? code) : "Đồng bộ lỗi.");
const SYNC_STATUS: Record<Stats["sync_status"], [string, string]> = { ok: ["Đồng bộ ổn", "bg-mint"], error: ["Đồng bộ lỗi", "bg-rose"], pending: ["Chưa đồng bộ", "bg-sun"] };

/**
 * Bị thu hồi phân công (403) thì bỏ mọi dữ liệu đã cache của đội và tải lại danh sách đội được giao.
 * Chỉ xóa query không còn hiển thị: query đang lỗi tự ẩn dữ liệu, xóa nó sẽ làm gọi lại vòng lặp 403.
 */
export function useForgetTeamOnForbidden(teamId: string, error: unknown) {
  const queryClient = useQueryClient();
  const forbidden = errorCode(error) === "FORBIDDEN";
  useEffect(() => {
    if (!forbidden) return;
    queryClient.removeQueries({ type: "inactive", predicate: (q) => q.queryKey[1] === teamId });
    for (const key of ["mentoring", "my-assignments"]) void queryClient.invalidateQueries({ queryKey: [key] });
  }, [forbidden, teamId, queryClient]);
}

export function useCommitStats(teamId: string) {
  return useQuery({
    queryKey: ["commit-stats", teamId],
    queryFn: async () => (await api.get<Stats>(`/teams/${teamId}/commit-stats`)).data,
    // Đang chạy thì đọc lại để thấy kết quả lượt đồng bộ
    refetchInterval: (q) => (q.state.data?.running ? 5000 : false),
  });
}

function useCommits(teamId: string, offset: number) {
  return useQuery({
    queryKey: ["commits", teamId, offset],
    queryFn: async () => (await api.get<Page<Commit>>(`/teams/${teamId}/commits`, { params: { limit: LIMIT, offset } })).data,
    placeholderData: keepPreviousData,
  });
}

/** Nút đồng bộ lại của BTC; sau mọi phản hồi đọc lại stats vì 503 vẫn có thể đã vào hàng đợi. */
function SyncButton({ teamId, running }: { teamId: string; running: boolean }) {
  const queryClient = useQueryClient();
  const sync = useMutation({
    mutationFn: () => api.post(`/teams/${teamId}/sync`),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["commit-stats", teamId] }),
  });
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <button type="button" className="btn min-h-9 bg-orange text-sm font-extrabold" disabled={sync.isPending || running} onClick={() => sync.mutate()}>
        {running ? "Đang đồng bộ…" : "Đồng bộ lại"}
      </button>
      {sync.isSuccess && !running && <span role="status" className="text-xs font-semibold">Đã xếp vào hàng đợi.</span>}
      {sync.isError && <span role="alert" className="text-xs font-semibold text-minus">{errorMessage(sync.error)}</span>}
    </span>
  );
}

/** Thẻ thống kê đồng bộ; `canSync` chỉ cho BTC (admin chỉ xem). */
export function CommitStatsCard({ teamId, canSync }: { teamId: string; canSync?: boolean }) {
  const stats = useCommitStats(teamId);
  useForgetTeamOnForbidden(teamId, stats.error);
  if (stats.isError) return <FormError>{errorMessage(stats.error)}</FormError>;
  if (!stats.data) return <p role="status">Đang tải…</p>;
  const s = stats.data;
  const cell = "rounded-2xl border-2 border-ink bg-paper px-4 py-3";
  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className={cell}>
          <p className="text-xs font-bold text-muted">Commit trong giờ thi</p>
          <p className="text-2xl font-black">{s.total}</p>
        </div>
        <div className={cell}>
          <p className="text-xs font-bold text-muted">Commit cuối (hệ thống thấy)</p>
          <p className="font-bold">{s.last_commit_at ? <LocalTime iso={s.last_commit_at} /> : "Chưa có"}</p>
        </div>
        <div className={cell}>
          <p className="text-xs font-bold text-muted">Đồng bộ thành công cuối</p>
          <p className="font-bold">{s.last_synced_at ? <LocalTime iso={s.last_synced_at} /> : "Chưa có"}</p>
        </div>
        <div className={cell}>
          <p className="text-xs font-bold text-muted">Trạng thái</p>
          <p className="mt-1 flex flex-wrap gap-1.5">
            <span className={`chip text-xs ${SYNC_STATUS[s.sync_status][1]}`}>{SYNC_STATUS[s.sync_status][0]}</span>
            {s.running && <span className="chip bg-sky text-xs">Đang chạy</span>}
          </p>
        </div>
      </div>
      {s.sync_status === "error" && <p className="rounded-xl border-2 border-ink bg-rose px-3.5 py-2.5 text-sm font-semibold">{syncError(s.sync_error)}</p>}
      {s.truncated && <p className="text-sm font-semibold">Lịch sử quá dài: chỉ giữ phần đã thấy, chưa xác nhận đủ commit.</p>}
      <p className="flex flex-wrap items-center gap-x-3 gap-y-2 text-xs text-muted">
        {s.branch && (
          <span>
            Branch theo dõi: <b className="font-mono">{s.branch}</b>
          </span>
        )}
        {s.last_attempt_at && (
          <span>
            Lần thử cuối <LocalTime iso={s.last_attempt_at} />
          </span>
        )}
        {canSync && <SyncButton teamId={teamId} running={s.running} />}
      </p>
    </div>
  );
}

function CommitBadges({ c }: { c: Commit }) {
  return (
    <>
      {c.removed && <span className="chip bg-rose text-xs">Đã bị xóa khỏi branch</span>}
      {c.baseline && <span className="chip bg-warm text-xs">Có trước giờ thi</span>}
      {!c.baseline && !c.in_event_window && <span className="chip bg-sun text-xs">Ngoài giờ thi</span>}
    </>
  );
}

/**
 * Timeline commit theo thời điểm hệ thống thấy (`first_seen_at`). `commitHref` có thì mở trang commit riêng
 * (admin), không thì xem diff ngay trong danh sách.
 */
export function CommitTimeline({ teamId, commitHref }: { teamId: string; commitHref?: (sha: string) => string }) {
  const [offset, setOffset] = useState(0);
  const [open, setOpen] = useState("");
  const list = useCommits(teamId, offset);
  useForgetTeamOnForbidden(teamId, list.error);
  // Lỗi (ví dụ vừa bị thu hồi phân công → 403) thì không hiện dữ liệu cũ còn trong cache
  if (list.isError) return <FormError>{errorMessage(list.error)}</FormError>;
  if (!list.data) return <p role="status">Đang tải…</p>;
  return (
    <div className="space-y-3">
      <p className="text-xs text-muted">Thời gian là lúc hệ thống thấy commit (sai số theo chu kỳ đồng bộ), không chứng minh giờ viết code hay tác giả. Commit có trước lượt đồng bộ đầu tiên được coi là có trước giờ thi.</p>
      {list.data.total === 0 && <p className="font-serif italic text-muted">Chưa có commit nào được đồng bộ.</p>}
      <ol className="space-y-2.5">
        {list.data.items.map((c) => (
          <li key={c.sha} className={`rounded-[18px] border-2 border-ink px-4 py-3 ${c.removed ? "bg-warm" : "bg-paper"}`}>
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-xs font-bold">{c.sha.slice(0, 7)}</span>
              <span className="text-xs text-muted">
                <LocalTime iso={c.first_seen_at} />
              </span>
              <span className="text-sm font-semibold">{c.author}</span>
              <span className="font-mono text-xs">
                <span className="text-plus">+{c.additions}</span> <span className="text-minus">−{c.deletions}</span>
              </span>
              <CommitBadges c={c} />
            </div>
            <p className={`mt-1.5 whitespace-pre-wrap break-words text-[15px] ${c.removed ? "line-through" : ""}`}>{c.message.split("\n")[0]}</p>
            <div className="mt-2 flex flex-wrap gap-2 text-sm">
              {commitHref ? (
                <Link href={commitHref(c.sha)} className="font-bold underline">
                  Chi tiết
                </Link>
              ) : (
                <button type="button" className="font-bold underline" aria-expanded={open === c.sha} onClick={() => setOpen(open === c.sha ? "" : c.sha)}>
                  {open === c.sha ? "Ẩn thay đổi" : "Xem thay đổi"}
                </button>
              )}
              <a href={c.url} target="_blank" rel="noreferrer" className="underline">
                GitHub
              </a>
              <button type="button" className="underline" onClick={() => navigator.clipboard.writeText(c.sha)}>
                Sao chép SHA
              </button>
            </div>
            {open === c.sha && (
              <div className="mt-3">
                <CommitDiff teamId={teamId} sha={c.sha} />
              </div>
            )}
          </li>
        ))}
      </ol>
      {list.data.total > LIMIT && <Pager offset={offset} limit={LIMIT} total={list.data.total} onChange={setOffset} />}
    </div>
  );
}

function patchLineClass(line: string) {
  if (line.startsWith("+")) return "bg-mint/60";
  if (line.startsWith("-")) return "bg-rose/60";
  if (line.startsWith("@@")) return "text-muted";
  return "";
}

/** File và patch thật đã lưu; render dạng text (React tự escape), không chạy gì từ repo. */
export function CommitDiff({ teamId, sha }: { teamId: string; sha: string }) {
  const [offset, setOffset] = useState(0);
  const diff = useQuery({
    queryKey: ["commit-diff", teamId, sha, offset],
    queryFn: async () => (await api.get<DiffPage>(`/teams/${teamId}/commits/${sha}/diff`, { params: { limit: LIMIT, offset } })).data,
    placeholderData: keepPreviousData,
  });
  if (diff.isError) return <FormError>{errorMessage(diff.error)}</FormError>;
  if (!diff.data) return <p role="status">Đang tải thay đổi…</p>;
  const d = diff.data;
  return (
    <div className="space-y-2.5">
      {d.truncated && <p className="rounded-xl border-2 border-ink bg-sun px-3 py-2 text-sm font-semibold">Commit quá lớn: chỉ lưu {d.total} file / tối đa 1 MiB patch, không phải toàn bộ thay đổi.</p>}
      {d.total === 0 && <p className="text-sm text-muted">Không có file thay đổi đã lưu.</p>}
      {d.items.map((f) => (
        <details key={f.path} className="rounded-xl border-2 border-ink bg-paper">
          <summary className="flex cursor-pointer flex-wrap items-center gap-2 px-3 py-2 text-sm">
            <span className="break-all font-mono font-semibold">
              {f.previous_path && f.previous_path !== f.path ? `${f.previous_path} → ` : ""}
              {f.path}
            </span>
            <span className="text-xs text-muted">{f.status}</span>
            <span className="font-mono text-xs">
              <span className="text-plus">+{f.additions}</span> <span className="text-minus">−{f.deletions}</span>
            </span>
            {f.binary === true && <span className="chip bg-warm text-xs">Binary</span>}
            {f.binary === null && <span className="chip bg-warm text-xs">Không rõ binary</span>}
            {f.truncated && <span className="chip bg-sun text-xs">Patch bị cắt</span>}
          </summary>
          {f.patch ? (
            <pre className="max-h-[480px] overflow-auto border-t-2 border-ink text-xs leading-5">
              {f.patch.split("\n").map((line, i) => (
                <code key={i} className={`block whitespace-pre px-3 ${patchLineClass(line)}`}>
                  {line || " "}
                </code>
              ))}
            </pre>
          ) : (
            <p className="border-t-2 border-ink px-3 py-2 text-sm text-muted">{f.binary ? "File binary, không có patch." : "Không có patch đã lưu cho file này."}</p>
          )}
        </details>
      ))}
      {d.total > LIMIT && <Pager offset={offset} limit={LIMIT} total={d.total} onChange={setOffset} />}
    </div>
  );
}

/** Tab "Tiến độ" của một đội: thống kê + timeline. */
export function TeamProgress({ teamId, canSync, commitHref }: { teamId: string; canSync?: boolean; commitHref?: (sha: string) => string }) {
  return (
    <div className="space-y-6">
      <CommitStatsCard teamId={teamId} canSync={canSync} />
      <CommitTimeline teamId={teamId} commitHref={commitHref} />
    </div>
  );
}

/**
 * Ô gắn commit vào góp ý/câu hỏi: gợi ý 20 commit mới nhất, commit cũ hơn thì dán đủ SHA
 * (copy từ timeline); BE kiểm tra SHA thuộc đúng đội. Rỗng = không gắn.
 */
export function CommitSelect({ teamId }: { teamId: string }) {
  const list = useCommits(teamId, 0);
  if (!list.data?.total) return null;
  const id = `commits-${teamId}`;
  return (
    <label className="block max-w-md text-xs font-bold">
      Gắn vào commit (không bắt buộc): chọn gợi ý hoặc dán đủ 40 ký tự SHA
      <input
        name="commit_sha"
        list={id}
        autoComplete="off"
        spellCheck={false}
        pattern="[0-9a-f]{40}"
        title="SHA đủ 40 ký tự thường 0-9, a-f"
        className="mt-1.5 block min-h-11 w-full rounded-xl border-2 border-ink bg-paper px-3 font-mono text-[13px] font-normal"
      />
      <datalist id={id}>
        {list.data.items
          .filter((c) => !c.removed)
          .map((c) => (
            <option key={c.sha} value={c.sha} label={c.message.split("\n")[0].slice(0, 60)} />
          ))}
      </datalist>
    </label>
  );
}

/** Bảng tổng quan BTC: sắp toàn bộ đội theo commit cuối, tô đội không hoạt động và đội lỗi đồng bộ. */
export function CommitOverviewPanel({ eventId }: { eventId: string }) {
  const [offset, setOffset] = useState(0);
  const [picked, setPicked] = useState("");
  const list = useQuery({
    queryKey: ["commit-overview", eventId],
    // BE phân trang theo thứ tự tạo đội nên tải hết rồi sắp ở FE.
    // shortcut: tải mọi trang 100 đội; cần BE hỗ trợ sắp xếp nếu một cuộc thi có hàng nghìn đội
    queryFn: async () => {
      const items: Overview[] = [];
      for (let total = Infinity; items.length < total; ) {
        const { data } = await api.get<Page<Overview>>(`/events/${eventId}/commit-overview`, { params: { limit: 100, offset: items.length } });
        items.push(...data.items);
        total = data.items.length ? data.total : items.length;
      }
      // Đội chưa có commit xếp cuối
      return items.sort((a, b) => (b.last_commit_at ?? "").localeCompare(a.last_commit_at ?? ""));
    },
    refetchInterval: 60_000,
  });
  if (list.isError) return <FormError>{errorMessage(list.error)}</FormError>;
  if (!list.data) return <p role="status">Đang tải…</p>;
  const all = list.data;
  const rows = all.slice(offset, offset + LIMIT);
  const team = all.find((r) => r.team.id === picked);
  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-black">Tiến độ commit</h2>
        <p className="mt-1 text-sm text-muted">Sắp theo commit cuối (mới nhất trước), tự cập nhật mỗi phút. Đỏ: đồng bộ lỗi (không tính là không hoạt động). Vàng: không có commit mới quá ngưỡng cảnh báo.</p>
      </div>
      {all.length === 0 && <p className="font-serif italic text-muted">Chưa có đội nào.</p>}
      {rows.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] border-collapse text-sm">
            <thead>
              <tr className="border-b-2 border-ink text-left">
                <th className="px-2 py-2">Đội</th>
                <th className="px-2 py-2">Commit</th>
                <th className="px-2 py-2">Commit cuối</th>
                <th className="px-2 py-2">Đồng bộ cuối</th>
                <th className="px-2 py-2">Trạng thái</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.team.id} className={`border-b border-dashed border-ink ${r.sync_status === "error" ? "bg-rose/50" : r.inactive ? "bg-sun/50" : ""}`}>
                  <td className="px-2 py-2">
                    <button type="button" className="text-left font-bold underline" aria-pressed={picked === r.team.id} onClick={() => setPicked(picked === r.team.id ? "" : r.team.id)}>
                      {r.team.name}
                    </button>
                  </td>
                  <td className="px-2 py-2 font-mono">{r.total}</td>
                  <td className="px-2 py-2">{r.last_commit_at ? <LocalTime iso={r.last_commit_at} /> : "Chưa có"}</td>
                  <td className="px-2 py-2">{r.last_synced_at ? <LocalTime iso={r.last_synced_at} /> : "Chưa có"}</td>
                  <td className="px-2 py-2">
                    <span className="flex flex-wrap gap-1">
                      {r.sync_status === "error" ? <span className="chip bg-rose text-xs" title={syncError(r.sync_error)}>Lỗi đồng bộ</span> : r.sync_status === "pending" && <span className="chip bg-sun text-xs">Chưa đồng bộ</span>}
                      {r.inactive && <span className="chip bg-sun text-xs">Không hoạt động</span>}
                      {r.running && <span className="chip bg-sky text-xs">Đang chạy</span>}
                      {r.sync_status === "ok" && !r.inactive && !r.running && <span className="chip bg-mint text-xs">Ổn</span>}
                    </span>
                    {r.sync_status === "error" && <span className="mt-1 block text-xs">{syncError(r.sync_error)}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {all.length > LIMIT && <Pager offset={offset} limit={LIMIT} total={all.length} onChange={setOffset} />}
      {team && (
        <section aria-label={`Tiến độ ${team.team.name}`} className="rounded-[22px] border-2 border-ink p-5">
          <h3 className="mb-4 text-lg font-black">{team.team.name}</h3>
          <TeamProgress key={team.team.id} teamId={team.team.id} canSync />
        </section>
      )}
    </div>
  );
}
