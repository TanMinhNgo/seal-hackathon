"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { TEAMS, type MentorNote, type NoteKind } from "./mock";

const KIND: Record<NoteKind, [string, string]> = {
  feedback: ["Góp ý", "bg-sun"],
  answer: ["Trả lời", "bg-sky"],
  progress: ["Ghi nhận tiến độ", "bg-mint"],
};

export function MentorView() {
  // State theo từng đội để chuyển qua lại không mất dữ liệu đang nhập
  const [teamIdx, setTeamIdx] = useState(0);
  const [questions, setQuestions] = useState(() => TEAMS.map((t) => t.questions));
  const [notes, setNotes] = useState(() => TEAMS.map((t) => t.notes));
  const [checks, setChecks] = useState(() => TEAMS.map((t) => t.checks));
  const [qDrafts, setQDrafts] = useState<Record<string, string>>({});
  const [kind, setKind] = useState<NoteKind>("feedback");
  const [anchor, setAnchor] = useState("");
  const [draft, setDraft] = useState("");
  const [fresh, setFresh] = useState("");

  const t = TEAMS[teamIdx];
  const maxBar = Math.max(1, ...t.bars);
  const doneCount = checks[teamIdx].filter((c) => c.done).length;

  const pickTeam = (i: number) => {
    setTeamIdx(i);
    setAnchor("");
  };

  // shortcut: chỉ cập nhật state cục bộ; gọi API trả lời câu hỏi (bổ sung hợp đồng Phase 4)
  const answer = (id: string) => {
    const text = (qDrafts[id] ?? "").trim() || "Đã trao đổi trực tiếp với đội.";
    setQuestions((all) => all.map((qs, i) => (i === teamIdx ? qs.map((q) => (q.id === id ? { ...q, answer: text } : q)) : qs)));
    setQDrafts((d) => ({ ...d, [id]: "" }));
  };

  // shortcut: chỉ cập nhật state cục bộ; gọi POST /teams/{id}/mentor-notes (Phase 4)
  const post = (e: FormEvent) => {
    e.preventDefault();
    const text = draft.trim();
    if (!text) return;
    const note: MentorNote = { id: `n${Date.now()}`, who: "[Tên mentor]", kind, anchor, text, time: "Vừa xong", replies: [] };
    setNotes((all) => all.map((ns, i) => (i === teamIdx ? [note, ...ns] : ns)));
    setFresh(note.id);
    setDraft("");
  };

  const toggleCheck = (k: number) => setChecks((all) => all.map((cs, i) => (i === teamIdx ? cs.map((c, j) => (j === k ? { ...c, done: !c.done } : c)) : cs)));

  return (
    <main className="mx-auto max-w-[1360px] px-6 pb-24 pt-8">
      <p className="font-serif text-lg italic">Xin chào, [Tên mentor]</p>
      <h1 className="mt-1 text-[clamp(38px,4.6vw,58px)] font-black leading-none tracking-[-0.045em]">Đồng hành cùng các đội.</h1>

      <div className="mt-7 flex flex-wrap items-start gap-6">
        <section aria-labelledby="teams" className="flex min-w-0 flex-[1_1_280px] flex-col gap-3">
          <h2 id="teams" className="text-lg font-black">
            Đội được phân công · {TEAMS.length}
          </h2>
          {TEAMS.map((x, i) => {
            const open = questions[i].filter((q) => !q.answer).length;
            const on = i === teamIdx;
            return (
              <button
                key={x.name}
                type="button"
                aria-pressed={on}
                onClick={() => pickTeam(i)}
                className={`flex flex-col gap-2 rounded-[20px] border-2 border-ink p-4 text-left transition-colors hover:bg-cream ${on ? "bg-cream shadow-sketch-sm" : "bg-paper"}`}
              >
                <span className="flex items-center justify-between gap-2">
                  <span className="text-[19px] font-black">{x.name}</span>
                  {open > 0 && <span className="chip bg-orange">{open} câu hỏi</span>}
                </span>
                <span className="text-[13px] font-semibold">
                  #{x.track} · commit cuối {x.lastCommit}
                </span>
                {x.alert && <span className={`chip self-start rounded-lg ${x.alert.bg}`}>{x.alert.text}</span>}
              </button>
            );
          })}
        </section>

        <section aria-labelledby="team-name" className="flex min-w-0 flex-[2.4_1_560px] flex-col gap-[22px]">
          <div className="sketch p-[22px]">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="min-w-0">
                <h2 id="team-name" className="text-[32px] font-black tracking-tight">
                  {t.name}
                </h2>
                <p className="mt-1 text-sm font-semibold">
                  #{t.track} · <a href="#repo" className="font-mono text-[13px] underline">github.com/[owner]/{t.repo}</a>
                </p>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {t.members.map((m) => (
                    <span key={m.name} className="inline-flex items-center gap-1.5 rounded-full border-[1.5px] border-ink py-0.5 pl-0.5 pr-2.5 text-[13px] font-semibold">
                      <span aria-hidden className={`grid size-6 place-items-center rounded-full border-[1.5px] border-ink text-[11px] font-extrabold ${m.bg}`}>
                        {m.name.split(" ").pop()![0]}
                      </span>
                      {m.name}
                    </span>
                  ))}
                </div>
              </div>
              <div className="flex gap-2.5">
                <div className="rounded-2xl border-2 border-ink bg-cream px-3.5 py-2.5 text-center">
                  <p className="font-mono text-[26px] font-extrabold">{t.commits}</p>
                  <p className="text-xs font-semibold">commit</p>
                </div>
                <div className="rounded-2xl border-2 border-ink bg-paper px-3.5 py-2.5 text-center">
                  <p className="font-mono text-[26px] font-extrabold">{t.ai}</p>
                  <p className="text-xs font-semibold">AI /10 · tham khảo</p>
                </div>
              </div>
            </div>
            <p className="mb-1.5 mt-[18px] text-[13px] font-extrabold">Commit theo giờ (12 giờ qua)</p>
            <div
              role="img"
              aria-label={`Số commit theo giờ: ${t.bars.join(", ")}`}
              className="grid h-20 grid-cols-12 items-end gap-1.5 border-b-2 border-ink pb-0.5"
            >
              {t.bars.map((n, k) => (
                <div
                  key={k}
                  className={`min-h-[3px] rounded-t-md border-[1.5px] border-b-0 border-ink ${k === t.bars.length - 1 ? "bg-orange" : n === 0 ? "bg-paper" : "bg-sun"}`}
                  style={{ height: `${(n / maxBar) * 100}%` }}
                />
              ))}
            </div>
            <div className="mt-1 flex justify-between font-mono text-[11px] text-muted">
              <span>-12h</span>
              <span>bây giờ</span>
            </div>
          </div>

          <div className="sketch p-[22px]">
            <h3 className="text-[22px] font-black">Câu hỏi từ đội</h3>
            {questions[teamIdx].length === 0 && <p className="mt-3 text-sm text-muted">Đội chưa có câu hỏi nào.</p>}
            <ul className="mt-3.5 flex flex-col gap-3">
              {questions[teamIdx].map((q) => (
                <li key={q.id} className={`rounded-[18px] border-2 border-ink px-4 py-3.5 ${q.answer ? "bg-paper" : "bg-cream"}`}>
                  <div className="flex flex-wrap items-center justify-between gap-2.5">
                    <span className="text-[13px] font-bold">
                      {q.from} · {q.time}
                    </span>
                    <span className={`chip ${q.answer ? "bg-mint" : "bg-orange"}`}>{q.answer ? "Đã giải quyết" : "Chưa trả lời"}</span>
                  </div>
                  <p className="mt-2 font-bold leading-normal">{q.text}</p>
                  {q.answer ? (
                    <p className="mt-2.5 rounded-r-xl border-l-4 border-leaf bg-paper px-3 py-2.5 text-sm leading-normal">
                      <b>Bạn:</b> {q.answer}
                    </p>
                  ) : (
                    <div className="mt-2.5 flex flex-wrap gap-2">
                      <label className="flex flex-[1_1_260px] flex-col gap-1 text-xs font-bold">
                        Trả lời
                        <textarea
                          rows={2}
                          value={qDrafts[q.id] ?? ""}
                          onChange={(e) => setQDrafts((d) => ({ ...d, [q.id]: e.target.value }))}
                          placeholder="Gợi ý hướng giải quyết…"
                          className="resize-y rounded-xl border-2 border-ink bg-paper px-2.5 py-2 text-[15px] font-normal"
                        />
                      </label>
                      <button type="button" onClick={() => answer(q.id)} className="btn self-end bg-ink text-sm text-paper shadow-lip-orange">
                        Gửi &amp; đã giải quyết
                      </button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </div>

          <div className="sketch p-[22px]">
            <h3 className="text-[22px] font-black">Góp ý cho đội</h3>
            <form onSubmit={post} className="mt-3.5 flex flex-col gap-2.5 rounded-[18px] border-2 border-dashed border-ink bg-cream p-3.5">
              <div role="group" aria-label="Loại góp ý" className="flex flex-wrap gap-1.5">
                {(Object.keys(KIND) as NoteKind[]).map((k) => (
                  <button key={k} type="button" aria-pressed={kind === k} onClick={() => setKind(k)} className={`chip min-h-[38px] cursor-pointer px-3 text-[13px] ${kind === k ? KIND[k][1] : "bg-paper"}`}>
                    {KIND[k][0]}
                  </button>
                ))}
              </div>
              <div role="group" aria-label="Gắn góp ý vào commit (tùy chọn)" className="flex flex-col gap-1">
                <span className="text-xs font-bold">Gắn vào commit (tùy chọn)</span>
                <div className="flex flex-wrap gap-1.5">
                  {["", ...t.recent.map((c) => c.sha)].map((sha) => (
                    <button
                      key={sha || "none"}
                      type="button"
                      aria-pressed={anchor === sha}
                      onClick={() => setAnchor(sha)}
                      className={`min-h-9 rounded-[10px] border-[1.5px] border-dashed border-ink px-2.5 font-mono text-xs font-semibold ${anchor === sha ? "bg-sun" : "bg-paper"}`}
                    >
                      {sha || "Không gắn"}
                    </button>
                  ))}
                </div>
              </div>
              <label className="flex flex-col gap-1 text-xs font-bold">
                Nội dung
                <textarea
                  rows={3}
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  placeholder="Viết góp ý cụ thể, có thể kèm đường dẫn tài liệu…"
                  className="resize-y rounded-xl border-2 border-ink bg-paper px-3 py-2.5 text-[15px] font-normal"
                />
              </label>
              <button type="submit" className="btn self-end bg-orange font-extrabold">
                Gửi góp ý
              </button>
            </form>
            <ul className="mt-[18px] flex flex-col gap-3.5" aria-live="polite">
              {notes[teamIdx].map((n) => (
                <li key={n.id} className={`rounded-[18px] border-2 border-ink bg-paper px-4 py-3.5 ${n.id === fresh ? "pop-in" : ""}`}>
                  <div className="flex flex-wrap items-center gap-2">
                    <span aria-hidden className="grid size-7 place-items-center rounded-full border-[1.5px] border-ink bg-mint text-xs font-extrabold">
                      M
                    </span>
                    <b className="text-sm">{n.who}</b>
                    <span className={`rounded-md border-[1.5px] border-ink px-2 text-[11px] font-extrabold ${KIND[n.kind][1]}`}>{KIND[n.kind][0]}</span>
                    <span className="text-xs text-muted">{n.time}</span>
                  </div>
                  {n.anchor && <p className="mt-2 inline-block rounded-lg border-[1.5px] border-dashed border-ink px-2 font-mono text-xs font-semibold">về {n.anchor}</p>}
                  <p className="mt-2 leading-relaxed">{n.text}</p>
                  {n.replies.map((r) => (
                    <div key={r.time + r.who} className="ml-[22px] mt-2.5 rounded-r-xl border-l-[3px] border-ink bg-warm px-3 py-2.5">
                      <p className="text-[13px]">
                        <b>{r.who}</b> <span className="text-muted">· {r.time}</span>
                      </p>
                      <p className="mt-1 text-sm leading-normal">{r.text}</p>
                    </div>
                  ))}
                </li>
              ))}
            </ul>
          </div>
        </section>

        <aside className="flex min-w-0 flex-[1_1_280px] flex-col gap-[22px]">
          <section aria-labelledby="progress" className="-rotate-[0.6deg] rounded-[22px] border-2 border-ink bg-mint p-5 shadow-sketch-sm">
            <h2 id="progress" className="text-[19px] font-black">
              Ghi nhận tiến độ
            </h2>
            <p className="mt-1 text-[13px] font-semibold">
              {doneCount}/{checks[teamIdx].length} mốc đã đạt
            </p>
            <ul className="mt-3 flex flex-col gap-2">
              {checks[teamIdx].map((c, k) => (
                <li key={c.label}>
                  <label className="flex min-h-11 cursor-pointer items-center gap-2.5 rounded-xl border-2 border-ink bg-paper px-3 text-sm font-bold">
                    <input type="checkbox" checked={c.done} onChange={() => toggleCheck(k)} className="size-5 accent-ink" />
                    <span className={c.done ? "line-through" : ""}>{c.label}</span>
                  </label>
                </li>
              ))}
            </ul>
          </section>

          <section aria-labelledby="recent" className="sketch rounded-[22px] p-5 shadow-sketch-sm">
            <h2 id="recent" className="text-[19px] font-black">
              Commit gần đây
            </h2>
            <ul className="mt-3">
              {t.recent.map((c) => (
                <li key={c.sha} className="border-b-[1.5px] border-dashed border-line py-2.5">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-xs font-extrabold">
                      {c.sha} · {c.time}
                    </span>
                    <span className={`chip text-[11px] ${c.bg}`}>{c.v}</span>
                  </div>
                  <p className="mt-1 text-sm font-semibold">{c.msg}</p>
                  {c.issue && <p className="mt-1 text-xs text-muted">AI: {c.issue}</p>}
                </li>
              ))}
            </ul>
            <Link href="/judge" className="mt-3 inline-block text-sm font-bold underline">
              Xem chi tiết AI review →
            </Link>
          </section>
        </aside>
      </div>
    </main>
  );
}
