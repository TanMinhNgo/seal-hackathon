# SEAL – Software Engineering Hackathon Management System

Oct 28, 2026 · @Ngo Minh Tan

## 1. Mô tả đề tài

**Tên tiếng Việt:** Hệ thống quản lý cuộc thi SEAL Hackathon ngành Kỹ thuật Phần mềm

**Tên tiếng Anh:** SEAL – Software Engineering Hackathon Management System

SEAL là nền tảng web tập trung, quản lý trọn vòng đời một cuộc thi hackathon: từ mở đăng ký, lập đội, nộp bài, chấm điểm đến công bố kết quả.

**Bối cảnh.** Hackathon là hoạt động học thuật quan trọng của ngành Kỹ thuật Phần mềm. Nó giúp sinh viên áp dụng kiến thức vào bài toán thực tế trong thời gian ngắn.

**Vấn đề.** Các cuộc thi thường được vận hành bằng nhiều công cụ rời rạc như Google Form, Excel, email và Drive. Cách làm này gây ra các hạn chế sau:

- Dữ liệu đăng ký, đội thi và bài nộp nằm ở nhiều nơi nên khó đối soát.
- Chấm điểm thủ công dễ sai sót, khó minh bạch và khó tổng hợp khi có nhiều giám khảo.
- Hệ thống không tự kiểm soát hạn nộp, số lượng thành viên hay xung đột lợi ích giữa giám khảo và đội thi.
- Thông báo đến thí sinh chậm và không nhất quán.
- Không lưu được lịch sử để thống kê và cải thiện các mùa thi sau.

**Giải pháp.** SEAL số hóa toàn bộ quy trình trên một hệ thống duy nhất, phân quyền theo vai trò (RBAC):

- Chấm điểm theo rubric có trọng số.
- Bảng xếp hạng tự động.
- Thông báo qua email và trong ứng dụng.
- Báo cáo thống kê cho ban tổ chức.

## 2. Mục tiêu và phạm vi

Mục tiêu cốt lõi: một cuộc thi có thể vận hành từ đầu đến cuối trên SEAL mà không cần công cụ ngoài để quản lý đăng ký, nộp bài hay chấm điểm.

### 2.1 Mục tiêu nghiệp vụ

1. Tập trung dữ liệu: cuộc thi, đội, thành viên, bài nộp và điểm số nằm trong một hệ thống.
2. Minh bạch chấm điểm: rubric, trọng số và cách tổng hợp điểm được công khai. Mọi thay đổi điểm đều được ghi log.
3. Tự động hóa: kiểm soát hạn nộp, giới hạn thành viên, phân công giám khảo, gửi thông báo và tính bảng xếp hạng.
4. Giảm tải cho ban tổ chức: theo dõi tiến độ và xuất báo cáo trên dashboard.

### 2.2 Mục tiêu kỹ thuật

1. Phân quyền chặt theo vai trò (RBAC). Mọi kiểm tra quyền thực hiện ở phía server.
2. Chịu được tải cao điểm, khi nhiều đội nộp bài sát hạn chót.
3. Kiến trúc module rõ ràng, dễ mở rộng thêm loại cuộc thi hoặc vòng thi.
4. Triển khai bằng Docker, có môi trường dev, staging và production.

### 2.3 Phạm vi (in scope)

