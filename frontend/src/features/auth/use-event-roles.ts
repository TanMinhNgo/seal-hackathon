import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { components } from "@/lib/api-types";
import { useAuth } from "@/stores/auth";

export type EventRole = components["schemas"]["EventRoleOutput"];
export type Role = EventRole["role"];
type MyEventPage = components["schemas"]["Page_MyEvent_"];

export function useMyEventRoles() {
  const user = useAuth((s) => s.user);
  return useQuery({
    queryKey: ["my-event-roles", user?.id],
    queryFn: async () => (await api.get<EventRole[]>("/users/me/event-roles")).data,
    // Admin là vai trò hệ thống, không mang vai trò theo cuộc thi
    enabled: !!user && !user.is_admin,
    staleTime: 60_000,
  });
}

/** Cuộc thi của tôi kèm vai trò và đội; admin không dùng. */
export function useMyEvents() {
  const user = useAuth((s) => s.user);
  return useQuery({
    queryKey: ["my-events", user?.id],
    // shortcut: lấy 100 cuộc thi đầu, đủ cho một người; thêm phân trang nếu có người tham gia nhiều hơn
    queryFn: async () => (await api.get<MyEventPage>("/me/events", { params: { limit: 100 } })).data,
    enabled: !!user && !user.is_admin,
  });
}

// Giữ nhiều vai trò ở các cuộc thi khác nhau thì ưu tiên việc vận hành/chấm trước
const PRIORITY: Role[] = ["organizer", "judge", "mentor", "participant"];
export const primaryRole = (roles: EventRole[]) => PRIORITY.find((p) => roles.some((r) => r.role === p)) ?? null;

/** Màn làm việc chính sau khi đăng nhập: admin vào quản trị, còn lại vào danh sách cuộc thi của mình. */
export const homeFor = (user: { is_admin: boolean }) => (user.is_admin ? "/admin" : "/dashboard");

/** Có vai trò `role` (trong `eventId` nếu truyền). */
export function hasRole(roles: EventRole[], role: Role, eventId?: string) {
  return roles.some((r) => r.role === role && (!eventId || r.event_id === eventId));
}
