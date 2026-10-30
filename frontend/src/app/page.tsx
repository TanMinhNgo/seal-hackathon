import type { ReactNode } from "react";
import { Doodle } from "@/components/ui/doodle";
import DoodleCrewFooter, { type CrewMember, type FooterColumn } from "@/components/ui/doodle-crew-footer";
import { EventStatusBadge } from "@/components/ui/event-status-badge";
import {
  EVENT,
  MILESTONES,
  OTHER_EVENTS,
  PEOPLE,
  PRIZES,
  REG_STEPS,
  RULES,
  SIDE_PRIZES,
  SPONSOR_TIERS,
} from "@/features/home/content";
import { Hero } from "@/features/home/hero";
import { RegisterCta } from "@/features/home/register-cta";

// "SEAL" chỉ có 4 chữ (chỉ số 0–3) nên nhóm nhân vật đặt lại cho vừa
const FOOTER_CREW: CrewMember[] = [
  { kind: "yeti", letter: 0, seat: "front", offset: -0.32, name: "Bruno", says: "Commit sớm, ngủ sớm." },
  { kind: "bird", letter: 1, seat: "top", offset: 0.02, name: "Pip", says: "Hạn nộp tính theo giờ server đó nha!" },
  { kind: "kid", letter: 2, seat: "top", offset: -0.05, name: "Juno", says: "Chỗ này xem bảng xếp hạng là nhất." },
  { kind: "ghost", letter: 3, seat: "behind", offset: -0.3, name: "Boo", says: "Hù! Repo private là khỏi đồng bộ." },
  { kind: "cat", letter: 3, seat: "front", offset: 0.45, flip: true, name: "Patch", says: "Meo. Nhớ viết test nha." },
];

const FOOTER_COLUMNS: FooterColumn[] = [
  { title: "Cuộc thi", links: [{ label: "Thể lệ", href: "#rules" }, { label: "Kết quả", href: `/events/${EVENT.slug}/results` }] },
  { title: "Thí sinh", links: [{ label: "Cuộc thi của tôi", href: "/dashboard" }, { label: "Đăng ký dự thi", href: "#register" }] },
  { title: "Giám khảo", links: [{ label: "Chấm điểm", href: "/judge" }, { label: "Mentor", href: "/mentor" }] },
  { title: "Tài khoản", links: [{ label: "Đăng nhập", href: "/login" }, { label: "Tạo tài khoản", href: "/register" }] },
];

const TILTS = ["-rotate-[1.2deg]", "rotate-[0.8deg]", "-rotate-[0.6deg]", "rotate-[1.2deg]"];
const NOTE_BGS = ["bg-cream", "bg-paper", "bg-sky", "bg-paper", "bg-rose", "bg-paper", "bg-mint", "bg-paper"];

function SectionTitle({ kicker, children }: { kicker?: string; children: ReactNode }) {
  return (
    <div>
      {kicker && <p className="m-0 font-serif text-xl italic">{kicker}</p>}
      <h2 className="mt-1.5 text-[clamp(40px,5vw,68px)] font-black leading-none tracking-[-0.045em]">{children}</h2>
    </div>
  );
}

