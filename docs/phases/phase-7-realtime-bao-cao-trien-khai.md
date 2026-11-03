# Phase 7 – Realtime, thông báo, báo cáo, triển khai

**Mục tiêu:** cập nhật tức thời, thông báo trong ứng dụng, dashboard và báo cáo, đưa hệ thống lên staging/production.

**Phụ thuộc:** Phase 4 và Phase 5.

## Hợp đồng API

### Socket.IO (`/socket.io`, room riêng xác thực bằng `auth: {token: access_token}`)

| Room | Sự kiện | Payload |
| --- | --- | --- |
| `user:{user_id}` | `notification:new` | `Notification` |
| `event:{event_id}` | `leaderboard:updated` | `{round_id}` – FE refetch leaderboard |
| `event:{event_id}` | `team:approved` | `{team_id}` – FE refetch `teams/public`, hành tinh mới xuất hiện trên màn quỹ đạo |
| `event:{event_id}` | `leaderboard:unpublished` | `{round_id}` – FE bỏ dữ liệu kết quả cũ và refetch |
| `event:{event_id}:organizer` | `sync:updated` | `{team_id, CommitStats}` |
| `team:{team_id}` | `ai_review:new` | `{review_id}` |

Client gửi `join` với `{room}`; server kiểm tra quyền trước khi cho vào room.

- Guest chỉ được connect/join room `event:{event_id}` của event công khai; room này chỉ phát ID vòng/sự kiện công khai, không điểm nháp, dữ liệu đội hoặc notification nội bộ. User room chỉ của chính mình; organizer room cần đúng role; team room chỉ active member, mentor/judge được giao khi payload được phép đọc. Admin không tự vào phòng nghiệp vụ riêng, dùng REST hồ sơ và thông báo cá nhân.
- Token hết hạn thì yêu cầu refresh/kết nối lại, không giữ socket có quyền vô thời hạn. Logout, khóa user, gỡ role hoặc thu hồi phân công phải đẩy kết nối khỏi room/đóng kết nối; kiểm tra lại khi join và khi quyền thay đổi. Redis lỗi không được mở quyền mặc định. AI visibility kiểm tra trước phát: never không gửi ai_review:new cho participant.
- Mất socket vẫn dùng được bằng REST/refetch khi reconnect/focus. Sự kiện chỉ làm invalidation; leaderboard unpublish phải xóa cache công khai kể cả Guest. URL file đã ký không thu hồi tức thời được, giới hạn TTL như Phase 3.

### REST

| Method | Path | Quyền | Body → Response |
| --- | --- | --- | --- |
| GET | `/me/notifications` | login | `?unread&limit&offset` → `{items: Notification[], total, unread_count}` |
| POST | `/me/notifications/{id}/read` | login | → 204 |
| POST | `/me/notifications/read-all` | login | → 204 |
| POST | `/events/{event_id}/announcements` | organizer, event chưa closed | `{title, body, audience: public\|all\|participants\|judges\|mentors, send_email}` → 201 `Announcement` |
| GET | `/events/{event_id}/announcements` | guest chỉ public; thành viên theo audience; organizer/admin mọi audience | `?limit&offset` → `{items: Announcement[], total}` |
| GET | `/events/{event_id}/dashboard` | organizer | → `{registrations, teams_by_status, submissions_by_round, judging_progress, commits_per_day, ai_verdict_counts}` |
| GET | `/events/{event_id}/reports/export` | organizer, admin | `?type=teams\|submissions\|leaderboard&format=xlsx\|pdf&round_id&track_id` → file |
| GET | `/events/{event_id}/notification-deliveries` | organizer, admin | `?status&limit&offset` → `{items: NotificationDelivery[], total}` |

