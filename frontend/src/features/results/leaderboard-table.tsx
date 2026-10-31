import type { Criterion, LeaderboardRow } from "@/features/events/types";

// Decimal về dạng chuỗi; chỉ đổi sang số để hiển thị, không tự tính điểm chính thức
const fmt = (v: string) => Number(v).toFixed(2);

/** Bảng xếp hạng chỉ hiển thị; dùng cho trang công khai (SSR) và màn BTC. */
export function LeaderboardTable({ rows, criteria, trackName }: { rows: LeaderboardRow[]; criteria: Criterion[]; trackName: Map<string, string> }) {
  if (!rows.length) return <p className="p-5 font-serif italic text-muted">Chưa có đội nào được xếp hạng.</p>;
  const cols = [...criteria].sort((a, b) => a.order - b.order);
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] border-collapse text-[15px]">
        <thead>
          <tr className="bg-ink text-left text-paper">
            <th scope="col" className="px-5 py-4">Hạng</th>
            <th scope="col" className="px-3 py-4">Đội</th>
            <th scope="col" className="px-3 py-4">Track</th>
            {cols.map((c) => (
              <th key={c.id} scope="col" className="px-3 py-4 text-right">
                {c.name} <span className="font-normal opacity-70">· {Number(c.weight)}%</span>
              </th>
            ))}
            <th scope="col" className="px-5 py-4 text-right">Tổng /100</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const avg = new Map(r.criteria.map((c) => [c.criterion_id, c.avg]));
            return (
              <tr key={r.team.id} className="border-t-[1.5px] border-dashed border-line">
                <td className="px-5 py-4 font-mono text-xl font-extrabold">{r.rank}</td>
                <td className="px-3 py-4 font-extrabold">
                  {r.team.name}
                  {r.tied && <span className="ml-2 rounded-lg border-[1.5px] border-dashed border-ink px-2 text-xs font-bold">đồng hạng</span>}
                </td>
                <td className="px-3 py-4">{(r.team.track_id && trackName.get(r.team.track_id)) || "—"}</td>
                {cols.map((c) => (
                  <td key={c.id} className="px-3 py-4 text-right font-mono">
                    {avg.has(c.id) ? fmt(avg.get(c.id)!) : "—"}
                  </td>
                ))}
                <td className="px-5 py-4 text-right">
                  <span className="inline-flex items-center gap-2.5">
                    <span aria-hidden className="inline-block h-2.5 w-[90px] overflow-hidden rounded-full border-[1.5px] border-ink">
                      <span className="block h-full bg-orange" style={{ width: `${Number(r.total)}%` }} />
                    </span>
                    <b className="font-mono text-lg tabular-nums">{fmt(r.total)}</b>
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export const FORMULA_NOTE =
  "Điểm = trung bình các giám khảo của Σ(điểm/điểm tối đa × trọng số), thang 100, làm tròn 2 chữ số. Đồng điểm: so điểm trung bình từng tiêu chí theo trọng số giảm dần, rồi thời điểm nộp bản cuối sớm hơn; vẫn bằng thì cùng hạng.";