- Quản lý cuộc thi: thông tin, thể lệ, mốc thời gian, vòng thi, track/chủ đề, giải thưởng.
- Đăng ký tài khoản; đăng ký tham gia theo cá nhân hoặc theo đội.
- Quản lý đội: tạo đội, mời và duyệt thành viên, giới hạn số người.
- Nộp bài: link repo, link demo, slide, video; cho phép nộp lại trước hạn và lưu phiên bản; khai báo repo GitHub của đội.
- Chấm điểm theo rubric nhiều tiêu chí; phân công giám khảo; khai báo xung đột lợi ích. AI đánh giá chất lượng code theo từng lượt commit, phân loại tốt/chưa tốt, phát hiện lỗi; kết quả là dữ liệu tham khảo cho giám khảo.
- Theo dõi tiến độ: trong thời gian thi, cứ 30 phút hệ thống tự đồng bộ commit từ repo của từng đội. Bảng xếp hạng và công bố kết quả theo vòng.
- Thông báo qua email và trong ứng dụng.
- Dashboard thống kê và xuất báo cáo (Excel/PDF).
- Quản trị người dùng, vai trò và nhật ký hệ thống (audit log).
- Mentor: phân công theo đội, góp ý/ghi nhận tiến độ và hỏi đáp bất đồng bộ; không chat realtime. Cuộc thi nhiều vòng có danh sách đội đủ điều kiện vòng tiếp theo, bài nộp cố định SHA và quy trình sửa/công bố lại kết quả có audit.

Rà soát chức năng theo vai trò và thứ tự hoàn thiện: [ROLE-REVIEW.md](ROLE-REVIEW.md). Hợp đồng API và checklist triển khai nằm trong [PHASES.md](PHASES.md) và `phases/`; mục được bổ sung vào tài liệu chưa có nghĩa đã được lập trình hoặc kiểm chứng runtime.

### 2.4 Ngoài phạm vi (out of scope)

- Thanh toán lệ phí hoặc chi trả giải thưởng trực tuyến.
- Livestream, video call hay chat realtime giữa các đội (dùng công cụ ngoài như Discord, Meet).
- Build, chạy test hoặc thực thi code của đội trong sandbox. AI chỉ đọc diff và mã nguồn, không chạy code. Có thể làm ở hướng phát triển.
- Ứng dụng mobile native; hệ thống chỉ cần responsive trên trình duyệt di động.
- Đăng nhập SSO với hệ thống của trường. Có thể làm ở hướng phát triển.

## 3. Actor và chức năng

Hệ thống có 6 nhóm actor (Guest, Participant, Mentor, Judge, Organizer, Admin) và 4 hệ thống ngoài. Leader là quyền bổ sung của Participant trên đội, không phải role riêng trong DB. Một tài khoản có thể có vai trò khác nhau ở các cuộc thi; các tổ hợp trong cùng cuộc thi phải tuân thủ quy tắc xung đột lợi ích dưới đây.

### 3.1 Danh sách actor

| Actor | Mô tả | Chức năng chính |
| --- | --- | --- |
| Khách (Guest) | Người chưa đăng nhập | Xem danh sách và thông tin cuộc thi, thể lệ, kết quả đã công bố; đăng ký tài khoản |
| Thí sinh (Participant) | Sinh viên tham gia cuộc thi | Đăng nhập, cập nhật hồ sơ; dashboard cuộc thi; đăng ký/rút khi chưa có đội và còn hạn; tạo hoặc tham gia đội; xem lịch, thông báo, góp ý và hỏi mentor; xem điểm và nhận xét sau công bố |
| Trưởng nhóm (Team Leader) | Thí sinh tạo đội; kế thừa quyền Thí sinh | Mời, duyệt, xóa thành viên; chọn track/chủ đề; nộp và cập nhật bài trước hạn; chuyển quyền trưởng nhóm |
| Mentor | Giảng viên hoặc chuyên gia hỗ trợ đội | Xem đội/bài nộp/commit được phân công; góp ý, trả lời câu hỏi bất đồng bộ, ghi nhận tiến độ; không chấm đội từng hỗ trợ |
| Giám khảo (Judge) | Người chấm điểm | Khai báo xung đột lợi ích; xem bài được phân công; xem báo cáo AI về chất lượng code của đội; chấm theo rubric và ghi nhận xét; lưu nháp, rồi xác nhận điểm |
| Ban tổ chức (Organizer) | Người vận hành cuộc thi được Admin giao | Cấu hình vòng thi, track, mốc thời gian, rubric; xem đăng ký, duyệt đội; phân công/thu hồi giám khảo, mentor; chọn đội qua vòng; khóa/mở điểm; công bố/thu hồi/công bố lại có lý do; gửi thông báo, xem dashboard, xuất báo cáo |
| Quản trị viên (Admin) | Quản trị toàn hệ thống, tách khỏi nghiệp vụ cuộc thi | Quản lý tài khoản; tạo cuộc thi/chỉ định BTC, sửa metadata và lưu trữ; xem hồ sơ mọi cuộc thi (điểm chỉ sau khóa), health/dung lượng/audit/export; không tham gia đội, duyệt đội, chấm, mentor hoặc công bố thay BTC |
| Dịch vụ email (hệ thống ngoài) | SMTP hoặc dịch vụ gửi mail | Gửi email xác thực, lời mời vào đội, nhắc hạn, thông báo kết quả |
| Lưu trữ file (hệ thống ngoài) | Cloudinary (authenticated raw assets) | Lưu slide, video, tài liệu bài nộp; upload và download có chữ ký |
| GitHub API (hệ thống ngoài) | Nguồn dữ liệu commit của các đội | Cung cấp danh sách commit của repo đội theo chu kỳ 30 phút; gửi webhook push nếu có cấu hình |
| Dịch vụ AI (hệ thống ngoài) | LLM API (ví dụ OpenAI) | Nhận diff của commit kèm rubric; trả về điểm theo tiêu chí, danh sách lỗi và đánh giá tổng (JSON) |

