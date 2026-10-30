"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { buttonClass } from "@/components/ui/button";
import { FormError } from "@/features/auth/auth-card";
import type { Team } from "@/features/events/types";
import { api, errorMessage } from "@/lib/api";

/** Trang mở từ link mời: người dùng tự bấm xin vào đội, không tự gửi khi mở link. */
export function JoinTeam({ code }: { code?: string }) {
  const queryClient = useQueryClient();
  const join = useMutation({
    mutationFn: async () => (await api.post<Team>("/teams/join", { invite_code: code })).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["my-events"] }),
  });

  return (
    <main className="mx-auto max-w-[560px] px-4 pb-24 pt-14 sm:px-6">
      <div className="sketch -rotate-[0.6deg] bg-cream p-8">
        <p className="font-serif text-lg italic">Lời mời vào đội</p>
        {!code ? (
          <div className="mt-4">
            <FormError>Link thiếu mã mời. Hãy mở lại link trưởng nhóm gửi.</FormError>
          </div>
        ) : join.isSuccess ? (
          <>
            <h1 className="mt-2 break-words text-[40px] font-black leading-none tracking-[-0.045em]">{join.data.name}</h1>
            <p role="status" className="mt-4 leading-relaxed">Đã gửi yêu cầu. Trưởng nhóm sẽ duyệt bạn vào đội.</p>
            <Link href="/dashboard" className={buttonClass("primary", "mt-5")}>
              Cuộc thi của tôi
            </Link>
          </>
        ) : (
          <>
            <h1 className="mt-2 text-[40px] font-black leading-none tracking-[-0.045em]">Xin vào đội</h1>
            <p className="mt-4 leading-relaxed">Bạn cần đã đăng ký dự thi cuộc thi của đội này. Trưởng nhóm sẽ duyệt bạn vào đội.</p>
            {join.isError && (
              <div className="mt-4 space-y-3">
                <FormError>{errorMessage(join.error)}</FormError>
                <Link href="/events" className="inline-block text-sm font-bold underline">
                  Tới danh sách cuộc thi để đăng ký
                </Link>
              </div>
            )}
            <button type="button" className={buttonClass("primary", "mt-5")} disabled={join.isPending} onClick={() => join.mutate()}>
              {join.isPending ? "Đang gửi…" : "Xin vào đội"}
            </button>
          </>
        )}
      </div>
      <p className="mt-6 text-center text-sm text-muted">Mỗi người chỉ ở một đội trong một cuộc thi.</p>
    </main>
  );
}
