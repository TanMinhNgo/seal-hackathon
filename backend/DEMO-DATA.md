# Dữ liệu demo local

Chạy từ `backend/`, sau khi PostgreSQL local đã chạy và `alembic upgrade head` hoàn tất:

```powershell
.\.venv\Scripts\python.exe -m app.seed_demo
```

Nhập mật khẩu chung cho tài khoản demo (8–128 ký tự, nhập ẩn). Tự động hóa có thể
truyền qua biến môi trường `SEAL_DEMO_PASSWORD`; không đặt mật khẩu trong Git.

Seed chỉ chấp nhận PostgreSQL `localhost`/`127.0.0.1:5434/seal`. Không xóa hoặc
cập nhật dữ liệu đang có. Toàn bộ dữ liệu được thêm trong một transaction, có
khóa chống chạy đồng thời. Chạy lại nhận `already seeded`: không đổi mật khẩu,
không đặt lại lịch, không ghi đè chỉnh sửa của bạn. Nếu email demo đã tồn tại
trước lần seed đầu, seed dừng và rollback để bảo vệ tài khoản đó.

Nếu đã nạp bộ mẫu phiên bản đầu, làm sạch một lần bằng:

```powershell
.\.venv\Scripts\python.exe -m app.seed_demo --clean
```

Lệnh này chỉ sửa nội dung mặc định của bộ mẫu và mốc tạo tài khoản/cuộc thi/vai trò;
bổ sung repo tham chiếu còn thiếu cho đội approved. Giữ nguyên mật khẩu, lịch thi,
trạng thái và nội dung đã tự chỉnh; ghi audit `demo.cleaned`. Chạy lại không thêm trùng.

## Tài khoản

Tất cả tài khoản bên dưới đã xác thực, đang hoạt động và **không phải admin**.
Admin và tài khoản cũ của bạn giữ nguyên. Vai trò được cấp riêng trong từng cuộc thi.

| Email | Mục đích |
| --- | --- |
| `demo.organizer@example.com` | BTC của cả 4 cuộc thi |
| `demo.judge1@example.com`, `demo.judge2@example.com` | Giám khảo |
| `demo.mentor1@example.com`, `demo.mentor2@example.com` | Mentor |
| `demo.student01@example.com` – `demo.student12@example.com` | Thí sinh, 3 người/đội |
| `demo.student13@example.com`, `demo.student14@example.com` | Đã đăng ký, chưa có đội |

Student01/04/07/10 lần lượt là trưởng đội Lotus AI/Green Byte/EduSpark/Mekong Makers.
Cùng nhóm tài khoản tham gia 3 cuộc thi public; không có vai trò vận hành trùng thí sinh.

## Dữ liệu

- 4 cuộc thi, slug: `demo-seal-draft`, `demo-seal-open`, `demo-seal-ongoing`,
  `demo-seal-judging`. Bản nháp chỉ admin/BTC được thấy.
- Mỗi cuộc thi có 2 vòng, 2 track và 3 giải thưởng (giá trị minh họa bằng VND).
- 12 đội, 36 bản ghi thành viên, 62 vai trò theo cuộc thi và 1 audit `demo.seeded`.
  Bộ mẫu cũ đã được làm sạch có thêm 1 audit `demo.cleaned`.
- Cuộc thi mở đăng ký có 2 đội approved, 1 pending, 1 rejected có lý do.
  Đội pending có một yêu cầu vào đội đang chờ duyệt. Hai cuộc thi còn lại mỗi
  cuộc có 4 đội approved; đội 2–4 người, thực tế mỗi đội có 3 bản ghi thành viên.
- Lịch tính từ thời điểm seed: open bắt đầu sau 10 ngày, đóng đăng ký sau 9 ngày;
  ongoing đã bắt đầu 2 ngày; judging đã kết thúc 5 ngày. Chạy lại không kéo dài lịch.
- Tên cuộc thi và mô tả theo nội dung, không gắn trạng thái vào tên. Thời điểm tạo
  tài khoản trước khi đăng ký/gia nhập; cuộc thi được tạo trước khi cấp vai trò và lập đội.
- Đội approved có repo tham chiếu công khai: Microsoft Generative AI for Beginners,
  FastAPI Full Stack Template, Vercel Next Learn và Streamlit Hello. Đây là tài liệu/
  mã nguồn mẫu của chủ sở hữu tương ứng, **không phải sản phẩm do đội demo sở hữu**.
  Các URL đã được kiểm tra qua GitHub API ngày 2026-10-30; không chứng nhận luồng
  kiểm tra repo bằng GITHUB_TOKEN của ứng dụng. Đội pending/rejected chưa có repo.
  Seed không gọi GitHub, gửi email hoặc tạo thông báo giả.

Các trạng thái và lịch sử trên là fixture demo được thêm trực tiếp vào DB,
không phải bằng chứng đã chạy hết luồng vận hành cuộc thi. Không tạo closed,
bài nộp, điểm, leaderboard, commit hay AI review vì backend Phase 3–6 chưa có.

## Kiểm tra và nối FE

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_seed_demo.py -q
```

Dùng API hiện có, không đổi contract:

1. Guest: `GET /api/v1/events`, chi tiết theo `/events/by-slug/{slug}`, rounds,
   tracks, prizes và `/events/{id}/teams/public`.
2. Đăng nhập tài khoản demo qua `/api/v1/auth/login`, dùng Bearer access token.
3. BTC xem registrations/roles/teams; student xem `/me/events` và đội của mình;
   admin xem danh sách tổng cùng audit. Judge/mentor mới có role, chưa có assignment.
4. Nếu giao diện vẫn hiển thị mock, FE cần nối các endpoint trên; seed không thay
   đổi mã frontend hoặc tự biến mock thành dữ liệu từ DB.

Trạng thái FE: [ ]