### 3.2 Nhóm chức năng theo module

1. **Xác thực và tài khoản:** đăng ký, đăng nhập, xác thực email, quên mật khẩu, hồ sơ cá nhân, JWT + refresh token.
2. **Quản lý cuộc thi:** CRUD cuộc thi, vòng thi, track, timeline, thể lệ, giải thưởng; trạng thái Draft → Open → Ongoing → Judging → Closed.
3. **Đăng ký và đội thi:** đăng ký, tạo đội, lời mời bằng mã hoặc link, giới hạn số thành viên, duyệt đội.
4. **Nộp bài:** nộp và nộp lại có phiên bản, kiểm tra hạn ở server, upload file; đồng bộ commit GitHub định kỳ 30 phút và hiển thị timeline commit theo đội.
5. **Chấm điểm:** rubric nhiều tiêu chí có trọng số, phân công giám khảo, xung đột lợi ích, chuẩn hóa điểm, khóa điểm; báo cáo AI đánh giá code làm dữ liệu tham khảo.
6. **Xếp hạng và kết quả:** tính tổng điểm, xếp hạng theo vòng hoặc track, xử lý đồng điểm, công bố.
7. **Thông báo:** email và in-app, nhắc hạn tự động theo lịch.
8. **Báo cáo và quản trị:** dashboard, xuất Excel/PDF, quản lý người dùng, audit log.

### 3.3 Điểm dễ nhầm khi đặc tả

- Vai trò gắn theo từng cuộc thi chứ không gắn cố định cho tài khoản. Nên có bảng `event_roles(user_id, event_id, role)` bên cạnh vai trò hệ thống (Admin).
- Trưởng nhóm không phải một actor độc lập. Đó là Thí sinh có thêm quyền trên một đội cụ thể.
- Giám khảo không được xem điểm của giám khảo khác trước khi khóa điểm, để tránh bị ảnh hưởng.
- Admin không được tự trở thành BTC khi tạo cuộc thi. Chỉ Admin cấp/bỏ organizer; BTC cấp/bỏ judge/mentor; participant được cấp qua đăng ký. Không cấp role cho tài khoản khóa/chưa xác thực hoặc Admin.
- Cùng event: participant không kiêm organizer/judge/mentor; organizer không kiêm judge; judge không được phân công đội mình từng mentor. Role lịch sử không giúp Admin vượt ranh giới nghiệp vụ.
- Thành viên pending chưa có quyền dữ liệu nội bộ của đội. Public response không chứa email/phone/student_id/mã mời; mọi tài nguyên lồng nhau và file phải kiểm tra quyền với event/team gốc.

