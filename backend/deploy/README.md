# Vận hành Phase 7

Compose này chỉ dựng backend và proxy; frontend do chủ sở hữu frontend cung cấp qua `FRONTEND_UPSTREAM`. Dev vẫn dùng Compose phụ trợ ở root. Không có deploy từ xa được thực hiện bằng việc thêm các file này.

## Staging / production

1. Trên Linux, copy `.env.example` thành `.env`, đặt secret thật, domain và origin HTTPS. Dùng password đã URL-encode trong `DATABASE_URL`. Không dùng giá trị mẫu cho production.
2. Cấp chứng chỉ TLS cho domain, đặt `fullchain.pem` và `privkey.pem` vào `certs/` (quyền 600 với private key); gia hạn chứng chỉ bằng hạ tầng của đơn vị rồi reload Nginx. Không commit private key.
3. Frontend phải truy cập được từ container Nginx; địa chỉ `host.docker.internal` trong ví dụ dành cho Docker Desktop. Trên Linux dùng upstream frontend đã triển khai trong mạng nội bộ. Không công khai port API/DB/Redis.
4. Tạo `backups/assets` thuộc UID/GID 1000 và quyền 700 trên host Linux (`install -d -o 1000 -g 1000 -m 0700 backups/assets`). Image backup DB chạy bằng user `postgres` (UID/GID 999 trên image Debian đã kiểm); tạo `backups/postgres` bằng `install -d -o 999 -g 999 -m 0700 backups/postgres`. Volume marker `/status` mới được khởi tạo thuộc postgres, mode 755 để asset-backup đọc marker 644. Khi nâng cấp volume marker hoặc thư mục backup đã có do root tạo, vận hành phải cấp quyền ghi cho UID 999 trên đúng thư mục/file đó, giữ dữ liệu backup; không chạy lại backup bằng root để né lỗi quyền. Chạy `docker compose -f compose.yml --env-file .env up -d --build`. Migration chạy trước API/worker. Beat duy nhất một instance; API một instance vì Engine.IO polling cần sticky session khi scale. Nếu scale API, cấu hình sticky session ở LB và kiểm tra ma trận socket trước.
5. Kiểm tra `/api/v1/ready`, `/api/v1/health`, `/admin/system`, worker/Beat healthchecks; xác nhận consumer `ai-review` khi dùng AI. Worker ping, heartbeat và Beat là ba tín hiệu riêng.
6. Smoke xác thực, refresh/logout, user bị khóa, thu hồi organizer/mentor/judge, public/unpublish và export sau khóa. Realtime kiểm tra lại quyền trước phát, quét idle mỗi 5 giây. Redis/DB lỗi sẽ từ chối/đóng socket. Token hết hạn cần refresh/reconnect.

Nginx chỉ log method + URI không có query; API tắt access log tại proxy để tránh token verify/reset, signed URL trong query. TLS terminate tại Nginx; API nhận forwarded IP từ mạng Compose tin cậy, không publish port 8000. Nếu đặt CDN/LB phía trước, cấu hình danh sách proxy/IP tin cậy trước khi dùng rate limit theo client IP. Không cho analytics thu thập query hoặc body auth.

## Outbox / email

Task `seal.notifications` chạy queue `realtime` mỗi 5 giây, phát outbox trước rồi chuyển in-app delivery; không gửi SMTP. Task `seal.notification_emails` chạy riêng queue `email` mỗi 5 giây; xác thực email và receipt kết quả cũ cũng dùng queue email. Các worker sync (`celery`), realtime, email, AI cần consumer riêng; restart toàn bộ worker/Beat sau khi đổi routing, kiểm tra `realtime_queue` và `email_queue` trong `/admin/system`. Queue cũ đang có task vẫn phải drain, không purge queue hoặc reset receipt `unknown`. Ghi notification + delivery trong transaction nghiệp vụ. API không phụ thuộc broker để lưu quyết định duyệt đội. Worker claim `queued → unknown` bền trước SMTP; thành công chuyển `sent`, lỗi mơ hồ giữ `unknown`, không tự retry. In-app đọc qua REST ngay cả mất socket; realtime invalidation có thể phát lại sau crash. Các receipt email/nhắc hạn cũ giữ lại, job kết quả cũ chỉ drain dữ liệu trước Phase 7.

`sent` chỉ là SMTP transport nhận; chưa chứng minh thư vào inbox. Delivery API không trả email đích, payload hay phản hồi SMTP. Khi gặp `unknown`, kiểm tra SMTP/provider bằng ID/thời điểm trước khi quyết định gửi bù; không đổi hàng loạt về queued. User bị khóa/mất audience không nhận thư đang chờ; notification riêng ẩn khỏi inbox khi mất role tương ứng.

## Backup và restore drill

Backup PostgreSQL tự động trong service `backup`: `pg_dump -Fc`, mã hóa age public key, checksum và retention theo env. Private key giữ offline. `/backups/last-success.txt` là thời điểm dump/mã hóa gần nhất, **không** là bằng chứng restore thành công. Giới hạn quyền thư mục host `backups/` cho vận hành; sao chép bản mã hóa sang nơi khác sau mỗi lần thành công. Theo dõi timestamp/exit/error log bằng hệ thống giám sát của môi trường.

