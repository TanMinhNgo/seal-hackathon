import type { Metadata } from "next";
import Link from "next/link";
import { EventStatusBadge, EVENT_STATUS, type EventStatus } from "@/components/ui/event-status-badge";
import type { EventPage } from "@/features/events/types";
import { api, errorMessage } from "@/lib/api";
import { LocalTime } from "@/components/ui/local-time";

export const metadata: Metadata = { title: "Các cuộc thi · SEAL" };

const FILTERS: (EventStatus | "all")[] = ["all", "open", "ongoing", "judging", "closed"];

export default async function EventsPage({ searchParams }: { searchParams: Promise<{ status?: string; q?: string }> }) {
  const { status = "all", q = "" } = await searchParams;
  let page: EventPage | null = null;
  let error = "";
  try {
    // shortcut: 100 cuộc thi đầu, chưa phân trang; thêm Pager khi số cuộc thi vượt mức này
    page = (await api.get<EventPage>("/events", { params: { status: status === "all" ? undefined : status, q: q || undefined, limit: 100 } })).data;
  } catch (e) {
    error = errorMessage(e);
  }

  return (
    <main className="mx-auto max-w-[1200px] px-4 pb-24 pt-12 sm:px-6">
      <p className="font-serif text-xl italic">Chọn sân chơi của bạn</p>
      <h1 className="mt-2 text-[clamp(44px,6vw,80px)] font-black leading-[0.95] tracking-[-0.05em]">Các cuộc thi.</h1>

      <div className="mt-8 flex flex-wrap items-end gap-3">
        <form role="search" className="flex min-w-0 flex-[1_1_320px] items-end gap-2">
          {status !== "all" && <input type="hidden" name="status" value={status} />}
          <label className="min-w-0 flex-1">
            <span className="text-sm font-bold">Tìm theo tên cuộc thi</span>
            <input name="q" type="search" defaultValue={q} maxLength={100} className="mt-1.5 block min-h-11 w-full rounded-xl border-2 border-ink bg-paper px-3.5" />
          </label>
          <button type="submit" className="btn bg-ink text-paper">
            Tìm
          </button>
        </form>
        <nav aria-label="Lọc theo trạng thái" className="flex flex-wrap gap-2">
          {FILTERS.map((s) => (
            <Link
              key={s}
              href={{ pathname: "/events", query: { ...(s !== "all" && { status: s }), ...(q && { q }) } }}
              aria-current={status === s ? "page" : undefined}
              className={`btn ${status === s ? "bg-ink text-paper" : "bg-paper"}`}
            >
              {s === "all" ? "Tất cả" : EVENT_STATUS[s].label}
            </Link>
          ))}
        </nav>
      </div>

      {error && <p role="alert" className="mt-8 rounded-xl border-2 border-ink bg-rose px-4 py-3 font-semibold">{error}</p>}
      {page?.total === 0 && <p className="mt-10 font-serif text-lg italic text-muted">Không có cuộc thi nào khớp.</p>}

      <ul className="mt-10 grid gap-7 sm:grid-cols-2 lg:grid-cols-3">
        {page?.items.map((e) => (
          <li key={e.id}>
            <Link href={`/events/${e.slug}`} className="sketch lift flex h-full flex-col gap-3.5 p-6">
              <span className="self-start">
                <EventStatusBadge status={e.status} />
              </span>
              <h2 className="text-[26px] font-black leading-tight tracking-tight">{e.name}</h2>
              {e.description && <p className="line-clamp-3 text-[15px] leading-relaxed text-muted">{e.description}</p>}
              <p className="mt-auto border-t-2 border-dashed border-line pt-3.5 font-mono text-sm font-extrabold">
                <LocalTime iso={e.starts_at} dateOnly /> → <LocalTime iso={e.ends_at} dateOnly />
              </p>
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
