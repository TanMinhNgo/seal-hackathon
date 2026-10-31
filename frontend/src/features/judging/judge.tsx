"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { buttonClass } from "@/components/ui/button";
import { LocalTime } from "@/components/ui/local-time";
import { FormError } from "@/features/auth/auth-card";
import { useMyEvents } from "@/features/auth/use-event-roles";
import type { Assignment, AssignmentDetail, Conflict, Page } from "@/features/events/types";
import { Receipt, useRounds } from "@/features/submissions/submissions";
import { api, errorCode, errorMessage } from "@/lib/api";

const STATUS: Record<Assignment["status"], [string, string]> = {
  pending: ["Chưa chấm", "bg-paper"],
  draft: ["Đang chấm (nháp)", "bg-sun"],
  submitted: ["Đã xác nhận", "bg-mint"],
  cancelled: ["BTC đã hủy", "bg-warm"],
};
const INPUT = "mt-1.5 block w-full rounded-xl border-2 border-ink bg-paper px-3 text-[15px]";

/** Danh sách bài được giao theo cuộc thi; `eventId` lấy từ ?event=, mặc định cuộc thi đầu tiên. */
export function JudgeHome({ eventId }: { eventId?: string }) {
  const mine = useMyEvents();
  const events = mine.data?.items.filter((m) => m.roles.includes("judge")).map((m) => m.event) ?? [];
  const event = events.find((e) => e.id === eventId) ?? events[0];

  return (
    <main className="mx-auto max-w-[1200px] space-y-7 px-4 pb-24 pt-8 sm:px-6">
      <div>
        <p className="font-serif text-lg italic">Giám khảo</p>
        <h1 className="mt-1 text-[clamp(38px,5vw,60px)] font-black leading-none tracking-[-0.045em]">Bài được giao.</h1>
      </div>
      {mine.isError && <FormError>{errorMessage(mine.error)}</FormError>}
      {mine.isPending && <p role="status">Đang tải…</p>}
      {events.length > 1 && (
        <nav aria-label="Chọn cuộc thi" className="flex flex-wrap gap-2">
          {events.map((e) => (
            <Link key={e.id} href={`/judge?event=${e.id}`} aria-current={e.id === event?.id ? "page" : undefined} className={`btn ${e.id === event?.id ? "bg-ink text-paper" : "bg-paper"}`}>
              {e.name}
            </Link>
          ))}
        </nav>
      )}
      {event && <EventAssignments key={event.id} eventId={event.id} />}
    </main>
  );
}

function EventAssignments({ eventId }: { eventId: string }) {
  const rounds = useRounds(eventId);
  const list = useQuery({
    queryKey: ["my-assignments", eventId],
    // shortcut: 100 phân công đầu; một giám khảo hiếm khi chấm nhiều hơn trong một cuộc thi
    queryFn: async () => (await api.get<Page<Assignment>>("/me/assignments", { params: { event_id: eventId, limit: 100 } })).data.items,
  });
  const roundName = new Map(rounds.data?.map((r) => [r.id, r.name]));
  const teams = [...new Map(list.data?.map((a) => [a.team.id, a.team.name])).entries()];

  return (
    <>
      <section className="sketch p-6">
        {list.isError && <FormError>{errorMessage(list.error)}</FormError>}
        {list.data?.length === 0 && <p className="font-serif italic text-muted">Chưa có bài nào được giao. BTC phân công sau hạn nộp của từng vòng.</p>}
        <ul className="space-y-2.5">
          {list.data?.map((a) => (
            <li key={a.id} className={`flex flex-wrap items-center gap-x-4 gap-y-2 rounded-2xl border-2 border-ink px-4 py-3 ${a.status === "cancelled" ? "bg-warm" : ""}`}>
              <span className="min-w-0 flex-[1_1_240px]">
                <b className="break-words text-lg">{a.team.name}</b>
                <span className="block text-sm text-muted">
                  {roundName.get(a.round_id) ?? "Vòng"}
                  {a.submitted_at && (
                    <>
                      {" "}
                      · xác nhận <LocalTime iso={a.submitted_at} />
                    </>
                  )}
                </span>
              </span>
              <span className={`chip ${STATUS[a.status][1]}`}>{STATUS[a.status][0]}</span>
              {a.status !== "cancelled" && (
                <Link href={`/judge/${a.id}`} className={buttonClass(a.status === "submitted" ? "secondary" : "primary")}>
                  {a.status === "submitted" ? "Xem điểm" : "Chấm →"}
                </Link>
              )}
            </li>
          ))}
        </ul>
      </section>
      {teams.length > 0 && <ConflictForm eventId={eventId} teams={teams} />}
    </>
  );
}