## 4. Kiến trúc hệ thống

Đề xuất kiến trúc **modular monolith**: một backend Python (FastAPI) chia theo module nghiệp vụ, kèm một worker xử lý việc nền. Với quy mô một cuộc thi cấp ngành, cách này đủ mạnh và đơn giản để triển khai. Khi cần, vẫn tách được thành microservice theo đúng ranh giới module.

&#91;embedded content: Kiến trúc tổng quan SEAL · client, API, dữ liệu, worker\]

Mọi request đi qua lớp dependency xác thực (JWT + RBAC theo cuộc thi) trước khi vào module. Các việc chậm như gửi email hay nhắc hạn được đẩy vào hàng đợi để API luôn phản hồi nhanh.

### 4.1 Công nghệ đề xuất

| Tầng | Công nghệ | Lý do chọn |
| --- | --- | --- |
| Frontend | Next.js, TypeScript, TanStack Query, Zustand, Tailwind | SSR cho trang công khai (cuộc thi, kết quả); TanStack Query quản lý cache dữ liệu server |
| Backend | FastAPI, Python 3.12, Pydantic v2 | Async nên gọi GitHub API và LLM hiệu quả; Pydantic validate request và ép schema JSON cho output AI; Depends() làm dependency injection; tự sinh OpenAPI docs; hệ sinh thái AI của Python mạnh |
| Database | PostgreSQL + SQLAlchemy 2.0 (async) + Alembic | Dữ liệu quan hệ chặt (đội, bài nộp, điểm); cần transaction và ràng buộc unique |
| Cache / Queue | Redis + Celery (Celery Beat chạy lịch 30 phút) | Cache bảng xếp hạng; job gửi email, nhắc hạn, tính lại điểm |
| Realtime | python-socketio (chạy chung ASGI app) | Cập nhật bảng xếp hạng và thông báo tức thời |
| Lưu trữ file | Cloudinary: signed POST FormData, authenticated raw; download URL ký có hạn | Client upload trực tiếp lên Cloudinary; khi chốt bài, API xác minh và đọc file kiểm tra trước khi lưu biên nhận |
| Triển khai | Docker Compose, Nginx, Ubuntu (VPS hoặc AWS EC2) | Một lệnh dựng toàn bộ hệ thống; dev và production giống nhau |

### 4.2 Tổ chức mã nguồn backend

Mỗi module theo cấu trúc `router → service (use case) → repository`. Repository bọc SQLAlchemy, nên service không phụ thuộc trực tiếp vào ORM và dễ viết unit test.

Cấu trúc thư mục đề xuất:

```
seal-backend/
├── app/
│   ├── main.py              # khởi tạo FastAPI, mount Socket.IO
│   ├── core/                # config, JWT, DB session, dependency RBAC
│   ├── modules/
│   │   ├── auth/            # router.py, service.py, repository.py, schemas.py, models.py
│   │   ├── events/
│   │   ├── teams/
│   │   ├── submissions/     # nộp bài + dữ liệu commit
│   │   ├── judging/         # rubric, chấm điểm, kết quả AI review
│   │   ├── ranking/
│   │   ├── notifications/
│   │   └── reports/
│   └── integrations/        # github_client.py, llm_client.py, mailer.py, storage.py (Cloudinary)
├── worker/
│   ├── celery_app.py        # cấu hình Celery + lịch Beat 30 phút
│   └── tasks/               # sync_commits.py, ai_review.py, send_email.py
├── alembic/                 # migration database
├── tests/
└── docker-compose.yml       # api, worker, beat, postgres, redis
```

Điểm dễ nhầm với stack Python:

