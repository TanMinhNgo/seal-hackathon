import type { Metadata } from "next";
import { AuthCard } from "@/features/auth/auth-card";
import { VerifyEmail } from "@/features/auth/verify-email";

export const metadata: Metadata = { title: "Xác thực email · SEAL" };

export default async function VerifyEmailPage({ searchParams }: { searchParams: Promise<{ token?: string | string[] }> }) {
  const { token } = await searchParams;
  return (
    <AuthCard title="Xác thực email">
      <VerifyEmail token={typeof token === "string" ? token : undefined} />
    </AuthCard>
  );
}
