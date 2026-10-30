export function Pager({ offset, limit, total, onChange }: { offset: number; limit: number; total: number; onChange: (offset: number) => void }) {
  return (
    <nav aria-label="Phân trang" className="mt-4 flex items-center justify-end gap-3 text-sm">
      <span>
        {total ? offset + 1 : 0}–{Math.min(offset + limit, total)} / {total}
      </span>
      <button type="button" className="btn bg-paper" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>
        Trước
      </button>
      <button type="button" className="btn bg-paper" disabled={offset + limit >= total} onClick={() => onChange(offset + limit)}>
        Sau
      </button>
    </nav>
  );
}
