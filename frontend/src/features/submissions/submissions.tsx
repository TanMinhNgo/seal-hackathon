"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type ChangeEvent, type FormEvent, type ReactNode } from "react";
import { buttonClass } from "@/components/ui/button";
import { InlineCountdown, serverNow, useSecondsLeft } from "@/components/ui/countdown";
import { Field } from "@/components/ui/field";
import { LocalTime } from "@/components/ui/local-time";
import { Pager } from "@/components/ui/pager";
import { FormError } from "@/features/auth/auth-card";
import type { Event, Page, Round, RoundSubmission, Submission, Team } from "@/features/events/types";
import { api, errorCode, errorMessage, uploadToStorage } from "@/lib/api";

// MIME phải đúng tuyệt đối theo hợp đồng; không dùng file.type vì Windows báo zip là application/x-zip-compressed
const FILE_TYPES: Record<string, string> = {
  pdf: "application/pdf",
  pptx: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  mp4: "video/mp4",
  zip: "application/zip",
};
const MAX_SIZE = 104_857_600;
const MAX_FILES = 10;
const LIMIT = 20;
const SELECT = "mt-1.5 block min-h-11 w-full rounded-xl border-2 border-ink bg-paper px-3 text-[15px]";

const typeOf = (name: string) => FILE_TYPES[name.split(".").pop()?.toLowerCase() ?? ""];
const mb = (n: number) => `${(n / 1_048_576).toFixed(1)} MB`;

export function useRounds(eventId: string) {
  return useQuery({
    queryKey: ["rounds", eventId],
    queryFn: async () => (await api.get<Page<Round>>(`/events/${eventId}/rounds`, { params: { limit: 100 } })).data.items.sort((a, b) => a.order - b.order),
    enabled: !!eventId,
  });
}

/** Vòng đang nhận bài, nếu không có thì vòng gần nhất đã qua, cuối cùng là vòng đầu. */
function defaultRound(rounds: Round[]) {
  const now = serverNow();
  const started = rounds.filter((r) => Date.parse(r.starts_at) <= now);
  return (started.find((r) => now < Date.parse(r.submission_deadline)) ?? started.at(-1) ?? rounds[0])?.id ?? "";
}

function RoundSelect({ rounds, value, onChange }: { rounds: Round[]; value: string; onChange: (id: string) => void }) {
  return (
    <label className="block max-w-sm">
      <span className="text-sm font-bold">Vòng thi</span>
      <select value={value} onChange={(e) => onChange(e.target.value)} className={SELECT}>
        {rounds.map((r) => (
          <option key={r.id} value={r.id}>
            {r.name}
          </option>
        ))}
      </select>
    </label>
  );
}

/** Chọn vòng rồi hiện nội dung theo vòng; dùng chung cho thí sinh, BTC, admin. */
export function WithRound({ eventId, children }: { eventId: string; children: (round: Round) => ReactNode }) {
  const rounds = useRounds(eventId);
  const [picked, setPicked] = useState("");
  if (rounds.isError) return <FormError>{errorMessage(rounds.error)}</FormError>;
  if (!rounds.data) return <p role="status">Đang tải…</p>;
  if (!rounds.data.length) return <p className="text-muted">Cuộc thi chưa có vòng thi.</p>;
  const round = rounds.data.find((r) => r.id === (picked || defaultRound(rounds.data)))!;
  return (
    <div className="space-y-5">
      <RoundSelect rounds={rounds.data} value={round.id} onChange={setPicked} />
      {children(round)}
    </div>
  );
}

