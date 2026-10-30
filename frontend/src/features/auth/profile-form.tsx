"use client";

import { useMutation } from "@tanstack/react-query";
import Link from "next/link";
import { useState, type FormEvent, type ReactNode } from "react";
import { buttonClass } from "@/components/ui/button";
import { Doodle, type DoodleKind } from "@/components/ui/doodle";
import { Field } from "@/components/ui/field";
import { api, errorMessage } from "@/lib/api";
import type { components } from "@/lib/api-types";
import { useAuth, type User } from "@/stores/auth";
import { FormError } from "./auth-card";
import { primaryRole, useMyEventRoles, useMyEvents, type EventRole, type Role } from "./use-event-roles";

type ProfileInput = components["schemas"]["ProfileInput"];
type Kind = "admin" | Role | "newcomer";
type Editable = "student_id" | "phone";

const ROLE_CHIP: Record<Role, [string, string]> = {
  organizer: ["Ban tổ chức", "bg-orange"],
  judge: ["Giám khảo", "bg-sun"],
  mentor: ["Mentor", "bg-mint"],
  participant: ["Thí sinh", "bg-sky"],
};

/** Mỗi vai trò một hồ sơ: chỉ hiện và chỉ cho sửa trường vai trò đó cần. */
const PROFILES: Record<Kind, { kicker: string; title: string; badge: [string, string]; card: string; doodle: DoodleKind; fields: Editable[]; hint: string }> = {
  admin: {
    kicker: "Tài khoản hệ thống",
    title: "Hồ sơ quản trị viên.",
    badge: ["Quản trị viên", "bg-sky"],
    card: "bg-sky",
    doodle: "bolt",
    fields: ["phone"],
    hint: "Số điện thoại dùng khi cần liên hệ khẩn về sự cố hệ thống.",
  },
  organizer: {
    kicker: "Ban tổ chức",
    title: "Hồ sơ ban tổ chức.",
    badge: ROLE_CHIP.organizer,
    card: "bg-[#FFE1D3]",
    doodle: "flame",
    fields: ["phone"],
    hint: "Thí sinh, giám khảo và mentor liên hệ ban tổ chức qua thông tin này.",
  },
  judge: {
    kicker: "Giám khảo",
    title: "Hồ sơ giám khảo.",
    badge: ROLE_CHIP.judge,
    card: "bg-[#FFF1C2]",
    doodle: "star",
    fields: ["phone"],
    hint: "Ban tổ chức dùng để liên hệ phân công chấm bài.",
  },
  mentor: {
    kicker: "Mentor",
    title: "Hồ sơ mentor.",
    badge: ROLE_CHIP.mentor,
    card: "bg-[#E4F8DA]",
    doodle: "heart",
    fields: ["phone"],
    hint: "Ban tổ chức và các đội được phân công dùng để liên hệ với bạn.",
  },
  participant: {
    kicker: "Thí sinh",
    title: "Hồ sơ thí sinh.",
    badge: ROLE_CHIP.participant,
    card: "bg-cream",
    doodle: "sparkle",
    fields: ["student_id", "phone"],
    hint: "Ban tổ chức dùng MSSV để xác minh thí sinh và số điện thoại để liên hệ đội.",
  },
  newcomer: {
    kicker: "Chưa tham gia cuộc thi",
    title: "Hồ sơ cá nhân.",
    badge: ["Thành viên mới", "bg-paper"],
    card: "bg-cream",
    doodle: "plane",
    fields: ["student_id", "phone"],
    hint: "Điền MSSV trước để ban tổ chức xác minh nhanh khi bạn đăng ký dự thi.",
  },
};

const LABELS: Record<Editable, string> = { student_id: "Mã số sinh viên", phone: "Số điện thoại" };

const initials = (name: string) => {
  const words = name.trim().split(/\s+/);
  return ((words[0]?.[0] ?? "") + (words.length > 1 ? words[words.length - 1][0] : "")).toUpperCase();
};

// Chỉ gửi trường đang hiện và đã đổi; ô tùy chọn để trống gửi null để xóa
function changes(form: HTMLFormElement, user: User, fields: Editable[]): ProfileInput {
  const fd = new FormData(form);
  const body: ProfileInput = {};
  for (const k of ["full_name", ...fields] as const) {
    const v = String(fd.get(k) ?? "").trim();
    if (v !== (user[k] ?? "")) body[k] = v || null;
  }
  return body;
}