- `Notification`: `{id, type, title, body, link, read_at, created_at}`
- `NotificationDelivery`: `{id, notification_type, recipient_id, channel: in_app|email, status: queued|sent|failed|unknown, error_code, created_at, updated_at}`; chỉ nghiệp vụ trong event được đọc, không lộ email xác thực/reset, raw SMTP response hoặc token.
- `recipient_id` nullable riêng với email mời tài khoản chưa đăng ký; email đích và nội dung outbox không trả qua API. Realtime kiểm tra lại quyền trước từng lần phát và tối đa mỗi 5 giây khi idle; lỗi DB/Redis đóng kết nối. Room team chỉ nhận invalidation AI của vòng mà người nhận có quyền đọc.
- Dashboard trả các nhóm count dưới dạng object (key là status/round UUID/ngày UTC); `judging_progress` đếm trạng thái assignment, `mentor_progress` đếm trạng thái ghi nhận tiến độ mới nhất mỗi đội. `unassigned_teams`, `unsubmitted_teams` là số đội approved thiếu phân công/bài nộp ở ít nhất một vòng đủ điều kiện. Bộ lọc round/track export luôn phải thuộc event; export submissions gồm các phiên bản, không kèm URL ký hoặc file bytes.
- `Announcement`: `{id, event_id, title, body, audience, send_email, created_at}`; title 1–150, body 1–5000 ký tự plain text. public hiện cho Guest, không gửi email cho khách chưa đăng ký; all là mọi role hiện tại trong event. Email public/all chỉ gửi user active/verified đã tham gia, không bao gồm tài khoản admin ngoài event. Lịch sử announcement là nguồn để tra cứu, không chỉ giữ notification trong từng inbox.

### Báo cáo, thông báo và vận hành

- Export type=leaderboard bắt buộc round_id và vòng đã khóa; Admin không được xuất điểm chưa khóa, kết quả chưa công bố chỉ BTC hoặc Admin sau khóa. Export teams/submissions là hồ sơ riêng, không public; không có password/hash/token/invite_code, không đính kèm secret từ diff hay tên judge vào bản công khai. XLSX ghi dữ liệu người dùng thành text để không thực thi công thức; PDF render nội dung đã escape, không tự tải URL do user cung cấp.
- Nhắc hạn 24h/1h đặt ở Phase 3; Phase 7 thêm in-app và lịch sử giao nhận. `notification_deliveries` unique loại sự kiện/recipient/channel/revision, trạng thái queued/sent/failed/unknown, giữ provider receipt khi có. Notification read chỉ update của chính user, read-all idempotent, không nhận user_id từ client. Link notification chỉ route nội bộ được phép.
- Tạo thông báo nghiệp vụ cùng transaction dữ liệu, enqueue sau commit qua outbox cho lời mời, duyệt đội, phân công, hỏi/đáp, đổi lịch, nhắc hạn, công bố/thu hồi/công bố lại. Announcement/send_email được dedupe theo ID và recipient; không tự retry SMTP receipt mơ hồ (unknown). Mail sent chỉ nghĩa transport nhận, không chứng minh inbox.
- Dashboard thêm `unassigned_teams`, `unsubmitted_teams`, `unresolved_questions`, `mentor_progress`, `sync_errors`, `ai_job_counts` khi phase tương ứng có sẵn; không dùng giá trị mẫu để báo dịch vụ đang hoạt động. Export/dashboard kiểm tra quyền sở hữu event trước query.
- Health public `/api/v1/health` giữ nguyên liveness. Thêm GET `/api/v1/ready` trả `{status: ready|not_ready}` với 200/503, chỉ kiểm tra DB/Redis có timeout, không lộ endpoint nội bộ; chi tiết dịch vụ xem admin/system. Worker và Beat có heartbeat riêng, kiểm tra queue ai-review khi bật Phase 6; không dùng ping worker để xác nhận scheduler.
- `/admin/system.services[].name` bổ sung `worker_heartbeat`, `ai_queue`; queue AI thiếu consumer/heartbeat trả degraded, không suy diễn LLM/provider hoạt động từ health này.
- Worker Phase 7 tách `realtime` khỏi sync (`celery`) và email (`email`): `seal.notifications` chỉ phát realtime/in-app, `seal.notification_emails` xử lý email riêng. Health thêm `realtime_queue`; `email_queue` kiểm tra consumer queue `email`. Lỗi xác thực/quyền 401/403/404 bị từ chối; lỗi kiểm quyền tạm thời 5xx phải đóng socket để client reconnect, không âm thầm loại riêng room và không mặc định cho qua.
- Backup tự động có retention theo cấu hình vận hành, mã hóa/quyền truy cập phù hợp; trước production diễn tập restore PostgreSQL và file bài nộp vào môi trường cách ly. Ghi thời điểm backup gần nhất và biên bản restore, không đánh dấu xong chỉ vì lệnh backup exit 0. Đội đã closed giữ lịch sử; chưa có yêu cầu retention/xóa dữ liệu cá nhân thì không tự tạo job xóa hồ sơ cuộc thi.
- HTTPS, CORS, cookie, proxy IP/rate limit theo môi trường; secret chỉ qua env; không đưa log query token verify/reset hoặc signed URL vào analytics/access log. Giữ workflow dev Compose phụ trợ + ứng dụng local; cấu hình staging/production tách riêng, không ghi đè dev Compose.
- Hợp đồng báo cáo hiện trả file đồng bộ; giới hạn tối đa 10000 dòng/lần, quá giới hạn trả `422 EXPORT_TOO_LARGE` và yêu cầu thu hẹp vòng/bộ lọc. Không tự thêm hệ thống job export trước khi có nhu cầu vượt giới hạn này.

