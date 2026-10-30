import type { Metadata } from "next";
import { ProfileView } from "@/features/auth/profile-form";
import { RequireAuth } from "@/features/auth/require-auth";

export const metadata: Metadata = { title: "Hồ sơ · SEAL" };

export default function ProfilePage() {
  return (
    <RequireAuth>
      <ProfileView />
    </RequireAuth>
  );
}