/** Biên nhận: chỉ thông tin server trả về mới chứng minh đã nộp. */
export function Receipt({ s }: { s: Submission }) {
  const download = useMutation({
    // URL ký chỉ sống vài phút nên lấy mới mỗi lần bấm tải
    mutationFn: async (key: string) => (await api.get<Submission>(`/submissions/${s.id}`)).data.files.find((f) => f.key === key)?.download_url,
    onSuccess: (url) => url && window.location.assign(url),
  });
  return (
    <article className={`rounded-2xl border-2 border-ink p-4 ${s.is_final ? "bg-mint" : "bg-paper"}`}>
      <div className="flex flex-wrap items-center gap-2">
        <b className="font-mono text-lg">v{s.version}</b>
        {s.is_final && <span className="chip bg-orange">Bản được tính điểm</span>}
        <span className="text-sm">
          nộp lúc <LocalTime iso={s.submitted_at} /> (giờ máy chủ)
        </span>
      </div>
      <dl className="mt-2.5 grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[auto_1fr]">
        <dt className="font-bold">Commit</dt>
        <dd className="break-all font-mono" title={s.commit_sha}>
          {s.commit_sha.slice(0, 12)}
        </dd>
        <dt className="font-bold">Repo</dt>
        <dd className="break-all">
          <a href={s.repo_url} target="_blank" rel="noreferrer" className="underline">
            {s.repo_url}
          </a>
        </dd>
        {s.demo_url && (
          <>
            <dt className="font-bold">Demo</dt>
            <dd className="break-all">
              <a href={s.demo_url} target="_blank" rel="noreferrer" className="underline">
                {s.demo_url}
              </a>
            </dd>
          </>
        )}
        {s.video_url && (
          <>
            <dt className="font-bold">Video</dt>
            <dd className="break-all">
              <a href={s.video_url} target="_blank" rel="noreferrer" className="underline">
                {s.video_url}
              </a>
            </dd>
          </>
        )}
        <dt className="font-bold">Mã biên nhận</dt>
        <dd className="break-all font-mono text-xs">{s.id}</dd>
      </dl>
      {s.description && <p className="mt-2.5 whitespace-pre-wrap text-sm">{s.description}</p>}
      {s.files.length > 0 && (
        <ul className="mt-3 flex flex-wrap gap-2">
          {s.files.map((f) => (
            <li key={f.key}>
              <button type="button" className="btn bg-paper text-sm" disabled={download.isPending} onClick={() => download.mutate(f.key)}>
                ⬇ {f.filename} <span className="text-muted">({mb(f.size)})</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {download.isError && <div className="mt-2"><FormError>{errorMessage(download.error)}</FormError></div>}
    </article>
  );
}

function History({ teamId, roundId }: { teamId: string; roundId: string }) {
  const [offset, setOffset] = useState(0);
  const list = useQuery({
    queryKey: ["submissions", teamId, roundId, offset],
    queryFn: async () => (await api.get<Page<Submission>>(`/teams/${teamId}/rounds/${roundId}/submissions`, { params: { limit: LIMIT, offset } })).data,
    placeholderData: keepPreviousData,
  });
  if (list.isError) return <FormError>{errorMessage(list.error)}</FormError>;
  if (!list.data) return <p role="status">Đang tải…</p>;
  return (
    <section aria-label="Lịch sử phiên bản" className="space-y-3">
      <h3 className="text-lg font-black">Lịch sử phiên bản</h3>
      {list.data.items.length ? list.data.items.map((s) => <Receipt key={s.id} s={s} />) : <p className="text-muted">Chưa có phiên bản nào.</p>}
      {list.data.total > LIMIT && <Pager offset={offset} limit={LIMIT} total={list.data.total} onChange={setOffset} />}
    </section>
  );
}

/** Hồ sơ bài nộp chỉ đọc theo vòng (admin, mentor được phân công). */
export function TeamSubmissions({ eventId, teamId }: { eventId: string; teamId: string }) {
  return <WithRound eventId={eventId}>{(r) => <History key={r.id} teamId={teamId} roundId={r.id} />}</WithRound>;
}

/** Tab "Nộp bài" của đội: leader nộp, thành viên xem lịch sử. */
export function SubmitTab({ event, team, leader }: { event: Event; team: Team; leader: boolean }) {
  return (
    <WithRound eventId={event.id}>
      {(r) => (
        <div key={r.id} className="space-y-6">
          <RoundStatus round={r} />
          {leader && event.status === "ongoing" && team.status === "approved" ? (
            <SubmitForm team={team} round={r} />
          ) : (
            <p className="text-sm text-muted">{leader ? "Chỉ nộp được khi cuộc thi đang diễn ra và đội đã được duyệt." : "Chỉ trưởng nhóm nộp bài. Bạn xem được các phiên bản đội đã nộp bên dưới."}</p>
          )}
          <History teamId={team.id} roundId={r.id} />
        </div>
      )}
    </WithRound>
  );
}

function RoundStatus({ round }: { round: Round }) {
  const toStart = useSecondsLeft(round.starts_at);
  const toDeadline = useSecondsLeft(round.submission_deadline);
  const [text, tone] =
    toStart === null ? ["…", "bg-paper"] : toStart > 0 ? ["Mở nhận bài sau", "bg-sky"] : toDeadline ? ["Hạn nộp còn", "bg-sun"] : ["Đã hết hạn nộp", "bg-warm"];
  return (
    <div role="status" className={`flex flex-wrap items-center gap-3 rounded-2xl border-2 border-ink px-4 py-3 ${tone}`}>
      <b>{text}</b>
      {toStart !== null && (toStart > 0 ? <InlineCountdown target={round.starts_at} /> : toDeadline ? <InlineCountdown target={round.submission_deadline} /> : null)}
      <span className="text-sm">
        Hạn chót <LocalTime iso={round.submission_deadline} /> · đếm theo giờ máy chủ
      </span>
    </div>
  );
}

type Picked = { file: File; type: string; progress: number; key?: string };

function SubmitForm({ team, round }: { team: Team; round: Round }) {
  const queryClient = useQueryClient();
  const toStart = useSecondsLeft(round.starts_at);
  const toDeadline = useSecondsLeft(round.submission_deadline);
  const [files, setFiles] = useState<Picked[]>([]);
  const [fileError, setFileError] = useState("");
  const [receipt, setReceipt] = useState<Submission | null>(null);
  // Giữ key khi gửi lại đúng payload (mất mạng, 503) để server trả biên nhận cũ thay vì tạo phiên bản mới
  const attempt = useRef<{ payload: string; key: string } | null>(null);
  const open = toStart === 0 && !!toDeadline;

  const update = (i: number, patch: Partial<Picked>) => setFiles((fs) => fs.map((f, j) => (j === i ? { ...f, ...patch } : f)));

  const submit = useMutation({
    mutationFn: async (form: HTMLFormElement) => {
      const fd = new FormData(form);
      const text = (k: string) => String(fd.get(k) ?? "").trim() || null;
      const keys: string[] = [];
      for (const [i, f] of files.entries()) {
        const key = f.key ?? (await uploadToStorage(team.id, f.file, f.type, (progress) => update(i, { progress })));
        update(i, { key, progress: 1 });
        keys.push(key);
      }
      const body = { repo_url: team.repo_url ?? "", demo_url: text("demo_url"), video_url: text("video_url"), description: text("description"), file_keys: keys };
      const payload = JSON.stringify(body);
      if (attempt.current?.payload !== payload) attempt.current = { payload, key: crypto.randomUUID() };
      const { data } = await api.post<Submission>(`/teams/${team.id}/rounds/${round.id}/submissions`, body, { headers: { "Idempotency-Key": attempt.current.key } });
      return { data, form };
    },
    onSuccess: ({ data, form }) => {
      attempt.current = null;
      setReceipt(data);
      setFiles([]);
      form.reset();
      return queryClient.invalidateQueries({ queryKey: ["submissions", team.id, round.id] });
    },
    onError: (e) => {
      // Key file chỉ dùng một lần: server từ chối thì phải xin chữ ký và tải lại
      if (errorCode(e) === "FILE_NOT_UPLOADED") setFiles((fs) => fs.map((f) => ({ ...f, key: undefined, progress: 0 })));
    },
  });

  function pick(e: ChangeEvent<HTMLInputElement>) {
    const chosen = Array.from(e.target.files ?? []);
    e.target.value = "";
    const bad = chosen.find((f) => !typeOf(f.name)) ?? chosen.find((f) => f.size === 0 || f.size > MAX_SIZE);
    if (bad) return setFileError(typeOf(bad.name) ? `“${bad.name}” rỗng hoặc vượt quá 100 MB.` : `“${bad.name}” không đúng loại: chỉ nhận .pdf, .pptx, .mp4, .zip.`);
    if (files.length + chosen.length > MAX_FILES) return setFileError(`Tối đa ${MAX_FILES} file mỗi lần nộp.`);
    setFileError("");
    setFiles((fs) => [...fs, ...chosen.map((file) => ({ file, type: typeOf(file.name), progress: 0 }))]);
  }

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setReceipt(null);
    submit.mutate(e.currentTarget);
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4 rounded-2xl border-2 border-ink bg-cream p-5">
      <h3 className="text-lg font-black">Nộp phiên bản mới</h3>
      <Field label="Repo (đã duyệt, server lấy commit mới nhất khi nộp)" value={team.repo_url ?? ""} readOnly />
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Link demo (không bắt buộc)" name="demo_url" type="url" maxLength={2048} placeholder="https://" />
        <Field label="Link video (không bắt buộc)" name="video_url" type="url" maxLength={2048} placeholder="https://" />
      </div>
      <label className="block">
        <span className="text-sm font-bold">Mô tả (không bắt buộc)</span>
        <textarea name="description" maxLength={20000} rows={4} className="mt-1.5 block w-full rounded-xl border-2 border-ink bg-paper px-3.5 py-2.5 text-[15px]" />
      </label>
      <div>
        <label className="block">
          <span className="text-sm font-bold">File đính kèm: .pdf, .pptx, .mp4, .zip; tối đa {MAX_FILES} file, mỗi file 100 MB</span>
          <input type="file" multiple accept=".pdf,.pptx,.mp4,.zip" onChange={pick} disabled={!open || submit.isPending} className="mt-1.5 block w-full text-sm file:mr-3 file:min-h-11 file:cursor-pointer file:rounded-xl file:border-2 file:border-ink file:bg-paper file:px-3 file:font-bold" />
        </label>
        {fileError && <div className="mt-2"><FormError>{fileError}</FormError></div>}
        {files.length > 0 && (
          <ul className="mt-3 space-y-2">
            {files.map((f, i) => (
              <li key={`${f.file.name}-${i}`} className="flex flex-wrap items-center gap-3 rounded-xl border-2 border-dashed border-ink px-3 py-2 text-sm">
                <span className="min-w-0 flex-[1_1_180px] break-all font-semibold">{f.file.name}</span>
                <span className="text-muted">{mb(f.file.size)}</span>
                {f.key ? (
                  <span className="chip bg-mint">Đã tải lên</span>
                ) : submit.isPending ? (
                  <progress value={f.progress} max={1} aria-label={`Tiến độ tải ${f.file.name}`} className="h-2.5 w-28 accent-orange" />
                ) : (
                  <span className="text-muted">Tải lên khi bấm Nộp</span>
                )}
                {!submit.isPending && (
                  <button type="button" className="font-bold underline" onClick={() => setFiles((fs) => fs.filter((_, j) => j !== i))}>
                    Bỏ
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
      {submit.isError && <FormError>{errorMessage(submit.error)}</FormError>}
      <button type="submit" className={buttonClass("primary")} disabled={!open || submit.isPending}>
        {submit.isPending ? "Đang nộp…" : open ? "Nộp bài" : toStart ? "Chưa tới giờ nộp" : "Đã hết hạn"}
      </button>
      <p className="text-xs text-muted">Bài chỉ được tính là đã nộp khi hiện biên nhận có số phiên bản và mã commit. Tải file lên xong chưa phải là đã nộp.</p>
      {receipt && (
        <div role="status" className="space-y-2">
          <p className="font-black">Đã nộp thành công. Biên nhận:</p>
          <Receipt s={receipt} />
        </div>
      )}
    </form>
  );
}

/** Bảng bài nộp theo vòng cho BTC/admin: bản cuối của mỗi đội đã duyệt, kể cả đội chưa nộp. */
export function RoundSubmissionsPanel({ eventId }: { eventId: string }) {
  return <WithRound eventId={eventId}>{(r) => <RoundTable key={r.id} eventId={eventId} roundId={r.id} />}</WithRound>;
}

function RoundTable({ eventId, roundId }: { eventId: string; roundId: string }) {
  const [offset, setOffset] = useState(0);
  const [missingOnly, setMissingOnly] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const list = useQuery({
    queryKey: ["round-submissions", eventId, roundId, offset],
    queryFn: async () => (await api.get<Page<RoundSubmission>>(`/events/${eventId}/rounds/${roundId}/submissions`, { params: { limit: LIMIT, offset } })).data,
    placeholderData: keepPreviousData,
  });
  if (list.isError) return <FormError>{errorMessage(list.error)}</FormError>;
  if (!list.data) return <p role="status">Đang tải…</p>;
  // shortcut: lọc "chưa nộp" trong trang hiện tại vì API chưa có tham số lọc; thêm ?submitted=false ở BE khi số đội lớn
  const rows = missingOnly ? list.data.items.filter((t) => !t.submission) : list.data.items;
  const missing = list.data.items.filter((t) => !t.submission).length;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm">
          Trang này: <b>{list.data.items.length - missing}</b> đội đã nộp, <b>{missing}</b> đội chưa nộp.
        </p>
        <label className="flex items-center gap-2 text-sm font-bold">
          <input type="checkbox" checked={missingOnly} onChange={(e) => setMissingOnly(e.target.checked)} className="size-4 accent-orange" />
          Chỉ đội chưa nộp
        </label>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[560px] border-collapse text-left text-sm">
          <thead>
            <tr className="border-b-2 border-ink">
              <th className="py-2 pr-3">Đội</th>
              <th className="py-2 pr-3">Phiên bản</th>
              <th className="py-2 pr-3">Nộp lúc</th>
              <th className="py-2 pr-3">Commit</th>
              <th className="py-2" />
            </tr>
          </thead>
          <tbody>
            {rows.map((t) => (
              <Row key={t.team_id} t={t} open={open === t.team_id} onToggle={() => setOpen(open === t.team_id ? null : t.team_id)} />
            ))}
          </tbody>
        </table>
      </div>
      {!rows.length && <p className="text-muted">{missingOnly ? "Mọi đội trong trang này đã nộp." : "Chưa có đội nào được duyệt."}</p>}
      <Pager offset={offset} limit={LIMIT} total={list.data.total} onChange={setOffset} />
    </div>
  );
}

function Row({ t, open, onToggle }: { t: RoundSubmission; open: boolean; onToggle: () => void }) {
  const s = t.submission;
  return (
    <>
      <tr className="border-b border-dashed border-line">
        <td className="py-2 pr-3 font-bold">{t.name}</td>
        <td className="py-2 pr-3 font-mono">{s ? `v${s.version}` : <span className="chip bg-rose">Chưa nộp</span>}</td>
        <td className="py-2 pr-3">{s && <LocalTime iso={s.submitted_at} />}</td>
        <td className="py-2 pr-3 font-mono">{s?.commit_sha.slice(0, 7)}</td>
        <td className="py-2 text-right">
          {s && (
            <button type="button" className="btn bg-paper text-sm" aria-expanded={open} onClick={onToggle}>
              {open ? "Đóng" : "Xem"}
            </button>
          )}
        </td>
      </tr>
      {s && open && (
        <tr>
          <td colSpan={5} className="py-3">
            <Receipt s={s} />
          </td>
        </tr>
      )}
    </>
  );
}
