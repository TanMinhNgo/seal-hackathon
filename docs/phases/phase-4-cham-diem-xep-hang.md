# Phase 4 – Chấm điểm, xếp hạng, công bố ⭐ MVP

**Mục tiêu:** chấm theo rubric, khóa điểm, xếp hạng, công bố. Hết phase này, một cuộc thi chạy trọn vòng đời trên SEAL.

**Phụ thuộc:** Phase 3.

## Hợp đồng API

### Rubric & phân công

| Method | Path | Quyền | Body → Response |
| --- | --- | --- | --- |
| GET | `/events/{event_id}/rounds/{round_id}/rubric` | public khi event đã open; draft/lưu trữ theo quyền Event | → `Rubric` (không có điểm/nhận xét cá nhân) |
| PUT | `/events/{event_id}/rounds/{round_id}/rubric` | organizer trước round.starts_at và trước khi có điểm | `{criteria: CriterionInput[]}` → `Rubric` |
| POST | `/events/{event_id}/conflicts` | judge | `{team_id, reason}` → 201 |
| GET | `/events/{event_id}/conflicts` | organizer tất cả; judge chỉ của mình | `?limit&offset` → `{items: Conflict[], total}` |
| GET | `/events/{event_id}/rounds/{round_id}/assignments` | organizer | `?limit&offset` → `{items: Assignment[], total}` |
| POST | `/events/{event_id}/rounds/{round_id}/assignments` | organizer | `{judge_id, team_ids}` → `AssignmentBatch` (báo rõ cặp bị bỏ) |
| POST | `/events/{event_id}/rounds/{round_id}/assignments/auto` | organizer | `{judges_per_team}` → `AssignmentBatch` |
| DELETE | `/assignments/{assignment_id}` | organizer (chưa chấm) | → 204 |
| POST | `/events/{event_id}/mentor-assignments` | organizer | `{mentor_id, team_ids}` → 201 |
| GET | `/events/{event_id}/mentor-assignments` | organizer, admin | `?limit&offset` → `{items: MentorAssignment[], total}` |
| DELETE | `/mentor-assignments/{assignment_id}` | organizer | → 204, thu hồi quyền hiện tại, giữ lịch sử góp ý |
| POST | `/assignments/{assignment_id}/cancel` | organizer, vòng chưa khóa/chưa công bố | `{reason}` → `Assignment` (hủy cả bài đã xác nhận, giữ lịch sử) |
| GET | `/events/{event_id}/rounds/{round_id}/eligible-teams` | organizer, admin | `?limit&offset` → `{items: RoundTeam[], total}` |
| PUT | `/events/{event_id}/rounds/{round_id}/eligible-teams` | organizer trước khi vòng bắt đầu | `{source_round_id, team_ids}` → `{items: RoundTeam[], total}` (thay toàn bộ danh sách) |

- `Rubric`: `{round_id, criteria: [{id, name, description, weight, max_score, order}]}`; tổng `weight` = 100.
- `Assignment`: `{id, round_id, judge: UserBrief, team: {id, name, track_id}, submission_id, status: pending|draft|submitted|cancelled, revision, submitted_at}`
- `Conflict`: `{id, judge: UserBrief, team_id, reason, created_at}`; không trả cho participant/mentor/guest, giữ hồ sơ sau khi thay phân công.
- `AssignmentBatch`: `{items: Assignment[], skipped: [{team_id, code}], unfilled: [{team_id, missing_judges}]}`; input tối đa 100 team IDs; không đủ judge vẫn phải báo thiếu, không tự coi thành công đầy đủ.
- `MentorAssignment`: `{id, event_id, mentor: UserBrief, team: {id, name}, created_at}`; POST trả `{items: MentorAssignment[]}` với tối đa 100 team IDs, không tạo trùng cặp mentor/team.
- `RoundTeam`: `{team_id, name, source_round_id}`. Vòng đầu mặc định mọi đội approved; vòng tiếp theo phải có danh sách BTC xác nhận từ đội có kết quả đã công bố ở vòng nguồn, cùng event và vòng nguồn có order thấp hơn. Không có wildcard tự vào lại vòng sau. Đổi danh sách trước starts_at ghi audit/thông báo; không tự chọn theo top N khi đồng hạng.

### Chấm điểm (giám khảo)

