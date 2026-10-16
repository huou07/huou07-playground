# H07P Credential Guard — Technical Specification v1.0

**Project:** Huou07 Playground (H07P)  
**Target:** Debian Linux, x86_64  
**Core language:** Rust  
**Status:** DESIGN / NOT IMPLEMENTED  
**Priority:** Security-critical  
**Deployment:** Self-hosted, single owner, WireGuard-only access

## 1. Mục tiêu và phạm vi

Xây dựng Credential Guard để bảo vệ credentials của hệ thống khỏi việc truy cập trái phép bởi AI coding agents, tiến trình không đáng tin cậy và lỗi ứng dụng.

Hệ thống phải:

1. Ngăn agent đọc credentials nằm ngoài phạm vi được cấp quyền, trước khi dữ liệu bị đọc.
2. Giám sát file mới, file thay đổi, log và các khu vực có nguy cơ rò rỉ credentials.
3. Phát hiện, phân loại, cách ly và cảnh báo mà không lưu nội dung secret.
4. Tích hợp với hệ thống ACL và GUI bảo mật đang có trong Playground.
5. Không làm mất khả năng hoạt động bình thường của DSH, OpenCode CLI/ACP, Codex CLI/ACP, LiteLLM và OmniRoute.
6. Hoạt động liên tục với mức tiêu thụ CPU/RAM thấp.
7. Cho phép tắt riêng scanner mà không làm mất các chính sách chặn bắt buộc.
8. Có khả năng rollback an toàn, không làm mất credentials hoặc phá hủy môi trường phát triển.

### Không nằm trong phạm vi v1

- Quét toàn bộ RAM, swap hoặc ZRAM để tìm token.
- Tự viết kernel module.
- Tự viết eBPF LSM hoặc thay thế AppArmor.
- Giải mã credentials của các harness.
- Đọc hoặc sao chép API key thật vào Playground.
- Tự động revoke API key trên các nhà cung cấp.
- Tự ý thay đổi kiến trúc ACP, provider routing hoặc đăng nhập của các harness.

**Nguyên tắc:** Credential Guard không phải công cụ kiểm soát bí mật sau khi đã lộ. Nó là hệ thống áp đặt quyền truy cập trước, có thêm khả năng phát hiện và xử lý sự cố.

## 2. Giai đoạn P0 — Security Audit bắt buộc

Chưa viết cơ chế chặn hoặc sửa systemd trước khi hoàn thành audit.

### 2.1. Kiểm tra repository

Repository tham chiếu: `/home/huou07/Projects/huou07-playground`.

Theo thông tin dự án gần đây:

- Backend Python `web/app.py` đang là bản tham chiếu đầy đủ chức năng.
- Rust backend nằm tại `crates/server`, sử dụng Axum/Tokio và đang trong quá trình migration.
- Frontend hiện có tại `web/static`, dùng HTML/CSS/JS thuần.
- Playground đã có các chức năng quản lý users, permissions và ACL.

Phải xác minh lại HEAD, đường dẫn và code thực tế. Không được mặc định rằng chức năng scanner hoặc API bảo mật có sẵn dưới một tên cụ thể.

Audit cần tìm cách GUI hiện tại lưu và thực thi quy tắc ACL, cách xác thực owner, cơ chế chạy lệnh đặc quyền, và khả năng rollback.

### 2.2. Kiểm tra Linux và services

Thu thập metadata, không đọc giá trị credentials:

| Nhóm | Nội dung phải kiểm tra |
|---|---|
| Identity | UID, GID, supplementary groups, quyền sudo |
| Processes | UID thực của DSH, OpenCode, Codex, Playground |
| Filesystem | POSIX ACL, default ACL, mount options, symlink |
| Authentication | Đường dẫn chứa credential, owner, mode, khả năng đọc |
| Process security | Yama ptrace, capabilities, NoNewPrivileges, namespaces |
| Mandatory access control | AppArmor enforce/complain, Landlock ABI |
| Memory persistence | Disk swap, ZRAM writeback, core dump, hibernation |
| Logging | journald, application logs, debug logs, log rotation |
| Networking | Unix sockets, TCP listeners, WireGuard, local API |
| Containers | Podman/Docker sockets, volume mounts, đặc quyền |
| Services | Unit/drop-in files, restart policy, phụ thuộc và secrets |

