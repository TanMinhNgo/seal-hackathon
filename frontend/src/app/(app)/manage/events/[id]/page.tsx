import type { Metadata } from "next";
import { RequireAuth } from "@/features/auth/require-auth";
import { ManageEvent } from "@/features/events/manage-event";

export const metadata: Metadata = { title: "Vận hành cuộc thi · SEAL" };

export default async function ManageEventPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <RequireAuth eventRole="organizer" eventId={id}>
      <ManageEvent eventId={id} />
    </RequireAuth>
  );
}
