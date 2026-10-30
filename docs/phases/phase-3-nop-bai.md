# Phase 3 – Nộp bài

**Mục tiêu:** đội nộp và nộp lại bài an toàn, kể cả sát hạn chót.

**Phụ thuộc:** Phase 2.

## Hợp đồng API

| Method | Path | Quyền | Body → Response |
| --- | --- | --- | --- |
| POST | `/uploads/presign` | thành viên active đội approved | `{team_id, filename, content_type, size}` → `{upload_url, method: "POST", headers: {}, fields: {public_id, timestamp, type, overwrite, api_key, signature}, file_key}`; Cloudinary signed multipart FormData, thêm trường `file` |
| POST | `/teams/{team_id}/rounds/{round_id}/submissions` | leader active | header `Idempotency-Key`; `SubmissionInput` → 201 `Submission` |
| GET | `/teams/{team_id}/rounds/{round_id}/submissions` | thành viên active, organizer, mentor/judge được phân công, admin | `?limit&offset` → `{items: Submission[], total}` (mới nhất trước) |
| GET | `/submissions/{submission_id}` | như trên | → `Submission` kèm `files[].download_url` (URL ký có hạn) |
| GET | `/events/{event_id}/rounds/{round_id}/submissions` | organizer, admin | `?limit&offset` → `{items: [{team_id, name, submission: Submission|null}], total}`; đội approved, bản cuối mỗi đội + đội chưa nộp |

- `SubmissionInput`: `{repo_url, demo_url?, video_url?, description?, file_keys: string[]}`
- `Submission`: `{id, team_id, round_id, version, repo_url, commit_sha, demo_url, video_url, description, files: [{key, filename, size, content_type, download_url?}], submitted_by, submitted_at, is_final}`
- File cho phép: pdf, pptx, mp4, zip; tối đa 100 MB/file (BE quyết định, FE kiểm tra trước để báo sớm).
- Admin chỉ đọc bài nộp (kể cả tải file qua URL ký); admin presign/nộp bài → 403. Không xóa bài nộp và file sau khi cuộc thi `closed`.
- Mã lỗi: `DEADLINE_PASSED`, `ROUND_NOT_OPEN`, `TEAM_NOT_APPROVED`, `FILE_TOO_LARGE`, `FILE_TYPE_NOT_ALLOWED`, `FILE_NOT_UPLOADED`.

### Chi tiết hợp đồng triển khai

- Prefix `/api/v1`; mọi GET trả `Cache-Control: no-store`. POST nộp chỉ leader active; presign cho mọi active member, admin luôn 403 ở hai POST.
- `GET /events/{event_id}/rounds/{round_id}/submissions` trả `{items: [{team_id, name, submission: Submission|null}], total}` cho đội approved chưa giải tán, kể cả đội chưa nộp; bản cuối theo version. Các danh sách mặc định 20, tối đa 100, offset >= 0.
- Presign: filename 1–255 ký tự, không đường dẫn/ký tự điều khiển; size số nguyên 1–104857600. MIME chính xác: `.pdf=application/pdf`, `.pptx=application/vnd.openxmlformats-officedocument.presentationml.presentation`, `.mp4=video/mp4`, `.zip=application/zip`. POST FormData gửi nguyên `fields` và trường `file`; không tự đặt Content-Type (browser tạo multipart boundary). Cloudinary raw không ràng buộc MIME/size bằng chữ ký, nên BE đối chiếu size thực và signature nhị phân khi submit; giới hạn raw/account Cloudinary có thể thấp hơn mức tối đa của API. File_key do server sinh, chỉ giữ extension. Tối đa 10 key không trùng mỗi bài. Presign chọn vòng đang mở mà đội eligible; không có vòng phù hợp trả ROUND_NOT_OPEN.
- Input chỉ nhận field đã mô tả; repo_url tối đa 2048 ký tự, phải bằng URL repo canonical đã duyệt; demo/video HTTP(S) tối đa 2048; description tối đa 20000, mặc định null; file_keys mặc định [].
- Lỗi bổ sung: 403 `FORBIDDEN`/`NOT_TEAM_LEADER`; 404 `TEAM_NOT_FOUND`/`ROUND_NOT_FOUND`/`SUBMISSION_NOT_FOUND`; 409 `DEADLINE_PASSED`/`ROUND_NOT_OPEN`/`TEAM_NOT_APPROVED`/`ROUND_NOT_ELIGIBLE`/`SUBMISSIONS_FROZEN`/`IDEMPOTENCY_CONFLICT`; 422 `REPO_MISMATCH`/`FILE_TOO_LARGE`/`FILE_TYPE_NOT_ALLOWED`/`FILE_NOT_UPLOADED` (bao gồm sai size, key ngoài đội hoặc đã dùng); 503 `REPO_UNAVAILABLE`/`STORAGE_NOT_CONFIGURED`/`STORAGE_UNAVAILABLE`. Lỗi schema/header dùng 422 `VALIDATION_ERROR` chung.
- Ghi audit `upload.presigned`, `submission.created` trong transaction dữ liệu; retry key cũ không thêm audit. Nhắc hạn claim một lần trước SMTP, lưu trạng thái accepted/failed riêng; failed hoặc receipt mơ hồ không tự retry.
- Storage dùng Cloudinary: SDK `cloudinary`, cấu hình `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`. Mọi file dùng resource_type=raw, type=authenticated, overwrite=false ký cùng public_id. Dùng product environment dev/test riêng; không bật unsigned preset cho vùng bài nộp. Credentials local đã được cấu hình và smoke test provider thật đã qua, xem bằng chứng dưới.
- Phase 4 nối `JudgingService.can_read_submission` với phân công mentor/judge thực và `submissions_frozen` với mốc bắt đầu phân công, dùng cùng khóa event. Trước khi có phân công, các quyền này mặc định đóng; role mentor/judge đơn thuần không cấp quyền đọc. Eligibility các vòng sau dùng round_eligibilities qua events service.

