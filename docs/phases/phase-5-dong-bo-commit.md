# Phase 5 – Đồng bộ commit GitHub

**Mục tiêu:** tự lấy commit của từng đội theo chu kỳ để BTC, mentor, giám khảo theo dõi tiến độ thật (mục 4.5 đặc tả).

**Phụ thuộc:** Phase 2 (đội đã khai báo repo). Có thể làm song song với Phase 3–4.

## Hợp đồng API

| Method | Path | Quyền | Body → Response |
| --- | --- | --- | --- |
| PATCH | `/events/{event_id}` | organizer | thêm field `sync_interval_minutes` (mặc định 30), `inactivity_alert_hours` (mặc định 6) |
| GET | `/teams/{team_id}/commits` | thành viên, organizer, mentor/judge được phân công, admin | `?limit&offset` → `{items: Commit[], total}` |
| GET | `/teams/{team_id}/commits/{sha}` | như trên | → `Commit` |
| GET | `/teams/{team_id}/commits/{sha}/diff` | như trên | `?limit&offset` → `{items: DiffFile[], total, truncated}` (total là số file đã thu thập, không cam kết toàn bộ repo khi truncated) |
| GET | `/teams/{team_id}/commit-stats` | như trên | → `CommitStats` |
| GET | `/events/{event_id}/commit-overview` | organizer | `?limit&offset` → `{items: [{team: {id, name}, ...CommitStats, inactive}], total}` |
| POST | `/teams/{team_id}/sync` | organizer, chỉ event ongoing | → 202 `{task_id, status: queued}`; chạy lại đồng bộ bị lỗi/chậm |

- `Commit`: `{id, sha, author, message, branch, committed_at, first_seen_at, additions, deletions, removed, url}` (`url` trỏ tới commit trên GitHub)
- `CommitStats`: `{total, last_commit_at, last_synced_at, sync_status: ok|error|pending, sync_error}`
- `inactive` = không có commit mới (theo `first_seen_at`) sau `inactivity_alert_hours`.
- Timeline hiển thị theo `first_seen_at`; `committed_at` chỉ để tham khảo vì thí sinh có thể sửa.

### Độ đầy đủ và khôi phục đồng bộ

