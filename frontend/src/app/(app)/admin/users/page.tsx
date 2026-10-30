import type { Metadata } from "next";
import { AdminTitle } from "@/features/admin/admin-title";
import { AdminUsers } from "@/features/admin/admin-users";

export const metadata: Metadata = { title: "Tài khoản · Quản trị · SEAL" };

export default function AdminUsersPage() {
  return (
    <>
      <AdminTitle kicker="Quản trị hệ thống">Tài khoản.</AdminTitle>
      <AdminUsers />
    </>
  );
}
