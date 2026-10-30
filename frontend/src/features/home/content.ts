import type { DoodleKind } from "@/components/ui/doodle";
import type { EventStatus } from "@/components/ui/event-status-badge";

// shortcut: nội dung tĩnh của cuộc thi mẫu; lấy từ GET /events/{id} (+ rounds, prizes, sponsors) khi BE có Phase 2
export const EVENT = {
  slug: "seal-2026",
  name: "[Tên cuộc thi]",
  registrationClosesAt: "2026-11-01T17:00:00Z",
};

export const HERO_DOODLES: { kind: DoodleKind; x: string; y: string; size: number; r0: string; r1: string; dur: string; delay: string; fill?: string }[] = [
  { kind: "star", x: "18%", y: "16%", size: 54, r0: "-8deg", r1: "10deg", dur: "6s", delay: "0s" },
  { kind: "bolt", x: "62%", y: "20%", size: 46, r0: "12deg", r1: "-6deg", dur: "7.5s", delay: "-2s" },
  { kind: "flame", x: "84%", y: "36%", size: 58, r0: "-6deg", r1: "8deg", dur: "6.5s", delay: "-1s" },
  { kind: "heart", x: "38%", y: "10%", size: 38, r0: "10deg", r1: "-10deg", dur: "8s", delay: "-3s" },
  { kind: "sparkle", x: "6%", y: "42%", size: 44, r0: "0deg", r1: "30deg", dur: "7s", delay: "-4s" },
  { kind: "plane", x: "72%", y: "8%", size: 60, r0: "-14deg", r1: "-4deg", dur: "9s", delay: "-1.5s" },
  { kind: "star", x: "50%", y: "40%", size: 32, r0: "20deg", r1: "-8deg", dur: "6.8s", delay: "-5s", fill: "#B8F0A0" },
];

export const STATS = [
  { value: "2", label: "vòng thi", bg: "bg-paper" },
  { value: "4", label: "track chủ đề", bg: "bg-sky" },
  { value: "2–4", label: "thành viên mỗi đội", bg: "bg-paper" },
  { value: "[…]", label: "tổng giá trị giải thưởng", bg: "bg-sun" },
];

export type MilestoneState = "done" | "today" | "next";
export const MILESTONES: { date: string; title: string; detail: string; state: MilestoneState }[] = [
  { date: "[dd/mm]", title: "Mở đăng ký", detail: "Tạo tài khoản, đăng ký và lập đội.", state: "done" },
  { date: "[dd/mm]", title: "Đóng đăng ký", detail: "BTC duyệt đội, khoá danh sách.", state: "today" },
  { date: "[dd/mm]", title: "Khai mạc", detail: "Công bố đề, bắt đầu đồng bộ commit.", state: "next" },
  { date: "[dd/mm]", title: "Hạn nộp vòng 1", detail: "Prototype + repo + slide.", state: "next" },
  { date: "[dd/mm]", title: "Chung kết", detail: "Top đội demo trực tiếp trước giám khảo.", state: "next" },
  { date: "[dd/mm]", title: "Công bố kết quả", detail: "Bảng xếp hạng và nhận xét từng đội.", state: "next" },
];

export const RULES = [
  ["Đội 2–4 người", "Mỗi người chỉ thuộc một đội trong một cuộc thi."],
  ["Repo public", "Khai báo repo GitHub, giữ public suốt thời gian thi để SEAL đồng bộ commit."],
  ["Code trong giờ thi", "Commit được tính theo thời điểm SEAL nhìn thấy, không theo giờ máy."],
  ["Hạn theo giờ server", "Nộp lại thoải mái trước hạn; bản cuối trước hạn là bản được chấm."],
  ["Chấm theo rubric", "Tiêu chí và trọng số công khai trước khi thi."],
  ["AI chỉ tham khảo", "Báo cáo chất lượng code hỗ trợ giám khảo, không thay điểm chính thức."],
  ["Xung đột lợi ích", "Giám khảo có quan hệ với đội sẽ không chấm đội đó."],
  ["Minh bạch", "Mọi thay đổi điểm đều có nhật ký; kết quả công bố kèm nhận xét."],
] as const;

