"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { loadSession } from "@/lib/api";

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(() => new QueryClient());
  useEffect(() => {
    loadSession();
  }, []);
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
