import type { Metadata } from "next";
import { AdminTeam } from "@/features/admin/admin-team";

export const metadata: Metadata = { title: "Hồ sơ đội · Quản trị · SEAL" };

export default async function AdminTeamPage({ params }: { params: Promise<{ id: string }> }) {
  return <AdminTeam teamId={(await params).id} />;
}