Chỉ báo cáo khả năng truy cập bằng `ALLOW`, `DENY`, `UNKNOWN`, không in nội dung file.

Các phép thử quyền phải chạy với đúng UID và môi trường thực tế của từng harness. Không sử dụng root để mô phỏng quyền của agent.

### 2.3. Phân loại vùng bảo mật

**Protected credential stores:** nơi lưu OAuth token, refresh token, API key thật, LiteLLM master/salt key, SSH private key và credentials của hệ thống.

**Trusted application state:** dữ liệu cấu hình thông thường không chứa credentials.

**Agent workspaces:** cây mã nguồn, build/test outputs, cache và file mà agent được quyền sửa.

**Untrusted output:** stdout/stderr, logs, artifacts và file tạo ra bởi coding agent hoặc công cụ phụ thuộc.

**Shared resources:** skills, AGENTS.md, binaries và những thư mục dùng chung có quyền ghi.

Phải lập ma trận `principal × path × operation` với các thao tác read, write, traverse, execute và debug.

### 2.4. Rủi ro P0: credentials thuộc cùng UID

Nếu `agents-worker` vừa chạy tool shell vừa lưu DSH/Codex/OpenCode credentials cùng một UID, agent có thể đọc file sở hữu bởi chính UID đó.

Đây là rủi ro kiến trúc, không phải lỗi thiếu regex quét token.

Credential Guard phải đưa ra một trong hai kết quả:

- `ISOLATED`: credential holder được tách khỏi tiến trình chạy lệnh không đáng tin cậy và kiểm thử thực tế đã đạt.
- `UNRESOLVED_SAME_UID`: chưa thể tách mà vẫn giữ chức năng harness. Không được hiển thị trạng thái bảo mật đầy đủ.

Không được giải quyết bằng cách chỉ đặt `chmod 600` cho file cùng UID.

### 2.5. Audit artifact

Phải tạo báo cáo đã khử thông tin nhạy cảm:

- `security-audit.md`
- `risk-matrix.json`
- `access-matrix.json`
- `compatibility-baseline.json`
- `deployment-preflight.md`

Chỉ sử dụng metadata và fake credentials. Báo cáo không được chứa bearer token, cookie, private key, giá trị biến môi trường nhạy cảm hoặc nội dung file authentication.

**Exit gate P0:** Xác định chính xác ranh giới UID, quyền truy cập hiện tại và các thành phần có nguy cơ bị ảnh hưởng. Không áp dụng thay đổi hệ thống nếu chưa qua gate này.

## 3. Kiến trúc tổng thể

Credential Guard gồm ba lớp:

### Layer A — Prevent

Cơ chế bảo vệ chính, do Linux kernel thực thi:

- Phân tách tài khoản chạy agent và nơi giữ credentials thật.
- POSIX ACL và quyền thư mục cha.
- AppArmor profile áp dụng bắt buộc lên tiến trình không đáng tin cậy.
- Landlock tại điểm khởi chạy agent nếu kernel và quy trình thực thi hỗ trợ.
- Hạn chế ptrace, capabilities và quyền truy cập thiết bị thô.
- Giới hạn truy cập filesystem qua namespaces khi cần.

Các chính sách này phải hoạt động kể cả khi Credential Guard daemon bị crash.

### Layer B — Detect

Rust daemon giám sát:

- `inotify` cho những thư mục được chọn.
- `fanotify` notification nếu khả năng kernel và mount cho phép.
- File create, modify, close-write, rename, move, delete, truncate.
- Log rotation và thay inode.
- Thay đổi ACL, owner, mode hoặc trạng thái bảo vệ.
- Credential patterns trong các log được phép giám sát.
- Mất event hoặc overflow của hàng đợi.
- Trạng thái core dump, disk swap và policy drift.

