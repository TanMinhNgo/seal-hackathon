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
- `Announcement`: `{id, event_id, title, body, audience, send_email, created_at}`; title 1–150, body 1–5000 ký tự plain text. public hiện cho Guest, không gửi email cho khách chưa đăng ký; all là mọi role hiện tại trong event. Email public/all chỉ gửi user active/verified đã tham gia, không bao gồm tài khoản admin ngoài event. Lịch sử announcement là nguồn để tra cứu, không chỉ giữ notification trong từng inbox.

### Báo cáo, thông báo và vận hành

- Export type=leaderboard bắt buộc round_id và vòng đã khóa; Admin không được xuất điểm chưa khóa, kết quả chưa công bố chỉ BTC hoặc Admin sau khóa. Export teams/submissions là hồ sơ riêng, không public; không có password/hash/token/invite_code, không đính kèm secret từ diff hay tên judge vào bản công khai. XLSX ghi dữ liệu người dùng thành text để không thực thi công thức; PDF render nội dung đã escape, không tự tải URL do user cung cấp.
- Nhắc hạn 24h/1h đặt ở Phase 3; Phase 7 thêm in-app và lịch sử giao nhận. `notification_deliveries` unique loại sự kiện/recipient/channel/revision, trạng thái queued/sent/failed/unknown, giữ provider receipt khi có. Notification read chỉ update của chính user, read-all idempotent, không nhận user_id từ client. Link notification chỉ route nội bộ được phép.
- Tạo thông báo nghiệp vụ cùng transaction dữ liệu, enqueue sau commit qua outbox cho lời mời, duyệt đội, phân công, hỏi/đáp, đổi lịch, nhắc hạn, công bố/thu hồi/công bố lại. Announcement/send_email được dedupe theo ID và recipient; không tự retry SMTP receipt mơ hồ (unknown). Mail sent chỉ nghĩa transport nhận, không chứng minh inbox.
- Dashboard thêm `unassigned_teams`, `unsubmitted_teams`, `unresolved_questions`, `mentor_progress`, `sync_errors`, `ai_job_counts` khi phase tương ứng có sẵn; không dùng giá trị mẫu để báo dịch vụ đang hoạt động. Export/dashboard kiểm tra quyền sở hữu event trước query.
- Health public `/api/v1/health` giữ nguyên liveness. Thêm GET `/api/v1/ready` trả `{status: ready|not_ready}` với 200/503, chỉ kiểm tra DB/Redis có timeout, không lộ endpoint nội bộ; chi tiết dịch vụ xem admin/system. Worker và Beat có heartbeat riêng, kiểm tra queue ai-review khi bật Phase 6; không dùng ping worker để xác nhận scheduler.
- Backup tự động có retention theo cấu hình vận hành, mã hóa/quyền truy cập phù hợp; trước production diễn tập restore PostgreSQL và file bài nộp vào môi trường cách ly. Ghi thời điểm backup gần nhất và biên bản restore, không đánh dấu xong chỉ vì lệnh backup exit 0. Đội đã closed giữ lịch sử; chưa có yêu cầu retention/xóa dữ liệu cá nhân thì không tự tạo job xóa hồ sơ cuộc thi.
- HTTPS, CORS, cookie, proxy IP/rate limit theo môi trường; secret chỉ qua env; không đưa log query token verify/reset hoặc signed URL vào analytics/access log. Giữ workflow dev Compose phụ trợ + ứng dụng local; cấu hình staging/production tách riêng, không ghi đè dev Compose.
- Hợp đồng báo cáo hiện trả file đồng bộ; giới hạn tối đa 10000 dòng/lần, quá giới hạn trả `422 EXPORT_TOO_LARGE` và yêu cầu thu hẹp vòng/bộ lọc. Không tự thêm hệ thống job export trước khi có nhu cầu vượt giới hạn này.

## Backend (Codex)

- [ ] python-socketio mount chung ASGI app, Redis làm message queue; xác thực JWT khi connect, kiểm tra quyền khi join room.
- [ ] Phát sự kiện từ worker (qua Redis manager) sau đồng bộ commit, AI review, khóa/công bố điểm.
- [ ] Module `notifications`: model, tạo thông báo cho các sự kiện đã có (lời mời, duyệt đội, nhắc hạn, kết quả, announcement).
- [ ] Module `reports`: query dashboard (tránh N+1), xuất xlsx (`openpyxl`) và pdf.
- [ ] Nginx reverse proxy (API + websocket), HTTPS; compose cho staging/production; backup Postgres định kỳ.
- [ ] Load test nộp bài sát hạn (vd. `locust`): 100 đội nộp trong 1 phút.
- [ ] Health check cho api, worker, beat (dùng chung cho `/admin/system` ở Phase 1).
- [ ] GET announcements theo audience, delivery/outbox và dedupe; test thu hồi quyền với socket/notification/export, retry không nhân đôi mail, SMTP unknown không tự gửi lại.
- [ ] Readiness tối giản, heartbeat tách worker/Beat, restore drill và smoke test theo ma trận ROLE-REVIEW; export chống công thức và không lộ điểm trước khóa.

## Frontend (Claude)

- [ ] Cài `socket.io-client`; một kết nối dùng chung, tự nối lại, gửi token mới sau refresh.
- [ ] Khi nhận sự kiện → `invalidateQueries` tương ứng, không tự ghép dữ liệu vào cache.
- [ ] Chuông thông báo ở header: số chưa đọc, dropdown, đánh dấu đã đọc; trang `/notifications`.
- [ ] BTC: form gửi thông báo hàng loạt.
- [ ] BTC `/manage/events/[id]/dashboard`: thẻ số liệu + biểu đồ.
- [ ] Nút xuất báo cáo (chọn loại, định dạng, vòng) và tải file; admin xuất được từ `/admin/events/[id]`.
- [ ] Rà responsive trên mobile và accessibility (bàn phím, label, contrast) toàn bộ trang.
- [ ] Dockerfile cho frontend, thêm vào compose staging/production riêng, giữ dev Compose phụ trợ.
- [ ] Lịch sử thông báo theo audience, BTC xem notification-deliveries trong dashboard vận hành; Guest subscribe kết quả công khai, xóa dữ liệu khi thu hồi; fallback REST khi mất socket.

Trạng thái FE: [ ]

## Xong khi

- Bảng xếp hạng công khai tự cập nhật khi BTC công bố, không cần reload.
- Deploy staging bằng Docker Compose sau Nginx, HTTPS hoạt động.
- Load test nộp bài đạt, không mất hay trùng bài nộp.
- Xuất được báo cáo xlsx và pdf.
