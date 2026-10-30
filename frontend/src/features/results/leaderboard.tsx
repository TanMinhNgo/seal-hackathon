"use client";

import { useState } from "react";
import { Doodle } from "@/components/ui/doodle";

// shortcut: dữ liệu mẫu; thay bằng GET /events/{id}/rounds/{round_id}/leaderboard (Phase 4)
const TEAMS = [
  { name: "Null Pointer", track: "web", members: 4, c1: 27.5, c2: 36.8, c3: 18.9, prev: 2 },
  { name: "Bug Hunters", track: "ai", members: 3, c1: 26.0, c2: 37.2, c3: 18.0, prev: 1 },
  { name: "Commit Sớm", track: "edtech", members: 4, c1: 25.4, c2: 34.1, c3: 19.5, prev: 5 },
  { name: "Team Trà Sữa", track: "web", members: 2, c1: 24.0, c2: 33.0, c3: 17.6, prev: 3 },
  { name: "Async Await", track: "ai", members: 4, c1: 23.8, c2: 33.2, c3: 17.6, prev: 4 },
  { name: "Merge Conflict", track: "edtech", members: 3, c1: 22.1, c2: 31.0, c3: 16.2, prev: 7 },
  { name: "404 Sleep Not Found", track: "web", members: 4, c1: 20.5, c2: 30.4, c3: 15.8, prev: 6 },
];

const ROUNDS = [
  { id: 1, label: "Vòng 1 · Prototype", factor: 0.94 },
  { id: 2, label: "Vòng 2 · Chung kết", factor: 1 },
];
const TRACKS = ["all", "web", "ai", "edtech"];
const PODIUM = [
  { bg: "bg-sun", tilt: "-rotate-[1.5deg]", h: "md:min-h-[300px]", prize: "Giải Nhất" },
  { bg: "bg-sky", tilt: "rotate-1", h: "md:min-h-[260px]", prize: "Giải Nhì" },
  { bg: "bg-rose", tilt: "-rotate-[0.6deg]", h: "md:min-h-[240px]", prize: "Giải Ba" },
];

