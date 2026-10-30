"use client";

import { useEffect, useRef, useState } from "react";
import { COMMITS, CRITERIA, type DiffLine, type FnVerdict, type Severity, type Verdict } from "./mock";

const VERDICT: Record<Verdict, [string, string]> = { good: ["Tốt", "bg-mint"], pass: ["Đạt", "bg-sun"], bad: ["Cần cải thiện", "bg-rose"] };
const SEV: Record<Severity, { label: string; row: string; edge: string }> = {
  high: { label: "Nghiêm trọng", row: "bg-rose", edge: "border-l-orange" },
  medium: { label: "Trung bình", row: "bg-[#FFF1C2]", edge: "border-l-sun" },
  low: { label: "Nhẹ", row: "bg-[#E9F7FF]", edge: "border-l-sky" },
};
const FN: Record<FnVerdict, [string, string]> = { ok: ["Ổn", "bg-mint"], fix: ["Cần sửa", "bg-sun"], danger: ["Nguy hiểm", "bg-orange"] };

// shortcut: rubric mẫu; lấy từ GET /events/{id}/rounds/{round_id}/rubric (Phase 4)
const RUBRIC = [
  { id: "idea", name: "Ý tưởng & tính mới", weight: 25, hint: "Vấn đề rõ ràng, cách giải quyết có điểm khác biệt.", ai: false },
  { id: "tech", name: "Kỹ thuật", weight: 40, hint: "Kiến trúc hợp lý, code chạy được, có test.", ai: true },
  { id: "ux", name: "Trải nghiệm người dùng", weight: 20, hint: "Dễ dùng, giao diện mạch lạc, chạy được trên điện thoại.", ai: false },
  { id: "pitch", name: "Trình bày", weight: 15, hint: "Demo rõ ràng, trả lời câu hỏi tốt.", ai: false },
];

const issuesOf = (lines: DiffLine[]) => lines.filter((l) => l.issue);

// Trung bình có trọng số theo số dòng thay đổi (đặc tả 4.6) để chia nhỏ commit không làm tăng điểm
const lineCount = COMMITS.reduce((s, c) => s + c.add + c.del, 0);
const AI_AVG = (COMMITS.reduce((s, c) => s + c.score * (c.add + c.del), 0) / lineCount).toFixed(1);
const COUNTS = { good: 0, pass: 0, bad: 0 } as Record<Verdict, number>;
COMMITS.forEach((c) => COUNTS[c.v]++);
const CATS = Object.entries(
  COMMITS.flatMap((c) => c.files.flatMap((f) => issuesOf(f.lines))).reduce<Record<string, number>>((m, l) => ({ ...m, [l.issue!.cat]: (m[l.issue!.cat] ?? 0) + 1 }), {}),
).sort((a, b) => b[1] - a[1]);

type Tab = "commits" | "rubric" | "submission";

export function JudgingView() {
  const [tab, setTab] = useState<Tab>("commits");
  return (
    <main className="mx-auto max-w-[1360px] px-6 pb-24 pt-8">
      <div className="flex flex-wrap items-end justify-between gap-5">
        <div>
          <p className="font-serif text-lg italic">Vòng 2 · Chung kết · #web · mentor: [Tên mentor]</p>
          <h1 className="mt-1 text-[clamp(40px,5vw,64px)] font-black leading-none tracking-[-0.045em]">Null Pointer</h1>
        </div>
        <div role="tablist" aria-label="Khu vực chấm" className="flex flex-wrap gap-2">
          {(
            [
              ["commits", "Commit & AI"],
              ["rubric", "Chấm rubric"],
              ["submission", "Bài nộp"],
            ] as const
          ).map(([k, label]) => (
            <button key={k} type="button" role="tab" aria-selected={tab === k} onClick={() => setTab(k)} className={`btn ${tab === k ? "bg-ink text-paper" : "bg-paper"}`}>
              {label}
            </button>
          ))}
        </div>
      </div>
      {tab === "commits" && <CommitsTab />}
      {tab === "rubric" && <RubricTab />}
      {tab === "submission" && <SubmissionTab />}
    </main>
  );
}