| Method | Path | Quyền | Body → Response |
| --- | --- | --- | --- |
| GET | `/me/assignments` | judge | `?event_id&round_id&limit&offset` → `{items: Assignment[], total}` |
| GET | `/assignments/{assignment_id}` | judge sở hữu phân công, organizer; admin sau khóa | → `{assignment, submission, rubric, scores}` |
| PUT | `/assignments/{assignment_id}/scores` | judge được phân công | `{expected_revision, scores: [{criterion_id, score, comment?}], general_comment?}` → `{assignment, scores}`; tăng revision |
| POST | `/assignments/{assignment_id}/submit` | judge được phân công | `{expected_revision}` → `Assignment`, xác nhận và tăng revision, không sửa được nữa |
| POST | `/assignments/{assignment_id}/reopen` | organizer | `{reason}` → `draft` (ghi audit log) |

### Khóa điểm, xếp hạng, công bố

| Method | Path | Quyền | Body → Response |
| --- | --- | --- | --- |
| GET | `/events/{event_id}/rounds/{round_id}/judging-progress` | organizer | `?limit&offset` → `{items: [{team, required, assigned, submitted, missing, has_conflict, status}], total, locked_at, published_at}` |
| POST | `/events/{event_id}/rounds/{round_id}/lock` | organizer | → 204 (mọi đội có bài hợp lệ đủ required_judges, các phân công còn hiệu lực đều submitted, không còn conflict) |
| POST | `/events/{event_id}/rounds/{round_id}/unlock` | organizer | `{reason}` → 204 |
| GET | `/events/{event_id}/rounds/{round_id}/leaderboard` | organizer; admin sau khóa; public sau công bố | `?track_id&limit&offset` → `{items: LeaderboardRow[], total, publication_revision}` |
| POST | `/events/{event_id}/rounds/{round_id}/publish` | organizer (đã khóa) | → 204, gửi email kết quả |
| POST | `/events/{event_id}/rounds/{round_id}/unpublish` | organizer, event chưa closed | `{reason}` → 204 (thu hồi công bố trước khi sửa) |
| GET | `/teams/{team_id}/rounds/{round_id}/result` | thành viên active (sau công bố), organizer/admin (sau khóa) | → `{rank, total, criteria: [{name, avg}], comments: string[], publication_revision}` (ẩn tên giám khảo) |
| GET/POST | `/teams/{team_id}/mentor-notes` | mentor được phân công (POST); mentor được phân công, thành viên active, organizer, admin (GET) | POST `{content, commit_sha?, kind?, progress_status?}` → 201 `MentorNote`; GET `?commit_sha&limit&offset` → `{items: MentorNote[], total}` |
| GET | `/me/mentoring` | mentor | `?event_id&limit&offset` → `{items: Team[], total}` |

- `MentorNote`: `{id, team_id, mentor: UserBrief, content, commit_sha, kind, progress_status, created_at}`; kind=`feedback|progress` mặc định feedback, progress_status=`on_track|at_risk|blocked` bắt buộc khi kind=progress, null khi feedback. `commit_sha` null nếu góp ý chung; chỉ nhận commit đã lưu đúng đội khi Phase 5 sẵn sàng. Góp ý không sửa/xóa sau gửi; tiến độ mới là note mới, trạng thái gần nhất dùng cho dashboard.
- `LeaderboardRow`: `{rank, team: {id, name, track_id}, total, criteria: [{criterion_id, avg}], tied}`
- `judging-progress.items[]` bổ sung `status: not_submitted|pending|complete` để BTC phân biệt đội không nộp với đội chưa chấm. Save/detail trả thêm `general_comment: string|null` để tải lại nháp đầy đủ.
- `judging-progress.locked_at` và `published_at` là timestamp UTC nullable ở cấp response, độc lập phân trang. Vòng chưa khóa/công bố trả null, kể cả chưa có bản ghi chấm. Unpublish chỉ xóa published_at; unlock xóa locked_at. FE dùng hai trường này để hiện nút phù hợp và refetch sau thao tác; quyền/điều kiện nghiệp vụ vẫn do server kiểm tra.
- Thu hồi công bố vòng nguồn trả `409 RESOURCE_IN_USE` nếu vòng sau đã bắt đầu và đang tham chiếu nguồn này. Khi vòng sau chưa bắt đầu, danh sách đã chọn được giữ để BTC đối chiếu nhưng không có hiệu lực nộp/chấm cho đến khi nguồn được công bố lại.
- Lỗi bổ sung: `RUBRIC_ORDER_INVALID`, `DEADLINE_NOT_PASSED`, `RUBRIC_REQUIRED`, `JUDGE_COUNT_MISMATCH`, `ASSIGNMENT_CANCELLED`, `SCORES_NOT_LOCKED`, `RESULT_NOT_FOUND`, `COMMIT_NOT_FOUND`, `EVENT_NOT_OPEN`; các lỗi đầu vào rubric/count/commit trả 422, điều kiện nghiệp vụ trả 409, result không tồn tại trả 404.
- publication_revision là số nguyên bắt đầu 0, tăng mỗi lần publish phiên bản mới. Batch scores/save/submit/reopen phản hồi chỉ điểm của phân công đó; không nhúng điểm của người khác.
- Công thức: điểm đội = trung bình giữa các giám khảo của `Σ(score/max_score × weight)`, thang 100, làm tròn 2 chữ số.
- Đồng điểm: so lần lượt avg tiêu chí theo weight giảm dần/order tăng dần, rồi thời điểm nộp bản cuối sớm hơn; vẫn bằng nhau thì cùng hạng. Quy tắc làm tròn và kiểu hạng ghi tại "Điều kiện chấm và sửa kết quả".
- Mã lỗi: `CONFLICT_OF_INTEREST`, `SCORES_LOCKED`, `ASSIGNMENT_SUBMITTED`, `SCORING_INCOMPLETE`, `SCORE_OUT_OF_RANGE`, `RUBRIC_WEIGHT_INVALID`, `NOT_PUBLISHED`.

