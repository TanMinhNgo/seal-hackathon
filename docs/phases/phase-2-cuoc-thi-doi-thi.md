# Phase 2 – Cuộc thi & đội thi

**Mục tiêu:** Admin tạo cuộc thi/giao BTC; BTC cấu hình, thí sinh đăng ký, lập đội, khai báo repo.

**Phụ thuộc:** Phase 1.

## Hợp đồng API

### Cuộc thi

`status`: `draft | open | ongoing | judging | closed`, chỉ chuyển theo thứ tự này.

| Method | Path | Quyền | Body → Response |
| --- | --- | --- | --- |
| GET | `/events` | public | `?status&q&include_archived&limit&offset` → `{items: EventSummary[], total}` (không trả `draft` cho người không phải BTC/admin; `include_archived` chỉ admin) |
| GET | `/events/{event_id}` | public (draft, đã lưu trữ: BTC, admin) | → `Event` |
| GET | `/events/by-slug/{slug}` | như GET chi tiết | → `Event` (đăng ký route trước `/{event_id}`) |
| GET | `/me/events` | login, trừ admin | `?limit&offset` → `{items: MyEvent[], total}` |
| POST | `/events` | admin | `EventInput` + `organizer_email` → 201 `Event` (gán `organizer` cho email đó; admin **không** tự thành BTC) |
| PATCH | `/events/{event_id}` | organizer, admin | `EventInput` (partial) → `Event` (admin sửa ghi audit log) |
| POST | `/events/{event_id}/archive` | admin (chỉ khi `closed`) | `{archived: bool}` → `Event` (ẩn/hiện ở trang công khai, không xóa dữ liệu) |
| POST | `/events/{event_id}/transition` | organizer | `{to_status}` → `Event` |
| GET/POST | `/events/{event_id}/rounds` | đọc theo quyền Event / organizer ghi | GET `?limit&offset` → `{items: Round[], total}`; POST `RoundInput` → 201 `Round` |
| PATCH/DELETE | `/events/{event_id}/rounds/{round_id}` | organizer | |
| GET/POST | `/events/{event_id}/tracks` | đọc theo quyền Event / organizer ghi | GET `?limit&offset` → `{items: Track[], total}`; POST `{name, description}` → 201 `Track` |
| PATCH/DELETE | `/events/{event_id}/tracks/{track_id}` | organizer | |
| GET/POST | `/events/{event_id}/prizes` | đọc theo quyền Event / organizer ghi | GET `?limit&offset` → `{items: Prize[], total}`; POST `{name, description, rank, value}` → 201 `Prize` |
| PATCH/DELETE | `/events/{event_id}/prizes/{prize_id}` | organizer | |
| GET | `/events/{event_id}/roles` | organizer, admin | `?role&q&limit&offset` → `{items: [{id, user: UserBrief, role}], total}` |
| POST | `/events/{event_id}/roles` | organizer chỉ judge/mentor; admin chỉ organizer | `{email, role}` → 201 (không tự cấp cho admin) |
| DELETE | `/events/{event_id}/roles/{role_id}` | organizer chỉ judge/mentor; admin chỉ organizer | → 204 (không xóa BTC cuối cùng, chặn role đang được sử dụng) |
| POST | `/events/{event_id}/register` | login, trừ admin/vai trò vận hành cùng event | → 201, gán role `participant` (chỉ khi `open` và trong thời gian đăng ký) |
| DELETE | `/events/{event_id}/register` | chính participant chưa có đội | → 204 (chỉ trong thời gian đăng ký; ghi audit) |
| GET | `/events/{event_id}/registrations` | organizer, admin | `?q&limit&offset` → `{items: Registration[], total}` |
| GET | `/events/{event_id}/team-directory` | judge của event | `?q&limit&offset` → `{items: TeamBrief[], total}` (phục vụ khai báo xung đột trước phân công) |

