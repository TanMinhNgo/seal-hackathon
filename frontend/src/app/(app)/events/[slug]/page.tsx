import { isAxiosError } from "axios";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { cache } from "react";
import { EventStatusBadge } from "@/components/ui/event-status-badge";
import { LocalTime } from "@/components/ui/local-time";
import { EventCta } from "@/features/events/event-cta";
import type { Event, Page, Prize, Round, Track } from "@/features/events/types";
import { api } from "@/lib/api";

const TRACK_TONES = ["bg-sky", "bg-rose", "bg-mint", "bg-sun"];
const PRIZE_TONES = ["bg-sun", "bg-sky", "bg-rose"];

// cache: generateMetadata và trang dùng chung một lượt gọi API mỗi request
const load = cache(async (slug: string) => {
  try {
    const event = (await api.get<Event>(`/events/by-slug/${encodeURIComponent(slug)}`)).data;
    const list = <T,>(what: string) => api.get<Page<T>>(`/events/${event.id}/${what}`, { params: { limit: 100 } }).then((r) => r.data.items);
    const [rounds, tracks, prizes] = await Promise.all([list<Round>("rounds"), list<Track>("tracks"), list<Prize>("prizes")]);
    return { event, rounds, tracks, prizes };
  } catch (e) {
    // Bản nháp/đã lưu trữ cũng trả 403/404 với khách: coi như không tồn tại
    if (isAxiosError(e) && (e.response?.status === 404 || e.response?.status === 403)) notFound();
    throw e;
  }
});

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { event } = await load((await params).slug);
  return { title: `${event.name} · SEAL`, description: event.description ?? undefined };
}

export default async function EventPage({ params }: { params: Promise<{ slug: string }> }) {
  const { event, rounds, tracks, prizes } = await load((await params).slug);

  return (
    <main className="mx-auto max-w-[1200px] px-4 pb-24 pt-12 sm:px-6">
      <section className="flex flex-wrap items-end justify-between gap-8">
        <div className="min-w-0 flex-[1_1_560px]">
          <EventStatusBadge status={event.status} />
          <h1 className="mt-4 break-words text-[clamp(44px,7vw,96px)] font-black leading-[0.92] tracking-[-0.055em]">{event.name}</h1>
          {event.description && <p className="mt-5 max-w-[620px] whitespace-pre-line font-serif text-xl italic leading-normal">{event.description}</p>}
        </div>
        <EventCta event={event} />
      </section>

      <dl className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-[18px] border-2 border-ink bg-cream p-4">
          <dt className="text-sm font-semibold">Đăng ký</dt>
          <dd className="mt-1 font-mono font-extrabold">
            <LocalTime iso={event.registration_opens_at} /> → <LocalTime iso={event.registration_closes_at} />
          </dd>
        </div>
        <div className="rounded-[18px] border-2 border-ink p-4">
          <dt className="text-sm font-semibold">Thời gian thi</dt>
          <dd className="mt-1 font-mono font-extrabold">
            <LocalTime iso={event.starts_at} /> → <LocalTime iso={event.ends_at} />
          </dd>
        </div>
        <div className="rounded-[18px] border-2 border-ink p-4">
          <dt className="text-sm font-semibold">Quy mô đội</dt>
          <dd className="mt-1 font-mono font-extrabold">
            {event.min_team_size === event.max_team_size ? `${event.max_team_size}` : `${event.min_team_size}–${event.max_team_size}`} người
          </dd>
        </div>
        <div className="rounded-[18px] border-2 border-ink bg-sky p-4">
          <dt className="text-sm font-semibold">Các đội</dt>
          <dd className="mt-1 font-extrabold">
            <Link href={`/events/${event.slug}/teams`} className="underline">
              Xem vũ trụ đội thi
            </Link>
          </dd>
        </div>
      </dl>

      {rounds.length > 0 && (
        <section className="mt-16">
          <h2 className="text-[clamp(32px,4vw,48px)] font-black tracking-[-0.045em]">Lịch các vòng.</h2>
          <ol className="mt-7 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {rounds.map((r) => (
              <li key={r.id} className="sketch p-5">
                <span className="font-mono text-[28px] font-extrabold">{String(r.order).padStart(2, "0")}</span>
                <p className="mt-1.5 text-xl font-black">{r.name}</p>
                <p className="mt-2.5 text-sm">
                  Bắt đầu: <b className="font-mono"><LocalTime iso={r.starts_at} /></b>
                </p>
                <p className="mt-1 text-sm">
                  Hạn nộp: <b className="font-mono"><LocalTime iso={r.submission_deadline} /></b>
                </p>
              </li>
            ))}
          </ol>
          <p className="mt-3 text-sm text-muted">Giờ hiển thị theo máy bạn; hạn nộp tính theo giờ server.</p>
        </section>
      )}

      {tracks.length > 0 && (
        <section className="mt-16">
          <h2 className="text-[clamp(32px,4vw,48px)] font-black tracking-[-0.045em]">Track chủ đề.</h2>
          <ul className="mt-7 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {tracks.map((t, i) => (
              <li key={t.id} className="rounded-[18px] border-2 border-dashed border-ink p-4">
                <span className={`chip ${TRACK_TONES[i % TRACK_TONES.length]}`}>{t.name}</span>
                {t.description && <p className="mt-2.5 text-sm leading-relaxed text-muted">{t.description}</p>}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="mt-16 flex flex-wrap gap-7">
        {event.rules && (
          <div className="min-w-0 flex-[1_1_420px]">
            <h2 className="text-[clamp(32px,4vw,48px)] font-black tracking-[-0.045em]">Thể lệ.</h2>
            <p className="mt-6 whitespace-pre-line text-[15px] leading-relaxed">{event.rules}</p>
          </div>
        )}
        {prizes.length > 0 && (
          <div className="min-w-0 flex-[1_1_420px]">
            <h2 className="text-[clamp(32px,4vw,48px)] font-black tracking-[-0.045em]">Giải thưởng.</h2>
            <ul className="mt-6 space-y-3">
              {prizes.map((p, i) => (
                <li key={p.id} className={`rounded-2xl border-2 border-ink px-4 py-3.5 ${PRIZE_TONES[i] ?? "bg-paper"}`}>
                  <div className="flex items-center justify-between gap-3">
                    <b className="text-[17px]">{p.name}</b>
                    <span className="font-mono font-extrabold">{Number(p.value).toLocaleString("vi-VN")} đ</span>
                  </div>
                  {p.description && <p className="mt-1 text-sm">{p.description}</p>}
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>
    </main>
  );
}