function IdentityCard({ user, kind, roles }: { user: User; kind: Kind; roles: EventRole[] }) {
  const p = PROFILES[kind];
  const chips = kind === "admin" ? [p.badge] : [...new Set(roles.map((r) => r.role))].map((r) => ROLE_CHIP[r]);
  return (
    <section aria-label="Thẻ thành viên" className={`sketch relative overflow-hidden p-6 ${p.card}`}>
      <Doodle kind={p.doodle} size={40} className="absolute right-5 top-5 rotate-12" />
      <span aria-hidden className="grid size-24 -rotate-6 place-items-center rounded-full border-2 border-ink bg-paper text-4xl font-black shadow-sketch-sm">
        {initials(user.full_name)}
      </span>
      <p className="mt-5 break-words text-[26px] font-black leading-tight tracking-[-0.03em]">{user.full_name}</p>
      <p className="mt-1 break-all font-mono text-sm">{user.email}</p>
      <div className="mt-4 flex flex-wrap gap-1.5">
        {(chips.length ? chips : [p.badge]).map(([label, bg]) => (
          <span key={label} className={`chip ${bg}`}>
            {label}
          </span>
        ))}
        {!user.email_verified && <span className="chip bg-sun">Chưa xác thực email</span>}
      </div>
      <dl className="mt-6 grid grid-cols-2 gap-3 border-t-2 border-dashed border-ink pt-4 text-sm">
        {p.fields.includes("student_id") ? (
          <div>
            <dt className="text-muted">MSSV</dt>
            <dd className="font-mono font-extrabold">{user.student_id ?? "—"}</dd>
          </div>
        ) : (
          <div>
            <dt className="text-muted">{kind === "admin" ? "Phạm vi" : "Số cuộc thi"}</dt>
            <dd className="font-mono font-extrabold">{kind === "admin" ? "Toàn hệ thống" : new Set(roles.map((r) => r.event_id)).size}</dd>
          </div>
        )}
        <div>
          <dt className="text-muted">Thành viên từ</dt>
          <dd className="font-mono font-extrabold">{new Date(user.created_at).toLocaleDateString("vi-VN")}</dd>
        </div>
      </dl>
    </section>
  );
}

function Card({ title, children, className = "" }: { title: string; children: ReactNode; className?: string }) {
  return (
    <section className={`sketch p-6 ${className}`}>
      <h2 className="text-xl font-black tracking-tight">{title}</h2>
      {children}
    </section>
  );
}

function ProfileForm({ user, kind }: { user: User; kind: Kind }) {
  const { fields, hint } = PROFILES[kind];
  const [dirty, setDirty] = useState(false);
  const save = useMutation({
    mutationFn: (body: ProfileInput) => api.patch<User>("/users/me", body),
    onSuccess: ({ data }) => {
      useAuth.getState().setUser(data);
      setDirty(false);
    },
  });

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const body = changes(e.currentTarget, user, fields);
    if (Object.keys(body).length) save.mutate(body);
  }

  return (
    <form onSubmit={submit} onChange={(e) => setDirty(Object.keys(changes(e.currentTarget, user, fields)).length > 0)} className="sketch p-6">
      <h2 className="text-xl font-black tracking-tight">Thông tin liên hệ</h2>
      <p className="mt-1 font-serif italic text-muted">{hint}</p>
      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <Field label="Họ và tên" name="full_name" defaultValue={user.full_name} autoComplete="name" required maxLength={100} />
        </div>
        {fields.map((k) => (
          <Field
            key={k}
            label={LABELS[k]}
            name={k}
            type={k === "phone" ? "tel" : "text"}
            autoComplete={k === "phone" ? "tel" : undefined}
            defaultValue={user[k] ?? ""}
            maxLength={k === "phone" ? 30 : 50}
          />
        ))}
      </div>
      <div className="mt-5 space-y-3">
        {save.isError && <FormError>{errorMessage(save.error)}</FormError>}
        {save.isSuccess && !dirty && (
          <p role="status" className="pop-in inline-flex items-center gap-2 rounded-xl border-2 border-ink bg-mint px-3.5 py-2 text-sm font-semibold">
            Đã lưu hồ sơ.
          </p>
        )}
      </div>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t-2 border-dashed border-line pt-4">
        <span className="text-sm text-muted">{dirty ? "Có thay đổi chưa lưu" : "Không có thay đổi"}</span>
        <button type="submit" className={buttonClass("primary")} disabled={!dirty || save.isPending}>
          {save.isPending ? "Đang lưu…" : "Lưu thay đổi"}
        </button>
      </div>
    </form>
  );
}

