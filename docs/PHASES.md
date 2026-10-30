# SEAL – Kế hoạch theo phase

Mỗi phase là một file trong `docs/phases/`, gồm: hợp đồng API chung, việc của Backend, việc của Frontend, tiêu chí hoàn thành.

Rà soát chức năng và ưu tiên bổ sung theo từng vai trò: [ROLE-REVIEW.md](ROLE-REVIEW.md). Các mục mới là kế hoạch cần triển khai, không phải xác nhận API đã tồn tại.

Tiến độ backend 2026-10-30: Phase 1 có 15 operation, Phase 2 có 41 operation và migration 0004 đã áp dụng local. Bằng chứng kiểm tra, giới hạn phụ thuộc Phase 3–4 và cấu hình GitHub còn thiếu xem [bàn giao Phase 2](phases/phase-2-cuoc-thi-doi-thi.md#bàn-giao-backend-phase-2). Frontend được theo dõi riêng, chưa suy là đã nối API từ trạng thái backend.

| Phase | File | Nội dung |
| --- | --- | --- |
| 0 | [phase-0-nen-mong.md](phases/phase-0-nen-mong.md) | Khung dự án, Docker Compose, CI |
| 1 | [phase-1-xac-thuc.md](phases/phase-1-xac-thuc.md) | Đăng ký, đăng nhập, JWT, phân quyền, audit log |
| 2 | [phase-2-cuoc-thi-doi-thi.md](phases/phase-2-cuoc-thi-doi-thi.md) | Cuộc thi, vòng, track, đội thi, khai báo repo |
| 3 | [phase-3-nop-bai.md](phases/phase-3-nop-bai.md) | Nộp bài, phiên bản, hạn nộp |
| 4 ⭐ | [phase-4-cham-diem-xep-hang.md](phases/phase-4-cham-diem-xep-hang.md) | Chấm điểm, xếp hạng, công bố – **MVP** |
| 5 | [phase-5-dong-bo-commit.md](phases/phase-5-dong-bo-commit.md) | Đồng bộ commit GitHub |
| 6 | [phase-6-ai-review.md](phases/phase-6-ai-review.md) | AI đánh giá code |
| 7 | [phase-7-realtime-bao-cao-trien-khai.md](phases/phase-7-realtime-bao-cao-trien-khai.md) | Realtime, thông báo, báo cáo, triển khai |

## Phân công

| Phần | Người làm | Thư mục |
| --- | --- | --- |
| Backend | Codex | `backend/` |
| Frontend | Claude | `frontend/` |

Quy tắc phối hợp:

1. **Hợp đồng API trong file phase là nguồn sự thật.** BE implement đúng path, schema, mã lỗi đã ghi; FE code theo đó.
2. Muốn đổi hợp đồng: sửa bảng trong file phase trước, rồi mới sửa code. Không tự đổi ngầm.
3. Mỗi bên chỉ sửa thư mục của mình. File dùng chung (`docs/`, `docker-compose.yml` ở root nếu có) sửa có ghi chú trong commit.
4. FE sinh type bằng `npm run gen:api` mỗi khi BE merge endpoint mới; lệch type = lệch hợp đồng, báo lại.
5. Đánh dấu `[x]` vào checklist khi xong việc.

## Phân tách vai trò (áp dụng mọi phase)

Theo đặc tả 3.1, mỗi vai trò chỉ thấy và chỉ thao tác màn của mình.

- **Admin** là vai trò quản lý toàn bộ hệ thống và dữ liệu:
  - Tài khoản: tìm kiếm, khóa/mở, cấp/bỏ admin.
  - Cuộc thi: tạo, sửa metadata (name/description/banner_url), chỉ định/bỏ BTC, lưu trữ (ẩn khỏi trang công khai, không xóa), xuất dữ liệu. Cấu hình vận hành do BTC quản lý.
  - Xem **toàn bộ dữ liệu** mọi cuộc thi: đội, thành viên, repo, commit, AI review, góp ý mentor, kết quả chấm.
  - Hệ thống: tình trạng dịch vụ, dung lượng lưu trữ, audit log.
  - **Không** làm việc của người trong cuộc thi: không chấm điểm, không góp ý, không lập/vào đội, không nộp bài, không duyệt đội, không khóa/công bố điểm. Admin không tự nhận vai trò theo cuộc thi.
- **BTC (organizer)** vận hành cuộc thi được giao. **Giám khảo, mentor, thí sinh** chỉ thao tác trong phạm vi được phân công.
- Mọi thay đổi dữ liệu của admin ghi `audit_logs`. FE ẩn nút theo vai trò chỉ là UX; BE kiểm tra quyền ở mọi endpoint.

### Quy tắc phối hợp quyền và dữ liệu

- Chính sách ở [ROLE-REVIEW.md](ROLE-REVIEW.md#quyết-định-nghiệp-vụ) áp dụng cùng bảng quyền từng phase: Admin không dùng event_roles lịch sử để làm nghiệp vụ; participant không kiêm vai trò vận hành trong cùng event; organizer không kiêm judge; mentor không chấm đội từng hỗ trợ.
- Chỉ Admin cấp/bỏ organizer. BTC cấp/bỏ judge, mentor; participant được cấp qua đăng ký. Không cấp role cho admin hoặc tài khoản chưa active/verified. Thu hồi role có phân công đang dùng phải giải quyết phân công trước.
- Mọi GET dùng chung với Admin vẫn có ngoại lệ: không mã mời; không điểm trước khóa; không bản nháp điểm của judge khác; không mặc định quyền đọc dữ liệu riêng qua endpoint public.
- `member.status=pending` chưa được quyền thành viên active. Mọi route lồng nhau phải xác nhận round/team/track/submission thuộc đúng event, kể cả route public.
- Danh sách mới dùng `{items,total}` và limit/offset mặc định 20, tối đa 100. Các mảng nhỏ vốn có (event-roles, bộ tiêu chí rubric, response batch assignment) được giữ nguyên; khi đổi response hiện có phải sửa hợp đồng trước và FE sinh lại type.
- Phase 4 không phụ thuộc Phase 5: mentor note không gắn commit và hỏi/đáp chạy được trước đồng bộ. `commit_sha` chỉ nhận khi Phase 5 đã có commit thuộc đúng đội; panel AI/diff nối dần ở Phase 5–6.

### Hồ sơ cuộc thi cho Admin

Cây dữ liệu: **Cuộc thi → Đội → Repo → Commit → Đánh giá trên commit** (AI review, góp ý mentor gắn commit), cùng bài nộp và kết quả chấm của đội. Mỗi phase mở thêm một tầng; admin dùng lại endpoint đọc sẵn có thay vì một bộ `/admin/*` trùng lặp:

| Tầng | Phase | Endpoint admin dùng |
| --- | --- | --- |
| Cuộc thi, BTC, đội, thành viên, repo | 2 | `GET /events?include_archived`, `GET /events/{id}`, `PATCH /events/{id}`, `POST /events/{id}/archive`, `GET/POST/DELETE /events/{id}/roles` (chỉ BTC), `GET /events/{id}/teams`, `GET /teams/{id}` |
| Bài nộp và file | 3 | `GET /teams/{id}/rounds/{round_id}/submissions`, `GET /submissions/{id}`, `GET /events/{id}/rounds/{round_id}/submissions` |
| Góp ý/hỏi đáp mentor, kết quả chấm | 4 | `GET /teams/{id}/mentor-notes?commit_sha=`, `GET /teams/{id}/questions`, `GET /questions/{id}/answers`, `GET /teams/{id}/rounds/{round_id}/result`, leaderboard |
| Commit | 5 | `GET /teams/{id}/commits`, `GET /teams/{id}/commits/{sha}`, `GET /teams/{id}/commit-stats` |
| AI review | 6 | `GET /teams/{id}/ai-reviews?commit_sha=`, `GET /teams/{id}/ai-summary` |
| Xuất dữ liệu | 7 | `GET /events/{id}/reports/export` |

- Điểm và nhận xét giám khảo chỉ hiện cho admin **sau khi vòng đã khóa điểm**, để không lộ điểm khi đang chấm.
- Admin không thấy `invite_code` của đội.
- Không xóa cứng cuộc thi đã qua `draft`; sau `closed` giữ nguyên đội, commit, review, điểm để tra cứu.
- Màn FE: `/admin/events` → `/admin/events/[id]` → `/admin/teams/[id]` → `/admin/teams/[id]/commits/[sha]`.

## Thứ tự phụ thuộc

```text
P0 → P1 → P2 → P3 → P4 (MVP)
            └──→ P5 → P6
P4 + P5 → P7
```

P5 chỉ cần P2, nên có thể làm song song với P3–P4.

