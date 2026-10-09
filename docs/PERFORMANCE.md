# Runtime performance sample

This is a first low-load sample from the live Debian target on 2026-10-09. It is a baseline for later comparisons, not a claim that every performance acceptance test is complete.

## Environment and method

- Hardware: Dell OptiPlex Micro 7010, Intel Core i5-13500T, 16 GiB RAM, NVMe storage.
- The dashboard and OpenCode Web services were active. OpenCode had no provider login or coding workload. The dashboard was open in a browser.
- Host CPU busy percentage was sampled from `/proc/stat` across 10 seconds.
- Service memory came from systemd `MemoryCurrent` for each service cgroup.
- API timings were five consecutive local loopback `curl` requests per endpoint. These omit SSH tunnel and browser rendering time.
- Swap counters were compared across a separate 10-second idle interval.

## Observations

| Measurement | Result |
| --- | ---: |
| Host CPU busy, 10 seconds | 0.69% |
| Available system memory | about 13 GiB |
| Dashboard service memory | 24,256,512 bytes (23.1 MiB) |
| OpenCode Web service memory | 239,628,288 bytes (228.4 MiB) |
| Dashboard `/api/health`, median of 5 | 0.76 ms |
| Dashboard `/api/metrics`, warm median of 4 | 5.52 ms |
| Dashboard `/api/metrics`, first request | 95.29 ms |
| Dashboard `/api/apps`, median of 5 | 17.37 ms |
| Disk swap used | about 4 GiB of 15 GiB |
| Swap-in / swap-out counter change over 10 seconds | none |

The first metrics request was slower than the next four; this small sample cannot determine whether that is repeatable cold-start work. The nonzero swap allocation did not change during the sample. With 13 GiB available and no observed swap traffic, adding ZRAM is not justified by this baseline.

## LiteLLM idle sample

After LiteLLM Gateway was installed on 2026-10-09, five authenticated local requests to `/v1/models` returned HTTP 200 with a 2.76 ms median; five liveness requests returned HTTP 200 with a 0.94 ms median. These are host-loopback API timings and do not include the SSH tunnel or browser UI. No provider or model is configured, so this does not measure inference latency.

At the same sample, systemd reported 611.6 MiB current memory for the gateway (2 GiB cap, two CPU quota cores) and 87.6 MiB for PostgreSQL (1 GiB cap, one CPU quota core). The full pod's memory, idle CPU, and storage-write rate have not been benchmarked separately.

## OmniRoute idle sample

After OmniRoute `3.8.51` was installed on 2026-10-09, five server-loopback health checks returned HTTP 200 with a 6.20 ms median. Five unauthenticated `/v1/models` checks on the separate API listener returned HTTP 401 with a 7.07 ms median, confirming key enforcement before the owner configures a provider. These local timings omit SSH forwarding and browser rendering and do not measure inference. The service cgroup used 406,159,360 bytes (387.4 MiB) against its 10 GiB memory cap after a same-snapshot restore. Idle CPU and longer-term cache/storage write rates have not been measured.

## SSH-forwarded dashboard and current service memory

On 2026-10-09, dashboard release `20261009063618-110298` (source assets match `fe832db90f9be6b842f12834341c48a9fe1af483`) was sampled from the Mac through a verified SSH tunnel to the Dell. Eight requests per route were measured; the first request is reported separately and the warm median uses the remaining seven. Each response returned HTTP 200. The browser was not used for this timing sample, so render and interaction time are excluded.

| Route | Response bytes | First request | Warm median |
| --- | ---: | ---: | ---: |
| `/` | 19,728 | 14.3 ms | 13.3 ms |
| `/api/health` | 11 | 12.5 ms | 12.1 ms |
| `/api/metrics` | 1,404 | 97.2 ms | 15.7 ms |
| `/api/apps` | 1,234 | 36.2 ms | 33.7 ms |
| `/api/vpn` | 224 | 54.7 ms | 48.4 ms |

