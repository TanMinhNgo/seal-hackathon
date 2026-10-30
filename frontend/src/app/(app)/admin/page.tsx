import type { Metadata } from "next";
import { AdminTitle } from "@/features/admin/admin-title";
import { SystemOverview } from "@/features/admin/system-overview";

export const metadata: Metadata = { title: "Tổng quan · Quản trị · SEAL" };

export default function AdminPage() {
  return (
    <>
      <AdminTitle kicker="Quản trị hệ thống">Tổng quan.</AdminTitle>
      <SystemOverview />
    </>
  );
}
