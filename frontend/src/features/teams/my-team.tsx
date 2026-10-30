"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { isAxiosError } from "axios";
import Link from "next/link";
import { useState, type FormEvent, type ReactNode } from "react";
import { buttonClass } from "@/components/ui/button";
import { useSecondsLeft } from "@/components/ui/countdown";
import { Field } from "@/components/ui/field";
import { LocalTime } from "@/components/ui/local-time";
import { FormError } from "@/features/auth/auth-card";
import { useMyEvents } from "@/features/auth/use-event-roles";
import { Tabs } from "@/features/events/manage";
import type { Event, Page, Team, Track } from "@/features/events/types";
import { SubmitTab } from "@/features/submissions/submissions";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/stores/auth";

const SELECT = "mt-1.5 block min-h-11 w-full rounded-xl border-2 border-ink bg-paper px-3 text-[15px] disabled:bg-warm";
const TEAM_STATUS: Record<Team["status"], [string, string]> = {
  pending: ["Chờ BTC duyệt", "bg-sun"],
  approved: ["Đã duyệt", "bg-mint"],
  rejected: ["Bị từ chối", "bg-rose"],
};

function Card({ title, tone = "", children }: { title: string; tone?: string; children: ReactNode }) {
  return (
    <section className={`sketch p-6 ${tone}`}>
      <h2 className="text-xl font-black tracking-tight">{title}</h2>
      <div className="mt-4">{children}</div>
    </section>
  );
}

export function MyTeam({ slug }: { slug: string }) {
  const user = useAuth((s) => s.user)!;
  const queryClient = useQueryClient();
  const event = useQuery({ queryKey: ["event-slug", slug], queryFn: async () => (await api.get<Event>(`/events/by-slug/${encodeURIComponent(slug)}`)).data });
  const eventId = event.data?.id;
  const tracks = useQuery({
    queryKey: ["tracks", eventId],
    queryFn: async () => (await api.get<Page<Track>>(`/events/${eventId}/tracks`, { params: { limit: 100 } })).data.items,
    enabled: !!eventId,
  });
  const team = useQuery({
    queryKey: ["my-team", eventId],
    queryFn: async () => {
      try {
        return (await api.get<Team>(`/events/${eventId}/teams/me`)).data;
      } catch (e) {
        // 404 = chưa có đội; 403 = chưa đăng ký (hoặc vừa rút) nên chưa phải thí sinh
        if (isAxiosError(e) && (e.response?.status === 404 || e.response?.status === 403)) return null;
        throw e;
      }
    },
    enabled: !!eventId,
  });
  const mine = useMyEvents();
  // Đếm ngược tới giờ bắt đầu: về 0 thì khóa UI ngay (server vẫn trả TEAM_FROZEN nếu đã khóa)
  const untilStart = useSecondsLeft(event.data?.starts_at ?? "");

  const setTeam = (t: Team | null) => {
    queryClient.setQueryData(["my-team", eventId], t);
    return queryClient.invalidateQueries({ queryKey: ["my-events"] });
  };
  const reload = () => Promise.all([queryClient.invalidateQueries({ queryKey: ["my-team", eventId] }), queryClient.invalidateQueries({ queryKey: ["my-events"] })]);

  const error = event.error ?? team.error ?? mine.error;
  if (error) return <Shell title="Đội của tôi."><FormError>{errorMessage(error)}</FormError></Shell>;
  if (!event.data || team.isPending || mine.isPending) return <p role="status" className="px-6 pt-12 text-center">Đang tải…</p>;

  const ev = event.data;
  const registered = mine.data?.items.some((m) => m.event.id === ev.id && m.roles.includes("participant"));
  const frozen = ev.status !== "open" || untilStart === 0;

  if (!team.data && !registered)
    return (
      <Shell title="Đội của tôi." event={ev}>
        <p className="font-serif text-lg italic">Bạn chưa đăng ký dự thi cuộc thi này.</p>
        <Link href={`/events/${ev.slug}`} className={buttonClass("primary", "mt-4")}>
          Tới trang cuộc thi để đăng ký
        </Link>
      </Shell>
    );

  if (!team.data)
    return (
      <Shell title="Lập đội." event={ev}>
        {frozen ? (
          <p className="font-serif text-lg italic">Đã qua thời gian lập đội.</p>
        ) : (
          <NoTeam event={ev} tracks={tracks.data ?? []} onTeam={setTeam} onWithdraw={reload} />
        )}
      </Shell>
    );

  const t = team.data;
  const me = t.members.find((m) => m.user.id === user.id);
  if (me?.status === "pending") return <Shell title="Đang chờ vào đội." event={ev}><PendingRequest team={t} userId={user.id} onDone={() => setTeam(null)} /></Shell>;

  const view = <TeamView event={ev} team={t} tracks={tracks.data ?? []} userId={user.id} frozen={frozen} onTeam={setTeam} onReload={reload} />;
  return (
    <Shell title={`${t.name}.`} event={ev}>
      {ev.status === "ongoing" || ev.status === "judging" || ev.status === "closed" ? (
        <TeamTabs submit={<SubmitTab event={ev} team={t} leader={t.leader_id === user.id} />}>{view}</TeamTabs>
      ) : (
        view
      )}
    </Shell>
  );
}