At the same sample, systemd cgroups for the dashboard, OpenCode Web, LiteLLM, OmniRoute, and wg-easy reported 1,313,619,968 bytes (about 1.22 GiB) combined. Each unit was active. This is the listed huou07 service set only; it excludes Cockpit, host services, and unrelated workloads. The API medians include SSH forwarding and local network round-trip time, unlike the earlier server-loopback measurements.

## Live telemetry cross-check and memory policy

On 2026-10-09, after release `609b8e242e362a4fb2adb6d4ad59f30f65543b9` was active, the deployed metrics endpoint was compared with Linux's `/proc`, `statvfs`, and sysfs data on the Dell. API CPU was 1%; an independent two-second `/proc/stat` sample was 1.0%. API RAM was 3,645,026,304 used / 16,441,217,024 total / 12,796,190,720 available bytes; direct `/proc/meminfo` was 3,642,179,584 / 16,441,217,024 / 12,799,037,440, a small difference from sequential sampling. Dashboard root-disk used/total matched `shutil.disk_usage` exactly at 229,759,639,552 / 485,325,094,912 bytes. Disk-swap used/total matched `/proc/swaps` exactly at 4,307,316,736 / 16,852,709,376 bytes.

The endpoint and `/sys/block` both found zero ZRAM devices. `vm.swappiness` was 1, memory pressure PSI averaged 0.00 over the last 10 seconds, and swap-in/out counters did not change during the two-second sample. With about 11.9 GiB available, there is no measured pressure that justifies adding compressed-memory CPU overhead; disk swap and the existing swappiness setting were left unchanged. This is an observed idle interval, not a stress test.

The live i915 sample reported 0% engine utilization while idle. For an active check, an 8-second, 1280×720, 30 fps VAAPI encode to FFmpeg's null output ran in a temporary systemd unit as the unprivileged dashboard account. The unit had only the `video` and `render` supplementary groups, access to `/dev/dri/renderD128`, no network sockets, a 50% CPU quota, a 256 MiB memory cap, and a 12-second runtime limit. FFmpeg exited successfully; the existing restricted GPU collector sampled Video at 3.8%, with Blitter, Render/3D, and VideoEnhance at 0%. A follow-up sample returned all engines to 0.0%. No GPU temperature interface was reported. The restricted CPU package collector reported 6.5 W for `PkgWatt`. An initial two-second network counter comparison was too noisy to assess rate accuracy; a longer transfer-aligned comparison is recorded below.

After release `20261009092950-217379` (source commit `700f2f6628e03937aeb43da140c0a659e1806e14`) was deployed, a bounded headless EGL workload ran as the unprivileged dashboard account with `video` and `render` groups, access restricted to `/dev/dri/renderD128`, no network sockets, empty capabilities, a 50% CPU quota, a 256 MiB memory cap, and a 20-second runtime limit. Mesa reported `Intel(R) UHD Graphics 770 (ADL-S GT1)` and the shader completed 6,629 frames at 1280×720 in its 15-second run. The deployed collector sampled Render/3D at 97.7% (Blitter, Video, and VideoEnhance at 0%); the next sample after the workload ended returned all engines to 0%. All dashboard and managed application services stayed active. The temporary benchmark packages and files were removed. This verifies real Render/3D utilization telemetry on the Dell; temperature remains unavailable.

## Current dashboard and navigation sample

On 2026-10-09, dashboard release `20261009072037-136357` from source commit `873895f3758167267b049a90c03adb15aba350ad` was measured with no coding workload. The server sample used eight loopback requests per route and a 10-second `/proc/stat` interval. The browser sample ran Chromium on the Mac through an SSH tunnel to the dashboard; a test hostname was mapped to the local tunnel so link rewriting for a private host could be observed. The browser was opened once in a fresh context. The route timing measured each sidebar click to the next animation frame, across three visits to all nine views.

