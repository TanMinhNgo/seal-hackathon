"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useSecondsLeft } from "@/components/ui/countdown";
import { api, errorMessage } from "@/lib/api";

// BE chặn gửi lại thư (xác thực, đặt lại mật khẩu) trong 60 giây theo tài khoản
export const in60s = () => new Date(Date.now() + 60_000).toISOString();

export function ResendVerification({ email, justSent = false }: { email: string; justSent?: boolean }) {
  const [until, setUntil] = useState(() => (justSent ? in60s() : new Date(0).toISOString()));
  const left = useSecondsLeft(until);
  const resend = useMutation({
    mutationFn: () => api.post("/auth/resend-verification", { email }),
    onSettled: () => setUntil(in60s()),
  });
  return (
    <div className="space-y-2 text-sm">
      <button type="button" className="btn bg-paper" disabled={resend.isPending || left !== 0} onClick={() => resend.mutate()}>
        {left ? `Gửi lại sau ${left}s` : "Gửi lại thư xác thực"}
      </button>
      {/* 204 không có nghĩa email tồn tại hay thư đã tới hộp thư */}
      {resend.isSuccess && <p role="status">Nếu email cần xác thực, thư mới đã được gửi.</p>}
      {resend.isError && <p role="alert">{errorMessage(resend.error)}</p>}
    </div>
  );
}