### Điều kiện chấm và sửa kết quả

- Chỉ tạo phân công sau hạn nộp, cho đội eligible có bản cuối hợp lệ; lưu submission_id cố định. Đội không có bài hợp lệ mang trạng thái `not_submitted`, không có điểm/hạng, vẫn hiện ở bảng tiến độ BTC; không chấm 0 rồi xếp hạng như đã nộp.
- required_judges lấy từ Round Phase 2; auto input phải bằng cấu hình này, phân bổ bù chỗ còn thiếu, không ghi đè phân công thủ công. Không vượt required_judges, không có đủ judge thì trả unfilled. Lock không thành công khi không có bài hợp lệ hoặc chỉ có tập phân công rỗng (`409 SCORING_INCOMPLETE`).
- Judge active/verified, có role đúng event; loại cặp có conflict hoặc từng là mentor của đội. Khai báo conflict sau phân công lập tức chặn sửa/xác nhận bài đó và khóa/công bố vòng; BTC phải cancel, thay judge. Nếu đã công bố thì BTC thu hồi công bố trước, điểm cũ không tự sửa. Cancel giữ mọi điểm/audit, loại phân công khỏi tổng hợp; DELETE chỉ dùng phân công pending chưa có điểm.
- Draft cho phép thiếu tiêu chí; submit phải đủ đúng một điểm/tiêu chí, không lặp hoặc có criterion ngoài rubric. max_score > 0, weight >= 0 và tổng weight=100; điểm là số hữu hạn trong giới hạn. expected_revision sai trả `409 SCORE_VERSION_CONFLICT` để hai tab không ghi đè nháp nhau. Mọi đổi điểm, submit/reopen/cancel/lock/unlock/publish/unpublish ghi audit cùng transaction.
- Reopen chỉ khi chưa khóa/chưa công bố. Unlock bị chặn khi còn công bố. Unpublish giữ snapshot lịch sử, xóa cờ public và cache; publish tiếp tăng publication_revision, chỉ gửi email/sự kiện một lần cho mỗi revision. Đóng event yêu cầu mọi vòng có kết quả cuối đã công bố; sau closed chỉ tra cứu, không sửa điểm.
- Dùng Decimal, làm tròn HALF_UP 2 chữ số cho tổng điểm chính thức; so tổng đã làm tròn, rồi avg từng tiêu chí theo weight giảm dần, order tăng dần, rồi submitted_at sớm hơn. Vẫn bằng dùng cùng hạng kiểu 1,1,3; track lọc và tính hạng riêng trong track. Public response chỉ team id/name/track và điểm; không tên/email judge hay raw score từng judge. result nội bộ trả publication_revision và nhận xét ẩn danh sau công bố; BTC đọc kết quả để kiểm tra sau khóa.
- Rubric và lịch sử snapshot đã sử dụng không sửa/xóa. Admin chỉ đọc điểm sau khóa; judge chỉ đọc scores của assignment của mình, kể cả khi vòng đã khóa. Không mở endpoint đọc điểm đồng nghiệp chỉ vì có cùng role judge.

### Hỏi/đáp mentor theo đội

