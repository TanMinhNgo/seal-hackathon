"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState, type CSSProperties } from "react";
import { LocalTime } from "@/components/ui/local-time";
import { Pager } from "@/components/ui/pager";
import { FormError } from "@/features/auth/auth-card";
import { api, errorMessage } from "@/lib/api";
import type { components } from "@/lib/api-types";
import { useRealtime } from "@/lib/realtime";
import { useAuth } from "@/stores/auth";

type Notification = components["schemas"]["NotificationOutput"];
type NotificationPage = components["schemas"]["NotificationPage"];

const LIMIT = 20;
// Server chỉ tạo link nội bộ; chặn thêm ở client để không thành open redirect nếu dữ liệu lỗi
const internal = (link: string) => link.startsWith("/") && !link.startsWith("//");

function useNotifications(params: { unread?: boolean; limit: number; offset: number }) {
  const userId = useAuth((s) => s.user?.id);
  return useQuery({
    queryKey: ["notifications", userId, params],
    queryFn: async () => (await api.get<NotificationPage>("/me/notifications", { params: { ...params, unread: params.unread || undefined } })).data,
    enabled: !!userId,
    placeholderData: keepPreviousData,
  });
}

function useMarkRead() {
  const queryClient = useQueryClient();
  const onSuccess = () => queryClient.invalidateQueries({ queryKey: ["notifications"] });
  return {
    one: useMutation({ mutationFn: (id: string) => api.post(`/me/notifications/${id}/read`), onSuccess }),
    all: useMutation({ mutationFn: () => api.post("/me/notifications/read-all"), onSuccess }),
  };
}

function Item({ n, onOpen }: { n: Notification; onOpen: (n: Notification) => void }) {
  const body = (
    <>
      <span className="flex items-start justify-between gap-3">
        <b className={n.read_at ? "font-semibold" : "font-black"}>{n.title}</b>
        {!n.read_at && <span className="mt-1.5 size-2.5 shrink-0 rounded-full bg-orange" aria-label="Chưa đọc" />}
      </span>
      {n.body && <span className="mt-0.5 block whitespace-pre-line text-sm text-muted">{n.body}</span>}
      <span className="mt-1 block font-mono text-xs text-muted">
        <LocalTime iso={n.created_at} />
      </span>
    </>
  );
  const cls = "block w-full rounded-xl px-3 py-2.5 text-left hover:bg-cream";
  return internal(n.link) ? (
    <Link href={n.link} className={cls} onClick={() => onOpen(n)}>
      {body}
    </Link>
  ) : (
    <button type="button" className={cls} onClick={() => onOpen(n)}>
      {body}
    </button>
  );
}

/** Chuông ở header: số chưa đọc, 5 thông báo mới nhất; nhận `notification:new` qua room riêng của user. */
export function NotificationBell() {
  const user = useAuth((s) => s.user);
  const [open, setOpen] = useState(false);
  // Màn hẹp: panel cố định theo viewport, ngay dưới nút chuông (header xuống dòng nên cao thấp khác nhau)
  const [top, setTop] = useState(80);
  const box = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();
  const list = useNotifications({ limit: 5, offset: 0 });
  const mark = useMarkRead();
  // Announcement mới cũng đến dưới dạng notification nên làm mới cả danh sách thông báo của cuộc thi
  useRealtime(user && `user:${user.id}`, { "notification:new": () => ["notifications", "announcements"].forEach((k) => queryClient.invalidateQueries({ queryKey: [k] })) });

  // Bấm ra ngoài hoặc Esc thì đóng
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !box.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  if (!user) return null;
  const unread = list.data?.unread_count ?? 0;
  const openItem = (n: Notification) => {
    if (!n.read_at) mark.one.mutate(n.id);
    setOpen(false);
  };

  return (
    <div ref={box} className="relative">
      <button
        type="button"
        aria-expanded={open}
        aria-controls="notification-panel"
        aria-label={unread ? `Thông báo, ${unread} chưa đọc` : "Thông báo"}
        onClick={(e) => {
          setTop(e.currentTarget.getBoundingClientRect().bottom + 8);
          setOpen((v) => !v);
        }}
        className="relative grid size-11 place-items-center rounded-full hover:bg-cream"
      >
        <Bell aria-hidden className="size-5" />
        {unread > 0 && <span className="absolute right-0.5 top-0.5 min-w-5 rounded-full border-2 border-paper bg-orange px-1 text-center font-mono text-[11px] font-extrabold leading-4">{unread > 99 ? "99+" : unread}</span>}
      </button>
      {open && (
        <div id="notification-panel" style={{ "--panel-top": `${top}px` } as CSSProperties} className="sketch fixed inset-x-4 top-(--panel-top) z-30 bg-paper p-2 sm:absolute sm:inset-x-auto sm:right-0 sm:top-12 sm:w-[360px]">
          <div className="flex items-center justify-between px-3 py-1.5">
            <b>Thông báo</b>
            <button type="button" className="text-sm font-bold underline disabled:no-underline disabled:opacity-50" disabled={!unread || mark.all.isPending} onClick={() => mark.all.mutate()}>
              Đọc hết
            </button>
          </div>
          {list.isError && <FormError>{errorMessage(list.error)}</FormError>}
          {list.data?.items.length === 0 && <p className="px-3 py-4 text-sm text-muted">Chưa có thông báo.</p>}
          <ul className="max-h-[60vh] overflow-y-auto">
            {list.data?.items.map((n) => (
              <li key={n.id}>
                <Item n={n} onOpen={openItem} />
              </li>
            ))}
          </ul>
          <Link href="/notifications" onClick={() => setOpen(false)} className="mt-1 block rounded-xl px-3 py-2.5 text-center text-sm font-bold hover:bg-cream">
            Xem tất cả
          </Link>
        </div>
      )}
    </div>
  );
}

export function NotificationList() {
  const [offset, setOffset] = useState(0);
  const [unread, setUnread] = useState(false);
  const list = useNotifications({ unread, limit: LIMIT, offset });
  const mark = useMarkRead();

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <label className="inline-flex min-h-11 items-center gap-2 text-sm font-bold">
          <input
            type="checkbox"
            className="size-4 accent-ink"
            checked={unread}
            onChange={(e) => {
              setUnread(e.target.checked);
              setOffset(0);
            }}
          />
          Chỉ chưa đọc
        </label>
        <button type="button" className="btn ml-auto bg-paper" disabled={!list.data?.unread_count || mark.all.isPending} onClick={() => mark.all.mutate()}>
          Đánh dấu đã đọc hết
        </button>
      </div>
      {(list.isError || mark.all.isError) && <FormError>{errorMessage(list.error ?? mark.all.error)}</FormError>}
      {!list.data && !list.isError && <p role="status">Đang tải…</p>}
      {list.data?.items.length === 0 && <p className="text-muted">{unread ? "Không còn thông báo chưa đọc." : "Chưa có thông báo."}</p>}
      <ul className="divide-y divide-dashed divide-line">
        {list.data?.items.map((n) => (
          <li key={n.id} className="py-1">
            <Item n={n} onOpen={(x) => !x.read_at && mark.one.mutate(x.id)} />
          </li>
        ))}
      </ul>
      {list.data && list.data.total > LIMIT && <Pager offset={offset} limit={LIMIT} total={list.data.total} onChange={setOffset} />}
    </div>
  );
}
