"use client";

import { useMutation } from "@tanstack/react-query";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { buttonClass } from "@/components/ui/button";
import { useSecondsLeft } from "@/components/ui/countdown";
import { Field } from "@/components/ui/field";
import { api, errorMessage } from "@/lib/api";
import { FormError } from "./auth-card";
import { in60s } from "./resend-verification";

export function ForgotPasswordForm() {
  const [until, setUntil] = useState(() => new Date(0).toISOString());
  const left = useSecondsLeft(until);
  const forgot = useMutation({
    mutationFn: (email: string) => api.post("/auth/forgot-password", { email }),
    onSettled: () => setUntil(in60s()),
  });

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    forgot.mutate(String(new FormData(e.currentTarget).get("email")));
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <Field label="Email" name="email" type="email" autoComplete="email" required maxLength={254} />
      {/* Luôn cùng một câu để không lộ email có tồn tại hay không */}
      {forgot.isSuccess && <p role="status">Nếu tài khoản hợp lệ, hướng dẫn đặt lại mật khẩu sẽ được gửi tới email này.</p>}
      {forgot.isError && <FormError>{errorMessage(forgot.error)}</FormError>}
      <button type="submit" className={buttonClass("primary", "w-full")} disabled={forgot.isPending || left !== 0}>
        {left ? `Gửi lại sau ${left}s` : forgot.isPending ? "Đang gửi…" : "Gửi hướng dẫn"}
      </button>
      <Link href="/login" className="inline-block text-sm font-semibold underline">
        Quay lại đăng nhập
      </Link>
    </form>
  );
}
