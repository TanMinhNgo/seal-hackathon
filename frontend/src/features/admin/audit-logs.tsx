"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Pager } from "@/components/ui/pager";
import { FormError } from "@/features/auth/auth-card";
import { api, errorMessage } from "@/lib/api";
import type { components } from "@/lib/api-types";
import { useLeaveOnForbidden } from "./use-leave-on-forbidden";

type AuditLogPage = components["schemas"]["AuditLogPage"];
const LIMIT = 20;
const INPUT = "mt-1.5 block min-h-11 w-full rounded-xl border-2 border-ink bg-paper px-3.5";

export function AuditLogs() {
  const [filter, setFilter] = useState({ actor_id: "", action: "" });
  const [offset, setOffset] = useState(0);

  const logs = useQuery({
    queryKey: ["audit-logs", filter, offset],
    queryFn: async () =>
      (
        await api.get<AuditLogPage>("/admin/audit-logs", {
          params: { actor_id: filter.actor_id || undefined, action: filter.action || undefined, limit: LIMIT, offset },
        })
      ).data,
    placeholderData: keepPreviousData,
  });
  useLeaveOnForbidden(logs.error);

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    setFilter({ actor_id: String(fd.get("actor_id")).trim(), action: String(fd.get("action")).trim() });
    setOffset(0);
  }

  return (
    <section>
      <form role="search" onSubmit={submit} className="flex flex-wrap items-end gap-2">
        <label className="min-w-0 flex-1">
          <span className="text-sm font-bold">ID người thực hiện</span>
          {/* BE lọc chính xác theo UUID */}
          <input name="actor_id" pattern="[0-9a-fA-F-]{36}" title="UUID của tài khoản" className={INPUT} />
        </label>
        <label className="min-w-0 flex-1">
          <span className="text-sm font-bold">Hành động</span>
          <input name="action" list="audit-actions" maxLength={100} className={INPUT} />
          <datalist id="audit-actions">
            <option value="user.updated" />
            <option value="admin.created" />
          </datalist>
        </label>
        <button type="submit" className="btn bg-ink text-paper">
          Lọc
        </button>
      </form>

      {logs.isError && <div className="mt-4"><FormError>{errorMessage(logs.error)}</FormError></div>}

      <div className="sketch mt-5 overflow-x-auto p-0">
        <table className="w-full min-w-[760px] text-left text-sm">
          <thead className="border-b-2 border-ink bg-cream">
            <tr>
              <th className="px-4 py-3">Thời gian</th>
              <th className="px-4 py-3">Người thực hiện</th>
              <th className="px-4 py-3">Hành động</th>
              <th className="px-4 py-3">Đối tượng</th>
              <th className="px-4 py-3">Dữ liệu</th>
            </tr>
          </thead>
          <tbody>
            {logs.data?.items.map((l) => (
              <tr key={l.id} className="border-t border-line align-top">
                <td className="whitespace-nowrap px-4 py-3">{new Date(l.created_at).toLocaleString("vi-VN")}</td>
                <td className="px-4 py-3">
                  <b>{l.actor_email}</b>
                  <div className="font-mono text-xs text-muted">{l.actor_id}</div>
                </td>
                <td className="px-4 py-3">
                  <span className="chip bg-paper font-mono">{l.action}</span>
                </td>
                <td className="px-4 py-3 font-mono text-xs">
                  {l.target_type}
                  <div className="text-muted">{l.target_id}</div>
                </td>
                <td className="px-4 py-3">
                  <pre className="whitespace-pre-wrap font-mono text-xs">{JSON.stringify(l.data, null, 1)}</pre>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {logs.isPending && <p role="status" className="p-4">Đang tải…</p>}
        {logs.data?.total === 0 && <p className="p-4">Chưa có bản ghi nào khớp.</p>}
      </div>
      {logs.data && <Pager offset={offset} limit={LIMIT} total={logs.data.total} onChange={setOffset} />}
    </section>
  );
}