### Biên nhận và toàn vẹn bài nộp

- repo_url phải khớp repo đã duyệt của đội; server lấy HEAD SHA qua GitHub client và lưu `commit_sha` bất biến. Không cần dữ liệu đồng bộ Phase 5 để nộp. GitHub không xác minh được trả `503 REPO_UNAVAILABLE`, không tạo phiên bản giả; link demo/video chỉ lưu HTTP(S), không fetch từ API.
- Nộp trong `[round.starts_at, submission_deadline)` theo UTC server, event ongoing, đội approved và đủ điều kiện của vòng. Vòng 1 nhận tất cả đội approved; các vòng sau dùng danh sách được BTC chọn ở Phase 4. Upload xong sau hạn không được nhận thêm thời gian nộp.
- `Idempotency-Key` bắt buộc, tối đa 128 ký tự, phạm vi user/team/round; lưu hash payload và response ID cùng transaction. Xác thực/quyền trước, rồi tra key trước kiểm tra hạn: retry đúng payload sau hạn vẫn nhận biên nhận cũ, không tạo bản mới; khác payload cùng key → `409 IDEMPOTENCY_CONFLICT`. Khóa theo team/round để cấp version khi nộp đồng thời.
- 201 và GET Submission là biên nhận: hiển thị id, version, server submitted_at và SHA; không coi upload thành công là đã nộp. Bản cuối hợp lệ được tính điểm; khi bắt đầu phân công chấm cố định `submission_id`, cấm nộp thêm cho vòng đó dù thời hạn cấu hình bị sửa.
- Presign chỉ cho active member của đội approved trong thời gian nhận bài; chữ ký upload còn hiệu lực khoảng 10 phút: Cloudinary nhận timestamp trong 1 giờ, BE ký timestamp lùi 50 phút. Tối đa 10 file/bài, mỗi file 100 MB ở mức API (còn phụ thuộc quota raw của tài khoản); server kiểm tra kích thước thực, extension/MIME/signature phù hợp, quyền file_key và không dùng filename làm object key.
- Khi submit, BE xác minh metadata qua Cloudinary Admin API rồi rename asset authenticated từ uploads/ sang public_id submissions/ không được cấp chữ ký upload. Đọc và kiểm tra bản đã chuyển trước khi lưu receipt; chữ ký cũ chỉ nhắm ID upload, không thể sửa ID bài nộp. Nếu validation/quá hạn sau rename, asset chưa nộp được dọn; FE phải xin chữ ký/upload lại khi retry báo FILE_NOT_UPLOADED. File ZIP chỉ tải về, không giải nén/chạy code; download qua private_download_url, attachment, expires_at tối đa 5 phút, không public delivery. Không khẳng định kiểm tra định dạng là quét sạch mã độc.
- Dọn upload tạm chưa gắn bài sau 24 giờ, tránh xóa file đang được chốt trong transaction; không dọn file bài đã nộp. Nhắc hạn chỉ gửi đội đủ điều kiện, dedupe theo team/round/mốc nhắc, email không retry receipt mơ hồ.

