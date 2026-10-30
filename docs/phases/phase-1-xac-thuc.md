# Phase 1 – Xác thực & phân quyền

**Mục tiêu:** đăng ký, đăng nhập được; server biết user là ai và giữ vai trò gì trong từng cuộc thi.

**Phụ thuộc:** Phase 0.

## Hợp đồng API

Cơ chế token: access token (JWT, 15 phút) trả trong body, FE giữ trong bộ nhớ. Refresh token (7 ngày) nằm trong cookie `httpOnly`, `SameSite=Lax`, path `/api/v1/auth`. FE gửi `credentials: "include"`.

| Method | Path | Quyền | Body → Response |
| --- | --- | --- | --- |
| POST | `/auth/register` | public | `{email, password, full_name}` → 201 `User` |
| POST | `/auth/verify-email` | public | `{token}` → 204 |
| POST | `/auth/resend-verification` | public | `{email}` → 204 |
| POST | `/auth/login` | public | `{email, password}` → `{access_token, token_type}` + set cookie |
| POST | `/auth/refresh` | cookie | → `{access_token, token_type}` |
| POST | `/auth/logout` | cookie | → 204, xóa cookie |
| POST | `/auth/forgot-password` | public | `{email}` → 204 (luôn 204, không lộ email tồn tại) |
| POST | `/auth/reset-password` | public | `{token, new_password}` → 204 |
| GET | `/users/me` | login | → `User` |
| PATCH | `/users/me` | login | `{full_name?, student_id?, phone?, avatar_url?}` → `User` |
| GET | `/users/me/event-roles` | login | → `[{event_id, role}]` |
| GET | `/admin/users` | admin | `?q&limit&offset` → `{items: User[], total}` |
| PATCH | `/admin/users/{user_id}` | admin | `{is_active?, is_admin?}` → `User` |
| GET | `/admin/audit-logs` | admin | `?actor_id&action&limit&offset` → `{items: AuditLog[], total}` |

- `User`: `{id, email, full_name, student_id, phone, avatar_url, is_admin, is_active, email_verified, created_at}`
- `AuditLog`: `{id, actor_id, actor_email, action, target_type, target_id, data, created_at}`
- `role` (theo cuộc thi): `organizer | judge | mentor | participant`
- Link trong email trỏ về FE: `{FRONTEND_URL}/verify-email?token=...`, `{FRONTEND_URL}/reset-password?token=...`
- Mã lỗi: `EMAIL_TAKEN`, `INVALID_CREDENTIALS`, `EMAIL_NOT_VERIFIED`, `INVALID_TOKEN`, `ACCOUNT_DISABLED`.

### Lượt API tài khoản đầu tiên

Phạm vi lượt này: register, verify-email, resend-verification, login, refresh, logout, GET/PATCH users/me (8 endpoint). Admin, event-roles và quên/reset mật khẩu chưa triển khai.

