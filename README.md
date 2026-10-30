# SEAL Hackathon

Bộ khung theo [đặc tả](docs/SEAL%20–%20Đặc%20tả%20đề%20tài.md): Next.js + FastAPI modular monolith, PostgreSQL, Redis và Celery.

## Cấu trúc

```text
frontend/
  src/app/           # App Router, layout, TanStack Query provider
  src/components/    # UI dùng chung
  src/features/      # UI và hook theo module nghiệp vụ
  src/lib/api.ts     # Axios client chung
  src/stores/        # Zustand cho state UI khi cần
backend/
  app/core/          # Settings, SQLAlchemy async session
  app/modules/       # auth, events, teams, submissions, judging, ranking, notifications, reports
  app/integrations/  # Client GitHub, LLM, mail, storage khi triển khai
  worker/tasks/      # Celery task khi triển khai nghiệp vụ
  alembic/           # Migration
  tests/
docs/
docker-compose.yml
```

Backend đã có tài khoản/xác thực/quản trị (Phase 1) và cuộc thi, vòng, track, giải, vai trò, đăng ký, đội, kiểm tra repo GitHub public (Phase 2). Chưa có nộp bài, chấm điểm, AI/storage hoặc lịch đồng bộ commit. Socket.IO đã mount nhưng từ chối kết nối cho tới khi có xác thực và kiểm tra quyền phòng.

## Chạy dev trên Windows

Yêu cầu: Node.js 24, Python 3.12, Docker Desktop đang chạy Linux containers. Thư viện đã được cài local; các lệnh cài dưới đây dành cho lần clone/setup lại.

Từ thư mục gốc, khởi động dữ liệu:

```powershell
docker compose up -d postgres redis
```

Terminal backend:

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Terminal frontend:

```powershell
cd frontend
npm ci
Copy-Item .env.example .env.local
npm run dev
```

- Web: http://localhost:3000
- Swagger: http://localhost:8000/docs
- API health: http://localhost:8000/api/v1/health (chỉ xác nhận API sống, không kiểm tra DB/Redis).

Không cần kích hoạt venv hay đổi PowerShell execution policy. Chỉ copy `.env` lần đầu để tránh ghi đè cấu hình cá nhân. Biến `NEXT_PUBLIC_*` là công khai; không đặt secret tại frontend.

## Docker Compose

Từ thư mục gốc, chạy toàn bộ và áp dụng migration:

```powershell
.\run.ps1
```

Mở Docker Desktop trước khi chạy. Script khởi động PostgreSQL/Redis bằng Compose, áp dụng migration rồi chạy API (reload), frontend dev, Celery worker và một Beat **local**. Log ở `.logs/`. Nhấn Ctrl+C để dừng các tiến trình ứng dụng do script tạo; PostgreSQL/Redis vẫn chạy. Kiểm tra script bằng mock: `pwsh -File tests/run.test.ps1`.

```powershell
docker compose up -d
docker compose logs -f postgres redis
docker compose down
```

Compose chỉ chứa PostgreSQL và Redis, dùng đúng image sẵn có trên máy: `pgvector/pgvector:pg16` (PostgreSQL 16) và `redis:8.6`. SEAL tạo container/volume riêng, không dùng chung dữ liệu của dự án khác; pgvector chưa được bật vì chưa có nghiệp vụ cần vector.

Đây là cấu hình **dev local**, dùng credential mẫu và chỉ publish cổng localhost: PostgreSQL `5434` → container `5432`, Redis `6379`. Cổng 5434 tránh PostgreSQL Windows đang dùng 5432 và StayReco đang dùng 5433. Không dùng `down -v` nếu muốn giữ dữ liệu PostgreSQL; script không tự dừng dịch vụ của dự án khác.

`NEXT_PUBLIC_API_URL` được Next.js đóng gói lúc build. Khi deploy khác localhost, cập nhật biến này ở build frontend và `CORS_ORIGINS` ở backend.

Worker trên Windows dùng pool solo. Nếu chạy từng phần thủ công:

```powershell
cd backend
.\.venv\Scripts\python.exe -m celery -A worker.celery_app:celery_app worker --pool=solo --loglevel=info
```

Beat chưa đăng ký lịch vì chưa có task đồng bộ thật. Chỉ chạy một Beat khi bổ sung lịch theo cấu hình từng cuộc thi.

## Migration và kiểm tra

```powershell
cd backend
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m alembic upgrade head
```

Đã có revision `0001_initial`, `0002_auth`, `0003_auth_admin` và `0004_events_teams` (events, rounds, tracks, prizes, teams, team_members, round_eligibilities; FK và created_at của event_roles). Khi thêm model, import model vào `alembic/env.py`, tạo revision bằng `alembic revision --autogenerate -m "..."`, đọc lại migration rồi mới upgrade. Không tự tạo bảng bằng `create_all` trong ứng dụng.