function RoleList({ roles }: { roles: EventRole[] }) {
  const mine = useMyEvents();
  const names = new Map(mine.data?.items.map((m) => [m.event.id, m.event.name]));
  return (
    <ul className="mt-4 space-y-2">
      {roles.map((r) => (
        <li key={`${r.event_id}-${r.role}`} className="flex items-center justify-between gap-3 rounded-xl border-2 border-dashed border-ink px-3.5 py-2.5">
          <span className="truncate font-semibold">{names.get(r.event_id) ?? "Cuộc thi"}</span>
          <span className={`chip ${ROLE_CHIP[r.role][1]}`}>{ROLE_CHIP[r.role][0]}</span>
        </li>
      ))}
    </ul>
  );
}

/** Khối riêng theo vai trò: việc của vai trò đó và lối vào màn làm việc. */
function RoleSection({ kind, roles }: { kind: Kind; roles: EventRole[] }) {
  const of = (...rs: Role[]) => roles.filter((r) => rs.includes(r.role));
  switch (kind) {
    case "admin":
      return (
        <Card title="Quyền quản trị">
          <p className="mt-1 text-sm text-muted">Quản lý toàn bộ hệ thống và dữ liệu; không tham gia chấm, góp ý hay dự thi.</p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Link href="/admin" className={buttonClass("primary")}>
              Tổng quan hệ thống
            </Link>
            <Link href="/admin/users" className={buttonClass("secondary")}>
              Tài khoản
            </Link>
            <Link href="/admin/audit-logs" className={buttonClass("secondary")}>
              Nhật ký
            </Link>
          </div>
        </Card>
      );
    case "organizer":
      return (
        <Card title="Cuộc thi phụ trách">
          <RoleList roles={of("organizer")} />
          <Link href="/dashboard" className={buttonClass("primary", "mt-4")}>
            Vào vận hành cuộc thi
          </Link>
        </Card>
      );
    case "judge":
    case "mentor":
      return (
        <Card title="Phân công của tôi">
          <RoleList roles={of("judge", "mentor")} />
          <div className="mt-4 flex flex-wrap gap-2">
            {of("judge").length > 0 && (
              <Link href="/judge" className={buttonClass("primary")}>
                Vào chấm điểm
              </Link>
            )}
            {of("mentor").length > 0 && (
              <Link href="/mentor" className={buttonClass(of("judge").length ? "secondary" : "primary")}>
                Vào khu mentor
              </Link>
            )}
          </div>
        </Card>
      );
    case "participant":
      return (
        <Card title="Cuộc thi tham gia">
          <RoleList roles={of("participant")} />
          <Link href="/dashboard" className={buttonClass("primary", "mt-4")}>
            Cuộc thi của tôi
          </Link>
        </Card>
      );
    default:
      return (
        <Card title="Bắt đầu dự thi" className="bg-cream">
          <p className="mt-1 font-serif italic text-muted">Bạn chưa tham gia cuộc thi nào.</p>
          <Link href="/events" className={buttonClass("primary", "mt-4")}>
            Xem các cuộc thi
          </Link>
        </Card>
      );
  }
}

function Security() {
  return (
    <section className="sketch flex flex-wrap items-center justify-between gap-4 bg-warm p-6">
      <div>
        <h2 className="text-xl font-black tracking-tight">Mật khẩu</h2>
        <p className="mt-1 text-sm text-muted">Đổi mật khẩu qua liên kết gửi tới email. Mọi phiên đăng nhập cũ sẽ bị đăng xuất.</p>
      </div>
      <Link href="/forgot-password" className={buttonClass("secondary")}>
        Đặt lại mật khẩu
      </Link>
    </section>
  );
}

export function ProfileView() {
  const user = useAuth((s) => s.user);
  const query = useMyEventRoles();
  if (!user) return null;
  if (!user.is_admin && query.isPending) return <p role="status" className="px-6 pt-12 text-center">Đang tải…</p>;
  if (query.isError) return <div className="mx-auto max-w-md px-4 pt-12"><FormError>{errorMessage(query.error)}</FormError></div>;

  const roles = query.data ?? [];
  const kind: Kind = user.is_admin ? "admin" : (primaryRole(roles) ?? "newcomer");
  const p = PROFILES[kind];
  return (
    <main className="mx-auto max-w-[1100px] px-4 pb-24 pt-10 sm:px-6">
      <p className="font-serif text-lg italic">{p.kicker}</p>
      <h1 className="mt-1 text-[clamp(36px,5vw,56px)] font-black leading-none tracking-[-0.045em]">{p.title}</h1>
      <div className="mt-8 grid items-start gap-7 lg:grid-cols-[340px_1fr]">
        <div className="lg:sticky lg:top-6">
          <IdentityCard user={user} kind={kind} roles={roles} />
        </div>
        <div className="space-y-7">
          <RoleSection kind={kind} roles={roles} />
          <ProfileForm user={user} kind={kind} />
          <Security />
        </div>
      </div>
    </main>
  );
}
