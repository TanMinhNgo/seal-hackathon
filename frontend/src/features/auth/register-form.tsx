"use client";

import { useMutation } from "@tanstack/react-query";
import Link from "next/link";
import type { FormEvent } from "react";
import { buttonClass } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { api, errorCode, errorMessage } from "@/lib/api";
import type { components } from "@/lib/api-types";
import { FormError } from "./auth-card";
import { ResendVerification } from "./resend-verification";

type RegisterInput = components["schemas"]["RegisterInput"];

export function RegisterForm() {
  const register = useMutation({ mutationFn: (body: RegisterInput) => api.post("/auth/register", body) });
  // Hàng đợi mail lỗi nhưng tài khoản đã lưu: vẫn coi như đăng ký xong, cho gửi lại thư
  const queued = errorCode(register.error) === "EMAIL_QUEUE_UNAVAILABLE";

  if ((register.isSuccess || queued) && register.variables) {
    return (
      <div className="space-y-4">
        {queued ? (
          <FormError>{errorMessage(register.error)}</FormError>
        ) : (
          <p role="status">
            Đã gửi thư xác thực tới <b>{register.variables.email}</b>. Mở thư và bấm liên kết để kích hoạt tài khoản.
          </p>
        )}
        <ResendVerification email={register.variables.email} justSent />
        <p className="text-sm text-muted">Sau khi đăng nhập, thí sinh vào mục Đăng ký dự thi ở trang chủ để lập đội.</p>
        <Link href="/login" className={buttonClass("primary", "w-full")}>
          Tới trang đăng nhập
        </Link>
      </div>
    );
  }

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    register.mutate({ full_name: String(fd.get("full_name")), email: String(fd.get("email")), password: String(fd.get("password")) });
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      {/* Vai trò gắn theo từng cuộc thi (đặc tả 3.1) nên form không cho chọn vai trò */}
      <div className="rounded-xl border-2 border-dashed border-ink bg-cream px-4 py-3 text-sm leading-relaxed">
        <p>
          Đây là bước <b>tạo tài khoản</b>, chưa phải đăng ký dự thi. Sau khi xác thực email và đăng nhập, thí sinh vào{" "}
          <b>Đăng ký dự thi</b> để lập hoặc tham gia đội.
        </p>
        <p className="mt-1.5 text-muted">Giám khảo, mentor và ban tổ chức cũng tạo tài khoản ở đây; ban tổ chức sẽ cấp vai trò cho bạn trong từng cuộc thi.</p>
      </div>
      <Field label="Họ và tên" name="full_name" autoComplete="name" required maxLength={100} />
      <Field label="Email" name="email" type="email" autoComplete="email" required maxLength={254} />
      <Field label="Mật khẩu (tối thiểu 8 ký tự)" name="password" type="password" autoComplete="new-password" required minLength={8} maxLength={128} />
      {register.isError && <FormError>{errorMessage(register.error)}</FormError>}
      <button type="submit" className={buttonClass("primary", "w-full")} disabled={register.isPending}>
        {register.isPending ? "Đang tạo tài khoản…" : "Đăng ký"}
      </button>
      <p className="text-sm">
        Đã có tài khoản?{" "}
        <Link href="/login" className="font-bold underline">
          Đăng nhập
        </Link>
      </p>
    </form>
  );
}