- ID tài khoản là UUID. Email được chuyển lowercase; mật khẩu 8–128 ký tự, giữ nguyên khoảng trắng. `full_name` trim, dài 1–100; student_id tối đa 50, phone 30, avatar_url là HTTP(S) tối đa 2048. Không nhận trường ngoài schema; PATCH không cho sửa email, mật khẩu, cờ admin/active/verified. Trường tùy chọn được xóa bằng null, trừ full_name.
- Cookie có tên `refresh_token`, tự bật Secure khi FRONTEND_URL dùng HTTPS; chỉ dùng HTTP cho local. Refresh xoay token và gia hạn 7 ngày từ lần refresh. Token cũ không dùng lại được. Logout thu hồi phiên hiện tại; access token của phiên đó cũng bị từ chối ngay.
- Token email ngẫu nhiên, hạn 24 giờ, chỉ lưu SHA-256, dùng một lần; resend thay thế token cũ. Với email chưa tồn tại/đã xác thực/đã khóa, resend trả 204. Resend có cooldown 60 giây theo tài khoản.
- Mọi POST auth giới hạn 30 request/phút/IP qua Redis; lỗi `429 RATE_LIMITED`. Chưa tin header proxy; trước khi deploy cần cấu hình proxy phù hợp. Redis lỗi trả `503 RATE_LIMIT_UNAVAILABLE`.
- POST auth kiểm tra Origin nếu header có mặt; Origin ngoài CORS trả `403 UNTRUSTED_ORIGIN`. Client ngoài trình duyệt có thể không gửi Origin.
- Mail đi qua task Celery, gửi SMTP thật theo env. Queue không nhận job: `503 EMAIL_QUEUE_UNAVAILABLE`; tài khoản/token đã lưu, có thể yêu cầu resend sau cooldown. Job SMTP lỗi không tự retry vì provider có thể đã nhận thư. Queue nhận job chưa chứng minh inbox nhận thư.
- JWT_SECRET phải có ít nhất 32 byte; thiếu/yếu trả `503 AUTH_NOT_CONFIGURED` cho thao tác ký/đọc JWT. Access JWT chỉ chấp nhận HS256, đúng issuer/audience/loại token và phiên còn hiệu lực.

### Lượt hoàn tất backend Phase 1

- Reset token ngẫu nhiên 32 byte, chỉ lưu SHA-256, hạn 1 giờ, dùng một lần. Yêu cầu mới thay token cũ; cooldown 60 giây/tài khoản. Chỉ tài khoản active, đã xác thực được nhận reset. Forgot luôn 204 kể cả email không tồn tại hoặc queue lỗi; lỗi enqueue chỉ ghi loại lỗi, không ghi email/token. Reset thành công đổi hash mật khẩu và thu hồi tất cả phiên access/refresh trong cùng transaction; không tự đăng nhập.
- GET `/users/me/event-roles` trả toàn bộ vai trò của chính user, sắp theo event_id/role. Phase 1 chưa có API cấp vai trò cuộc thi; FK event_id bổ sung ở Phase 2. Dependency vai trò không cho admin tự vượt quyền theo cuộc thi.
- Admin users: `q` tối đa 100 ký tự, tìm chuỗi con email/full_name không phân biệt hoa thường; limit 1–100 (mặc định 20), offset >= 0. PATCH chỉ nhận boolean không null, cấm tự bỏ admin hoặc tự khóa (`403 SELF_ADMIN_CHANGE`), user không tồn tại `404 USER_NOT_FOUND`. Khóa tài khoản thu hồi mọi phiên để mở lại cũng không khôi phục token cũ. Mọi thay đổi cờ admin/active ghi audit cùng transaction; PATCH rỗng hoặc giữ nguyên không tạo audit.
- Audit log: UUID, actor_email lấy từ tài khoản hiện tại; action `user.updated` hoặc `admin.created`, target_type `user`, target_id UUID dạng chuỗi; data chỉ chứa cờ trước/sau, không có mật khẩu/token. Danh sách mới nhất trước, lọc actor_id/action chính xác, phân trang như users.
- CLI `python -m app.modules.auth.cli --email EMAIL --full-name NAME`: nhập mật khẩu ẩn và xác nhận, chỉ tạo tài khoản admin đầu tiên khi chưa có admin, email chưa dùng; tài khoản được xác thực và audit trong cùng transaction. Không truyền mật khẩu qua đối số shell. Chạy sau migration.
- Mã lỗi bổ sung: `FORBIDDEN`, `SELF_ADMIN_CHANGE`, `USER_NOT_FOUND`, `ADMIN_EXISTS`.

### Tổng quan hệ thống cho Admin (API đã triển khai)

Admin là vai trò hệ thống, chỉ quản trị (đặc tả 3.1): không chấm điểm, không làm mentor, không tham gia đội. Màn `/admin` cần biết hệ thống đang chạy thế nào và đang lưu bao nhiêu dữ liệu.

