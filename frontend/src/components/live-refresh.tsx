"use client";

import { useRouter } from "next/navigation";
import { useRealtime } from "@/lib/realtime";

/** Trang SSR công khai: có sự kiện thì render lại từ server, kể cả khi kết quả bị thu hồi. */
export function LiveRefresh({ room, events }: { room: string; events: string[] }) {
  const router = useRouter();
  useRealtime(room, Object.fromEntries(events.map((e) => [e, () => router.refresh()])));
  return null;
}
