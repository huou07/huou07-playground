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

On 2026-10-09, the dashboard was sampled from the Mac through a verified SSH tunnel to the Dell. Eight requests per route were measured; the first request is reported separately and the warm median uses the remaining seven. Each response returned HTTP 200. The browser was not used for this timing sample, so render and interaction time are excluded.

| Route | Response bytes | First request | Warm median |
| --- | ---: | ---: | ---: |
| `/` | 19,728 | 26.8 ms | 13.6 ms |
| `/api/health` | 11 | 12.0 ms | 11.5 ms |
| `/api/metrics` | 1,400 | 108.6 ms | 15.6 ms |
| `/api/apps` | 1,235 | 32.9 ms | 31.8 ms |
| `/api/vpn` | 224 | 53.4 ms | 50.8 ms |

At the same sample, systemd cgroups for the dashboard, OpenCode Web, LiteLLM, OmniRoute, and wg-easy reported 1,313,619,968 bytes (about 1.22 GiB) combined. Each unit was active. This is the listed huou07 service set only; it excludes Cockpit, host services, and unrelated workloads. The API medians include SSH forwarding and local network round-trip time, unlike the earlier server-loopback measurements.

## Still to measure

- Rendered page load and navigation interaction time through the SSH tunnel, with repeated browser runs.
- CPU and memory with the dashboard open versus closed over longer samples.
- File upload and download throughput, including a test larger than available RAM, through Cockpit Files after the owner signs in.
- WireGuard latency and throughput after owner setup and an external handshake. Tailscale Serve remains disabled.
- Provider request latency and memory under authenticated LiteLLM / OmniRoute traffic.
- OmniRoute dashboard navigation and API timing through the SSH tunnel after owner login.
- LiteLLM admin UI navigation, provider setup, and model management after owner sign-in.

Repeat the measurements after material changes and record the exact commit, target state, sample length, and whether the browser was open.
