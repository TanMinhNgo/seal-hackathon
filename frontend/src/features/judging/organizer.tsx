"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { buttonClass } from "@/components/ui/button";
import { serverNow, useSecondsLeft } from "@/components/ui/countdown";
import { LocalTime } from "@/components/ui/local-time";
import { FormError } from "@/features/auth/auth-card";
import { Tabs, useEvent, useTracks } from "@/features/events/manage";
import type { Assignment, AssignmentBatch, Conflict, JudgingProgress, LeaderboardData, MentorAssignment, Page, Progress, RoleItem, Round, RoundTeam, Rubric, Team } from "@/features/events/types";
import { FORMULA_NOTE, LeaderboardTable } from "@/features/results/leaderboard-table";
import { useRounds, WithRound } from "@/features/submissions/submissions";
import { api, codeMessage, errorMessage } from "@/lib/api";

// shortcut: các danh sách dưới đây lấy 100 mục đầu, đủ cho một cuộc thi hackathon; thêm phân trang nếu vượt
const ALL = { params: { limit: 100 } };
const INPUT = "block min-h-11 w-full rounded-xl border-2 border-ink bg-paper px-3 text-[15px]";
const ASSIGNMENT_STATUS: Record<Assignment["status"], [string, string]> = {
  pending: ["Chưa chấm", "bg-paper"],
  draft: ["Đang chấm", "bg-sun"],
  submitted: ["Đã xác nhận", "bg-mint"],
  cancelled: ["Đã hủy", "bg-warm"],
};

/** Hỏi lý do; trả null nếu người dùng hủy hoặc để trống (BE bắt buộc lý do). */
function askReason(question: string) {
  const r = window.prompt(question)?.trim();
  return r ? r : null;
}

function useRoleUsers(eventId: string, role: "judge" | "mentor") {
  // Cùng key với RolesPanel để thêm/gỡ vai trò cập nhật luôn ở đây
  const roles = useQuery({ queryKey: ["roles", eventId], queryFn: async () => (await api.get<Page<RoleItem>>(`/events/${eventId}/roles`, ALL)).data.items });
  return roles.data?.filter((r) => r.role === role).map((r) => r.user);
}

function useRubric(eventId: string, roundId: string) {
  // Không tự tải lại: form rubric dựng theo lần tải, tải lại giữa chừng sẽ xóa phần đang sửa
  return useQuery({ queryKey: ["rubric", roundId], queryFn: async () => (await api.get<Rubric>(`/events/${eventId}/rounds/${roundId}/rubric`)).data, staleTime: Infinity });
}

function useEligible(eventId: string, roundId: string) {
  return useQuery({ queryKey: ["eligible", roundId], queryFn: async () => (await api.get<Page<RoundTeam>>(`/events/${eventId}/rounds/${roundId}/eligible-teams`, ALL)).data.items });
}

type SubTab = "rubric" | "eligible" | "assign" | "progress";

/** Tab "Chấm điểm" của BTC: mọi việc theo từng vòng. */
export function JudgingPanel({ eventId }: { eventId: string }) {
  const [tab, setTab] = useState<SubTab>("rubric");
  return (
    <WithRound eventId={eventId}>
      {(round) => (
        <div className="space-y-5">
          <Tabs<SubTab>
            label="Chấm điểm theo vòng"
            value={tab}
            onChange={setTab}
            tabs={[
              ["rubric", "Rubric"],
              ["eligible", "Đội vào vòng"],
              ["assign", "Phân công giám khảo"],
              ["progress", "Tiến độ & công bố"],
            ]}
          />
          {tab === "rubric" && <RubricEditor key={round.id} eventId={eventId} round={round} />}
          {tab === "eligible" && <EligiblePanel key={round.id} eventId={eventId} round={round} />}
          {tab === "assign" && <AssignmentsPanel key={round.id} eventId={eventId} round={round} />}
          {tab === "progress" && <ProgressPanel key={round.id} eventId={eventId} round={round} />}
        </div>
      )}
    </WithRound>
  );
}

// ---------- Rubric ----------

type Row = { name: string; description: string; weight: string; max_score: string };

function RubricEditor({ eventId, round }: { eventId: string; round: Round }) {
  const rubric = useRubric(eventId, round.id);
  if (rubric.isError) return <FormError>{errorMessage(rubric.error)}</FormError>;
  if (!rubric.data) return <p role="status">Đang tải…</p>;
  return <RubricForm key={rubric.dataUpdatedAt} eventId={eventId} round={round} rubric={rubric.data} />;
}