Sử dụng sự kiện thay vì quét toàn bộ filesystem liên tục.

### Layer C — Respond

Khi phát hiện nghi vấn:

1. Phân loại severity và confidence.
2. Kiểm tra file hiện có được bảo vệ hay chưa.
3. Duy trì hoặc bổ sung quyền DENY thông qua policy helper, nếu chính sách cho phép.
4. Quarantine chỉ với các khu vực an toàn đã chỉ định.
5. Tạo security event đã khử dữ liệu nhạy cảm.
6. Gửi thông báo tới GUI.
7. Yêu cầu owner xử lý nếu sự cố có thể cần revoke hoặc rotation key.

Không được tự động xóa credentials của các harness.

## 4. Công nghệ và cấu trúc thành phần

### 4.1. Rust components

Đề xuất workspace logic:

- `guard-core`: policy evaluation, classifications và interfaces.
- `guard-watch`: inotify/fanotify, queue management, reconciliation.
- `guard-detect`: streaming secret detection, redaction.
- `guard-policy`: ACL adapter, kiểm tra ownership, chính sách kernel.
- `guard-ipc`: giao tiếp Unix socket, request validation.
- `guard-service`: daemon, supervision, metrics, lifecycle.
- `guard-tests`: fixtures và benchmark.

Ưu tiên thư viện đã được kiểm chứng, không tự phát minh filesystem/event framework mới.

Có thể sử dụng Tokio cho async runtime, `serde` cho dữ liệu, `rustix` cho Linux APIs và regex/streaming matcher phù hợp. Dependency và phiên bản cụ thể phải được pin theo repository lockfile sau audit.

### 4.2. Privilege separation

Không chạy toàn bộ scanner với root.

Đề xuất:

- `credential-guard`: daemon riêng với quyền tối thiểu, đọc được những thư mục monitoring đã cấp rõ ràng.
- `credential-guard-policy`: helper đặc quyền rất nhỏ, chỉ xử lý những thao tác ACL/chính sách đã được phê duyệt.
- `huou07-playground`: control plane và giao diện owner.
- `agents-worker`: không được truy cập socket điều khiển hoặc dữ liệu riêng của guard.

Policy helper phải kiểm tra peer identity, đường dẫn, inode và phạm vi được cấp. Không chấp nhận shell command tự do, tham số tùy ý cho `sudo`, hoặc đường dẫn nằm ngoài allowlist.

Giao tiếp nội bộ sử dụng Unix domain socket với kiểm tra `SO_PEERCRED`.

### 4.3. Hệ thống ACL hiện có

Không tạo thêm một ACL engine độc lập.

Credential Guard phải sử dụng chung policy store, quy tắc ownership, transaction lock và cơ chế rollback của Playground nếu đã tồn tại.

Thứ tự ưu tiên:

1. Quy tắc bảo vệ bắt buộc cho credentials.
2. Mandatory policy của kernel.
3. Quy tắc DENY của owner.
4. Quy tắc ALLOW cho workspace đã đăng ký.
5. Chính sách mặc định.

ALLOW trên GUI không được tự động vô hiệu hóa mandatory DENY. Mọi thao tác nâng quyền cần owner approval và revalidation.

Nếu ACL có `mask` hạn chế effective permissions, phải kiểm tra quyền thực tế, không chỉ đọc giá trị được khai báo.

## 5. Default-deny policy

### 5.1. Protected paths

Các vùng credentials đã được xác minh trong audit được đưa vào danh sách bảo vệ bắt buộc.

Có thể bao gồm:

- Codex OAuth store và CODEX_HOME có credentials.
- OpenCode authentication state.
- DSH provider credentials và launch tokens.
- LiteLLM master key, salt key, database credentials.
- OmniRoute authentication material.
- SSH private keys.
- Secret stores của Playground.

Không dùng regex đường dẫn chung chung để tự động khóa toàn bộ `.config` hoặc toàn bộ HOME.