function CommitsTab() {
  const [filter, setFilter] = useState<Verdict | "all">("all");
  const [selSha, setSelSha] = useState(COMMITS[0].sha);
  const [fileIdx, setFileIdx] = useState(0);
  const [flags, setFlags] = useState<Record<string, boolean>>({});

  const shown = COMMITS.filter((c) => filter === "all" || c.v === filter);
  const c = shown.find((x) => x.sha === selSha) ?? shown[0] ?? COMMITS[0];
  const file = c.files[Math.min(fileIdx, c.files.length - 1)];
  const select = (sha: string) => {
    setSelSha(sha);
    setFileIdx(0);
  };

  return (
    <div className="mt-7 flex flex-wrap items-start gap-6">
      <section aria-labelledby="clist" className="sketch min-w-0 flex-[1_1_300px] overflow-hidden rounded-[22px] shadow-sketch-sm">
        <div className="border-b-2 border-dashed border-line p-4 pb-3">
          <h2 id="clist" className="text-xl font-black">
            Commit · {COMMITS.length}
          </h2>
          <div role="group" aria-label="Lọc theo nhãn AI" className="mt-2.5 flex flex-wrap gap-1.5">
            {(["all", "good", "pass", "bad"] as const).map((k) => (
              <button
                key={k}
                type="button"
                aria-pressed={filter === k}
                onClick={() => setFilter(k)}
                className={`chip min-h-9 cursor-pointer ${filter === k ? (k === "all" ? "bg-cream" : VERDICT[k][1]) : "bg-paper"}`}
              >
                {k === "all" ? "Tất cả" : VERDICT[k][0]}
              </button>
            ))}
          </div>
        </div>
        <ul>
          {shown.map((x) => {
            const on = x.sha === c.sha;
            return (
              <li key={x.sha}>
                <button
                  type="button"
                  aria-pressed={on}
                  onClick={() => select(x.sha)}
                  className={`flex w-full flex-col gap-1.5 border-b-[1.5px] border-l-[6px] border-b-line px-4 py-3.5 text-left transition-colors hover:bg-cream ${on ? "border-l-orange bg-cream" : "border-l-transparent bg-paper"}`}
                >
                  <span className="flex items-center justify-between gap-2">
                    <span className="font-mono text-[13px] font-extrabold">{x.sha}</span>
                    <span className={`chip ${VERDICT[x.v][1]}`}>
                      {VERDICT[x.v][0]} · {x.score}
                    </span>
                  </span>
                  <span className="text-sm font-bold leading-snug">{x.msg}</span>
                  <span className="text-xs text-muted">
                    {x.author} · thấy lúc {x.seen} · <span className="font-bold text-plus">+{x.add}</span> <span className="font-bold text-minus">−{x.del}</span>
                  </span>
                  {x.critical && <span className="chip self-start rounded-md bg-orange text-[11px]">✕ Lỗi nghiêm trọng</span>}
                  {x.injection && <span className="chip self-start rounded-md border-dashed bg-sun text-[11px]">⚠ Nghi prompt injection</span>}
                </button>
              </li>
            );
          })}
        </ul>
      </section>

      <section aria-labelledby="cdetail" className="flex min-w-0 flex-[2.4_1_560px] flex-col gap-5">
        <div className="sketch rounded-[22px] p-5 shadow-sketch-sm">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="font-mono text-[13px] font-semibold text-muted">
                {c.sha} · {c.author} · thấy lúc {c.seen}
              </p>
              <h2 id="cdetail" className="mt-1 text-2xl font-black tracking-tight">
                {c.msg}
              </h2>
            </div>
            <div className="text-right">
              <span className={`chip px-3 py-1 text-sm ${VERDICT[c.v][1]}`}>{VERDICT[c.v][0]}</span>
              <p className="mt-1.5 font-mono text-[32px] font-extrabold leading-none">
                {c.score}
                <span className="text-[15px] text-muted">/10</span>
              </p>
            </div>
          </div>
          <p className="mt-3 rounded-[14px] bg-warm px-3.5 py-3 leading-relaxed">{c.summary}</p>
          <ul aria-label="Điểm theo tiêu chí" className="mt-4 grid gap-x-5 gap-y-2.5 sm:grid-cols-2 lg:grid-cols-3">
            {CRITERIA.map(([k, label]) => {
              const v = c.crit[k];
              return (
                <li key={k}>
                  <div className="flex justify-between text-[13px] font-bold">
                    <span>{label}</span>
                    <span className="font-mono">{v.toFixed(1)}</span>
                  </div>
                  <div aria-hidden className="mt-1 h-2.5 overflow-hidden rounded-full border-[1.5px] border-ink">
                    <div className={`h-full ${v >= 8 ? "bg-leaf" : v >= 5 ? "bg-sun" : "bg-orange"}`} style={{ width: `${v * 10}%` }} />
                  </div>
                </li>
              );
            })}
          </ul>
        </div>

        <div className="sketch flex flex-wrap overflow-hidden rounded-[22px] shadow-sketch-sm">
          <nav aria-label="File thay đổi" className="min-w-0 flex-[1_1_220px] border-r-2 border-dashed border-line p-3.5">
            <p className="mb-2.5 text-[15px] font-black">File thay đổi · {c.files.length}</p>
            <ul className="flex flex-col gap-1.5">
              {c.files.map((f, i) => {
                const iss = issuesOf(f.lines);
                const worst = iss.some((l) => l.issue!.sev === "high") ? "high" : iss.length ? "warn" : "ok";
                const on = f === file;
                return (
                  <li key={f.path}>
                    <button
                      type="button"
                      aria-pressed={on}
                      onClick={() => setFileIdx(i)}
                      className={`flex min-h-11 w-full items-center gap-2 rounded-xl border-2 px-2.5 py-2 text-left transition-colors hover:bg-cream ${on ? "border-ink bg-cream" : "border-line bg-paper"}`}
                    >
                      <span aria-hidden className={`grid size-[22px] flex-none place-items-center rounded-full border-[1.5px] border-ink text-xs font-black ${worst === "high" ? "bg-orange" : worst === "warn" ? "bg-sun" : "bg-mint"}`}>
                        {worst === "high" ? "✕" : worst === "warn" ? "!" : "✓"}
                      </span>
                      <span className="min-w-0 flex-1 break-all font-mono text-xs font-semibold">{f.path}</span>
                      <span className="whitespace-nowrap text-[11px] font-extrabold">{iss.length ? `${iss.length} vấn đề` : "ổn"}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </nav>
          <div className="min-w-0 flex-[3_1_420px]">
            <div className="flex flex-wrap justify-between gap-2.5 border-b-2 border-dashed border-line px-3.5 py-2.5 font-mono text-[13px] font-extrabold">
              <span>{file.path}</span>
              <span className="font-semibold text-muted">{issuesOf(file.lines).length} vấn đề</span>
            </div>
            <div className="overflow-x-auto">
              <div role="table" aria-label={`Diff của ${file.path}`} className="min-w-[460px] font-mono text-[13px] leading-relaxed">
                {file.lines.map((l, i) => {
                  const s = l.issue && SEV[l.issue.sev];
                  return (
                    <div key={i}>
                      <div
                        role="row"
                        className={`grid grid-cols-[46px_22px_minmax(0,1fr)] border-l-[5px] ${s ? `${s.row} ${s.edge}` : `border-l-transparent ${l.sign === "+" ? "bg-[#F1FBEA]" : l.sign === "-" ? "bg-[#FFF0F2]" : "bg-paper"}`}`}
                      >
                        <span role="cell" className="px-2 py-px text-right text-[#777]">
                          {l.n}
                        </span>
                        <span role="cell" className={`px-1 py-px font-extrabold ${l.sign === "+" ? "text-plus" : "text-minus"}`}>
                          {l.sign.trim()}
                        </span>
                        <span role="cell" className="whitespace-pre py-px pl-1 pr-2.5">
                          {l.code}
                        </span>
                      </div>
                      {l.issue && s && (
                        <div role="note" className={`mb-2.5 ml-[72px] mr-3 mt-1.5 rounded-[14px] border-2 border-ink px-3 py-2.5 font-sans shadow-[3px_3px_0_var(--ink)] ${s.row}`}>
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="rounded-md border-[1.5px] border-ink bg-paper px-2 text-[11px] font-extrabold">{s.label}</span>
                            <span className="text-xs font-extrabold">{l.issue.cat}</span>
                            <span className="text-xs text-muted">· AI</span>
                          </div>
                          <p className="mt-1.5 text-sm font-semibold leading-normal">{l.issue.msg}</p>
                          <p className="mt-1 text-[13px] leading-normal">
                            <b>Gợi ý:</b> {l.issue.sug}
                          </p>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>

        <div className="sketch rounded-[22px] p-[18px] shadow-sketch-sm">
          <h3 className="text-lg font-black">Đánh giá theo function</h3>
          <div className="mt-2.5 overflow-x-auto">
            <table className="w-full min-w-[560px] border-collapse text-sm">
              <thead>
                <tr className="border-b-2 border-ink text-left">
                  <th scope="col" className="py-2 pr-2">Function</th>
                  <th scope="col" className="p-2">Vị trí</th>
                  <th scope="col" className="p-2">Đánh giá</th>
                  <th scope="col" className="py-2 pl-2">Nhận xét của AI</th>
                </tr>
              </thead>
              <tbody>
                {c.functions.map((fn) => (
                  <tr key={fn.name} className="border-b-[1.5px] border-dashed border-line">
                    <td className="py-2.5 pr-2 font-mono font-extrabold">{fn.name}</td>
                    <td className="p-2 font-mono text-xs text-muted">{fn.where}</td>
                    <td className="p-2">
                      <span className={`chip ${FN[fn.v][1]}`}>{FN[fn.v][0]}</span>
                    </td>
                    <td className="py-2.5 pl-2 leading-normal">{fn.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-xs text-muted">Nguồn: model [tên-model] · prompt v3 · chỉ để tham khảo, không cộng vào điểm rubric.</p>
        </div>
      </section>

      <aside className="flex min-w-0 flex-[1_1_280px] flex-col gap-5">
        <section aria-labelledby="sum" className="rounded-[22px] border-2 border-ink bg-cream p-[18px] shadow-sketch-sm">
          <h2 id="sum" className="text-lg font-black">
            Tổng quan AI của đội
          </h2>
          <p className="mt-2.5 font-mono text-[44px] font-extrabold leading-none">
            {AI_AVG}
            <span className="text-base text-muted">/10</span>
          </p>
          <p className="mt-1 text-xs text-muted">trung bình có trọng số theo số dòng thay đổi</p>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {(["good", "pass", "bad"] as const).map((k) => (
              <span key={k} className={`chip ${VERDICT[k][1]}`}>
                {VERDICT[k][0]} · {COUNTS[k]}
              </span>
            ))}
          </div>
          <p className="mb-1.5 mt-4 text-sm font-extrabold">Lỗi hay gặp</p>
          <ul className="flex flex-col gap-1.5">
            {CATS.slice(0, 5).map(([cat, n]) => (
              <li key={cat} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-2 text-[13px]">
                <span>
                  {cat}
                  <span aria-hidden className="mt-0.5 block h-1.5 rounded-full bg-ink" style={{ width: `${(n / CATS[0][1]) * 100}%` }} />
                </span>
                <b className="font-mono">{n}</b>
              </li>
            ))}
          </ul>
        </section>

        <section aria-labelledby="flag" className="rounded-[22px] border-2 border-dashed border-ink bg-paper p-[18px]">
          <h2 id="flag" className="text-lg font-black">
            Commit {c.sha}
          </h2>
          <label className="mt-3 flex flex-col gap-1.5 text-sm font-bold">
            Ghi chú riêng của giám khảo
            <textarea key={c.sha} rows={3} placeholder="Chỉ bạn và BTC thấy…" className="resize-y rounded-xl border-2 border-ink px-3 py-2.5 text-[15px] font-normal" />
          </label>
          {flags[c.sha] && (
            <p role="status" className="mt-3 rounded-xl border-2 border-ink bg-sun px-3 py-2 text-[13px] font-extrabold">
              Đã đánh dấu: đánh giá AI cho commit này sai.
            </p>
          )}
          <button type="button" onClick={() => setFlags((f) => ({ ...f, [c.sha]: !f[c.sha] }))} className="btn mt-3 bg-paper text-[13px]">
            {flags[c.sha] ? "Bỏ đánh dấu" : "Đánh dấu AI đánh giá sai"}
          </button>
        </section>
      </aside>
    </div>
  );
}

function RubricTab() {
  const [scores, setScores] = useState<Record<string, number>>({ idea: 8, tech: 7.5, ux: 8.5, pitch: 7 });
  const [phase, setPhase] = useState<"draft" | "confirming" | "locked">("draft");
  const [saved, setSaved] = useState(true);
  const saveT = useRef<ReturnType<typeof setTimeout>>(undefined);
  useEffect(() => () => clearTimeout(saveT.current), []);

  const locked = phase === "locked";
  const total = RUBRIC.reduce((s, r) => s + (scores[r.id] / 10) * r.weight, 0).toFixed(1);
  // shortcut: giả lập lưu nháp; gọi PUT /assignments/{id}/scores (Phase 4)
  const change = (id: string, v: number) => {
    setScores((s) => ({ ...s, [id]: v }));
    setSaved(false);
    clearTimeout(saveT.current);
    saveT.current = setTimeout(() => setSaved(true), 700);
  };

  return (
    <section aria-labelledby="rubric-title" className="sketch mt-7 max-w-[860px] rounded-[26px] p-7 shadow-[8px_8px_0_var(--ink)]">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="rubric-title" className="text-[28px] font-black tracking-tight">
          Rubric chính thức
        </h2>
        <span role="status" className="rounded-full border-[1.5px] border-dashed border-ink px-3 py-1 text-[13px] font-bold">
          {locked ? "Đã khóa" : saved ? "Đã lưu nháp" : "Đang lưu…"}
        </span>
      </div>
      <ul className="mt-5 flex flex-col gap-4">
        {RUBRIC.map((r) => (
          <li key={r.id} className={`rounded-[18px] border-2 border-ink p-[18px] ${r.ai ? "bg-cream" : "bg-paper"}`}>
            <div className="flex flex-wrap items-baseline justify-between gap-3">
              <label htmlFor={r.id} className="text-[17px] font-extrabold">
                {r.name} <span className="text-[13px] font-semibold text-muted">· trọng số {r.weight}%</span>
              </label>
              <span className="font-mono text-[26px] font-extrabold">
                {scores[r.id]}
                <span className="text-[15px] text-muted">/10</span>
              </span>
            </div>
            <p className="mb-2 mt-1 text-[13px] text-muted">{r.hint}</p>
            <input
              id={r.id}
              type="range"
              min={0}
              max={10}
              step={0.5}
              value={scores[r.id]}
              disabled={locked}
              onChange={(e) => change(r.id, Number(e.target.value))}
              className="h-7 w-full cursor-pointer accent-orange"
            />
            {r.ai && (
              <p className="mt-2 inline-block rounded-[10px] border-[1.5px] border-dashed border-ink bg-warm px-2.5 py-0.5 text-xs font-bold">
                Tham khảo AI: {AI_AVG}/10 trung bình commit · {COUNTS.bad} commit lỗi nghiêm trọng
              </p>
            )}
          </li>
        ))}
      </ul>
      <label className="mt-[18px] flex flex-col gap-1.5 font-extrabold">
        Nhận xét gửi đội (hiện sau khi công bố)
        <textarea rows={3} placeholder="Điểm mạnh, điểm cần cải thiện…" className="resize-y rounded-[14px] border-2 border-ink px-3.5 py-3 text-base font-normal" />
      </label>
      <div className="mt-6 flex flex-wrap items-center justify-between gap-4 border-t-2 border-dashed border-line pt-5">
        <div>
          <p className="text-sm font-bold">Tổng có trọng số</p>
          <p className="font-mono text-[52px] font-extrabold leading-none">
            {total}
            <span className="text-xl text-muted">/100</span>
          </p>
        </div>
        {phase === "draft" && (
          <button type="button" onClick={() => setPhase("confirming")} className="btn h-[54px] bg-ink px-6 text-base font-extrabold text-paper shadow-lip-orange">
            Xác nhận điểm
          </button>
        )}
        {phase === "confirming" && (
          <div role="alertdialog" aria-label="Xác nhận điểm" className="flex flex-[1_1_100%] flex-wrap items-center justify-between gap-3 rounded-[18px] border-2 border-ink bg-cream p-4">
            <p className="font-bold">Sau khi xác nhận, chỉ ban tổ chức mở lại được. Chắc chứ?</p>
            <div className="flex gap-2.5">
              <button type="button" onClick={() => setPhase("draft")} className="btn bg-paper">
                Xem lại
              </button>
              <button type="button" onClick={() => setPhase("locked")} className="btn bg-orange font-extrabold">
                Xác nhận {total} điểm
              </button>
            </div>
          </div>
        )}
        {locked && (
          <p role="status" className="-rotate-[1.5deg] rounded-full border-2 border-ink bg-mint px-4 py-2.5 font-extrabold">
            ✓ Đã xác nhận · chờ ban tổ chức khóa điểm
          </p>
        )}
      </div>
    </section>
  );
}

function SubmissionTab() {
  const links = [
    { label: "Repo GitHub", meta: "github.com/[owner]/[repo]", bg: "bg-paper" },
    { label: "Demo trực tuyến", meta: "[demo-url]", bg: "bg-paper" },
    { label: "Slide thuyết trình", meta: "PDF · 4.2 MB", bg: "bg-sky" },
    { label: "Video demo", meta: "3:12", bg: "bg-rose" },
  ];
  const versions = ["Hôm qua 21:10 (được chấm)", "Hôm qua 16:42", "Hôm qua 10:05", "Hôm kia 23:58", "Hôm kia 20:11"];
  return (
    <div className="mt-7 flex flex-wrap items-start gap-6">
      <section aria-labelledby="sub-title" className="sketch min-w-0 flex-[2_1_480px] p-6">
        <h2 id="sub-title" className="text-2xl font-black">
          Bài nộp · v5 <span className="chip ml-1 bg-sun align-middle text-[13px]">bản cuối trước hạn</span>
        </h2>
        <ul className="mt-4 flex flex-col gap-2.5">
          {links.map((l) => (
            <li key={l.label}>
              <a href="#open" className={`flex min-h-[54px] items-center gap-3 rounded-[14px] border-2 border-ink px-4 ${l.bg}`}>
                <span className="flex-1 font-extrabold">{l.label}</span>
                <span className="font-mono text-xs text-muted">{l.meta}</span>
              </a>
            </li>
          ))}
        </ul>
        <p className="mt-4 leading-relaxed">
          <b>Mô tả của đội:</b> [Mô tả ngắn sản phẩm do đội nhập khi nộp bài.]
        </p>
      </section>
      <section aria-labelledby="ver-title" className="sketch min-w-0 flex-[1_1_280px] p-6">
        <h2 id="ver-title" className="text-xl font-black">
          Lịch sử phiên bản
        </h2>
        <ul className="mt-3">
          {versions.map((at, i) => (
            <li key={at} className="flex justify-between gap-2.5 border-b-[1.5px] border-dashed border-line py-2.5 text-sm">
              <b className="font-mono">v{versions.length - i}</b>
              <span className="flex-1 text-muted">{at}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