File Cloudinary cần backup riêng. Từ môi trường có backend env và CLI `age` (Linux/Windows), chạy trong `backend/`:

```sh
python -m ops.backup_assets /secure-backups/files-YYYYMMDD.zip.age --recipient age1PUBLICKEY
```

Recipient phải là public key age native `age1…` (62 ký tự); script không nhận SSH recipient hoặc option thay public key. Đường dẫn output được chuẩn hóa thành tuyệt đối trước gọi age; không qua shell.

Compose đã có service `asset-backup`: sau mỗi marker dump PostgreSQL mới, backup toàn bộ file đã chốt, dùng cùng timestamp để ghép bộ DB/file; chỉ giữ marker thành công khi mã hóa xong. Script chỉ tải authenticated raw, kiểm tra size, lưu SHA256/ID/key trong manifest, stream ZIP trực tiếp qua age, không ghi URL ký. File sau khi chốt là bất biến, nên inventory sau DB dump có thể là superset của DB snapshot; khi drill đối chiếu đủ mọi file DB tham chiếu. Giữ bộ DB + file cùng timestamp, không xóa file Cloudinary gốc. Kiểm tra cả `backups/postgres/last-success.txt` lẫn `backups/assets/last-success.txt`/`last-completed-at.txt`; chỉ có một timestamp DB chưa đủ để báo backup toàn bộ thành công. Cloudinary credentials phải được cấu hình cho service này.

Trước production, thực hiện trên **môi trường cách ly**, dùng key offline:

```sh
sha256sum -c seal-TIMESTAMP.dump.age.sha256
age -d -i /offline/identity.txt -o /isolated/seal.dump seal-TIMESTAMP.dump.age
createdb seal_restore_YYYYMMDD
pg_restore --exit-on-error --no-owner --no-privileges -d seal_restore_YYYYMMDD /isolated/seal.dump
age -d -i /offline/identity.txt -o /isolated/files.zip files-TIMESTAMP.zip.age
export SEAL_RESTORE_ROOT=/isolated
python -m ops.verify_assets /isolated/files.zip /isolated/restored-files-YYYYMMDD
```

`SEAL_RESTORE_ROOT` phải là thư mục cách ly đã tồn tại, do vận hành sở hữu và không cho tài khoản không tin cậy sửa symlink/thư mục trong lúc restore. Target phải là thư mục mới nằm dưới root này, kể cả sau khi resolve symlink/`..`; ID file trong archive vẫn bắt buộc UUID. Trên PowerShell đặt `$env:SEAL_RESTORE_ROOT = 'F:\isolated'` trước chạy CLI.

Kiểm tra schema/migration, số đội/bài nộp/file, các FK; đối chiếu từng `submission_files.id/storage_key/size` của DB đã restore với manifest. Mở file mẫu từ thư mục cách ly, xác nhận checksum và đọc nội dung; thử API read với DB cách ly và storage mock/copy thuộc Cloudinary environment cách ly, không ghi vào provider production. Ghi biên bản: timestamp backup, checksum, phiên bản DB, số bản ghi/file, thời gian restore, người thực hiện, lỗi và kết quả smoke. Chỉ tick nghiệm thu khi có biên bản thật. Bảo vệ/xóa plaintext restore theo quy trình của đơn vị; không tự xóa hồ sơ cuộc thi.

## Load test nộp bài

Chuẩn bị **staging riêng** với 100 đội approved, mỗi đội một leader verified, repo đúng đội và vòng còn hạn. Fixture JSON gồm 100 object: `team_id`, `round_id`, `access_token`, `idempotency_key`, `body` (schema nộp bài Phase 3, file_keys upload thật nếu đo storage). Đặt fixture ngoài Git, bảo vệ như secret.

```sh
export SEAL_LOAD_ALLOWED_ORIGINS=https://staging.example.com
python -m ops.load_submissions https://staging.example.com /secure/load-fixture.json
```

Allowlist do vận hành đặt qua môi trường, tách khỏi argument CLI; nhiều origin ngăn bằng dấu phẩy. Chỉ cấu hình staging được quản lý/tin cậy, không wildcard. URL CLI phải khớp origin cho phép, không credentials/path/query/fragment. Harness không theo redirect hoặc proxy từ môi trường, validate UUID team/round trước gửi token. Trên PowerShell dùng `$env:SEAL_LOAD_ALLOWED_ORIGINS = 'https://staging.example.com'`.

Harness rải 100 đội trong 60 giây, replay cùng key và so ID/version; exit khác 0 nếu mất/trùng receipt. Xác minh DB có đúng 100 receipt/version tương ứng và deadline server; lưu kết quả JSON, tài nguyên máy, p95, log lỗi đã bỏ secret. Nếu mock GitHub/storage chỉ chứng minh backend/DB; nghiệm thu end-to-end cần provider thật, HTTPS và upload thật. Token fixture phải còn hạn suốt lượt. Không chạy vào cuộc thi đang hoạt động.
