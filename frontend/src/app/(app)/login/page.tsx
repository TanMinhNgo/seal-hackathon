import type { Metadata } from "next";
import { AuthCard } from "@/features/auth/auth-card";
import { LoginForm } from "@/features/auth/login-form";

export const metadata: Metadata = { title: "Đăng nhập · SEAL" };

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ next?: string | string[] }> }) {
  const { next } = await searchParams;
  return (
    <AuthCard title="Đăng nhập">
      <LoginForm next={typeof next === "string" ? next : undefined} />
    </AuthCard>
  );
}
