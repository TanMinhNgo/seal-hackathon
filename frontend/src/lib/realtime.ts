"use client";

import { useEffect, useEffectEvent } from "react";
import { io, type Socket } from "socket.io-client";
import { useAuth } from "@/stores/auth";
import { api, refreshAccessToken } from "./api";

let socket: Socket | null = null;
// Server từ chối join (mất quyền, room sai) thì chỉ ghi cảnh báo: dữ liệu vẫn lấy qua REST
const join = (s: Socket, room: string) => s.emit("join", { room }, (ack?: { ok: boolean; code?: string }) => ack?.ok || console.warn(`[realtime] join ${room}: ${ack?.code ?? "no ack"}`));
let retryTimer: ReturnType<typeof setTimeout> | undefined;
// Server không có lệnh rời room: chỉ những room còn component dùng mới được join lại khi nối lại
const rooms = new Map<string, number>();

const expiresSoon = (token: string) => {
  try {
    return JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))).exp * 1000 < Date.now() + 30_000;
  } catch {
    return true;
  }
};

// Server ngắt (token hết hạn, mất quyền, Redis lỗi) thì client không tự nối lại; làm mới token nếu cần rồi nối lại sau 5 giây
function recover(s: Socket) {
  clearTimeout(retryTimer);
  retryTimer = setTimeout(async () => {
    const token = useAuth.getState().accessToken;
    if (token && expiresSoon(token)) await refreshAccessToken().catch(() => undefined);
    if (!s.connected) s.connect();
  }, 5_000);
}

function getSocket() {
  if (socket) return socket;
  const s = io(new URL(api.defaults.baseURL ?? "", window.location.href).origin, {
    // Hàm auth chạy lại mỗi lần nối nên luôn gửi access token mới nhất
    auth: (cb) => cb(useAuth.getState().accessToken ? { token: useAuth.getState().accessToken } : {}),
    transports: ["websocket"],
  });
  s.on("connect", () => rooms.forEach((_, room) => join(s, room)));
  s.on("disconnect", (reason) => reason === "io server disconnect" && recover(s));
  s.on("connect_error", () => !s.active && recover(s));
  // Server chốt quyền theo token lúc connect: đăng nhập, đăng xuất hay refresh đều phải nối lại
  useAuth.subscribe((state, prev) => {
    if (state.accessToken !== prev.accessToken) s.disconnect().connect();
  });
  socket = s;
  return s;
}

/**
 * Vào `room` và gọi handler khi có sự kiện tương ứng. Handler chỉ nên refetch/invalidate, không ghép payload vào cache.
 * Mỗi lần nối lại cũng gọi mọi handler để bù sự kiện lỡ trong lúc mất kết nối.
 */
export function useRealtime(room: string | null | undefined, handlers: Record<string, () => void>) {
  const names = Object.keys(handlers).join(",");
  const fire = useEffectEvent((name?: string) => (name ? handlers[name]?.() : Object.values(handlers).forEach((h) => h())));

  useEffect(() => {
    if (!room) return;
    const s = getSocket();
    rooms.set(room, (rooms.get(room) ?? 0) + 1);
    if (s.connected) join(s, room);
    let seen = s.connected;
    const onConnect = () => {
      if (seen) fire();
      seen = true;
    };
    const listeners = names.split(",").map((name) => [name, () => fire(name)] as const);
    s.on("connect", onConnect);
    listeners.forEach(([name, fn]) => s.on(name, fn));
    return () => {
      s.off("connect", onConnect);
      listeners.forEach(([name, fn]) => s.off(name, fn));
      const left = (rooms.get(room) ?? 1) - 1;
      if (left) rooms.set(room, left);
      else rooms.delete(room);
    };
  }, [room, names]);
}
