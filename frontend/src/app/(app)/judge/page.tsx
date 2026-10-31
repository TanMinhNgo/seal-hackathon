import type { Metadata } from "next";
import { RequireAuth } from "@/features/auth/require-auth";
import { JudgeHome } from "@/features/judging/judge";

export const metadata: Metadata = { title: "Chấm điểm · SEAL" };

export default async function JudgePage({ searchParams }: { searchParams: Promise<{ event?: string }> }) {
  const { event } = await searchParams;
  return (
    <RequireAuth eventRole="judge" eventId={event}>
      <JudgeHome eventId={event} />
    </RequireAuth>
  );
}
