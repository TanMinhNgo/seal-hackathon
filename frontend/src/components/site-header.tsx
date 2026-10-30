import Link from "next/link";
import { MainNav } from "@/features/auth/user-menu";

export function SiteHeader() {
  return (
    <header className="border-b-2 border-dashed border-line">
      <nav aria-label="Điều hướng chính" className="mx-auto flex min-h-18 max-w-[1360px] flex-wrap items-center gap-1 px-4 sm:px-6">
        <Link href="/" className="mr-auto text-[22px] font-black tracking-tight">
          SEAL
        </Link>
        <MainNav />
      </nav>
    </header>
  );
}
