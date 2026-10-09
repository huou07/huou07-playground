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

The live i915 sample reported 0% engine utilization while idle. For an active check, an 8-second, 1280×720, 30 fps VAAPI encode to FFmpeg's null output ran in a temporary systemd unit as the unprivileged dashboard account. The unit had only the `video` and `render` supplementary groups, access to `/dev/dri/renderD128`, no network sockets, a 50% CPU quota, a 256 MiB memory cap, and a 12-second runtime limit. FFmpeg exited successfully; the existing restricted GPU collector sampled Video at 3.8%, with Blitter, Render/3D, and VideoEnhance at 0%. A follow-up sample returned all engines to 0.0%. This verifies active Video-engine telemetry; a Render/3D workload remains untested. No GPU temperature interface was reported. The restricted CPU package collector reported 6.5 W for `PkgWatt`. Network rates were 26.3/40.8 Kbps from the endpoint and 20.6/26.9 Kbps from an independent two-second physical-interface counter sample. That short comparison is noisy because the API and direct sample windows differ; repeat it over longer intervals before drawing a rate-accuracy conclusion.

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

## Still to measure

- Repeated initial-page browser load samples and dashboard-open versus closed CPU/memory over longer intervals.
- CPU and memory with the dashboard open versus closed over longer samples.
- Exact Cockpit Files upload/download throughput and behavior after interruption or resume. The 16-GiB integrity run completed through a disposable account; the owner's own permissions and copy/move workflow remain untested.
- WireGuard latency and throughput after owner setup and an external handshake. Tailscale Serve remains disabled.
- Provider request latency and memory under authenticated LiteLLM / OmniRoute traffic.
- OmniRoute dashboard navigation and API timing through the SSH tunnel after owner login.
- LiteLLM admin UI navigation, provider setup, and model management after owner sign-in.

Repeat the measurements after material changes and record the exact commit, target state, sample length, and whether the browser was open.
