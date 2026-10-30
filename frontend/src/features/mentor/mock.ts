// shortcut: dữ liệu mẫu; thay bằng GET /me/mentoring, /teams/{id}/mentor-notes, câu hỏi đội và checklist (bổ sung hợp đồng Phase 4)

export type NoteKind = "feedback" | "answer" | "progress";

export interface MentorNote {
  id: string;
  who: string;
  kind: NoteKind;
  anchor: string;
  text: string;
  time: string;
  replies: { who: string; time: string; text: string }[];
}
export interface TeamQuestion {
  id: string;
  from: string;
  time: string;
  text: string;
  answer?: string;
}
export interface MentoredTeam {
  name: string;
  track: string;
  repo: string;
  lastCommit: string;
  commits: number;
  ai: string;
  alert?: { text: string; bg: string };
  members: { name: string; bg: string }[];
  bars: number[];
  recent: { sha: string; time: string; msg: string; v: string; bg: string; issue?: string }[];
  questions: TeamQuestion[];
  notes: MentorNote[];
  checks: { label: string; done: boolean }[];
}

const CHECKS = ["Khai báo repo public", "Prototype chạy được", "Có test cho luồng chính", "Slide bản nháp", "Video demo"];
const checks = (...done: boolean[]) => CHECKS.map((label, i) => ({ label, done: done[i] }));

export const TEAMS: MentoredTeam[] = [
  {
    name: "Null Pointer", track: "web", repo: "null-pointer", lastCommit: "12 phút trước", commits: 47, ai: "7.4",
    members: [{ name: "Minh Anh", bg: "bg-sun" }, { name: "Quốc Bảo", bg: "bg-rose" }, { name: "Thu Hà", bg: "bg-mint" }, { name: "Gia Huy", bg: "bg-paper" }],
    bars: [1, 0, 2, 3, 5, 2, 4, 6, 3, 5, 7, 4],
    recent: [
      { sha: "0b7c3d2", time: "14:30", msg: "feat: tính tổng điểm có trọng số", v: "Tốt", bg: "bg-mint", issue: "nghi prompt injection trong comment" },
      { sha: "5be0e11", time: "14:00", msg: "feat: lưu file bài nộp lên storage", v: "Đạt", bg: "bg-sun", issue: "put_object() thiếu xử lý timeout" },
      { sha: "19e6aa4", time: "13:30", msg: "chore: thêm cấu hình môi trường", v: "Cần cải thiện", bg: "bg-rose", issue: "lộ secret trong backend/.env" },
      { sha: "c41b7f0", time: "13:00", msg: "wip", v: "Đạt", bg: "bg-sun" },
    ],
    questions: [
      { id: "q1", from: "Minh Anh", time: "14:10", text: "Bọn em nên retry upload ở client hay server ạ? Đang bị timeout khi file > 50MB." },
      { id: "q2", from: "Quốc Bảo", time: "11:20", text: "Có nên tách service chấm điểm ra module riêng không ạ?", answer: "Giữ trong module judging là đủ, tách theo hàm service rõ ràng là được." },
    ],
    notes: [
      { id: "n1", who: "[Tên mentor]", kind: "feedback", anchor: "19e6aa4 · backend/.env:2", time: "13:42",
        text: "Repo đang public mà có S3_SECRET_KEY – thu hồi khóa ngay và thêm .env vào .gitignore nhé. Dùng .env.example cho giá trị mẫu.",
        replies: [{ who: "Minh Anh", time: "13:50", text: "Dạ em đã thu hồi khóa và xoá khỏi lịch sử rồi ạ." }] },
      { id: "n2", who: "[Tên mentor]", kind: "progress", anchor: "", time: "12:15", text: "Đã có luồng nộp bài chạy end-to-end. Mốc \"prototype chạy được\" đạt.", replies: [] },
    ],
    checks: checks(true, true, false, false, false),
  },
  {
    name: "Merge Conflict", track: "edtech", repo: "merge-conflict", lastCommit: "7 giờ trước", commits: 12, ai: "6.1",
    alert: { text: "Không có commit 7 giờ", bg: "bg-orange" },
    members: [{ name: "Hoàng Nam", bg: "bg-sky" }, { name: "Ngọc Lan", bg: "bg-sun" }, { name: "Đức Trí", bg: "bg-paper" }],
    bars: [3, 4, 2, 1, 0, 0, 0, 0, 0, 0, 0, 0],
    recent: [
      { sha: "e91a002", time: "07:40", msg: "feat: trang danh sách bài học", v: "Đạt", bg: "bg-sun", issue: "thiếu phân trang khi gọi API" },
      { sha: "b7710cd", time: "07:05", msg: "init project", v: "Tốt", bg: "bg-mint" },
    ],
    questions: [{ id: "q3", from: "Ngọc Lan", time: "07:50", text: "Đội em bị kẹt khi deploy, build lỗi thiếu biến môi trường. Mentor xem giúp được không ạ?" }],
    notes: [{ id: "n3", who: "[Tên mentor]", kind: "feedback", anchor: "e91a002 · web/lib/api.ts:12", time: "08:10", text: "Khi gọi danh sách bài học nên truyền limit/offset, đừng tải hết một lần.", replies: [] }],
    checks: checks(true, false, false, false, false),
  },
  {
    name: "Team Trà Sữa", track: "web", repo: "tra-sua", lastCommit: "40 phút trước", commits: 31, ai: "7.9",
    alert: { text: "Lỗi đồng bộ: repo chuyển private", bg: "bg-sun" },
    members: [{ name: "Khánh Vy", bg: "bg-rose" }, { name: "Bảo Long", bg: "bg-mint" }],
    bars: [2, 3, 3, 2, 4, 3, 2, 3, 4, 2, 1, 0],
    recent: [{ sha: "4c0ffee", time: "13:50", msg: "feat: bảng điều khiển đội", v: "Tốt", bg: "bg-mint" }],
    questions: [],
    notes: [{ id: "n4", who: "[Tên mentor]", kind: "answer", anchor: "", time: "14:20", text: "Repo đang private nên SEAL không đồng bộ được commit – chuyển lại public giúp mình nhé.", replies: [] }],
    checks: checks(false, true, true, false, false),
  },
];
