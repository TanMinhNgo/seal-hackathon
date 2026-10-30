// Server lưu và so sánh UTC; FE chỉ đổi sang giờ máy khi hiển thị hoặc khi điền form.

const pad = (n: number) => String(n).padStart(2, "0");

/** ISO (UTC) → giá trị cho <input type="datetime-local"> theo giờ máy. */
export function toLocalInput(iso: string | null | undefined) {
  if (!iso) return "";
  const d = new Date(iso);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Giá trị datetime-local (giờ máy) → ISO UTC gửi server; rỗng → null. */
export const fromLocalInput = (v: string) => (v ? new Date(v).toISOString() : null);

export const formatDateTime = (iso: string) => new Date(iso).toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" });
export const formatDate = (iso: string) => new Date(iso).toLocaleDateString("vi-VN");