### 5.2. Agent workspace policy

Agent tiếp tục được:

- Đọc và ghi mã nguồn trong các dự án được cấp quyền.
- Chạy Git, Cargo, Python, Node và build tools.
- Tạo cache, build artifacts, logs kiểm thử.
- Sử dụng skills chung đúng phạm vi.
- Gọi coding harness thông qua giao diện được phê duyệt.

Bị chặn:

- Đọc protected credentials.
- Đọc bộ nhớ tiến trình có đặc quyền hoặc credential holder.
- Truy cập raw swap/ZRAM/block devices.
- Đọc trực tiếp secret stores của provider khác.
- Chỉnh sửa policy engine hoặc truy cập policy-helper socket.
- Lạm dụng Docker/Podman socket hay sudo để vượt qua sandbox.

Không áp dụng deny toàn bộ `/proc` hoặc toàn bộ biến môi trường.

### 5.3. Credential broker

Nếu cần bảo vệ key của chính một harness trước shell agent, phải kiểm tra phương án:

- Harness authentication holder chạy dưới UID riêng hoặc trong miền bảo mật bắt buộc.
- Agent executor tiếp tục chạy dưới `agents-worker`.
- Giao tiếp qua IPC hoặc API có kiểm soát.
- Agent nhận quyền sử dụng dịch vụ, không được đọc refresh token hoặc provider key thật.

Nếu Codex ACP, OpenCode ACP hoặc DSH không hỗ trợ mô hình này, giữ cơ chế đăng nhập đang hoạt động và đánh dấu hạn chế chưa được giải quyết. Không phá vỡ authentication để đạt trạng thái bảo mật giả.

## 6. Realtime watcher

### 6.1. Event handling

Pipeline:

`Kernel event → Event queue → Path/inode validation → Classification → Policy decision → Response → Sanitized event`

Các yêu cầu:

- Event processing không block toàn bộ async runtime.
- Queue phải có giới hạn và metrics.
- Phát hiện `IN_Q_OVERFLOW`/`FAN_Q_OVERFLOW`.
- Hỗ trợ nhiều filesystem/mount namespaces trong phạm vi đã kiểm chứng.
- Phát hiện việc mất watch hoặc thay đổi mount.
- Khi overflow, chuyển trạng thái `DEGRADED` và thực hiện reconciliation.
- Không đánh dấu `HEALTHY` khi các watch quan trọng chưa khôi phục.

### 6.2. Fanotify permission events

Không sử dụng permission interception trên toàn bộ filesystem trong v1.

Các permission events cần capability đặc biệt và có thể làm chậm hoặc treo ứng dụng nếu listener không phản hồi.

Chỉ thử nghiệm trong VM tách biệt nếu có trường hợp mà AppArmor/ACL không giải quyết được. Bắt buộc đo deadlock, queue pressure, timeout và hành vi khi daemon chết.

Không dùng fanotify như lớp bảo vệ duy nhất.

### 6.3. Streaming log detection

Yêu cầu xử lý:

- Token signatures đã biết.
- Private key delimiters.
- Authorization headers.
- Credential-like strings với confidence và entropy.
- Các biến thể bị tách qua nhiều chunk.
- Log append, truncate, rotate, atomic replace.
- Giới hạn kích thước/bytes xử lý mỗi chu kỳ.

Ưu tiên redaction tại nguồn, trước khi ghi log xuống đĩa. Watcher chỉ là lớp phát hiện bổ sung, không có khả năng thu hồi dữ liệu đã bị đọc.

Không được đưa toàn bộ log chứa secrets vào API, model context, telemetry hoặc GUI.

### 6.4. RAM, swap và core dumps

- Không dump RAM để tìm credentials.
- Không cấp quyền đọc bộ nhớ tùy ý cho agent hoặc scanner.
- Kiểm tra disk swap và ZRAM writeback.
- Hạn chế quyền tới các thiết bị khối.
- Tắt core dump cho các dịch vụ giữ credentials khi tương thích.
- Giữ khả năng debug các ứng dụng phát triển trong môi trường thử nghiệm phù hợp.
- Giám sát policy drift thay vì quét dữ liệu trong RAM.