- Chỉ đội approved/không giải tán có repo đã chốt; theo dõi một branch cố định được ghi ở lượt quan sát đầu sau ongoing. `CommitStats` thêm `branch`, `last_attempt_at`, `running`, `truncated`; sync_error là mã/thông báo an toàn, không URL/token/stack trace.
- `DiffFile`: `{path, previous_path, status, additions, deletions, patch, binary, truncated}`. Giới hạn 1000 file và 1 MiB patch lưu mỗi commit, đánh dấu rõ khi vượt giới hạn; binary không có patch. Render text đã escape, không HTML từ repo, không thực thi mã. Không gắn nhãn review function nếu không có dữ liệu phân tích tương ứng.
- Không dùng chỉ `since=last_synced_at` như bằng chứng đủ commit: lịch sử có thể được push muộn hoặc rewritten. Lưu head SHA và đối chiếu lịch sử branch có phân trang; chỉ đánh dấu removed khi đã xác minh không còn reachable trên lịch sử thu thập đầy đủ, không suy từ việc vắng trong một trang hay lỗi 404 tạm thời.
- Một khóa job theo team, có TTL/heartbeat; bấm sync khi đang chạy trả `409 SYNC_IN_PROGRESS`, cooldown 60 giây (`429 RATE_LIMITED`). Lỗi enqueue trả `503 SYNC_QUEUE_UNAVAILABLE`; job retry phải idempotent và không tạo lịch chồng. last_synced_at chỉ cập nhật sau lượt thành công, không dùng lần thử lỗi làm mốc bỏ qua commit.
- GET commit-overview dùng limit/offset → `{items: [{team, ...CommitStats, inactive}], total}`. Inactivity đo từ lần chuyển sang ongoing trong audit log nếu chưa có commit; dữ liệu cũ/fixture không có audit dùng `starts_at`. Không biến repo lỗi thành “không hoạt động” mà phải hiện lỗi riêng.
- Lượt đầu có thể nhập commit cũ làm baseline: gắn `in_event_window` dựa trên cửa sổ first_seen_at và baseline, không coi toàn bộ lịch sử repo là tiến độ trong giờ thi. first_seen_at chỉ là thời điểm quan sát có sai số theo lịch; không chứng minh tác giả hoặc giờ viết code.
- Thu hồi phân công mentor/judge chặn đọc diff ngay như đọc đội. Admin được đọc và kiểm tra lỗi, không gọi sync nghiệp vụ thay BTC.
- Cấu hình: `sync_interval_minutes` 1–1440, `inactivity_alert_hours` 1–168; BTC được đổi trong ongoing. Branch mặc định được chốt ở lượt quan sát đầu sau ongoing, giữ nguyên cả khi GitHub đổi default branch. Baseline là toàn bộ lịch sử của lượt đầy đủ đầu tiên; commit baseline luôn `in_event_window=false`. Thêm `baseline`, `in_event_window` vào `Commit`.
- `CommitStats.total` đếm commit trong cửa sổ thi đang reachable, `last_commit_at` là `first_seen_at` mới nhất của nhóm này; timeline vẫn giữ mọi commit baseline/removed. Overview trả mọi đội chưa giải tán, phân trang theo thứ tự tạo đội; FE có thể lọc/sắp xếp trang hiện tại, không suy là đã sắp toàn bộ dữ liệu.
- Enqueue lỗi giữ lease tối đa 5 phút do broker có thể đã nhận task; trả 503 và ghi `SYNC_QUEUE_UNAVAILABLE`. Lease hết hạn hiện `SYNC_WORKER_TIMEOUT`; Beat có thể khôi phục mà không đợi hết chu kỳ cuộc thi. Lease heartbeat 5 phút, mỗi task giới hạn 240 giây mềm/270 giây cứng; chạy worker Linux (Celery time limit không được bảo đảm trên Windows).
- Giới hạn 100 trang lịch sử/lượt; quá giới hạn giữ dữ liệu đã thấy, báo `truncated=true`, không đánh dấu removed và không cập nhật mốc thành công. Thiếu patch không chứng minh binary: `binary` nullable, `null` là không xác định, đồng thời `truncated=true`. Repo private/deleted được cảnh báo qua trạng thái lỗi của overview; email cảnh báo được gửi một lần mỗi đợt lỗi (SMTP acceptance không chứng minh inbox).

## Backend (Codex)

- [x] Model `commits` (unique `(team_id, sha)`), bảng `commit_sync_states` theo đội chứa `last_synced_at`, `sync_status`, `sync_error` và lease/head/baseline (tách trạng thái worker khỏi thông tin đội).
- [x] Task điều phối chạy mỗi phút qua Beat, chọn cuộc thi `ongoing` đã đến hạn theo `sync_interval_minutes` của từng cuộc thi.
- [x] Fan-out mỗi đội một task con; giới hạn song song bằng rate limit của Celery.
- [x] Task con: chốt head rồi duyệt lịch sử bằng `sha=head` có phân trang, upsert theo `sha`, cập nhật `last_synced_at` chỉ khi đủ lịch sử. Không lọc `since` vì có push muộn.
- [x] Commit đã lưu mà không còn trên repo → `removed = true`, không xóa.
- [x] Lỗi từng repo: retry có backoff, ghi `sync_error`, gửi cảnh báo cho BTC khi repo private/bị xóa.
- [x] Theo dõi header rate limit GitHub; dừng lượt khi gần hết hạn mức.
- [x] Cuộc thi `closed` thì ngừng đồng bộ nhưng giữ nguyên commit để tra cứu.
- [x] Test: admin đọc commit 200, user ngoài đội 403; chạy lại không tạo trùng, một repo lỗi không làm dừng đội khác, đánh dấu `removed`.
- [x] Endpoint diff có coverage/truncation; head/baseline tracking, khóa job/cooldown, sync thủ công cho BTC; test push muộn, pagination thiếu, rate limit và enqueue lỗi không bỏ qua commit.

## Frontend (Claude)