function RubricForm({ eventId, round, rubric }: { eventId: string; round: Round; rubric: Rubric }) {
  const queryClient = useQueryClient();
  const [rows, setRows] = useState<Row[]>(() =>
    [...rubric.criteria].sort((a, b) => a.order - b.order).map((c) => ({ name: c.name, description: c.description ?? "", weight: String(Number(c.weight)), max_score: String(Number(c.max_score)) })),
  );
  const [saved, setSaved] = useState(false);
  const save = useMutation({
    mutationFn: async () =>
      (
        await api.put<Rubric>(`/events/${eventId}/rounds/${round.id}/rubric`, {
          criteria: rows.map((r, i) => ({ name: r.name.trim(), description: r.description.trim() || null, weight: r.weight, max_score: r.max_score, order: i + 1 })),
        })
      ).data,
    onSuccess: (r) => {
      setSaved(true);
      queryClient.setQueryData(["rubric", round.id], r);
    },
  });
  const locked = serverNow() >= Date.parse(round.starts_at);
  const total = rows.reduce((s, r) => s + (Number(r.weight) || 0), 0);
  // So theo phần trăm làm tròn 2 chữ số để 33.33 + 33.33 + 33.34 không lệch do số thực
  const valid = rows.length > 0 && Math.round(total * 100) === 10_000 && rows.every((r) => r.name.trim() && Number(r.max_score) > 0 && Number(r.weight) >= 0);
  const edit = (i: number, patch: Partial<Row>) => {
    setSaved(false);
    setRows((all) => all.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  };
  const move = (i: number, d: number) => {
    setSaved(false);
    setRows((all) => {
      const next = [...all];
      [next[i], next[i + d]] = [next[i + d], next[i]];
      return next;
    });
  };

  function submit(e: FormEvent) {
    e.preventDefault();
    if (valid) save.mutate();
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-black">Rubric · {round.name}</h2>
        <span role="status" aria-live="polite" className={`chip font-mono text-sm ${Math.round(total * 100) === 10_000 ? "bg-mint" : "bg-rose"}`}>
          Tổng trọng số {Math.round(total * 100) / 100}/100
        </span>
      </div>
      {locked && <p className="rounded-xl border-2 border-dashed border-ink bg-warm px-3.5 py-2.5 text-sm">Vòng đã bắt đầu nên rubric chỉ còn xem; rubric đã dùng để chấm không sửa được.</p>}
      {rows.length === 0 && <p className="font-serif italic text-muted">Chưa có tiêu chí nào.</p>}
      <ol className="space-y-3">
        {rows.map((r, i) => (
          <li key={i} className="rounded-2xl border-2 border-ink p-3.5">
            <fieldset disabled={locked} className="flex flex-wrap items-end gap-2.5">
              <legend className="sr-only">Tiêu chí {i + 1}</legend>
              <span className="font-mono text-lg font-extrabold">{i + 1}.</span>
              <label className="min-w-0 flex-[2_1_220px]">
                <span className="text-sm font-bold">Tên tiêu chí</span>
                <input value={r.name} onChange={(e) => edit(i, { name: e.target.value })} required maxLength={200} className={`mt-1.5 ${INPUT}`} />
              </label>
              <label className="w-28">
                <span className="text-sm font-bold">Trọng số %</span>
                <input value={r.weight} onChange={(e) => edit(i, { weight: e.target.value })} required inputMode="decimal" className={`mt-1.5 ${INPUT} font-mono`} />
              </label>
              <label className="w-28">
                <span className="text-sm font-bold">Điểm tối đa</span>
                <input value={r.max_score} onChange={(e) => edit(i, { max_score: e.target.value })} required inputMode="decimal" className={`mt-1.5 ${INPUT} font-mono`} />
              </label>
              <span className="flex gap-1.5">
                <button type="button" className="btn bg-paper text-sm" disabled={i === 0} onClick={() => move(i, -1)} aria-label={`Đưa tiêu chí ${i + 1} lên`}>
                  ↑
                </button>
                <button type="button" className="btn bg-paper text-sm" disabled={i === rows.length - 1} onClick={() => move(i, 1)} aria-label={`Đưa tiêu chí ${i + 1} xuống`}>
                  ↓
                </button>
                <button type="button" className="btn bg-paper text-sm" onClick={() => setRows((all) => all.filter((_, j) => j !== i))}>
                  Xóa
                </button>
              </span>
              <label className="w-full">
                <span className="text-sm font-bold">Mô tả cho giám khảo</span>
                <input value={r.description} onChange={(e) => edit(i, { description: e.target.value })} maxLength={2000} className={`mt-1.5 ${INPUT}`} />
              </label>
            </fieldset>
          </li>
        ))}
      </ol>
      {!locked && (
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" className={buttonClass("accent")} onClick={() => setRows((all) => [...all, { name: "", description: "", weight: "0", max_score: "10" }])}>
            + Thêm tiêu chí
          </button>
          <button type="submit" className={buttonClass("primary")} disabled={!valid || save.isPending}>
            {save.isPending ? "Đang lưu…" : "Lưu rubric"}
          </button>
          {!valid && rows.length > 0 && <span className="text-sm text-muted">Tổng trọng số phải đúng 100, mỗi tiêu chí cần tên và điểm tối đa &gt; 0.</span>}
          {saved && <span role="status" className="text-sm font-semibold">Đã lưu.</span>}
        </div>
      )}
      {save.isError && <FormError>{errorMessage(save.error)}</FormError>}
    </form>
  );
}

// ---------- Đội vào vòng ----------

function EligiblePanel({ eventId, round }: { eventId: string; round: Round }) {
  const rounds = useRounds(eventId);
  const eligible = useEligible(eventId, round.id);
  const earlier = rounds.data?.filter((r) => r.order < round.order) ?? [];
  if (eligible.isError) return <FormError>{errorMessage(eligible.error)}</FormError>;
  if (!eligible.data || !rounds.data) return <p role="status">Đang tải…</p>;
  if (!earlier.length)
    return (
      <div className="space-y-3">
        <h2 className="text-xl font-black">Đội thi {round.name}</h2>
        <p className="text-sm text-muted">Vòng đầu: mọi đội đã duyệt đều được thi.</p>
        <TeamChips teams={eligible.data} />
      </div>
    );
  return <EligibleForm eventId={eventId} round={round} earlier={earlier} current={eligible.data} />;
}

function TeamChips({ teams }: { teams: RoundTeam[] }) {
  if (!teams.length) return <p className="font-serif italic text-muted">Chưa có đội nào.</p>;
  return (
    <ul className="flex flex-wrap gap-2">
      {teams.map((t) => (
        <li key={t.team_id} className="chip bg-paper">
          {t.name}
        </li>
      ))}
    </ul>
  );
}

function EligibleForm({ eventId, round, earlier, current }: { eventId: string; round: Round; earlier: Round[]; current: RoundTeam[] }) {
  const queryClient = useQueryClient();
  const [source, setSource] = useState(current[0]?.source_round_id ?? earlier.at(-1)!.id);
  const [picked, setPicked] = useState(() => new Set(current.map((t) => t.team_id)));
  // BTC đọc được bảng xếp hạng vòng nguồn kể cả trước công bố; BE chỉ nhận đội có kết quả đã công bố
  const board = useQuery({ queryKey: ["leaderboard", source, ""], queryFn: async () => (await api.get<LeaderboardData>(`/events/${eventId}/rounds/${source}/leaderboard`, ALL)).data });
  const save = useMutation({
    mutationFn: async () => (await api.put<Page<RoundTeam>>(`/events/${eventId}/rounds/${round.id}/eligible-teams`, { source_round_id: source, team_ids: [...picked] })).data.items,
    onSuccess: (items) => queryClient.setQueryData(["eligible", round.id], items),
  });
  const locked = serverNow() >= Date.parse(round.starts_at);
  const toggle = (id: string) =>
    setPicked((s) => {
      const next = new Set(s);
      if (!next.delete(id)) next.add(id);
      return next;
    });

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-black">Đội đi tiếp vào {round.name}</h2>
      <p className="text-sm text-muted">
        Chọn từ đội có kết quả đã công bố ở vòng nguồn. Không tự lấy top N khi đồng hạng; đổi danh sách trước giờ bắt đầu sẽ ghi audit và báo trưởng nhóm.
      </p>
      <label className="block max-w-sm">
        <span className="text-sm font-bold">Vòng nguồn</span>
        <select value={source} disabled={locked} onChange={(e) => setSource(e.target.value)} className={`mt-1.5 ${INPUT}`}>
          {earlier.map((r) => (
            <option key={r.id} value={r.id}>
              {r.name}
            </option>
          ))}
        </select>
      </label>
      {board.isError && <FormError>{errorMessage(board.error)}</FormError>}
      <fieldset disabled={locked} className="space-y-2">
        <legend className="text-sm font-bold">Đội được chọn · {picked.size}</legend>
        {board.data?.items.length === 0 && <p className="font-serif italic text-muted">Vòng nguồn chưa có đội được xếp hạng.</p>}
        {board.data?.items.map((r) => (
          <label key={r.team.id} className="flex min-h-11 cursor-pointer items-center gap-3 rounded-xl border-2 border-ink px-3 text-sm">
            <input type="checkbox" checked={picked.has(r.team.id)} onChange={() => toggle(r.team.id)} className="size-5 accent-ink" />
            <span className="font-mono font-extrabold">#{r.rank}</span>
            <b className="flex-1">{r.team.name}</b>
            {r.tied && <span className="chip bg-sun text-xs">đồng hạng</span>}
            <span className="font-mono">{Number(r.total).toFixed(2)}</span>
          </label>
        ))}
      </fieldset>
      {locked ? (
        <p className="text-sm text-muted">Vòng đã bắt đầu nên danh sách đã chốt.</p>
      ) : (
        <button type="button" className={buttonClass("primary")} disabled={save.isPending} onClick={() => save.mutate()}>
          {save.isPending ? "Đang lưu…" : "Lưu danh sách"}
        </button>
      )}
      {save.isError && <FormError>{errorMessage(save.error)}</FormError>}
      {save.isSuccess && <p role="status" className="text-sm font-semibold">Đã lưu {save.data.length} đội.</p>}
    </div>
  );
}

