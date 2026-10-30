import type { Metadata } from "next";
import { RequireAuth } from "@/features/auth/require-auth";
import { MentorView } from "@/features/mentor/mentor-view";

export const metadata: Metadata = { title: "Mentor · SEAL" };

export default function MentorPage() {
  return (
    <RequireAuth eventRole="mentor">
      <MentorView />
    </RequireAuth>
  );
}
