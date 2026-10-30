import type { CSSProperties } from "react";

// Hình vẽ tay trong ô 32 đơn vị, cùng bộ với DoodleCrewFooter
const PATHS = {
  star: "M0 -13 L3.6 -4.4 L13 -4 L5.8 2.2 L8.2 12 L0 6.6 L-8.2 12 L-5.8 2.2 L-13 -4 L-3.6 -4.4 Z",
  bolt: "M3 -14 L-8 2 L-1 2 L-4 14 L8 -3 L1 -3 Z",
  flame: "M0 14 C-9 14 -12 6 -10 0 C-8 -5 -4 -6 -4 -12 C1 -9 3 -5 2 -1 C4 -3 5 -6 5 -8 C10 -3 11 4 8 9 C6 12 3 14 0 14 Z",
  heart: "M0 11 C-6 6 -13 1 -13 -5 C-13 -10 -8 -13 -4 -11 C-2 -10 -1 -8 0 -6 C1 -8 2 -10 4 -11 C8 -13 13 -10 13 -5 C13 1 6 6 0 11 Z",
  sparkle: "M0 -13 C1 -4 4 -1 13 0 C4 1 1 4 0 13 C-1 4 -4 1 -13 0 C-4 -1 -1 -4 0 -13 Z",
  plane: "M-13 -1 L13 -10 L4 12 L0 3 Z",
} as const;

export type DoodleKind = keyof typeof PATHS;

const FILLS: Record<DoodleKind, string> = {
  star: "#FFD23F",
  bolt: "#FFD23F",
  flame: "#FF7A1A",
  heart: "#FF5C7A",
  sparkle: "#8FDCFF",
  plane: "#FFFFFF",
};

export function Doodle({
  kind,
  size = 32,
  fill = FILLS[kind],
  className,
  style,
}: {
  kind: DoodleKind;
  size?: number;
  fill?: string;
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <svg aria-hidden width={size} height={size} viewBox="-16 -16 32 32" className={className} style={style}>
      <path d={PATHS[kind]} fill={fill} stroke="#0D0D0D" strokeWidth="1.9" strokeLinejoin="round" />
      {kind === "plane" && <path d="M0 3 L13 -10 M0 3 L-2 9 L2 5" fill="none" stroke="#0D0D0D" strokeWidth="1.9" />}
    </svg>
  );
}
