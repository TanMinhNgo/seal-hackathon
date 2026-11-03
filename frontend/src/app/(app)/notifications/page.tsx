import type { Metadata } from "next";
import { RequireAuth } from "@/features/auth/require-auth";
import { NotificationList } from "@/features/notifications/notifications";

export const metadata: Metadata = { title: "Thông báo · SEAL" };

export default function NotificationsPage() {
  return (
    <RequireAuth>
      <main className="mx-auto max-w-3xl px-4 pb-24 pt-10 sm:px-6">
        <h1 className="mb-6 text-[clamp(36px,5vw,56px)] font-black leading-none tracking-[-0.045em]">Thông báo.</h1>
        <NotificationList />
      </main>
    </RequireAuth>
  );
}
