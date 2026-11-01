"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { buttonClass } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { LocalTime } from "@/components/ui/local-time";
import { Pager } from "@/components/ui/pager";
import { FormError } from "@/features/auth/auth-card";
import { CommitSelect, useForgetTeamOnForbidden } from "@/features/commits/commits";
import type { Answer, MentorNote, Page, Question } from "@/features/events/types";
import { api, errorMessage } from "@/lib/api";

const LIMIT = 20;
const TEXTAREA = "mt-1.5 block w-full resize-y rounded-xl border-2 border-ink bg-paper px-3 py-2.5 text-[15px] font-normal";
export const PROGRESS: Record<NonNullable<MentorNote["progress_status"]>, [string, string]> = {
  on_track: ["Đúng tiến độ", "bg-mint"],
  at_risk: ["Có rủi ro", "bg-sun"],
  blocked: ["Đang bị chặn", "bg-rose"],
};

/** Góp ý & ghi nhận tiến độ của mentor; `canPost` chỉ cho mentor đang được phân công. */
export function MentorNotes({ teamId, canPost, commitFilter, commitSha = "" }: { teamId: string; canPost?: boolean; commitFilter?: boolean; commitSha?: string }) {
  const queryClient = useQueryClient();
  const [sha, setSha] = useState(commitSha);
  const [offset, setOffset] = useState(0);
  const [kind, setKind] = useState<MentorNote["kind"]>("feedback");
  const notes = useQuery({
    queryKey: ["mentor-notes", teamId, sha, offset],
    queryFn: async () => (await api.get<Page<MentorNote>>(`/teams/${teamId}/mentor-notes`, { params: { commit_sha: sha || undefined, limit: LIMIT, offset } })).data,
    placeholderData: keepPreviousData,
  });
  useForgetTeamOnForbidden(teamId, notes.error);
  const post = useMutation({
    mutationFn: (body: { content: string; kind: MentorNote["kind"]; progress_status: MentorNote["progress_status"]; commit_sha: string | null }) => api.post(`/teams/${teamId}/mentor-notes`, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["mentor-notes", teamId] }),
  });

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const fd = new FormData(form);
    const progress_status = kind === "progress" ? (String(fd.get("progress_status")) as MentorNote["progress_status"]) : null;
    post.mutate({ content: String(fd.get("content")).trim(), kind, progress_status, commit_sha: String(fd.get("commit_sha") ?? "") || null }, { onSuccess: () => form.reset() });
  }

  return (
    <div className="space-y-4">
      {canPost && (
        <form onSubmit={submit} className="space-y-2.5 rounded-[18px] border-2 border-dashed border-ink bg-cream p-3.5">
          <div role="group" aria-label="Loại ghi chú" className="flex flex-wrap gap-1.5">
            {(
              [
                ["feedback", "Góp ý", "bg-sun"],
                ["progress", "Ghi nhận tiến độ", "bg-mint"],
              ] as const
            ).map(([k, label, bg]) => (
              <button key={k} type="button" aria-pressed={kind === k} onClick={() => setKind(k)} className={`chip min-h-[38px] cursor-pointer px-3 text-[13px] ${kind === k ? bg : "bg-paper"}`}>
                {label}
              </button>
            ))}
          </div>
          {kind === "progress" && (
            <label className="block max-w-xs text-xs font-bold">
              Tình trạng
              <select name="progress_status" required className="mt-1.5 block min-h-11 w-full rounded-xl border-2 border-ink bg-paper px-3 text-[15px] font-normal">
                {Object.entries(PROGRESS).map(([k, [label]]) => (
                  <option key={k} value={k}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label className="block text-xs font-bold">
            Nội dung (gửi rồi không sửa/xóa được)
            <textarea name="content" required rows={3} maxLength={5000} className={TEXTAREA} />
          </label>
          <CommitSelect teamId={teamId} />
          <button type="submit" className="btn bg-orange font-extrabold" disabled={post.isPending}>
            Gửi
          </button>
          {post.isError && <FormError>{errorMessage(post.error)}</FormError>}
        </form>
      )}
      {commitFilter && (
        <form
          role="search"
          className="flex items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            setSha(String(new FormData(e.currentTarget).get("sha")).trim());
            setOffset(0);
          }}
        >
          <Field label="Lọc theo commit SHA" name="sha" maxLength={40} />
          <button type="submit" className="btn bg-ink text-paper">
            Lọc
          </button>
        </form>
      )}
      {notes.isError && <FormError>{errorMessage(notes.error)}</FormError>}
      {notes.data?.total === 0 && <p className="font-serif italic text-muted">Chưa có ghi chú nào.</p>}
      <ul className="space-y-3">
        {notes.data?.items.map((n) => (
          <li key={n.id} className="rounded-[18px] border-2 border-ink bg-paper px-4 py-3.5">
            <div className="flex flex-wrap items-center gap-2">
              <b className="text-sm">{n.mentor.full_name}</b>
              <span className={`rounded-md border-[1.5px] border-ink px-2 text-[11px] font-extrabold ${n.kind === "progress" ? "bg-mint" : "bg-sun"}`}>{n.kind === "progress" ? "Tiến độ" : "Góp ý"}</span>
              {n.progress_status && <span className={`chip text-xs ${PROGRESS[n.progress_status][1]}`}>{PROGRESS[n.progress_status][0]}</span>}
              <span className="text-xs text-muted">
                <LocalTime iso={n.created_at} />
              </span>
            </div>
            {n.commit_sha && <p className="mt-2 inline-block rounded-lg border-[1.5px] border-dashed border-ink px-2 font-mono text-xs font-semibold">về {n.commit_sha.slice(0, 7)}</p>}
            <p className="mt-2 whitespace-pre-wrap leading-relaxed">{n.content}</p>
          </li>
        ))}
      </ul>
      {notes.data && notes.data.total > LIMIT && <Pager offset={offset} limit={LIMIT} total={notes.data.total} onChange={setOffset} />}
    </div>
  );
}

const Q_STATUS: Record<Question["status"], [string, string]> = { open: ["Chưa trả lời", "bg-orange"], answered: ["Đã trả lời", "bg-sky"], resolved: ["Đã giải quyết", "bg-mint"] };

/**
 * Hỏi/đáp riêng của đội. `member`: hỏi và đánh dấu giải quyết (người hỏi hoặc trưởng nhóm);
 * `mentor`: trả lời; `read`: chỉ xem (BTC/admin).
 */
export function TeamQuestions({ teamId, mode, userId, isLeader }: { teamId: string; mode: "member" | "mentor" | "read"; userId?: string; isLeader?: boolean }) {
  const queryClient = useQueryClient();
  const [offset, setOffset] = useState(0);
  const list = useQuery({
    queryKey: ["questions", teamId, offset],
    queryFn: async () => (await api.get<Page<Question>>(`/teams/${teamId}/questions`, { params: { limit: LIMIT, offset } })).data,
    placeholderData: keepPreviousData,
  });
  useForgetTeamOnForbidden(teamId, list.error);
  const ask = useMutation({
    mutationFn: (body: { title: string; content: string; commit_sha: string | null }) => api.post(`/teams/${teamId}/questions`, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["questions", teamId] }),
  });

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const fd = new FormData(form);
    ask.mutate({ title: String(fd.get("title")).trim(), content: String(fd.get("content")).trim(), commit_sha: String(fd.get("commit_sha") ?? "") || null }, { onSuccess: () => form.reset() });
  }

  return (
    <div className="space-y-4">
      {mode === "member" && (
        <form onSubmit={submit} className="space-y-2.5 rounded-[18px] border-2 border-dashed border-ink bg-cream p-3.5">
          <Field label="Tiêu đề câu hỏi" name="title" required maxLength={150} />
          <label className="block text-sm font-bold">
            Nội dung
            <textarea name="content" required rows={3} maxLength={5000} className={TEXTAREA} />
          </label>
          <CommitSelect teamId={teamId} />
          <p className="text-xs text-muted">Chỉ đội và mentor được phân công đọc được. Nếu đội chưa có mentor, câu hỏi vẫn được lưu và mentor thấy ngay khi được phân công.</p>
          <button type="submit" className={buttonClass("primary")} disabled={ask.isPending}>
            Gửi câu hỏi
          </button>
          {ask.isError && <FormError>{errorMessage(ask.error)}</FormError>}
        </form>
      )}
      {list.isError && <FormError>{errorMessage(list.error)}</FormError>}
      {list.data?.total === 0 && <p className="font-serif italic text-muted">Chưa có câu hỏi nào.</p>}
      <ul className="space-y-3">
        {list.data?.items.map((q) => (
          <QuestionItem key={q.id} q={q} mode={mode} canResolve={mode === "member" && (q.author.id === userId || !!isLeader)} />
        ))}
      </ul>
      {list.data && list.data.total > LIMIT && <Pager offset={offset} limit={LIMIT} total={list.data.total} onChange={setOffset} />}
    </div>
  );
}

