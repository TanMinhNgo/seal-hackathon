# SEAL – Rà soát chức năng theo vai trò

Ngày rà soát: 2026-10-29. Phạm vi: toàn bộ `docs/`, đối chiếu ranh giới auth backend hiện có; không phải chứng nhận các chức năng đã chạy trên môi trường thật.

Các mục bổ sung dưới đây là yêu cầu được theo dõi theo từng phase; trạng thái triển khai mới nhất xem checklist và bàn giao trong file phase, không suy từ bảng đánh giá này. Hợp đồng chi tiết nằm trong file phase; checklist BE/FE mới đều để `[ ]`. Các kết quả kiểm tra cũ trong tài liệu được giữ như lịch sử.

## Đánh giá từng vai trò

| Vai trò | Tài liệu đã có | Khoảng trống và phần bổ sung | Phase |
| --- | --- | --- | --- |
| Guest | Danh sách, chi tiết cuộc thi, kết quả công khai | Tra cứu bằng slug cho route FE; rubric công khai khi mở đăng ký; không lộ draft qua rounds/tracks/prizes; thông báo công khai tách khỏi thông báo nội bộ | 2, 4, 7 |
| Participant | Tài khoản, đăng ký, vào đội, xem kết quả | Dashboard có thông tin cuộc thi thay vì chỉ UUID; xem/rút đăng ký khi chưa có đội; biết lý do đội bị từ chối; đọc góp ý, đặt câu hỏi cho mentor | 2, 4 |
| Team Leader | Mời, duyệt thành viên, chuyển leader, repo, nộp bài | Vòng đời mã mời; đóng băng đội khi bắt đầu thi; sửa đội đã duyệt phải duyệt lại; biên nhận bài nộp và snapshot commit; xử lý đội chỉ còn leader | 2, 3 |
| Mentor | Đội được phân công, ghi góp ý | Đang thiếu quyền GET góp ý của chính đội được giao; thiếu đọc bài nộp; thiếu API hỏi/đáp và ghi nhận tiến độ dù DESIGN đã vẽ; thiếu thu hồi/phân công lại | 3, 4 |
| Judge | Rubric, phân công, nháp/xác nhận, xung đột lợi ích, AI | Xem xung đột của mình; khai báo trước phân công mà không được đọc dữ liệu riêng của đội; xử lý xung đột phát sinh; sửa nháp đồng thời; cố định bài được chấm | 2, 4, 6 |
| Organizer | Vận hành vòng đời, đội, rubric, điểm, dashboard | Xem danh sách người đăng ký; phân công mentor đầy đủ GET/DELETE; chỉ định đội qua vòng sau; chặn khóa khi thiếu giám khảo; quy trình thu hồi công bố, sửa và công bố lại; lịch sử thông báo | 2, 4, 7 |
| Admin | Tài khoản, audit, hồ sơ toàn cuộc thi, lưu trữ | `/admin/system` mới là hợp đồng chờ BE; chặn vai trò nghiệp vụ ngay cả khi còn event_roles cũ; giới hạn trường được sửa; phân biệt worker/Beat và SMTP/inbox; kiểm tra phục hồi backup | 1, 2, 7 |

Mentor là vai trò thiếu luồng sử dụng hoàn chỉnh nhất. BTC có nhiều endpoint nhưng còn thiếu các bước xử lý ngoại lệ. Admin đã được mở rộng trong bản docs gần nhất; không cần trao thêm quyền chấm điểm hay vận hành đội.

## Quyết định nghiệp vụ

1. Admin tạo cuộc thi và chỉ định BTC; BTC cấu hình, vận hành cuộc thi được giao. Không thêm một luồng “BTC tạo cuộc thi” cạnh tranh với chính sách mới.
2. Role là quyền theo event; leader là quyền trên team. Cùng người có thể là thí sinh ở event A và judge ở event B. Trong cùng event, participant không kiêm organizer/judge/mentor; organizer không kiêm judge; mentor không chấm đội mình đang hoặc từng hỗ trợ. Admin không thực hiện nghiệp vụ cuộc thi dù còn bản ghi vai trò lịch sử.
3. Thông tin công khai dùng schema riêng. `UserBrief` có email chỉ dùng nội bộ; leaderboard, danh sách đội để khai báo xung đột và thông báo công khai không kèm email, phone, student_id, invite_code hay nhận xét chưa công bố.
4. Thành viên `pending` chỉ xem yêu cầu gia nhập của mình và thông tin đội cơ bản; chưa có quyền đọc bài nộp, mã mời, góp ý, AI hay upload. “Thành viên” trong các hợp đồng đọc dữ liệu riêng nghĩa là `active`.
5. Nộp bài tạo phiên bản bất biến và ghi SHA của repo tại thời điểm nộp. Chấm bài gắn đúng phiên bản, không tự chuyển khi có bản mới. Lịch sử commit là bằng chứng hỗ trợ; số commit, first_seen_at hay điểm AI không tự quyết định kết quả chính thức.
6. Hỏi/đáp mentor là trao đổi bất đồng bộ theo đội, không có chat, presence, typing hoặc video call. Ghi nhận tiến độ dùng mở rộng mentor note, không dựng module quản lý dự án mới.
7. Vòng có thể diễn ra trước khi event chuyển sang `judging`: kiểm tra giờ bắt đầu/hạn nộp và cờ vòng độc lập. `judging` toàn event nghĩa là tất cả vòng đã ngừng nhận bài; không được dùng nó làm điều kiện bắt buộc cho mọi lần chấm nếu còn vòng sau.
8. Một cuộc thi có nhiều vòng cần danh sách đội được thi vòng tiếp theo; kết quả công bố không tự cấp quyền nộp mọi vòng. BTC xác nhận danh sách trước khi vòng bắt đầu.
9. Sửa điểm sau công bố phải thu hồi công bố → mở khóa → mở bài chấm → xác nhận lại → khóa → công bố revision mới. Không sửa âm thầm hoặc cho Admin sửa điểm.