| Method | Path | Quyền | Body → Response |
| --- | --- | --- | --- |
| GET | `/teams/{team_id}/questions` | active member, mentor được phân công, organizer, admin | `?status&limit&offset` → `{items: MentorQuestion[], total}` |
| POST | `/teams/{team_id}/questions` | active member, event open/ongoing | `{title, content, commit_sha?}` → 201 `MentorQuestion` |
| POST | `/questions/{question_id}/answers` | mentor đang được phân công, event open/ongoing | `{content}` → 201 `MentorAnswer` |
| POST | `/questions/{question_id}/resolve` | người hỏi hoặc leader active của đội | → 204, idempotent, event open/ongoing |

- `MentorQuestion`: `{id, team_id, author: UserBrief, title, content, commit_sha, status: open|answered|resolved, created_at, resolved_at}`; title 1–150, content 1–5000 ký tự đã trim; chỉ đội và người được phép đọc, không chat công khai. Question list không nhúng mảng answers vô hạn.
- `MentorAnswer`: `{id, question_id, mentor: UserBrief, content, created_at}`; thêm GET `/questions/{question_id}/answers?limit&offset` → `{items: MentorAnswer[],total}` cùng quyền GET question. Trả lời đầu chuyển open → answered, câu hỏi resolved không nhận trả lời; nội dung gửi rồi không sửa/xóa. Góp ý bổ sung dùng câu trả lời mới.
- Member pending/người ngoài/judge không được đọc Q&A, mentor bị gỡ phân công mất quyền đọc/ghi mới, hồ sơ câu trả lời vẫn giữ. Giới hạn POST tạo câu hỏi/trả lời 30/phút/user; UI báo khi chưa có mentor, cho lưu câu hỏi chờ phân công. Thay mentor không xóa câu hỏi cũ.
- Mã lỗi bổ sung: `SCORE_VERSION_CONFLICT`, `ROUND_ALREADY_STARTED`, `ROUND_NOT_ELIGIBLE`, `RESULTS_PUBLISHED`, `QUESTION_RESOLVED`; sai trạng thái 409, ngoài quyền 403. Giới hạn role xem team/round/assignment luôn kiểm tra cả event sở hữu.

## Backend (Codex)

- [x] Module `judging`: model `rubric_criteria`, `conflicts`, `assignments`, `scores`, `mentor_assignments`, `mentor_notes`.
- [x] Validate tổng trọng số = 100; điểm trong `[0, max_score]`.
- [x] Giám khảo không đọc được điểm của giám khảo khác trước khi khóa (kiểm tra trong service).
- [x] Phân công tự động: chia đều, bỏ cặp xung đột, không phân công trùng.
- [x] Mọi thay đổi điểm sau xác nhận (reopen, unlock) ghi audit log.
- [x] Module `ranking`: tính bảng xếp hạng theo công thức trên, cache Redis, xóa cache khi khóa/mở/sửa điểm.
- [x] Publish: đặt cờ đã công bố, gửi email kết quả qua worker.
- [x] `mentor_notes` có `commit_sha` (nullable, index `(team_id, commit_sha)`).
- [x] Admin đọc result/leaderboard chỉ sau khi vòng đã khóa; admin gọi chấm, phân công, khóa, công bố, ghi góp ý → 403.
- [x] Test: admin đọc result trước khóa → 403, sau khóa → 200; công thức điểm, đồng điểm, giám khảo xem điểm người khác (403), chấm bài không được phân công (403), xung đột lợi ích.
- [x] Dùng events service quản lý round eligibility đã tạo Phase 2; migration assignment submission_id/revision/cancelled, publication snapshots/revision; khóa khi đủ judge cho từng đội, xử lý conflict muộn và sửa công bố theo transaction/audit.
- [x] Mentor assignment GET/DELETE; note tiến độ; models mentor_questions/mentor_answers, API hỏi/đáp và rate limit; Phase 4 chạy được không có commit/AI.
- [x] Nối quyền đọc team cho mentor/judge qua phân công thực tế; thay guard thu hồi role đang ongoing/judging của Phase 2 bằng kiểm tra assignment còn hiệu lực. Nối điều kiện judging → closed với snapshot kết quả đã công bố, thay RESULTS_NOT_READY mặc định của Phase 2.
- [x] Test: zero assignments không khóa được; đổi ID round/team chéo event, chấm phiên bản cũ đúng snapshot, xung đột mentor-judge, nháp stale, unpublish/unlock/reopen/republish, đội không qua vòng không nộp được; mentor bị gỡ không đọc bài/Q&A.

## Frontend (Claude)

