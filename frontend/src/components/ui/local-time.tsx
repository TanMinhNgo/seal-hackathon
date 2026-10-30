"use client";

import { formatDate, formatDateTime } from "@/lib/datetime";

// Server render theo múi giờ server; trình duyệt render lại theo giờ máy người xem nên bỏ cảnh báo lệch hydrate
export function LocalTime({ iso, dateOnly = false }: { iso: string; dateOnly?: boolean }) {
  return (
    <time dateTime={iso} suppressHydrationWarning>
      {dateOnly ? formatDate(iso) : formatDateTime(iso)}
    </time>
  );
}