- `schemas.py` (Pydantic: dữ liệu vào/ra API) và `models.py` (SQLAlchemy: bảng DB) là hai lớp khác nhau. Đừng trả thẳng model DB ra API.
- Celery task mặc định chạy đồng bộ. Trong task nên dùng client đồng bộ (`httpx.Client`, session SQLAlchemy sync), không gọi thẳng hàm `async` của API.
- Celery Beat chỉ được chạy **một** instance. Chạy nhiều bản thì lịch 30 phút sẽ bị kích hoạt trùng.
- Chạy API bằng Uvicorn/Gunicorn với nhiều worker thì Socket.IO cần Redis làm message queue, nếu không sự kiện realtime chỉ đến được client nối vào cùng một process.

### 4.3 Luồng chính

1. **Vòng đời cuộc thi:** Admin tạo cuộc thi và chỉ định BTC (Draft) → BTC cấu hình, mở đăng ký (Open) → thi (Ongoing) → tất cả vòng hết hạn nộp (Judging) → công bố các vòng, đóng (Closed). Mỗi vòng có lịch nhận/chấm và danh sách đội đủ điều kiện riêng; có thể chấm vòng trước khi event còn Ongoing để tổ chức vòng tiếp theo.
2. **Lập đội:** Thí sinh tạo đội và trở thành Trưởng nhóm → gửi mã mời → thành viên tham gia (server kiểm tra giới hạn số người và mỗi người chỉ thuộc một đội trong một cuộc thi) → BTC duyệt đội.
3. **Nộp bài:** client gọi `/uploads/presign` lấy `upload_url` và `fields` đã ký → POST FormData gồm nguyên `fields` + `file` lên Cloudinary → gửi metadata/file_keys và Idempotency-Key tới API nộp bài → API kiểm tra điều kiện vòng/hạn theo UTC server, chuyển asset authenticated raw sang ID bài nộp riêng, kiểm tra file và chốt SHA repo, trả biên nhận/version. Upload thành công chưa phải nộp bài thành công; bài tính điểm là bản cuối hợp lệ trước hạn, được cố định trong phân công chấm. File chỉ tải qua download URL ký có hạn từ API.
4. **Chấm điểm:** BTC phân công đủ giám khảo mỗi đội (loại xung đột và mentor của đội) → chấm nháp/xác nhận → BTC khóa khi đủ bài chấm hợp lệ → tính điểm, xếp hạng. Đội không nộp không có hạng; vòng sau cần BTC xác nhận danh sách từ kết quả vòng trước.
5. **Công bố:** BTC công bố → worker gửi email kết quả → bảng xếp hạng công khai cập nhật qua WebSocket.
6. **Sửa kết quả:** khi event chưa Closed, BTC thu hồi công bố có lý do → mở khóa/mở bài chấm → judge sửa/xác nhận → khóa và công bố revision mới, giữ lịch sử/audit và thông báo thay đổi.
7. **Hỗ trợ mentor:** BTC phân công → đội đặt câu hỏi → mentor đọc bài/tiến độ, trả lời hoặc gửi note → đội đánh dấu giải quyết. Gỡ phân công thu hồi quyền hiện tại, giữ hồ sơ góp ý.

### 4.4 Rủi ro kỹ thuật và cách xử lý

- **Nộp bài sát hạn chót:** hạn được kiểm tra ở server, không tin giờ của client; client upload trực tiếp lên Cloudinary bằng signed POST. API vẫn đọc/kiểm tra file khi chốt và kiểm tra hạn lần nữa; cần dành thời gian cho bước nộp bài sau upload, không cộng thêm thời gian vì upload đã bắt đầu trước hạn.
- **Nộp trùng khi bấm nhiều lần:** dùng idempotency key hoặc ràng buộc unique `(team_id, round_id, version)`.
- **Sai lệch điểm:** điểm đã xác nhận chỉ BTC mở lại được; mọi thay đổi đều ghi vào audit log.
- **Lộ quyền:** kiểm tra quyền theo cuộc thi ở mọi endpoint. Ví dụ: Giám khảo chỉ đọc được bài được phân công cho mình.