function ConflictForm({ eventId, teams }: { eventId: string; teams: [string, string][] }) {
  const queryClient = useQueryClient();
  const mine = useQuery({ queryKey: ["conflicts", eventId], queryFn: async () => (await api.get<Page<Conflict>>(`/events/${eventId}/conflicts`, { params: { limit: 100 } })).data.items });
  const add = useMutation({
    mutationFn: (body: { team_id: string; reason: string }) => api.post(`/events/${eventId}/conflicts`, body),
    onSuccess: () => Promise.all([queryClient.invalidateQueries({ queryKey: ["conflicts", eventId] }), queryClient.invalidateQueries({ queryKey: ["my-assignments", eventId] })]),
  });
  const name = new Map(teams);

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const fd = new FormData(form);
    add.mutate({ team_id: String(fd.get("team")), reason: String(fd.get("reason")).trim() }, { onSuccess: () => form.reset() });
  }

  return (
    <section className="rounded-[22px] border-2 border-dashed border-ink p-6">
      <h2 className="text-xl font-black">Khai báo xung đột lợi ích</h2>
      <p className="mt-1 text-sm text-muted">Quen biết, từng làm cùng hoặc từng hướng dẫn đội? Khai báo để BTC thay giám khảo. Bài đó sẽ bị chặn chấm ngay.</p>
      {!!mine.data?.length && (
        <ul className="mt-3 space-y-1.5 text-sm">
          {mine.data.map((c) => (
            <li key={c.id}>
              <b>{name.get(c.team_id) ?? "Đội"}</b>: “{c.reason}” · <LocalTime iso={c.created_at} />
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={submit} className="mt-4 flex flex-wrap items-end gap-3">
        <label className="min-w-0 flex-[1_1_200px]">
          <span className="text-sm font-bold">Đội</span>
          <select name="team" required className={`${INPUT} min-h-11`}>
            {teams.map(([id, n]) => (
              <option key={id} value={id}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <label className="min-w-0 flex-[2_1_300px]">
          <span className="text-sm font-bold">Lý do</span>
          <input name="reason" required maxLength={2000} className={`${INPUT} min-h-11`} />
        </label>
        <button type="submit" className={buttonClass("primary")} disabled={add.isPending}>
          Khai báo
        </button>
        {add.isError && <div className="w-full"><FormError>{errorMessage(add.error)}</FormError></div>}
      </form>
    </section>
  );
}

// ---------- Màn chấm ----------

export function ScoreScreen({ assignmentId }: { assignmentId: string }) {
  const detail = useQuery({ queryKey: ["assignment", assignmentId], queryFn: async () => (await api.get<AssignmentDetail>(`/assignments/${assignmentId}`)).data,
    // Tải lại sẽ dựng lại form và xóa phần đang nhập, nên chỉ tải khi người dùng bấm
    staleTime: Infinity,
  });
  if (detail.isError) return <main className="mx-auto max-w-[1360px] px-4 pt-10 sm:px-6"><FormError>{errorMessage(detail.error)}</FormError></main>;
  if (!detail.data) return <p role="status" className="px-6 pt-12 text-center">Đang tải…</p>;
  const d = detail.data;
  return (
    <main className="mx-auto max-w-[1360px] px-4 pb-24 pt-8 sm:px-6">
      <Link href="/judge" className="text-sm font-bold underline">
        ← Bài được giao
      </Link>
      <h1 className="mt-2 break-words text-[clamp(38px,5vw,60px)] font-black leading-none tracking-[-0.045em]">{d.assignment.team.name}</h1>
      <div className="mt-7 flex flex-wrap items-start gap-6">
        <div className="min-w-0 flex-[1_1_420px] space-y-5">
          <section aria-labelledby="sub" className="sketch p-5">
            <h2 id="sub" className="mb-3 text-xl font-black">
              Bài được chấm
            </h2>
            <p className="mb-3 text-sm text-muted">Bản cuối hợp lệ trước hạn, đã ghim khi phân công; đội nộp thêm cũng không đổi.</p>
            <Receipt s={d.submission} />
          </section>
          <section className="rounded-[22px] border-2 border-dashed border-ink p-5 text-sm">
            <h2 className="text-lg font-black">Commit &amp; AI review</h2>
            <p className="mt-1.5 text-muted">Chưa sẵn sàng: lịch sử commit và nhận xét AI sẽ có khi hệ thống bật đồng bộ GitHub và AI review. Điểm AI chỉ để tham khảo, không cộng vào rubric.</p>
          </section>
        </div>
        <ScoreForm key={detail.dataUpdatedAt} detail={d} onReload={() => detail.refetch()} />
      </div>
    </main>
  );
}

type Value = { score: string; comment: string };

function ScoreForm({ detail, onReload }: { detail: AssignmentDetail; onReload: () => void }) {
  const queryClient = useQueryClient();
  const criteria = [...detail.rubric.criteria].sort((a, b) => a.order - b.order);
  const [values, setValues] = useState<Record<string, Value>>(() =>
    Object.fromEntries(criteria.map((c) => {
      const s = detail.scores.find((x) => x.criterion_id === c.id);
      return [c.id, { score: s ? String(Number(s.score)) : "", comment: s?.comment ?? "" }];
    })),
  );
  const [general, setGeneral] = useState(detail.general_comment ?? "");
  const [assignment, setAssignment] = useState(detail.assignment);
  const [dirty, setDirty] = useState(false);
  const [stale, setStale] = useState(false);
  const [confirming, setConfirming] = useState(false);
  // Giữ revision mới nhất ngoài state để lượt lưu kế tiếp không dùng giá trị cũ của closure
  const revision = useRef(detail.assignment.revision);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const editable = (assignment.status === "pending" || assignment.status === "draft") && !stale;

  // Đếm lần sửa để biết có gõ thêm trong lúc đang lưu hay không
  const edits = useRef(0);
  const save = useMutation({
    mutationFn: async () => {
      const sent = edits.current;
      const { data } = await api.put<{ assignment: Assignment }>(`/assignments/${assignment.id}/scores`, {
        expected_revision: revision.current,
        scores: criteria.filter((c) => values[c.id].score.trim() !== "").map((c) => ({ criterion_id: c.id, score: values[c.id].score.trim(), comment: values[c.id].comment.trim() || null })),
        general_comment: general.trim() || null,
      });
      return { assignment: data.assignment, sent };
    },
    onSuccess: (r) => {
      revision.current = r.assignment.revision;
      setAssignment(r.assignment);
      if (edits.current === r.sent) setDirty(false);
    },
    // Không tự thử lại khi bản nháp bị tab khác đổi, để không ghi đè
    onError: (e) => errorCode(e) === "SCORE_VERSION_CONFLICT" && setStale(true),
  });
  const submit = useMutation({
    mutationFn: async () => {
      if (dirty) await save.mutateAsync();
      return (await api.post<Assignment>(`/assignments/${assignment.id}/submit`, { expected_revision: revision.current })).data;
    },
    onSuccess: (a) => {
      revision.current = a.revision;
      setAssignment(a);
      setConfirming(false);
      return queryClient.invalidateQueries({ queryKey: ["my-assignments"] });
    },
    onError: (e) => errorCode(e) === "SCORE_VERSION_CONFLICT" && setStale(true),
  });

  // Tự lưu nháp 1,2 giây sau lần gõ cuối; đang lưu thì chờ lượt sau
  useEffect(() => {
    if (!dirty || !editable) return;
    clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      if (!save.isPending) save.mutate();
    }, 1200);
    return () => clearTimeout(timer.current);
  }, [values, general, dirty, editable, save]);

  const touch = () => {
    edits.current++;
    setDirty(true);
  };
  const change = (id: string, patch: Partial<Value>) => {
    setValues((v) => ({ ...v, [id]: { ...v[id], ...patch } }));
    touch();
  };
  const complete = criteria.every((c) => {
    const n = Number(values[c.id].score);
    return values[c.id].score.trim() !== "" && n >= 0 && n <= Number(c.max_score);
  });
  // Chỉ là tạm tính để giám khảo tự kiểm tra; điểm chính thức do server tính
  const preview = criteria.reduce((s, c) => s + ((Number(values[c.id].score) || 0) / Number(c.max_score)) * Number(c.weight), 0);
  const saveLabel = stale ? "Có thay đổi ở nơi khác" : save.isPending ? "Đang lưu…" : dirty ? "Chưa lưu" : assignment.status === "submitted" ? "Đã xác nhận" : "Đã lưu nháp";

  return (
    <section aria-labelledby="rubric-title" className="sketch min-w-0 flex-[1.3_1_480px] rounded-[26px] p-6 shadow-[8px_8px_0_var(--ink)]">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="rubric-title" className="text-[26px] font-black tracking-tight">
          Rubric
        </h2>
        <span role="status" aria-live="polite" className="rounded-full border-[1.5px] border-dashed border-ink px-3 py-1 text-[13px] font-bold">
          {saveLabel}
        </span>
      </div>
      {stale && (
        <div role="alert" className="mt-4 rounded-xl border-2 border-ink bg-rose p-3.5 text-sm">
          <p className="font-bold">Bản nháp trên máy chủ đã đổi (tab hoặc thiết bị khác). Tự lưu đã dừng để không ghi đè.</p>
          <p className="mt-1">Giá trị bạn đang nhập vẫn hiện bên dưới để đối chiếu. Tải bản trên máy chủ sẽ thay chúng.</p>
          <button type="button" className="btn mt-2.5 bg-paper text-sm" onClick={onReload}>
            Tải bản trên máy chủ
          </button>
        </div>
      )}
      {assignment.status === "cancelled" && <p className="mt-4 rounded-xl border-2 border-ink bg-warm p-3.5 text-sm font-bold">BTC đã hủy phân công này; điểm không còn được tính.</p>}
      {criteria.length === 0 && <p className="mt-4 text-muted">Vòng chưa có rubric.</p>}
      <fieldset disabled={!editable} className="mt-5 space-y-4">
        <legend className="sr-only">Điểm từng tiêu chí</legend>
        {criteria.map((c) => (
          <div key={c.id} className="rounded-[18px] border-2 border-ink p-4">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <label htmlFor={`s-${c.id}`} className="min-w-0 flex-[1_1_200px] text-[17px] font-extrabold">
                {c.name} <span className="text-[13px] font-semibold text-muted">· trọng số {Number(c.weight)}%</span>
              </label>
              <span className="flex items-baseline gap-1 font-mono">
                <input
                  id={`s-${c.id}`}
                  type="number"
                  min={0}
                  max={Number(c.max_score)}
                  step="any"
                  inputMode="decimal"
                  value={values[c.id].score}
                  onChange={(e) => change(c.id, { score: e.target.value })}
                  className="min-h-11 w-24 rounded-xl border-2 border-ink bg-paper px-2 text-right text-xl font-extrabold"
                />
                <span className="text-muted">/{Number(c.max_score)}</span>
              </span>
            </div>
            {c.description && <p className="mt-1 text-[13px] text-muted">{c.description}</p>}
            <label className="mt-2 block text-xs font-bold">
              Nhận xét tiêu chí (tùy chọn)
              <input value={values[c.id].comment} onChange={(e) => change(c.id, { comment: e.target.value })} maxLength={2000} className={`${INPUT} min-h-10 text-sm font-normal`} />
            </label>
          </div>
        ))}
        <label className="block font-extrabold">
          Nhận xét chung gửi đội (ẩn danh, hiện sau khi công bố)
          <textarea
            rows={3}
            value={general}
            onChange={(e) => {
              setGeneral(e.target.value);
              touch();
            }}
            maxLength={5000}
            className="mt-1.5 block w-full resize-y rounded-[14px] border-2 border-ink px-3.5 py-3 text-base font-normal"
          />
        </label>
      </fieldset>
      {save.isError && !stale && <div className="mt-3"><FormError>{errorMessage(save.error)}</FormError></div>}
      {submit.isError && !stale && <div className="mt-3"><FormError>{errorMessage(submit.error)}</FormError></div>}
      <div className="mt-6 flex flex-wrap items-center justify-between gap-4 border-t-2 border-dashed border-line pt-5">
        <div>
          <p className="text-sm font-bold">Tạm tính (điểm chính thức do hệ thống tính)</p>
          <p className="font-mono text-[44px] font-extrabold leading-none">
            {preview.toFixed(2)}
            <span className="text-xl text-muted">/100</span>
          </p>
        </div>
        {assignment.status === "submitted" ? (
          <p role="status" className="-rotate-[1.5deg] rounded-full border-2 border-ink bg-mint px-4 py-2.5 font-extrabold">
            ✓ Đã xác nhận · chỉ BTC mở lại được
          </p>
        ) : confirming ? (
          <div role="alertdialog" aria-label="Xác nhận điểm" className="flex flex-[1_1_100%] flex-wrap items-center justify-between gap-3 rounded-[18px] border-2 border-ink bg-cream p-4">
            <p className="font-bold">Sau khi xác nhận bạn không sửa được nữa, chỉ ban tổ chức mở lại được. Chắc chứ?</p>
            <div className="flex gap-2.5">
              <button type="button" onClick={() => setConfirming(false)} className="btn bg-paper">
                Xem lại
              </button>
              <button type="button" onClick={() => submit.mutate()} disabled={submit.isPending} className="btn bg-orange font-extrabold">
                {submit.isPending ? "Đang gửi…" : "Xác nhận điểm"}
              </button>
            </div>
          </div>
        ) : (
          editable && (
            <button type="button" onClick={() => setConfirming(true)} disabled={!complete} className="btn h-[54px] bg-ink px-6 text-base font-extrabold text-paper shadow-lip-orange">
              Xác nhận điểm
            </button>
          )
        )}
      </div>
      {editable && !complete && <p className="mt-2 text-sm text-muted">Cần điểm hợp lệ cho mọi tiêu chí trước khi xác nhận.</p>}
    </section>
  );
}
