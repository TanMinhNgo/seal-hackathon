"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import type { ReactNode } from "react";
import { buttonClass } from "@/components/ui/button";
import { useSecondsLeft } from "@/components/ui/countdown";
import { FormError } from "@/features/auth/auth-card";
import { useMyEvents } from "@/features/auth/use-event-roles";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/stores/auth";
import type { Event } from "./types";

function Box({ title, tone, children }: { title: string; tone: string; children: ReactNode }) {
  return (
    <aside aria-label="Tham gia cuộc thi" className={`sketch flex-[1_1_340px] p-6 sm:max-w-[400px] ${tone}`}>
      <p className="text-xl font-black tracking-tight">{title}</p>
      <div className="mt-2 space-y-3 text-sm leading-relaxed">{children}</div>
    </aside>
  );
}

/** Ô tham gia ở trang cuộc thi: đổi theo người xem và vai trò của họ trong cuộc thi này. */
export function EventCta({ event }: { event: Event }) {
  const { status, user } = useAuth();
  const mine = useMyEvents();
  const queryClient = useQueryClient();
  const refresh = () => Promise.all([queryClient.invalidateQueries({ queryKey: ["my-events"] }), queryClient.invalidateQueries({ queryKey: ["my-event-roles"] })]);
  const register = useMutation({ mutationFn: () => api.post(`/events/${event.id}/register`), onSuccess: refresh });
  const withdraw = useMutation({ mutationFn: () => api.delete(`/events/${event.id}/register`), onSuccess: refresh });
  const error = register.error ?? withdraw.error;
  // Gợi ý theo giờ máy, tự cập nhật khi tới mốc; server quyết định cuối cùng theo giờ của nó
  const untilOpen = useSecondsLeft(event.registration_opens_at);
  const untilClose = useSecondsLeft(event.registration_closes_at);

  if (status === "loading" || (user && !user.is_admin && mine.isPending)) return null;
  const teamHref = `/events/${event.slug}/my-team`;

  if (!user)
    return (
      <Box title="Tham gia cuộc thi" tone="bg-cream">
        <p>Tạo tài khoản và xác thực email trước, rồi quay lại đây để đăng ký dự thi.</p>
        <div className="flex flex-wrap gap-2">
          <Link href="/register" className={buttonClass("accent")}>
            Tạo tài khoản
          </Link>
          <Link href={`/login?next=${encodeURIComponent(`/events/${event.slug}`)}`} className={buttonClass("secondary")}>
            Đăng nhập
          </Link>
        </div>
      </Box>
    );

  if (user.is_admin)
    return (
      <Box title="Tài khoản quản trị" tone="bg-warm">
        <p>Admin không dự thi. Xem hồ sơ cuộc thi trong khu quản trị.</p>
        <Link href={`/admin/events/${event.id}`} className={buttonClass("primary")}>
          Hồ sơ cuộc thi
        </Link>
      </Box>
    );

  const me = mine.data?.items.find((m) => m.event.id === event.id);
  const roles = me?.roles ?? [];
  if (roles.includes("organizer"))
    return (
      <Box title="Bạn là ban tổ chức" tone="bg-warm">
        <Link href={`/manage/events/${event.id}`} className={buttonClass("primary")}>
          Vận hành cuộc thi
        </Link>
      </Box>
    );
  if (roles.includes("judge") || roles.includes("mentor"))
    return (
      <Box title={roles.includes("judge") ? "Bạn là giám khảo" : "Bạn là mentor"} tone="bg-warm">
        <p>Người giữ vai trò vận hành trong cuộc thi này không được dự thi.</p>
      </Box>
    );

  if (me?.team)
    return (
      <Box title={`Đội: ${me.team.name}`} tone="bg-sun">
        <p>{me.team.member_status === "pending" ? "Bạn đang chờ trưởng nhóm duyệt vào đội." : "Bạn đã có đội trong cuộc thi này."}</p>
        <Link href={teamHref} className={buttonClass("primary")}>
          Đội của tôi
        </Link>
      </Box>
    );

  if (roles.includes("participant"))
    return (
      <Box title="Bạn đã đăng ký" tone="bg-sky">
        <p>Bước tiếp theo: lập đội mới hoặc nhập mã mời của bạn bè.</p>
        {withdraw.isError && <FormError>{errorMessage(withdraw.error)}</FormError>}
        <div className="flex flex-wrap gap-2">
          <Link href={teamHref} className={buttonClass("primary")}>
            Lập đội / vào đội
          </Link>
          <button type="button" className={buttonClass("secondary")} disabled={withdraw.isPending} onClick={() => withdraw.mutate()}>
            Rút đăng ký
          </button>
        </div>
      </Box>
    );

  const inWindow = event.status === "open" && untilOpen === 0 && !!untilClose;
  return (
    <Box title={inWindow ? "Đăng ký dự thi" : "Chưa mở đăng ký"} tone={inWindow ? "bg-mint" : "bg-warm"}>
      <p>{inWindow ? "Đăng ký xong bạn có thể lập đội hoặc nhập mã mời." : "Cuộc thi hiện không nhận đăng ký."}</p>
      {error && <FormError>{errorMessage(error)}</FormError>}
      {inWindow && (
        <button type="button" className={buttonClass("primary")} disabled={register.isPending} onClick={() => register.mutate()}>
          {register.isPending ? "Đang đăng ký…" : "Đăng ký dự thi"}
        </button>
      )}
    </Box>
  );
}
