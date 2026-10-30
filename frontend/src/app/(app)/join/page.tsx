import type { Metadata } from "next";
import { RequireAuth } from "@/features/auth/require-auth";
import { JoinTeam } from "@/features/teams/join-team";

export const metadata: Metadata = { title: "Tham gia đội · SEAL" };

export default async function JoinPage({ searchParams }: { searchParams: Promise<{ code?: string | string[] }> }) {
  const { code } = await searchParams;
  return (
    <RequireAuth member>
      <JoinTeam code={typeof code === "string" ? code : undefined} />
    </RequireAuth>
  );
}
