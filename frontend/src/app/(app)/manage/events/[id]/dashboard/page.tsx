import type { Metadata } from "next";
import { RequireAuth } from "@/features/auth/require-auth";
import { EventDashboard } from "@/features/reports/reports";

export const metadata: Metadata = { title: "Dashboard cuộc thi · SEAL" };

export default async function EventDashboardPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <RequireAuth eventRole="organizer" eventId={id}>
      <EventDashboard eventId={id} />
    </RequireAuth>
  );
}
