import type { ReactNode } from "react";

export function AdminTitle({ kicker, children }: { kicker: string; children: ReactNode }) {
  return (
    <div className="mb-7">
      <p className="font-serif text-lg italic">{kicker}</p>
      <h1 className="mt-1 text-[clamp(36px,5vw,56px)] font-black leading-none tracking-[-0.045em]">{children}</h1>
    </div>
  );
}
