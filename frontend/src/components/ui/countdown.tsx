"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

const pad = (n: number) => String(n).padStart(2, "0");

// Độ lệch (ms) giữa giờ server và giờ máy, đo một lần mỗi phiên; máy chạy sai giờ vẫn đếm đúng hạn nộp
let skew = 0;
let skewLoad: Promise<void> | null = null;
function loadSkew() {
  skewLoad ??= (async () => {
    const t0 = Date.now();
    const { data } = await api.get<{ now: string }>("/time");
    skew = Date.parse(data.now) - (t0 + Date.now()) / 2;
  })().catch(() => {});
  return skewLoad;
}

/** Giờ hiện tại theo server (ms), dùng cho hiển thị; quyết định thật vẫn ở server. */
export const serverNow = () => Date.now() + skew;

/** Giây còn lại tới `target`; null cho tới khi chạy ở client để tránh lệch hydrate. */
export function useSecondsLeft(target: string) {
  const [left, setLeft] = useState<number | null>(null);
  useEffect(() => {
    const end = Date.parse(target);
    const tick = () => setLeft(Math.max(0, Math.floor((end - serverNow()) / 1000)));
    loadSkew().then(tick);
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
