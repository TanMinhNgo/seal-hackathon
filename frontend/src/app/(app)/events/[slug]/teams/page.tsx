import { isAxiosError } from "axios";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { TeamOrbit } from "@/features/events/team-orbit";
import type { Event, Page, PublicTeam, Track } from "@/features/events/types";
import { api } from "@/lib/api";

export const metadata: Metadata = { title: "Vũ trụ đội thi · SEAL" };

export default async function EventTeamsPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  let event: Event;
  try {
    event = (await api.get<Event>(`/events/by-slug/${encodeURIComponent(slug)}`)).data;
  } catch (e) {
    if (isAxiosError(e) && (e.response?.status === 404 || e.response?.status === 403)) notFound();
    throw e;
  }
  const [teams, tracks] = await Promise.all([
    api.get<PublicTeam[]>(`/events/${event.id}/teams/public`).then((r) => r.data),
    api.get<Page<Track>>(`/events/${event.id}/tracks`, { params: { limit: 100 } }).then((r) => r.data.items),
  ]);

  return (
    <main className="mx-auto max-w-[1100px] px-4 pb-24 pt-10 sm:px-6">
      <p className="font-serif text-lg italic">
        <Link href={`/events/${event.slug}`} className="underline">
          {event.name}
        </Link>{" "}
        · mỗi đội là một hành tinh
      </p>
      <h1 className="mt-1 text-[clamp(36px,5vw,56px)] font-black leading-none tracking-[-0.045em]">Vũ trụ đội thi.</h1>
      <div className="mt-8">
        {/* shortcut: dữ liệu lấy lúc tải trang; tự thêm hành tinh khi có sự kiện realtime team:approved (Phase 7) */}
        <TeamOrbit eventName={event.name} teams={teams} tracks={tracks} />
      </div>
    </main>
  );
}