- [x] BTC – editor rubric: thêm/xóa/sắp xếp tiêu chí, hiển thị tổng trọng số realtime, chặn lưu khi ≠ 100.
- [x] BTC – màn phân công: ma trận giám khảo × đội, nút tự động phân công, đánh dấu cặp xung đột.
- [x] BTC – tiến độ chấm, nút khóa/mở khóa (nhập lý do), xem bảng xếp hạng, nút công bố có xác nhận.
- [x] BTC – phân công mentor.
- [x] Giám khảo `/judge`: danh sách bài được giao, trạng thái từng bài; khai báo xung đột lợi ích.
- [x] Giám khảo – màn chấm: bên trái thông tin bài nộp (link, file), bên phải form rubric; tự lưu nháp; nút xác nhận có cảnh báo không sửa được.
- [x] Mentor `/mentor`: danh sách đội, ghi góp ý (chọn gắn vào commit nào).
- [x] Admin `/admin/teams/[id]`: tab Góp ý mentor (lọc theo commit) và tab Kết quả chấm (chỉ hiện khi vòng đã khóa).
- [x] Trang công khai `/events/[slug]/results` (SSR): bảng xếp hạng theo vòng/track, đánh dấu đồng hạng.
- [x] Thí sinh: xem điểm từng tiêu chí và nhận xét của đội sau công bố.
- [x] BTC quản lý đội qua vòng, thu hồi/thay mentor và judge; AssignmentBatch hiển thị skipped/unfilled thay vì báo hoàn tất chung.
- [x] Mentor và đội: câu hỏi, câu trả lời, đánh dấu giải quyết; note ghi tiến độ; panel commit/AI hiển thị chưa sẵn sàng khi Phase 5–6 chưa có.
- [x] Judge tự lưu có expected_revision; khi conflict không tự retry ghi đè. BTC có luồng thu hồi công bố → sửa → công bố revision mới; public ẩn kết quả khi bị thu hồi.

Trạng thái FE: [ ] — code xong 2026-10-31 (typecheck/lint/build xanh; trang công khai SSR thử với vòng chưa công bố và slug sai). BE đã thêm `locked_at`, `published_at` vào `judging-progress`; FE cần sinh lại type và dùng metadata này thay cho việc luôn hiện đủ bốn nút. Kết quả nghiệm thu trình duyệt và phạm vi còn lại xem phần bổ sung bên dưới; chưa đánh dấu nghiệm thu toàn bộ FE.

## Xong khi

- Chạy trọn một cuộc thi thử từ `draft` đến `closed` chỉ trên SEAL.
- Test BE về điểm, đồng điểm, quyền xem điểm pass.
- Bảng xếp hạng công khai chỉ hiện sau khi công bố.

## Bàn giao backend Phase 4

Ngày 2026-10-31: đã triển khai 34 operation Phase 4, tổng OpenAPI hiện có 97 operation. Migration `0006_judging` thêm 11 bảng, đã upgrade PostgreSQL local và `alembic check` không drift. Không thêm dependency hoặc biến môi trường. Không sửa frontend, không commit/push.

### Hành vi và dữ liệu FE cần nối

