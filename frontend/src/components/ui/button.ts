// Dùng chung cho <button> và <Link> để cùng một kiểu nút sổ phác thảo
const variants = {
  primary: "bg-ink text-paper shadow-lip-orange",
  secondary: "bg-paper text-ink",
  accent: "bg-orange text-ink",
  sun: "bg-sun text-ink",
} as const;

export type ButtonVariant = keyof typeof variants;

export function buttonClass(variant: ButtonVariant = "primary", className = "") {
  return `btn ${variants[variant]} ${className}`;
}