Sau migration, tạo admin đầu tiên từ terminal backend:

```powershell
.\.venv\Scripts\python.exe -m app.modules.auth.cli --email admin@example.com --full-name "SEAL Administrator"
```

CLI yêu cầu nhập mật khẩu ẩn hai lần (8–128 ký tự), tạo tài khoản đã xác thực và ghi audit cùng transaction. Không chạy được nếu đã có admin hoặc email đã dùng; không nhận mật khẩu qua command line. Không tự sinh tài khoản admin khi start API.

```powershell
cd frontend
npm run lint
npm run build
npm run typecheck
```

`requirements.in` khai báo dependency backend; `requirements-dev.in` thêm pytest/Ruff. `requirements.lock` ghim toàn bộ môi trường dev đã cài, dùng được cho setup và Docker. Sau khi chủ động đổi dependency: cài từ `requirements-dev.in`, chạy kiểm tra rồi tạo lại lock bằng `python -m pip freeze`. Frontend dùng `package-lock.json`.

Mail dùng SMTP trực tiếp, không dùng Mailpit. Điền `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM` trong `backend/.env`; `SMTP_TLS=starttls` thường đi với cổng 587, `ssl` thường đi với 465 (theo cấu hình nhà cung cấp). Đã có task gửi xác thực email; worker phải đang chạy. SMTP trong test được mock, chưa xác nhận gửi/nhận thư thật. Không đặt SMTP secret ở frontend.

API tài khoản hiện có: POST `/api/v1/auth/register`, `/verify-email`, `/resend-verification`, `/login`, `/refresh`, `/logout`, `/forgot-password`, `/reset-password` (cùng prefix auth); GET/PATCH `/api/v1/users/me`; GET `/api/v1/users/me/event-roles`; GET `/api/v1/admin/users`, PATCH `/api/v1/admin/users/{user_id}`, GET `/api/v1/admin/audit-logs`, GET `/api/v1/admin/system`. Hợp đồng, schema, mã lỗi và hướng dẫn nối frontend ở [Phase 1](docs/phases/phase-1-xac-thuc.md).

System overview chỉ dành cho admin: thống kê dữ liệu và trạng thái DB/Redis/worker/Beat/email queue/storage. Worker bận hoặc không trả lời hiển thị degraded; queue email ok không xác nhận inbox. Beat dùng HeartbeatScheduler ghi heartbeat Redis độc lập mỗi 30 giây, không phụ thuộc worker; restart Beat sau khi cập nhật code. Storage chưa chọn provider hiển thị not_configured. Không cần env hoặc migration mới cho endpoint này.

Phase 2 có 41 operation cho cuộc thi/đội; hợp đồng, giới hạn và hướng dẫn FE ở [Phase 2](docs/phases/phase-2-cuoc-thi-doi-thi.md#bàn-giao-backend-phase-2). Cấu hình `GITHUB_TOKEN` hệ thống đọc repo public trong `backend/.env` rồi restart API để dùng PUT repo/duyệt đội approved; thiếu token trả GITHUB_NOT_CONFIGURED. Kiểm tra repo không chạy code. Đóng event chờ kiểm tra kết quả đã công bố ở Phase 4.

`JWT_SECRET` cần ít nhất 32 byte, không dùng chung với dự án khác. File `.env` local đã được sinh secret riêng; xem `.env.example` để tự sinh khi setup máy mới. API auth cần Redis để rate limit và Celery worker để gửi email. Redis local dùng `127.0.0.1:6379` để tránh timeout phân giải localhost trên Windows.

Test mặc định dùng SQLite async qua `aiosqlite` (chỉ là dependency dev) và mock queue SMTP. Có thể chạy lại test auth với PostgreSQL bằng `SEAL_TEST_DATABASE_URL` trỏ tới **database test riêng** tên `seal_test_*`; fixture tạo/xóa bảng trong database đó, tuyệt đối không trỏ vào database ứng dụng.

Thư viện LLM/storage chưa cài thêm vì chưa chọn provider. Theo quy tắc dự án, sinh type frontend từ OpenAPI khi triển khai các API nghiệp vụ.

Hợp đồng và bàn giao backend hiện tại: [Phase 0](docs/phases/phase-0-nen-mong.md). Frontend tiếp tục theo phần việc riêng trong tài liệu này. Tham khảo setup: [Next.js](https://nextjs.org/docs/app/getting-started/installation), [FastAPI settings](https://fastapi.tiangolo.com/advanced/settings/).
