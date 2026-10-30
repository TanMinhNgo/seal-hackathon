# Phase 3 – Nộp bài

**Mục tiêu:** đội nộp và nộp lại bài an toàn, kể cả sát hạn chót.

**Phụ thuộc:** Phase 2.

## Hợp đồng API

| Method | Path | Quyền | Body → Response |
| --- | --- | --- | --- |
| POST | `/uploads/presign` | thành viên đội | `{team_id, filename, content_type, size}` → `{upload_url, method, headers, file_key}` |
| POST | `/teams/{team_id}/rounds/{round_id}/submissions` | leader | header `Idempotency-Key`; `SubmissionInput` → 201 `Submission` |
| GET | `/teams/{team_id}/rounds/{round_id}/submissions` | thành viên active, organizer, mentor/judge được phân công, admin | `?limit&offset` → `{items: Submission[], total}` (mới nhất trước) |
| GET | `/submissions/{submission_id}` | như trên | → `Submission` kèm `files[].download_url` (URL ký có hạn) |
| GET | `/events/{event_id}/rounds/{round_id}/submissions` | organizer, admin | `?limit&offset` → bản cuối của mỗi đội + đội chưa nộp |

- `SubmissionInput`: `{repo_url, demo_url?, video_url?, description?, file_keys: string[]}`
- `Submission`: `{id, team_id, round_id, version, repo_url, commit_sha, demo_url, video_url, description, files: [{key, filename, size, content_type, download_url?}], submitted_by, submitted_at, is_final}`
- File cho phép: pdf, pptx, mp4, zip; tối đa 100 MB/file (BE quyết định, FE kiểm tra trước để báo sớm).
- Admin chỉ đọc bài nộp (kể cả tải file qua URL ký); admin presign/nộp bài → 403. Không xóa bài nộp và file sau khi cuộc thi `closed`.
- Mã lỗi: `DEADLINE_PASSED`, `ROUND_NOT_OPEN`, `TEAM_NOT_APPROVED`, `FILE_TOO_LARGE`, `FILE_TYPE_NOT_ALLOWED`, `FILE_NOT_UPLOADED`.

### Biên nhận và toàn vẹn bài nộp

- repo_url phải khớp repo đã duyệt của đội; server lấy HEAD SHA qua GitHub client và lưu `commit_sha` bất biến. Không cần dữ liệu đồng bộ Phase 5 để nộp. GitHub không xác minh được trả `503 REPO_UNAVAILABLE`, không tạo phiên bản giả; link demo/video chỉ lưu HTTP(S), không fetch từ API.
- Nộp trong `[round.starts_at, submission_deadline)` theo UTC server, event ongoing, đội approved và đủ điều kiện của vòng. Vòng 1 nhận tất cả đội approved; các vòng sau dùng danh sách được BTC chọn ở Phase 4. Upload xong sau hạn không được nhận thêm thời gian nộp.
- `Idempotency-Key` bắt buộc, tối đa 128 ký tự, phạm vi user/team/round; lưu hash payload và response ID cùng transaction. Xác thực/quyền trước, rồi tra key trước kiểm tra hạn: retry đúng payload sau hạn vẫn nhận biên nhận cũ, không tạo bản mới; khác payload cùng key → `409 IDEMPOTENCY_CONFLICT`. Khóa theo team/round để cấp version khi nộp đồng thời.
- 201 và GET Submission là biên nhận: hiển thị id, version, server submitted_at và SHA; không coi upload thành công là đã nộp. Bản cuối hợp lệ được tính điểm; khi bắt đầu phân công chấm cố định `submission_id`, cấm nộp thêm cho vòng đó dù thời hạn cấu hình bị sửa.
- Presign chỉ cho active member của đội approved trong thời gian nhận bài; URL upload hết hạn sau 10 phút. Tối đa 10 file/bài, mỗi file 100 MB; server kiểm tra kích thước thực, extension/MIME/signature phù hợp, quyền file_key và không dùng filename làm object key.
- Giữ file bài nộp bất biến bằng object version hoặc copy từ vùng upload tạm sang key riêng không còn URL PUT. Chỉ HEAD trước submit chưa ngăn được ghi đè sau submit. File ZIP chỉ tải về, không giải nén/chạy code; download dạng attachment và URL ký tối đa 5 phút, không public bucket. Không khẳng định kiểm tra định dạng là quét sạch mã độc.
- Dọn upload tạm chưa gắn bài sau 24 giờ, tránh xóa file đang được chốt trong transaction; không dọn file bài đã nộp. Nhắc hạn chỉ gửi đội đủ điều kiện, dedupe theo team/round/mốc nhắc, email không retry receipt mơ hồ.

## Backend (Codex)

- [ ] `integrations/storage.py`: presigned PUT/GET qua storage provider được chọn; bucket dev/test riêng. Không tự thêm MinIO hoặc thay cách chạy local khi chưa chọn provider.
- [ ] Model `submissions`, `submission_files`; unique `(team_id, round_id, version)`.
- [ ] Kiểm tra hạn bằng `now()` của server; chặn khi đội chưa được duyệt.
- [ ] Idempotency: cùng `Idempotency-Key` trả lại kết quả cũ, không tạo version mới.
- [ ] Xác nhận `file_key` đã tồn tại trên storage và thuộc đúng đội trước khi lưu.
- [ ] `is_final` = bản cuối trước hạn.
- [ ] Task Beat nhắc hạn (24h và 1h trước `submission_deadline`), không gửi trùng.
- [ ] Test: admin đọc bài nộp 200, admin nộp → 403; nộp sau hạn, nộp lại tăng version, gửi trùng key, file của đội khác.
- [ ] Snapshot SHA độc lập Phase 5, biên nhận bất biến, version cấp trong transaction; test retry sau hạn, key đổi payload, ghi đè file sau submit và mentor chỉ đọc đội được giao.

## Frontend (Claude)

- [ ] Tab "Nộp bài" trong `/events/[slug]/my-team`: chọn vòng, form link + upload file.
- [ ] Upload: gọi presign → PUT thẳng lên storage có thanh tiến độ → gửi metadata; sinh `Idempotency-Key` một lần cho mỗi lần bấm nộp.
- [ ] Đếm ngược hạn dựa trên `/time` của server (bù lệch đồng hồ máy).
- [ ] Lịch sử phiên bản, đánh dấu bản đang được tính điểm.
- [ ] Khóa nút nộp khi quá hạn, nhưng vẫn hiển thị lỗi `DEADLINE_PASSED` nếu server từ chối.
- [ ] BTC: bảng bài nộp theo vòng, lọc đội chưa nộp.
- [ ] Admin `/admin/teams/[id]`: tab Bài nộp (các phiên bản theo vòng, bản đang tính điểm, tải file).
- [ ] Biên nhận hiển thị version/server time/SHA; giữ key khi retry cùng payload, tạo key mới khi chủ động nộp phiên bản mới; mentor có tab bài nộp chỉ đọc.

Trạng thái FE: [ ]

## Xong khi

- Demo luồng 4.3.3 của đặc tả.
- Bấm nộp liên tục chỉ tạo 1 phiên bản; nộp sau hạn bị chặn ở BE.
- Kiểm tra task nhắc hạn qua SMTP được cấu hình, dedupe không gửi trùng; ghi riêng bằng chứng SMTP chấp nhận và inbox nhận. Không dùng Mailpit.