| Method | Path | Quyền | Response |
| --- | --- | --- | --- |
| GET | `/admin/system` | admin | `SystemOverview` |

- `SystemOverview`: `{server_time, services: ServiceStatus[], data: DataCounts}`
- `ServiceStatus`: `{name, status, latency_ms, detail}`; `name` ∈ `database | redis | worker | beat | email_queue | storage`; `status` ∈ `ok | degraded | down | not_configured`; `latency_ms` số nguyên hoặc null; `detail` chuỗi ngắn hoặc null, không chứa secret/URL kết nối.
- `DataCounts`: `{users, active_users, admins, events, teams, submissions, commits, ai_reviews, audit_logs, database_bytes, storage_bytes}`; bảng chưa có ở phase hiện tại trả `0`; `database_bytes`/`storage_bytes` null nếu không đo được.
- Mỗi kiểm tra có timeout ngắn (≤ 2 giây) và chạy song song; lỗi từng dịch vụ trả down/degraded theo mức xác minh, endpoint vẫn trả 200 sau xác thực thành công. `Cache-Control: no-store`.
- Worker: `inspect ping` hoặc heartbeat riêng; Beat: heartbeat riêng của scheduler (mỗi 30 giây, quá 90 giây coi stale). Ping worker không chứng minh Beat đang chạy; timeout ping khi worker bận chỉ là `degraded` nếu chưa có bằng chứng đã dừng.
- `email_queue` chỉ xác nhận broker/consumer sẵn sàng, không gửi mail thăm dò và không khẳng định SMTP/inbox thành công. Khi Redis hoặc DB mất kết nối, vẫn phải xác thực và kiểm tra admin trước; chỉ trả 200 trạng thái từng dịch vụ sau khi xác thực thành công. Nếu không xác thực được thì dùng lỗi auth/503 phù hợp, không bypass quyền để giữ 200.
- Worker kiểm tra bằng Celery inspect active_queues, giới hạn 2 giây: có phản hồi là worker ok; không phản hồi là degraded (có thể worker solo đang bận). email_queue ok khi có consumer của queue gửi mail, không kết luận về SMTP. Beat ghi heartbeat Redis độc lập từ scheduler, không qua task worker; quá 90 giây/mất key coi down. Storage chưa có provider ở Phase 1 trả not_configured, storage_bytes=null.
- DB probe sau xác thực có cả counts và database_bytes (PostgreSQL, null nếu không đo được). Khi probe lỗi/timeout: database=down, detail báo không có thống kê, counts trả 0 và byte=null; FE không được diễn giải 0 là dữ liệu rỗng khi database down. Bảng nghiệp vụ chưa tạo ở Phase 1 trả 0. Xác thực không truy vấn được DB trả `503 AUTH_UNAVAILABLE` và không chạy probes.
- [x] BE: endpoint + test admin 200, user thường 403, dịch vụ lỗi vẫn trả 200; không chạy probe trước xác thực; lỗi truy vấn phiên trả AUTH_UNAVAILABLE và không lộ connection string.

### Bổ sung từ rà soát vai trò

