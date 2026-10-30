"use client";

import Link from "next/link";
import { useAuth } from "@/stores/auth";
import { ArrowKnob } from "./hero";

const CTA = "btn group h-14 border-cream bg-orange pl-6 pr-1.5 text-[17px] font-extrabold text-ink shadow-none hover:gap-4";

/** Tạo tài khoản và đăng ký dự thi là hai bước khác nhau; đăng ký dự thi làm trong trang từng cuộc thi. */
export function RegisterCta() {
  const { status, user } = useAuth();
  if (status === "loading") return null;

  if (!user)
    return (
      <>
        <Link href="/register" className={CTA}>
          Bước 1 · Tạo tài khoản
          <ArrowKnob />
        </Link>
        <Link href="/login?next=%2Fevents" className="px-1.5 py-3 font-bold text-cream underline underline-offset-[5px]">
          Đã có tài khoản? Đăng nhập để đăng ký dự thi
        </Link>
      </>
    );

  if (user.is_admin) return <p className="max-w-xl font-serif text-lg italic leading-normal">Tài khoản quản trị chỉ dùng để vận hành hệ thống, không đăng ký dự thi.</p>;

  return (
    <Link href="/events" className={CTA}>
      Bước 2 · Chọn cuộc thi &amp; đăng ký
      <ArrowKnob />
    </Link>
  );
}