### 4.5 Đồng bộ commit tự động (30 phút/lần)

Trong lúc cuộc thi ở trạng thái Ongoing, worker tự chạy mỗi 30 phút để lấy commit mới từ repo GitHub của từng đội. BTC, mentor và giám khảo nhờ đó theo dõi được tiến độ thật của đội mà không cần hỏi.

**Cách hoạt động**

1. Khi lập đội hoặc trước giờ thi, Trưởng nhóm khai báo repo GitHub. Repo bắt buộc public trong suốt thời gian thi. Hệ thống kiểm tra repo truy cập được ngay lúc khai báo, và cảnh báo BTC nếu repo bị chuyển sang private hoặc bị xóa.
2. Một Celery Beat chạy job điều phối mỗi phút, chọn cuộc thi Ongoing đến hạn theo sync_interval_minutes (mặc định 30). Chỉ một scheduler và không để các job cùng đội chồng nhau.
3. Job điều phối tách ra mỗi đội một job con (fan-out), giới hạn số job chạy song song để không vượt hạn mức GitHub API.
4. Mỗi job con đọc lịch sử branch có phân trang, lưu head SHA và đối chiếu commit mới; không dùng riêng since=last_synced_at để bỏ qua push muộn. Unique `(team_id, sha)` chống trùng; SHA có thể xuất hiện ở nhiều đội mà vẫn phải lưu hồ sơ riêng.
5. Job cập nhật `last_synced_at` và trạng thái đồng bộ của đội, rồi đẩy sự kiện qua WebSocket để dashboard BTC tự cập nhật.

**Dữ liệu lưu cho mỗi commit:** `team_id`, `sha`, `author`, `message`, `committed_at`, `first_seen_at`, `branch`, số dòng thêm/xóa (nếu lấy), baseline/in_event_window và coverage của diff. Lượt đầu nhập lịch sử cũ không có nghĩa mọi commit được viết trong giờ thi.

**Hiển thị:** timeline commit theo đội; tổng số commit; thời điểm commit cuối; cảnh báo đội không có commit sau N giờ (BTC cấu hình N).

**Điểm dễ nhầm**

- `committed_at` do máy của thí sinh ghi và có thể bị sửa. Muốn biết commit có thật sự xuất hiện trong giờ thi hay không, hãy dựa vào `first_seen_at`, tức thời điểm SEAL thấy commit lần đầu. Vì vậy chu kỳ 30 phút cũng chính là sai số của mốc thời gian này.
- Force push có thể xóa commit khỏi repo. Giữ lại bản ghi đã lưu và đánh dấu `removed` thay vì xóa.
- Lỗi từng repo (đổi tên, chuyển private, token hết hạn) phải được cô lập: chỉ job của đội đó thất bại và retry, kèm cảnh báo cho BTC, không làm dừng cả lượt đồng bộ.
- Hạn mức GitHub API tính theo giờ. Với 100 đội, mỗi giờ chỉ cần khoảng 200 request, nhưng vẫn phải gọi API kèm token của hệ thống: không có token, GitHub chỉ cho khoảng 60 request/giờ cho mỗi IP.
- Chu kỳ 30 phút nên là cấu hình theo từng cuộc thi, không hard-code.

**Hướng mở rộng:** dùng thêm webhook `push` của GitHub để cập nhật gần như tức thời. Cron 30 phút khi đó giữ vai trò lưới an toàn, bù những lần webhook bị lỡ.

### 4.6 AI đánh giá chất lượng code theo commit

Sau mỗi lượt đồng bộ, commit mới của từng đội được đưa vào hàng đợi `ai-review`. AI chấm theo tiêu chí, phân loại commit, liệt kê lỗi và tổng hợp thành báo cáo theo đội. **Điểm AI chỉ để giám khảo tham khảo, không thay thế rubric chấm chính thức.**

**Pipeline xử lý**

