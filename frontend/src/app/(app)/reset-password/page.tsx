import type { Metadata } from "next";
import { AuthCard } from "@/features/auth/auth-card";
import { ResetPasswordForm } from "@/features/auth/reset-password-form";

export const metadata: Metadata = { title: "Đặt lại mật khẩu · SEAL" };

export default async function ResetPasswordPage({ searchParams }: { searchParams: Promise<{ token?: string | string[] }> }) {
  const { token } = await searchParams;
  return (
    <AuthCard title="Đặt lại mật khẩu">
      <ResetPasswordForm token={typeof token === "string" ? token : undefined} />
    </AuthCard>
  );
}