- `Event`: `{id, name, slug, description, rules, banner_url, status, registration_opens_at, registration_closes_at, starts_at, ends_at, min_team_size, max_team_size, archived_at, created_at}`
- `EventSummary` thêm `team_count`, `participant_count`, `archived_at` cho danh sách của admin.
- `Round`: `{id, event_id, name, order, starts_at, submission_deadline, ends_at}`
- `UserBrief`: `{id, full_name, email, avatar_url}`
- `MyEvent`: `{event: EventSummary, roles: string[], team: {id, name, status, member_status}|null}`; chỉ event user có role, gồm vai trò lịch sử sau đóng, không trả event của người khác. Event lưu trữ chỉ đọc với người đã tham gia; không xuất hiện ở trang công khai.
- `Registration`: `{user: UserBrief, registered_at, team_id, member_status}`; chỉ người đang đăng ký, gồm người chưa có đội. Role participant có `created_at` để ghi nhận thời gian; rút đăng ký xóa role hiện tại và giữ audit. Không dùng endpoint role để duyệt/từ chối cá nhân: cá nhân tự đăng ký, BTC duyệt đội.
- `TeamBrief`: `{id, name, track_id}`; không thành viên/email/repo/invite_code. Không cho judge đọc Team đầy đủ khi chưa phân công.

### Giới hạn cấu hình và vòng đời đội

- `EventInput`: các trường có thể ghi của Event, không nhận id/status/archived_at/created_at. POST nhận organizer_email riêng. Admin chỉ PATCH name/description/banner_url; cấu hình vận hành, thể lệ, lịch, giới hạn đội do BTC quản lý. `slug` duy nhất và không đổi sau `draft`.
- `RoundInput`: `{name, order, starts_at, submission_deadline, ends_at, required_judges?}`; required_judges mặc định 2, tối thiểu 1; Round response thêm trường này. Tất cả mốc UTC; `registration_opens_at < registration_closes_at <= starts_at < ends_at`, `round.starts_at < submission_deadline <= round.ends_at` và vòng nằm trong thời gian event. Min/max đội là số nguyên `1 <= min <= max`; thi cá nhân dùng min=max=1.
- Draft và event lưu trữ áp dụng cùng giới hạn truy cập cho rounds/tracks/prizes/rubric/announcements, không chỉ GET Event. Event lưu trữ cho người từng tham gia đọc dữ liệu của mình theo quyền cũ; Admin/BTC đọc hồ sơ; không ghi nghiệp vụ mới.
- Tạo đội, đổi tên/track, vào/rời/duyệt thành viên, chuyển leader, quay mã và sửa repo chỉ khi `open` và chưa tới starts_at; tới giờ thi đóng băng đội/repo dù BTC chuyển trạng thái trễ. Link repo chỉ nhận HTTPS github.com/owner/repo, kiểm tra qua GitHub client, không fetch URL bất kỳ từ người dùng.
- Mã mời có ít nhất 128 bit entropy, chỉ active member thấy; tạo lại hủy mã cũ. `invite_expires_at = registration_closes_at`; hết hạn hoặc khác event không gia nhập được. Join có rate limit 30/phút/user; request pending cũng tính vào max_team_size để không giữ chỗ vô hạn. Người dùng được hủy yêu cầu pending qua DELETE chính mình.
- Leader cuối cùng rời đội khi `open` thì giải tán mềm (`disbanded_at`), hủy mã, gỡ membership hiện tại; giữ bản ghi/audit, không xuất hiện trong danh sách đội hoạt động. Nếu còn người khác kể cả pending phải chuyển leader cho active member trước. Không giải tán sau khi thi bắt đầu.
- Đội approved bị đổi tên/track/repo/thành viên thì trở về pending, xóa kết quả duyệt hiện tại nhưng giữ audit. Team response thêm `review_note`, `reviewed_at`, `disbanded_at`, `invite_expires_at`; note từ chối bắt buộc, leader sửa để gửi duyệt lại. Duyệt approved yêu cầu đủ min/max active member, không pending, repo hợp lệ.
- Chuyển open → ongoing chỉ từ giờ starts_at, không có đội approved sai điều kiện; đội pending/rejected không được nộp bài hoặc nhận phân công. Không sửa thời gian vòng đã bắt đầu, rubric đã có điểm, xóa track đang dùng hoặc vòng có bài nộp/phân công. Mọi đổi lịch trước bắt đầu ghi audit và phát thông báo khi Phase 7 có sẵn.
- DELETE role/phân công thu hồi quyền đọc mới ngay; audit và tác phẩm lịch sử vẫn giữ. Không xóa/khóa BTC active cuối của event chưa closed; chỉ định người thay trước. Không gán role vận hành cho participant hoặc admin; mentor từng hỗ trợ một đội không được chấm đội đó. BTC duyệt đội chỉ khi open và chưa starts_at.
- Mã lỗi bổ sung: `ROLE_CONFLICT`, `ROLE_IN_USE`, `EVENT_ROLES_PRESENT`, `TEAM_FROZEN`, `TEAM_HAS_MEMBERS`, `INVALID_SCHEDULE`, `RESOURCE_IN_USE`; vi phạm trạng thái/ràng buộc 409, quyền 403, input sai 422.

