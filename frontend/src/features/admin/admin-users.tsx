"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Pager } from "@/components/ui/pager";
import { FormError } from "@/features/auth/auth-card";
import { api, errorMessage } from "@/lib/api";
import type { components } from "@/lib/api-types";
import { useAuth, type User } from "@/stores/auth";
import { useLeaveOnForbidden } from "./use-leave-on-forbidden";

type UserPage = components["schemas"]["UserPage"];
type AdminUserInput = components["schemas"]["AdminUserInput"];
const LIMIT = 20;

export function AdminUsers() {
  const me = useAuth((s) => s.user);
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const queryClient = useQueryClient();

  const users = useQuery({
    queryKey: ["admin-users", q, offset],
    queryFn: async () => (await api.get<UserPage>("/admin/users", { params: { q: q || undefined, limit: LIMIT, offset } })).data,
    placeholderData: keepPreviousData,
  });
  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: AdminUserInput }) => api.patch<User>(`/admin/users/${id}`, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-users"] }),
  });
  useLeaveOnForbidden(users.error ?? update.error);

  function search(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setQ(String(new FormData(e.currentTarget).get("q")).trim());
    setOffset(0);
  }

  return (
    <section>
      <form role="search" onSubmit={search} className="flex flex-wrap items-end gap-2">
        <label className="min-w-0 flex-1">
          <span className="text-sm font-bold">Tìm theo email hoặc họ tên</span>
          <input name="q" type="search" maxLength={100} className="mt-1.5 block min-h-11 w-full rounded-xl border-2 border-ink bg-paper px-3.5" />
        </label>
        <button type="submit" className="btn bg-ink text-paper">
          Tìm
        </button>
      </form>

      {users.isError && <div className="mt-4"><FormError>{errorMessage(users.error)}</FormError></div>}
      {update.isError && <div className="mt-4"><FormError>{errorMessage(update.error)}</FormError></div>}

      <div className="sketch mt-5 overflow-x-auto p-0">
        <table className="w-full min-w-[720px] text-left text-sm">
          <thead className="border-b-2 border-ink bg-cream">
            <tr>
              <th className="px-4 py-3">Người dùng</th>
              <th className="px-4 py-3">Trạng thái</th>
              <th className="px-4 py-3">Tạo lúc</th>
              <th className="px-4 py-3 text-right">Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {users.data?.items.map((u) => {
              // BE cấm tự khóa/tự bỏ admin; ẩn nút để khỏi bấm nhầm
              const self = u.id === me?.id;
              const busy = update.isPending && update.variables?.id === u.id;
              return (
                <tr key={u.id} className="border-t border-line">
                  <td className="px-4 py-3">
                    <b>{u.full_name}</b>
                    <div className="text-muted">{u.email}</div>
                  </td>
                  <td className="space-x-1 px-4 py-3">
                    <span className={`chip ${u.is_active ? "bg-mint" : "bg-rose"}`}>{u.is_active ? "Hoạt động" : "Đã khóa"}</span>
                    {u.is_admin && <span className="chip bg-sky">Admin</span>}
                    {!u.email_verified && <span className="chip bg-sun">Chưa xác thực</span>}
                  </td>
                  <td className="px-4 py-3">{new Date(u.created_at).toLocaleString("vi-VN")}</td>
                  <td className="px-4 py-3 text-right">
                    {self ? (
                      <span className="text-muted">Tài khoản của bạn</span>
                    ) : (
                      <span className="inline-flex gap-2">
                        <button type="button" className="btn bg-paper" disabled={busy} onClick={() => update.mutate({ id: u.id, body: { is_active: !u.is_active } })}>
                          {u.is_active ? "Khóa" : "Mở khóa"}
                        </button>
                        <button type="button" className="btn bg-paper" disabled={busy} onClick={() => update.mutate({ id: u.id, body: { is_admin: !u.is_admin } })}>
                          {u.is_admin ? "Bỏ admin" : "Cấp admin"}
                        </button>
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {users.isPending && <p role="status" className="p-4">Đang tải…</p>}
        {users.data?.total === 0 && <p className="p-4">Không có tài khoản nào khớp.</p>}
      </div>
      {users.data && <Pager offset={offset} limit={LIMIT} total={users.data.total} onChange={setOffset} />}
    </section>
  );
}