## Backend (Codex)

- [x] `integrations/storage.py`: signed POST/download qua Cloudinary authenticated raw; env local đã cấu hình và provider smoke test đã qua với file mẫu nhỏ. Không đổi runtime local.
- [x] Model `submissions`, `submission_files`; unique `(team_id, round_id, version)`.
- [x] Kiểm tra hạn bằng `now()` của server; chặn khi đội chưa được duyệt.
- [x] Idempotency: cùng `Idempotency-Key` trả lại kết quả cũ, không tạo version mới.
- [x] Xác nhận `file_key` đã tồn tại trên storage và thuộc đúng đội trước khi lưu.
- [x] `is_final` = bản cuối trước hạn.
- [x] Task Beat nhắc hạn (24h và 1h trước `submission_deadline`), không gửi trùng; test SMTP mock, chưa chứng nhận inbox thật.
- [x] Test: admin đọc bài nộp 200, admin nộp → 403; nộp sau hạn, nộp lại tăng version, gửi trùng key, file của đội khác.
- [x] Snapshot SHA độc lập Phase 5, biên nhận bất biến, version cấp trong transaction; test retry sau hạn, key đổi payload, ghi đè file sau submit và quyền mentor qua hook phân công (DB phân công thực thuộc Phase 4).

## Frontend (Claude)

- [x] Tab "Nộp bài" trong `/events/[slug]/my-team`: chọn vòng, form link + upload file.
- [x] Upload: gọi presign → POST FormData gồm nguyên `fields` + `file` thẳng lên Cloudinary có thanh tiến độ → gửi metadata; sinh `Idempotency-Key` một lần cho mỗi lần bấm nộp.
- [x] Đếm ngược hạn dựa trên `/time` của server (bù lệch đồng hồ máy).
- [x] Lịch sử phiên bản, đánh dấu bản đang được tính điểm.
- [x] Khóa nút nộp khi quá hạn, nhưng vẫn hiển thị lỗi `DEADLINE_PASSED` nếu server từ chối.
- [x] BTC: bảng bài nộp theo vòng, lọc đội chưa nộp (lọc trong trang hiện tại vì API chưa có tham số lọc).
- [x] Admin `/admin/teams/[id]`: tab Bài nộp (các phiên bản theo vòng, bản đang tính điểm, tải file).
- [x] Biên nhận hiển thị version/server time/SHA; giữ key khi retry cùng payload, tạo key mới khi chủ động nộp phiên bản mới.
- [ ] Mentor có tab bài nộp chỉ đọc: làm cùng màn mentor ở Phase 4 (BE đóng quyền đọc tới khi có phân công; component `TeamSubmissions` dùng lại được).

Trạng thái FE: [ ]

## Xong khi

- Demo luồng 4.3.3 của đặc tả.
- Bấm nộp liên tục chỉ tạo 1 phiên bản; nộp sau hạn bị chặn ở BE.
- Kiểm tra task nhắc hạn qua SMTP được cấu hình, dedupe không gửi trùng; ghi riêng bằng chứng SMTP chấp nhận và inbox nhận. Không dùng Mailpit.

## Bàn giao backend Phase 3

Đã triển khai **5 operation** theo bảng trên; OpenAPI giữ riêng `PresignInput/Output`, `SubmissionInput/Output`, `FileOutput`, `RoundSubmission` và Page tương ứng. Checklist Backend hoàn thành ở mức triển khai/test; Cloudinary và GitHub đã có smoke test provider thật với phạm vi ghi dưới đây. Phase 3 chưa nghiệm thu toàn luồng FE và email nhắc hạn thật.

### Migration và hành vi