## Backend (Codex)

- [x] python-socketio mount chung ASGI app, Redis làm message queue; xác thực JWT khi connect, kiểm tra quyền khi join room.
- [x] Phát sự kiện từ worker (qua Redis manager) sau đồng bộ commit, AI review, khóa/công bố điểm.
- [x] Module `notifications`: model, tạo thông báo cho các sự kiện đã có (lời mời, duyệt đội, nhắc hạn, kết quả, announcement).
- [x] Module `reports`: query dashboard (tránh N+1), xuất xlsx (`openpyxl`) và pdf.
- [x] Nginx reverse proxy (API + websocket), HTTPS; compose cho staging/production; backup Postgres định kỳ.
- [x] Load test nộp bài sát hạn (vd. `locust`): 100 đội nộp trong 1 phút.
- [x] Health check cho api, worker, beat (dùng chung cho `/admin/system` ở Phase 1).
- [x] GET announcements theo audience, delivery/outbox và dedupe; test thu hồi quyền với socket/notification/export, retry không nhân đôi mail, SMTP unknown không tự gửi lại.
- [x] Readiness tối giản, heartbeat tách worker/Beat, restore drill và smoke test theo ma trận ROLE-REVIEW; export chống công thức và không lộ điểm trước khóa.

## Bàn giao backend Phase 7 (2026-11-03)

Checkbox Backend xác nhận code và kiểm tra local dưới đây, không thay cho nghiệm thu toàn hệ thống ở mục “Xong khi”. Không sửa `frontend/`; FE sinh lại type bằng `npm run gen:api` khi nối API mới.

- **9 HTTP operation**: 8 operation thông báo/báo cáo trong bảng REST, cùng `/api/v1/ready`. Thêm migration `0010_notifications` với `announcements`, `notifications`, `notification_deliveries`, `realtime_outbox`; đã áp dụng PostgreSQL local, `alembic check` không drift.
- Socket.IO dùng Redis manager; JWT/session còn hạn, join theo quyền hiện tại, kiểm tra lại trước phát từng packet và quét idle mỗi 5 giây. Guest chỉ vào event đọc được; Admin không vào organizer/team room. Team AI kiểm tra đúng review/vòng/assignment/membership và snapshot visibility. Thu hồi organizer/assignment hoặc logout không giữ quyền cũ. Socket chỉ invalidation; reconnect/focus vẫn refetch REST.
- Thông báo lưu cùng transaction của mời/duyệt đội, phân công, mentor/Q&A, đổi lịch, nhắc hạn, publish/unpublish/republish và lỗi sync repo. Announcement giữ lịch sử/audience. User đã mất audience không đọc nội dung riêng trong inbox; worker kiểm tra lại recipient trước gửi. Delivery API không trả payload/email đích/token. DB unique bảo vệ receipt; claim email bền trước SMTP, `unknown` không tự gửi lại. Review cùng status/note và lời mời cùng mã/email không tạo receipt mới. Sự kiện chỉ được worker phát sau commit qua outbox, không từ request chưa commit.
- `seal.notifications` quét mỗi 5 giây; worker/Beat phải restart để nhận task, heartbeat và hooks mới. Job email kết quả cũ chỉ xử lý receipt lịch sử, publish mới dùng outbox. Xem cập nhật tương thích ở Phase 2/4. SMTP chưa cấu hình trả receipt `failed/SMTP_NOT_CONFIGURED`, không trả lỗi broker sau khi đã lưu quyết định.
- Dashboard dùng aggregate SQL, không có dữ liệu mẫu. Export có kiểm tra event/round/track, giới hạn 10000 dòng, XLSX text chống công thức, PDF Unicode escape và không tải URL user. Leaderboard export bắt buộc vòng đã khóa kể cả BTC, không xuất tên judge hoặc điểm nháp. Teams/submissions chỉ chọn cột hồ sơ cần thiết, không secret hoặc URL ký.
- Cấu hình staging/production, TLS proxy, backup PostgreSQL + file mã hóa age/retention, heartbeat và hướng dẫn restore/load test ở [backend/deploy/README.md](../../backend/deploy/README.md). Compose dev ở root giữ nguyên. File backup chạy sau marker DB dump, giữ bộ archive cùng timestamp; không coi chỉ dump exit 0 là nghiệm thu restore.

