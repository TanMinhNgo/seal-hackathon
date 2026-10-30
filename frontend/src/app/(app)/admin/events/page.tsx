import type { Metadata } from "next";
import { AdminEvents } from "@/features/admin/admin-events";
import { AdminTitle } from "@/features/admin/admin-title";

export const metadata: Metadata = { title: "Cuộc thi · Quản trị · SEAL" };

export default function AdminEventsPage() {
  return (
    <>
      <AdminTitle kicker="Quản trị hệ thống">Cuộc thi.</AdminTitle>
      <AdminEvents />
    </>
  );
}
