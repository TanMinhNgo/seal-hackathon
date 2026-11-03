"use client";

import Link from "next/link";
import { useState } from "react";
import { FormError } from "@/features/auth/auth-card";
import { AiConfigPanel, AiQuality } from "@/features/ai-reviews/ai-reviews";
import { CommitOverviewPanel } from "@/features/commits/commits";
import { AnnouncementForm, AnnouncementList } from "@/features/notifications/announcements";
import { JudgingPanel, MentorAssignmentsPanel } from "@/features/judging/organizer";
import { RoundSubmissionsPanel } from "@/features/submissions/submissions";
import { errorMessage } from "@/lib/api";
import { CrudPanel, EventEditor, RegistrationsPanel, RolesPanel, StatusStepper, Tabs, TeamsPanel, useEvent, useEventCache } from "./manage";

type Tab = "info" | "rounds" | "tracks" | "prizes" | "roles" | "teams" | "registrations" | "submissions" | "judging" | "mentors" | "progress" | "ai" | "announcements";

/** Khu vận hành của ban tổ chức cho một cuộc thi. */
export function ManageEvent({ eventId }: { eventId: string }) {
  const event = useEvent(eventId);
  const [tab, setTab] = useState<Tab>("teams");
  const cacheEvent = useEventCache(eventId);

  if (event.isError) return <main className="mx-auto max-w-[1360px] px-4 pt-10 sm:px-6"><FormError>{errorMessage(event.error)}</FormError></main>;
  if (!event.data) return <p role="status" className="px-6 pt-12 text-center">Đang tải…</p>;
  const e = event.data;
  // Slug chỉ đổi được khi còn bản nháp
  const infoKeys = ["name", ...(e.status === "draft" ? ["slug"] : []), "registration_opens_at", "registration_closes_at", "starts_at", "ends_at", "min_team_size", "max_team_size", "sync_interval_minutes", "inactivity_alert_hours", "banner_url", "description", "rules"];

  return (
    <main className="mx-auto max-w-[1360px] space-y-7 px-4 pb-24 pt-8 sm:px-6">
      <div>
        <p className="font-serif text-lg italic">Ban tổ chức</p>
        <h1 className="mt-1 break-words text-[clamp(36px,5vw,56px)] font-black leading-none tracking-[-0.045em]">{e.name}.</h1>
        <p className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-sm font-bold">
          <Link href={`/manage/events/${e.id}/dashboard`} className="underline">
            Dashboard &amp; báo cáo
          </Link>
          {e.status !== "draft" && (
            <Link href={`/events/${e.slug}`} className="underline">
              Xem trang công khai
            </Link>
          )}
        </p>
      </div>

      <StatusStepper event={e} canTransition />

      <Tabs<Tab>
        label="Khu vận hành"
        value={tab}
        onChange={setTab}
        tabs={[
          ["info", "Thông tin"],
          ["rounds", "Vòng thi"],
          ["tracks", "Track"],
          ["prizes", "Giải thưởng"],
          ["roles", "Giám khảo & mentor"],
          ["teams", "Duyệt đội"],
          ["registrations", "Người đăng ký"],
          ["submissions", "Bài nộp"],
          ["progress", "Tiến độ"],
          ["ai", "AI review"],
          ["mentors", "Phân công mentor"],
          ["judging", "Chấm điểm"],
          ["announcements", "Thông báo"],
        ]}
      />

      <section className="sketch p-6">
        {tab === "info" && (
          <>
            <h2 className="mb-1 text-xl font-black">Thông tin &amp; lịch</h2>
            <p className="mb-4 text-sm text-muted">Giờ nhập theo máy bạn, lưu ở server theo UTC. Sau giờ bắt đầu thi chỉ còn sửa được tên, mô tả, ảnh bìa, chu kỳ đồng bộ và ngưỡng cảnh báo.</p>
            <EventEditor event={e} keys={infoKeys} />
          </>
        )}
        {(tab === "rounds" || tab === "tracks" || tab === "prizes") && <CrudPanel key={tab} eventId={e.id} kind={tab} />}
        {tab === "roles" && <RolesPanel eventId={e.id} roles={["judge", "mentor"]} />}
        {tab === "teams" && <TeamsPanel eventId={e.id} review />}
        {tab === "registrations" && <RegistrationsPanel eventId={e.id} />}
        {tab === "submissions" && (
          <>
            <h2 className="mb-4 text-xl font-black">Bài nộp theo vòng</h2>
            <RoundSubmissionsPanel eventId={e.id} />
          </>
        )}
        {tab === "progress" && <CommitOverviewPanel eventId={e.id} teamExtra={(teamId) => <AiQuality teamId={teamId} mode="organizer" canReadFlags />} />}
        {tab === "ai" && <AiConfigPanel event={e} onSaved={cacheEvent} />}
        {tab === "mentors" && <MentorAssignmentsPanel eventId={e.id} />}
        {tab === "judging" && <JudgingPanel eventId={e.id} />}
        {tab === "announcements" && (
          <div className="space-y-8">
            <div>
              <h2 className="mb-4 text-xl font-black">Gửi thông báo</h2>
              <AnnouncementForm eventId={e.id} closed={e.status === "closed"} />
            </div>
            <div className="border-t-2 border-dashed border-line pt-6">
              <h2 className="mb-4 text-xl font-black">Đã gửi</h2>
              <AnnouncementList eventId={e.id} showAudience />
            </div>
          </div>
        )}
      </section>
    </main>
  );
}
