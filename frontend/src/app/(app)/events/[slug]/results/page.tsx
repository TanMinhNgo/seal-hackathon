import type { Metadata } from "next";
import { Leaderboard } from "@/features/results/leaderboard";

export const metadata: Metadata = { title: "Bảng xếp hạng · SEAL" };

export default async function ResultsPage({ params, searchParams }: { params: Promise<{ slug: string }>; searchParams: Promise<{ round?: string; track?: string }> }) {
  const [{ slug }, { round, track }] = await Promise.all([params, searchParams]);
  return <Leaderboard slug={slug} roundId={round} trackId={track} />;
}