- [x] Tab "Tiến độ" trong trang đội: timeline commit (message, tác giả, +/−, nhãn `removed`), phân trang.
- [x] Thẻ thống kê: tổng commit, commit cuối, lần đồng bộ cuối, trạng thái đồng bộ.
- [x] BTC tab "Tiến độ" trong `/manage/events/[id]` (khu vận hành dùng tab, không tách route): bảng tổng quan các đội, sắp xếp theo commit cuối, tô màu đội `inactive` và đội lỗi đồng bộ.
- [x] Form cấu hình cuộc thi: thêm 2 field chu kỳ đồng bộ và ngưỡng cảnh báo.
- [x] Giám khảo/mentor xem được tab tiến độ của đội được phân công.
- [x] Admin `/admin/teams/[id]`: tab Commit (timeline, thống kê đồng bộ). Trang `/admin/teams/[id]/commits/[sha]`: thông tin commit, link GitHub, và các đánh giá gắn commit đó (góp ý mentor từ Phase 4, AI review từ Phase 6).
- [x] BTC có nút đồng bộ lại kèm running/cooldown; mentor/judge xem file và patch thật, hiển thị binary/truncated/baseline thay vì giả lập diff đầy đủ.

Trạng thái FE: [ ] — code xong 2026-11-02 (typecheck/lint/build xanh), chưa nghiệm thu trên trình duyệt với dữ liệu commit thật.

## Bàn giao backend Phase 5

Triển khai 2026-11-02 trong `backend/`, migration `0007_commits`; không thêm dependency. Sáu operation mới và hai field cấu hình trên API event hiện có. Dữ liệu đồng bộ nằm trong `commits`/`commit_sync_states`; không đưa lease worker vào schema đội công khai.

### Quyền, lỗi và vận hành