export function Leaderboard() {
  const [round, setRound] = useState(2);
  const [track, setTrack] = useState("all");
  const factor = ROUNDS.find((r) => r.id === round)!.factor;

  const rows = TEAMS.map((t) => ({ ...t, total: Math.round((t.c1 + t.c2 + t.c3) * factor * 10) / 10 }))
    // Đồng điểm: so tiêu chí trọng số lớn nhất (Kỹ thuật)
    .sort((a, b) => b.total - a.total || b.c2 - a.c2)
    .filter((t) => track === "all" || t.track === track)
    .map((t, i, list) => ({ ...t, rank: i + 1, tied: list.some((o) => o !== t && o.total === t.total), move: t.prev - (i + 1) }));

  return (
    <main className="mx-auto max-w-6xl px-6 pb-24 pt-14">
      <p className="font-serif text-xl italic">[Tên cuộc thi] · đã công bố</p>
      <div className="mt-2 flex flex-wrap items-end justify-between gap-6">
        <h1 className="text-[clamp(48px,7vw,96px)] font-black leading-[0.95] tracking-[-0.05em]">
          Bảng
          <br />
          xếp hạng.
        </h1>
        <div className="flex flex-col items-start gap-3 sm:items-end">
          <div role="group" aria-label="Chọn vòng" className="flex flex-wrap gap-2">
            {ROUNDS.map((r) => (
              <button key={r.id} type="button" aria-pressed={round === r.id} onClick={() => setRound(r.id)} className={`btn text-sm ${round === r.id ? "bg-ink text-paper" : "bg-paper"}`}>
                {r.label}
              </button>
            ))}
          </div>
          <div role="group" aria-label="Lọc theo track" className="flex flex-wrap gap-1.5">
            {TRACKS.map((t) => (
              <button
                key={t}
                type="button"
                aria-pressed={track === t}
                onClick={() => setTrack(t)}
                className={`min-h-11 rounded-[10px] border-[1.5px] border-dashed border-ink px-3.5 text-sm font-semibold ${track === t ? "bg-sun" : "bg-paper"}`}
              >
                #{t === "all" ? "tất-cả" : t}
              </button>
            ))}
          </div>
        </div>
      </div>

      <section aria-label="Top 3" className="mt-14 grid items-end gap-7 md:grid-cols-3">
        {rows.slice(0, 3).map((r, i) => (
          <article key={r.name} className={`flex flex-col justify-between gap-5 rounded-[26px] border-2 border-ink p-[26px] shadow-sketch ${PODIUM[i].bg} ${PODIUM[i].tilt} ${PODIUM[i].h}`}>
            <div className="flex items-start justify-between">
              <span className="grid size-16 place-items-center rounded-full border-2 border-ink bg-paper font-mono text-[28px] font-extrabold">{r.rank}</span>
              <Doodle kind="star" size={46} />
            </div>
            <div>
              <h2 className="text-3xl font-black leading-tight tracking-tight">{r.name}</h2>
              <p className="mt-1.5 text-sm font-semibold">
                #{r.track} · {r.members} thành viên
              </p>
            </div>
            <div className="flex items-baseline justify-between border-t-2 border-dashed border-ink/30 pt-3.5">
              <span className="font-serif italic">{PODIUM[i].prize}</span>
              <span className="font-mono text-[34px] font-extrabold tabular-nums">{r.total.toFixed(1)}</span>
            </div>
          </article>
        ))}
      </section>

      <section aria-label="Toàn bộ bảng xếp hạng" className="sketch mt-14 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] border-collapse text-[15px]">
            <thead>
              <tr className="bg-ink text-left text-paper">
                <th scope="col" className="px-5 py-4">Hạng</th>
                <th scope="col" className="px-3 py-4">Đội</th>
                <th scope="col" className="px-3 py-4">Track</th>
                <th scope="col" className="px-3 py-4 text-right">Ý tưởng</th>
                <th scope="col" className="px-3 py-4 text-right">Kỹ thuật</th>
                <th scope="col" className="px-3 py-4 text-right">Trình bày</th>
                <th scope="col" className="px-5 py-4 text-right">Tổng /100</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.name} className="border-t-[1.5px] border-dashed border-line transition-colors hover:bg-cream">
                  <td className="px-5 py-4">
                    <span className="inline-flex items-center gap-2.5">
                      <span className="min-w-7 font-mono text-xl font-extrabold">{r.rank}</span>
                      <span className={`chip font-mono ${r.move > 0 ? "bg-mint" : r.move < 0 ? "bg-rose" : "bg-paper"}`}>
                        {r.move > 0 ? `▲${r.move}` : r.move < 0 ? `▼${-r.move}` : "–"}
                        <span className="sr-only">{r.move > 0 ? "hạng tăng" : r.move < 0 ? "hạng giảm" : "giữ hạng"}</span>
                      </span>
                    </span>
                  </td>
                  <td className="px-3 py-4 font-extrabold">
                    {r.name}
                    {r.tied && <span className="ml-2 rounded-lg border-[1.5px] border-dashed border-ink px-2 text-xs font-bold">đồng hạng</span>}
                  </td>
                  <td className="px-3 py-4">#{r.track}</td>
                  <td className="px-3 py-4 text-right font-mono">{r.c1.toFixed(1)}</td>
                  <td className="px-3 py-4 text-right font-mono">{r.c2.toFixed(1)}</td>
                  <td className="px-3 py-4 text-right font-mono">{r.c3.toFixed(1)}</td>
                  <td className="px-5 py-4 text-right">
                    <span className="inline-flex items-center gap-2.5">
                      <span aria-hidden className="inline-block h-2.5 w-[90px] overflow-hidden rounded-full border-[1.5px] border-ink">
                        <span className="block h-full bg-orange" style={{ width: `${r.total}%` }} />
                      </span>
                      <b className="font-mono text-lg tabular-nums">{r.total.toFixed(1)}</b>
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <p className="mt-4 text-sm text-muted">
        Điểm = trung bình các giám khảo của Σ(điểm/điểm tối đa × trọng số). Đồng điểm: so tiêu chí có trọng số lớn nhất, rồi đến thời điểm
        nộp bản cuối sớm hơn.
      </p>
    </main>
  );
}
