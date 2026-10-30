import type { ReactNode } from "react";

export function AuthCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <main className="mx-auto max-w-md px-4 pb-24 pt-12 sm:px-6">
      <div className="sketch p-6 sm:p-8">
        <h1 className="text-[32px] font-black leading-none tracking-[-0.04em]">{title}</h1>
        <div className="mt-6">{children}</div>
      </div>
    </main>
  );
}

export function FormError({ children }: { children: ReactNode }) {
  return (
    <p role="alert" className="rounded-xl border-2 border-ink bg-rose px-3.5 py-2.5 text-sm font-semibold">
      {children}
    </p>
  );
}
