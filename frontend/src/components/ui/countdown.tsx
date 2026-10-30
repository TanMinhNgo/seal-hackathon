"use client";

import { useEffect, useState } from "react";

const pad = (n: number) => String(n).padStart(2, "0");

/** Giây còn lại tới `target`; null cho tới khi chạy ở client để tránh lệch hydrate. */
export function useSecondsLeft(target: string) {
  const [left, setLeft] = useState<number | null>(null);
  useEffect(() => {
    const end = Date.parse(target);
    // shortcut: dùng đồng hồ máy; đổi sang bù lệch theo GET /time khi nối API (Phase 0)
    const tick = () => setLeft(Math.max(0, Math.floor((end - Date.now()) / 1000)));
    const first = setTimeout(tick, 0);
    const id = setInterval(tick, 1000);
    return () => {
      clearTimeout(first);
      clearInterval(id);
    };
  }, [target]);
  return left;
}

export function splitTime(left: number | null) {
  if (left === null) return [{ value: "--", label: "ngày" }, { value: "--", label: "giờ" }, { value: "--", label: "phút" }, { value: "--", label: "giây" }];
  return [
    { value: pad(Math.floor(left / 86400)), label: "ngày" },
    { value: pad(Math.floor((left % 86400) / 3600)), label: "giờ" },
    { value: pad(Math.floor((left % 3600) / 60)), label: "phút" },
    { value: pad(left % 60), label: "giây" },
  ];
}

/** Dòng chữ ngắn "3n 09:12:40". */
export function InlineCountdown({ target }: { target: string }) {
  const parts = splitTime(useSecondsLeft(target));
  return (
    <span className="font-mono tabular-nums">
      {parts[0].value}n {parts[1].value}:{parts[2].value}:{parts[3].value}
    </span>
  );
}
