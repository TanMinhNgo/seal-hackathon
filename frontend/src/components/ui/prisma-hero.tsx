"use client";

import { motion, useInView } from "framer-motion";
import { useRef, type CSSProperties } from "react";

/* ---------------- WordsPullUp ---------------- */
// Lấy từ PrismaHero; phần hero riêng của Prisma (video, nội dung) dựng lại cho SEAL ở features/home/hero.tsx
interface WordsPullUpProps {
  text: string;
  className?: string;
  showAsterisk?: boolean;
  style?: CSSProperties;
}

export const WordsPullUp = ({ text, className = "", showAsterisk = false, style }: WordsPullUpProps) => {
  const ref = useRef<HTMLDivElement>(null);
  const isInView = useInView(ref, { once: true });
  const words = text.split(" ");

  return (
    <div ref={ref} className={`inline-flex flex-wrap ${className}`} style={style}>
      {words.map((word, i) => {
        const isLast = i === words.length - 1;
        return (
          <motion.span
            key={i}
            initial={{ y: 20, opacity: 0 }}
            animate={isInView ? { y: 0, opacity: 1 } : {}}
            transition={{ duration: 0.6, delay: i * 0.08, ease: [0.16, 1, 0.3, 1] }}
            className="relative inline-block"
            style={{ marginRight: isLast ? 0 : "0.25em" }}
          >
            {word}
            {showAsterisk && isLast && <span className="absolute -right-[0.3em] top-[0.65em] text-[0.31em]">*</span>}
          </motion.span>
        );
      })}
    </div>
  );
};