### Đội thi

`team.status`: `pending | approved | rejected`. `member.status`: `pending | active`.

| Method | Path | Quyền | Body → Response |
| --- | --- | --- | --- |
| POST | `/events/{event_id}/teams` | participant chưa có đội | `{name, track_id?}` → 201 `Team` (người tạo là leader) |
| GET | `/events/{event_id}/teams` | organizer, admin | `?status&track_id&q&limit&offset` → `{items: Team[], total}` |
| GET | `/events/{event_id}/teams/me` | participant | → `Team` hoặc 404 |
| GET | `/events/{event_id}/teams/public` | public | → `[{id, name, track_id, member_count, approved_at}]` – chỉ đội `approved`, không có thông tin cá nhân; không phân trang (màn quỹ đạo vẽ toàn bộ), sắp theo `approved_at` |
| GET | `/teams/{team_id}` | thành viên, organizer, mentor/judge được phân công, admin | → `Team` |
| PATCH | `/teams/{team_id}` | leader | `{name?, track_id?}` → `Team` |
| POST | `/teams/{team_id}/invite-code` | leader | → `{invite_code}` (tạo mã mới, mã cũ hết hiệu lực) |
| POST | `/teams/{team_id}/invitations` | leader, event open | `{email}` → 202 `{status: queued}` (gửi link với mã hiện tại, không tự đổi mã) |
| POST | `/teams/join` | participant chưa có đội | `{invite_code}` → `Team` (member `pending`) |
| POST | `/teams/{team_id}/members/{user_id}/approve` | leader | → `Team` |
| DELETE | `/teams/{team_id}/members/{user_id}` | leader, hoặc chính user (rời đội) | → 204 |
| POST | `/teams/{team_id}/transfer-leader` | leader | `{user_id}` → `Team` |
| PUT | `/teams/{team_id}/repo` | leader | `{repo_url}` → `Team` (BE kiểm tra repo public) |
| POST | `/teams/{team_id}/review` | organizer | `{status: approved\|rejected, note?}` → `Team` |

- `Team`: `{id, event_id, name, status, track_id, leader_id, invite_code (chỉ trả cho thành viên; không trả cho admin), repo_url, members: [{user: UserBrief, status, joined_at}], created_at}`
- Link mời FE: `{FRONTEND_URL}/join?code=...`
- Gửi lời mời không tạo thành viên hoặc tiết lộ email đã đăng ký; mã hết hạn phải quay mã trước. Giới hạn 30 email/giờ/leader; queue lỗi trả `503 EMAIL_QUEUE_UNAVAILABLE`, queued không chứng minh inbox nhận. Người nhận vẫn phải đăng nhập, đăng ký đúng event và xin vào đội.
- Mã lỗi: `LAST_ORGANIZER`, `EVENT_NOT_CLOSED`, `INVALID_STATUS_TRANSITION`, `REGISTRATION_CLOSED`, `ALREADY_IN_TEAM`, `TEAM_FULL`, `INVALID_INVITE_CODE`, `REPO_NOT_ACCESSIBLE`, `NOT_TEAM_LEADER`.

## Backend (Codex)

