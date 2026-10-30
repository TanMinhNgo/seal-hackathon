# SEAL – Rules code

Đặc tả gốc: `docs/SEAL – Đặc tả đề tài.md`. Kế hoạch phase: `docs/PHASES.md`.
Monorepo: `backend/` (FastAPI) và `frontend/` (Next.js 16, React 19, Tailwind 4).

## Chung

- Chỉ làm đúng phạm vi mục 2.3 của đặc tả. Mục 2.4 (thanh toán, chat realtime, chạy code đội thi, mobile native, SSO) không làm.
- Thay đổi nhỏ nhất mà đủ. Không thêm abstraction, option, config "để sau dùng".
- Không thêm dependency nếu vài dòng code tự viết được. Dependency mới phải ghi lý do trong PR.
- Không commit secret. Mọi cấu hình đọc từ biến môi trường; có `.env.example` cập nhật kèm.
- Thời gian lưu và so sánh bằng UTC ở server. Frontend chỉ đổi sang giờ địa phương khi hiển thị.
- Đặt tên code bằng tiếng Anh; comment và tài liệu được viết tiếng Việt. Comment chỉ giải thích "tại sao".

## Backend (FastAPI, Python 3.12)

### Cấu trúc

- Mỗi module trong `app/modules/<name>/` gồm: `router.py`, `service.py`, `repository.py`, `schemas.py`, `models.py`.
- Luồng một chiều: `router → service → repository`. Router không gọi repository hay session DB trực tiếp. Service không import SQLAlchemy.
- Module không import `repository`/`models` của module khác; gọi qua `service` của module đó.
- Client bên ngoài (GitHub, LLM, mail, storage) chỉ nằm trong `app/integrations/`.
- `schemas.py` (Pydantic) ≠ `models.py` (SQLAlchemy). Không bao giờ trả model DB thẳng ra API.

### Phân quyền & bảo mật

- Mọi endpoint (trừ public: danh sách cuộc thi, kết quả đã công bố, đăng ký/đăng nhập) phải có dependency xác thực.
- Quyền kiểm tra theo cuộc thi qua bảng `event_roles(user_id, event_id, role)`. Admin là vai trò hệ thống riêng.
- Trưởng nhóm không phải role: kiểm tra bằng `teams.leader_id == current_user.id`.
- Kiểm tra quyền sở hữu tài nguyên trong service (chống IDOR): giám khảo chỉ đọc bài được phân công, thành viên chỉ sửa đội của mình.
- Giám khảo không thấy điểm của giám khảo khác trước khi BTC khóa điểm.
- Mọi thao tác thay đổi điểm, vai trò, trạng thái cuộc thi phải ghi `audit_logs`.
- Trạng thái cuộc thi `Draft → Open → Ongoing → Judging → Closed` chỉ đi một chiều; service chặn thao tác không hợp lệ với trạng thái hiện tại.
- Hạn nộp kiểm tra bằng giờ server, không nhận thời gian từ client.

### Database

- SQLAlchemy 2.0 async cho API; session sync trong Celery task.
- Mọi thay đổi schema qua Alembic migration. Không sửa migration đã merge.
- Ràng buộc nghiệp vụ đặt ở DB khi có thể: unique `(team_id, round_id, version)`, unique `commits.sha` theo team, unique `(user_id, event_id)` cho thành viên đội.
- Không xóa cứng commit đã lưu: force push → đánh dấu `removed`.
- FK luôn có index. Tránh N+1: dùng `selectinload`/`joinedload` khi trả danh sách.

### Worker (Celery)

- Task phải idempotent (chạy lại không tạo dữ liệu trùng).
- Task dùng client sync (`httpx.Client`), không gọi hàm `async` của API.
- Celery Beat chỉ chạy 1 instance. Chu kỳ đồng bộ commit đọc từ cấu hình cuộc thi, không hard-code 30 phút.
- Lỗi của một đội chỉ làm job con đó fail/retry, không dừng cả lượt.
- Queue `ai-review` tách riêng, concurrency thấp.

### AI review

- Output LLM ép theo schema Pydantic; validate trước khi lưu. Temperature thấp.
- System prompt ghi rõ diff chỉ là dữ liệu (chống prompt injection).
- Lưu `model` và `prompt_version` mỗi lần review. Không đổi prompt giữa một vòng thi.
- Điểm AI chỉ là tham khảo, không cộng vào điểm rubric chính thức.

### API

- Prefix `/api/v1`. Tên resource số nhiều, kebab-case: `/events/{event_id}/teams`.
- Lỗi trả `{"detail": "...", "code": "SNAKE_CASE_CODE"}` với HTTP status đúng (400/401/403/404/409/422).
- Danh sách có phân trang (`limit`, `offset`), mặc định `limit=20`, tối đa 100.

### Chất lượng

- Format + lint: `ruff format`, `ruff check`. Type hint đầy đủ cho hàm public.
- Test bằng `pytest`. Service có logic nhánh (phân quyền, hạn nộp, tính điểm, xếp hạng, đồng điểm) bắt buộc có test.
- Không dùng `print`; dùng `logging`. Không log token, mật khẩu, nội dung diff đầy đủ.

## Frontend (Next.js 16, TypeScript strict)

- App Router trong `src/app/`. Trang công khai (cuộc thi, kết quả) dùng Server Component để SSR.
- Chỉ thêm `"use client"` khi cần state, effect hoặc event handler.
- Dữ liệu server dùng TanStack Query; Zustand chỉ cho state UI thuần client (không lưu dữ liệu server vào Zustand).
- Gọi API qua một client chung trong `src/lib/api.ts`; không `fetch` rải rác trong component.
- Kiểu dữ liệu API sinh từ OpenAPI của backend (`openapi-typescript`), không gõ tay lặp lại.
- Không dùng `any`. Không tắt rule ESLint/TS trừ khi có comment lý do.
- Ẩn nút theo quyền chỉ là UX; quyền thật luôn do server quyết định.
- Upload file: gọi `/uploads/presign` lấy chữ ký Cloudinary, POST FormData gồm nguyên `fields` và `file` trực tiếp tới `upload_url`; không tự đặt multipart Content-Type. File dùng authenticated raw, tải qua URL ký từ API.
- Style bằng Tailwind; responsive tới màn hình di động. Form có `label`, ảnh có `alt`, điều khiển dùng được bằng bàn phím.
- Cấu trúc: `src/app/` (route), `src/components/` (UI dùng chung), `src/features/<module>/` (component + hook theo module), `src/lib/` (api client, util).

## Git

- Nhánh: `feat/<module>-<mô-tả>`, `fix/...`, `chore/...`. Không push thẳng `main`.
- Commit theo Conventional Commits: `feat(teams): giới hạn số thành viên`.
- PR nhỏ, một mục đích; CI (lint + test + build) phải xanh trước khi merge.
