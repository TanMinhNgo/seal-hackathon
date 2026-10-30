"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { useAuth } from "@/stores/auth";
import { hasRole, homeFor, useMyEventRoles, type Role } from "./use-event-roles";

/**
 * Chặn trang theo vai trò. Chỉ là UX; quyền thật do server quyết định.
 * - `admin`: chỉ admin vào được.
 * - `member`: mọi tài khoản trừ admin (admin không làm việc nghiệp vụ cuộc thi).
 * - `eventRole` (+ `eventId`): chỉ người giữ vai trò đó, trong đúng cuộc thi nếu có `eventId`.
 */
export function RequireAuth({
  admin = false,
  member = false,
  eventRole,
  eventId,
  children,
}: {
  admin?: boolean;
  member?: boolean;
  eventRole?: Role;
  eventId?: string;
  children: ReactNode;
}) {
  const { status, user } = useAuth();
  const roles = useMyEventRoles();
  const router = useRouter();
  const pathname = usePathname();

  // null = chưa đủ dữ liệu để quyết định
  let allowed: boolean | null = null;
  if (user) {
    if (admin) allowed = user.is_admin;
    else if (user.is_admin) allowed = !member && !eventRole;
    else if (!eventRole) allowed = true;
    else if (roles.isError) allowed = false;
    else if (roles.data) allowed = hasRole(roles.data, eventRole, eventId);
  }

  useEffect(() => {
    // Giữ cả query (vd. ?code= của link mời) để đăng nhập xong quay lại đúng chỗ
    if (status === "guest") router.replace(`/login?next=${encodeURIComponent(pathname + window.location.search)}`);
    else if (allowed === false && user) router.replace(homeFor(user));
  }, [status, allowed, user, router, pathname]);

  if (!allowed) return <p role="status" className="px-6 pt-12 text-center">Đang tải…</p>;
  return children;
}
