import type { Metadata } from "next";
import { RequireAuth } from "@/features/auth/require-auth";
import { ScoreScreen } from "@/features/judging/judge";

export const metadata: Metadata = { title: "Chấm bài · SEAL" };

export default async function ScorePage({ params }: { params: Promise<{ assignmentId: string }> }) {
  const { assignmentId } = await params;
  return (
    <RequireAuth eventRole="judge">
      <ScoreScreen assignmentId={assignmentId} />
    </RequireAuth>
  );
}
