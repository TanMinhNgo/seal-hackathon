import type { Metadata } from "next";
import { Be_Vietnam_Pro, JetBrains_Mono, Lora } from "next/font/google";
import type { ReactNode } from "react";
import { Providers } from "./providers";
import "./globals.css";

const vietnam = Be_Vietnam_Pro({
  subsets: ["latin", "vietnamese"],
  weight: ["400", "500", "600", "700", "800", "900"],
  variable: "--font-vietnam",
  display: "swap",
});
const lora = Lora({
  subsets: ["latin", "vietnamese"],
  style: ["italic"],
  weight: ["500", "600"],
  variable: "--font-lora",
  display: "swap",
});
const jetbrains = JetBrains_Mono({
  subsets: ["latin", "vietnamese"],
  weight: ["500", "600", "800"],
  variable: "--font-jetbrains",
  display: "swap",
});

export const metadata: Metadata = {
  title: "SEAL Hackathon",
  description: "Hệ thống quản lý cuộc thi SEAL Hackathon",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="vi" className={`${vietnam.variable} ${lora.variable} ${jetbrains.variable}`}>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