1. Job đồng bộ lưu commit mới, rồi đẩy job `ai-review` vào một queue riêng. Queue này đặt concurrency thấp để kiểm soát chi phí và rate limit.
2. Lấy diff qua GitHub API: `GET /repos/{owner}/{repo}/commits/{sha}` cho từng commit, hoặc `GET /repos/{owner}/{repo}/compare/{base}...{head}` để gộp mọi commit của một lượt 30 phút.
3. Lọc diff: bỏ lock file, thư mục build, `node_modules`, ảnh, file sinh tự động; cắt bớt diff quá lớn. Gửi kèm cây thư mục và README tóm tắt để AI có ngữ cảnh.
4. Tùy chọn: chạy linter hoặc Semgrep trên các file thay đổi (chỉ đọc file, không thực thi code). Cách này cho ra lỗi chắc chắn để AI giải thích và xếp mức ưu tiên.
5. Gọi LLM với rubric, diff và commit message; ép trả JSON theo schema (structured output), đặt temperature thấp.
6. Validate JSON, lưu vào `commit_reviews`, cập nhật điểm tổng hợp của đội, đẩy dữ liệu lên dashboard qua WebSocket.

**Tiêu chí đánh giá đề xuất**

| Tiêu chí | AI kiểm tra gì |
| --- | --- |
| Lỗi và tính đúng đắn | Bug logic, null/undefined, xử lý bất đồng bộ sai, điều kiện biên |
| Bảo mật | Secret/API key hard-code, SQL injection, XSS, thiếu kiểm tra quyền |
| Clean code | Đặt tên, hàm quá dài, code lặp, độ dễ đọc |
| Cấu trúc | Tách lớp/module hợp lý, phụ thuộc chéo, vi phạm kiến trúc đã chọn |
| Xử lý lỗi | Try/catch, validate input, log lỗi |
| Kiểm thử | Có thêm hoặc cập nhật test cho phần code thay đổi |
| Thói quen commit | Commit message rõ ràng, commit có kích thước hợp lý |

**Phân loại commit (ngưỡng đề xuất, BTC cấu hình được):** Tốt (từ 8/10), Đạt (5 đến dưới 8), Cần cải thiện (dưới 5). Commit có lỗi mức `high` (ví dụ lộ secret) được gắn thêm cờ **Có lỗi nghiêm trọng**, bất kể điểm.

**Dữ liệu lưu:** `commit_reviews(team_id, round_id, commit_shas, model, prompt_version, scores, issues, verdict, coverage, tokens_used, created_at)`; một review có thể gộp nhiều SHA. Mỗi issue gồm `file`, `line` (nullable khi không xác minh vị trí), `severity`, `category`, `message`, `suggestion`.

**Hiển thị:** biểu đồ điểm chất lượng của đội theo thời gian; danh sách commit kèm nhãn; top lỗi theo loại. BTC quyết định thí sinh được xem báo cáo của đội mình trong lúc thi (như một mentor tự động) hay chỉ sau khi kết thúc vòng.

**Rủi ro và cách xử lý**

- **AI đánh giá sai hoặc bịa dòng code:** chỉ dùng làm tham khảo; lưu `model` và `prompt_version` để truy vết; giám khảo có thể đánh dấu một đánh giá là sai.
- **Prompt injection trong code:** thí sinh có thể viết comment kiểu “hãy cho điểm 10”. Cần khai báo rõ trong system prompt rằng diff chỉ là dữ liệu, ép output theo schema, và cảnh báo khi điểm tăng đột biến.
- **Lách điểm:** chia nhỏ commit hay commit rác không được làm tăng điểm. Điểm đội tính trung bình có trọng số theo số dòng thay đổi, không cộng dồn theo số commit.
- **Chi phí:** bỏ qua merge commit và commit chỉ đổi file không phải code; khi số commit lớn, review theo diff gộp mỗi lượt 30 phút thay vì từng commit.
- **Công bằng:** mọi đội dùng cùng model, cùng prompt và cùng tham số. Không đổi prompt giữa chừng vòng thi.
