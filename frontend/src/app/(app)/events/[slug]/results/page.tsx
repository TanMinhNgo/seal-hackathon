import type { Metadata } from "next";
import { Leaderboard } from "@/features/results/leaderboard";

export const metadata: Metadata = { title: "Bảng xếp hạng · SEAL" };

export default function ResultsPage() {
  return <Leaderboard />;
}
