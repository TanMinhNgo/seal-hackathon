import { isAxiosError } from "axios";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Doodle } from "@/components/ui/doodle";
import type { Event, LeaderboardData, Page, Round, Rubric, Track } from "@/features/events/types";
import { api } from "@/lib/api";
import { FORMULA_NOTE, LeaderboardTable } from "./leaderboard-table";

const PODIUM = [
  { bg: "bg-sun", tilt: "-rotate-[1.5deg]", h: "md:min-h-[260px]" },
  { bg: "bg-sky", tilt: "rotate-1", h: "md:min-h-[230px]" },
  { bg: "bg-rose", tilt: "-rotate-[0.6deg]", h: "md:min-h-[210px]" },
];

// shortcut: lấy 100 đội đầu mỗi vòng; thêm phân trang nếu một vòng có hơn 100 đội
const board = (eventId: string, roundId: string, trackId?: string) =>
  api
    .get<LeaderboardData>(`/events/${eventId}/rounds/${roundId}/leaderboard`, { params: { track_id: trackId, limit: 100 } })
    .then((r) => r.data)
    // Chưa công bố hoặc bị thu hồi (409 NOT_PUBLISHED) thì khách không thấy vòng đó
    .catch((e: unknown) => {
      if (isAxiosError(e) && e.response?.status === 409) return null;
      throw e;
    });

export async function Leaderboard({ slug, roundId, trackId }: { slug: string; roundId?: string; trackId?: string }) {
  let event: Event;
  try {
    event = (await api.get<Event>(`/events/by-slug/${encodeURIComponent(slug)}`)).data;
  } catch (e) {
    if (isAxiosError(e) && (e.response?.status === 404 || e.response?.status === 403)) notFound();
    throw e;
  }
  const list = <T,>(what: string) => api.get<Page<T>>(`/events/${event.id}/${what}`, { params: { limit: 100 } }).then((r) => r.data.items);
  const [rounds, tracks] = await Promise.all([list<Round>("rounds"), list<Track>("tracks")]);
  rounds.sort((a, b) => a.order - b.order);
  const boards = await Promise.all(rounds.map((r) => board(event.id, r.id)));
  const published = rounds.filter((_, i) => boards[i]);
  const round = published.find((r) => r.id === roundId) ?? published.at(-1);
  const track = tracks.find((t) => t.id === trackId);
  const data = round && (track ? await board(event.id, round.id, track.id) : boards[rounds.indexOf(round)]);
  const rubric = round && (await api.get<Rubric>(`/events/${event.id}/rounds/${round.id}/rubric`)).data;
  const trackName = new Map(tracks.map((t) => [t.id, t.name]));
  const href = (r?: string, t?: string) => `/events/${slug}/results?${new URLSearchParams({ ...(r && { round: r }), ...(t && { track: t }) })}`;

  return (
    <main className="mx-auto max-w-6xl px-4 pb-24 pt-14 sm:px-6">
      <Link href={`/events/${slug}`} className="font-serif text-xl italic underline-offset-4 hover:underline">
        {event.name}
      </Link>
      <div className="mt-2 flex flex-wrap items-end justify-between gap-6">
        <h1 className="text-[clamp(48px,7vw,96px)] font-black leading-[0.95] tracking-[-0.05em]">
          Bảng
          <br />
          xếp hạng.
        </h1>
        {round && (
          <div className="flex flex-col items-start gap-3 sm:items-end">
            <nav aria-label="Chọn vòng" className="flex flex-wrap gap-2">
              {published.map((r) => (
                <Link key={r.id} href={href(r.id, track?.id)} aria-current={r.id === round.id ? "page" : undefined} className={`btn text-sm ${r.id === round.id ? "bg-ink text-paper" : "bg-paper"}`}>
                  {r.name}
                </Link>
              ))}
            </nav>
            {tracks.length > 0 && (
              <nav aria-label="Lọc theo track" className="flex flex-wrap gap-1.5">
                {[undefined, ...tracks].map((t) => (
                  <Link
                    key={t?.id ?? "all"}
                    href={href(round.id, t?.id)}
                    aria-current={t?.id === track?.id ? "page" : undefined}
                    className={`inline-flex min-h-11 items-center rounded-[10px] border-[1.5px] border-dashed border-ink px-3.5 text-sm font-semibold ${t?.id === track?.id ? "bg-sun" : "bg-paper"}`}
                  >
                    #{t?.name ?? "tất-cả"}
                  </Link>
                ))}
              </nav>
            )}
          </div>
        )}
      </div>

      {!round || !data || !rubric ? (
        <p className="mt-14 font-serif text-xl italic text-muted">Chưa có vòng nào công bố kết quả.</p>
      ) : (
        <>
          {data.items.length > 0 && (
            <section aria-label="Top 3" className="mt-14 grid items-end gap-7 md:grid-cols-3">
              {data.items.slice(0, 3).map((r, i) => (
                <article key={r.team.id} className={`flex flex-col justify-between gap-5 rounded-[26px] border-2 border-ink p-[26px] shadow-sketch ${PODIUM[i].bg} ${PODIUM[i].tilt} ${PODIUM[i].h}`}>
                  <div className="flex items-start justify-between">
                    <span className="grid size-16 place-items-center rounded-full border-2 border-ink bg-paper font-mono text-[28px] font-extrabold">{r.rank}</span>
                    <Doodle kind="star" size={46} />
                  </div>
                  <div>
                    <h2 className="break-words text-3xl font-black leading-tight tracking-tight">{r.team.name}</h2>
                    {r.team.track_id && <p className="mt-1.5 text-sm font-semibold">#{trackName.get(r.team.track_id)}</p>}
                  </div>
                  <div className="flex items-baseline justify-between border-t-2 border-dashed border-ink/30 pt-3.5">
                    <span className="font-serif italic">{r.tied ? "Đồng hạng" : `Hạng ${r.rank}`}</span>
                    <span className="font-mono text-[34px] font-extrabold tabular-nums">{Number(r.total).toFixed(2)}</span>
                  </div>
                </article>
              ))}
            </section>
          )}
          <section aria-label="Toàn bộ bảng xếp hạng" className="sketch mt-14 overflow-hidden">
            <LeaderboardTable rows={data.items} criteria={rubric.criteria} trackName={trackName} />
          </section>
          <p className="mt-4 text-sm text-muted">
            {FORMULA_NOTE} Công bố lần {data.publication_revision}.
          </p>
        </>
      )}
    </main>
  );
}
