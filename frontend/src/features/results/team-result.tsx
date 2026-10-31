"use client";

import { useQuery } from "@tanstack/react-query";
import { FormError } from "@/features/auth/auth-card";
import type { TeamResult } from "@/features/events/types";
import { WithRound } from "@/features/submissions/submissions";
import { api, errorCode, errorMessage } from "@/lib/api";

// Trạng thái bình thường của vòng chưa có kết quả, không phải lỗi
const WAITING: Record<string, string> = {
  NOT_PUBLISHED: "Kết quả vòng này chưa được công bố.",
  FORBIDDEN: "Kết quả chỉ hiện khi BTC đã khóa điểm vòng này.",
  RESULT_NOT_FOUND: "Đội không có bài được chấm ở vòng này.",
};

/** Điểm từng tiêu chí và nhận xét ẩn danh của đội theo vòng; quyền xem do server quyết định. */
export function TeamResults({ eventId, teamId }: { eventId: string; teamId: string }) {
  return <WithRound eventId={eventId}>{(r) => <RoundResult key={r.id} teamId={teamId} roundId={r.id} />}</WithRound>;
}

function RoundResult({ teamId, roundId }: { teamId: string; roundId: string }) {
  const result = useQuery({
    queryKey: ["team-result", teamId, roundId],
    queryFn: async () => (await api.get<TeamResult>(`/teams/${teamId}/rounds/${roundId}/result`)).data,
    retry: false,
  });
  if (result.isError) {
    const waiting = WAITING[errorCode(result.error) ?? ""];
    return waiting ? <p className="font-serif italic text-muted">{waiting}</p> : <FormError>{errorMessage(result.error)}</FormError>;
  }
  if (!result.data) return <p role="status">Đang tải…</p>;
  const r = result.data;
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end gap-6">
        <div>
          <p className="text-sm font-bold">Hạng</p>
          <p className="font-mono text-[44px] font-extrabold leading-none">#{r.rank}</p>
        </div>
        <div>
          <p className="text-sm font-bold">Tổng</p>
          <p className="font-mono text-[44px] font-extrabold leading-none">
            {Number(r.total).toFixed(2)}
            <span className="text-xl text-muted">/100</span>
          </p>
        </div>
        <span className="chip bg-paper">Công bố lần {r.publication_revision}</span>
      </div>
      <ul aria-label="Điểm trung bình từng tiêu chí" className="grid gap-2.5 sm:grid-cols-2">
        {r.criteria.map((c) => (
          <li key={c.name} className="flex items-baseline justify-between gap-3 rounded-xl border-2 border-ink px-3.5 py-2.5">
            <span className="font-bold">{c.name}</span>
            <span className="font-mono font-extrabold">{Number(c.avg).toFixed(2)}</span>
          </li>
        ))}
      </ul>
      <section>
        <h3 className="font-black">Nhận xét của giám khảo</h3>
        {r.comments.length === 0 ? (
          <p className="mt-1 text-sm text-muted">Không có nhận xét.</p>
        ) : (
          <ul className="mt-2 space-y-2">
            {r.comments.map((c, i) => (
              <li key={i} className="whitespace-pre-wrap rounded-r-xl border-l-4 border-ink bg-warm px-3 py-2.5 text-sm">
                {c}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
