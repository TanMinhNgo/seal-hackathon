"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { buttonClass } from "@/components/ui/button";
import { api } from "@/lib/api";
import { useAuth } from "@/stores/auth";
import { hasRole, useMyEventRoles } from "./use-event-roles";

const ADMIN_LINKS = [
  { href: "/admin", label: "Tổng quan" },
  { href: "/admin/events", label: "Cuộc thi" },
  { href: "/admin/users", label: "Tài khoản" },
  { href: "/admin/audit-logs", label: "Nhật ký" },
];
const LINK = "rounded-full px-3 py-3 text-[15px] font-semibold hover:bg-cream aria-[current=page]:bg-cream";

/** Mỗi vai trò chỉ thấy màn của mình (đặc tả 3.1). */
function useNavLinks() {
  const user = useAuth((s) => s.user);
  const roles = useMyEventRoles().data ?? [];
  if (user?.is_admin) return ADMIN_LINKS;
  const links = [{ href: "/events", label: "Cuộc thi" }];
  if (!user) return links;
  links.push({ href: "/dashboard", label: "Cuộc thi của tôi" });
  if (hasRole(roles, "judge")) links.push({ href: "/judge", label: "Chấm điểm" });
  if (hasRole(roles, "mentor")) links.push({ href: "/mentor", label: "Mentor" });
  return links;
}

export function MainNav() {
  const { status, user } = useAuth();
  const links = useNavLinks();
  const pathname = usePathname();
  const router = useRouter();

  async function logout() {
    // Dù server lỗi vẫn xóa phiên ở client
    await api.post("/auth/logout").catch(() => undefined);
    useAuth.getState().clear();
    router.push("/");
  }

  return (
    <>
      {status !== "loading" &&
        links.map((l) => (
          <Link key={l.href} href={l.href} aria-current={pathname === l.href ? "page" : undefined} className={LINK}>
            {l.label}
          </Link>
        ))}
      {status === "guest" && (
        <>
          <Link href="/login" className={LINK}>
            Đăng nhập
          </Link>
          <Link href="/register" className={buttonClass("accent")}>
            Tạo tài khoản
          </Link>
        </>
      )}
      {user && (
        <>
          <Link href="/profile" className={`max-w-48 truncate font-bold ${LINK}`}>
            {user.full_name}
          </Link>
          <button type="button" onClick={logout} className={buttonClass("secondary")}>
            Đăng xuất
          </button>
        </>
      )}
    </>
  );
}