- Migration **0005_submissions**, nối từ 0004_events_teams, thêm `submissions`, `submission_files`, `file_uploads`, `deadline_reminders`. Mọi FK có index; unique version `(team_id, round_id, version)`, biên nhận `(submitted_by, team_id, round_id, idempotency_key)`, file key và mốc nhắc đều được bảo vệ tại DB. Không sửa migration cũ, không xóa dữ liệu cũ.
- Mutation khóa theo thứ tự user → event → team → upload keys đã sắp xếp; cấp version và ghi audit trong cùng transaction. Khóa event hiện tuần tự hóa các mutation cùng cuộc thi, khớp Phase 2; Phase 4 phải dùng cùng khóa khi tạo phân công. GET tải file theo batch, danh sách mới nhất trước, không trả ORM thẳng ra API.
- Chỉ leader active nộp; member active khác được presign/đọc; pending bị chặn. Admin chỉ dùng 3 GET, kể cả lấy download URL; lịch sử event-role không cho admin nộp thay đội. Team/round được đối chiếu cùng event trước truy xuất dữ liệu.
- Kiểm tra `[starts_at, submission_deadline)` bằng UTC server hai lần: trước gọi provider và sau kiểm tra file; mốc cuối cũng là `submitted_at`. Retry được xác thực/quyền trước, rồi tra key trước trạng thái/hạn; đúng payload trả ID cũ, khác payload trả 409. `commit_sha` cố định từ GitHub HEAD, không phụ thuộc đồng bộ Phase 5. `is_final` được tính từ version cuối, các field biên nhận khác không bị sửa.
- Upload Cloudinary signed POST FormData, type=authenticated, resource_type=raw, overwrite=false, public_id ngẫu nhiên kèm extension. Chữ ký còn khoảng 600 giây nhờ timestamp lùi 50 phút trên cửa sổ 1 giờ của Cloudinary; không ràng buộc size/MIME ở provider bằng chữ ký. BE kiểm tra metadata Admin API, rename sang `submissions/{submission_id}/{random_id}.{ext}`, đọc và kiểm tra size/signature của asset đã chuyển trước khi lưu biên nhận. PDF kiểm tra magic; MP4 kiểm tra ftyp; ZIP/PPTX đọc central directory, PPTX phải có cấu trúc tối thiểu, không giải nén/chạy nội dung. Đây là kiểm tra định dạng, không phải quét mã độc. Download private_download_url ký 300 giây, attachment, không phát URL CDN public; chỉ GET chi tiết thêm download_url.
- Key upload chỉ dùng một lần; gửi phiên bản mới có file thì xin/upload key mới. FileOutput.key giữ key đã cấp để đối chiếu, download thực tế dùng public_id nội bộ. Chữ ký upload cũ không nhắm ID bài nộp; replay chỉ có thể tạo lại ID tạm, không ảnh hưởng receipt. Rename thất bại hoặc quá hạn sau rename có thể cần FE upload lại key mới; không coi HTTP upload thành công là nộp bài thành công.
- Beat `seal.submission_reminders` chạy mỗi 60 giây: nhắc leader active/verified của đội approved eligible, một lần/team/round/mốc 24h hoặc 1h. Khi worker khởi động muộn, chọn mốc còn phù hợp (còn <=1h không gửi bù cả mốc 24h). Claim trước SMTP; accepted chỉ là transport chấp nhận, failed/claimed sau sự cố cần kiểm tra thủ công, không tự retry email.
- Beat `seal.cleanup_uploads` mỗi giờ: destroy asset authenticated raw ở vùng upload tạm quá 24h theo batch 100 tới khi hết; `FOR UPDATE SKIP LOCKED` tránh file đang được chốt. Không đụng file receipt. Lỗi validation hoặc quá hạn sau rename cố gắng dọn asset chưa nộp; nếu DB/commit hoặc storage cleanup gặp sự cố, có thể còn asset mồ côi, cần đối chiếu DB thủ công, không tự xóa vùng submissions vì receipt commit có thể mơ hồ.

### Bằng chứng kiểm tra local (2026-10-30)

