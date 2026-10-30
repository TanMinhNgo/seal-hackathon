# Phase 0 – Nền móng

**Mục tiêu:** dựng khung hai repo, chạy toàn bộ bằng một lệnh, FE gọi được BE.

## Hợp đồng API

| Method | Path | Quyền | Response |
| --- | --- | --- | --- |
| GET | `/api/v1/health` | public | `{"status": "ok"}` |
| GET | `/api/v1/time` | public | `{"now": "<ISO 8601 UTC>"}` – FE dùng để đếm ngược theo giờ server |

Quy ước chung cho mọi phase:

- Base URL: `http://localhost:8000/api/v1`. OpenAPI tại `http://localhost:8000/openapi.json`.
- Thời gian: chuỗi ISO 8601 có `Z` (UTC).
- Lỗi: `{"detail": "...", "code": "SNAKE_CASE_CODE"}`.
- Danh sách: query `limit` (mặc định 20, tối đa 100), `offset`; response `{"items": [...], "total": n}`.
- CORS cho `http://localhost:3000`, `allow_credentials=True` (cookie refresh token ở Phase 1).

## Backend (Codex) – `backend/`

- [x] Khung FastAPI theo cấu trúc mục 4.2 của đặc tả (`app/main.py`, `app/core/`, `app/modules/`, `app/integrations/`, `worker/`).
- [x] `core/config.py` đọc env bằng `pydantic-settings`; `.env.example` gồm `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, `FRONTEND_URL`, `CORS_ORIGINS`.
- [x] `core/db.py`: engine + session async (API) và session sync (worker).
- [x] Handler lỗi chung trả đúng format `{detail, code}`.
- [x] Alembic khởi tạo, migration rỗng đầu tiên.
- [x] Celery app + Beat, task `ping` để kiểm tra.
- [x] Endpoint `health`, `time`.
- [x] `docker-compose.yml` chỉ chạy `postgres`, `redis`; API, frontend, worker và Beat chạy local qua `run.ps1`. Mail dùng SMTP trực tiếp theo yêu cầu mới.
- [x] `ruff`, `pytest` cấu hình sẵn; 1 test cho `/health`.
- [x] GitHub Actions job backend: ruff + pytest (đã tạo workflow, chưa chạy remote).

### Bàn giao backend

Backend đã kiểm tra local: Ruff, format, 7 test pytest, dependency check và migration SQL offline; Compose đã qua `docker compose config --quiet`. `run.ps1` đã qua test mô phỏng khởi động local, migration lỗi, Docker lỗi và dọn tiến trình khi khởi động dở dang. TestClient hiện có cảnh báo deprecated từ Starlette/httpx nhưng test vẫn pass. Đã mở Docker Desktop và đối chiếu image có sẵn: `pgvector/pgvector:pg16`, `redis:8.6`. Chưa chạy container SEAL, migration online, task qua Redis hay email SMTP thật; chưa có bằng chứng CI remote.

- `health`: `GET /api/v1/health` → `{"status":"ok"}`; chỉ liveness, không cam kết DB/Redis sẵn sàng.
- `time`: `GET /api/v1/time` → `{"now":"2026-10-29T00:00:00.000000Z"}`; giờ server UTC tại thời điểm xử lý request.
- OpenAPI: `GET /openapi.json`; Swagger: `/docs`.
- Lỗi HTTP có `detail`, `code`; validation dùng `VALIDATION_ERROR`, lỗi bất ngờ dùng `INTERNAL_SERVER_ERROR` và không lộ nội dung exception. Lỗi CORS do middleware trả theo giao thức CORS.
- CORS mặc định chỉ cho `http://localhost:3000`, cho phép credentials. Socket.IO chưa cho kết nối vì chưa có xác thực.
- FE cần dùng base URL `http://localhost:8000/api/v1`, sinh type từ OpenAPI, nối health vào trang chủ và xử lý schema lỗi. Next.js public env phải đặt trước lúc build.
- JWT và cấu hình SMTP hiện đã triển khai trong lượt tài khoản đầu tiên ở [Phase 1](phase-1-xac-thuc.md); JWT_SECRET local đã được sinh riêng, tối thiểu 32 byte.

Trạng thái FE: [ ]

### Kiểm tra môi trường local sau khi sửa cổng PostgreSQL

- PostgreSQL Windows đang chiếm `5432`; StayReco sử dụng `5433`. SEAL dùng `127.0.0.1:5434` → container `5432`.
- Đã cập nhật URL trong `backend/.env`, `.env.example` và default settings; SMTP được giữ nguyên.
- Đã chạy thực tế `docker compose up --detach --wait`: PostgreSQL và Redis healthy; `alembic upgrade head` thành công, truy vấn từ backend xác nhận đúng database `seal`.
- Chưa kiểm tra toàn bộ `run.ps1` với frontend/worker/Beat thật trong lượt sửa cổng. API tài khoản được triển khai ở lượt tiếp theo, xem Phase 1.

## Frontend (Claude) – `frontend/`

- [x] Cài `@tanstack/react-query`, `zustand`, `openapi-typescript` (dev).
- [x] Script `npm run gen:api` sinh `src/lib/api-types.ts` từ `openapi.json` của BE.
- [x] `src/lib/api.ts`: client chung đọc `NEXT_PUBLIC_API_URL`, parse lỗi `{detail, code}` thành `ApiError`.
- [x] `QueryProvider` bọc trong `src/app/layout.tsx`.
- [x] Layout chung: header, footer, container responsive; thay trang mặc định của Next.
- [x] Trang chủ tạm gọi `/health` để chứng minh kết nối. Thay bằng ô `api` ở `/admin` (system overview) gọi `/health`; trang chủ là landing nên không gắn chỉ báo tạm.
- [x] Tạo thư mục `src/components/`, `src/features/`, `src/lib/`.
- [x] `.env.example` với `NEXT_PUBLIC_API_URL`.
- [x] GitHub Actions job frontend: `npm run lint` + `npm run build` (`.github/workflows/frontend.yml`).

## Xong khi

- `run.ps1` chạy PostgreSQL/Redis qua Compose và ứng dụng local, `GET /api/v1/health` trả OK.
- FE dev server hiển thị trạng thái health lấy từ BE.
- `npm run gen:api` chạy được với BE đang chạy.
- CI cả hai job xanh.