| Measurement | Result |
| --- | ---: |
| Host CPU busy, 10 seconds | 0.90% |
| Available system memory | 12,770,545,664 bytes (about 11.9 GiB) |
| Disk swap used/total | 4,307,304,448 / 16,852,709,376 bytes |
| Listed huou07 service memory, including Cockpit socket | 1,321,598,976 bytes (1,260.4 MiB) |
| Dashboard service memory | 50,782,208 bytes (48.4 MiB) |
| `/` loopback, first / warm median of 7 | 21.01 / 0.72 ms |
| `/api/health` loopback, first / warm median of 7 | 0.31 / 0.30 ms |
| `/api/metrics` loopback, first / warm median of 7 | 67.76 / 1.90 ms |
| `/api/apps` loopback, first / warm median of 7 | 33.42 / 14.49 ms |
| `/api/vpn` loopback, first / warm median of 7 | 18.41 / 36.53 ms |
| Browser navigation to next frame, 27 clicks | 16.4 ms median (1.5–25.2 ms) |
| Browser navigation response end / DOM ready / load event | 18.8 / 55.9 / 83.0 ms |
| Browser transferred resource bytes | 137,933 bytes |

The real browser loaded all nine routes, reported no console warnings, and had no horizontal overflow at 375 px. Private-service links rewrote to their fixed relay ports. This simulated the private-host name through an SSH tunnel; it was not an external WireGuard client test. Loopback API timings omit WAN or VPN latency. The short sample does not measure application launch, provider inference, or file transfer.

## Cockpit Files large-transfer integrity

On 2026-10-09, a real Chromium session connected to Cockpit Files through the SSH recovery tunnel using a disposable, non-sudo Linux account. A local sparse, zero-filled 16-GiB file was uploaded through the Files UI; Cockpit finalized it under its requested name and displayed it as 17.2 GB. The target reported 13,250,101,248 bytes available RAM at upload start, so the payload exceeded available RAM by 3,929,767,936 bytes. The upload and a separate browser download both had exact size 17,179,869,184 bytes and SHA-256 `07d217ebccc55480b7afa191674ec5da87f2d14efbc04dbc7e40efe345f16776`. The download saved locally and matched the source hash. During transfers, the Cockpit bridge process high-water RSS was about 34 MiB; target available RAM stayed around 12.3–13.2 GiB. This verifies streaming-sized operations and integrity for a file larger than available RAM, but does not establish peak memory for every Cockpit process or sustained throughput. Temporary accounts, homes, and files were removed; root filesystem free space returned to its prior range.

A second 16-GiB run was completed through Cockpit Files on dashboard release `20261009121351-328537` (source commit `c708485`). The target began with about 12.1 GiB available RAM and stayed around 12.0–12.1 GiB during the upload and download. Upload I/O sampling showed a sustained 15–17 MiB/s during the final half; the automation's 15-minute visibility wait expired before this long transfer completed, and the file appeared in the Files view after reconnecting. The browser download completed in 859.321 seconds (19.1 MiB/s) with no download failure. Source, uploaded file, and downloaded file all measured 17,179,869,184 bytes and had the same SHA-256 shown above. While the download ran, dashboard health and metrics returned HTTP 200 in 104 ms and 173 ms. The test file was deleted through Cockpit Files, the disposable account and local payloads were removed, and server free space returned to 216 GiB.

## Cockpit Files throughput comparison

On 2026-10-09, a real Chromium session used Cockpit Files through the existing SSH tunnel with a disposable non-sudo account. A 268,435,456-byte random-data file was uploaded and downloaded once each. `scp` transferred the same file in each direction over the verified SSH alias to and from the same root filesystem (`/var/tmp`) as the comparison baseline. All four files had the same SHA-256: `367156b0b3592736cf887dc70eda03696e6275bcd8c93190da634e97684fddc0`.

| Direction | Cockpit Files | `scp` baseline |
| --- | ---: | ---: |
| Upload | 17.724 s · 14.44 MiB/s (121.2 Mbit/s) | 17.496 s · 14.63 MiB/s (122.7 Mbit/s) |
| Download | 13.216 s · 19.37 MiB/s (162.5 Mbit/s) | 12.990 s · 19.71 MiB/s (165.3 Mbit/s) |

