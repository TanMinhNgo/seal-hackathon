import type { Metadata } from "next";
import { RequireAuth } from "@/features/auth/require-auth";
import { JudgingView } from "@/features/judging/judging-view";

export const metadata: Metadata = { title: "Chấm điểm · SEAL" };

// shortcut: hiện thẳng một bài được giao; tách /judge (danh sách) và /judge/[assignmentId] khi nối API Phase 4
export default function JudgePage() {
  return (
    <RequireAuth eventRole="judge">
      <JudgingView />
    </RequireAuth>
  );
}
