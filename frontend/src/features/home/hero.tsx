"use client";

import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import Link from "next/link";
import type { CSSProperties } from "react";
import { InlineCountdown } from "@/components/ui/countdown";
import { Doodle } from "@/components/ui/doodle";
import { WordsPullUp } from "@/components/ui/prisma-hero";
import { useAuth } from "@/stores/auth";
import { EVENT, HERO_DOODLES, STATS } from "./content";

// Hero không dùng SiteHeader nên tự hiện lối vào tài khoản theo trạng thái đăng nhập
function AccountButton() {
  const user = useAuth((s) => s.user);
  const [href, label] = !user ? ["/login", "Đăng nhập"] : user.is_admin ? ["/admin", "Quản trị"] : ["/profile", user.full_name];
  return (
    <Link href={href} className="btn absolute right-5 top-5 z-20 max-w-48 bg-paper text-sm">
      <span className="truncate">{label}</span>
    </Link>
  );
}

// shortcut: video nền mẫu lấy từ prompt PrismaHero (CDN bên ngoài, ~16MB); thay bằng video của cuộc thi, tự host, kèm poster trước khi lên production
const HERO_VIDEO = "https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260405_170732_8a9ccda6-5cff-4628-b164-059c500a2b41.mp4";

const NAV = [
  ["#rules", "Thể lệ"],
  ["#schedule", "Lịch trình"],
  ["#prizes", "Giải thưởng"],
  ["#sponsors", "Tài trợ"],
  ["#register", "Đăng ký dự thi"],
  [`/events/${EVENT.slug}/results`, "Kết quả"],
];

const rise = (delay: number) => ({
  initial: { y: 20, opacity: 0 },
  animate: { y: 0, opacity: 1 },
  transition: { duration: 0.8, delay, ease: [0.16, 1, 0.3, 1] as const },
});

export function ArrowKnob() {
  return (
    <span className="grid size-10 place-items-center rounded-full bg-ink transition-transform duration-200 group-hover:-rotate-12 group-hover:scale-110">
      <ArrowRight aria-hidden className="size-4 text-cream" />
    </span>
  );
}

export function Hero() {
  return (
    <section id="top" className="p-3">
      <div className="relative flex h-[calc(100svh-24px)] min-h-[720px] flex-col justify-end overflow-hidden rounded-2xl border-2 border-ink bg-ink md:rounded-[2rem]">
        <video
          autoPlay
          loop
          muted
          playsInline
          aria-hidden
          className="absolute inset-0 size-full object-cover motion-reduce:hidden"
          src={HERO_VIDEO}
        />
        <div aria-hidden className="noise pointer-events-none absolute inset-0 opacity-70 mix-blend-overlay" />
        <div aria-hidden className="pointer-events-none absolute inset-0 bg-gradient-to-b from-ink/40 via-transparent to-ink/80" />

        {HERO_DOODLES.slice(0, 4).map((d, i) => (
          <Doodle
            key={i}
            kind={d.kind}
            size={d.size * 0.8}
            fill={d.fill}
            className="drift absolute opacity-90"
            style={{ left: d.x, top: d.y, animationDuration: d.dur, animationDelay: d.delay, "--r0": d.r0, "--r1": d.r1 } as CSSProperties}
          />
        ))}

        <Link href="/" className="absolute left-5 top-5 z-20 flex items-center gap-2.5 text-cream">
          <span aria-hidden className="grid size-[42px] -rotate-6 place-items-center rounded-full border-2 border-ink bg-sun text-lg font-black text-ink">
            S
          </span>
          <span className="text-xl font-black tracking-tight">SEAL</span>
        </Link>

        <nav aria-label="Điều hướng chính" className="absolute left-1/2 top-0 z-20 -translate-x-1/2 max-lg:top-20 max-lg:w-[calc(100%-24px)]">
          <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1 rounded-2xl bg-ink px-4 py-2 sm:gap-x-6 lg:gap-x-12 lg:rounded-t-none lg:rounded-b-3xl lg:px-8">
            {NAV.map(([href, label]) => (
              <a key={href} href={href} className="py-1.5 text-xs text-cream/80 transition-colors hover:text-cream sm:text-sm">
                {label}
              </a>
            ))}
          </div>
        </nav>

        <AccountButton />

        <div className="relative z-10 px-4 pb-2 sm:px-6 md:px-10">
          <div className="grid grid-cols-12 items-end gap-4">
            <div className="col-span-12 lg:col-span-8">
              <h1 className="text-[26vw] font-black leading-[0.85] tracking-[-0.07em] text-cream sm:text-[24vw] md:text-[22vw] lg:text-[19vw] [&_.absolute]:text-orange">
                <WordsPullUp text="SEAL" showAsterisk />
              </h1>
            </div>

            <div className="col-span-12 flex flex-col gap-5 pb-6 lg:col-span-4 lg:pb-10">
              <motion.span {...rise(0.4)} className="chip -rotate-2 self-start bg-mint px-3.5 py-2 text-[13px]">
                <span aria-hidden className="size-2 rounded-full bg-ink" />
                Mở đăng ký · đóng sau <InlineCountdown target={EVENT.registrationClosesAt} />
              </motion.span>
              <motion.p {...rise(0.5)} className="text-2xl font-black leading-tight tracking-tight text-cream md:text-3xl">
                {EVENT.name} – Software Engineering Hackathon
              </motion.p>
              <motion.p {...rise(0.6)} className="font-serif text-base italic leading-snug text-cream/85 md:text-lg">
                48 giờ để biến một ý tưởng thành phần mềm chạy được. Lập đội 2–4 người, chọn track, commit liên tục – ban giám khảo và
                mentor đồng hành từ dòng code đầu tiên.
              </motion.p>
              <motion.div {...rise(0.7)} className="flex flex-wrap items-center gap-3">
                <a href="#register" className="btn group h-[54px] bg-orange pl-[22px] pr-1.5 text-base font-extrabold text-ink hover:gap-4">
                  Đăng ký dự thi
                  <ArrowKnob />
                </a>
                <a href="#rules" className="px-1.5 py-3 font-bold text-cream underline decoration-orange decoration-wavy underline-offset-[6px]">
                  Xem thể lệ
                </a>
              </motion.div>
            </div>
          </div>
        </div>
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4">
        {STATS.map((s) => (
          <div key={s.label} className={`flex flex-col-reverse gap-0.5 rounded-[20px] border-2 border-ink px-5 py-4 ${s.bg}`}>
            <dt className="text-sm font-semibold">{s.label}</dt>
            <dd className="m-0 font-mono text-[34px] font-extrabold tracking-tight">{s.value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