function TeamTabs({ submit, children }: { submit: ReactNode; children: ReactNode }) {
  const [tab, setTab] = useState<"submit" | "team">("submit");
  return (
    <div className="space-y-7">
      <Tabs<"submit" | "team">
        label="Đội của tôi"
        value={tab}
        onChange={setTab}
        tabs={[
          ["submit", "Nộp bài"],
          ["team", "Đội & repo"],
        ]}
      />
      {tab === "submit" ? submit : children}
    </div>
  );
}

function Shell({ title, event, children }: { title: string; event?: Event; children: ReactNode }) {
  return (
    <main className="mx-auto max-w-[1200px] px-4 pb-24 pt-10 sm:px-6">
      {event && (
        <p className="font-serif text-lg italic">
          <Link href={`/events/${event.slug}`} className="underline">
            {event.name}
          </Link>{" "}
          · đội và repo khóa lúc <LocalTime iso={event.starts_at} />
        </p>
      )}
      <h1 className="mt-1.5 break-words text-[clamp(40px,6vw,72px)] font-black leading-[0.95] tracking-[-0.05em]">{title}</h1>
      <div className="mt-8">{children}</div>
    </main>
  );
}

function NoTeam({ event, tracks, onTeam, onWithdraw }: { event: Event; tracks: Track[]; onTeam: (t: Team) => void; onWithdraw: () => void }) {
  const create = useMutation({
    mutationFn: async (body: { name: string; track_id: string | null }) => (await api.post<Team>(`/events/${event.id}/teams`, body)).data,
    onSuccess: onTeam,
  });
  const join = useMutation({ mutationFn: async (invite_code: string) => (await api.post<Team>("/teams/join", { invite_code })).data, onSuccess: onTeam });
  const withdraw = useMutation({ mutationFn: () => api.delete(`/events/${event.id}/register`), onSuccess: onWithdraw });

  function submitCreate(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    create.mutate({ name: String(fd.get("name")).trim(), track_id: String(fd.get("track_id")) || null });
  }
  function submitJoin(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    join.mutate(String(new FormData(e.currentTarget).get("code")).trim());
  }

  return (
    <div className="grid gap-7 md:grid-cols-2">
      <Card title="Lập đội mới" tone="bg-cream">
        <form onSubmit={submitCreate} className="space-y-4">
          <p className="text-sm text-muted">
            Bạn sẽ là trưởng nhóm. Đội {event.min_team_size}–{event.max_team_size} người.
          </p>
          <Field label="Tên đội" name="name" required maxLength={100} />
          <label className="block">
            <span className="text-sm font-bold">Track (chọn sau cũng được)</span>
            <select name="track_id" className={SELECT} defaultValue="">
              <option value="">Chưa chọn</option>
              {tracks.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </label>
          {create.isError && <FormError>{errorMessage(create.error)}</FormError>}
          <button type="submit" className={buttonClass("primary")} disabled={create.isPending}>
            Tạo đội
          </button>
        </form>
      </Card>
      <Card title="Vào đội bạn bè">
        <form onSubmit={submitJoin} className="space-y-4">
          <p className="text-sm text-muted">Nhập mã mời trưởng nhóm gửi hoặc mở link mời. Trưởng nhóm sẽ duyệt bạn vào đội.</p>
          <Field label="Mã mời" name="code" required minLength={20} maxLength={64} autoComplete="off" />
          {join.isError && <FormError>{errorMessage(join.error)}</FormError>}
          <button type="submit" className={buttonClass("secondary")} disabled={join.isPending}>
            Xin vào đội
          </button>
        </form>
        <p className="mt-5 border-t-2 border-dashed border-line pt-4 text-sm text-muted">
          Đổi ý không dự thi nữa?{" "}
          <button type="button" className="font-bold text-ink underline" disabled={withdraw.isPending} onClick={() => withdraw.mutate()}>
            Rút đăng ký
          </button>
        </p>
        {withdraw.isError && <div className="mt-3"><FormError>{errorMessage(withdraw.error)}</FormError></div>}
      </Card>
    </div>
  );
}

function PendingRequest({ team, userId, onDone }: { team: Team; userId: string; onDone: () => void }) {
  const cancel = useMutation({ mutationFn: () => api.delete(`/teams/${team.id}/members/${userId}`), onSuccess: onDone });
  return (
    <Card title={`Bạn đã xin vào đội ${team.name}`} tone="bg-cream">
      <p className="leading-relaxed">Trưởng nhóm sẽ thấy yêu cầu của bạn. Trong lúc chờ, bạn chưa xem được thành viên và repo của đội.</p>
      {cancel.isError && <div className="mt-3"><FormError>{errorMessage(cancel.error)}</FormError></div>}
      <button type="button" className={buttonClass("secondary", "mt-4")} disabled={cancel.isPending} onClick={() => cancel.mutate()}>
        Hủy yêu cầu
      </button>
    </Card>
  );
}

function TeamView({ event, team, tracks, userId, frozen, onTeam, onReload }: { event: Event; team: Team; tracks: Track[]; userId: string; frozen: boolean; onTeam: (t: Team | null) => void; onReload: () => void }) {
  const leader = team.leader_id === userId;
  const canEdit = leader && !frozen;
  const others = team.members.filter((m) => m.user.id !== userId);
  const active = team.members.filter((m) => m.status === "active");
  const [msg, setMsg] = useState("");

  const call = useMutation({
    mutationFn: async (fn: () => Promise<Team | null>) => fn(),
    onSuccess: (t) => (t ? onTeam(t) : onReload()),
  });
  const run = (fn: () => Promise<Team | null>) => {
    setMsg("");
    call.mutate(fn);
  };
  const teamCall = (method: "post" | "patch" | "put", url: string, body?: unknown) => async () => (await api[method]<Team>(url, body)).data;
  const voidCall = (url: string) => async () => {
    await api.delete(url);
    return null;
  };
  const leave = () => {
    if (leader && others.length === 0 && !window.confirm("Bạn là người cuối cùng: rời đội sẽ giải tán đội. Tiếp tục?")) return;
    run(voidCall(`/teams/${team.id}/members/${userId}`));
  };
  const transfer = (id: string, name: string) => {
    if (window.confirm(`Chuyển trưởng nhóm cho ${name}?`)) run(teamCall("post", `/teams/${team.id}/transfer-leader`, { user_id: id }));
  };
  const rotate = () => {
    if (!window.confirm("Tạo mã mới sẽ làm mã cũ hết hiệu lực. Tiếp tục?")) return;
    run(async () => {
      await api.post(`/teams/${team.id}/invite-code`);
      return null;
    });
  };

  function saveInfo(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const name = String(fd.get("name")).trim();
    const track_id = String(fd.get("track_id")) || null;
    const repo_url = String(fd.get("repo_url")).trim();
    // Chỉ gửi phần đổi: đội đã duyệt mà đổi gì cũng quay về chờ duyệt
    run(async () => {
      let t = team;
      if (name !== team.name || track_id !== team.track_id) t = (await api.patch<Team>(`/teams/${team.id}`, { ...(name !== team.name && { name }), ...(track_id !== team.track_id && { track_id }) })).data;
      if (repo_url && repo_url !== (team.repo_url ?? "")) t = (await api.put<Team>(`/teams/${team.id}/repo`, { repo_url })).data;
      return t;
    });
  }

  const [label, tone] = TEAM_STATUS[team.status];
  return (
    <div className="space-y-7">
      <div role="status" className={`flex flex-wrap items-center gap-3 rounded-2xl border-2 border-ink px-4 py-3.5 ${frozen ? "bg-warm" : tone}`}>
        <span className="chip bg-paper">{frozen ? "Đã khóa" : label}</span>
        <span className="text-[15px] leading-normal">
          {frozen
            ? "Cuộc thi đã bắt đầu hoặc không còn mở: đội, thành viên và repo bị khóa."
            : team.status === "rejected"
              ? `Ghi chú của BTC: “${team.review_note ?? ""}”. Sửa lại rồi đội tự quay về chờ duyệt.`
              : team.status === "approved"
                ? "Đội đã sẵn sàng. Đổi tên, track, repo hoặc thành viên sẽ đưa đội về chờ duyệt."
                : leader
                  ? `BTC chỉ duyệt khi đủ ${event.min_team_size}–${event.max_team_size} thành viên chính thức, không còn yêu cầu chờ và có repo hợp lệ.`
                  : "Đội đang chờ ban tổ chức duyệt."}
        </span>
      </div>
      {call.isError && <FormError>{errorMessage(call.error)}</FormError>}
      {msg && <p role="status" className="rounded-xl border-2 border-ink bg-mint px-4 py-2.5 text-sm font-semibold">{msg}</p>}

      <div className="flex flex-wrap items-start gap-7">
        <div className="min-w-0 flex-[999_1_520px]">
          <Card title={`Thành viên ${active.length}/${event.max_team_size}`}>
            <ul className="space-y-2.5">
              {team.members.map((m) => {
                const isLeader = m.user.id === team.leader_id;
                const pending = m.status === "pending";
                return (
                  <li key={m.user.id} className={`flex flex-wrap items-center gap-x-3.5 gap-y-2 rounded-2xl border-2 border-dashed border-ink px-3.5 py-3 ${pending ? "bg-cream" : ""}`}>
                    <span className="min-w-0 flex-[1_1_180px]">
                      <b className="break-words">{m.user.full_name}</b>
                      <span className="block break-all text-sm text-muted">{m.user.email}</span>
                    </span>
                    <span className={`chip ${isLeader ? "bg-orange" : pending ? "bg-sun" : "bg-mint"}`}>{isLeader ? "Trưởng nhóm" : pending ? "Chờ duyệt" : "Thành viên"}</span>
                    {canEdit && !isLeader && (
                      <span className="flex flex-wrap gap-1.5">
                        {pending && (
                          <button type="button" className="btn bg-mint text-sm" disabled={call.isPending} onClick={() => run(teamCall("post", `/teams/${team.id}/members/${m.user.id}/approve`))}>
                            Duyệt
                          </button>
                        )}
                        {!pending && (
                          <button type="button" className="btn bg-paper text-sm" disabled={call.isPending} onClick={() => transfer(m.user.id, m.user.full_name)}>
                            Chuyển trưởng nhóm
                          </button>
                        )}
                        <button type="button" className="btn bg-paper text-sm" disabled={call.isPending} onClick={() => run(voidCall(`/teams/${team.id}/members/${m.user.id}`))}>
                          {pending ? "Từ chối" : "Xóa khỏi đội"}
                        </button>
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>
            {!frozen && (
              <p className="mt-4 text-sm text-muted">
                {leader
                  ? others.length
                    ? "Muốn rời đội? Chuyển trưởng nhóm cho một thành viên chính thức trước."
                    : "Đội chỉ còn mình bạn: rời đội sẽ giải tán đội."
                  : "Không muốn tiếp tục cùng đội?"}{" "}
                {(!leader || others.length === 0) && (
                  <button type="button" className="font-bold text-ink underline" disabled={call.isPending} onClick={leave}>
                    {leader ? "Giải tán đội" : "Rời đội"}
                  </button>
                )}
              </p>
            )}
          </Card>
        </div>

        <div className="min-w-0 flex-[1_1_340px] space-y-7">
          {!frozen && team.invite_code && <Invite team={team} leader={leader} onRotate={rotate} onSent={setMsg} busy={call.isPending} />}

          <Card title="Tên, track & repo">
            <form onSubmit={saveInfo} className="space-y-4">
              <Field label="Tên đội" name="name" defaultValue={team.name} required maxLength={100} readOnly={!canEdit} />
              <label className="block">
                <span className="text-sm font-bold">Track</span>
                <select name="track_id" defaultValue={team.track_id ?? ""} disabled={!canEdit} className={SELECT}>
                  <option value="">Chưa chọn</option>
                  {tracks.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
                </select>
              </label>
              <Field label="Repo GitHub (công khai)" name="repo_url" type="url" placeholder="https://github.com/chu-repo/ten-repo" defaultValue={team.repo_url ?? ""} readOnly={!canEdit} pattern="https://github\.com/[^/]+/[^/]+/?" />
              {canEdit && (
                <button type="submit" className={buttonClass("primary")} disabled={call.isPending}>
                  Lưu
                </button>
              )}
            </form>
          </Card>
        </div>
      </div>
    </div>
  );
}

function Invite({ team, leader, onRotate, onSent, busy }: { team: Team; leader: boolean; onRotate: () => void; onSent: (m: string) => void; busy: boolean }) {
  const link = typeof window === "undefined" ? "" : `${window.location.origin}/join?code=${encodeURIComponent(team.invite_code ?? "")}`;
  const send = useMutation({
    mutationFn: (email: string) => api.post(`/teams/${team.id}/invitations`, { email }),
    onSuccess: () => onSent("Đã xếp lời mời vào hàng gửi email."),
  });
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    send.mutate(String(new FormData(form).get("email")).trim(), { onSuccess: () => form.reset() });
  }
  return (
    <Card title="Mời thành viên" tone="bg-cream">
      <p className="break-all font-mono text-lg font-extrabold">{team.invite_code}</p>
      {team.invite_expires_at && (
        <p className="mt-1 text-sm text-muted">
          Hết hạn <LocalTime iso={team.invite_expires_at} />
        </p>
      )}
      <div className="mt-3.5 flex flex-wrap gap-2">
        <button type="button" className={buttonClass("primary")} onClick={() => navigator.clipboard.writeText(link).then(() => onSent("Đã sao chép link mời."))}>
          Sao chép link mời
        </button>
        {leader && (
          <button type="button" className={buttonClass("secondary")} disabled={busy} onClick={onRotate}>
            Tạo mã mới
          </button>
        )}
      </div>
      {leader && (
        <form onSubmit={submit} className="mt-4 flex flex-wrap items-end gap-2 border-t-2 border-dashed border-ink pt-4">
          <div className="min-w-0 flex-[1_1_200px]">
            <Field label="Gửi link qua email" name="email" type="email" required maxLength={254} />
          </div>
          <button type="submit" className={buttonClass("secondary")} disabled={send.isPending}>
            Gửi
          </button>
          {send.isError && <div className="w-full"><FormError>{errorMessage(send.error)}</FormError></div>}
        </form>
      )}
    </Card>
  );
}