## 7. Quarantine và phản ứng sự cố

### 7.1. Điều kiện cách ly

Chỉ tự động quarantine nếu file thuộc thư mục được định nghĩa là safe-to-quarantine, và hành động đó không phá vỡ service hoặc dữ liệu đang sử dụng.

Ví dụ phù hợp: log export hoặc artifact nghi chứa token trong một thư mục staging được giám sát.

Không tự động di chuyển:

- Database.
- Credentials gốc của harness.
- Source file đang được build.
- Log file đang mở bởi dịch vụ quan trọng.
- SSH authentication material.
- Tệp ngoài allowlist.

Không coi `rename`, `chmod` hoặc `setfacl` sau sự kiện là cách thu hồi dữ liệu đã đọc hoặc file descriptor đã mở.

### 7.2. Path validation

Phải kiểm tra chống:

- Symlink traversal.
- Hardlink alias.
- `../` traversal.
- Rename race và TOCTOU.
- Bind mount/mount namespace khác.
- File replacement giữa scan và policy update.

Sử dụng descriptor-relative operations; đánh giá `openat2` với `RESOLVE_BENEATH`, `RESOLVE_NO_MAGICLINKS` và các cờ phù hợp.

Không dựa vào canonicalized string path làm bằng chứng duy nhất về danh tính file.

### 7.3. Incident record

Mỗi sự kiện chỉ được lưu:

- Event ID.
- Timestamp.
- Event type.
- Severity/confidence.
- Principal hoặc UID liên quan nếu xác định được.
- Đường dẫn đã được hạn chế hoặc che theo quyền người xem.
- Hành động thực thi và kết quả.
- Policy revision.
- Thông tin phục vụ audit không chứa secret.

Không lưu giá trị match, đoạn context quanh token, raw request headers hoặc environment values.

### 7.4. False positive

Mặc định:

- Confidence thấp: báo cáo.
- Confidence trung bình: cảnh báo và gợi ý kiểm tra.
- Confidence cao: áp dụng policy cho phạm vi được phép; quarantine chỉ trong safe-to-quarantine zone.
- Bất kỳ mức confidence nào: không tự ý xóa dữ liệu gốc.

Các quy tắc tự động phải idempotent và có cooldown để tránh vòng lặp cảnh báo.

## 8. Tích hợp GUI Playground

Không viết lại frontend bằng framework mới.

Bổ sung Credential Guard vào khu vực Security đang có, giữ giao diện tối giản và cùng mô hình permission hiện hành.

### 8.1. UI sections

**Overview**

- Enforcement status.
- Scanner status.
- Protected zones.
- Unresolved exposure risks.
- Last successful audit.
- Event queue health.

**Policies**

- Xem mandatory DENY.
- Xem workspace grants.
- Quản lý ngoại lệ với owner approval.
- Xem effective permissions.

**Events**

- Realtime incident timeline.
- Filter theo severity, principal và nguồn.
- Chi tiết sự kiện đã khử secret.
- Xác nhận xử lý.

**Diagnostics**

- Fanotify/inotify capabilities.
- AppArmor/Landlock support.
- Core dump và disk swap status.
- Event queue overflow.
- p50/p95/p99 latency.
- Last compatibility test.

### 8.2. API contract đề xuất

Các route thuộc namespace `/api/security/credential-guard`:

| Method | Endpoint | Chức năng |
|---|---|---|
| GET | `/status` | Health và enforcement status |
| GET | `/policies` | Chính sách đã khử dữ liệu nhạy cảm |
| GET | `/events` | Incident metadata |
| GET | `/metrics` | Performance và counters |
| POST | `/scan` | Yêu cầu quét có giới hạn |
| POST | `/policies/dry-run` | Xem thay đổi trước khi áp dụng |
| POST | `/policies/apply` | Áp dụng sau khi xác thực owner |
| POST | `/quarantine/restore` | Khôi phục có kiểm chứng |