- [x] BE Phase 1: `AuthService.require_event_role` từ chối `is_admin=true` trước khi xét role DB. Các service nghiệp vụ Phase 2 trở đi phải dùng kiểm tra này; quyền đọc hồ sơ cho admin được cho phép tường minh theo từng endpoint, không mặc định bypass guard.
- [x] BE Phase 2: cấp admin cho user có role ở cuộc thi chưa `closed` trả `409 EVENT_ROLES_PRESENT`; giải quyết đội/phân công và thu hồi role trước. Role lịch sử ở cuộc thi đã đóng được giữ, không tạo quyền nghiệp vụ cho admin. Hạ admin không tự khôi phục role thao tác trong event đang chạy.
- [x] BE Phase 2: kiểm tra tổ hợp role theo `PHASES.md`; không cho BTC cấp organizer hoặc tạo participant bằng endpoint role, không gỡ role còn phân công đang hoạt động (`409 ROLE_IN_USE`).
- [x] BE Phase 2: khóa tài khoản là BTC active cuối cùng của event chưa closed phải trả `409 LAST_ORGANIZER`; Admin chỉ định người thay trước để cuộc thi không mất người vận hành. Không tự thêm quyền vận hành cho Admin để giải quyết tình huống này.
- [x] BE: test user có role đúng event được phép, sai event 403; sau nâng admin vẫn giữ role cũ nhưng guard nghiệp vụ trả 403. GET event-roles giữ hồ sơ lịch sử theo hợp đồng, không xóa dữ liệu để chặn quyền.
- [x] FE: không dùng sự tồn tại của event-role để vượt khu quản trị; nối system overview và kiểm tra guard UI theo API mới.

Trạng thái FE: [ ]

## Backend (Codex)

- [x] Model + migration `users`, `refresh_sessions`, `email_verification_tokens`.
- [x] Model + migration `event_roles(user_id, event_id, role)` (unique bộ ba; FK `event_id` thêm ở Phase 2), `audit_logs`.
- [x] Hash mật khẩu bằng Argon2id; mật khẩu tối thiểu 8 ký tự.
- [x] JWT access + refresh, lưu refresh token đã hash để thu hồi khi logout.
- [x] Token xác thực email: dùng một lần, có hạn, resend có cooldown.
- [x] Token reset mật khẩu: dùng một lần, có hạn.
- [x] Dependency `get_current_user`.
- [x] Dependency `require_admin`, `require_event_role(*roles)`.
- [x] Helper `AuthService.write_audit_log(...)` dùng chung cho các module sau, caller commit cùng transaction nghiệp vụ.
- [x] `integrations/mailer.py` + task Celery `send_email`; nội dung xác thực email có link về FE, hỗ trợ STARTTLS/SSL qua SMTP.
- [x] Nội dung reset mật khẩu.
- [x] Admin endpoints; admin không tự bỏ quyền admin của chính mình.
- [x] Lệnh CLI tạo admin đầu tiên.
- [x] Test: login sai, chưa xác thực email, token hết hạn/dùng lại, refresh rotation, logout thu hồi, profile không cho nâng quyền.
- [x] Test user thường gọi admin → 403.
- [x] GET `/admin/system`, thống kê dữ liệu, probe timeout/không lộ lỗi provider; Beat heartbeat độc lập và guard Admin với role lịch sử.

### Bàn giao system overview và phạm vi hoàn tất

- Phase 1 hiện có **15 operation API** (14 operation auth/profile/admin trước đây + GET `/api/v1/admin/system`); có CLI tạo admin. Ba ràng buộc EVENT_ROLES_PRESENT/ROLE_IN_USE/LAST_ORGANIZER cần event/phân công nên vẫn để Phase 2, không đánh dấu đã triển khai.
- FE sinh lại type từ OpenAPI, gọi system endpoint bằng Bearer admin; response gồm server_time UTC, sáu services và data. Dùng status/latency/detail theo schema, không tự suy “SMTP gửi được” từ email_queue=ok. storage=not_configured và storage_bytes=null là trạng thái thật ở Phase 1.
- Khi database=down, counts=0 nghĩa là chưa đo được, UI hiển thị “không có dữ liệu thống kê” thay vì số 0 thực. database_bytes/storage_bytes=null hiển thị “chưa đo được”; không đổi thành 0 byte. Đề nghị refetch tối thiểu 30 giây/lần, có nút tải lại.
- 401 xử lý refresh một lần như auth hiện có, 403 rời khu admin; 503 AUTH_UNAVAILABLE báo tạm thời không xác thực được, không diễn giải như API đang public hoặc cấp quyền từ cache.
- Không thêm env, dependency, bảng hoặc migration. Cần restart API/Beat (hoặc chạy lại run.ps1 khi đã dừng phiên cũ) để Beat dùng `worker.scheduler:HeartbeatScheduler`; scheduler ghi `seal:health:beat` mỗi 30 giây, TTL 120 giây, stale sau 90 giây. Không đăng ký task nghiệp vụ/sync giả chỉ để báo Beat đang chạy.
- Lượt này không sửa frontend, không gửi email thăm dò và không khởi động lại tiến trình đang chạy của người dùng.

