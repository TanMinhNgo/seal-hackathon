"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { FormEvent } from "react";
import { buttonClass } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { api, errorCode, errorMessage } from "@/lib/api";
import type { components } from "@/lib/api-types";
import { useAuth, type User } from "@/stores/auth";
import { FormError } from "./auth-card";
import { ResendVerification } from "./resend-verification";
import { homeFor } from "./use-event-roles";

type LoginInput = components["schemas"]["LoginInput"];
type Token = components["schemas"]["TokenOutput"];

// Chỉ nhận đường dẫn nội bộ để `next` không thành open redirect ("//evil.com", "/\evil.com")
export const safeNext = (next: string | undefined, fallback: string) => (next && /^\/(?![/\\])/.test(next) ? next : fallback);

export function LoginForm({ next }: { next?: string }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const login = useMutation({
    mutationFn: async (body: LoginInput) => {
      const { data } = await api.post<Token>("/auth/login", body);
      useAuth.getState().setToken(data.access_token);
      const { data: user } = await api.get<User>("/users/me");
      // Bỏ dữ liệu của phiên trước (người khác có thể vừa dùng máy này)
      queryClient.clear();
      useAuth.getState().setUser(user);
      return homeFor(user);
    },
    onSuccess: (home) => router.replace(safeNext(next, home)),
  });

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    login.mutate({ email: String(fd.get("email")), password: String(fd.get("password")) });
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <Field label="Email" name="email" type="email" autoComplete="email" required maxLength={254} />
      <Field label="Mật khẩu" name="password" type="password" autoComplete="current-password" required maxLength={128} />
      <Link href="/forgot-password" className="inline-block text-sm font-semibold underline">
        Quên mật khẩu?
      </Link>
      {login.isError && <FormError>{errorMessage(login.error)}</FormError>}
      {errorCode(login.error) === "EMAIL_NOT_VERIFIED" && login.variables && <ResendVerification email={login.variables.email} />}
      <button type="submit" className={buttonClass("primary", "w-full")} disabled={login.isPending}>
        {login.isPending ? "Đang đăng nhập…" : "Đăng nhập"}
      </button>
      <p className="text-sm">
        Chưa có tài khoản?{" "}
        <Link href="/register" className="font-bold underline">
          Tạo tài khoản
        </Link>
      </p>
    </form>
  );
}
