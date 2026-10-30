import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { errorCode } from "@/lib/api";

/** Bị thu hồi quyền admin giữa chừng thì rời khu quản trị. */
export function useLeaveOnForbidden(error: unknown) {
  const router = useRouter();
  const forbidden = errorCode(error) === "FORBIDDEN";
  useEffect(() => {
    if (forbidden) router.replace("/");
  }, [forbidden, router]);
}