## Thứ tự triển khai

| Mức | Việc cần hoàn thành | Lý do |
| --- | --- | --- |
| Trước khi mở nghiệp vụ Phase 2 | Chính sách role, lọc dữ liệu, dashboard theo event, đăng ký/đội và giới hạn trạng thái | Tránh tự nâng quyền, lộ dữ liệu hoặc đội mất trưởng nhóm |
| Trong MVP Phase 3–4 | Biên nhận/snapshot bài nộp, chấm cố định phiên bản, đủ giám khảo, sửa công bố, quyền mentor và phân công | Cuộc thi phải chạy trọn vòng đời và khôi phục được khi thao tác sai |
| Hoàn thiện vai trò ở Phase 4 | Hỏi/đáp mentor, ghi tiến độ, danh sách đội qua vòng | Lấp chức năng đã xuất hiện trong đặc tả và thiết kế |
| Phase 5–6 | Khôi phục đồng bộ lỗi, diff thật, trạng thái AI, giới hạn chi phí, xử lý flag | Dữ liệu code không mất ngữ cảnh và AI không làm hỏng nghiệp vụ chính |
| Phase 7 trước production | Thông báo có lịch sử, phân quyền export/realtime, readiness, backup/restore, smoke test từng role | Vận hành được và phát hiện được lỗi ngoài bộ test |

Không bổ sung trong lượt này: thanh toán, chat realtime, chạy code đội thi, SSO, mobile native, diễn đàn công khai, marketplace mentor, chứng chỉ tự động hoặc hệ thống ticket tổng quát. Khiếu nại có SLA và quy trình kỷ luật riêng cần BTC xác định quy chế trước; MVP dùng quy trình sửa công bố có audit, không tự sáng tác quy chế giải quyết tranh chấp.

## Chỗ tài liệu đã được đồng bộ

- Đặc tả gốc: actor, phạm vi, vòng đời, đồng bộ commit; giữ nguyên các giới hạn ngoài phạm vi.
- `PHASES.md`: chính sách role và thứ tự ưu tiên; phase vẫn là nguồn hợp đồng API.
- Phase 1–7: API, giới hạn dữ liệu, checklist BE/FE và kiểm tra chấp nhận cho các bổ sung.
- `DESIGN.md`: màn mentor hỏi đáp/tiến độ và màn sửa kết quả được gắn phase cụ thể; chưa khẳng định FE đã nối API.
- Phase 3 bỏ tiêu chí Mailpit cũ: dự án dùng SMTP trực tiếp; local Compose vẫn chỉ là dịch vụ phụ trợ, không tự đổi cách chạy API/FE/worker.

## Cơ sở tham khảo

Các quyết định về vai trò, vòng thi và điểm là thiết kế riêng của SEAL từ docs hiện tại. Các nguồn bên ngoài dưới đây chỉ hỗ trợ cách triển khai kỹ thuật, không áp đặt quy chế cuộc thi:

- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): kiểm tra quyền ở mọi request và theo quan hệ với tài nguyên; dùng cho team, assignment, file, report và socket.
- [OWASP File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html): không tin Content-Type client, kiểm tra loại/kích thước/quyền truy cập và dùng tên file do server tạo. Kiểm tra cơ bản không chứng minh file sạch mã độc.
- [GitHub REST commits](https://docs.github.com/en/rest/commits/commits#compare-two-commits): compare có giới hạn danh sách file; diff nhị phân/lớn có thể không đầy đủ. Phải ghi coverage thay vì coi dữ liệu bị cắt là toàn bộ repo.
- [Celery workers](https://docs.celeryq.dev/en/stable/userguide/workers.html#remote-control), [Celery periodic tasks](https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html#introduction): ping kiểm tra worker; Beat là scheduler riêng, chỉ một instance/lịch, job có thể chồng nhau và cần chống chạy trùng.

## Kiểm tra chấp nhận chung

- [ ] Seed tối thiểu Guest, Admin, BTC, Judge, Mentor, Leader, member active/pending và người ngoài cuộc thi; kiểm tra cả luồng được phép và 403/404 theo tài nguyên.
- [ ] Kiểm tra cùng tài khoản có role khác nhau ở hai event; đổi event_id/team_id/round_id/assignment_id không đọc chéo dữ liệu.
- [ ] Gỡ role/phân công hoặc khóa tài khoản thì REST, file URL mới, export và socket ngừng cấp dữ liệu riêng. URL ký đã phát còn dùng đến hết TTL; TTL tải file tối đa 5 phút.
- [ ] Chạy demo ít nhất hai vòng, một đội bị loại, một xung đột lợi ích, một lần thay judge và một lần sửa kết quả đã công bố.
- [ ] Đánh dấu riêng bằng chứng unit/integration test, trình duyệt thật, SMTP/inbox, worker/provider và staging; không dùng checklist docs thay cho bằng chứng runtime.

Trạng thái FE: [ ]

Kiểm tra tài liệu trong lượt rà soát: đã kiểm tra link nội bộ, số cột bảng Markdown, code fence, bao phủ vai trò và các điểm mâu thuẫn được sửa. Không chỉnh backend/frontend hoặc chạy lại kiểm thử ứng dụng cho thay đổi chỉ ở docs; các chức năng mới cần được triển khai và kiểm chứng theo phase.
