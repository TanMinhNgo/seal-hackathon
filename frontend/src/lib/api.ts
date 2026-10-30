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
  DEADLINE_PASSED: "Đã quá hạn nộp của vòng này (tính theo giờ máy chủ).",
  ROUND_NOT_OPEN: "Đội chưa nộp được vòng này: vòng chưa mở, đã đóng, hoặc đội chưa được BTC chọn vào vòng.",
  ROUND_NOT_FOUND: "Không tìm thấy vòng thi.",
  ROUND_NOT_ELIGIBLE: "Đội không thuộc danh sách được thi vòng này.",
  TEAM_NOT_APPROVED: "Đội chưa được duyệt nên chưa nộp được bài.",
  SUBMISSIONS_FROZEN: "Vòng này đã bắt đầu chấm, không nhận thêm phiên bản.",
  SUBMISSION_NOT_FOUND: "Không tìm thấy bài nộp.",
  IDEMPOTENCY_CONFLICT: "Lần gửi này trùng mã với một lần nộp khác. Tải lại trang rồi nộp lại.",
  REPO_MISMATCH: "Repo nộp phải đúng repo đội đã được duyệt.",
  REPO_UNAVAILABLE: "Chưa lấy được commit mới nhất từ GitHub, bài chưa được nộp. Hãy thử lại.",
  FILE_TOO_LARGE: "File vượt quá 100 MB.",
  FILE_TYPE_NOT_ALLOWED: "Chỉ nhận file .pdf, .pptx, .mp4, .zip đúng định dạng.",
  FILE_NOT_UPLOADED: "File chưa tải lên xong hoặc đã dùng cho lần nộp khác. Hãy chọn và tải lại file.",
  STORAGE_NOT_CONFIGURED: "Máy chủ chưa cấu hình nơi lưu file.",
  STORAGE_UNAVAILABLE: "Kho lưu file đang không phản hồi, hãy thử lại sau.",
};

type Presign = components["schemas"]["PresignOutput"];

/** Gửi file thẳng lên storage theo chữ ký từ `/uploads/presign`; trả `file_key` để gắn vào bài nộp. */
export async function uploadToStorage(teamId: string, file: File, contentType: string, onProgress: (ratio: number) => void) {
  const { data: p } = await api.post<Presign>("/uploads/presign", { team_id: teamId, filename: file.name, content_type: contentType, size: file.size });
  const form = new FormData();
  for (const [k, v] of Object.entries(p.fields)) form.append(k, v);
  form.append("file", file);
  // axios thuần, không qua `api`: không được gửi Bearer của SEAL sang Cloudinary; để browser tự đặt multipart boundary
  await axios.request({ url: p.upload_url, method: p.method, data: form, headers: p.headers, onUploadProgress: (e) => onProgress(e.total ? e.loaded / e.total : 0) });
  return p.file_key;
}

export function errorCode(error: unknown): string | undefined {
  return isAxiosError<{ code?: string }>(error) ? error.response?.data?.code : undefined;
}

export function errorMessage(error: unknown): string {
  if (isAxiosError(error) && !error.response) return "Không kết nối được máy chủ.";
  return MESSAGES[errorCode(error) ?? ""] ?? "Có lỗi xảy ra, hãy thử lại.";
}