- API đọc kiểm tra thành viên **active**, BTC hoặc mentor/judge có phân công đang hiệu lực; admin được đọc. SHA phải đủ 40 ký tự hex viết thường. Commit thuộc đội khác hoặc không tồn tại trả `404 COMMIT_NOT_FOUND`; góp ý/câu hỏi Phase 4 dùng SHA không thuộc đội trả `422 COMMIT_NOT_FOUND`.
- `POST /teams/{id}/sync`: chỉ BTC, event ongoing, đội approved có repo. Admin/ngoài phạm vi trả 403; event sai trạng thái `409 EVENT_NOT_ONGOING`; đội chưa đủ điều kiện `409 TEAM_NOT_ELIGIBLE`; khóa/cooldown/queue như hợp đồng phía trên. Thao tác sync thủ công ghi audit log.
- Beat `seal.sync_commits` mỗi 60 giây; mỗi đội một `seal.sync_team`, rate limit 30 task/phút/**mỗi worker**, retry tối đa 3 lần, backoff 60/120/240 giây. Chỉ chạy **một Beat**. Hạn mức GitHub dùng chung qua Redis: còn ≤10 request hoặc bị 429/secondary limit thì tạm dừng tới reset/retry-after; không gọi GitHub trong lúc pause.
- Queue dùng worker mặc định hiện có, không cần thêm queue mới. `GITHUB_TOKEN`/`REDIS_URL`/SMTP dùng cấu hình sẵn trong `.env.example`; không thêm secret hay cấu hình mới. Local Windows tiếp tục dùng `--pool=solo`; triển khai worker Linux để có time limit của Celery.
- Worker kiểm tra lại event trước mỗi lần lưu; chuyển sang judging/closed sẽ dừng. Lease token được đổi khi bắt đầu task để chặn bản giao trùng, heartbeat và khóa dòng bảo vệ ghi dữ liệu khi lease bị thay thế. Job lỗi không cập nhật `last_synced_at`; retry đọc lại toàn bộ lịch sử, giữ nguyên `first_seen_at` đã lưu.
- `sync_error` chỉ có mã an toàn: `GITHUB_NOT_CONFIGURED`, `REPO_NOT_ACCESSIBLE`, `GITHUB_UNAVAILABLE`, `GITHUB_INCOMPLETE_HISTORY`, `GITHUB_RATE_LIMITED`, `SYNC_COORDINATION_UNAVAILABLE`, `SYNC_QUEUE_UNAVAILABLE`, `SYNC_WORKER_TIMEOUT`. FE hiển thị thông báo tiếng Việt tương ứng, không suy lỗi repo thành inactive.

### FE cần nối

1. Sinh lại type bằng `npm run gen:api` sau khi API chạy bản mới; không sửa tay type sinh tự động.
2. Nối timeline + thống kê + phân trang commit/diff. Render message/path/patch dưới dạng text; nhãn baseline, removed, `in_event_window`, `binary=null` và truncated phải hiện đúng. Không hiển thị dữ liệu này như bằng chứng giờ viết code.
3. Nối bảng BTC với response `{items,total}`; giữ riêng trạng thái lỗi và inactive. Nút sync xử lý 202, 409, 429, 503; sau 503 đọc lại stats vì job có thể đã vào queue. Poll stats khi `running=true`.
4. Form cấu hình dùng giới hạn đã ghi; mentor note/câu hỏi được gửi `commit_sha` có thật của đúng đội. Thu hồi phân công phải xử lý 403 và xóa dữ liệu đã cache của đội khỏi màn hình.
5. Admin chỉ xem commit/diff/thống kê; không có nút sync. Panel AI nối ở Phase 6.

### Bằng chứng và giới hạn nghiệm thu

- Migration `0007_commits (head)` đã áp dụng PostgreSQL local; `alembic check` không có drift. Migration upgrade/downgrade/upgrade trên SQLite đã qua test.
- Smoke GitHub thật với `octocat/Hello-World`: branch `master`, 3 commit, lịch sử đầy đủ, diff head có 1 file, không truncated. Chỉ đọc provider, không push hay đổi repo.
- `ruff format --check .`: 99 file đúng format; `ruff check .`: xanh. `git diff --check`: không lỗi whitespace.
- 20 test Phase 5 qua SQLite và PostgreSQL: phân quyền/admin/pending, mentor bị thu hồi, SHA gắn note/Q&A, push muộn, baseline/force push, lịch sử thiếu trang/thiếu parent, giới hạn diff/UTF-8, rate limit, fan-out, enqueue lỗi, retry, lease chạy trùng/hết hạn/chạy đồng thời và event dừng giữa lượt.
- Bao phủ toàn bộ 194 test trên PostgreSQL qua các lượt: lượt toàn suite có 173 test qua, dừng ở test system cũ mặc định dung lượng DB phải null; đã sửa kỳ vọng theo dialect (PostgreSQL phải trả số byte dương), chạy lại `tests/test_commits.py tests/test_system.py tests/test_worker.py` có 41 test qua, gồm 20 test Phase 5 chạy lại ở bản cuối và toàn bộ 21 test còn lại. Không gọi đây là một lệnh full suite xanh duy nhất. Lượt full SQLite trước đó: 169 qua/5 bỏ qua do cần PostgreSQL; test Phase 5 mới chạy riêng 20/20.
- Chưa nghiệm thu FE/browser, chu kỳ Beat → broker → worker → GitHub với commit vừa push, chuyển repo thật sang private, SMTP/inbox, repo rất lớn và tải nhiều đội. Không đổi repo thật sang private trong lượt triển khai này.
- Lịch có độ trễ kiểm tra tối đa khoảng một phút cộng thời gian queue/API; repo nhiều lịch sử có thể cần nhiều lượt để lấy đủ detail. Quá 10.000 commit/lượt hoặc 1.000 file/1 MiB patch thì coverage bị giới hạn như hợp đồng. Baseline của lượt đầy đủ đầu tiên có thể bao gồm commit push trong khoảng từ lúc ongoing tới lần quan sát đó; UI cần ghi rõ giới hạn này.

## Xong khi

- Đội có repo thật, commit mới xuất hiện trong ≤ 1 chu kỳ.
- Chạy job hai lần liền không sinh bản ghi trùng.
- Đổi một repo sang private → chỉ đội đó báo lỗi, BTC thấy cảnh báo.
