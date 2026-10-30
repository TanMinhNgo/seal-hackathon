import type { Metadata } from "next";
import { AdminEventDetail } from "@/features/admin/admin-event-detail";

export const metadata: Metadata = { title: "Hồ sơ cuộc thi · Quản trị · SEAL" };

export default async function AdminEventPage({ params }: { params: Promise<{ id: string }> }) {
  return <AdminEventDetail eventId={(await params).id} />;
}