- `backend/.venv/Scripts/python.exe -m ruff format .` và `-m ruff check .`: xanh.
- Sau chuyển Cloudinary, `-m pytest -q --disable-warnings --maxfail=1`: **157 passed, 4 skipped**, 6 cảnh báo deprecation không gây fail (166.39s). Bốn test khóa dòng dành riêng PostgreSQL bỏ qua ở SQLite; hai test Phase 3 trong số này đã chạy xanh trên PostgreSQL ở lượt dưới.
- Database riêng **seal_test_phase3** sau chuyển Cloudinary: `SEAL_TEST_DATABASE_URL=postgresql+asyncpg://.../seal_test_phase3`; `pytest tests/test_submissions.py tests/test_submission_jobs.py tests/test_storage.py -q --disable-warnings --maxfail=1`: **45 passed** (114.12s). Chứng minh nộp cùng key đồng thời chỉ một ID, khác key cấp version 2/3; cleanup bỏ qua row đang khóa; chữ ký upload khóa public_id/type/overwrite, download attachment hết hạn và kiểm tra bytes sau rename. Fixture chỉ reset database có tên bắt đầu `seal_test_`, không reset DB local chứa dữ liệu demo.
- `alembic upgrade head` thành công trên PostgreSQL SEAL local; `alembic current` = **0005_submissions (head)**, `alembic check` không có schema drift. Test migration còn kiểm tra upgrade/downgrade/upgrade trên SQLite. `pip check` không có dependency lỗi.
- Lượt rà soát docs/Phase 3 hiện tại: `ruff check .` xanh; `pytest tests/test_submissions.py tests/test_submission_jobs.py tests/test_storage.py -q --disable-warnings`: **43 passed, 2 skipped** (72.56s); hai test khóa dòng Phase 3 cần PostgreSQL nên bỏ qua ở lượt SQLite này. Đã đọc lại `alembic current`/`check`: head 0005, không drift. Kết quả toàn bộ 157 test và 45 test PostgreSQL ở trên là bằng chứng lượt triển khai trước; không chạy lại toàn bộ suite cho thay đổi chỉ tài liệu này.
- Test bao gồm biên start/deadline chính xác, provider chậm vượt hạn, trạng thái event/vòng, pending/admin/nonleader, đội chưa duyệt, chéo event/round, eligibility vòng sau, idempotency/conflict, snapshot SHA, file key ngoài đội/đã dùng/chưa upload, MIME/size/signature, TTL/attachment, audit và reminder dedupe/SMTP receipt mơ hồ.
- Không sửa `frontend/`, không push/commit. Docker Desktop và Compose PostgreSQL/Redis đã được khởi động lại để kiểm tra migration. Các thay đổi docs Phase 0–2 và workflow frontend xuất hiện từ luồng khác được giữ nguyên.

### Mã lỗi mới và việc FE cần làm

- Mã lỗi/status đầy đủ ở mục "Chi tiết hợp đồng triển khai": FE cần xử lý thêm `IDEMPOTENCY_CONFLICT`, `REPO_MISMATCH`, `REPO_UNAVAILABLE`, `ROUND_NOT_ELIGIBLE`, `SUBMISSIONS_FROZEN`, `STORAGE_NOT_CONFIGURED`, `STORAGE_UNAVAILABLE`, cùng các lỗi file/hạn/đội trong bảng gốc. 503 không tạo phiên bản giả; khi response nộp bị mất, retry cùng key/payload hoặc GET lịch sử để xác minh.
- FE chạy `npm run gen:api` từ OpenAPI mới; không sửa tay type. API CORS đã cho phép header `Idempotency-Key`.
- Xin presign rồi tạo FormData, append nguyên từng cặp `fields` và `file` là File/Blob, POST tới upload_url theo `method`. Không tự đặt Content-Type multipart hoặc thêm tham số upload ngoài fields đã ký. Không upload qua API backend; không dùng secure_url public từ response Cloudinary để tải bài. API secret chỉ ở backend.
- Giữ key idempotency cho retry cùng payload, key mới khi chủ động nộp phiên bản mới; chỉ 201/GET receipt xác nhận đã nộp. Hiện id/version/submitted_at/commit_sha và is_final; đồng hồ client chỉ hỗ trợ hiển thị. Tải file bằng GET `/submissions/{id}` để lấy URL mới khi URL cũ hết hạn.
- BTC/Admin dùng Page RoundSubmission với `submission=null` cho đội chưa nộp; admin không có nút presign/nộp. Mentor/judge chỉ mở được sau khi Phase 4 nối phân công thực.

### Giới hạn nghiệm thu và cấu hình