- Khởi động API rồi chạy `npm run gen:api` ở frontend. Dùng schema OpenAPI cho rubric, assignment, score, leaderboard, mentor và hỏi/đáp. Decimal được trả bằng chuỗi JSON; UI chuyển sang số khi cần hiển thị, không tự tính điểm chính thức.
- Tạo rubric trước `round.starts_at`, tổng weight đúng 100, order không lặp. Sau deadline mới phân công; auto dùng đúng `round.required_judges`. Response batch phải hiển thị cả `skipped` và `unfilled`, kể cả HTTP 200.
- Assignment ghim bản cuối hợp lệ qua `submission_id`; không tự đổi theo lần tải bài mới nhất. Form chấm lấy `general_comment` từ detail, lưu toàn bộ danh sách nháp kèm `expected_revision`; save/submit trả revision mới. Gặp `SCORE_VERSION_CONFLICT` phải tải lại và cho người dùng đối chiếu, không retry ghi đè.
- `judging-progress.status` phân biệt `not_submitted`, `pending`, `complete`; `missing = max(0, required - submitted)`. `has_conflict` cũng bật khi judge không còn đủ điều kiện tài khoản/role. Đội không có bài hợp lệ không có hạng. Không được khóa một tập bài/phân công rỗng.
- BTC kiểm tra điểm trước công bố; Admin chỉ đọc điểm sau khóa, không gọi API vận hành. Judge chỉ đọc phân công của mình, kể cả sau khóa; participant chỉ lấy result của đội active sau công bố. Public leaderboard không có email, nhận xét hay điểm riêng từng judge.
- Sửa kết quả: unpublish → unlock → reopen → save/submit → lock → publish. Mọi bước ghi audit trong cùng transaction; mỗi publish mới tăng revision và giữ snapshot cũ. Nút publish lại cùng revision không tạo thêm email.
- `eligible-teams` vòng đầu mặc định đội approved. Vòng sau BTC chọn từ đội có kết quả công bố ở vòng nguồn trước đó. Khi nguồn bị thu hồi, GET vẫn giữ lựa chọn để đối chiếu nhưng quyền nộp/chấm tạm dừng; chặn thu hồi nếu vòng phụ thuộc đã bắt đầu. Đổi danh sách trước start có audit và email báo leader bị ảnh hưởng.
- Mentor dùng `/me/mentoring` và phân công hiện tại. Thu hồi phân công làm mất quyền đọc bài, đội riêng, note/Q&A ngay; giữ note, câu trả lời và lịch sử từng hỗ trợ để tránh xung đột chấm. Note không sửa/xóa; lấy note `kind=progress` mới nhất theo `created_at` để hiển thị tiến độ. Danh sách note/question/answer mặc định mới nhất trước, có limit/offset.
- Hỏi/đáp chỉ ghi khi event open/ongoing; member pending và judge không đọc được. Gửi câu hỏi/trả lời dùng chung giới hạn 30 request/phút/user; xử lý 429, 503, `QUESTION_RESOLVED`. Notes tiến độ yêu cầu `progress_status`; feedback phải null. Phase 5 đã nối commit: gửi `commit_sha` đã lưu của đúng đội hoặc null; SHA không thuộc đội trả 422 `COMMIT_NOT_FOUND`. API commit/diff xem [Phase 5](phase-5-dong-bo-commit.md); panel AI đợi Phase 6.
- Tất cả response Phase 4 có `Cache-Control: no-store`. Cache Redis nội bộ dùng revision tăng khi thay đổi phân công/điểm/khóa/công bố; key cũ không còn được đọc và hết hạn sau 300 giây. Redis lỗi thì tính từ DB; quyền và cờ công bố luôn kiểm tra trước cache.

### Worker và kiểm chứng

- Chạy worker và **một** Celery Beat theo hướng dẫn runtime hiện tại. Task `seal.result_emails` chạy mỗi 60 giây, tối đa 100 email/lượt. Biên nhận `result_emails` được tạo cùng transaction publish, unique theo snapshot/user; worker claim trước khi gửi và chỉ lấy revision còn công bố. Trạng thái `sending`/`failed` cần đối chiếu SMTP trước khi gửi thủ công, không tự retry thư có kết quả mơ hồ.
- Ruff lint/format xanh; toàn bộ backend có **168 test qua, 5 bỏ qua** ở SQLite. Migration upgrade/downgrade/check được kiểm tra trong test migration. Phase 4: 12 test qua PostgreSQL (gồm row lock/stale draft và worker biên nhận), 11 qua SQLite/1 bỏ qua vì cần row lock; các guard `/me/*` đã kiểm tra lại sau lượt rà soát cuối. Redis local đã kiểm tra write/read và cô lập key theo revision.
- Test bao phủ công thức/tie/track, bản cuối được ghim, phân quyền Admin/Judge/member, điểm thiếu/ngoài giới hạn/trùng tiêu chí, phân công thiếu hoặc lặp, conflict muộn/cancel/thay judge, unpublish/unlock/reopen/republish, đóng event, vòng nguồn bị thu hồi, mentor bị gỡ, Q&A/pending/rate limit và email không gửi trùng.
- Chưa nghiệm thu frontend/trình duyệt, demo thật đủ hai vòng và SMTP/inbox. Test worker dùng mailer giả lập, không phải bằng chứng provider nhận hoặc người dùng nhận thư. Worker/Beat đang chạy phiên cũ cần restart để nạp task mới. Backend API không được tự bật trong lượt này; PostgreSQL/Redis local đang chạy để kiểm thử.

Trạng thái FE: [ ]

## Bổ sung trạng thái vòng trong judging-progress (2026-10-31)

- Response dùng schema `JudgingProgress`, giữ nguyên `items`/`total`, thêm `locked_at: string|null`, `published_at: string|null`. Timestamp theo UTC, ví dụ `2026-10-31T15:50:00Z`. Không đổi DB hoặc quyền organizer. GET không tự tạo bản ghi `round_judging`; vòng mới trả cả hai trường null. Metadata vẫn có khi items rỗng do phân trang.
- FE chạy lại `npm run gen:api`. Trong `ProgressPanel`, query giữ toàn bộ `.data`; render bảng từ `.data.items` và đọc timestamp ở cấp `.data`, không tìm trong từng đội. Sau lock/unlock/publish/unpublish tiếp tục invalidate query `progress` để tải trạng thái mới từ server.