Thao tác thay đổi trạng thái chỉ được thực hiện qua phiên owner hợp lệ, chống CSRF và kiểm tra authorization phía server.

Không cho worker gọi API đặc quyền thông qua localhost hoặc socket.

### 8.3. Migration compatibility

Trong giai đoạn Python backend còn là nguồn chức năng chính, thêm adapter nhỏ vào backend hiện có để gọi Rust daemon qua Unix socket.

Khi Rust/Axum backend đạt parity và được chọn làm production, chuyển adapter sang Rust mà giữ nguyên API contract.

Không tạo hai policy store riêng giữa Python và Rust.

## 9. Hiệu năng và benchmark

Ưu tiên không làm chậm đường chạy thông thường của coding agent.

Benchmark phải đo các thành phần riêng và tác động end-to-end.

### 9.1. Metrics

- Kernel policy check overhead.
- Event arrival latency.
- Detection latency.
- ACL transaction latency.
- Quarantine latency.
- GUI event delivery latency.
- CPU, RSS, file descriptors.
- Queue depth và overflow.
- False positive/false negative trên fixtures.
- Build/test time regression.

Báo cáo p50, p95, p99, maximum và số lượng mẫu cho từng loại workload.

### 9.2. Mục tiêu thử nghiệm sơ bộ

| Metric | Mục tiêu |
|---|---|
| Phát hiện thay đổi file nhỏ, p99 | Dưới 20 ms |
| Phát hiện token trong log 4 KiB, p99 | Dưới 50 ms |
| ACL transaction cho một file, p99 | Dưới 20 ms |
| GUI notification sau khi phát hiện, p99 | Dưới 250 ms |
| Build/test runtime regression | Không quá 5% |
| Sustained scanner CPU | Càng thấp càng tốt; báo cáo đo thực tế |
| Unauthorized read ở protected roots | 0 lần thành công trong bộ acceptance test |

Các mục tiêu trên là **benchmark targets, không phải cam kết đã đạt**.

Thời gian detection không được dùng làm tiêu chuẩn bảo đảm không lộ secret. Tiêu chuẩn bảo mật là quyền đọc bị DENY trước khi dữ liệu trở nên truy cập được.

### 9.3. Test workloads

- 1.000 / 10.000 / 100.000 file synthetic.
- Nhiều tiến trình ghi log song song.
- Append/truncate/rotate liên tục.
- Credentials chia nhỏ qua chunk boundaries.
- Rename, symlink, hardlink và replace races.
- Burst events và forced queue overflow.
- Daemon restart/crash.
- Scanner mất quyền đọc.
- Disk gần đầy và tài nguyên hạn chế.
- Concurrent ACL changes từ GUI.

Mọi benchmark phải báo cáo CPU, RAM, filesystem, kernel version và phương pháp đo.

## 10. Kiểm thử bảo mật

Chỉ sử dụng credentials giả tạo trong môi trường cách ly.

### 10.1. Fake credentials

Fixtures phải bao gồm:

- Fake provider API keys.
- Fake OAuth access/refresh tokens.
- Fake private keys.
- Fake `.env` và authentication JSON.
- Fake Authorization headers.
- Dữ liệu entropy cao nhưng không phải secret.
- Token chia qua hai hoặc nhiều lượt ghi.
- Unicode, binary và escaped strings.
- Token nằm trong tên file hoặc nội dung log.

Không sử dụng bất kỳ credential thật nào trong unit test, CI, benchmark hoặc báo cáo.

### 10.2. Attack simulation

Kiểm thử:

- Agent đọc protected file.
- Agent đọc `/proc/<pid>/environ` thuộc credential holder.
- Agent thử đọc `/proc/<pid>/mem`.
- Agent dùng symlink hoặc hardlink.
- Agent đổi tên file sau khi được scan.
- Agent tạo file nhạy cảm ngay trong workspace.
- Agent truy cập Docker/Podman socket.
- Agent cố sửa ACL hoặc policy store.
- Agent truy cập Unix socket của policy helper.
- Agent sử dụng những file descriptor đã được mở trước khi thay chính sách.

