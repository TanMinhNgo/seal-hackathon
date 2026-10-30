import type { Metadata } from "next";
import { RequireAuth } from "@/features/auth/require-auth";
import { MyTeam } from "@/features/teams/my-team";

export const metadata: Metadata = { title: "Đội của tôi · SEAL" };

export default async function MyTeamPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return (
    <RequireAuth member>
      <MyTeam slug={slug} />
    </RequireAuth>
  );
}
