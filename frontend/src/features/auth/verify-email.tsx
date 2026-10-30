"use client";

import { useMutation } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useRef } from "react";
import { buttonClass } from "@/components/ui/button";
import { api, errorMessage } from "@/lib/api";
import { FormError } from "./auth-card";

export function VerifyEmail({ token }: { token?: string }) {
  const { mutate, isSuccess, isError, error } = useMutation({ mutationFn: (t: string) => api.post("/auth/verify-email", { token: t }) });
  // Token dùng một lần: chặn StrictMode gọi hai lần làm lần sau báo INVALID_TOKEN
  const sent = useRef(false);

  useEffect(() => {
    if (!token || sent.current) return;
    sent.current = true;
    window.history.replaceState(null, "", "/verify-email"); // không để token nằm lại trong lịch sử trình duyệt
    mutate(token);
  }, [token, mutate]);

  if (!token) return <FormError>Liên kết thiếu mã xác thực. Hãy mở lại liên kết trong email.</FormError>;
  if (isError)
    return (
      <div className="space-y-4">
        <FormError>{errorMessage(error)}</FormError>
        <p className="text-sm">Đăng nhập bằng email của bạn để gửi lại thư xác thực.</p>
        <Link href="/login" className={buttonClass("secondary", "w-full")}>
          Tới trang đăng nhập
        </Link>
      </div>
    );
  if (isSuccess)
    return (
      <div className="space-y-4">
        <p role="status">Email đã được xác thực. Bạn có thể đăng nhập.</p>
        <Link href="/login" className={buttonClass("primary", "w-full")}>
          Đăng nhập
        </Link>
      </div>
    );
  return <p role="status">Đang xác thực…</p>;
}