- [x] Module `events`: model + migration `events`, `rounds`, `tracks`, `prizes`, `round_eligibilities` (unique round/team, FK round/team có index); thêm FK `event_roles.event_id`. Eligibility được đọc qua events service ở Phase 3 và cấu hình bằng API Phase 4; không để Phase 3 import module tương lai.
- [x] Máy trạng thái: bảng chuyển hợp lệ trong service; ghi audit log mỗi lần chuyển.
- [x] Mỗi thao tác kiểm tra trạng thái theo mục "Giới hạn cấu hình và vòng đời đội"; tạo/thay đổi đội chỉ khi `open`.
- [x] Module `teams`: model `teams`, `team_members` với unique `(event_id, user_id)` để mỗi người chỉ ở một đội.
- [x] Kiểm tra `max_team_size` trong transaction (khóa hàng `teams` khi duyệt thành viên).
- [x] Leader không được rời đội khi còn thành viên khác; phải chuyển quyền trước.
- [x] `integrations/github_client.py`: kiểm tra repo public (`GET /repos/{owner}/{repo}`) bằng token hệ thống.
- [x] Email lời mời và kết quả duyệt đội.
- [x] Quyền admin theo "Phân tách vai trò" trong `PHASES.md`: đọc các endpoint hồ sơ cho phép rõ trong bảng quyền, không mặc định toàn bộ GET (ví dụ `/me/events` không dành cho admin); tạo/sửa metadata/lưu trữ cuộc thi, thêm/bỏ BTC có audit. Thao tác nghiệp vụ đội, duyệt đội, vòng, track, giải, chuyển trạng thái vẫn 403 với admin.
- [x] Cột `events.archived_at`; trang công khai bỏ cuộc thi đã lưu trữ. Không xóa cứng cuộc thi đã qua `draft` cùng đội, thành viên.
- [x] Dashboard `/me/events`, resolver slug, registrations và team-directory theo schema; participant role có created_at; kiểm tra cấu hình thời gian, tổ hợp role và dữ liệu public.
- [x] Vòng đời mã mời/đội duyệt lại/giải tán mềm; test member pending không đọc dữ liệu nội bộ, IDOR event-round-track, đội thi cá nhân, role cấp chéo và lịch sai.
- [x] Test: đội đầy, vào đội thứ hai, chuyển trạng thái sai, non-leader sửa đội; admin đọc đội nhưng không thấy `invite_code`; admin duyệt đội/chuyển trạng thái → 403; lưu trữ cuộc thi chưa `closed` → 409; xóa BTC cuối cùng → 409.

## Frontend (Claude)

- [x] Trang công khai `/events` (SSR): danh sách, lọc theo trạng thái, tìm kiếm.
- [x] Trang công khai `/events/[slug]` (SSR): mô tả, thể lệ, timeline vòng thi, track, giải thưởng, nút đăng ký.
- [x] Khu BTC `/manage/events/[id]`: tab Thông tin, Vòng thi, Track, Giải thưởng, Vai trò, Đội thi; nút chuyển trạng thái có xác nhận.
- [x] Admin `/admin/events`: mọi cuộc thi (kể cả draft, đã lưu trữ), lọc trạng thái, tìm kiếm, số đội/thí sinh.
- [x] Admin: form tạo cuộc thi kèm email BTC phụ trách; sửa metadata được phép; nút lưu trữ/bỏ lưu trữ (chỉ khi `closed`, có xác nhận).
- [x] Admin `/admin/events/[id]`: thông tin, timeline vòng, BTC (thêm/bỏ), danh sách đội (lọc trạng thái/track).
- [x] Admin `/admin/teams/[id]`: thành viên, leader, track, trạng thái duyệt, link repo; khung tab cho commit/đánh giá ở phase sau.
- [x] Header admin thêm mục "Cuộc thi".
- [x] Khu thí sinh `/events/[slug]/my-team`: tạo đội, nhập mã mời, xem thành viên, duyệt/xóa thành viên, chuyển leader, chọn track, khai báo repo, sao chép link mời.
- [x] Trang `/join?code=...`: tham gia đội bằng link.
- [x] Trang công khai `/events/[slug]/teams` "Vũ trụ đội thi": cuộc thi là mặt trời, mỗi đội đã duyệt là một hành tinh quay theo chiều kim đồng hồ, không giới hạn số đội (đã có giao diện với dữ liệu mẫu, chờ nối `teams/public`).
- [x] Bảng duyệt đội cho BTC (lọc theo trạng thái/track).
- [x] Trang `/dashboard`: danh sách cuộc thi tôi tham gia, kèm vai trò.
- [x] Nối `/me/events` cho dashboard, slug resolver cho trang chi tiết; màn BTC xem người chưa có đội.
- [ ] Judge chọn tên đội từ `team-directory` để khai báo xung đột: làm cùng màn giám khảo ở Phase 4.
- [x] Hiển thị review_note, yêu cầu pending và mã mời hết hạn; cho rút đăng ký/hủy yêu cầu, khóa thao tác đội khi ongoing.

