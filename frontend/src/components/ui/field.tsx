import type { InputHTMLAttributes } from "react";

export function Field({ label, ...props }: { label: string } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className="block">
      <span className="text-sm font-bold">{label}</span>
      <input {...props} className="mt-1.5 block min-h-11 w-full rounded-xl border-2 border-ink bg-paper px-3.5 text-[15px] read-only:bg-warm" />
    </label>
  );
}