Trạng thái FE: [ ]

### Bàn giao frontend cho lượt API đầu tiên

- Sinh lại type từ `/openapi.json`; 8 endpoint trên đã có request/response schema và schema lỗi trong OpenAPI. User chỉ trả các trường công khai trong hợp đồng, không trả password hash/token email/refresh token trong JSON.
- Form register gửi JSON `{email, password, full_name}`. Sau 201 chuyển sang thông báo kiểm tra email; không gọi login ngay vì phải xác thực trước. Trang `/verify-email` lấy token từ query rồi POST JSON `{token}`; token không được ghi analytics/log. FE cần `Referrer-Policy: no-referrer` cho trang chứa token.
- Login gửi JSON `{email,password}` với Axios `withCredentials: true`. Giữ access_token trong bộ nhớ; gửi `Authorization: Bearer ...` khi gọi `/users/me`. Refresh/logout cũng cần `withCredentials: true`. Cookie httpOnly không đọc bằng JS, không copy vào localStorage.
- Khi tải lại trang, gọi refresh rồi GET me; mỗi lần 401 chỉ thử refresh một lần. Các request refresh đồng thời dùng chung một promise ở FE vì BE chỉ cho xoay mỗi token một lần. Refresh fail thì xóa state auth và về login.
- PATCH me chỉ gửi các field muốn đổi; null xóa student_id/phone/avatar_url; full_name không được null/rỗng. Không gửi email/is_admin/is_active/email_verified.
- Hiển thị thông báo theo code; riêng `EMAIL_QUEUE_UNAVAILABLE` báo tài khoản đã lưu và cho resend sau 60 giây. Resend trả 204 không có nghĩa email tồn tại hay đã đến inbox.
- Các API `/auth/forgot-password`, `/auth/reset-password`, `/users/me/event-roles` và `/admin/*` đã được bổ sung trong lượt hoàn tất bên dưới.
- Sau khi đổi env cần khởi động lại backend/worker (`Ctrl+C` rồi chạy lại `run.ps1`). Với local dùng thống nhất hostname `localhost` cho trình duyệt/API để cookie không lệch host; DB/Redis dùng IPv4 `127.0.0.1`.

Trạng thái FE: [ ]

### Bàn giao frontend cho lượt hoàn tất Phase 1

- Sinh lại type từ OpenAPI; 6 operation mới: forgot-password, reset-password, event-roles, admin list users, admin patch user, admin audit logs. Cấu hình/env dùng lại Phase 1, không thêm secret.
- Form forgot gửi `{email}` và luôn hiển thị thông báo chung “Nếu tài khoản hợp lệ, hướng dẫn đặt lại mật khẩu sẽ được gửi”. Cho yêu cầu lại sau ít nhất 60 giây; 204 không xác nhận email tồn tại hoặc thư đã đến inbox.
- Trang `/reset-password` lấy token từ query, gửi `{token,new_password}` (8–128 ký tự). Không ghi token vào log/analytics; dùng Referrer-Policy no-referrer như verify-email. Thành công xóa auth state và về login; mọi phiên cũ đều bị thu hồi. `400 INVALID_TOKEN` cần xin link mới.
- Dashboard gọi GET `/users/me/event-roles` với Bearer để lấy mảng `{event_id,role}`. Có thể rỗng; UI cấp vai trò cuộc thi chờ Phase 2.
- Trang admin users gửi `q/limit/offset`, nhận `{items,total}`; PATCH chỉ gửi `{is_active?,is_admin?}` boolean. Ẩn/tắt thao tác tự khóa hoặc tự bỏ admin và vẫn xử lý `403 SELF_ADMIN_CHANGE`. Khi tài khoản bị khóa, token cũ bị từ chối ngay.
- Trang audit logs phân trang và lọc actor_id/action; hiển thị actor_email, action, target, data before/after, created_at đổi sang giờ địa phương. `403 FORBIDDEN` chuyển khỏi khu quản trị; route guard FE cần kiểm tra `user.is_admin`.
- Người vận hành chạy migration rồi tạo admin đầu tiên bằng CLI; không cần UI cấp admin công khai. Không có tài khoản admin/mật khẩu mẫu được tự tạo.