### Bằng chứng kiểm tra local

- Ruff check/format và `pip check` qua; OpenAPI có đủ 9 operation mới. Hai image backend/backup build thành công; Compose và shell scripts qua kiểm tra cấu hình/cú pháp.
- **246/246 test PostgreSQL đã có kết quả passed**, gộp lượt hồi quy và lượt chạy lại sau sửa lifecycle Socket.IO: lượt đầu 198 passed + 2 teardown error; đã sửa shutdown lặp, lượt cuối nhóm bị ảnh hưởng và phần còn lại **77 passed**, đối chiếu đủ mọi node của 246 test. Nhóm SQLite socket/health/submission-jobs **8 passed, 1 skipped** (khóa dòng chỉ kiểm PostgreSQL); pipeline backup/restore và storage **18 passed**; AI visibility, thu hồi organizer/participant và inbox đã được kiểm tra. Còn cảnh báo TestClient/httpx và Alembic path_separator từ dependency hiện tại.
- Lượt tải PostgreSQL: 100 leader/đội độc lập, 200 request gồm replay, đúng **100 receipt/version**, không mất/trùng; **19.131 giây**, p95 nộp + replay **5.514 giây**. GitHub/storage là mock; đây là bằng chứng backend/DB, chưa phải tải provider hoặc nộp qua HTTPS staging.
- WebSocket + Redis thật: handshake/join ack, chặn Guest vào organizer, phát unpublish cho Guest; sau gỡ organizer, socket không nhận packet sync riêng; logout đóng socket. Nginx HTTPS/WSS local qua với chứng chỉ tự ký một ngày, chưa là chứng chỉ/domain staging thật.
- Runtime container cách ly: API ready 200; worker/Beat heartbeat độc lập qua; `database`, `redis`, `worker`, `email_queue`, `worker_heartbeat`, `ai_queue`, `beat` đều `ok`. Storage ở môi trường smoke không cấu hình và báo đúng `not_configured`.
- Restore PostgreSQL cách ly qua `pg_dump → age → decrypt → pg_restore`: đủ **38 bảng** và bản ghi kiểm chứng. Pipeline ZIP file → age thật → decrypt → phục hồi/checksum cũng qua với **file fixture**, không gọi Cloudinary thật. Các DB smoke nằm riêng `seal_test_backup_phase7` / `seal_restore_phase7_20261103`, không sửa dữ liệu cuộc thi chính.

### Chưa nghiệm thu

- Tại mốc bàn giao backend ban đầu, FE/browser và invalidation/refetch chưa được nghiệm thu. Kết quả FE mới nằm ở phần Frontend bên dưới; các lỗi được phát hiện và bản sửa backend được ghi riêng để không coi bằng chứng cũ là nghiệm thu bản mới.
- Staging/production với domain/chứng chỉ thật, frontend upstream, secret, quyền thư mục backup, lịch dài hạn/retention, giám sát và biên bản restore dữ liệu/file Cloudinary thật. Thư mục backup host cần provision theo README.
- SMTP transport/inbox thật, tải 100 đội với GitHub/Cloudinary thật và đường truyền staging. `sent` chỉ là transport nhận. Không phát email thật trong lượt này.
- Local smoke không chứng nhận CI remote hoặc production. Giữ các tiêu chí “Xong khi” và FE chưa tick cho tới nghiệm thu đủ.
- Đã tắt container smoke API/worker/Beat/proxy/Redis và PostgreSQL/Redis dev sau kiểm thử, xác minh các port 3000/8000/8017/8447/5434/6379 đã nhả; giữ volume/data, không xóa DB đã kiểm chứng.

## Frontend (Claude)

