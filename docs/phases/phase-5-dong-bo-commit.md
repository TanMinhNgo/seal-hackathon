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
| GET | `/events/{event_id}/commit-overview` | organizer | → `[{team: {id, name}, ...CommitStats, inactive}]` |
| POST | `/teams/{team_id}/sync` | organizer, chỉ event ongoing | → 202 `{task_id, status: queued}`; chạy lại đồng bộ bị lỗi/chậm |

- `Commit`: `{id, sha, author, message, branch, committed_at, first_seen_at, additions, deletions, removed, url}` (`url` trỏ tới commit trên GitHub)
- `CommitStats`: `{total, last_commit_at, last_synced_at, sync_status: ok|error|pending, sync_error}`
- `inactive` = không có commit mới (theo `first_seen_at`) sau `inactivity_alert_hours`.
- Timeline hiển thị theo `first_seen_at`; `committed_at` chỉ để tham khảo vì thí sinh có thể sửa.

### Độ đầy đủ và khôi phục đồng bộ

- Chỉ đội approved/không giải tán có repo đã chốt; theo dõi một branch cố định được ghi lúc bắt đầu thi. `CommitStats` thêm `branch`, `last_attempt_at`, `running`, `truncated`; sync_error là mã/thông báo an toàn, không URL/token/stack trace.
- `DiffFile`: `{path, previous_path, status, additions, deletions, patch, binary, truncated}`. Giới hạn 1000 file và 1 MiB patch lưu mỗi commit, đánh dấu rõ khi vượt giới hạn; binary không có patch. Render text đã escape, không HTML từ repo, không thực thi mã. Không gắn nhãn review function nếu không có dữ liệu phân tích tương ứng.
- Không dùng chỉ `since=last_synced_at` như bằng chứng đủ commit: lịch sử có thể được push muộn hoặc rewritten. Lưu head SHA và đối chiếu lịch sử branch có phân trang; chỉ đánh dấu removed khi đã xác minh không còn reachable trên lịch sử thu thập đầy đủ, không suy từ việc vắng trong một trang hay lỗi 404 tạm thời.
- Một khóa job theo team, có TTL/heartbeat; bấm sync khi đang chạy trả `409 SYNC_IN_PROGRESS`, cooldown 60 giây (`429 RATE_LIMITED`). Lỗi enqueue trả `503 SYNC_QUEUE_UNAVAILABLE`; job retry phải idempotent và không tạo lịch chồng. last_synced_at chỉ cập nhật sau lượt thành công, không dùng lần thử lỗi làm mốc bỏ qua commit.
- GET commit-overview dùng limit/offset → `{items: [{team, ...CommitStats, inactive}], total}`. Inactivity đo từ đầu ongoing nếu chưa có commit; không biến repo lỗi thành “không hoạt động” mà phải hiện lỗi riêng.
- Lượt đầu có thể nhập commit cũ làm baseline: gắn `in_event_window` dựa trên cửa sổ first_seen_at và baseline, không coi toàn bộ lịch sử repo là tiến độ trong giờ thi. first_seen_at chỉ là thời điểm quan sát có sai số theo lịch; không chứng minh tác giả hoặc giờ viết code.
- Thu hồi phân công mentor/judge chặn đọc diff ngay như đọc đội. Admin được đọc và kiểm tra lỗi, không gọi sync nghiệp vụ thay BTC.

## Backend (Codex)

- [ ] Model `commits` (unique `(team_id, sha)`), thêm `last_synced_at`, `sync_status`, `sync_error` cho `teams`.
- [ ] Task điều phối chạy mỗi phút qua Beat, chọn cuộc thi `ongoing` đã đến hạn theo `sync_interval_minutes` của từng cuộc thi.
- [ ] Fan-out mỗi đội một task con; giới hạn song song bằng rate limit của Celery.
- [ ] Task con: `GET /repos/{owner}/{repo}/commits?since=...` (phân trang), upsert theo `sha`, cập nhật `last_synced_at`.
- [ ] Commit đã lưu mà không còn trên repo → `removed = true`, không xóa.
- [ ] Lỗi từng repo: retry có backoff, ghi `sync_error`, gửi cảnh báo cho BTC khi repo private/bị xóa.
- [ ] Theo dõi header rate limit GitHub; dừng lượt khi gần hết hạn mức.
- [ ] Cuộc thi `closed` thì ngừng đồng bộ nhưng giữ nguyên commit để tra cứu.
- [ ] Test: admin đọc commit 200, user ngoài đội 403; chạy lại không tạo trùng, một repo lỗi không làm dừng đội khác, đánh dấu `removed`.
- [ ] Endpoint diff có coverage/truncation; head/baseline tracking, khóa job/cooldown, sync thủ công cho BTC; test push muộn, pagination thiếu, rate limit và enqueue lỗi không bỏ qua commit.

## Frontend (Claude)

- [ ] Tab "Tiến độ" trong trang đội: timeline commit (message, tác giả, +/−, nhãn `removed`), phân trang.
- [ ] Thẻ thống kê: tổng commit, commit cuối, lần đồng bộ cuối, trạng thái đồng bộ.
- [ ] BTC `/manage/events/[id]/progress`: bảng tổng quan các đội, sắp xếp theo commit cuối, tô màu đội `inactive` và đội lỗi đồng bộ.
- [ ] Form cấu hình cuộc thi: thêm 2 field chu kỳ đồng bộ và ngưỡng cảnh báo.
- [ ] Giám khảo/mentor xem được tab tiến độ của đội được phân công.
- [ ] Admin `/admin/teams/[id]`: tab Commit (timeline, thống kê đồng bộ). Trang `/admin/teams/[id]/commits/[sha]`: thông tin commit, link GitHub, và các đánh giá gắn commit đó (góp ý mentor từ Phase 4, AI review từ Phase 6).
- [ ] BTC có nút đồng bộ lại kèm running/cooldown; mentor/judge xem file và patch thật, hiển thị binary/truncated/baseline thay vì giả lập diff đầy đủ.

Trạng thái FE: [ ]

## Xong khi

- Đội có repo thật, commit mới xuất hiện trong ≤ 1 chu kỳ.
- Chạy job hai lần liền không sinh bản ghi trùng.
- Đổi một repo sang private → chỉ đội đó báo lỗi, BTC thấy cảnh báo.