| Trạng thái response | Nút BTC hiển thị |
| --- | --- |
| `locked_at=null`, `published_at=null` | Khóa điểm |
| `locked_at!=null`, `published_at=null` | Mở khóa, Công bố |
| `published_at!=null` | Thu hồi công bố |
| Event closed hoặc archived | Chỉ đọc, không hiện thao tác thay đổi |

- Không suy đoán trạng thái khi query chưa tải xong hoặc lỗi; disable thao tác. Các điều kiện đủ điểm, xung đột và quyền vẫn do server kiểm tra sau khi bấm nút.
- Kiểm tra thay đổi: toàn bộ `tests/test_judging.py` qua SQLite (12 passed, 1 skipped vì row lock); hai test metadata/vòng sửa công bố qua PostgreSQL. Bao gồm null ban đầu, UTC, giữ locked_at khi unpublish, xóa khi unlock, publish lại, pagination rỗng, quyền và `Cache-Control: no-store`. Ruff lint/format xanh. API cổng 8000 đã restart và OpenAPI thật trỏ tới `JudgingProgress`.

### Nghiệm thu trình duyệt có đăng nhập

Đã chạy bằng Chrome DevTools trên FE `localhost:3000` và API `localhost:8000`, với bốn context riêng: BTC, hai judge và thí sinh; guest ở context riêng. Do chưa có mật khẩu demo, không reset `demo.organizer@example.com`; tạo một fixture local riêng, không ghi mật khẩu vào repo. Fixture ban đầu (tài khoản verified/role, event open, round, đội approved) được tạo trong một transaction DB có audit `browser_fixture.created`; không coi bước chuẩn bị này là bằng chứng UI tạo/duyệt cuộc thi.

- Cuộc thi: `SEAL Phase 4 Browser Acceptance`, slug `phase4-browser-20261031`, event ID `203b016e-e531-4b65-9697-9df0a7167b82`; vòng `cdc6a092-309d-41d5-8521-9a20b39705ce`. Dữ liệu được giữ lại để tra cứu tại `/events/phase4-browser-20261031/results`.
- Từ UI: BTC soạn/lưu rubric 100%, chuyển open → ongoing đúng giờ server; thí sinh nộp repo public thật và nhận v1 `eeefc54d-7b6b-4911-a260-c91ff09ed9c8`, commit bắt đầu `f4bcfaba7c85`. Chờ deadline thật `2026-10-31T15:46:14.983943Z`, không chỉnh giờ hay chèn điểm/bài nộp vào DB.
- Qua hạn: BTC auto tạo hai phân công; hai judge thấy cùng bản v1 đã ghim, lưu nháp và xác nhận lần lượt 8/10, 9/10. Tiến độ ghi assigned=2/submitted=2/missing=0, trung bình tiêu chí 8.50, tổng 85.00, hạng 1.
- Khóa → công bố trả 204. Network `judging-progress` ghi `locked_at=2026-10-31T15:48:11.499131Z`, `published_at=2026-10-31T15:48:29.605759Z`; guest thấy 85.00 sau công bố, trước đó không thấy bảng điểm.
- Thu hồi → mở khóa cũng thao tác qua UI: public trở lại “Chưa có vòng nào công bố kết quả”; progress sau thu hồi giữ locked_at và xóa published_at, sau mở khóa trả cả hai null. Khóa/công bố lại tạo revision 2, giữ 85.00; thí sinh xem được điểm và nhận xét ẩn danh. Sau cùng BTC chuyển judging → closed qua UI thành công.
- Đối chiếu DB chỉ đọc: event đã closed, hai snapshot revision 1/2 còn nguyên, audit có rubric/assignments/lock/publish/unpublish/unlock/transition. Hai biên nhận email đang `pending`; chưa xác nhận worker gửi thư, SMTP acceptance hoặc inbox.

### Việc FE còn phải xử lý trước khi nghiệm thu toàn bộ

1. Sinh lại API type và giữ metadata progress; hiện tại `ProgressPanel` vẫn lấy `.data.items` nên luôn hiện bốn nút, kể cả khi event closed. Dùng bảng trạng thái ở trên và event status/archived để ẩn thao tác không phù hợp.
2. Tab Phân công mở trước deadline không tự cập nhật nút khi đồng hồ qua hạn; đã quan sát nút vẫn disabled sau deadline, đổi tab rồi quay lại mới bật. Cần timer/re-render dựa giờ server khi qua mốc thời gian.
3. Tab Kết quả của thí sinh hiện chỉ mở khi event judging/closed. Kết quả vòng đã công bố khi event còn ongoing (nhiều vòng) cần được tra cứu độc lập theo publication của vòng.
FE đã sửa mục 1–3 ngày 2026-10-31 (sinh lại type; nút theo `locked_at`/`published_at`, ẩn khi event closed/archived, chưa tải xong thì không hiện; nút phân công đếm theo giờ server; tab Kết quả mở từ khi event ongoing). Typecheck/lint/build xanh, chưa nghiệm thu lại trên trình duyệt.

