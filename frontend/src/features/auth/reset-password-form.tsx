"use client";

import { useMutation } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { buttonClass } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { api, errorCode, errorMessage } from "@/lib/api";
import type { components } from "@/lib/api-types";
import { useAuth } from "@/stores/auth";
import { FormError } from "./auth-card";

type ResetPasswordInput = components["schemas"]["ResetPasswordInput"];

export function ResetPasswordForm({ token }: { token?: string }) {
  // Giữ token trong state rồi xóa khỏi URL để không nằm lại trong lịch sử trình duyệt
  const [saved] = useState(token);
  useEffect(() => {
    if (token) window.history.replaceState(null, "", "/reset-password");
  }, [token]);

  const reset = useMutation({
    mutationFn: (body: ResetPasswordInput) => api.post("/auth/reset-password", body),
    // BE thu hồi mọi phiên cũ sau khi đổi mật khẩu
    onSuccess: () => useAuth.getState().clear(),
  });

  if (!saved) return <FormError>Liên kết thiếu mã đặt lại. Hãy mở lại liên kết trong email.</FormError>;
  if (reset.isSuccess)
    return (
      <div className="space-y-4">
        <p role="status">Đã đổi mật khẩu. Hãy đăng nhập lại bằng mật khẩu mới.</p>
        <Link href="/login" className={buttonClass("primary", "w-full")}>
          Đăng nhập
        </Link>
      </div>
    );

  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    reset.mutate({ token: saved, new_password: String(new FormData(e.currentTarget).get("new_password")) });
  };

  return (
    <form onSubmit={submit} className="space-y-4">
      <Field label="Mật khẩu mới (tối thiểu 8 ký tự)" name="new_password" type="password" autoComplete="new-password" required minLength={8} maxLength={128} />
      {reset.isError && <FormError>{errorMessage(reset.error)}</FormError>}
      {errorCode(reset.error) === "INVALID_TOKEN" && (
        <Link href="/forgot-password" className="inline-block text-sm font-semibold underline">
          Xin liên kết mới
        </Link>
      )}
      <button type="submit" className={buttonClass("primary", "w-full")} disabled={reset.isPending}>
        {reset.isPending ? "Đang lưu…" : "Đổi mật khẩu"}
      </button>
    </form>
  );
}