Mỗi bài kiểm thử phải ghi nhận rõ `PASS`, `FAIL` hoặc `LIMITATION`, không che giấu đường bypass.

### 10.3. Tình huống crash

Kiểm thử việc dừng scanner trong khi:

- Protected file đang được truy cập.
- Log đang ghi.
- ACL transaction đang chạy.
- Event queue đang đầy.
- Playground backend restart.
- DSH/OpenCode/Codex ACP đang làm việc.

Khi scanner crash, mandatory DENY phải tiếp tục hoạt động. Tình trạng detection phải hiển thị `DEGRADED` hoặc `OFFLINE`, không giả báo hệ thống đang bảo vệ đầy đủ.

## 11. Regression testing — không phá vỡ harness

Các bài acceptance bắt buộc:

**DSH**

- Login và load giao diện.
- Model request thành công.
- Streaming response.
- Tool execution.
- Permission approval.
- Session resume/cancel.

**OpenCode CLI/ACP**

- Native login vẫn hợp lệ.
- ACP initialize và session creation.
- Gọi model.
- Đọc/ghi dự án được phép.
- Chạy tool/build/test.
- Restart và reconnect.

**Codex CLI/ACP**

- ChatGPT authentication.
- ACP initialize.
- Chạy coding task.
- Shell/tool invocation.
- Cancellation và session lifecycle.
- Không lộ authentication files.

**Playground**

- Security GUI cũ hoạt động.
- ACL deny/allow cũ giữ nguyên.
- File manager và project access hoạt động.
- Metrics/process monitoring không bị mất.
- Audit không hiển thị credentials.
- GUI và API đồng nhất trạng thái.

**Development workflow**

- Git, Cargo, Node, Python.
- Build/test workflows thực tế.
- Shared skills/AGENTS.md.
- Debug/profiling trong phạm vi được phép.
- Không xuất hiện các service/session trùng lặp.

Không sửa authentication, provider, ACP transport hoặc quyền workspace chỉ để làm cho bài test Guardian vượt qua. Khi cần thay đổi những phần đó, phải có review riêng.

## 12. CI và validation

Giữ nguyên quy tắc của H07P: **Debian production không phải máy chạy stress test hoặc destructive test.**

Toàn bộ build, integration, security simulation và benchmark phải chạy trên môi trường GitHub runner hoặc VM dùng một lần, với kernel/capabilities đủ phù hợp cho chức năng được thử nghiệm.

Các bước:

- Rust format, Clippy và unit tests.
- Existing Python checks.
- Existing Rust smoke tests.
- Existing Playwright E2E.
- Security fixtures.
- Privilege boundary tests.
- Benchmark trước/sau.
- Packaging và install/uninstall.
- Rollback rehearsal.

Đồng thời bổ sung Rust Guard checks vào CI authoritative thay vì chỉ kiểm tra backend Python.

Những phép thử kernel đòi root/capabilities mà hosted runner không hỗ trợ phải chạy trong VM cô lập; không được thay thế bằng mock rồi tuyên bố đã xác minh thực tế.

Trên Debian production chỉ cho phép preflight đọc trạng thái và smoke test không phá hủy sau khi owner phê duyệt triển khai.

## 13. Deployment và rollback

### 13.1. Deployment

- Daemon đóng gói bằng systemd system service.
- Không đưa credentials vào command-line arguments.
- State directory chỉ dịch vụ đáng tin cậy truy cập.
- Có cấu hình restart và resource limits.
- Lưu policy snapshot và checksum.
- Privileged operations chạy qua helper bị giới hạn chặt chẽ.
- Service không bắt buộc phụ thuộc vào LiteLLM hoặc các coding harness.
- GUI vẫn phải tải được nếu daemon offline.