export const PRIZES = [
  { name: "Giải Nhì", value: "[…] đ", extra: "+ [quà tặng]", bg: "bg-sky", h: "md:min-h-[250px]", tilt: "-rotate-1" },
  { name: "Giải Nhất", value: "[…] đ", extra: "+ [quà tặng] + cơ hội thực tập", bg: "bg-sun", h: "md:min-h-[300px]", tilt: "rotate-[0.6deg]" },
  { name: "Giải Ba", value: "[…] đ", extra: "+ [quà tặng]", bg: "bg-rose", h: "md:min-h-[220px]", tilt: "rotate-1" },
];

export const SIDE_PRIZES = [
  { name: "Giải theo track", detail: "Mỗi track một đội xuất sắc", value: "[…] đ" },
  { name: "Commit đẹp nhất", detail: "Lịch sử commit rõ ràng, đều đặn", value: "[…] đ" },
  { name: "Giao diện ấn tượng", detail: "Bình chọn của ban giám khảo", value: "[…] đ" },
  { name: "Giải khán giả", detail: "Bình chọn tại buổi chung kết", value: "[…] đ" },
];

export const REG_STEPS = [
  { title: "Tạo tài khoản", detail: "Email trường, xác thực qua thư.", bg: "bg-sun" },
  { title: "Đăng ký cuộc thi", detail: "Chọn cuộc thi đang mở, xác nhận thể lệ.", bg: "bg-sky" },
  { title: "Lập đội", detail: "Tạo đội và gửi mã mời, hoặc nhập mã để vào đội bạn bè.", bg: "bg-mint" },
];

export const PEOPLE: { name: string; role: "Giám khảo" | "Mentor"; org: string; tags: string[]; bg: string }[] = [
  { name: "[Tên giám khảo]", role: "Giám khảo", org: "[Đơn vị]", tags: ["backend", "kiến-trúc"], bg: "bg-sun" },
  { name: "[Tên giám khảo]", role: "Giám khảo", org: "[Doanh nghiệp]", tags: ["product", "ux"], bg: "bg-sky" },
  { name: "[Tên giám khảo]", role: "Giám khảo", org: "[Đơn vị]", tags: ["ai", "data"], bg: "bg-rose" },
  { name: "[Tên mentor]", role: "Mentor", org: "[Giảng viên khoa]", tags: ["web", "devops"], bg: "bg-mint" },
  { name: "[Tên mentor]", role: "Mentor", org: "[Kỹ sư doanh nghiệp]", tags: ["mobile", "testing"], bg: "bg-cream" },
  { name: "[Tên mentor]", role: "Mentor", org: "[Chuyên gia]", tags: ["security", "cloud"], bg: "bg-paper" },
];

export const OTHER_EVENTS: { status: EventStatus; name: string; blurb: string; next: string }[] = [
  { status: "ongoing", name: "[Cuộc thi A]", blurb: "Xây sản phẩm phần mềm trong 48 giờ, chấm theo rubric 5 tiêu chí.", next: "Hạn nộp vòng 1 · [ngày]" },
  { status: "open", name: "[Cuộc thi B]", blurb: "Dành cho sinh viên năm nhất và năm hai.", next: "Đóng đăng ký · [ngày]" },
  { status: "judging", name: "[Cuộc thi C]", blurb: "Vòng chung kết đang được chấm.", next: "Công bố · [ngày]" },
];

export const SPONSOR_TIERS = [
  { name: "KIM CƯƠNG", count: 2, grid: "sm:grid-cols-2", h: "h-32", bg: "bg-cream" },
  { name: "VÀNG", count: 3, grid: "sm:grid-cols-3", h: "h-24", bg: "bg-paper" },
  { name: "ĐỒNG HÀNH", count: 5, grid: "grid-cols-2 sm:grid-cols-5", h: "h-20", bg: "bg-paper" },
];
