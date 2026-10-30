import type { Metadata } from "next";
import { AuthCard } from "@/features/auth/auth-card";
import { RegisterForm } from "@/features/auth/register-form";

export const metadata: Metadata = { title: "Đăng ký · SEAL" };

export default function RegisterPage() {
  return (
    <AuthCard title="Tạo tài khoản">
      <RegisterForm />
    </AuthCard>
  );
}