These single runs were close to the `scp` baseline on this route and disk. A later repeated `scp` sample on the same route and filesystem is recorded below; Cockpit itself has not yet been repeated. Neither run predicts speeds on other networks or storage. Interruption/resume behavior remains untested. The 16-GiB integrity run above is the separate large-file and memory observation. The temporary account, local files, and server files were removed.

## Repeated SSH transfer baseline

On 2026-10-09, a 268,435,456-byte random-data file was transferred three times in each direction with `scp` over the verified SSH connection to the Dell's `/var/tmp`. Transfer timing excludes local file generation and hash calculation. Every uploaded and downloaded copy matched SHA-256 `52c7707a971735d5ab137433e35d9ebdf30e5570a50631e94f162fbfe4362b60`, and the temporary files were removed.

| Direction | Three sample times | Median throughput | Throughput range |
| --- | --- | ---: | ---: |
| Upload | 17.116 / 17.439 / 17.783 s | 14.68 MiB/s | 14.40–14.96 MiB/s |
| Download | 13.146 / 13.012 / 12.864 s | 19.67 MiB/s | 19.47–19.90 MiB/s |

These repeated SSH results are close to the earlier one-run Cockpit Files measurements (14.44 MiB/s upload and 19.37 MiB/s download). Repeated Cockpit Files samples and an interrupted-upload retry are recorded below. The values characterize this SSH route and local storage at this time only; peak memory during these repeated transfers was not sampled.

## Repeated Cockpit Files transfer and interruption check

On 2026-10-09, a real Chromium browser used Cockpit Files through the SSH recovery tunnel with a disposable non-sudo account. A 268,435,456-byte random file was uploaded three times and downloaded three times. Upload timing ran from clicking Upload through the UI success alert; download timing ran from choosing Download through the completed browser download. Each remote upload and local download had the exact size and SHA-256 `80af0dee6c031bcf6fb11aa1600abf37c7755508bf26f13c2bc39f144392d511`.

| Direction | Three sample times | Median throughput | Throughput range |
| --- | --- | ---: | ---: |
| Cockpit upload | 22.355 / 18.142 / 18.154 s | 14.10 MiB/s | 11.45–14.11 MiB/s |
| Cockpit download | 12.949 / 12.938 / 13.230 s | 19.77 MiB/s | 19.35–19.79 MiB/s |

The upload median was about 3.9% slower than the repeated `scp` median above; the download median was about 0.5% faster. The first UI upload was slower than the next two. This small sample is specific to this tunnel and target storage and includes the browser's upload chooser and success alert in upload timing.

For interruption behavior, the browser was closed about three seconds after selecting a separate 256 MiB upload. The requested filename was absent on the target after disconnect. Reconnecting and uploading that file again from the beginning completed in 18.135 s with matching size and SHA-256. No partial file was available to resume in this run. The disposable account, home directory, uploaded/downloaded files, local payload and password file were removed.

## Dashboard open/closed resource sample

On 2026-10-09, the deployed `20261009092950-217379` release (source commit `700f2f6628e03937aeb43da140c0a659e1806e14`) was reached through an SSH tunnel from Chromium. I sampled the dashboard systemd cgroup 12 times with five-second sleeps between samples, first with the browser closed and then with the Home page open. CPU use is the `CPUUsageNSec` delta over the approximately 55-second sample window, expressed as a share of one logical CPU; memory is the median of `MemoryCurrent` samples.

| State | Dashboard cgroup CPU | Median cgroup memory |
| --- | ---: | ---: |
| Browser closed | 2.1% of one CPU | 52,406,272 bytes (50.0 MiB) |
| Home page open | 3.4% of one CPU | 53,340,160 bytes (50.9 MiB) |

The page-open sample briefly peaked at 61,485,056 bytes (58.6 MiB) during initial loading. Chromium reported no console errors or warnings. This is one 55-second low-load sample per state; it includes scheduled collectors and systemd cgroup accounting, and does not isolate individual requests or establish a long-term idle baseline. Repeat it across longer intervals before making optimization decisions.

## Repeated dashboard open/closed resource sample

