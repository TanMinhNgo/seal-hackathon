import axios, { isAxiosError, type InternalAxiosRequestConfig } from "axios";
import { useAuth, type User } from "@/stores/auth";
import type { components } from "./api-types";

type Token = components["schemas"]["TokenOutput"];

export const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1",
  timeout: 15_000,
  withCredentials: true,
});

api.interceptors.request.use((config) => {
  const token = useAuth.getState().accessToken;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// BE chỉ cho xoay mỗi refresh token một lần nên các lời gọi đồng thời dùng chung một promise
let refreshing: Promise<void> | null = null;
export function refreshAccessToken() {
  refreshing ??= api
    .post<Token>("/auth/refresh")
    .then((r) => useAuth.getState().setToken(r.data.access_token))
    .catch((e: unknown) => {
      useAuth.getState().clear();
      throw e;
    })
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

api.interceptors.response.use(undefined, async (error: unknown) => {
  if (!isAxiosError(error)) throw error;
  const config = error.config as (InternalAxiosRequestConfig & { _retried?: boolean }) | undefined;
  if (error.response?.status !== 401 || !config || config._retried || config.url?.startsWith("/auth/")) throw error;
  config._retried = true;
  await refreshAccessToken();
  return api(config);
});

/** Gọi khi tải app: còn cookie refresh thì khôi phục phiên, không thì thành khách. */
export async function loadSession() {
  try {
    await refreshAccessToken();
    const { data } = await api.get<User>("/users/me");
    useAuth.getState().setUser(data);
  } catch {
    useAuth.getState().clear();
  }
}

const MESSAGES: Record<string, string> = {
  EMAIL_TAKEN: "Email này đã được đăng ký.",
  INVALID_CREDENTIALS: "Email hoặc mật khẩu không đúng.",
  EMAIL_NOT_VERIFIED: "Email chưa được xác thực. Hãy mở thư xác thực hoặc gửi lại.",
  INVALID_TOKEN: "Liên kết không hợp lệ hoặc đã hết hạn.",
  ACCOUNT_DISABLED: "Tài khoản đã bị khóa.",
  EMAIL_QUEUE_UNAVAILABLE: "Tài khoản đã được lưu nhưng chưa gửi được thư. Hãy thử gửi lại sau 60 giây.",
  RATE_LIMITED: "Bạn thao tác quá nhanh, hãy thử lại sau ít phút.",
  VALIDATION_ERROR: "Dữ liệu chưa hợp lệ, hãy kiểm tra lại.",
  UNTRUSTED_ORIGIN: "Yêu cầu bị từ chối vì không đến từ trang SEAL.",
  UNAUTHORIZED: "Phiên đăng nhập đã hết, hãy đăng nhập lại.",
  FORBIDDEN: "Bạn không có quyền thực hiện thao tác này.",
  SELF_ADMIN_CHANGE: "Không thể tự khóa hoặc tự bỏ quyền quản trị của chính mình.",
  USER_NOT_FOUND: "Không tìm thấy tài khoản.",
  AUTH_UNAVAILABLE: "Hệ thống xác thực tạm thời không truy cập được cơ sở dữ liệu. Hãy thử lại sau.",
  AUTH_NOT_CONFIGURED: "Máy chủ chưa cấu hình xác thực.",
  RATE_LIMIT_UNAVAILABLE: "Máy chủ đang bận, hãy thử lại sau ít phút.",
  ALREADY_IN_TEAM: "Bạn đã ở một đội khác trong cuộc thi này.",
  EVENT_CLOSED: "Cuộc thi đã kết thúc, không thay đổi được nữa.",
  EVENT_NOT_CLOSED: "Chỉ lưu trữ được cuộc thi đã kết thúc.",
  EVENT_NOT_FOUND: "Không tìm thấy cuộc thi.",
  EVENT_ROLES_PRESENT: "Tài khoản đang giữ vai trò trong cuộc thi chưa kết thúc; gỡ vai trò trước.",
  GITHUB_NOT_CONFIGURED: "Máy chủ chưa cấu hình kết nối GitHub, chưa kiểm tra được repo.",
  GITHUB_UNAVAILABLE: "GitHub đang không phản hồi, hãy thử lại sau.",
  INVALID_INVITE_CODE: "Mã mời không đúng, đã hết hạn hoặc thuộc cuộc thi khác.",
  INVALID_SCHEDULE: "Lịch không hợp lệ: kiểm tra thứ tự các mốc thời gian.",
  INVALID_STATUS_TRANSITION: "Chưa chuyển được trạng thái này (sai thứ tự hoặc chưa tới giờ).",
  LAST_ORGANIZER: "Không bỏ được ban tổ chức cuối cùng; thêm người thay trước.",
  MEMBER_NOT_FOUND: "Không tìm thấy thành viên.",
  NOT_TEAM_LEADER: "Chỉ trưởng nhóm làm được thao tác này.",
  REGISTRATION_CLOSED: "Ngoài thời gian đăng ký.",
  REPO_NOT_ACCESSIBLE: "Repo không tồn tại hoặc không công khai. Chỉ nhận https://github.com/chủ-repo/tên-repo.",
  RESOURCE_CONFLICT: "Dữ liệu bị trùng (ví dụ đường dẫn cuộc thi đã có).",
  RESOURCE_IN_USE: "Mục này đang được dùng nên chưa xóa hay sửa được.",
  RESOURCE_NOT_FOUND: "Không tìm thấy dữ liệu.",
  RESULTS_NOT_READY: "Chưa đóng được cuộc thi: kết quả chưa công bố (Phase 4).",
  ROLE_CONFLICT: "Vai trò xung đột: người này đã có vai trò khác trong cuộc thi.",
  ROLE_IN_USE: "Người này đang có phân công nên chưa gỡ được vai trò.",
  ROLE_NOT_FOUND: "Không tìm thấy vai trò.",
  TEAM_FROZEN: "Cuộc thi đã bắt đầu: đội và repo đã khóa.",
  TEAM_FULL: "Đội đã đủ người (tính cả người đang chờ duyệt).",
  TEAM_HAS_MEMBERS: "Còn thành viên khác: chuyển trưởng nhóm trước khi rời đội.",
  TEAM_NOT_ELIGIBLE: "Đội chưa đủ điều kiện duyệt: cần đủ thành viên chính thức, không còn yêu cầu chờ và có repo.",
  TEAM_NOT_FOUND: "Không tìm thấy đội.",
  TRACK_NOT_FOUND: "Không tìm thấy track.",
};

export function errorCode(error: unknown): string | undefined {
  return isAxiosError<{ code?: string }>(error) ? error.response?.data?.code : undefined;
}

export function errorMessage(error: unknown): string {
  if (isAxiosError(error) && !error.response) return "Không kết nối được máy chủ.";
  return MESSAGES[errorCode(error) ?? ""] ?? "Có lỗi xảy ra, hãy thử lại.";
}