4. Chưa nghiệm thu UI mentor/admin, cuộc thi hai vòng có đội bị loại, stale draft/conflict/reopen trên trình duyệt, và SMTP/inbox. Các test API tương ứng trước đây không thay cho bằng chứng UI.

Trạng thái FE: [ ]

### Nghiệm thu trình duyệt FE (Claude, 2026-10-31)

Fixture local riêng `fe-check-1031b` (event `05162704-62d8-431f-913d-fc5dc4ea9f28`; BTC, 2 judge, mentor, 3 đội, admin; mật khẩu không ghi vào repo). Bài nộp vòng 1 chèn sẵn trong DB để tập trung vào UI Phase 4; deadline vòng 1 là giờ thật, không chỉnh đồng hồ. Chạy bằng Playwright trên `next start` + API local.

- Đã qua trên UI: tab Phân công mở trước hạn, nút tự bật sau hạn 1 giây không cần đổi tab; tự động phân công báo đủ 6 phân công; nút Khóa/Mở khóa/Công bố/Thu hồi đúng từng trạng thái; hai tab cùng chấm → tab cũ dừng tự lưu, báo xung đột, tải bản máy chủ; chấm/xác nhận 6 bài; xếp hạng 85.00 và đồng hạng 2-2 (Beta/Gamma 70.00); trang công khai thấy sau công bố, ẩn sau thu hồi, lọc track; thu hồi → mở khóa → mở lại bài → judge chấm lại → khóa → công bố revision 2 (Alpha 88.00); thí sinh xem Kết quả khi event còn ongoing và hỏi mentor; mentor trả lời, ghi góp ý/tiến độ, xem bài nộp; admin xem kết quả sau khóa, góp ý (lọc SHA), hỏi/đáp chỉ đọc; vòng 2 soạn rubric (chặn khi ≠100, đổi thứ tự) và chọn đội từ kết quả vòng 1.
- Lỗi tìm thấy và đã sửa: lưu rubric gửi `description: null` khi để trống → 422 (BE nhận chuỗi); thông báo “Đã lưu.” của rubric không hiện vì form bị dựng lại; bài chưa chấm hiện nhãn “Đã lưu nháp”.
- Lượt bổ sung (giờ vòng 2 được dời trong DB để mở/hết hạn trong vài phút): thí sinh đánh dấu câu hỏi đã giải quyết; BTC thu hồi mentor → mentor không còn thấy đội; Alpha/Beta nộp vòng 2 qua UI (commit HEAD thật từ GitHub), Gamma không được chọn bị chặn `ROUND_NOT_ELIGIBLE`; auto phân công vòng 2; judge khai báo xung đột → lưu điểm bị chặn `CONFLICT_OF_INTEREST`; BTC gỡ phân công, batch báo rõ đội bị bỏ qua; event closed và archived (admin bấm Lưu trữ qua UI) không còn nút thao tác ở màn tiến độ.
- Lỗi FE tìm thấy và đã sửa: tự lưu nháp gửi PUT lặp mỗi ~1 giây khi server từ chối (ví dụ xung đột lợi ích); nay dừng tới lần sửa kế tiếp.
- Cần BE/BTC quyết: conflict khai báo ở cấp event nên judge từng chấm Alpha vòng 1 (đã công bố) khai báo xung đột ở vòng 2 làm `results_ready` của vòng 1 thành false → toàn bộ vòng 2 mất đội eligible (cả Beta) và event không đóng được cho tới khi BTC thu hồi vòng 1 và thay judge. Đúng chữ đặc tả nhưng tác động rộng; UI hiện chưa giải thích nguyên nhân này cho BTC.
- Email kết quả: mỗi lần publish tạo 3 biên nhận `pending` (đúng 3 thí sinh), không gửi vì SMTP local trỏ Gmail thật; cần Mailpit hoặc địa chỉ thật để nghiệm thu gửi/inbox.
- Ghi chú UX: đội không được chọn vào vòng sau vẫn thấy nút “Nộp bài” bật, chỉ bị server chặn khi bấm (participant chưa có API đọc eligibility).

