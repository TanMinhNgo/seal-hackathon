import type { ReactNode } from "react";
import { RequireAuth } from "@/features/auth/require-auth";

export default function AdminLayout({ children }: { children: ReactNode }) {
  return (
    <RequireAuth admin>
      <main className="mx-auto max-w-[1360px] px-4 pb-24 pt-8 sm:px-6">{children}</main>
    </RequireAuth>
  );
}