Trạng thái FE: [ ]

### Kết quả kiểm tra backend (2026-10-30)

- Ruff check và format pass. Bộ test đầy đủ: 106 pass, 2 skip trên SQLite; hai ca chỉ kiểm tra PostgreSQL không được coi là đã pass nhờ SQLite.
- Đã chạy 42 ca Phase 2/admin trên PostgreSQL test riêng: tất cả pass, gồm giới hạn đội khi join đồng thời. Sau các thay đổi cuối, chạy thêm 3 ca PostgreSQL về join tranh chấp, cấp role cùng lúc nâng admin, cập nhật giới hạn đội/hạn mã mời: tất cả pass. Các database test đã được xóa sau chạy, không dùng DB ứng dụng để reset test.
- Migration mới được thử upgrade → alembic check → downgrade 0003 → upgrade lại → alembic check trên PostgreSQL riêng; schema khớp model. SQLite có kiểm tra migration round-trip riêng.
- Database SEAL local đã upgrade tới 0004_events_teams, alembic check không có thay đổi chưa ghi migration. API đang chạy có 41 operation Phase 2; GET /api/v1/events trả 200. OpenAPI giữ schema Team/Event đầy đủ và thể hiện optional authentication cho các GET public.
- Đã bật kiểm tra foreign key SQLite trong fixture, bổ sung event thật cho fixture role cũ; test có kiểm tra timezone +07:00 lưu/đọc đúng UTC và giá trị giải thưởng/audit không đi qua float mất độ chính xác.
- Không sửa frontend, không thêm dependency, không gửi email thật trong lượt triển khai này. GitHub dùng HTTP mock; GITHUB_TOKEN local chưa được cấu hình, nên chưa có chứng cứ repo/provider thật. Chưa chứng nhận FE nối API hoặc CI remote. Còn cảnh báo deprecation TestClient/httpx và Alembic path_separator, không làm test fail.

## Xong khi

- Backend Phase 2 chạy Draft → Open → Ongoing → Judging và luồng lập đội; chuyển Closed cần kết quả đã công bố ở Phase 4. Demo đầy đủ trên giao diện chờ FE nối API và Phase 4.
- Repo private bị từ chối khi khai báo.
- Test BE về giới hạn đội và trạng thái pass.


## Bàn giao backend Phase 2

### Dữ liệu demo local (2026-10-30)

- Đã thêm `backend/app/seed_demo.py`: 19 tài khoản theo vai trò, 4 cuộc thi
  draft/open/ongoing/judging, 8 vòng, 8 track, 12 giải, 12 đội, 36 bản ghi thành viên,
  62 event-role và audit `demo.seeded`. Không sửa tài khoản cũ, không tạo closed
  hoặc dữ liệu các phase chưa triển khai. Chạy lại giữ nguyên dữ liệu và lịch.
- Hướng dẫn chạy, tài khoản và kịch bản FE: [backend/DEMO-DATA.md](../../backend/DEMO-DATA.md).
  Không thay đổi endpoint/schema; FE dùng API đã có thay nguồn mock hiện tại.
- Bộ mẫu v2 làm rõ nội dung cuộc thi, thống nhất lịch sử tạo/đăng ký/gia nhập và
  thêm repo tham chiếu public cho đội approved; `python -m app.seed_demo --clean`
  nâng bộ mẫu v1 tại chỗ, giữ nguyên tài khoản, lịch thi và nội dung người dùng tự sửa.
  Repo là nguồn tham khảo của chủ sở hữu tương ứng, không phải repo do đội demo sở hữu.
