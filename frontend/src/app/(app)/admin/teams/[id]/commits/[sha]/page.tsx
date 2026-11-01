import type { Metadata } from "next";
import { AdminCommit } from "@/features/admin/admin-commit";

export const metadata: Metadata = { title: "Commit · Quản trị · SEAL" };

export default async function AdminCommitPage({ params }: { params: Promise<{ id: string; sha: string }> }) {
  const { id, sha } = await params;
  return <AdminCommit teamId={id} sha={sha} />;
}
