import { create } from "zustand";
import type { components } from "@/lib/api-types";

export type User = components["schemas"]["UserOutput"];

interface AuthState {
  // access token chỉ giữ trong bộ nhớ; refresh token nằm ở cookie httpOnly
  accessToken: string | null;
  user: User | null;
  status: "loading" | "authed" | "guest";
  setToken: (token: string) => void;
  setUser: (user: User) => void;
  clear: () => void;
}

export const useAuth = create<AuthState>()((set) => ({
  accessToken: null,
  user: null,
  status: "loading",
  setToken: (accessToken) => set({ accessToken }),
  setUser: (user) => set({ user, status: "authed" }),
  clear: () => set({ accessToken: null, user: null, status: "guest" }),
}));