// ---------- Phân công giám khảo ----------

function AssignmentsPanel({ eventId, round }: { eventId: string; round: Round }) {
  const queryClient = useQueryClient();
  const judges = useRoleUsers(eventId, "judge");
  const teams = useEligible(eventId, round.id);
  const assignments = useQuery({ queryKey: ["assignments", round.id], queryFn: async () => (await api.get<Page<Assignment>>(`/events/${eventId}/rounds/${round.id}/assignments`, ALL)).data.items });
  const conflicts = useQuery({ queryKey: ["conflicts", eventId], queryFn: async () => (await api.get<Page<Conflict>>(`/events/${eventId}/conflicts`, ALL)).data.items });
  const [batch, setBatch] = useState<AssignmentBatch | null>(null);
  // Đếm theo giờ server để nút phân công tự bật đúng lúc qua hạn nộp
  const deadlinePassed = useSecondsLeft(round.submission_deadline) === 0;
  const reload = () => Promise.all([queryClient.invalidateQueries({ queryKey: ["assignments", round.id] }), queryClient.invalidateQueries({ queryKey: ["progress", round.id] })]);
  const onBatch = { onSuccess: (b: AssignmentBatch) => setBatch(b), onSettled: reload };
  const auto = useMutation({ mutationFn: async () => (await api.post<AssignmentBatch>(`/events/${eventId}/rounds/${round.id}/assignments/auto`, { judges_per_team: round.required_judges })).data, ...onBatch });
  const assign = useMutation({ mutationFn: async (b: { judge_id: string; team_ids: string[] }) => (await api.post<AssignmentBatch>(`/events/${eventId}/rounds/${round.id}/assignments`, b)).data, ...onBatch });
  const act = useMutation({
    mutationFn: ({ a, action, reason }: { a: Assignment; action: "delete" | "cancel" | "reopen"; reason?: string }) =>
      action === "delete" ? api.delete(`/assignments/${a.id}`) : api.post(`/assignments/${a.id}/${action}`, { reason }),
    onSettled: reload,
  });

  if (teams.isError || assignments.isError) return <FormError>{errorMessage(teams.error ?? assignments.error)}</FormError>;
  if (!teams.data || !assignments.data || !judges) return <p role="status">Đang tải…</p>;
  const active = new Map(assignments.data.filter((a) => a.status !== "cancelled").map((a) => [`${a.judge.id}:${a.team.id}`, a]));
  const conflict = new Map(conflicts.data?.map((c) => [`${c.judge.id}:${c.team_id}`, c]));
  const teamName = new Map(teams.data.map((t) => [t.team_id, t.name]));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-black">Phân công · {round.required_judges} giám khảo/đội</h2>
        <button type="button" className={buttonClass("accent")} disabled={auto.isPending || !deadlinePassed} onClick={() => auto.mutate()}>
          {auto.isPending ? "Đang phân công…" : "Tự động phân công"}
        </button>
      </div>
      {!deadlinePassed && (
        <p className="text-sm text-muted">
          Chỉ phân công được sau hạn nộp (<LocalTime iso={round.submission_deadline} />), cho đội có bản cuối hợp lệ.
        </p>
      )}
      <p className="text-sm text-muted">Tự động chỉ bù chỗ còn thiếu, không ghi đè phân công thủ công và bỏ cặp có xung đột hoặc từng là mentor của đội.</p>
      {[auto, assign, act].map((m, i) => m.isError && <FormError key={i}>{errorMessage(m.error)}</FormError>)}
      {batch && <BatchReport batch={batch} teamName={teamName} onClose={() => setBatch(null)} />}
      {judges.length === 0 ? (
        <p className="font-serif italic text-muted">Chưa có giám khảo; thêm ở tab “Giám khảo &amp; mentor”.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm" style={{ minWidth: 200 + judges.length * 170 }}>
            <thead className="border-b-2 border-ink">
              <tr>
                <th scope="col" className="px-3 py-2.5">Đội \ Giám khảo</th>
                {judges.map((j) => (
                  <th key={j.id} scope="col" className="px-3 py-2.5">
                    <span className="block break-words">{j.full_name}</span>
                    <span className="block break-all text-xs font-normal text-muted">{j.email}</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {teams.data.map((t) => (
                <tr key={t.team_id} className="border-t border-line align-top">
                  <th scope="row" className="px-3 py-3 font-extrabold">{t.name}</th>
                  {judges.map((j) => {
                    const a = active.get(`${j.id}:${t.team_id}`);
                    const c = conflict.get(`${j.id}:${t.team_id}`);
                    return (
                      <td key={j.id} className={`px-3 py-3 ${c ? "bg-rose/40" : ""}`}>
                        <div className="flex flex-col items-start gap-1.5">
                          {c && (
                            <span className="chip bg-rose text-xs" title={c.reason}>
                              ⚠ Xung đột
                            </span>
                          )}
                          {a ? (
                            <>
                              <span className={`chip text-xs ${ASSIGNMENT_STATUS[a.status][1]}`}>{ASSIGNMENT_STATUS[a.status][0]}</span>
                              <span className="flex flex-wrap gap-1">
                                {a.status === "pending" ? (
                                  <button type="button" className="btn min-h-9 bg-paper text-xs" disabled={act.isPending} onClick={() => act.mutate({ a, action: "delete" })}>
                                    Gỡ
                                  </button>
                                ) : (
                                  <button
                                    type="button"
                                    className="btn min-h-9 bg-paper text-xs"
                                    disabled={act.isPending}
                                    onClick={() => {
                                      const reason = askReason(`Lý do hủy phân công ${j.full_name} – ${t.name}? Điểm đã chấm được giữ trong lịch sử nhưng không tính.`);
                                      if (reason) act.mutate({ a, action: "cancel", reason });
                                    }}
                                  >
                                    Hủy…
                                  </button>
                                )}
                                {a.status === "submitted" && (
                                  <button
                                    type="button"
                                    className="btn min-h-9 bg-paper text-xs"
                                    disabled={act.isPending}
                                    onClick={() => {
                                      const reason = askReason(`Lý do mở lại bài chấm của ${j.full_name} cho ${t.name}?`);
                                      if (reason) act.mutate({ a, action: "reopen", reason });
                                    }}
                                  >
                                    Mở lại…
                                  </button>
                                )}
                              </span>
                            </>
                          ) : (
                            !c && (
                              <button type="button" className="btn min-h-9 bg-paper text-xs" disabled={assign.isPending || !deadlinePassed} onClick={() => assign.mutate({ judge_id: j.id, team_ids: [t.team_id] })}>
                                + Giao
                              </button>
                            )
                          )}
                        </div>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          {teams.data.length === 0 && <p className="p-3 font-serif italic text-muted">Vòng chưa có đội nào được thi.</p>}
        </div>
      )}
      {!!conflicts.data?.length && (
        <section className="rounded-2xl border-2 border-dashed border-ink p-4">
          <h3 className="font-black">Khai báo xung đột lợi ích · {conflicts.data.length}</h3>
          <ul className="mt-2 space-y-1.5 text-sm">
            {conflicts.data.map((c) => (
              <li key={c.id}>
                <b>{c.judge.full_name}</b> – {teamName.get(c.team_id) ?? "đội khác vòng"}: “{c.reason}” · <LocalTime iso={c.created_at} />
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

/** Kết quả một lượt phân công; HTTP 200 vẫn có thể thiếu chỗ nên phải liệt kê rõ. */
function BatchReport({ batch, teamName, onClose }: { batch: AssignmentBatch; teamName: Map<string, string>; onClose: () => void }) {
  const ok = !batch.skipped.length && !batch.unfilled.length;
  return (
    <div role="status" className={`rounded-2xl border-2 border-ink p-4 text-sm ${ok ? "bg-mint" : "bg-sun"}`}>
      <div className="flex items-start justify-between gap-3">
        <p className="font-bold">
          Đã tạo {batch.items.length} phân công.{ok ? " Mọi đội đủ giám khảo." : " Chưa đầy đủ:"}
        </p>
        <button type="button" className="btn min-h-9 bg-paper text-xs" onClick={onClose}>
          Đóng
        </button>
      </div>
      {batch.skipped.length > 0 && (
        <ul className="mt-2 list-disc pl-5">
          {batch.skipped.map((s, i) => (
            <li key={i}>
              Bỏ qua {teamName.get(s.team_id) ?? s.team_id}: {codeMessage(s.code)}
            </li>
          ))}
        </ul>
      )}
      {batch.unfilled.length > 0 && (
        <ul className="mt-2 list-disc pl-5">
          {batch.unfilled.map((u) => (
            <li key={u.team_id}>
              {teamName.get(u.team_id) ?? u.team_id} còn thiếu {u.missing_judges} giám khảo
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ---------- Tiến độ, khóa, công bố ----------

const PROGRESS_STATUS: Record<Progress["status"], [string, string]> = {
  not_submitted: ["Không nộp bài", "bg-warm"],
  pending: ["Đang chấm", "bg-sun"],
  complete: ["Đủ điểm", "bg-mint"],
};

function ProgressPanel({ eventId, round }: { eventId: string; round: Round }) {
  const queryClient = useQueryClient();
  const tracks = useTracks(eventId);
  const rubric = useRubric(eventId, round.id);
  const [trackId, setTrackId] = useState("");
  const progress = useQuery({ queryKey: ["progress", round.id], queryFn: async () => (await api.get<JudgingProgress>(`/events/${eventId}/rounds/${round.id}/judging-progress`, ALL)).data });
  const event = useEvent(eventId);
  const board = useQuery({
    queryKey: ["leaderboard", round.id, trackId],
    queryFn: async () => (await api.get<LeaderboardData>(`/events/${eventId}/rounds/${round.id}/leaderboard`, { params: { limit: 100, track_id: trackId || undefined } })).data,
  });
  const [done, setDone] = useState("");
  const change = useMutation({
    mutationFn: ({ action, reason }: { action: "lock" | "unlock" | "publish" | "unpublish"; reason?: string }) => api.post(`/events/${eventId}/rounds/${round.id}/${action}`, reason ? { reason } : undefined),
    onSuccess: (_, { action }) => setDone({ lock: "Đã khóa điểm.", unlock: "Đã mở khóa điểm.", publish: "Đã công bố kết quả; email gửi qua hàng đợi.", unpublish: "Đã thu hồi công bố." }[action]),
    onSettled: () => Promise.all(["progress", "leaderboard", "assignments"].map((k) => queryClient.invalidateQueries({ queryKey: [k, round.id] }))),
  });
  const run = (action: "lock" | "unlock" | "publish" | "unpublish") => {
    setDone("");
    if (action === "lock" && window.confirm("Khóa điểm vòng này? Giám khảo không sửa được nữa; Admin đọc được điểm.")) change.mutate({ action });
    if (action === "publish" && window.confirm("Công bố kết quả? Bảng xếp hạng hiện công khai và email kết quả được gửi cho các đội.")) change.mutate({ action });
    if (action === "unlock") {
      const reason = askReason("Lý do mở khóa điểm?");
      if (reason) change.mutate({ action, reason });
    }
    if (action === "unpublish") {
      const reason = askReason("Lý do thu hồi công bố? Trang công khai sẽ ẩn kết quả cho tới khi công bố lại.");
      if (reason) change.mutate({ action, reason });
    }
  };
  const trackName = new Map(tracks.data?.map((t) => [t.id, t.name]));
  // Chưa tải xong trạng thái vòng/cuộc thi thì không hiện thao tác, tránh đoán sai
  const state = progress.data && event.data ? progress.data : null;
  const readOnly = event.data?.status === "closed" || !!event.data?.archived_at;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-black">Tiến độ chấm · {round.name}</h2>
        {state && (
          <div className="flex flex-wrap items-center gap-2">
            <span className={`chip ${state.published_at ? "bg-mint" : state.locked_at ? "bg-sun" : "bg-paper"}`}>
              {state.published_at ? "Đã công bố" : state.locked_at ? "Đã khóa điểm" : "Đang chấm"}
            </span>
            {!readOnly && !state.locked_at && (
              <button type="button" className={buttonClass("primary")} disabled={change.isPending} onClick={() => run("lock")}>
                Khóa điểm
              </button>
            )}
            {!readOnly && state.locked_at && !state.published_at && (
              <>
                <button type="button" className={buttonClass("secondary")} disabled={change.isPending} onClick={() => run("unlock")}>
                  Mở khóa…
                </button>
                <button type="button" className={buttonClass("accent")} disabled={change.isPending} onClick={() => run("publish")}>
                  Công bố
                </button>
              </>
            )}
            {!readOnly && state.published_at && (
              <button type="button" className={buttonClass("secondary")} disabled={change.isPending} onClick={() => run("unpublish")}>
                Thu hồi công bố…
              </button>
            )}
          </div>
        )}
      </div>
      <p className="text-sm text-muted">Sửa kết quả đã công bố: Thu hồi công bố → Mở khóa → Mở lại bài chấm (tab Phân công) → giám khảo xác nhận lại → Khóa → Công bố bản mới.</p>
      {change.isError && <FormError>{errorMessage(change.error)}</FormError>}
      {done && <p role="status" className="rounded-xl border-2 border-ink bg-mint px-3.5 py-2.5 text-sm font-semibold">{done}</p>}
      {progress.isError && <FormError>{errorMessage(progress.error)}</FormError>}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-left text-sm">
          <thead className="border-b-2 border-ink">
            <tr>
              <th scope="col" className="px-3 py-2.5">Đội</th>
              <th scope="col" className="px-3 py-2.5">Trạng thái</th>
              <th scope="col" className="px-3 py-2.5 text-right">Cần</th>
              <th scope="col" className="px-3 py-2.5 text-right">Đã giao</th>
              <th scope="col" className="px-3 py-2.5 text-right">Đã xác nhận</th>
              <th scope="col" className="px-3 py-2.5 text-right">Thiếu</th>
              <th scope="col" className="px-3 py-2.5">Xung đột</th>
            </tr>
          </thead>
          <tbody>
            {progress.data?.items.map((p) => (
              <tr key={p.team.id} className="border-t border-line">
                <td className="px-3 py-3 font-extrabold">{p.team.name}</td>
                <td className="px-3 py-3">
                  <span className={`chip ${PROGRESS_STATUS[p.status][1]}`}>{PROGRESS_STATUS[p.status][0]}</span>
                </td>
                <td className="px-3 py-3 text-right font-mono">{p.required}</td>
                <td className="px-3 py-3 text-right font-mono">{p.assigned}</td>
                <td className="px-3 py-3 text-right font-mono">{p.submitted}</td>
                <td className="px-3 py-3 text-right font-mono">{p.missing}</td>
                <td className="px-3 py-3">{p.has_conflict ? <span className="chip bg-rose">⚠ Cần thay giám khảo</span> : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {progress.data?.items.length === 0 && <p className="p-3 font-serif italic text-muted">Vòng chưa có đội nào.</p>}
      </div>

      <section className="space-y-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <h3 className="text-lg font-black">Bảng xếp hạng (BTC xem trước khi công bố)</h3>
          {!!tracks.data?.length && (
            <select aria-label="Lọc track" value={trackId} onChange={(e) => setTrackId(e.target.value)} className="min-h-11 rounded-xl border-2 border-ink bg-paper px-3">
              <option value="">Mọi track</option>
              {tracks.data.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          )}
        </div>
        {board.isError && <FormError>{errorMessage(board.error)}</FormError>}
        {board.data && rubric.data && (
          <div className="sketch overflow-hidden">
            <LeaderboardTable rows={board.data.items} criteria={rubric.data.criteria} trackName={trackName} />
          </div>
        )}
        <p className="text-xs text-muted">
          {FORMULA_NOTE} {board.data && `Đã công bố ${board.data.publication_revision} lần.`}
        </p>
      </section>
    </div>
  );
}

// ---------- Phân công mentor (theo cuộc thi) ----------

export function MentorAssignmentsPanel({ eventId }: { eventId: string }) {
  const queryClient = useQueryClient();
  const mentors = useRoleUsers(eventId, "mentor");
  const teams = useQuery({ queryKey: ["event-teams", eventId, "approved-all"], queryFn: async () => (await api.get<Page<Team>>(`/events/${eventId}/teams`, { params: { status: "approved", limit: 100 } })).data.items });
  const list = useQuery({ queryKey: ["mentor-assignments", eventId], queryFn: async () => (await api.get<Page<MentorAssignment>>(`/events/${eventId}/mentor-assignments`, ALL)).data.items });
  const reload = () => queryClient.invalidateQueries({ queryKey: ["mentor-assignments", eventId] });
  const add = useMutation({ mutationFn: (body: { mentor_id: string; team_ids: string[] }) => api.post(`/events/${eventId}/mentor-assignments`, body), onSuccess: reload });
  const remove = useMutation({ mutationFn: (id: string) => api.delete(`/mentor-assignments/${id}`), onSuccess: reload });

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const fd = new FormData(form);
    const team_ids = fd.getAll("team").map(String);
    if (team_ids.length) add.mutate({ mentor_id: String(fd.get("mentor")), team_ids }, { onSuccess: () => form.reset() });
  }

  return (
    <div className="space-y-5">
      <h2 className="text-xl font-black">Phân công mentor</h2>
      <p className="text-sm text-muted">Thu hồi phân công làm mentor mất quyền đọc đội ngay; góp ý và câu trả lời cũ vẫn được giữ. Mentor từng hỗ trợ đội sẽ không được giao chấm đội đó.</p>
      {list.isError && <FormError>{errorMessage(list.error)}</FormError>}
      {remove.isError && <FormError>{errorMessage(remove.error)}</FormError>}
      {list.data?.length === 0 && <p className="font-serif italic text-muted">Chưa có phân công nào.</p>}
      <ul className="space-y-2.5">
        {list.data?.map((m) => (
          <li key={m.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-2xl border-2 border-dashed border-ink px-3.5 py-3">
            <span className="min-w-0 flex-[1_1_220px]">
              <b className="break-words">{m.mentor.full_name}</b> → <b>{m.team.name}</b>
              <span className="block text-xs text-muted">
                từ <LocalTime iso={m.created_at} />
              </span>
            </span>
            <button
              type="button"
              className="btn bg-paper text-sm"
              disabled={remove.isPending}
              onClick={() => {
                if (window.confirm(`Thu hồi ${m.mentor.full_name} khỏi đội ${m.team.name}?`)) remove.mutate(m.id);
              }}
            >
              Thu hồi
            </button>
          </li>
        ))}
      </ul>
      {mentors?.length === 0 ? (
        <p className="font-serif italic text-muted">Chưa có mentor; thêm ở tab “Giám khảo &amp; mentor”.</p>
      ) : (
        <form onSubmit={submit} className="space-y-3 border-t-2 border-dashed border-line pt-4">
          <label className="block max-w-sm">
            <span className="text-sm font-bold">Mentor</span>
            <select name="mentor" required className={`mt-1.5 ${INPUT}`}>
              {mentors?.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.full_name} · {m.email}
                </option>
              ))}
            </select>
          </label>
          <fieldset>
            <legend className="text-sm font-bold">Đội (đã duyệt)</legend>
            {teams.data?.length === 0 && <p className="text-sm text-muted">Chưa có đội đã duyệt.</p>}
            <div className="mt-1.5 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {teams.data?.map((t) => (
                <label key={t.id} className="flex min-h-11 cursor-pointer items-center gap-2.5 rounded-xl border-2 border-ink px-3 text-sm font-bold">
                  <input type="checkbox" name="team" value={t.id} className="size-5 accent-ink" />
                  {t.name}
                </label>
              ))}
            </div>
          </fieldset>
          <button type="submit" className={buttonClass("primary")} disabled={add.isPending}>
            Phân công
          </button>
          {add.isError && <FormError>{errorMessage(add.error)}</FormError>}
        </form>
      )}
    </div>
  );
}