Trạng thái FE: [ ]

### Kết quả kiểm tra backend của lượt đầu

- Ruff check/format và `pip check`: pass; bộ test mặc định 38 pass. Đã chạy lại 28 ca auth trên database PostgreSQL test riêng, gồm đăng ký/refresh đồng thời; database test đã được xóa sau chạy.
- Migration thật trên database SEAL đã ở `0002_auth`; `alembic check` không phát hiện schema lệch model.
- Redis thật: 30 request được phép, request 31 bị chặn 429, key test riêng đã dọn. Đã đổi REDIS_URL local sang `127.0.0.1` vì async client qua localhost timeout trên máy này.
- Celery worker thật chạy queue test riêng nhận `seal.ping` và trả pong; đã dừng worker test. Không dispatch job gửi email thật.
- OpenAPI load được đủ 8 operation auth/profile. Chưa có bằng chứng FE nối API, CI remote hay SMTP/inbox thật. TestClient hiện có một cảnh báo deprecated Starlette/httpx, không làm test fail.

### Kết quả kiểm tra lượt hoàn tất backend

- 57 test pass trên SQLite tạm, queue mail mock; gồm reset hết hạn/thay thế/dùng một lần và gọi đồng thời, thu hồi phiên sau reset/khóa tài khoản, admin 401/403, không tự khóa/bỏ quyền, lọc/phân trang, audit rollback khi ghi lỗi, bootstrap admin và kiểm tra dependency vai trò đúng cuộc thi.
- Migration `0003_auth_admin` đã kiểm tra upgrade → đối chiếu metadata → downgrade về `0002_auth` → upgrade lại trên database SQLite tạm. Chưa áp dụng revision mới lên database ứng dụng: Docker Engine local chưa chạy, không kết nối được PostgreSQL cổng 5434. Sau khi bật Docker, chạy `alembic upgrade head` và `alembic check`; cần chạy lại test với PostgreSQL riêng để xác nhận khóa hàng/advisory lock thực tế.
- Ruff check/format và pip check pass. OpenAPI có đủ 6 operation mới. Không thêm dependency hoặc sửa frontend. Còn cảnh báo deprecation TestClient/httpx và cấu hình path_separator Alembic, không làm test fail.
- Chưa gửi SMTP thật, chưa xác nhận inbox, FE, CI remote hoặc production. Chưa tạo admin trên DB ứng dụng; CLI chỉ được kiểm tra qua logic service/test và help. Thư mục workspace hiện không có metadata Git nên không tạo commit.

### Kiểm tra lượt bổ sung system overview

- Người dùng xác nhận các kiểm tra trước đã pass; các ghi chú môi trường/SMTP ở hai lượt trên là lịch sử, không dùng chúng làm lý do dừng công việc lần này.
- Trong lượt bổ sung: bộ test đầy đủ 74 pass; sau sửa cuối về không thay current Celery app và chuẩn hóa lỗi kết nối DB, chạy lại nhóm system/admin 39 pass (có thêm 4 trường hợp so với lượt full). Ruff check/format pass.
- Test mới dùng database SQLite tạm thật và mock probe Redis/Celery; xác nhận số user/active/admin/audit, thiếu bảng phase sau trả 0, deadline các probe chạy song song, lỗi provider được ẩn, quyền 401/403/503, consumer đúng queue, heartbeat stale/invalid và scheduler không dừng khi Redis lỗi.
- Chưa khởi động Beat thật bằng scheduler mới hoặc gọi provider thật trong lượt này. Không có thay đổi schema; endpoint không chứng minh SMTP/inbox. Bước FE nối endpoint vẫn chưa được đánh dấu hoàn tất.