export default function Home() {
  return (
    <>
      <main className="overflow-hidden">
        <Hero />

        <section id="schedule" className="mx-auto max-w-7xl px-6 pb-10 pt-28">
          <SectionTitle kicker="Đánh dấu lịch đi">Lịch trình.</SectionTitle>
          <ol className="mt-13 grid gap-4 sm:grid-cols-3 lg:grid-cols-6">
            {MILESTONES.map((m, i) => (
              <li key={m.title} className="relative pt-9">
                {i < MILESTONES.length - 1 && (
                  <span aria-hidden className={`absolute left-0 right-[-16px] top-3 border-t-[2.5px] border-ink ${m.state === "done" ? "border-solid" : "border-dashed"} max-sm:hidden`} />
                )}
                <span aria-hidden className={`absolute left-0 top-0 size-[26px] rounded-full border-[2.5px] border-ink ${m.state === "done" ? "bg-mint" : m.state === "today" ? "bg-orange" : "bg-paper"}`} />
                {m.state === "today" && <span className="chip absolute left-9 top-[-4px] -rotate-3 bg-orange">Hôm nay</span>}
                <p className="m-0 font-mono text-sm font-extrabold">{m.date}</p>
                <p className="mt-1 text-lg font-extrabold">{m.title}</p>
                <p className="mt-1 text-sm leading-normal text-muted">{m.detail}</p>
              </li>
            ))}
          </ol>
        </section>

        <section id="rules" className="mx-auto max-w-7xl px-6 pb-10 pt-24">
          <div className="flex flex-wrap items-end justify-between gap-5">
            <h2 className="text-[clamp(40px,5vw,68px)] font-black leading-none tracking-[-0.045em]">
              Thể lệ,
              <br />
              <span className="font-serif font-semibold italic">ngắn gọn.</span>
            </h2>
            <a href="#pdf" className="btn bg-paper">
              <svg aria-hidden width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 4v11M7 10l5 5 5-5M5 20h14" />
              </svg>
              Tải thể lệ đầy đủ (PDF)
            </a>
          </div>
          <ol className="mt-12 grid gap-[22px] sm:grid-cols-2 lg:grid-cols-4">
            {RULES.map(([title, detail], i) => (
              <li key={title} className={`rounded-[18px] border-2 border-ink p-5 shadow-sketch-sm ${NOTE_BGS[i]} ${TILTS[i % 4]}`}>
                <span className="font-mono text-[28px] font-extrabold">{String(i + 1).padStart(2, "0")}</span>
                <p className="mt-2 text-[17px] font-extrabold">{title}</p>
                <p className="mt-1.5 text-sm leading-normal">{detail}</p>
              </li>
            ))}
          </ol>
        </section>

        <section id="prizes" className="mx-auto max-w-7xl px-6 pb-10 pt-24">
          <SectionTitle>Giải thưởng.</SectionTitle>
          <div className="mt-12 grid items-end gap-6 md:grid-cols-3">
            {PRIZES.map((p) => (
              <article key={p.name} className={`flex flex-col justify-between gap-[18px] rounded-[26px] border-2 border-ink p-[26px] shadow-sketch ${p.bg} ${p.h} ${p.tilt}`}>
                <div className="flex items-start justify-between">
                  <h3 className="text-3xl font-black tracking-tight">{p.name}</h3>
                  <Doodle kind="star" size={42} />
                </div>
                <div>
                  <p className="m-0 font-mono text-4xl font-extrabold">{p.value}</p>
                  <p className="mt-1.5 text-[15px] font-semibold">{p.extra}</p>
                </div>
              </article>
            ))}
          </div>
          <ul className="mt-7 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {SIDE_PRIZES.map((s) => (
              <li key={s.name} className="flex items-center justify-between gap-3 rounded-[18px] border-2 border-dashed border-ink px-[18px] py-4">
                <span>
                  <b className="block">{s.name}</b>
                  <span className="text-[13px] text-muted">{s.detail}</span>
                </span>
                <span className="font-mono font-extrabold">{s.value}</span>
              </li>
            ))}
          </ul>
        </section>

        <section id="register" className="mx-auto max-w-7xl px-6 pb-10 pt-24">
          <div className="rounded-[32px] border-2 border-ink bg-ink p-[clamp(24px,4vw,56px)] text-cream shadow-[8px_8px_0_var(--orange)]">
            <div className="flex flex-wrap items-end justify-between gap-6">
              <h2 className="text-[clamp(40px,5vw,68px)] font-black leading-none tracking-[-0.045em]">
                Đăng ký
                <br />
                trong 3 bước.
              </h2>
              <p className="max-w-[380px] font-serif text-lg italic leading-normal">
                Hạn đăng ký: [hh:mm, dd/mm/yyyy]. Dành cho sinh viên ngành Kỹ thuật Phần mềm và các ngành liên quan.
              </p>
            </div>
            <ol className="mt-10 grid gap-[18px] md:grid-cols-3">
              {REG_STEPS.map((r, i) => (
                <li key={r.title} className={`rounded-[22px] border-2 border-cream p-[22px] text-ink ${r.bg}`}>
                  <span className="grid size-10 place-items-center rounded-full border-2 border-ink bg-paper font-mono font-extrabold">{i + 1}</span>
                  <p className="mt-3.5 text-[22px] font-black">{r.title}</p>
                  <p className="mt-1.5 text-sm leading-normal">{r.detail}</p>
                </li>
              ))}
            </ol>
            <div className="mt-8 flex flex-wrap items-center gap-3.5">
              <RegisterCta />
            </div>
          </div>
        </section>

        <section id="people" className="mx-auto max-w-7xl px-6 pb-10 pt-24">
          <SectionTitle kicker="Không ai code một mình">Ai đồng hành cùng bạn.</SectionTitle>
          <ul className="mt-11 grid gap-[22px] sm:grid-cols-2 lg:grid-cols-3">
            {PEOPLE.map((p, i) => (
              <li key={i} className="sketch lift rounded-[22px] p-5 shadow-sketch-sm">
                <div className="flex items-center gap-3">
                  <span aria-hidden className={`grid size-[52px] place-items-center rounded-full border-2 border-ink text-xl font-black ${p.bg}`}>
                    {p.role === "Mentor" ? "M" : "G"}
                  </span>
                  <span className={`chip ${p.role === "Mentor" ? "bg-mint" : "bg-orange"}`}>{p.role}</span>
                </div>
                <p className="mt-3.5 text-[19px] font-black">{p.name}</p>
                <p className="mt-0.5 text-sm text-muted">{p.org}</p>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {p.tags.map((t) => (
                    <span key={t} className="rounded-lg border-[1.5px] border-dashed border-ink px-2 text-xs font-semibold">
                      #{t}
                    </span>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        </section>

        <section id="events" className="mx-auto max-w-7xl px-6 pb-10 pt-24">
          <SectionTitle>Các cuộc thi khác.</SectionTitle>
          <ul className="mt-10 grid gap-7 md:grid-cols-3">
            {OTHER_EVENTS.map((e) => (
              <li key={e.name} className="sketch lift flex flex-col gap-3.5 p-6">
                <span className="self-start">
                  <EventStatusBadge status={e.status} />
                </span>
                <h3 className="text-[26px] font-black tracking-tight">{e.name}</h3>
                <p className="text-[15px] leading-relaxed text-muted">{e.blurb}</p>
                <p className="mt-auto border-t-2 border-dashed border-line pt-3.5 font-serif italic">{e.next}</p>
              </li>
            ))}
          </ul>
        </section>

        <section id="sponsors" className="mx-auto max-w-7xl px-6 pb-20 pt-24">
          <div className="flex flex-wrap items-end justify-between gap-5">
            <SectionTitle>Nhà tài trợ.</SectionTitle>
            <a href="mailto:[email]" className="btn bg-sun">
              Trở thành nhà tài trợ →
            </a>
          </div>
          {SPONSOR_TIERS.map((t) => (
            <div key={t.name} className="mt-9">
              <p className="mb-3.5 font-mono text-sm font-extrabold tracking-wider">{t.name}</p>
              <ul className={`grid gap-4 ${t.grid}`}>
                {Array.from({ length: t.count }, (_, i) => (
                  <li key={i} className={`grid place-items-center rounded-[18px] border-2 border-dashed border-ink text-sm font-bold text-muted ${t.h} ${t.bg}`}>
                    [Logo nhà tài trợ]
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </section>
      </main>

      <DoodleCrewFooter
        wordmark="SEAL"
        brand="SEAL Hackathon"
        blurb="Nền tảng vận hành trọn một cuộc thi hackathon ngành Kỹ thuật Phần mềm."
        tagline="Từ commit đầu tiên đến bục vinh quang."
        palette={{ background: "var(--paper)", ink: "var(--ink)", accent: "#ff6b2c" }}
        columns={FOOTER_COLUMNS}
        actions={[
          { label: "Tạo tài khoản", href: "/register", icon: "bolt", variant: "outline" },
          { label: "Xem kết quả", href: `/events/${EVENT.slug}/results`, icon: "star", variant: "solid" },
        ]}
        crew={FOOTER_CREW}
        doodles={["star", "bolt", "flame", "sparkle", "heart", "plane"]}
        copyright="© 2026 SEAL – Software Engineering Hackathon Management System"
        legal={[]}
        socials={[]}
      />
    </>
  );
}
