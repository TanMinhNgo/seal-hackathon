export type EventStatus = "draft" | "open" | "ongoing" | "judging" | "closed";

// Nhãn + màu trạng thái dùng chung, xem docs/DESIGN.md
export const EVENT_STATUS: Record<EventStatus, { label: string; tone: string }> = {
  draft: { label: "Bản nháp", tone: "bg-warm" },
  open: { label: "Mở đăng ký", tone: "bg-mint" },
  ongoing: { label: "Đang thi", tone: "bg-orange" },
  judging: { label: "Đang chấm", tone: "bg-sun" },
  closed: { label: "Đã kết thúc", tone: "bg-paper" },
};

export function EventStatusBadge({ status }: { status: EventStatus }) {
  const { label, tone } = EVENT_STATUS[status];
  return (
    <span className={`chip -rotate-2 px-3 py-1 text-[13px] ${tone}`}>
      <span aria-hidden className="size-2 rounded-full bg-ink" />
      {label}
    </span>
  );
}
