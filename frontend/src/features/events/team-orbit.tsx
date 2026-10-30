"use client";

import { OrbitScene, type OrbitTeam } from "./orbit-scene";
import type { PublicTeam, Track } from "./types";

// Màu track theo thứ tự track của cuộc thi; đội chưa chọn track dùng màu trung tính
const PALETTE = ["#8fdcff", "#ffb8c6", "#b8f0a0", "#ffd23f", "#c9b8ff", "#ffcf9e"];
const NO_TRACK = { label: "Chưa chọn track", color: "#e4e1da" };

export function TeamOrbit({ eventName, teams, tracks }: { eventName: string; teams: PublicTeam[]; tracks: Track[] }) {
  const legend = tracks.map((t, i) => ({ id: t.id, label: t.name, color: PALETTE[i % PALETTE.length] }));
  const byId = new Map(legend.map((l) => [l.id, l]));
  const planets: OrbitTeam[] = teams.map((t) => {
    const track = (t.track_id && byId.get(t.track_id)) || NO_TRACK;
    return { id: t.id, name: t.name, trackLabel: track.label, color: track.color, members: t.member_count };
  });

  return (
    <section>
      <ul aria-label="Chú thích track" className="flex flex-wrap gap-2 text-sm">
        {[...legend, ...(planets.some((p) => p.color === NO_TRACK.color) ? [{ id: "none", ...NO_TRACK }] : [])].map((t) => (
          <li key={t.id} className="chip bg-paper">
            <span aria-hidden className="size-3 rounded-full border border-ink" style={{ background: t.color }} />
            {t.label}
          </li>
        ))}
      </ul>

      <div className="sketch mt-6 overflow-hidden bg-ink p-0">
        <OrbitScene teams={planets} eventName={eventName} />
      </div>
      <p className="mt-3 text-center font-serif italic text-muted">
        {planets.length ? "Kéo để xoay góc nhìn, cuộn để phóng to. Rê chuột vào vũ trụ để dừng quỹ đạo và xem tên đội." : "Chưa có đội nào được duyệt. Hành tinh sẽ xuất hiện khi ban tổ chức duyệt đội."}
      </p>

      {planets.length > 0 && (
        <details className="sketch mt-6 p-5">
          <summary className="cursor-pointer font-bold">Danh sách {planets.length} đội đã duyệt</summary>
          <ol className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {planets.map((t) => (
              <li key={t.id} className="flex items-center gap-2 text-sm">
                <span aria-hidden className="size-3 shrink-0 rounded-full border border-ink" style={{ background: t.color }} />
                <span className="truncate font-semibold">{t.name}</span>
                <span className="ml-auto shrink-0 text-muted">
                  {t.trackLabel} · {t.members} người
                </span>
              </li>
            ))}
          </ol>
        </details>
      )}
    </section>
  );
}