- SDK **cloudinary** và dependency lock đã cập nhật. `.env.example` có `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`; dùng product environment dev/test riêng và không cấu hình unsigned upload cho vùng bài nộp. Tham khảo [chữ ký Cloudinary](https://cloudinary.com/documentation/authentication_signatures), [Upload API / rename / download](https://cloudinary.com/documentation/image_upload_api_reference) và [authenticated access](https://cloudinary.com/documentation/control_access_to_media).
- Local hiện có đủ ba cấu hình Cloudinary và GITHUB_TOKEN; chỉ kiểm tra cờ tồn tại, không ghi giá trị vào docs/log. Đã xác minh GitHub HEAD repo public `fastapi/fastapi` qua đúng github_client của backend; đây là bằng chứng provider đọc repo public, chưa phải nghiệm thu repo của từng đội. SMTP có cấu hình nhưng lượt này không gửi thư thật; chưa có bằng chứng SMTP chấp nhận hoặc inbox nhận reminder.
- Phase 4 phải thay hook mặc định trong `JudgingService` bằng truy vấn assignment thực, kiểm tra mentor bị thu hồi, judge đúng submission snapshot, và đóng nhận bài khi phân công bắt đầu. Test hiện tại chứng minh service tôn trọng hook, không chứng nhận DB phân công chưa tồn tại. Vòng sau mặc định không đủ điều kiện nếu chưa có round_eligibilities do Phase 4 xác nhận.
- Chưa kiểm tra CI remote, giao diện FE và triển khai production. Không đánh đồng test local với nghiệm thu các tầng này.

### Smoke test Cloudinary thật (rà soát 2026-10-30)

Gọi đúng `Storage.presign` → HTTP signed multipart upload trực tiếp → `Storage.seal` (Admin API + rename + đọc kiểm tra) → `Storage.download` trên cấu hình local. Dùng namespace test ngẫu nhiên `uploads/phase3-smoke/` và `submissions/phase3-smoke/`, không sửa asset người dùng hoặc dữ liệu cuộc thi.

| File mẫu | Upload | Chốt/đọc file | Tải bằng URL ký | URL không ký | Replay chữ ký upload cũ | Dọn file test |
| --- | --- | --- | --- | --- | --- | --- |
| PDF | 200 | Qua | 200, bytes khớp, attachment | 401 | File đã chốt giữ nguyên | Qua |
| ZIP | 200 | Qua | 200, bytes khớp, attachment | 401 | File đã chốt giữ nguyên | Qua |
| PPTX | 200 | Qua | 200, bytes khớp, attachment | 401 | File đã chốt giữ nguyên | Qua |
| MP4 | 200 | Qua | 200, bytes khớp, attachment | 401 | File đã chốt giữ nguyên | Qua |

Mẫu nhỏ chỉ dùng kiểm tra đường đi byte/signature và quyền truy cập, không chứng nhận nội dung slide/video mở được trong mọi phần mềm. Đã destroy cả ID upload tái tạo bởi replay và ID đã chốt; cleanup cả bốn loại thành công. Không lưu chữ ký, download URL hay secret vào tài liệu. Chưa thử file 100 MB, quota/raw limit của account, hết hạn URL theo thời gian thực hoặc upload từ browser thật.

### Việc còn lại để nghiệm thu Phase 3

- [ ] **Frontend (Claude):** sinh lại type từ OpenAPI (hiện `frontend/src/lib/api-types.ts` chưa có `/uploads/presign`/SubmissionInput); làm các màn trong checklist FE, POST FormData đúng fields, giữ key khi retry, hiển thị biên nhận/lịch sử/bản cuối và bảng BTC/Admin. Lượt rà soát chỉ đọc FE, không sửa thư mục frontend.
- [ ] **Demo toàn luồng:** leader active của đội approved nộp qua FE với repo đội thật; kiểm tra upload → submit → receipt → tải file, nonleader/pending/admin bị chặn, retry và quá hạn ở server. Smoke provider và pytest không thay bằng chứng tích hợp browser/API/DB này.
- [ ] **Email nhắc hạn:** chạy đúng worker/Beat trên event test có leader nhận thư được chọn, xác minh claim 24h/1h không trùng, ghi riêng SMTP accepted và inbox nhận. Không gửi vào tài khoản demo/người dùng hiện có khi chưa chọn người nhận để nghiệm thu.
- [ ] **Giới hạn provider:** xác minh account cho phép authenticated raw ở mức dung lượng mong muốn, thử file gần giới hạn và URL ký hết hạn; file 100 MB hiện mới là giới hạn validation của API. Signed upload không khóa size ở provider, nên quota Cloudinary cần được quản lý cả với upload chưa submit.
- [ ] **Phụ thuộc Phase 4:** nối DB assignment vào `can_read_submission` và `submissions_frozen`; dùng cùng khóa event, kiểm tra mentor bị thu hồi/judge đúng snapshot; xác nhận đội qua vòng qua round_eligibilities. Hiện chỉ active member/BTC/admin có đường đọc thực, mentor/judge chỉ có role vẫn bị chặn.

Theo dõi thêm ngoài API nộp bài: `SystemService.overview` hiện vẫn ghi cứng storage=`not_configured` và storage_bytes chưa đo được, kể cả khi Cloudinary đã cấu hình. Cần nối health/usage Cloudinary khi hoàn thiện dashboard hệ thống; không dùng ô health này để kết luận signed upload đang lỗi. Không đổi endpoint hay schema health trong lượt cập nhật docs này.

Trạng thái FE: [ ]
