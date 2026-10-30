import type { Metadata } from "next";
import { AuthCard } from "@/features/auth/auth-card";
import { ForgotPasswordForm } from "@/features/auth/forgot-password-form";

export const metadata: Metadata = { title: "Quên mật khẩu · SEAL" };

export default function ForgotPasswordPage() {
  return (
    <AuthCard title="Quên mật khẩu">
      <ForgotPasswordForm />
    </AuthCard>
  );
}