Không thay thế service manager, user accounts hoặc container setup hiện có nếu không cần thiết.

### 13.2. Rollback

Trước khi apply:

1. Backup ACLs, mandatory policies, service unit và app configuration.
2. Lưu policy revision và expected file identities.
3. Verify khả năng rollback trong VM.
4. Tạo dry-run diff cho owner xem.
5. Xác nhận rollback không cấp quyền rộng hơn trạng thái baseline.

Khi rollback:

- Dừng phiên bản mới.
- Khôi phục unit/config và những ACL do Credential Guard sở hữu.
- Không vô hiệu hóa chính sách DENY có từ trước.
- Không xóa hay thay đổi credentials.
- Không rollback các thay đổi của dự án khác.
- Không xóa dữ liệu forensic hoặc log chưa được xử lý mà không có quyết định của owner.

Rollback phải idempotent và từ chối ghi đè khi phát hiện conflict với thay đổi được thực hiện sau thời điểm snapshot.

## 14. Trạng thái vận hành

Hệ thống báo một trong các trạng thái:

| Status | Ý nghĩa |
|---|---|
| `AUDIT_ONLY` | Chưa kích hoạt chính sách mới |
| `PROTECTED` | Enforcement hoạt động; các acceptance gates đã đạt |
| `DEGRADED` | Policy còn hoạt động nhưng watcher/telemetry gặp lỗi |
| `PARTIAL` | Có vùng đã bảo vệ nhưng còn rủi ro chưa giải quyết |
| `POLICY_ERROR` | Chính sách không được áp dụng đúng |
| `OFFLINE` | Daemon ngừng hoạt động |

Scanner bật không đồng nghĩa với trạng thái `PROTECTED`.

Phải công khai những giới hạn chưa thể khắc phục, đặc biệt là credentials nằm cùng UID với phần thực thi lệnh không đáng tin cậy.

## 15. Thứ tự triển khai

**Phase 0 — Audit:** Xác minh trạng thái thực tế, ma trận truy cập và baseline.

**Phase 1 — Prevention:** Chính sách kernel/ACL và ranh giới quyền, kiểm thử trên VM.

**Phase 2 — Rust daemon:** Watcher, secret detection, event store, metrics.

**Phase 3 — Response:** Policy helper, quarantine có điều kiện, notification.

**Phase 4 — Playground integration:** API adapter và GUI.

**Phase 5 — Acceptance:** Security adversarial tests, performance A/B, harness regression.

**Phase 6 — Production:** Owner-reviewed deployment, post-deploy validation và rollback readiness.

Không chuyển sang phase sau nếu security gate của phase hiện tại chưa đạt.

## 16. Definition of Done

Credential Guard chỉ được chấp nhận khi:

- Không có unauthorized read thành công trong bộ test protected credentials.
- Không xuất hiện real API key hoặc token trong log, telemetry, browser state hoặc test artifacts.
- Bảo vệ bắt buộc vẫn hoạt động khi scanner bị tắt.
- GUI thể hiện chính xác tình trạng bảo vệ và các hạn chế.
- Scanner hoạt động liên tục mà không làm rớt sự kiện không được phát hiện.
- Các hàng đợi overflow được phát hiện và reconciled.
- Các false positive không phá hủy dữ liệu.
- DSH, OpenCode ACP và Codex ACP vượt qua bài test chức năng thực tế.
- Toàn bộ Rust/Python/frontend CI đạt.
- Có kết quả benchmark p50/p95/p99 và so sánh baseline.
- Rollback được thử nghiệm trên môi trường dùng một lần.
- Chủ máy có thể điều khiển chính sách qua Playground mà agent không nhận được quyền quản trị tương đương.
- Không có thay đổi không cần thiết tới các service khác.

**Quy tắc cuối cùng:** Không đánh đổi tính bảo mật để đạt benchmark đẹp, và không đánh đổi chức năng thực tế của các harness chỉ để đạt một checklist bảo mật mang tính hình thức. Mọi giới hạn còn lại phải được báo cáo chính xác.