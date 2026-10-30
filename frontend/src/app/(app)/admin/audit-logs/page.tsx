import type { Metadata } from "next";
import { AdminTitle } from "@/features/admin/admin-title";
import { AuditLogs } from "@/features/admin/audit-logs";

export const metadata: Metadata = { title: "Nhật ký · Quản trị · SEAL" };

export default function AuditLogsPage() {
  return (
    <>
      <AdminTitle kicker="Quản trị hệ thống">Nhật ký thao tác.</AdminTitle>
      <AuditLogs />
    </>
  );
}