- Trạng thái FE: [ ]

Đã triển khai **41 operation**, xem hợp đồng phía trên và OpenAPI `/openapi.json`. Các checklist Backend đánh dấu hoàn thành ở mức code/test; không đồng nghĩa FE hoặc GitHub/SMTP thật đã được nghiệm thu. FE không được sửa tay type API.

### Schema và hành vi đã chốt

- `EventInput`: name 1–100, slug lowercase kebab-case tối đa 120; description/rules tối đa 20000; banner HTTP(S) hoặc null; bốn mốc thời gian bắt buộc có timezone. Mọi datetime input được chuẩn hóa UTC trước lưu, output ISO 8601 UTC. Min/max đội 1–100, mặc định 1/5. Payload không nhận field lạ hoặc status từ client.
- `EventCreate` thêm organizer_email; tài khoản BTC phải tồn tại, active, verified và không phải admin. Tạo event và cấp organizer/audit trong một transaction. Admin không tự trở thành organizer. Slug trùng trả 409 RESOURCE_CONFLICT.
- Round/Track/Prize GET trả `{items,total}`, POST trả 201 đối tượng, PATCH trả đối tượng mới, DELETE trả 204. `Track={id,event_id,name,description}`; `Prize={id,event_id,name,description,rank,value}` với value Decimal không âm, tối đa 18 chữ số/2 chữ số lẻ, JSON là chuỗi. Round có required_judges mặc định 2.
- Cấu hình vận hành được sửa trước starts_at; không giảm max xuống dưới số người của đội hiện có hoặc tăng min làm đội approved không hợp lệ. Đổi hạn đăng ký cập nhật invite_expires_at các đội cùng transaction. Không đổi slug sau draft. Draft chỉ mở khi đã có ít nhất một vòng hợp lệ.
- POST roles trả 201 `{id,user:UserBrief,role}`; GET roles/registrations phân trang và tìm email/full_name, không phân biệt hoa thường. POST register trả 201, DELETE register 204; tham gia/rút trong `[registration_opens_at,registration_closes_at)`. Register trùng hoặc vai trò xung đột trả 409 ROLE_CONFLICT.
- GET events public không kèm team_count/participant_count; admin có hai số đếm này (team_count là đội chưa giải tán). Các nullable field khác vẫn giữ null. `include_archived=true` chỉ admin. GET theo slug dùng `/events/by-slug/{slug}`. GET `/me/events` trả thông tin event, role và đội của chính user, có lịch sử đã lưu trữ; admin dùng GET events riêng.
- Team active member được đọc mã mời; admin/BTC/người ngoài không có field invite_code/invite_expires_at trong JSON. Member pending chỉ thấy thông tin đội cơ bản, bản ghi thành viên của chính mình; repo_url/review_note=null và không có mã mời. Người không có quyền nhận 403, không trả hồ sơ đội.
- Team response thêm review_note, reviewed_at, disbanded_at và invite_expires_at. Đội approved có đổi name/track/repo/member chuyển pending; từ chối bắt buộc note. Mã mời tạo bằng token_urlsafe(24), quay mã hủy mã cũ; pending cũng chiếm chỗ. Chuyển leader chỉ cho active member có tài khoản hợp lệ. Leader cuối rời đội giải tán mềm, không xóa lịch sử/audit.
- GET `/events/{event_id}/teams/public` trả mảng đầy đủ đội approved theo reviewed_at/id, mỗi item đúng `{id,name,track_id,member_count,approved_at}`; approved_at lấy reviewed_at lần duyệt hiện tại. Không email, thành viên, repo hoặc mã mời. Đội cần duyệt lại/giải tán biến mất khỏi danh sách này.
- Join giới hạn 30/phút/user, email lời mời 30/giờ/leader qua Redis. Redis lỗi 503 RATE_LIMIT_UNAVAILABLE; vượt mức 429 RATE_LIMITED. Các phản hồi có dữ liệu event/team dùng Cache-Control:no-store để tránh cache dùng chung giữa quyền public/admin/member.
- Các mutation khóa user theo UUID tăng dần → event → team, kiểm tra lại trạng thái/quyền trong transaction. Mutation cùng event được tuần tự hóa để giữ giới hạn đội và không tranh chấp với cấp admin/gỡ BTC. Danh sách team/member/user được tải theo batch, tránh query theo từng thành viên.

