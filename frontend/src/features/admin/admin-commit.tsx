"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { LocalTime } from "@/components/ui/local-time";
import { FormError } from "@/features/auth/auth-card";
import { CommitDiff, type Commit } from "@/features/commits/commits";
import type { Team } from "@/features/events/types";
import { MentorNotes } from "@/features/mentor/team-support";
import { api, errorMessage } from "@/lib/api";
import { useLeaveOnForbidden } from "./use-leave-on-forbidden";

/** Một commit của đội cho admin: thông tin, link GitHub, thay đổi và các đánh giá gắn commit này. */
export function AdminCommit({ teamId, sha }: { teamId: string; sha: string }) {
  const team = useQuery({ queryKey: ["team", teamId], queryFn: async () => (await api.get<Team>(`/teams/${teamId}`)).data });
  const commit = useQuery({ queryKey: ["commit", teamId, sha], queryFn: async () => (await api.get<Commit>(`/teams/${teamId}/commits/${sha}`)).data });
  useLeaveOnForbidden(commit.error);

  if (commit.isError) return <FormError>{errorMessage(commit.error)}</FormError>;
  if (!commit.data) return <p role="status">Đang tải…</p>;
  const c = commit.data;

  return (
    <div className="space-y-7">
      <nav aria-label="Đường dẫn" className="text-sm font-bold">
        <Link href="/admin/events">Cuộc thi</Link> / <Link href={`/admin/teams/${teamId}`}>{team.data?.name ?? "Đội"}</Link> / <span className="font-mono">{c.sha.slice(0, 7)}</span>
      </nav>
      <section className="sketch space-y-3 p-6">
        <h1 className="whitespace-pre-wrap break-words text-2xl font-black leading-tight">{c.message}</h1>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <b>{c.author}</b>
          <span className="font-mono text-xs">{c.branch}</span>
          <span className="font-mono">
            <span className="text-plus">+{c.additions}</span> <span className="text-minus">−{c.deletions}</span>
          </span>
          {c.removed && <span className="chip bg-rose text-xs">Đã bị xóa khỏi branch</span>}
          {c.baseline && <span className="chip bg-warm text-xs">Có trước giờ thi</span>}
          {!c.baseline && !c.in_event_window && <span className="chip bg-sun text-xs">Ngoài giờ thi</span>}
        </div>
        <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-[auto_1fr]">
          <dt className="font-bold">Hệ thống thấy lúc</dt>
          <dd>
            <LocalTime iso={c.first_seen_at} />
          </dd>
          <dt className="font-bold">Giờ commit (do người commit khai)</dt>
          <dd>
            <LocalTime iso={c.committed_at} />
          </dd>
          <dt className="font-bold">SHA</dt>
          <dd className="break-all font-mono">{c.sha}</dd>
        </dl>
        <a href={c.url} target="_blank" rel="noreferrer" className="inline-block font-bold underline">
          Mở trên GitHub
        </a>
      </section>

      <section className="sketch p-6">
        <h2 className="mb-4 text-xl font-black">Thay đổi</h2>
        <CommitDiff teamId={teamId} sha={c.sha} />
      </section>

      <section className="sketch p-6">
        <h2 className="mb-4 text-xl font-black">Góp ý mentor gắn commit này</h2>
        <MentorNotes teamId={teamId} commitSha={c.sha} />
        <p className="mt-4 text-sm text-muted">AI review sẽ có ở Phase 6.</p>
      </section>
    </div>
  );
}