- [x] Cài `socket.io-client`; một kết nối dùng chung, tự nối lại, gửi token mới sau refresh.
- [x] Khi nhận sự kiện → `invalidateQueries` tương ứng, không tự ghép dữ liệu vào cache.
- [x] Chuông thông báo ở header: số chưa đọc, dropdown, đánh dấu đã đọc; trang `/notifications`.
- [x] BTC: form gửi thông báo hàng loạt.
- [x] BTC `/manage/events/[id]/dashboard`: thẻ số liệu + biểu đồ.
- [x] Nút xuất báo cáo (chọn loại, định dạng, vòng) và tải file; admin xuất được từ `/admin/events/[id]`.
- [x] Rà responsive trên mobile và accessibility (bàn phím, label, contrast) toàn bộ trang. Contrast chưa đo bằng công cụ, dùng lại bảng màu đã duyệt ở `docs/DESIGN.md`.
- [x] Dockerfile cho frontend, thêm vào compose staging/production riêng, giữ dev Compose phụ trợ.
- [x] Lịch sử thông báo theo audience, BTC xem notification-deliveries trong dashboard vận hành; Guest subscribe kết quả công khai, xóa dữ liệu khi thu hồi; fallback REST khi mất socket.

Trạng thái FE: [x] — 2026-11-03, nghiệm thu trình duyệt (Playwright) trên DB bản sao, có Beat + worker thật.

- Code: `src/lib/realtime.ts` (socket dùng chung, hàm `auth` gửi token mới nhất, nối lại khi đổi token, server ngắt thì làm mới token gần hết hạn rồi nối lại sau 5 giây, join lại room và refetch khi nối lại, có ack join); `components/live-refresh.tsx` (trang SSR `router.refresh()`); `features/notifications/` (chuông, `/notifications`, announcement form/lịch sử); `features/reports/` (dashboard SVG, deliveries, export). Room: `user:{id}`, `event:{id}` (bảng xếp hạng: `leaderboard:updated/unpublished`; quỹ đạo: `team:approved`), `event:{id}:organizer` (`sync:updated` → commit overview/stats), `team:{id}` (`ai_review:new`, không join với BTC/admin).
- Đã kiểm: thu hồi công bố → trang kết quả của khách tự gỡ bảng, không reload; announcement → chuông của thí sinh tăng số sau khoảng 5 giây; khách chỉ thấy announcement `public`, thí sinh thấy thêm `participants`; `ai_review:new` → tab AI của thí sinh tự thêm review sau khoảng 3 giây; xuất xlsx/pdf (BTC, admin), lỗi 422/409 đọc đúng từ body blob; dashboard, deliveries; Esc/bàn phím cho dropdown; quét 375px và nhãn/alt/tên nút trên các trang của 5 vai trò.
- Link thông báo từ BE là `/events/{event_id}`; FE redirect id → slug ở trang cuộc thi.
- Deploy: `docker compose -f backend/deploy/compose.yml -f frontend/deploy/compose.yml up -d --build`, đặt `FRONTEND_UPSTREAM=http://frontend:3000`. `NEXT_PUBLIC_API_URL` nhúng lúc build theo `DOMAIN`; SSR trong container dùng `API_INTERNAL_URL=http://api:8000/api/v1`. Image build thành công, `compose config` hợp lệ; chưa chạy cả stack staging.

### Cần backend xử lý (phát hiện khi nghiệm thu FE)

1. **Room `event:{id}:organizer` mất thành viên sau lượt kiểm quyền 5 giây.** Join trả `{ok: true}`, nhận được `sync:updated` nếu phát trong khoảng 5 giây đầu; sau đó không còn nhận dù outbox đã `sent_at`. Join lại thì nhận tiếp. Room `user:`, `event:{id}` và `team:` không bị. Gọi trực tiếp `app.realtime.authorized(token, room)` ngoài server trả `True`, nên nghi ở `watch()`/`GuardedRedisManager` trong tiến trình API. Repro: client socket.io đăng nhập BTC, join room organizer, đợi 12 giây, `POST /teams/{id}/sync`.
2. Worker `-Q celery` local (`--pool=solo`) xử lý outbox `seal.notifications` chung hàng với job sync, nên khi nhiều đội sync lần đầu thì sự kiện realtime trễ 20–30 giây. Lượt `seal.notifications` có 6 email (SMTP chưa cấu hình) chạy 11 giây.
3. Sync lần đầu gọi API chi tiết từng commit cho toàn bộ lịch sử repo; repo lớn (flask, rich…) gần như tiêu hết hạn mức GitHub 5000 request/giờ. Các đội "Load" của `fe-check-p5` và đội demo sẽ kích hoạt việc này khi bật Beat trên DB app.
4. Republish vòng 1 của `fe-check-1031b` trả `SCORING_INCOMPLETE` dù trước đó đã công bố. **Kết luận (b): fixture có conflict khai báo sau công bố**, không bỏ kiểm tra progress khi publish. HTTP 409 giữ mã `SCORING_INCOMPLETE`; `detail` bổ sung tên/ID đội, số lượt đã xác nhận/yêu cầu và cờ conflict/giám khảo không hợp lệ, không chứa điểm hoặc nhận xét của giám khảo. FE hiển thị `detail` cho BTC và tải lại `judging-progress` để xử lý phân công.