### Giới hạn phụ thuộc phase sau

- `judging → closed` hiện trả 409 RESULTS_NOT_READY: Phase 4 phải kiểm tra snapshot kết quả đã công bố trước khi mở nhánh này. Không giả lập điểm hoặc đóng cuộc thi khi chưa có kết quả.
- Mentor/judge chưa có phân công trong Phase 2 nên không đọc Team đầy đủ chỉ bằng role. Judge dùng team-directory không có dữ liệu cá nhân. Phase 4 nối quyền đọc theo phân công và thay guard ROLE_IN_USE hiện chặn gỡ judge/mentor khi ongoing/judging bằng kiểm tra assignment thực tế.
- Chưa có submission/rubric/assignment ở Phase 2; Phase 3–4 bổ sung ràng buộc không sửa/xóa dữ liệu đã dùng và xử lý vòng qua bảng round_eligibilities đã tạo. Phase 7 bổ sung outbox/thông báo đổi lịch và in-app.

### Cấu hình GitHub và email

- Thêm `GITHUB_TOKEN` trong backend/.env.example; điền token hệ thống có quyền đọc repo public vào backend/.env rồi restart API. Thiếu token trả 503 GITHUB_NOT_CONFIGURED, provider lỗi/rate limit trả 503 GITHUB_UNAVAILABLE. Không cần cấp quyền repo private; code chủ động từ chối repo private/disabled. Chỉ nhận https://github.com/owner/repo, không fetch URL bất kỳ hoặc theo redirect.
- Local hiện chưa có GITHUB_TOKEN. Bộ test đã mô phỏng GitHub public/private/404/401/5xx và URL không an toàn; chưa gọi repo thật bằng token hệ thống.
- Lời mời dùng mã hiện tại và link FRONTEND_URL/join?code=..., không tạo membership hoặc tiết lộ email có tài khoản. Review gửi email cho leader sau commit; queue lỗi trả 503 EMAIL_QUEUE_UNAVAILABLE nhưng quyết định đã lưu. Không tự gửi lại nếu người dùng bấm review cùng trạng thái/note; Phase 7 bổ sung outbox để khôi phục enqueue. Queue nhận không chứng minh SMTP/inbox.

### Việc FE cần làm

1. Chạy `npm run gen:api`; nối danh sách/chi tiết event, resolver slug, dashboard `/me/events`. Guest không cần token; muốn thấy draft của BTC hoặc dữ liệu admin thì gửi Bearer đúng quyền.
2. Admin: tạo event với organizer_email, sửa metadata được phép, thêm/bỏ BTC và archive/unarchive. Hiển thị LAST_ORGANIZER/EVENT_ROLES_PRESENT; không gọi transition, duyệt đội hoặc nộp repo thay người dùng.
3. BTC: cấu hình vòng/track/prize, roles judge/mentor, registrations và team list. Form PATCH chỉ gửi field đổi; không gửi id/event_id/status hoặc field readonly. Hiển thị lỗi lịch/role/resource đang dùng bằng code.
4. Participant: đăng ký rồi tạo/vào đội, hiển thị pending/active; yêu cầu pending chỉ có dữ liệu giới hạn. Leader dùng Team trả về để cập nhật cache sau duyệt/chuyển leader/đổi repo; không giữ invite_code cũ sau rotate. Rời đội và rút đăng ký là hai thao tác khác nhau.
5. Trang quỹ đạo đội dùng teams/public (mảng, không Page). Member_count chỉ người active; dùng team.id làm key, không lấy hồ sơ private cho trang public.
6. Xử lý TEAM_FROZEN theo server và khóa UI ở starts_at; HEAD/đồng hồ client không thay quyết định server. RESULTS_NOT_READY ở closed đang chờ Phase 4. Khi EMAIL_QUEUE_UNAVAILABLE sau review, refetch đội vì dữ liệu có thể đã lưu; không tự retry gửi mail mù.

Trạng thái FE: [ ]