### Kiểm chứng heartbeat thật sau khởi động lại (2026-10-29, 23:43 giờ Việt Nam)

- Đã khởi động lại bộ ứng dụng bằng run.ps1 vì supervisor của phiên cũ dừng cả bộ khi một tiến trình thoát. Worker cũ phản hồi không có task đang chạy trước khi dừng; PostgreSQL/Redis vẫn healthy. Phiên run.ps1 mới chạy nền, log supervisor tại `.logs/supervisor-20261029-234325.out.log` và `.err.log`.
- API `/api/v1/health` và web localhost:3000 trả 200; OpenAPI đang chạy có `/api/v1/admin/system`, gọi không Bearer trả 401.
- Beat thật tạo key `seal:health:beat`; hai lần đọc cách 32 giây xác nhận timestamp tăng 30.02 giây, tuổi heartbeat 10.01 giây và TTL còn 110 giây ở lần đọc cuối. Chỉ có một cây tiến trình Beat của SEAL (venv launcher và Python con), không khởi động thêm scheduler thứ hai.
- Probe Celery thật có worker phản hồi và consumer của queue celery (queue gửi email hiện tại). Không gửi email thăm dò. Chưa kiểm tra trang Admin sau đăng nhập trong trình duyệt ở lượt vận hành này.

## Frontend (Claude)

- [x] Store auth (Zustand): `accessToken`, `user`; tự gọi `/auth/refresh` khi load app và khi gặp 401 (retry 1 lần).
- [x] Trang `/register`, `/login`, `/verify-email`, `/forgot-password`, `/reset-password`.
- [x] Trang `/profile`: xem và sửa hồ sơ.
- [x] Header: trạng thái đăng nhập, menu user, logout.
- [x] Guard route: trang cần login chuyển về `/login?next=...`; trang admin ẩn với non-admin.
- [x] Trang `/admin/users`: tìm kiếm, phân trang, khóa/mở tài khoản, cấp/bỏ admin.
- [x] Trang `/admin/audit-logs`: bảng có lọc và phân trang.
- [x] Hiển thị lỗi theo `code` bằng tiếng Việt.
- [x] Điều hướng và guard theo vai trò: admin chỉ vào khu quản trị; `/judge`, `/mentor`, đội của tôi theo `event-roles`.
- [x] Trang `/admin`: tình trạng hệ thống, dữ liệu lưu trữ, hoạt động gần đây (dùng `/admin/system`, type sinh từ OpenAPI). CSDL `down` thì không hiện số 0 mà báo chưa có thống kê.
- [x] Admin luôn vào khu quản trị trước, không dùng event-role để vượt; vào màn nghiệp vụ (`/judge`, `/mentor`, đội của tôi) bị chuyển về `/admin`.
- Mục "Cuộc thi" trong header admin chuyển sang checklist Phase 2 (cần API events).

## Xong khi

- Đăng ký → nhận mail qua SMTP → xác thực → đăng nhập → reload trang vẫn giữ phiên.
- User thường vào trang admin bị chặn ở cả FE lẫn BE (403).
- Test phân quyền BE pass.

Các ràng buộc tài khoản phụ thuộc event đã được triển khai trong Phase 2; chi tiết và giới hạn assignment ở [bàn giao Phase 2](phase-2-cuoc-thi-doi-thi.md#bàn-giao-backend-phase-2).
