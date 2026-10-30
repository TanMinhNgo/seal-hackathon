# SEAL – Hệ thống thiết kế "Sổ phác thảo"

Bản xem trước: canvas Claude Design (5 màn: Trang chủ, Bảng xếp hạng, Đội của tôi, Giám khảo, Mentor).
Token và utility nằm trong `frontend/src/app/globals.css`; component dùng chung trong `frontend/src/components/ui/`.

## 1. Tinh thần

Giao diện như một trang sổ phác thảo: nền giấy trắng, nét mực đen, sticker màu, doodle vẽ tay. "Sống động" đến từ dữ liệu thật (đồng hồ đếm ngược, commit mới, đổi hạng) và vài chuyển động có mục đích, không từ trang trí thừa.

- Thí sinh sát hạn cần **tự tin**: biết còn bao lâu, đã nộp chưa.
- Giám khảo, mentor, BTC cần **rõ ràng**: bảng dễ đọc, hành động chính nổi bật.

## 2. Màu (class Tailwind)

| Token | Hex | Dùng cho |
| --- | --- | --- |
| `paper` | `#FFFFFF` | Nền trang, thẻ |
| `ink` | `#0D0D0D` | Chữ, viền, bóng cứng, nút chính |
| `cream` | `#FFF8E0` | Vùng nhấn nhẹ, mục đang chọn |
| `warm` | `#F7F5F0` | Vùng phụ, khối AI tham khảo |
| `line` | `#E4E1DA` | Đường kẻ nét đứt |
| `muted` | `#555555` | Chữ phụ |
| `orange` | `#FF6B2C` | Nhấn chính: CTA, "Đang thi", lỗi nghiêm trọng, gờ nút chính |
| `sun` | `#FFD23F` | "Đang chấm", "Đạt", "Cần sửa", cảnh báo < 1 giờ |
| `sky` | `#8FDCFF` | Sticker trang trí, giải Nhì |
| `rose` | `#FFB8C6` | "Cần cải thiện", giải Ba |
| `mint` | `#B8F0A0` | "Mở đăng ký", "Tốt", "Ổn", đã giải quyết |
| `plus` / `minus` | `#1E7A34` / `#B4232C` | Số dòng thêm / xóa trong diff |

Không truyền thông tin chỉ bằng màu: mọi nhãn đều có chữ, mũi tên hạng có chữ cho trình đọc màn hình.

## 3. Chữ

- **Be Vietnam Pro** (`font-sans`): toàn bộ giao diện, tiêu đề 900 với tracking âm (−0.03 đến −0.07em).
- **Lora nghiêng** (`font-serif italic`): câu dẫn, chú thích cảm xúc ("Đánh dấu lịch đi").
- **JetBrains Mono** (`font-mono`): số, điểm, đồng hồ, sha, đường dẫn file; luôn `tabular-nums` cho số thay đổi.
- Font tải qua `next/font/google` với subset `vietnamese`.

## 4. Thành phần nền

| Utility / component | Mô tả |
| --- | --- |
| `sketch` | Thẻ viền mực 2px, bo 24px, bóng cứng 6px |
| `btn` + `buttonClass()` | Nút pill có gờ dưới; nhấn xuống lún 2px; hover nghiêng nhẹ (chỉ thiết bị có chuột) |
| `chip` | Nhãn nhỏ viền mực |
| `lift` | Thẻ nổi lên khi hover |
| `Doodle` | Sao, sét, lửa, tim, lấp lánh, máy bay giấy (cùng bộ với footer) |
| `EventStatusBadge` | Nhãn trạng thái cuộc thi |
| `useSecondsLeft`, `InlineCountdown` | Đồng hồ đếm ngược, render "--" tới khi chạy ở client |
| `DoodleCrewFooter` | Footer có nhân vật vẽ tay trên chữ SEAL (trang chủ) |

## 5. Chuyển động

- `pull`: chữ kéo lên từng chữ (20px → 0, 600ms, trễ 80ms/chữ) – hero.
- `drift`: doodle trôi chậm trong hero.
- `pop-in`: mục mới (góp ý vừa gửi) xuất hiện.
- Nút phản hồi lúc nhấn xuống, không đợi nhả.
- Không animate bảng dữ liệu dày và thao tác bàn phím.
- `prefers-reduced-motion`: tắt toàn bộ animation, giữ phản hồi màu.

## 6. Màn hình

| Route | Điểm chính |
| --- | --- |
| `/` | Hero kiểu WordsPullUp + nav tab treo; lịch trình, thể lệ, giải thưởng, đăng ký, người đồng hành, nhà tài trợ |
| `/events/[slug]/results` | Bục top 3, bảng điểm theo tiêu chí, lọc vòng/track, đánh dấu đồng hạng |
| `/events/[slug]/my-team` | Đồng hồ đổi màu theo mức gấp, nộp bài có tiến độ, timeline commit, thẻ mentor + hỏi mentor |
| `/judge` | Chấm rubric, Bài nộp, xung đột của tôi (Phase 4); Commit → file → diff thật (Phase 5), chú thích AI theo file/dòng có coverage (Phase 6). Không giả lập đánh giá function khi API chưa có dữ liệu |
| `/mentor` | Đội được giao + cảnh báo, câu hỏi từ đội, góp ý gắn commit, checklist tiến độ |

Dữ liệu hiện là mẫu trong `src/features/*/mock.ts` và `content.ts`, đánh dấu `shortcut:` chỗ cần nối API.

### Luồng cần hoàn thiện theo vai trò

- `/dashboard`: `/me/events` (Phase 2), hiển thị đúng role và đội của từng event; không dùng ID role như dữ liệu giới thiệu cuộc thi.
- Đội của tôi: review_note, trạng thái pending/active, hạn mã mời và đóng băng đội (Phase 2); biên nhận version/server time/SHA (Phase 3); câu hỏi/đáp và góp ý/tiến độ mentor (Phase 4).
- `/mentor`: danh sách đội và bài nộp được giao, câu hỏi chưa giải quyết, note kind=progress (Phase 4); commit/AI bổ sung ở Phase 5–6. Không có typing/presence/chat.
- BTC: màn đăng ký/chưa có đội (Phase 2), phân công và thu hồi, chọn đội qua vòng, thiếu judge, sửa kết quả bằng thu hồi công bố rồi công bố revision mới (Phase 4), lịch sử announcement và delivery (Phase 7).
- `/admin`: system overview chờ API; hồ sơ cuộc thi chỉ đọc theo từng phase. Điểm chưa khóa không được hiện qua tab, export hoặc dữ liệu ẩn của trang.
- Guest: thông tin/rubric/announcement public/kết quả công bố; ẩn email và thông tin riêng của thành viên. Khi kết quả bị thu hồi phải bỏ cache đang hiển thị.

Các dòng này là yêu cầu thiết kế cần nối theo hợp đồng phase; không thay đổi trạng thái hoàn thành FE. Ma trận đánh giá và thứ tự ưu tiên: [ROLE-REVIEW.md](ROLE-REVIEW.md).

## 7. Kiểm tra trước khi xong một màn

- [ ] Dùng được bằng bàn phím, focus thấy rõ (viền nét đứt).
- [ ] Đúng ở 360px, 768px, 1280px; không cuộn ngang trang (bảng rộng cuộn trong hộp).
- [ ] Bật reduced motion vẫn dùng tốt.
- [ ] Thử dữ liệu xấu: tên đội dài, danh sách rỗng, tiếng Việt có dấu (skill `break-ui`).
