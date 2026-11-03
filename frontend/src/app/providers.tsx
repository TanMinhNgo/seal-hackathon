"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { isAxiosError } from "axios";
import { useEffect, useState, type ReactNode } from "react";
import { loadSession } from "@/lib/api";

// Lỗi 4xx là câu trả lời của server (quyền, không tìm thấy...), thử lại chỉ làm chậm; chỉ retry lỗi mạng/5xx
const retry = (count: number, error: unknown) => count < 3 && !(isAxiosError(error) && error.response && error.response.status < 500);

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(() => new QueryClient({ defaultOptions: { queries: { retry } } }));
  useEffect(() => {
    loadSession();
  }, []);
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