On 2026-10-09, deployed release `20261009101431-248479` (source commit `73fb4ebfb816a8a0e86f816a8a54e39ec78f5de2`) was sampled through the SSH recovery tunnel. Each state ran for 301 seconds with 61 samples five seconds apart. CPU is the `cpu.stat` usage delta divided by elapsed time, as a share of one logical CPU. Memory is from the dashboard's systemd cgroup; the browser was fully closed for the first interval and Chromium kept the Home page open at its default five-second refresh for the second.

| State | Dashboard cgroup CPU | Median memory | 95th percentile | Peak memory |
| --- | ---: | ---: | ---: | ---: |
| Browser closed | 1.77% of one CPU | 51,957,760 bytes (49.5 MiB) | 52,514,816 bytes (50.1 MiB) | 52,760,576 bytes (50.3 MiB) |
| Home page open | 2.77% of one CPU | 52,600,832 bytes (50.2 MiB) | 55,083,008 bytes (52.5 MiB) | 55,832,576 bytes (53.3 MiB) |

The browser-open interval used the Mac's installed Chrome through the SSH tunnel and rendered the deployed Home view successfully. It reported no page or console errors. The tunnel was closed afterward; the target dashboard service remained active and its health endpoint returned `{"ok":true}`. This is a low-load sample of one client and one five-second refresh setting; it includes the dashboard's scheduled collectors and does not model concurrent clients or application workloads.

## Network rate counter cross-check under transfer

On 2026-10-09, a 268,435,456-byte random file was uploaded from the Mac to the Dell with `scp` in 17.778 seconds. The local and remote SHA-256 values matched. A server-side sampler polled `/api/metrics` every five seconds for about 70 seconds and read `/proc/net/dev` immediately after each API sample for the same detected, up, device-backed interface. Across the three complete five-second windows during the upload, the median dashboard receive rate was 16,494,737 bytes/s and the independent counter rate was 16,460,696 bytes/s; the median absolute per-window difference was 0.49%. Transmit rates were 53,588 and 53,224 bytes/s, respectively, with a 0.38% median absolute difference. The API and counter sample boundaries were offset by the time needed to make the local API request, so this verifies close agreement during sustained traffic on this host and path, not a universal accuracy bound. The temporary file was removed.

## Swap and memory-pressure snapshot

On 2026-10-09, the Dell running dashboard release `20261009140922-393650` reported 15.31 GiB RAM, 12.14 GiB available, and 4.21 GiB used on its existing 15.69 GiB disk swap partition. `/proc/swaps` listed only `/dev/nvme0n1p3`; no ZRAM device or loaded `zram` module was present. `vm.swappiness` remained `1`. Linux memory PSI reported `0.00%` for `some` and `full` pressure over each of its 10-, 60-, and 300-second windows. Existing swap use therefore did not coincide with observed memory stalls, and this idle snapshot does not justify adding ZRAM or changing the host swap policy. Repeat the measurement during an authenticated inference workload before reconsidering memory-compression changes; no swap configuration was changed for this check.

## Still to measure

- Owner-specific Cockpit login and permission changes remain unverified. Repeated 256 MiB Cockpit Files and `scp` throughput samples passed integrity checks; a browser-disconnected upload left no file with the requested name, and a fresh full retry succeeded. A resumable partial transfer was not available in that run. The 16-GiB integrity run completed through a disposable account. A small copy/paste and download check passed. The companion Move files page passed no-overwrite and cross-filesystem moves; a 3 MiB file retained its SHA-256 and the source disappeared. A disposable non-sudo account changed its own file mode 0664→0464→0664.
- WireGuard latency and throughput after owner setup and an external handshake. Tailscale Serve remains disabled.
- Provider request latency and memory under authenticated LiteLLM / OmniRoute traffic.
- OmniRoute dashboard navigation and API timing through the SSH tunnel after owner login.
- LiteLLM admin UI navigation, provider setup, and model management after owner sign-in.

Repeat the measurements after material changes and record the exact commit, target state, sample length, and whether the browser was open.