### Bản sửa backend sau nghiệm thu FE (2026-11-03)

Phạm vi ban đầu: mục 1–3 phía trên; kết luận và bằng chứng mục 4 được bổ sung riêng bên dưới. Giữ nguyên event/room/payload cho FE; không sửa frontend và không nới quyền BTC/Admin.

1. **Room BTC và kiểm quyền định kỳ:** `authorized()` trước đây gom cả `ApiError` 5xx thành `False`, nên lỗi DB/auth tạm thời có thể bị coi là thu hồi quyền và watch âm thầm loại room. Nay 5xx được phân biệt, đóng socket để FE reconnect; nếu quyền thật sự bị thu hồi trong watch cũng đóng kết nối thay vì giữ socket mất subscription. Log chỉ mã lỗi/loại lỗi, không token hoặc chi tiết provider. Không tái hiện được việc mất room sau 5 giây trong ca idle trước sửa trên SQLite/PostgreSQL, nên chưa khẳng định 5xx là nguyên nhân duy nhất của lượt FE ban đầu. Bản sửa đã kiểm tra bằng client WebSocket thật với organizer/session hiện có của **`fe-check-p5`**, API dùng pool mặc định, Redis cách ly: join thành công, đợi **12 giây**, vẫn nhận `sync:updated`; DB app chỉ đọc. Ca tự động còn kiểm tra logout, thu hồi organizer và lỗi 5xx (không được tự cho phép truy cập).
2. **Không để sync/SMTP chặn realtime:** `seal.notifications` chỉ phát outbox và in-app trên queue **`realtime`**; SMTP chuyển sang `seal.notification_emails` trên queue **`email`**. Auth email và receipt kết quả cũ cũng route queue email. Outbox invalidation chạy trước in-app. In-app không lấy khóa user mà SMTP giữ; quyền vẫn được kiểm lại trước emit, còn email giữ cơ chế serialize với thu hồi quyền và không retry `unknown`. `run.ps1` chạy **7 process** với worker riêng cho sync/realtime/email/AI; Compose backend có consumer tương ứng. `/admin/system` thêm `realtime_queue` và kiểm tra email consumer đúng queue. Smoke bằng **3 worker Celery solo thật + Redis cách ly**, giữ đồng thời worker sync và email bận 20 giây: realtime xử lý outbox trong **0.250 giây**. Đây là kiểm tra cô lập queue, không phải SLA cho mọi mức tải.
3. **Hạn mức GitHub:** baseline vẫn xác minh lịch sử head-pinned, nhưng metadata/author/message/timestamp và additions/deletions thật lấy qua GraphQL theo lô tối đa **100 SHA**, không gọi REST detail từng commit cũ. Diff baseline chưa tải trả `{items:[],total:0,truncated:true}`; dữ liệu cũ không bị xóa/ghi đè, commit mới sau baseline vẫn lưu diff. Head không đổi và lượt trước đã hoàn tất `ok` thì không quét lịch sử lại. Guard giữ **500 request/point** theo header và pause dùng chung, không fallback sang tải chi tiết hàng nghìn commit khi batch lỗi. Test **201 SHA → 3 request metadata**, reject batch thiếu/private/sai SHA/stats; smoke GitHub thật với **1 commit `octocat/Hello-World`** qua. Chưa chạy lại repo lớn thật để tránh tiêu quota; thời gian/quota baseline lớn cần theo dõi sau restart. Chi tiết và nguồn schema ở [Phase 5](phase-5-dong-bo-commit.md#độ-đầy-đủ-và-khôi-phục-đồng-bộ).

**Kiểm chứng:** nhóm commit/AI/realtime/notification/worker/system **103 passed PostgreSQL**; SQLite commit/system **51 passed**, AI/notification/worker **50 passed, 1 skipped** (test khóa dòng yêu cầu PostgreSQL). Ca giữ room qua hai lượt watch đã chạy Redis thật trên cả SQLite/PostgreSQL. Ruff check/format, mock startup/partial cleanup (`tests/run.test.ps1`) và Compose config qua. Không chạy lại toàn bộ backend hoặc toàn bộ UI trong lượt sửa này; số 246 ở phần bàn giao trước là bằng chứng của mốc trước bản sửa.

**Cập nhật runtime:** restart API, cả bốn worker và Beat để nạp code/routing mới; các lệnh có trong README và `backend/deploy/README.md`. Giữ đúng một Beat, không purge queue, không reset receipt `unknown`. Worker thường còn xử lý task cũ đang nằm queue `celery`; task mới sẽ route đúng queue. SMTP consumer thiếu sẽ được báo degraded. Các tiến trình API/worker và Redis cách ly do lượt smoke này tạo đã được tắt; PostgreSQL/Redis dev đang chạy từ trước lượt sửa được giữ nguyên.

**Nghiệm thu lại FE sau bản sửa (2026-11-03, Claude):** DB bản sao + API, worker `celery`/`realtime`, Beat thật. Client Node đợi 20 giây sau join vẫn nhận `sync:updated`. Trình duyệt BTC ở tab "Tiến độ": hai sự kiện lúc 26 và 91 giây sau khi join đều tới và refetch `commit-overview` ngay trong giây đó, socket giữ kết nối 110 giây không bị đóng. Độ trễ outbox → trình duyệt khoảng 1–5 giây. Mục 1–2 coi như đã đóng phía FE; lưu ý sync tay lặp trong 60 giây trả `429 RATE_LIMITED` nên không phát thêm sự kiện.

### Kết luận mục 4 – republish fixture `fe-check-1031b` (2026-11-03, kiểm chứng xong 2026-11-04)

**Chọn hướng (b), giữ logic kiểm tra điểm/conflict.** Khóa điểm ngăn sửa điểm/phân công nhưng không ngăn giám khảo khai báo conflict muộn. Conflict ảnh hưởng tính hợp lệ của lượt chấm; công bố lại snapshot cũ sẽ giữ điểm của giám khảo đã khai báo xung đột. Sau khi xử lý conflict, publish tiếp tục tính ranking từ các phân công hợp lệ hiện tại, tạo snapshot revision mới và ghi `audit_logs` như trước. Snapshot cũ chỉ dùng tra cứu lịch sử, không dùng để bỏ qua điều kiện công bố.

**Tái hiện trên bản sao:** khởi động riêng PostgreSQL dev đã dừng; `pg_dump -Fc` DB `seal`, tạo DB **`seal_test_republish_20261103`** rồi `pg_restore --no-owner`. DB app chỉ đọc để dump, không sửa fixture app, không chạy migration/worker/Beat/API trên DB app. DB pytest PostgreSQL riêng **`seal_test_republish_suite_20261103`**, không dùng bản sao fixture vì pytest tạo/xóa bảng. Thời điểm kiểm tra hiện tại vòng phụ thuộc đã bắt đầu nên unpublish trước tiên bị `409 RESOURCE_IN_USE`; chỉ trên bản sao, lùi lịch vòng phụ thuộc sang tương lai để cô lập lỗi mục 4, sau đó unpublish → publish tái hiện đúng `409 SCORING_INCOMPLETE`.

Dòng progress duy nhất khác `complete` (đã in ra từ `JudgingService.progress_rows()` trên bản sao):

| Đội | ID | status | required | assigned | submitted | missing | has_conflict | Nguyên nhân |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Đội Alpha | `21db0dda-0644-4d41-a846-695f218f0994` | `pending` | 2 | 2 | 2 | 0 | true | Có bài hợp lệ, hai assignment đều submitted, cả hai judge còn hợp lệ; một cặp judge–đội có conflict |

- Vòng khóa lúc **2026-10-31 16:37:50.462713 UTC**, công bố revision 2 lúc **16:38:03.022813 UTC**; snapshot revision 2 tạo lúc **16:38:02.922201 UTC**.
- Assignment bị conflict: **`84828591-625c-4ad9-8af9-1e390f38b102`**, judge **`1d1acf2d-e66a-4427-8455-5f19414f8951`**. Conflict tạo lúc **16:57:38.077761 UTC**, lý do **“Từng làm cùng công ty với trưởng nhóm”**. Assignment còn lại **`542eb1e5-a57d-47ec-9eb6-e759f6deacb6`** không bị conflict. Vì vậy nguyên nhân thực tế không phải thiếu điểm, submission mới, đội đổi trạng thái hay assignment cancelled.

**Cách sửa fixture:** dùng bản sao có vòng phụ thuộc chưa bắt đầu; BTC unpublish → unlock (có lý do) → cancel assignment xung đột (có lý do) → phân công một judge khác không có conflict → judge chấm/xác nhận đủ rubric → lock → publish. Không xóa conflict, không sửa điểm trực tiếp bằng SQL, không dùng lại snapshot để vượt kiểm tra. Trên DB app hiện tại, không lùi lịch vòng thật hoặc bỏ guard vòng phụ thuộc; cần fixture mới/cách ly để nghiệm thu lại luồng này.

**Thông điệp cho FE:** giữ HTTP **409**, `code=SCORING_INCOMPLETE`; `detail` sau sửa trên bản sao:

```text
Every submitted team needs complete conflict-free judging. Đội Alpha (21db0dda-0644-4d41-a846-695f218f0994): submitted=2, required=2, assigned=2, conflict_or_invalid_judge=True
```

Detail liệt kê các đội có bài đang chặn; tập bài rỗng dùng `No eligible submitted teams`. Không bổ sung điểm, tên/email hay nhận xét của judge. Guard quyền organizer giữ nguyên. FE hiển thị detail và dẫn BTC về tiến độ/phân công; không tự retry publish khi chưa xử lý dữ liệu.

**Kiểm chứng mục 4:** Test `test_republish_blocked_by_late_conflict_until_reassigned` bao phủ publish → unpublish → conflict muộn → republish 409, detail chỉ đội, snapshot cũ/khóa giữ nguyên, public vẫn `NOT_PUBLISHED`, không cho khóa lại trước khi thay judge và chấm đủ, sau sửa publish revision 2 có audit. `backend/alembic.ini` thêm `path_separator = os` và chạy lại `tests/test_auth_migration.py`.

- `python -m pytest tests/test_judging.py tests/test_auth_migration.py -q` trên SQLite: **14 passed, 1 skipped** (khóa dòng yêu cầu PostgreSQL).
- `ruff check .` và `ruff format --check .`: qua, **137 file** đã đúng format; `git diff --check` qua.
- Toàn bộ `python -m pytest -q` trên SQLite: **252 passed, 8 skipped**, **803.25 giây**. Còn một cảnh báo Starlette/httpx từ dependency; không còn DeprecationWarning Alembic `path_separator`.
- Toàn bộ `python -m pytest -q` với `SEAL_TEST_DATABASE_URL` trỏ DB PostgreSQL riêng nêu trên: **258 passed, 2 skipped**, **955.10 giây**; cùng một cảnh báo Starlette/httpx. Hai ca bật riêng chưa chạy là tải 100 đội (`SEAL_RUN_LOAD=1`) và socket Redis thật (`SEAL_TEST_REDIS=1`); SQLite bỏ qua thêm 6 ca khóa dòng chỉ dành cho PostgreSQL. Kịch bản republish và migration đều qua trên cả hai lượt toàn bộ.
- Không sửa `frontend/`, không commit, không đổi DB app. Chưa nghiệm thu lại browser/SMTP/staging trong lượt mục 4 này; kết quả các lượt trước giữ nguyên giới hạn. Sau test đã tắt PostgreSQL, Docker xác nhận `Running=false` và TCP `127.0.0.1:5434` không kết nối được; Windows còn ghi một số entry PID 0 nên không khẳng định bảng socket đã sạch. Giữ volume/DB bản sao để đối chiếu, đã xóa file dump tạm.

## Xong khi

- Bảng xếp hạng công khai tự cập nhật khi BTC công bố, không cần reload.
- Deploy staging bằng Docker Compose sau Nginx, HTTPS hoạt động.
- Load test nộp bài đạt, không mất hay trùng bài nộp.
- Xuất được báo cáo xlsx và pdf.
