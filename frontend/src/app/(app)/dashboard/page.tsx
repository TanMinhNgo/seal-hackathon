import type { Metadata } from "next";
import { RequireAuth } from "@/features/auth/require-auth";
import { MyEvents } from "@/features/events/my-events";

export const metadata: Metadata = { title: "Cuộc thi của tôi · SEAL" };

export default function DashboardPage() {
  return (
    <RequireAuth member>
      <MyEvents />
    </RequireAuth>
  );
}