function QuestionItem({ q, mode, canResolve }: { q: Question; mode: "member" | "mentor" | "read"; canResolve: boolean }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(q.status === "open" && mode === "mentor");
  const answers = useQuery({
    queryKey: ["answers", q.id],
    // shortcut: 100 câu trả lời đầu của một câu hỏi; thêm phân trang nếu trao đổi dài hơn
    queryFn: async () => (await api.get<Page<Answer>>(`/questions/${q.id}/answers`, { params: { limit: 100 } })).data.items,
    enabled: open,
  });
  const reload = () => Promise.all([queryClient.invalidateQueries({ queryKey: ["answers", q.id] }), queryClient.invalidateQueries({ queryKey: ["questions", q.team_id] })]);
  const reply = useMutation({ mutationFn: (content: string) => api.post(`/questions/${q.id}/answers`, { content }), onSuccess: reload });
  const resolve = useMutation({ mutationFn: () => api.post(`/questions/${q.id}/resolve`), onSuccess: reload });

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    reply.mutate(String(new FormData(form).get("content")).trim(), { onSuccess: () => form.reset() });
  }

  return (
    <li className={`rounded-[18px] border-2 border-ink px-4 py-3.5 ${q.status === "open" ? "bg-cream" : "bg-paper"}`}>
      <div className="flex flex-wrap items-center justify-between gap-2.5">
        <span className="text-[13px] font-bold">
          {q.author.full_name} · <LocalTime iso={q.created_at} />
        </span>
        <span className={`chip ${Q_STATUS[q.status][1]}`}>{Q_STATUS[q.status][0]}</span>
      </div>
      {q.commit_sha && <p className="mt-2 inline-block rounded-lg border-[1.5px] border-dashed border-ink px-2 font-mono text-xs font-semibold">về {q.commit_sha.slice(0, 7)}</p>}
      <p className="mt-2 font-extrabold leading-normal">{q.title}</p>
      <p className="mt-1 whitespace-pre-wrap leading-normal">{q.content}</p>
      <div className="mt-2.5 flex flex-wrap gap-2">
        <button type="button" className="btn min-h-9 bg-paper text-sm" aria-expanded={open} onClick={() => setOpen(!open)}>
          {open ? "Ẩn trả lời" : "Xem trả lời"}
        </button>
        {canResolve && q.status !== "resolved" && (
          <button type="button" className="btn min-h-9 bg-mint text-sm" disabled={resolve.isPending} onClick={() => resolve.mutate()}>
            Đã giải quyết
          </button>
        )}
      </div>
      {resolve.isError && <div className="mt-2"><FormError>{errorMessage(resolve.error)}</FormError></div>}
      {open && (
        <div className="mt-3 space-y-2.5">
          {answers.isError && <FormError>{errorMessage(answers.error)}</FormError>}
          {answers.data?.length === 0 && <p className="text-sm text-muted">Chưa có câu trả lời.</p>}
          {answers.data?.map((a) => (
            <div key={a.id} className="ml-[18px] rounded-r-xl border-l-4 border-leaf bg-paper px-3 py-2.5">
              <p className="text-[13px]">
                <b>{a.mentor.full_name}</b> <span className="text-muted">· <LocalTime iso={a.created_at} /></span>
              </p>
              <p className="mt-1 whitespace-pre-wrap text-sm leading-normal">{a.content}</p>
            </div>
          ))}
          {mode === "mentor" && q.status !== "resolved" && (
            <form onSubmit={submit} className="flex flex-wrap items-end gap-2">
              <label className="flex-[1_1_260px] text-xs font-bold">
                Trả lời (gửi rồi không sửa được)
                <textarea name="content" required rows={2} maxLength={5000} className={TEXTAREA} />
              </label>
              <button type="submit" className="btn bg-ink text-sm text-paper shadow-lip-orange" disabled={reply.isPending}>
                Gửi trả lời
              </button>
              {reply.isError && <div className="w-full"><FormError>{errorMessage(reply.error)}</FormError></div>}
            </form>
          )}
        </div>
      )}
    </li>
  );
}
